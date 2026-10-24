"""Owned Antigravity CLI processes backed by the user's Google sign-in."""

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


class AntigravityRuntime:
    """Run the official ``agy`` headless protocol without API keys."""

    TERMINAL = {"completed", "failed", "cancelled"}
    SUCCESS = {"SUCCESS"}
    SUPPORTED_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
    DEFAULT_MODEL = "gemini-4-argon-medium"
    DEFAULT_EFFORT = "medium"
    PROBE_TTL = 120.0

    def __init__(self, executable=None):
        self.executable = self._find_executable(executable)
        self._lock = threading.RLock()
        self._runs = {}
        self._processes = {}
        self._writers = {}
        self._probe_cache: dict | None = None
        self._probe_cache_at: float = 0.0
        self._models_cache: dict | None = None
        self._models_cache_at: float = 0.0

    @staticmethod
    def _find_executable(explicit=None) -> str:
        local = Path(os.getenv("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
        candidates = [
            explicit, os.getenv("QUARTZ_ANTIGRAVITY_PATH"),
            shutil.which("agy.exe"), shutil.which("agy"), local,
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        raise FileNotFoundError("Antigravity CLI (agy) was not found")

    def list_models(self, force: bool = False) -> dict:
        """Discover supported models and efforts directly from `agy models`."""
        now = time.monotonic()
        with self._lock:
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
                if len(parts) < 2: continue  # CLI progress text is not a model
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
        return dict(result)

    def probe(self, force: bool = False) -> dict:
        now = time.monotonic()
        with self._lock:
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
        return dict(res)

    def start(self, prompt, project_path, *, write=False, full_access=False,
              squad_task_id=None, squad_agent_id=None, conversation_id=None,
              timeout="10m", model: str | None = None, effort: str | None = None,
              desktop_connection=None, tool_guard=False) -> dict:
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
        sandbox_label = "danger-full-access" if full_access else ("workspace-write" if effective_write else "sandbox")

        run_id = uuid.uuid4().hex
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
                "first_event_at": None, "first_text_at": None,
                "finished_at": None, "exit_code": None,
                "conversation_id": conversation_id,
                "model": clean_model, "effort": clean_effort,
                "result": "",
                "errors": [], "events": [], "progress_log": [], "usage": None,
                "denied_actions": [],
                "commands": [], "files_changed": [],
                "squad_task_id": squad_task_id,
                "squad_agent_id": squad_agent_id,
                "cancel_requested": False,
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
            args += ["--mode", "auto" if desktop_connection is not None or tool_guard else "plan", "--sandbox"]
        else:
            args += ["--mode", "accept-edits", "--dangerously-skip-permissions"]
            home_dir = str(Path.home())
            if os.path.isdir(home_dir):
                args += ["--add-dir", home_dir]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process_options = {}
        if desktop_connection is not None:
            from core.desktop_agents import connection_environment
            process_options["env"] = connection_environment(desktop_connection)
        try:
            process = subprocess.Popen(
                [self.executable, *args], cwd=str(project), stdin=subprocess.DEVNULL,
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

        with self._lock:
            record["pid"] = process.pid
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
            value = dict(record)
            value["errors"] = list(record["errors"][-20:])
            value["events"] = list(record["events"][-100:])
            value["progress_log"] = list(record.get("progress_log", [])[-50:])
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
                raise KeyError(f"Unknown Antigravity run: {run_id}")
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
            active = [key for key, proc in self._processes.items() if proc.poll() is None]
        for run_id in active:
            try:
                self.cancel(run_id)
            except Exception:
                pass

    def _probe(self, args, timeout=15) -> dict:
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
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"event": "raw", "text": line}
            with self._lock:
                record = self._runs[run_id]
                if record.get("first_event_at") is None:
                    record["first_event_at"] = time.time()
                record["events"].append(event)
                event_type = event.get("event")
                if event_type == "init":
                    record["conversation_id"] = event.get("conversation_id") or record["conversation_id"]
                elif event_type == "step_update":
                    step = event.get("step_update") or {}
                    delta = step.get("text_delta")
                    if delta:
                        if record.get("first_text_at") is None:
                            record["first_text_at"] = time.time()
                        record["result"] = (record["result"] or "") + delta
                    tool_name = step.get("tool_name")
                    if tool_name:
                        tool_state = step.get("state", "RUNNING")
                        record.setdefault("progress_log", []).append(f"Tool {tool_name}: {tool_state}")
                        tool_info = step.get("tool_info") or {}
                        params = tool_info.get("parameters") or {}
                        if tool_state in {"DONE", "ERROR"} and tool_name == "run_command":
                            record["commands"].append({
                                "command": str(params.get("CommandLine") or "")[:1000],
                                "exit_code": tool_info.get("exit_code"),
                                "output": str(tool_info.get("output") or tool_info.get("error") or "")[:4000],
                            })
                        if tool_state == "DONE" and tool_name in {
                            "create_file", "edit_file", "delete_file", "write_to_file",
                            "replace_file_content", "multi_replace_file_content", "notebook_edit",
                        }:
                            path = str(params.get("Path") or params.get("TargetFile") or
                                       params.get("file_path") or params.get("path") or "")
                            if path and path not in record["files_changed"]:
                                record["files_changed"].append(path)
                elif event_type == "result":
                    result = event.get("result") or {}
                    record["conversation_id"] = result.get("conversation_id") or record["conversation_id"]
                    final_resp = str(result.get("response") or "")
                    if final_resp:
                        if record.get("first_text_at") is None:
                            record["first_text_at"] = time.time()
                        record["result"] = final_resp
                    record["usage"] = result.get("usage")
                    record["remote_status"] = str(result.get("status") or "")
                    if result.get("error"):
                        record["errors"].append(str(result["error"]))
                    if result.get("denied_actions"):
                        record["denied_actions"] = list(result["denied_actions"])
                        denied = ", ".join(
                            str(item.get("action") or item.get("display_name") or "unknown")
                            for item in result["denied_actions"]
                        )
                        record["errors"].append(
                            f"Antigravity permission policy denied: {denied}"
                        )
                    if result.get("status") == "SUCCESS" and not record["result"]:
                        record["errors"].append("Antigravity returned SUCCESS without a response")

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
            elif (code == 0 and record.get("remote_status") in self.SUCCESS
                  and record["result"] and not record["denied_actions"]):
                record["status"] = "completed"
            else:
                record["status"] = "failed"
            self._processes.pop(run_id, None)
            if self._writers.get(project_key) == run_id:
                self._writers.pop(project_key, None)
