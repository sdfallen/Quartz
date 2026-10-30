"""Owned, non-blocking Codex CLI processes backed by ChatGPT login."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from core.process_tree import stop_process_tree


class CodexRuntime:
    TERMINAL = {"completed", "failed", "cancelled"}
    SUPPORTED_EFFORTS = ["low", "medium", "high", "xhigh", "max", "ultra"]
    PROBE_TTL = 300.0
    _SHARED_PROBE_CACHE: dict[str, tuple[float, dict]] = {}

    def __init__(self, executable=None):
        self.executable = None
        self._init_error = ""
        try:
            self.executable = self._find_executable(executable)
        except Exception as exc:
            self._init_error = str(exc)
        self._lock = threading.RLock()
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
            if not force and cached and cached.get("ready") and (now - cached_at < self.PROBE_TTL):
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
            if result.get("ready"):
                self._SHARED_PROBE_CACHE[cache_key] = (stamp, dict(result))
        return result

    def start(self, prompt, project_path, *, sandbox="read-only", approval="never",
              squad_task_id=None, squad_agent_id=None, resume_thread_id=None,
              model: str | None = None, effort: str | None = None,
              desktop_connection=None, tool_guard=False) -> dict:
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
        project = Path(project_path).resolve(strict=True)
        if not project.is_dir():
            raise NotADirectoryError(str(project))

        clean_model = str(model or "").strip() or None
        clean_effort = str(effort or "").strip().lower() or None
        if clean_effort and clean_effort not in self.SUPPORTED_EFFORTS:
            raise ValueError(f"Unsupported Codex reasoning effort: {clean_effort}")

        is_writer = sandbox in {"workspace-write", "danger-full-access"}
        run_id = uuid.uuid4().hex
        project_key = os.path.normcase(str(project))
        started_wall = time.time()
        with self._lock:
            if is_writer and project_key in self._writers:
                raise RuntimeError("This project already has an active write-capable agent")
            record = {
                "id": run_id, "status": "starting", "pid": None,
                "project": str(project), "sandbox": sandbox,
                "approval": approval, "started_at": started_wall,
                "first_event_at": None, "first_text_at": None,
                "finished_at": None, "exit_code": None, "thread_id": None,
                "model": clean_model, "effort": clean_effort,
                "result": "", "errors": [], "events": [], "usage": None,
                "commands": [], "files_changed": [],
                "squad_task_id": squad_task_id,
                "squad_agent_id": squad_agent_id,
                "cancel_requested": False,
            }
            self._runs[run_id] = record
            if is_writer:
                self._writers[project_key] = run_id

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
        if tool_guard:
            if desktop_connection is not None or sandbox != "read-only":
                raise ValueError("Log observer cannot receive desktop/write permissions")
        if tool_guard or desktop_connection is not None:
            # Per-run only: no user config changes. Disable inherited integrations
            # as well as shell/browser/desktop capabilities in the evidence reader.
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
                if not re.fullmatch(r"[A-Za-z0-9_-]+",name):
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
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            from core.cli_installer import cli_environment
            process_options = {"env": desktop_env if desktop_env is not None else cli_environment()}
            process = subprocess.Popen(
                command, cwd=str(project), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", creationflags=flags,
                **process_options,
            )
        except Exception:
            with self._lock:
                record["status"] = "failed"
                record["finished_at"] = time.time()
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
                self._writers.pop(project_key, None)
            raise

        with self._lock:
            record["pid"] = process.pid
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

    def resume(self, run_id, prompt, *, model: str | None = None, effort: str | None = None) -> dict:
        previous = self.get(run_id)
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
            value = dict(record)
            value["errors"] = list(record["errors"][-20:])
            value["events"] = list(record["events"][-100:])
            value["commands"] = list(record.get("commands", [])[-30:])
            value["files_changed"] = list(record.get("files_changed", []))
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
        if process is not None and process.poll() is None:
            stop_process_tree(process, timeout=max(1, timeout))
        return self.get(run_id)

    def shutdown(self):
        with self._lock:
            active = [run_id for run_id, proc in self._processes.items() if proc.poll() is None]
        for run_id in active:
            try:
                self.cancel(run_id)
            except Exception:
                pass

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
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"type": "raw", "text": line}
            with self._lock:
                record = self._runs[run_id]
                if record.get("first_event_at") is None:
                    record["first_event_at"] = time.time()
                record["events"].append(event)
                event_type = event.get("type")
                if event_type == "thread.started":
                    record["thread_id"] = event.get("thread_id")
                elif event_type == "item.completed":
                    item = event.get("item") or {}
                    if item.get("type") == "agent_message":
                        text_val = str(item.get("text") or "")
                        if text_val and record.get("first_text_at") is None:
                            record["first_text_at"] = time.time()
                        record["result"] = text_val
                    elif item.get("type") == "error":
                        record["errors"].append(str(item.get("message") or "Codex error"))
                    elif item.get("type") == "command_execution":
                        record["commands"].append({
                            "command": str(item.get("command") or "")[:1000],
                            "exit_code": item.get("exit_code"),
                            "output": str(item.get("aggregated_output") or "")[:4000],
                        })
                    elif item.get("type") == "file_change":
                        for change in item.get("changes") or []:
                            path = str(change.get("path") or "")
                            if path and path not in record["files_changed"]:
                                record["files_changed"].append(path)
                elif event_type == "turn.failed":
                    error_msg = event.get("error") or event.get("message") or "Codex turn failed"
                    record["errors"].append(str(error_msg))
                elif event_type == "error":
                    record["errors"].append(str(event.get("message") or "Codex error"))
                elif event_type == "turn.completed":
                    record["usage"] = event.get("usage")

    def _read_stderr(self, run_id, process):
        if process.stderr is None:
            return
        for raw in process.stderr:
            line = raw.strip()
            if line:
                with self._lock:
                    self._runs[run_id]["errors"].append(line)

    def _wait(self, run_id, process, project_key, stdout_thread, stderr_thread):
        code = process.wait()
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        with self._lock:
            record = self._runs[run_id]
            record["exit_code"] = code
            record["finished_at"] = time.time()
            if record["cancel_requested"]:
                record["status"] = "cancelled"
            elif code == 0 and record["result"]:
                record["status"] = "completed"
            else:
                record["status"] = "failed"
            self._processes.pop(run_id, None)
            if self._writers.get(project_key) == run_id:
                self._writers.pop(project_key, None)
