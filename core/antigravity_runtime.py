"""Owned Antigravity CLI processes backed by the user's Google sign-in."""

from __future__ import annotations

import json
import os
import re
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


class AntigravityRuntime:
    """Run the official ``agy`` headless protocol without API keys."""

    TERMINAL = {"completed", "failed", "cancelled"}
    SUCCESS = {"SUCCESS"}
    SUPPORTED_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
    DEFAULT_MODEL = "gemini-4-argon-medium"
    DEFAULT_EFFORT = "medium"
    PROBE_TTL = 300.0
    _SHARED_PROBE_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
    _SHARED_MODELS_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
    _EXIT_CODE_RE = re.compile(r"Command exited with code (-?\d+)")
    _FILE_CHANGE_TOOLS = {
        "create_file": "add",
        "write_to_file": "write",
        "write_file": "write",
        "edit_file": "update",
        "replace": "update",
        "replace_file_content": "update",
        "multi_replace_file_content": "update",
        "notebook_edit": "update",
        "delete_file": "delete",
    }
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
        self._lock = threading.RLock()
        self._runs = {}
        self._processes = {}
        self._writers = {}
        cache_key = self._cache_key()
        now = time.monotonic()
        shared_probe = self._SHARED_PROBE_CACHE.get(cache_key)
        if shared_probe and (now - shared_probe[0]) < self.PROBE_TTL:
            self._probe_cache: dict | None = dict(shared_probe[1])
            self._probe_cache_at: float = shared_probe[0]
        else:
            self._probe_cache = None
            self._probe_cache_at = 0.0
        shared_models = self._SHARED_MODELS_CACHE.get(cache_key)
        if shared_models and (now - shared_models[0]) < self.PROBE_TTL:
            self._models_cache: dict | None = dict(shared_models[1])
            self._models_cache_at: float = shared_models[0]
        else:
            self._models_cache = None
            self._models_cache_at = 0.0

    def _cache_key(self) -> tuple[str, str]:
        return (str(getattr(self, "backend", "agy")), str(self.executable or ""))

    @staticmethod
    def _find_executable(explicit=None) -> str:
        from core.cli_installer import resolve_cli
        return resolve_cli("agy", explicit)

    @staticmethod
    def _next_oracle_seq(record: dict) -> int:
        seq = int(record.get("_oracle_seq", 0)) + 1
        record["_oracle_seq"] = seq
        return seq

    @classmethod
    def _extract_command_exit_code(cls, tool_info: dict, tool_state: str, output_text: str) -> int | None:
        for key in ("exit_code", "returncode", "return_code"):
            raw = tool_info.get(key)
            if isinstance(raw, int) and not isinstance(raw, bool):
                return int(raw)
        match = cls._EXIT_CODE_RE.search(output_text or "")
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _read_guard_matches(workspace: Path, roots) -> bool:
        """Fail closed unless the workspace carries exactly Quartz's read guard for these roots."""
        agents = workspace / ".agents"
        try:
            hooks = json.loads((agents / "hooks.json").read_text(encoding="utf-8"))
            expected = {"quartz-project-read": {"PreToolUse": [{"matcher": "*", "hooks": [
                {"type": "command", "command": r".\read-guard.exe --project-read", "timeout": 5}]}]}}
            listed = json.loads((agents / "read-roots.json").read_text(encoding="utf-8")).get("roots")
            return (hooks == expected and (agents / "read-guard.exe").is_file()
                    and isinstance(listed, list)
                    and sorted(os.path.normcase(str(Path(r).resolve())) for r in listed)
                    == sorted(os.path.normcase(str(r)) for r in roots))
        except (OSError, ValueError, AttributeError, TypeError):
            return False

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

    def list_models(self, force: bool = False) -> dict:
        """Discover supported models and efforts directly from `agy models`."""
        if not self.executable:
            return {
                "provider": "antigravity",
                "default_model": self.DEFAULT_MODEL,
                "default_effort": self.DEFAULT_EFFORT,
                "efforts": list(self.SUPPORTED_EFFORTS),
                "models": [],
                "source": "cli_unavailable",
                "error": self._init_error or "Antigravity CLI was not found",
            }
        now = time.monotonic()
        cache_key = self._cache_key()
        with self._lock:
            if self._models_cache is None and self._models_cache_at == 0.0:
                shared = self._SHARED_MODELS_CACHE.get(cache_key)
                if shared and (now - shared[0]) < self.PROBE_TTL:
                    self._models_cache_at, self._models_cache = shared[0], dict(shared[1])
            if not force and self._models_cache is not None and (now - self._models_cache_at) < self.PROBE_TTL:
                return dict(self._models_cache)

        raw = self._probe(["models"], timeout=20)
        models: list[dict] = []
        if raw["returncode"] == 0 and raw["stdout"].strip():
            for line in raw["stdout"].splitlines():
                clean = line.strip()
                if not clean:
                    continue
                parts = [p.strip() for p in clean.split("\t") if p.strip()]
                if len(parts) < 2:
                    continue  # CLI progress text is not a model
                model_id = parts[0] if parts else clean
                label = parts[1] if len(parts) > 1 else model_id
                inferred_effort = self.DEFAULT_EFFORT
                for eff in ("low", "medium", "high", "xhigh", "max"):
                    if model_id.endswith(f"-{eff}"):
                        inferred_effort = eff
                        break
                models.append({
                    "id": model_id,
                    "label": label,
                    "description": label,
                    "default_effort": inferred_effort,
                    "efforts": [inferred_effort] if model_id.endswith("-"+inferred_effort) else list(self.SUPPORTED_EFFORTS),
                })

        default_model = self.DEFAULT_MODEL
        if models and not any(m["id"] == default_model for m in models):
            default_model = models[0]["id"]

        result = {
            "provider": "antigravity",
            "default_model": default_model,
            "default_effort": self.DEFAULT_EFFORT,
            "efforts": list(self.SUPPORTED_EFFORTS),
            "models": models,
            "source": "agy_cli_models" if models else "cli_unavailable",
            "error": "" if models else (raw["stderr"] or raw["stdout"] or "agy models returned no models").strip(),
        }
        with self._lock:
            self._models_cache = result
            self._models_cache_at = time.monotonic()
            self._SHARED_MODELS_CACHE[cache_key] = (self._models_cache_at, dict(result))
        return dict(result)

    def probe(self, force: bool = False) -> dict:
        if not self.executable:
            res = {
                "installed": False, "version": "", "executable": None,
                "authenticated": False, "authentication": "required", "ready": False,
                "error": self._init_error or "Antigravity CLI was not found",
            }
            with self._lock:
                self._probe_cache = res
                self._probe_cache_at = time.monotonic()
            return dict(res)
        now = time.monotonic()
        cache_key = self._cache_key()
        with self._lock:
            if self._probe_cache is None and self._probe_cache_at == 0.0:
                shared = self._SHARED_PROBE_CACHE.get(cache_key)
                if shared and (now - shared[0]) < self.PROBE_TTL:
                    self._probe_cache_at, self._probe_cache = shared[0], dict(shared[1])
            if not force and self._probe_cache is not None and (now - self._probe_cache_at) < self.PROBE_TTL:
                return dict(self._probe_cache)

        version = self._probe(["--version"])
        if version["returncode"] != 0:
            res = {
                "installed": False, "version": "", "executable": self.executable,
                "authenticated": False, "authentication": "required", "ready": False,
                "error": version["stderr"] or "Antigravity CLI could not start",
            }
            with self._lock:
                self._probe_cache = res
                self._probe_cache_at = time.monotonic()
                self._SHARED_PROBE_CACHE[cache_key] = (self._probe_cache_at, dict(res))
            return dict(res)
        # /model is handled locally by the CLI. In headless mode missing cached
        # credentials fail instead of opening an OAuth browser or hanging.
        auth = self._probe(["-p", "/model"], timeout=30)
        auth_text = (auth["stdout"] + "\n" + auth["stderr"]).strip()
        authenticated = auth["returncode"] == 0 and "authentication required" not in auth_text.lower()
        res = {
            "installed": True, "version": version["stdout"].strip(),
            "executable": self.executable, "authenticated": authenticated,
            "authentication": "google-account" if authenticated else "required",
            "ready": authenticated,
            "error": "" if authenticated else (auth_text or "Google account sign-in required"),
        }
        with self._lock:
            self._probe_cache = res
            self._probe_cache_at = time.monotonic()
            self._SHARED_PROBE_CACHE[cache_key] = (self._probe_cache_at, dict(res))
        return dict(res)

    def start(self, prompt, project_path, *, write=False, full_access=False,
              squad_task_id=None, squad_agent_id=None, conversation_id=None,
              timeout="10m", model: str | None = None, effort: str | None = None,
              desktop_connection=None, tool_guard=False, read_dirs=()) -> dict:
        if not self.executable:
            raise RuntimeError(self._init_error or "Antigravity CLI was not found")
        text = str(prompt or "").strip()
        if not text:
            raise ValueError("Antigravity prompt cannot be empty")
        if len(text) > 100_000:
            raise ValueError("Antigravity prompt is too long")
        project = Path(project_path).resolve(strict=True)
        if not project.is_dir():
            raise NotADirectoryError(str(project))

        clean_model = str(model or "").strip() or None
        clean_effort = str(effort or "").strip().lower() or None
        if clean_effort and clean_effort not in self.SUPPORTED_EFFORTS:
            raise ValueError(f"Unsupported Antigravity reasoning effort: {clean_effort}")
        encoded_effort = next((e for e in self.SUPPORTED_EFFORTS if clean_model and clean_model.endswith("-"+e)), None)
        if encoded_effort and clean_effort and encoded_effort != clean_effort:
            raise ValueError("Selected model already fixes its effort; select the matching model variant")

        effective_write = bool(write or full_access)
        if effective_write and not full_access:
            raise PermissionError("Antigravity cannot enforce project-only writes on Windows; explicit full access is required.")
        # Extra read roots are only for a read-only run whose workspace carries
        # Quartz's read-only PreToolUse hook (see chat_coordination); the CLI
        # sandbox alone is not trusted to stop built-in file writes on Windows.
        extra_dirs = [Path(d).resolve(strict=True) for d in (read_dirs or ())]
        if any(not d.is_dir() for d in extra_dirs):
            raise NotADirectoryError("Antigravity read directory is not a folder")
        # Only the agy CLI honours the workspace PreToolUse guard; the Gemini CLI
        # subclass rewrites --mode auto to yolo and drops --add-dir (Gemini review).
        if extra_dirs and (getattr(self, "backend", "agy") != "agy"
                           or effective_write or desktop_connection is not None or tool_guard
                           or not self._read_guard_matches(project, extra_dirs)):
            raise PermissionError("Read directories need a read-only, hook-guarded Antigravity run")
        sandbox_label = "danger-full-access" if full_access else ("workspace-write" if effective_write else "sandbox")

        run_id = uuid.uuid4().hex
        timeout_seconds = self._parse_timeout_seconds(timeout)
        project_key = os.path.normcase(str(project))
        with self._lock:
            if effective_write and project_key in self._writers:
                raise RuntimeError("This project already has an active Antigravity writer")
            record = {
                "id": run_id, "provider": "antigravity", "status": "starting",
                "pid": None, "project": str(project),
                "sandbox": sandbox_label,
                "approval": "always-proceed" if effective_write else "configured-policy",
                "started_at": time.time(),
                "timeout_seconds": timeout_seconds,
                "first_event_at": None, "first_text_at": None,
                "finished_at": None, "exit_code": None,
                "conversation_id": conversation_id,
                "model": clean_model, "effort": clean_effort,
                "result": "",
                "errors": [], "events": [], "progress_log": [], "usage": None,
                "denied_actions": [],
                "commands": [], "command_results": [], "command_exit_codes": [],
                "files_changed": [], "scratch_files_changed": [], "file_changes": [],
                "unauthorized_write_detected": False, "unauthorized_files_changed": [],
                "error_events": [],
                "job_bound": False, "job_assignment_error": "",
                "squad_task_id": squad_task_id,
                "squad_agent_id": squad_agent_id,
                "cancel_requested": False,
                "_oracle_seq": 0,
                "_pending_tool_params": {},
                "_tool_guard": bool(tool_guard),
            }
            self._runs[run_id] = record
            if effective_write:
                self._writers[project_key] = run_id

        args = ["-p", text, "--output-format", "stream-json", "--print-timeout", timeout]
        if clean_model:
            args += ["--model", clean_model]
        if clean_effort and not encoded_effort:
            args += ["--effort", clean_effort]
        if conversation_id:
            args += ["--conversation", str(conversation_id)]
        if not effective_write:
            # A separately confirmed desktop capability needs execution, not
            # planning-only. Keep terminal sandbox; never silently add full access.
            args += ["--mode", "auto" if desktop_connection is not None or tool_guard or extra_dirs else "plan", "--sandbox"]
            for directory in extra_dirs:
                args += ["--add-dir", str(directory)]
        else:
            args += ["--mode", "accept-edits", "--dangerously-skip-permissions"]
            home_dir = str(Path.home())
            if os.path.isdir(home_dir):
                args += ["--add-dir", home_dir]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | CREATE_SUSPENDED
        process_options = {}
        if desktop_connection is not None:
            from core.desktop_agents import connection_environment
            process_options["env"] = connection_environment(desktop_connection)
        process_options = self._process_options(process_options, project, desktop_connection, tool_guard)
        job_errors: list[str] = []
        try:
            process = subprocess.Popen(
                self._command(args), cwd=str(project), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", creationflags=flags,
                **process_options,
            )
            job_bound = bind_kill_on_close_job(process, resume=True, error_sink=job_errors.append)
        except Exception:
            with self._lock:
                record["status"] = "failed"
                record["finished_at"] = time.time()
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
            name=f"agy-out-{run_id[:8]}", daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stderr, args=(run_id, process),
            name=f"agy-err-{run_id[:8]}", daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        threading.Thread(
            target=self._wait,
            args=(run_id, process, project_key, stdout_thread, stderr_thread),
            name=f"agy-wait-{run_id[:8]}", daemon=True,
        ).start()
        return self.get(run_id)

    def resume(self, run_id, prompt, *, model: str | None = None, effort: str | None = None) -> dict:
        previous = self.get(run_id)
        conversation_id = previous.get("conversation_id")
        if not conversation_id:
            raise RuntimeError("The Antigravity conversation id is not available")
        if previous["status"] not in self.TERMINAL:
            raise RuntimeError("Cannot resume a running Antigravity task")
        return self.start(
            prompt, previous["project"],
            write=previous["sandbox"] in {"workspace-write", "danger-full-access"},
            full_access=previous["sandbox"] == "danger-full-access",
            squad_task_id=previous.get("squad_task_id"),
            squad_agent_id=previous.get("squad_agent_id"),
            conversation_id=conversation_id,
            model=model or previous.get("model"),
            effort=effort or previous.get("effort"),
        )

    def get(self, run_id) -> dict:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(f"Unknown Antigravity run: {run_id}")
            record = self._runs[run_id]
            value = {k: v for k, v in record.items() if not str(k).startswith("_")}
            value["errors"] = list(record["errors"][-20:])
            value["events"] = list(record["events"][-100:])
            value["progress_log"] = list(record.get("progress_log", [])[-50:])
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
                raise KeyError(f"Unknown Antigravity run: {run_id}")
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
        return [self.executable, *args]

    def _process_options(self, options, project, desktop_connection, tool_guard):
        return options

    def _normalize_event(self, event):
        return event

    def _probe(self, args, timeout=15) -> dict:
        if not self.executable:
            return {"returncode": -1, "stdout": "", "stderr": self._init_error or "Antigravity CLI was not found"}
        try:
            completed = subprocess.run(
                [self.executable, *args], stdin=subprocess.DEVNULL,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            return {"returncode": completed.returncode, "stdout": completed.stdout,
                    "stderr": completed.stderr}
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
                    event = {"event": "raw", "text": line}
                event = self._normalize_event(event)
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
                    event_type = event.get("event")
                    if event_type == "init":
                        record["conversation_id"] = event.get("conversation_id") or record["conversation_id"]
                    elif event_type == "step_update":
                        step = event.get("step_update") or {}
                        delta = step.get("text_delta")
                        if delta and not is_terminal:
                            if record.get("first_text_at") is None:
                                record["first_text_at"] = time.time()
                            record["result"] = (record["result"] or "") + delta
                        tool_name = step.get("tool_name")
                        if tool_name:
                            tool_state = str(step.get("state") or "RUNNING").upper()
                            record.setdefault("progress_log", []).append(f"Tool {tool_name}: {tool_state}")
                            tool_info = step.get("tool_info") or {}
                            raw_params = tool_info.get("parameters") or {}
                            pending_map = record.setdefault("_pending_tool_params", {})
                            step_key = str(step.get("id") or step.get("step_id") or tool_name)
                            if tool_state == "RUNNING":
                                if raw_params:
                                    pending_map[step_key] = dict(raw_params)
                                    pending_map[tool_name] = dict(raw_params)
                            params = dict(pending_map.get(step_key) or pending_map.get(tool_name) or {})
                            params.update(raw_params)
                            if tool_state in {"DONE", "ERROR"}:
                                pending_map.pop(step_key, None)
                                pending_map.pop(tool_name, None)

                            if tool_state in {"DONE", "ERROR"} and tool_name in {"run_command", "run_shell_command"}:
                                cmd_str = str(params.get("CommandLine") or params.get("command") or "")[:1000]
                                out_str = str(tool_info.get("output") or tool_info.get("error") or "")[:4000]
                                err_str = str(tool_info.get("error") or "")[:2000]
                                exit_code = self._extract_command_exit_code(tool_info, tool_state, out_str)
                                seq = self._next_oracle_seq(record)
                                record["commands"].append({
                                    "command": cmd_str,
                                    "exit_code": exit_code,
                                    "output": out_str,
                                })
                                record.setdefault("command_exit_codes", []).append(exit_code)
                                ok = tool_state == "DONE" and exit_code in (0, None)
                                if exit_code not in (None, 0):
                                    ok = False
                                record.setdefault("command_results", []).append({
                                    "seq": seq,
                                    "tool": tool_name,
                                    "command": cmd_str,
                                    "exit_code": exit_code,
                                    "ok": ok,
                                    "state": tool_state,
                                    "output": out_str,
                                    "error": err_str if not ok else "",
                                })
                                if not ok:
                                    record.setdefault("error_events", []).append({
                                        "seq": seq,
                                        "source": "command",
                                        "kind": "nonzero_exit" if exit_code not in (None, 0) else "command_error",
                                        "tool": tool_name,
                                        "command": cmd_str,
                                        "exit_code": exit_code,
                                        "message": err_str or out_str[:1000] or f"Tool {tool_name} failed",
                                    })
                            elif tool_state in {"DONE", "ERROR"} and tool_name in self._FILE_CHANGE_TOOLS:
                                path = str(params.get("Path") or params.get("TargetFile") or
                                           params.get("file_path") or params.get("path") or "")
                                change_kind = self._FILE_CHANGE_TOOLS[tool_name]
                                seq = self._next_oracle_seq(record)
                                is_scratch = self._is_scratch_workspace_path(
                                    record.get("project", ""),
                                    path,
                                    tool_guard=bool(record.get("_tool_guard")),
                                )
                                if path:
                                    record.setdefault("file_changes", []).append({
                                        "seq": seq,
                                        "path": path,
                                        "kind": change_kind,
                                        "tool": tool_name,
                                        "state": tool_state,
                                    })
                                if tool_state == "DONE":
                                    if is_scratch:
                                        if path:
                                            scratch_list = record.setdefault("scratch_files_changed", [])
                                            if path not in scratch_list:
                                                scratch_list.append(path)
                                    else:
                                        if path and path not in record["files_changed"]:
                                            record["files_changed"].append(path)
                                        if record.get("sandbox") == "sandbox":
                                            record["unauthorized_write_detected"] = True
                                            unauth_list = record.setdefault("unauthorized_files_changed", [])
                                            if path and path not in unauth_list:
                                                unauth_list.append(path)
                                            violation_msg = f"Read-only Antigravity run modified file without write permission: {path or tool_name}"
                                            record["errors"].append(violation_msg)
                                            record.setdefault("denied_actions", []).append({
                                                "action": "write",
                                                "display_name": tool_name,
                                                "path": path,
                                                "reason": "read_only_violation",
                                            })
                                            record.setdefault("error_events", []).append({
                                                "seq": seq,
                                                "source": "sandbox_guard",
                                                "kind": "unauthorized_readonly_write",
                                                "tool": tool_name,
                                                "command": None,
                                                "exit_code": None,
                                                "message": violation_msg,
                                            })
                                elif tool_state == "ERROR":
                                    err_msg = str(tool_info.get("error") or tool_info.get("output") or f"Tool {tool_name} failed")
                                    record.setdefault("error_events", []).append({
                                        "seq": seq,
                                        "source": "tool",
                                        "kind": "file_change_error",
                                        "tool": tool_name,
                                        "command": None,
                                        "exit_code": None,
                                        "message": err_msg[:1000],
                                    })
                            elif tool_state == "ERROR":
                                seq = self._next_oracle_seq(record)
                                err_msg = str(tool_info.get("error") or tool_info.get("output") or f"Tool {tool_name} failed")
                                record.setdefault("error_events", []).append({
                                    "seq": seq,
                                    "source": "tool",
                                    "kind": "tool_error",
                                    "tool": tool_name,
                                    "command": None,
                                    "exit_code": None,
                                    "message": err_msg[:1000],
                                })
                    elif event_type == "result":
                        result = event.get("result") or {}
                        record["conversation_id"] = result.get("conversation_id") or record["conversation_id"]
                        final_resp = str(result.get("response") or "")
                        if final_resp and not is_terminal:
                            if record.get("first_text_at") is None:
                                record["first_text_at"] = time.time()
                            record["result"] = final_resp
                        record["usage"] = result.get("usage")
                        record["remote_status"] = str(result.get("status") or "")
                        if result.get("error"):
                            err_msg = str(result["error"])
                            record["errors"].append(err_msg)
                            seq = self._next_oracle_seq(record)
                            record.setdefault("error_events", []).append({
                                "seq": seq,
                                "source": "result",
                                "kind": "result_error",
                                "tool": None,
                                "command": None,
                                "exit_code": None,
                                "message": err_msg,
                            })
                        if result.get("denied_actions"):
                            record["denied_actions"] = list(result["denied_actions"])
                            denied = ", ".join(
                                str(item.get("action") or item.get("display_name") or "unknown")
                                for item in result["denied_actions"]
                            )
                            deny_msg = f"Antigravity permission policy denied: {denied}"
                            record["errors"].append(deny_msg)
                            seq = self._next_oracle_seq(record)
                            record.setdefault("error_events", []).append({
                                "seq": seq,
                                "source": "permission",
                                "kind": "permission_denied",
                                "tool": None,
                                "command": None,
                                "exit_code": None,
                                "message": deny_msg,
                            })
                        if result.get("status") == "SUCCESS" and not record["result"]:
                            empty_msg = "Antigravity returned SUCCESS without a response"
                            record["errors"].append(empty_msg)
                            seq = self._next_oracle_seq(record)
                            record.setdefault("error_events", []).append({
                                "seq": seq,
                                "source": "result",
                                "kind": "empty_output",
                                "tool": None,
                                "command": None,
                                "exit_code": None,
                                "message": empty_msg,
                            })
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

    @staticmethod
    def _parse_timeout_seconds(timeout) -> float:
        if isinstance(timeout, (int, float)):
            return max(1.0, float(timeout))
        raw = str(timeout or "10m").strip().lower()
        try:
            if raw.endswith("ms"):
                return max(1.0, float(raw[:-2]) / 1000.0)
            if raw.endswith("s"):
                return max(1.0, float(raw[:-1]))
            if raw.endswith("m"):
                return max(1.0, float(raw[:-1]) * 60.0)
            if raw.endswith("h"):
                return max(1.0, float(raw[:-1]) * 3600.0)
            return max(1.0, float(raw))
        except ValueError:
            return 600.0

    def _wait(self, run_id, process, project_key, stdout_thread, stderr_thread):
        with self._lock:
            timeout_sec = self._runs.get(run_id, {}).get("timeout_seconds") or 600.0
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
                    elif (not timed_out and code == 0 and record.get("remote_status") in self.SUCCESS
                          and record["result"] and not record["denied_actions"]
                          and not record.get("unauthorized_write_detected")):
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
