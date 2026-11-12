"""Owned, non-blocking Codex CLI processes backed by ChatGPT login."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from core.process_tree import (CREATE_SUSPENDED, OwnedCleanupUnconfirmed,
                               bind_kill_on_close_job, close_process_job,
                               owned_cleanup_pending, stop_process_tree,
                               wait_for_owned_cleanup,
                               wait_process_with_job_sync)


class CodexRuntime:
    TERMINAL = {"completed", "failed", "cancelled"}
    SUPPORTED_EFFORTS = ["low", "medium", "high", "xhigh", "max", "ultra"]
    PROBE_TTL = 300.0
    _SHARED_PROBE_CACHE: dict[str, tuple[float, dict]] = {}
    _SCRATCH_WORKSPACE_PREFIXES = (
        "quartz-chat-tool-",
        "quartz-desktop-task-",
        "quartz-rea-readonly-",
    )

    def __init__(self, executable=None):
        self.executable = None
        self._init_error = ""
        try:
            self.executable = self._find_executable(executable)
        except Exception as exc:
            self._init_error = str(exc)
        self.lock = self._lock = threading.RLock()
        self._runs = {}
        self._processes = {}
        self._writers = {}
        shared = self._SHARED_PROBE_CACHE.get(str(self.executable or ""))
        if shared and (time.monotonic() - shared[0] < self.PROBE_TTL):
            self._probe_cache: tuple[float, dict] = (shared[0], dict(shared[1]))
        else:
            self._probe_cache = (0.0, {})

    @staticmethod
    def _find_executable(explicit=None) -> str:
        from core.cli_installer import resolve_cli
        try:
            return resolve_cli("codex", explicit)
        except FileNotFoundError:
            pass
        bundled = []
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            bin_root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            try:
                bundled = sorted(
                    bin_root.glob("*/codex.exe"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            except OSError:
                bundled = []
        candidates = [
            explicit, os.getenv("QUARTZ_CODEX_PATH"), shutil.which("codex.exe"),
            *bundled, shutil.which("codex.cmd"), shutil.which("codex"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        raise FileNotFoundError("Codex CLI was not found")

    def list_models(self, force: bool = False) -> dict:
        """Discover real Codex models and reasoning efforts from local Codex CLI configuration and cache."""
        codex_home = Path(os.getenv("CODEX_HOME") or (Path.home() / ".codex"))
        default_model = "gpt-6.1-sol"
        default_effort = "low"
        config_path = codex_home / "config.toml"
        if config_path.is_file():
            try:
                for raw_line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = raw_line.strip()
                    if line.startswith("model") and "=" in line and not line.startswith("model_"):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            default_model = val
                    elif line.startswith("model_reasoning_effort") and "=" in line:
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            default_effort = val
            except OSError:
                pass

        models = []
        seen = set()
        cache_path = codex_home / "models_cache.json"
        if cache_path.is_file():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8", errors="replace"))
                raw_models = payload.get("models") if isinstance(payload, dict) else []
                for item in raw_models or []:
                    if not isinstance(item, dict):
                        continue
                    slug = str(item.get("slug") or item.get("id") or "").strip()
                    if not slug or slug in seen:
                        continue
                    visibility = str(item.get("visibility") or "list").lower()
                    if visibility == "hide" and slug != default_model:
                        continue
                    efforts = [
                        str(e.get("effort")).strip()
                        for e in (item.get("supported_reasoning_levels") or [])
                        if isinstance(e, dict) and e.get("effort")
                    ] or list(self.SUPPORTED_EFFORTS)
                    models.append({
                        "id": slug,
                        "label": str(item.get("display_name") or slug),
                        "efforts": efforts,
                        "default_effort": str(item.get("default_reasoning_level") or default_effort),
                    })
                    seen.add(slug)
            except Exception:
                pass

        if default_model and default_model not in seen:
            models.insert(0, {
                "id": default_model,
                "label": default_model,
                "efforts": list(self.SUPPORTED_EFFORTS),
                "default_effort": default_effort,
            })

        return {
            "default_model": default_model,
            "default_effort": default_effort,
            "efforts": list(self.SUPPORTED_EFFORTS),
            "models": models,
        }

    def probe(self, force: bool = False) -> dict:
        if not self.executable:
            return {
                "installed": False,
                "version": "",
                "executable": None,
                "authenticated": False,
                "authentication": "required",
                "ready": False,
                "error": self._init_error or "Codex CLI was not found",
            }
        now = time.monotonic()
        cache_key = str(self.executable or "")
        with self._lock:
            cached_at, cached = self._probe_cache
            if not cached and cached_at == 0.0:
                shared = self._SHARED_PROBE_CACHE.get(cache_key)
                if shared and (now - shared[0] < self.PROBE_TTL):
                    cached_at, cached = shared[0], dict(shared[1])
                    self._probe_cache = (cached_at, dict(cached))
            if not force and cached and (now - cached_at < self.PROBE_TTL):
                return dict(cached)

        version = self._probe(["--version"])
        login = self._probe(["login", "status"])
        login_text = (login["stdout"] + "\n" + login["stderr"]).strip()
        authenticated = login["returncode"] == 0 and "logged in" in login_text.lower()
        method = "chatgpt" if "chatgpt" in login_text.lower() else "unknown"
        result = {
            "installed": version["returncode"] == 0,
            "version": version["stdout"].strip(),
            "executable": self.executable,
            "authenticated": authenticated,
            "authentication": method if authenticated else "required",
            "ready": version["returncode"] == 0 and authenticated,
            "error": "" if authenticated else (login_text or "Authentication required"),
        }
        with self._lock:
            stamp = time.monotonic()
            self._probe_cache = (stamp, dict(result))
            self._SHARED_PROBE_CACHE[cache_key] = (stamp, dict(result))
        return result

    @staticmethod
    def _parse_timeout_seconds(timeout):
        if timeout is None:
            return None  # Existing callers had no implicit Codex deadline.
        import math
        if isinstance(timeout, bool):
            raise ValueError("Invalid task timeout")
        raw = str(timeout).strip().lower()
        units = (("ms", .001), ("s", 1), ("m", 60), ("h", 3600))
        multiplier = 1
        for suffix, factor in units:
            if raw.endswith(suffix):
                raw, multiplier = raw[:-len(suffix)], factor
                break
        value = float(raw) * multiplier
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid task timeout")
        return max(1.0, value)

    @staticmethod
    def _next_oracle_seq(record: dict) -> int:
        seq = int(record.get("_oracle_seq", 0)) + 1
        record["_oracle_seq"] = seq
        return seq

    @classmethod
    def _is_scratch_workspace_path(cls, project_path: str | Path, file_path: str, *, tool_guard: bool = False) -> bool:
        if tool_guard:
            return False
        try:
            proj = Path(project_path).resolve()
            temp_root = Path(tempfile.gettempdir()).resolve()
        except (OSError, ValueError):
            return False
        if proj.parent != temp_root or not proj.name.lower().startswith(cls._SCRATCH_WORKSPACE_PREFIXES):
            return False
        raw = str(file_path or "").strip()
        if not raw:
            return True
        try:
            candidate = Path(raw)
            target = (candidate if candidate.is_absolute() else (proj / candidate)).resolve()
            target.relative_to(proj)
            return True
        except (OSError, ValueError):
            return False

    PROJECT_READ_FEATURES_OFF = ("shell_tool", "unified_exec", "apps", "plugins", "multi_agent",
                                 "multi_agent_v2", "computer_use", "browser_use", "browser_use_external",
                                 "in_app_browser", "image_generation", "view_image", "memories", "hooks")

    def _project_read_config(self, read_root, cwd, should_abort=None):
        """Config flags that leave ONLY quartz_project enabled, proven with `codex mcp list`.

        The effective MCP set also comes from plugins and other layers (a live
        probe found node_repl/cua_repl beside the user TOML), so the set is read
        back with the same flags; anything still enabled besides quartz_project
        is disabled by name and re-checked, and the start is refused otherwise.
        """
        import json as _json
        import re as _re
        from core.project_read_mcp import codex_override
        flags = []
        for feature in self.PROJECT_READ_FEATURES_OFF:
            flags += ["-c", f"features.{feature}=false"]
        flags += ["-c", 'web_search="disabled"', "-c", codex_override(read_root)]

        def enabled_extra(current):
            from core.cli_installer import cli_environment
            if should_abort and should_abort():
                raise RuntimeError("Project read cancelled before start")
            probe = subprocess.run(self._command(current + ["mcp", "list", "--json"]), cwd=str(cwd),
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=30, env=cli_environment(),
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if probe.returncode != 0:
                raise RuntimeError("Cannot verify Codex's effective MCP servers")
            servers = _json.loads(probe.stdout)
            if not isinstance(servers, list):
                raise RuntimeError("Unexpected Codex MCP listing")
            # Every row must state its name and enabled flag; an unknown state is a refusal.
            if not all(isinstance(s, dict) and isinstance(s.get("name"), str)
                       and isinstance(s.get("enabled"), bool) for s in servers):
                raise RuntimeError("Codex MCP listing has an entry of unknown state")
            names = [s["name"] for s in servers if s["enabled"]]
            if "quartz_project" not in names:
                raise RuntimeError("Quartz project tools are not active in Codex")
            return [n for n in names if n != "quartz_project"]

        extra = enabled_extra(flags)
        for name in extra:
            if not isinstance(name, str) or not _re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise RuntimeError("Cannot safely disable an inherited MCP server")
            flags += ["-c", f"mcp_servers.{name}.enabled=false"]
        if extra and enabled_extra(flags):
            raise RuntimeError("Codex keeps other MCP servers enabled; project read refused")
        return flags

    def start(self, prompt, project_path, *, sandbox="read-only", approval="never",
              squad_task_id=None, squad_agent_id=None, resume_thread_id=None,
              timeout=None, model: str | None = None, effort: str | None = None,
              desktop_connection=None, tool_guard=False, project_read=False, should_abort=None) -> dict:
        if not self.executable:
            raise RuntimeError(self._init_error or "Codex CLI was not found")
        text = str(prompt or "").strip()
        if not text:
            raise ValueError("Codex prompt cannot be empty")
        if len(text) > 100_000:
            raise ValueError("Codex prompt is too long")
        if sandbox not in {"read-only", "workspace-write", "danger-full-access"}:
            raise ValueError("Unsupported Codex sandbox")
        if approval not in {"never", "on-request"}:
            raise ValueError("Unsupported approval policy")
        # Profiles are validated before any run/writer is registered so a
        # refused request leaves no record or project lock behind.
        if tool_guard and (desktop_connection is not None or sandbox != "read-only"):
            raise ValueError("Log observer cannot receive desktop/write permissions")
        # project_read is the project ROOT to expose through Quartz's own
        # read-only MCP tools; the Codex process itself runs elsewhere with
        # every built-in tool (shell included) disabled.
        read_root = None
        if project_read:
            if (tool_guard or desktop_connection is not None or sandbox != "read-only"
                    or approval != "never" or resume_thread_id):
                raise ValueError("Project-read runs are read-only, fresh and tool-scoped")
            read_root = Path(project_read).resolve(strict=True)
            if not read_root.is_dir():
                raise NotADirectoryError(str(read_root))
        project = Path(project_path).resolve(strict=True)
        if not project.is_dir():
            raise NotADirectoryError(str(project))
        if read_root:
            # Resolve the helper/config and PROVE the effective tool set now: a
            # failure must not leave a "starting" record without a process.
            read_config = self._project_read_config(read_root, project, should_abort)

        clean_model = str(model or "").strip() or None
        clean_effort = str(effort or "").strip().lower() or None
        if clean_effort and clean_effort not in self.SUPPORTED_EFFORTS:
            raise ValueError(f"Unsupported Codex reasoning effort: {clean_effort}")

        is_writer = sandbox in {"workspace-write", "danger-full-access"}
        run_id = uuid.uuid4().hex
        project_key = os.path.normcase(str(project))
        started_wall = time.time()
        timeout_seconds = self._parse_timeout_seconds(timeout)
        with self._lock:
            if is_writer and project_key in self._writers:
                raise RuntimeError("This project already has an active write-capable agent")
            record = {
                "id": run_id, "status": "starting", "pid": None,
                "project": str(project), "sandbox": sandbox,
                "approval": approval, "started_at": started_wall,
                "timeout_seconds": timeout_seconds,
                "first_event_at": None, "first_text_at": None,
                "finished_at": None, "exit_code": None, "thread_id": None,
                "model": clean_model, "effort": clean_effort,
                "result": "", "errors": [], "events": [], "usage": None,
                "commands": [], "command_results": [], "command_exit_codes": [],
                "files_changed": [], "scratch_files_changed": [], "file_changes": [],
                "unauthorized_write_detected": False, "unauthorized_files_changed": [],
                "error_events": [],
                "job_bound": False, "job_assignment_error": "",
                "squad_task_id": squad_task_id,
                "squad_agent_id": squad_agent_id,
                "cancel_requested": False,
                "_oracle_seq": 0,
                "_tool_guard": bool(tool_guard),
                "_project_read": str(read_root) if read_root else None,
            }
            self._runs[run_id] = record
            if is_writer:
                self._writers[project_key] = run_id

        if read_root:
            # Project read runs over app-server so the verified tool set is the
            # SAME session that receives the prompt (Codex owner review).
            return self._start_project_session(run_id, record, project, read_config, text,
                                               clean_model, clean_effort, timeout_seconds, should_abort)

        # `exec` has no interactive approval channel. Automatic review keeps
        # workspace-write inside the CLI sandbox without silently denying
        # every normal build/test tool request.
        common = ["--cd", str(project)]
        if sandbox == "danger-full-access":
            common.append("--dangerously-bypass-approvals-and-sandbox")
        elif sandbox == "workspace-write" and approval == "on-request":
            common.append("--approve-for-me")
        else:
            common += ["--ask-for-approval", approval, "--sandbox", sandbox]
        if clean_model:
            common += ["-m", clean_model]
        if clean_effort:
            common += ["-c", f'model_reasoning_effort="{clean_effort}"']
        if read_root:
            common += read_config  # verified effective tool set (see _project_read_config)
        elif tool_guard or desktop_connection is not None:
            # Per-run only: no user config changes. Disable inherited integrations
            # as well as shell/browser/desktop capabilities.
            for feature in ("shell_tool", "unified_exec", "apps", "plugins", "multi_agent",
                            "multi_agent_v2", "computer_use", "browser_use", "browser_use_external",
                            "in_app_browser", "image_generation", "view_image", "memories"):
                common += ["-c", f"features.{feature}=false"]
            common += ["-c", 'web_search="disabled"']
            import tomllib
            config_path = Path(os.getenv("CODEX_HOME") or Path.home()/".codex")/"config.toml"
            configuration = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
            for name in configuration.get("mcp_servers", {}):
                import re
                if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                    raise ValueError("Cannot safely override this inherited MCP name")
                common += ["-c", "mcp_servers." + name + ".enabled=false"]
        desktop_env = None
        if desktop_connection is not None:
            from core.desktop_agents import codex_mcp_override, connection_environment
            common += ["-c", codex_mcp_override(desktop_connection)]
            desktop_env = connection_environment(desktop_connection)
        common.append("exec")

        if resume_thread_id:
            resume_opts = ["--json", "--skip-git-repo-check"]
            if clean_model:
                resume_opts += ["-m", clean_model]
            if clean_effort:
                resume_opts += ["-c", f'model_reasoning_effort="{clean_effort}"']
            args = common + [
                "resume", *resume_opts,
                str(resume_thread_id), "-",
            ]
        else:
            args = common + ["--json", "--skip-git-repo-check", "-"]
        command = self._command(args)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | CREATE_SUSPENDED
        job_errors: list[str] = []
        if should_abort and should_abort():
            # Stop arrived while the project-read checks ran: no process starts.
            with self._lock:
                record["status"] = "cancelled"
                record["finished_at"] = time.time()
                record.update(cleanup_pending=False, process_exit_confirmed=True)
                if self._writers.get(project_key) == run_id:
                    self._writers.pop(project_key, None)
            raise RuntimeError("Codex run cancelled before start")
        try:
            from core.cli_installer import cli_environment
            process_options = {"env": desktop_env if desktop_env is not None else cli_environment()}
            process = subprocess.Popen(
                command, cwd=str(project), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", creationflags=flags,
                **process_options,
            )
            job_bound = bind_kill_on_close_job(process, resume=True, error_sink=job_errors.append)
        except Exception:
            with self._lock:
                record["status"] = "failed"
                record["finished_at"] = time.time()
                if self._writers.get(project_key) == run_id:
                    self._writers.pop(project_key, None)
            raise

        try:
            process.stdin.write(text)
            process.stdin.close()
        except Exception:
            process.terminate()
            with self._lock:
                record["status"] = "failed"
                record["finished_at"] = time.time()
                if self._writers.get(project_key) == run_id:
                    self._writers.pop(project_key, None)
            raise

        with self._lock:
            record["pid"] = process.pid
            record["job_bound"] = bool(job_bound)
            if job_errors:
                record["job_assignment_error"] = job_errors[-1]
                seq = self._next_oracle_seq(record)
                record.setdefault("error_events", []).append({
                    "seq": seq,
                    "source": "job_object",
                    "kind": "job_assignment_failed",
                    "tool": None,
                    "command": None,
                    "exit_code": None,
                    "message": job_errors[-1],
                })
            record["status"] = "running"
            self._processes[run_id] = process
        stdout_thread = threading.Thread(
            target=self._read_stdout, args=(run_id, process),
            name=f"codex-out-{run_id[:8]}", daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stderr, args=(run_id, process),
            name=f"codex-err-{run_id[:8]}", daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        threading.Thread(
            target=self._wait,
            args=(run_id, process, project_key, stdout_thread, stderr_thread),
            name=f"codex-wait-{run_id[:8]}", daemon=True,
        ).start()
        return self.get(run_id)

    def _start_project_session(self, run_id, record, project, read_config, text,
                               model, effort, timeout_seconds, should_abort):
        """Spawn `codex app-server` with the project-read config and drive one verified turn."""
        from core.cli_installer import cli_environment
        from core.codex_project_session import AppServerSession, SessionRefused, ALLOWED_SERVER, ALLOWED_TOOLS

        def read_root_of(rec):
            return rec.get("_project_read")

        def finish(status, error=None, *, no_process=False):
            with self._lock:
                if no_process:  # nothing was spawned, so there is nothing left to stop
                    record.update(cleanup_pending=False, process_exit_confirmed=True)
                if record["status"] not in self.TERMINAL:
                    record["status"] = "cancelled" if record.get("cancel_requested") else status
                if error and record["status"] != "cancelled":
                    record["errors"].append(str(error)[:500])
                record["finished_at"] = record.get("finished_at") or time.time()

        if should_abort and should_abort():
            finish("cancelled", no_process=True)
            raise RuntimeError("Codex run cancelled before start")
        args = list(read_config)
        if effort:
            args += ["-c", f'model_reasoning_effort="{effort}"']
        command = self._command(args + ["app-server"])
        job_errors: list[str] = []
        try:
            process = subprocess.Popen(
                command, cwd=str(project), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | CREATE_SUSPENDED,
                env=cli_environment())
            job_bound = bind_kill_on_close_job(process, resume=True, error_sink=job_errors.append)
        except Exception as exc:
            finish("failed", exc, no_process=True)
            raise
        with self._lock:
            record["pid"] = process.pid
            record["job_bound"] = bool(job_bound)
            if job_errors:
                record["job_assignment_error"] = job_errors[-1]
            record["status"] = "running"
            record["transport"] = "app-server"
            record["process_exit_confirmed"] = False
            self._processes[run_id] = process

        def note(event):
            with self._lock:
                record["events"].append(event)

        def drive():
            deadline = time.monotonic() + float(timeout_seconds or 900)
            outcome = ["failed", None]  # decided here, reported only after the process is gone
            try:
                session = AppServerSession(process, on_event=note)
                thread_id = session.open_verified_thread(cwd=project, model=model, should_abort=should_abort,
                                                         expected_root=read_root_of(record))
                with self._lock:
                    record["thread_id"] = thread_id
                    record["first_event_at"] = record.get("first_event_at") or time.time()
                    record["tool_set_verified"] = True
                if should_abort and should_abort():
                    raise SessionRefused("Cancelled before the prompt was delivered")
                params = {"threadId": thread_id, "input": [{"type": "text", "text": text}]}
                if effort:
                    params["effort"] = effort
                session.request("turn/start", params)
                final_text, last_text = "", ""
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Project read timed out")
                    message = session.next_notification(min(remaining, 5))
                    if message is None:
                        if process.poll() is not None:
                            raise SessionRefused("Codex app-server exited")
                        continue
                    method = message.get("method")
                    params_in = message.get("params") or {}
                    if method == "item/completed":
                        item = params_in.get("item") or {}
                        kind = item.get("type")
                        if kind == "agentMessage":
                            last_text = str(item.get("text") or "")
                            if item.get("phase") == "final_answer":
                                final_text = last_text
                            with self._lock:
                                record["first_text_at"] = record.get("first_text_at") or time.time()
                        elif kind == "mcpToolCall":
                            server, tool = item.get("server"), item.get("tool")
                            note({"type": "mcp_tool_call", "server": server, "tool": tool,
                                  "status": item.get("status")})
                            if server != ALLOWED_SERVER or tool not in ALLOWED_TOOLS:
                                raise SessionRefused(f"Tool outside Quartz read set: {server}/{tool}")
                        elif kind not in {"userMessage", "reasoning"}:
                            # commandExecution, fileChange, webSearch, ... are not part of a project read.
                            note({"type": "unexpected_item", "item_type": str(kind)[:60]})
                            raise SessionRefused(f"Unexpected Codex action in a project read: {kind}")
                    elif method == "turn/completed":
                        turn = params_in.get("turn") or {}
                        with self._lock:
                            record["result"] = final_text or last_text
                        status = turn.get("status")
                        outcome[:] = (["completed", None] if status == "completed"
                                      else ["failed", f"Turn ended: {status} {turn.get('error')}"])
                        return
            except Exception as exc:
                outcome[:] = ["failed", exc]
            finally:
                # Completion is reported only after the owned process tree is gone;
                # an unconfirmed cleanup keeps ownership so shutdown() still sees it.
                with self._lock:
                    record["cleanup_pending"] = True
                try:
                    stop_process_tree(process, timeout=5)
                except Exception:
                    pass
                try:
                    wait_for_owned_cleanup(process, lambda: None)
                    cleaned = True
                except Exception:
                    cleaned = False
                with self._lock:
                    record["cleanup_pending"] = not cleaned
                    # The chat's stop receipt waits on this exact flag (Gemini review).
                    record["process_exit_confirmed"] = cleaned
                    if cleaned:
                        record["exit_code"] = process.poll()
                        self._processes.pop(run_id, None)
                if cleaned:
                    finish(*outcome)
                else:
                    finish("failed", "Codex app-server cleanup is not confirmed")

        threading.Thread(target=drive, name=f"codex-read-{run_id[:8]}", daemon=True).start()
        return self.get(run_id)

    def resume(self, run_id, prompt, *, model: str | None = None, effort: str | None = None) -> dict:
        previous = self.get(run_id)
        with self._lock:
            raw = self._runs.get(run_id, {})
            scoped = bool(raw.get("_project_read") or raw.get("_tool_guard"))
        if scoped:
            # This generic resume would not carry the run's tool profile.
            raise PermissionError("A project-read or guarded Codex run cannot be resumed")
        thread_id = previous.get("thread_id")
        if not thread_id:
            raise RuntimeError("The Codex thread id is not available")
        if previous["status"] not in self.TERMINAL:
            raise RuntimeError("Cannot resume a running Codex task")
        return self.start(
            prompt, previous["project"], sandbox=previous["sandbox"],
            approval=previous["approval"],
            squad_task_id=previous.get("squad_task_id"),
            squad_agent_id=previous.get("squad_agent_id"),
            resume_thread_id=thread_id,
            model=model or previous.get("model"),
            effort=effort or previous.get("effort"),
        )

    def get(self, run_id) -> dict:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(f"Unknown Codex run: {run_id}")
            record = self._runs[run_id]
            value = {k: v for k, v in record.items() if not str(k).startswith("_")}
            value["errors"] = list(record["errors"][-20:])
            value["events"] = list(record["events"][-100:])
            value["commands"] = [dict(item) for item in record.get("commands", [])[-30:]]
            value["command_results"] = [dict(item) for item in record.get("command_results", [])[-50:]]
            value["command_exit_codes"] = list(record.get("command_exit_codes", [])[-50:])
            value["files_changed"] = list(record.get("files_changed", []))
            value["scratch_files_changed"] = list(record.get("scratch_files_changed", []))
            value["file_changes"] = [dict(item) for item in record.get("file_changes", [])[-100:]]
            value["unauthorized_files_changed"] = list(record.get("unauthorized_files_changed", []))
            value["error_events"] = [dict(item) for item in record.get("error_events", [])[-50:]]
            return value

    def list(self, limit=20) -> list[dict]:
        with self._lock:
            ids = list(self._runs)[-max(1, int(limit)):]
        return [self.get(run_id) for run_id in reversed(ids)]

    def cancel(self, run_id, timeout=5) -> dict:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(f"Unknown Codex run: {run_id}")
            record = self._runs[run_id]
            process = self._processes.get(run_id)
            if record["status"] in self.TERMINAL:
                return self.get(run_id)
            record["cancel_requested"] = True
            record["status"] = "cancelling"
        if owned_cleanup_pending(process):
            stop_process_tree(process, timeout=max(1, timeout))
        return self.get(run_id)

    def shutdown(self):
        with self._lock:
            owned = list(self._processes.items())
        for run_id, process in owned:
            if owned_cleanup_pending(process):
                self.cancel(run_id)
        # Sending Stop is not proof that an owned process actually exited.
        for _, process in owned:
            if owned_cleanup_pending(process):
                raise RuntimeError("Owned runtime cleanup is not confirmed")

    def _command(self, args):
        suffix = Path(self.executable).suffix.lower()
        if suffix in {".js", ".mjs", ".cjs"}:
            from core.cli_installer import node_command
            return node_command(self.executable, args)
        if os.name == "nt" and suffix in {".cmd", ".bat"}:
            if suffix == ".cmd":
                try:
                    from core.cli_installer import node_command
                    return node_command(self.executable, args)
                except Exception:
                    pass
            command_text = subprocess.list2cmdline([self.executable, *args])
            return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command_text]
        return [self.executable, *args]

    def _probe(self, args) -> dict:
        from core.cli_installer import cli_environment
        try:
            completed = subprocess.run(
                self._command(args), stdin=subprocess.DEVNULL,
                env=cli_environment(),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        except Exception as exc:
            return {"returncode": -1, "stdout": "", "stderr": str(exc)}

    def _read_stdout(self, run_id, process):
        if process.stdout is None:
            return
        try:
            for raw in process.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"type": "raw", "text": line}
                with self._lock:
                    record = self._runs.get(run_id)
                    if not record:
                        continue
                    is_terminal = record.get("status") in self.TERMINAL
                    if is_terminal:
                        continue  # A terminal receipt/session identity is immutable.
                    if not is_terminal and record.get("first_event_at") is None:
                        record["first_event_at"] = time.time()
                    record["events"].append(event)
                    event_type = event.get("type")
                    if event_type == "thread.started":
                        record["thread_id"] = event.get("thread_id")
                    elif event_type == "item.completed":
                        item = event.get("item") or {}
                        item_type = item.get("type")
                        if item_type == "agent_message":
                            text_val = str(item.get("text") or "")
                            if not is_terminal:
                                if text_val and record.get("first_text_at") is None:
                                    record["first_text_at"] = time.time()
                                record["result"] = text_val
                        elif item_type == "error":
                            msg = str(item.get("message") or "Codex error")
                            record["errors"].append(msg)
                            seq = self._next_oracle_seq(record)
                            record.setdefault("error_events", []).append({
                                "seq": seq,
                                "source": "item.error",
                                "kind": "item_error",
                                "tool": None,
                                "command": None,
                                "exit_code": None,
                                "message": msg,
                            })
                        elif item_type == "command_execution":
                            cmd_str = str(item.get("command") or "")[:1000]
                            raw_exit = item.get("exit_code")
                            exit_code = int(raw_exit) if isinstance(raw_exit, int) and not isinstance(raw_exit, bool) else None
                            out_str = str(item.get("aggregated_output") or "")[:4000]
                            item_status = str(item.get("status") or ("completed" if exit_code == 0 else "failed")).lower()
                            state_str = "DONE" if (exit_code == 0 and item_status not in {"failed", "declined", "error"}) else "ERROR"
                            seq = self._next_oracle_seq(record)
                            record["commands"].append({
                                "command": cmd_str,
                                "exit_code": exit_code,
                                "output": out_str,
                            })
                            record.setdefault("command_exit_codes", []).append(exit_code)
                            record.setdefault("command_results", []).append({
                                "seq": seq,
                                "tool": "command_execution",
                                "command": cmd_str,
                                "exit_code": exit_code,
                                "ok": exit_code == 0 and state_str == "DONE",
                                "state": state_str,
                                "output": out_str,
                                "error": "" if exit_code == 0 and state_str == "DONE" else (out_str[:1000] or f"Command exited with code {exit_code}"),
                            })
                            if exit_code not in (None, 0) or state_str == "ERROR":
                                record.setdefault("error_events", []).append({
                                    "seq": seq,
                                    "source": "command",
                                    "kind": "nonzero_exit" if exit_code not in (None, 0) else "command_error",
                                    "tool": "command_execution",
                                    "command": cmd_str,
                                    "exit_code": exit_code,
                                    "message": out_str[:1000] or f"Command exited with code {exit_code}",
                                })
                        elif item_type == "file_change":
                            item_status = str(item.get("status") or "completed").lower()
                            state_str = "ERROR" if item_status in {"failed", "declined", "error"} else "DONE"
                            for change in item.get("changes") or []:
                                path = str(change.get("path") or "")
                                change_kind = str(change.get("kind") or "update").lower()
                                if path:
                                    seq = self._next_oracle_seq(record)
                                    is_scratch = self._is_scratch_workspace_path(
                                        record.get("project", ""),
                                        path,
                                        tool_guard=bool(record.get("_tool_guard")),
                                    )
                                    record.setdefault("file_changes", []).append({
                                        "seq": seq,
                                        "path": path,
                                        "kind": change_kind,
                                        "tool": "file_change",
                                        "state": state_str,
                                    })
                                    if state_str == "DONE":
                                        if is_scratch:
                                            scratch_list = record.setdefault("scratch_files_changed", [])
                                            if path not in scratch_list:
                                                scratch_list.append(path)
                                        else:
                                            if path not in record["files_changed"]:
                                                record["files_changed"].append(path)
                                            if record.get("sandbox") == "read-only":
                                                record["unauthorized_write_detected"] = True
                                                unauth_list = record.setdefault("unauthorized_files_changed", [])
                                                if path not in unauth_list:
                                                    unauth_list.append(path)
                                                violation_msg = f"Read-only Codex run modified file without write permission: {path}"
                                                record["errors"].append(violation_msg)
                                                record.setdefault("error_events", []).append({
                                                    "seq": seq,
                                                    "source": "sandbox_guard",
                                                    "kind": "unauthorized_readonly_write",
                                                    "tool": "file_change",
                                                    "command": None,
                                                    "exit_code": None,
                                                    "message": violation_msg,
                                                })
                                    elif state_str == "ERROR":
                                        record.setdefault("error_events", []).append({
                                            "seq": seq,
                                            "source": "file_change",
                                            "kind": "file_change_error",
                                            "tool": "file_change",
                                            "command": None,
                                            "exit_code": None,
                                            "message": f"File change failed for {path} ({change_kind})",
                                        })
                    elif event_type == "turn.failed":
                        error_msg = str(event.get("error") or event.get("message") or "Codex turn failed")
                        record["errors"].append(error_msg)
                        seq = self._next_oracle_seq(record)
                        record.setdefault("error_events", []).append({
                            "seq": seq,
                            "source": "turn.failed",
                            "kind": "turn_failed",
                            "tool": None,
                            "command": None,
                            "exit_code": None,
                            "message": error_msg,
                        })
                    elif event_type == "error":
                        error_msg = str(event.get("message") or "Codex error")
                        record["errors"].append(error_msg)
                        seq = self._next_oracle_seq(record)
                        record.setdefault("error_events", []).append({
                            "seq": seq,
                            "source": "stream.error",
                            "kind": "stream_error",
                            "tool": None,
                            "command": None,
                            "exit_code": None,
                            "message": error_msg,
                        })
                    elif event_type == "turn.completed":
                        record["usage"] = event.get("usage")
        except (OSError, ValueError):
            pass

    def _read_stderr(self, run_id, process):
        if process.stderr is None:
            return
        try:
            for raw in process.stderr:
                line = raw.strip()
                if line:
                    with self._lock:
                        record = self._runs.get(run_id)
                        if record:
                            record["errors"].append(line)
                            seq = self._next_oracle_seq(record)
                            record.setdefault("error_events", []).append({
                                "seq": seq,
                                "source": "stderr",
                                "kind": "stderr_line",
                                "tool": None,
                                "command": None,
                                "exit_code": None,
                                "message": line,
                            })
        except (OSError, ValueError):
            pass

    def _wait(self, run_id, process, project_key, stdout_thread, stderr_thread):
        with self._lock:
            timeout_sec = self._runs.get(run_id, {}).get("timeout_seconds")
        timed_out = False
        code = -1
        exit_known = False
        def pending_cleanup():
            with self._lock:
                record = self._runs.get(run_id)
                if record:
                    record.update(status="cancelling", cleanup_pending=True, process_exit_confirmed=False)
        try:
            try:
                code = wait_process_with_job_sync(process, timeout=timeout_sec)
                exit_known = True
            except subprocess.TimeoutExpired:
                timed_out = True
                stop_process_tree(process, timeout=5)
                try:
                    code = process.wait(timeout=5)
                    exit_known = True
                except Exception:
                    code = -1
            if not exit_known or owned_cleanup_pending(process, include_root=False):
                exit_known = False
                code = wait_for_owned_cleanup(process, pending_cleanup)
                exit_known = True
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            with self._lock:
                record = self._runs.get(run_id)
                if record:
                    record.update(cleanup_pending=False, process_exit_confirmed=True)
                    record["exit_code"] = code
                    record["finished_at"] = time.time()
                    if timed_out:
                        msg = f"Task timed out after {timeout_sec:g}s"
                        record["errors"].append(msg)
                        seq = self._next_oracle_seq(record)
                        record.setdefault("error_events", []).append({
                            "seq": seq,
                            "source": "process",
                            "kind": "timeout",
                            "tool": None,
                            "command": None,
                            "exit_code": code,
                            "message": msg,
                        })
                    if record.get("cancel_requested"):
                        record["status"] = "cancelled"
                    elif not timed_out and code == 0 and record.get("result") and not record.get("unauthorized_write_detected"):
                        record["status"] = "completed"
                    else:
                        record["status"] = "failed"
                        if code != 0 and not record["errors"]:
                            msg = f"Process exited with code {code}"
                            record["errors"].append(msg)
                            seq = self._next_oracle_seq(record)
                            record.setdefault("error_events", []).append({
                                "seq": seq,
                                "source": "process",
                                "kind": "process_exit",
                                "tool": None,
                                "command": None,
                                "exit_code": code,
                                "message": msg,
                            })
                        elif code == 0 and not record.get("result") and not record["errors"]:
                            msg = "Codex returned exit code 0 without response output"
                            record["errors"].append(msg)
                            seq = self._next_oracle_seq(record)
                            record.setdefault("error_events", []).append({
                                "seq": seq,
                                "source": "process",
                                "kind": "empty_output",
                                "tool": None,
                                "command": None,
                                "exit_code": code,
                                "message": msg,
                            })
        except Exception as exc:
            with self._lock:
                record = self._runs.get(run_id)
                if record:
                    record["status"] = "failed" if exit_known else "cancelling"
                    record["cleanup_pending"] = not exit_known
                    record["process_exit_confirmed"] = exit_known
                    if exit_known:
                        record["finished_at"] = time.time()
                    if isinstance(exc, OwnedCleanupUnconfirmed):
                        record.update(root_exit_confirmed=True, exit_code=exc.root_returncode,
                                      cleanup_error='tree_discovery_incomplete')
                        msg = "Ana süreç durdu; alt süreçlerin kapanışı doğrulanamadı."
                        record["errors"].append(msg)
                        seq = self._next_oracle_seq(record)
                        record.setdefault("error_events", []).append({
                            "seq": seq,
                            "source": "process",
                            "kind": "cleanup_unconfirmed",
                            "tool": None,
                            "command": None,
                            "exit_code": exc.root_returncode,
                            "message": msg,
                        })
                    else:
                        msg = "Process watcher failed; inspect cleanup status"
                        record["errors"].append(msg)
                        seq = self._next_oracle_seq(record)
                        record.setdefault("error_events", []).append({
                            "seq": seq,
                            "source": "process",
                            "kind": "watcher_error",
                            "tool": None,
                            "command": None,
                            "exit_code": None,
                            "message": msg,
                        })
        finally:
            with self._lock:
                if exit_known:
                    close_process_job(process)
                    self._processes.pop(run_id, None)
                    if self._writers.get(project_key) == run_id:
                        self._writers.pop(project_key, None)
