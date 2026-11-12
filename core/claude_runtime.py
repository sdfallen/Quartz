"""Owned, non-blocking Claude Code CLI processes (user's own Claude login).

Same record contract as :class:`core.codex_runtime.CodexRuntime` so chat,
writer evidence, Stop and shutdown treat both agents alike. Every run is
locked down on the command line and then PROVEN from the CLI's own ``init``
event: the tool list and MCP server list must equal what Quartz asked for,
otherwise the process tree is stopped before the model can act.

Lock-down (verified on Claude Code 2.1.318):
- ``--tools`` / ``--allowedTools``: exact built-in tool set per sandbox mode;
  the default set (30 tools, incl. SendMessage, scheduling, web, artifacts) is
  never used.
- ``--strict-mcp-config --mcp-config``: only Quartz's MCP servers (none yet).
- ``--setting-sources ""``: user/project/local settings and their hooks are
  not loaded. ``--bare`` is NOT used: it disables OAuth (subscription) login.
- ``--permission-mode dontAsk``: anything not pre-approved is refused.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from core.codex_runtime import CodexRuntime
from core.process_tree import (CREATE_SUSPENDED, bind_kill_on_close_job,
                               stop_process_tree)

READ_TOOLS = ("Read", "Grep", "Glob")
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
TOOLS_BY_SANDBOX = {
    # Plain conversation: no tools at all (the init event must report []).
    "none": (),
    "read-only": READ_TOOLS,
    # No OS sandbox for Claude Code shells on Windows: file edits only.
    "workspace-write": READ_TOOLS + EDIT_TOOLS,
    # The user's explicit "Tam yetki" choice: shells too.
    "danger-full-access": READ_TOOLS + EDIT_TOOLS + SHELL_TOOLS,
}
# Pre-approved permission rules under --permission-mode dontAsk. Claude Code
# lets the file tools read inside the working directory without a rule and
# asks (= refuses, in dontAsk) for anything outside it; Edit(./**) approves
# writes inside the project only (it also covers Write/NotebookEdit). Live
# 13 Nov: an unscoped "Read" rule let a read-only run read another project.
ALLOWED_BY_SANDBOX = {
    "none": (),
    "read-only": (),
    "workspace-write": ("Edit(./**)",),
    # Shells can reach any path anyway; the user's "Tam yetki" choice.
    "danger-full-access": READ_TOOLS + EDIT_TOOLS + SHELL_TOOLS,
}
FILE_TOOLS = {"Edit": "update", "Write": "add", "NotebookEdit": "update"}
# Variables that would make the child think it runs inside another Claude
# session (desktop app, IDE, nested CLI) or reach that session's channels.
_INHERITED_SESSION_VARS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT",
                           "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_AGENT_SDK_VERSION")
MODELS = (
    ("opus", "Claude Opus (en güçlü)"),
    ("sonnet", "Claude Sonnet (hızlı ve güçlü)"),
    ("haiku", "Claude Haiku (en hızlı)"),
)


class ClaudeRuntime(CodexRuntime):
    SUPPORTED_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
    _SHARED_PROBE_CACHE: dict[str, tuple[float, dict]] = {}

    @staticmethod
    def _find_executable(explicit=None) -> str:
        candidates = [explicit, os.getenv("QUARTZ_CLAUDE_PATH")]
        home_bin = Path.home() / ".local" / "bin"
        candidates += [home_bin / "claude.exe", shutil.which("claude.exe"), shutil.which("claude")]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        raise FileNotFoundError("Claude CLI was not found")

    # -- discovery ---------------------------------------------------------
    def list_models(self, force: bool = False) -> dict:
        return {
            "default_model": "sonnet",
            "models": [{"id": mid, "label": label, "efforts": list(self.SUPPORTED_EFFORTS),
                        "default_effort": "medium"} for mid, label in MODELS],
            "efforts": list(self.SUPPORTED_EFFORTS),
            "default_effort": "medium",
            "source": "builtin",
        }

    def probe(self, force: bool = False) -> dict:
        if not self.executable:
            return {"installed": False, "version": "", "executable": None, "authenticated": False,
                    "authentication": "required", "ready": False,
                    "error": self._init_error or "Claude CLI was not found"}
        now = time.monotonic()
        with self._lock:
            cached_at, cached = self._probe_cache
            if not force and cached and (now - cached_at < self.PROBE_TTL):
                return dict(cached)
        version = self._probe(["--version"])
        status = self._probe(["auth", "status"])
        try:
            info = json.loads(status["stdout"] or "{}")
        except json.JSONDecodeError:
            info = {}
        authenticated = status["returncode"] == 0 and info.get("loggedIn") is True
        result = {
            "installed": version["returncode"] == 0,
            "version": version["stdout"].strip(),
            "executable": self.executable,
            "authenticated": authenticated,
            "authentication": str(info.get("authMethod") or "unknown") if authenticated else "required",
            "ready": version["returncode"] == 0 and authenticated,
            "error": "" if authenticated else
                "Claude girişi yok veya süresi dolmuş: bir terminalde `claude` açıp /login yapın.",
        }
        with self._lock:
            stamp = time.monotonic()
            self._probe_cache = (stamp, dict(result))
            self._SHARED_PROBE_CACHE[str(self.executable)] = (stamp, dict(result))
        return result

    # -- runs --------------------------------------------------------------
    @staticmethod
    def tools_for(sandbox: str) -> tuple[str, ...]:
        try:
            return TOOLS_BY_SANDBOX[sandbox]
        except KeyError:
            raise ValueError("Unsupported Claude sandbox") from None

    def build_args(self, sandbox, *, model=None, effort=None, session_id=None, resume_id=None):
        tools = ",".join(self.tools_for(sandbox))
        args = ["-p", "--output-format", "stream-json", "--verbose",
                "--strict-mcp-config", "--mcp-config", json.dumps({"mcpServers": {}}),
                "--setting-sources", "", "--permission-mode", "dontAsk", "--tools", tools]
        allowed = ",".join(ALLOWED_BY_SANDBOX[sandbox])
        if allowed:
            args += ["--allowedTools", allowed]
        if model:
            args += ["--model", model]
        if effort:
            args += ["--effort", effort]
        if resume_id:
            args += ["--resume", resume_id]
        elif session_id:
            args += ["--session-id", session_id]
        return args

    @staticmethod
    def child_environment():
        from core.cli_installer import cli_environment
        env = cli_environment()
        for name in _INHERITED_SESSION_VARS:
            env.pop(name, None)
        return env

    def start(self, prompt, project_path, *, sandbox="read-only", approval="never",
              squad_task_id=None, squad_agent_id=None, resume_thread_id=None,
              timeout=None, model: str | None = None, effort: str | None = None,
              desktop_connection=None, tool_guard=False, project_read=False, should_abort=None) -> dict:
        if not self.executable:
            raise RuntimeError(self._init_error or "Claude CLI was not found")
        text = str(prompt or "").strip()
        if not text:
            raise ValueError("Claude prompt cannot be empty")
        if len(text) > 100_000:
            raise ValueError("Claude prompt is too long")
        expected_tools = self.tools_for(sandbox)
        if desktop_connection is not None or tool_guard or project_read:
            # Desktop/observer/project-read profiles need Quartz's MCP servers
            # and guards; until they are wired for Claude they are refused.
            raise PermissionError("Claude does not run desktop, observer or project-read profiles yet")
        project = Path(project_path).resolve(strict=True)
        if not project.is_dir():
            raise NotADirectoryError(str(project))
        clean_model = str(model or "").strip() or None
        clean_effort = str(effort or "").strip().lower() or None
        if clean_effort and clean_effort not in self.SUPPORTED_EFFORTS:
            raise ValueError(f"Unsupported Claude effort: {clean_effort}")

        is_writer = sandbox in {"workspace-write", "danger-full-access"}
        run_id = uuid.uuid4().hex
        session_id = None if resume_thread_id else str(uuid.uuid4())
        project_key = os.path.normcase(str(project))
        with self._lock:
            if is_writer and project_key in self._writers:
                raise RuntimeError("This project already has an active write-capable agent")
            record = {
                "id": run_id, "status": "starting", "pid": None, "agent": "claude",
                "project": str(project), "sandbox": sandbox, "approval": approval,
                "started_at": time.time(), "timeout_seconds": self._parse_timeout_seconds(timeout),
                "first_event_at": None, "first_text_at": None, "finished_at": None,
                "exit_code": None, "thread_id": resume_thread_id or session_id,
                "model": clean_model, "effort": clean_effort,
                "result": "", "errors": [], "events": [], "usage": None, "cost_usd": None,
                "commands": [], "command_results": [], "command_exit_codes": [],
                "files_changed": [], "scratch_files_changed": [], "file_changes": [],
                "unauthorized_write_detected": False, "unauthorized_files_changed": [],
                "error_events": [], "job_bound": False, "job_assignment_error": "",
                "squad_task_id": squad_task_id, "squad_agent_id": squad_agent_id,
                "cancel_requested": False, "tools_verified": False,
                "_oracle_seq": 0, "_tool_guard": False, "_project_read": None,
                "_expected_tools": sorted(expected_tools), "_pending_tools": {},
            }
            self._runs[run_id] = record
            if is_writer:
                self._writers[project_key] = run_id

        def release(status):
            with self._lock:
                record["status"] = status
                record["finished_at"] = time.time()
                record.update(cleanup_pending=False, process_exit_confirmed=True)
                if self._writers.get(project_key) == run_id:
                    self._writers.pop(project_key, None)

        if should_abort and should_abort():
            release("cancelled")
            raise RuntimeError("Claude run cancelled before start")
        command = self._command(self.build_args(sandbox, model=clean_model, effort=clean_effort,
                                                session_id=session_id, resume_id=resume_thread_id))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | CREATE_SUSPENDED
        job_errors: list[str] = []
        try:
            process = subprocess.Popen(
                command, cwd=str(project), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", creationflags=flags,
                env=self.child_environment(),
            )
            job_bound = bind_kill_on_close_job(process, resume=True, error_sink=job_errors.append)
        except Exception:
            release("failed")
            raise
        try:
            process.stdin.write(text)
            process.stdin.close()
        except Exception:
            process.terminate()
            release("failed")
            raise
        with self._lock:
            record["pid"] = process.pid
            record["job_bound"] = bool(job_bound)
            if job_errors:
                record["job_assignment_error"] = job_errors[-1]
            record["status"] = "running"
            self._processes[run_id] = process
        stdout_thread = threading.Thread(target=self._read_stdout, args=(run_id, process),
                                         name=f"claude-out-{run_id[:8]}", daemon=True)
        stderr_thread = threading.Thread(target=self._read_stderr, args=(run_id, process),
                                         name=f"claude-err-{run_id[:8]}", daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        threading.Thread(target=self._wait, args=(run_id, process, project_key, stdout_thread, stderr_thread),
                         name=f"claude-wait-{run_id[:8]}", daemon=True).start()
        return self.get(run_id)

    def resume(self, run_id, prompt, *, model: str | None = None, effort: str | None = None) -> dict:
        previous = self.get(run_id)
        if not previous.get("thread_id"):
            raise RuntimeError("The Claude session id is not available")
        if previous["status"] not in self.TERMINAL:
            raise RuntimeError("Cannot resume a running Claude task")
        return self.start(prompt, previous["project"], sandbox=previous["sandbox"],
                          approval=previous["approval"], squad_task_id=previous.get("squad_task_id"),
                          squad_agent_id=previous.get("squad_agent_id"),
                          resume_thread_id=previous["thread_id"],
                          model=model or previous.get("model"), effort=effort or previous.get("effort"))

    # -- stream-json ---------------------------------------------------------
    def _error(self, record, source, kind, message, **extra):
        record["errors"].append(message)
        record.setdefault("error_events", []).append({
            "seq": self._next_oracle_seq(record), "source": source, "kind": kind,
            "tool": extra.get("tool"), "command": extra.get("command"),
            "exit_code": extra.get("exit_code"), "message": message})

    def _refuse_profile(self, record, event):
        """Return a refusal message when the CLI did not load exactly what Quartz asked for."""
        tools = sorted(str(t) for t in (event.get("tools") or []))
        servers = [s.get("name") if isinstance(s, dict) else str(s) for s in (event.get("mcp_servers") or [])]
        if tools != record["_expected_tools"]:
            return f"Claude araç listesi beklenenden farklı: {tools}"
        if servers:
            return f"Claude beklenmeyen MCP sunucusu yükledi: {servers}"
        if event.get("permissionMode") not in (None, "dontAsk"):
            return f"Claude izin modu beklenenden farklı: {event.get('permissionMode')}"
        return ""

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
                refused = ""
                with self._lock:
                    record = self._runs.get(run_id)
                    if not record or record.get("status") in self.TERMINAL:
                        continue
                    if record.get("first_event_at") is None:
                        record["first_event_at"] = time.time()
                    record["events"].append(_compact(event))
                    kind, subtype = event.get("type"), event.get("subtype")
                    if kind == "system" and subtype == "init":
                        refused = self._refuse_profile(record, event)
                        if refused:
                            self._error(record, "profile_guard", "profile_mismatch", refused)
                        else:
                            record["tools_verified"] = True
                            record["thread_id"] = event.get("session_id") or record.get("thread_id")
                    elif not record["tools_verified"] and kind in ("assistant", "user"):
                        refused = "Claude araç doğrulamasından önce çalışmaya başladı"
                        self._error(record, "profile_guard", "unverified_profile", refused)
                    elif kind == "assistant":
                        self._on_assistant(record, event)
                    elif kind == "user":
                        self._on_tool_results(record, event)
                    elif kind == "result":
                        record["usage"] = event.get("usage")
                        record["cost_usd"] = event.get("total_cost_usd")
                        text_val = str(event.get("result") or "")
                        # A failed turn can still say subtype "success": is_error decides.
                        if event.get("is_error") or subtype not in (None, "success"):
                            self._error(record, "result", "turn_failed", text_val or f"Claude turn failed ({subtype})")
                        elif text_val:
                            record["result"] = text_val
                if refused:
                    stop_process_tree(process, timeout=5)
                    return
        except (OSError, ValueError):
            pass

    def _on_assistant(self, record, event):
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text"):
                if record.get("first_text_at") is None:
                    record["first_text_at"] = time.time()
            elif block.get("type") == "tool_use":
                record["_pending_tools"][block.get("id")] = (block.get("name"), block.get("input") or {})

    def _on_tool_results(self, record, event):
        for block in (event.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            name, data = record["_pending_tools"].pop(block.get("tool_use_id"), (None, {}))
            failed = bool(block.get("is_error"))
            output = _tool_text(block.get("content"))[:4000]
            seq = self._next_oracle_seq(record)
            if name in SHELL_TOOLS:
                command = str(data.get("command") or "")[:1000]
                record["commands"].append({"command": command, "exit_code": None if failed else 0, "output": output})
                record["command_exit_codes"].append(None if failed else 0)
                record["command_results"].append({
                    "seq": seq, "tool": name, "command": command, "exit_code": None if failed else 0,
                    "ok": not failed, "state": "ERROR" if failed else "DONE", "output": output,
                    "error": output[:1000] if failed else ""})
                if failed:
                    record["error_events"].append({"seq": seq, "source": "command", "kind": "command_error",
                                                   "tool": name, "command": command, "exit_code": None,
                                                   "message": output[:1000] or "Command failed"})
            elif name in FILE_TOOLS:
                path = str(data.get("file_path") or data.get("notebook_path") or "")
                if not path:
                    continue
                record["file_changes"].append({"seq": seq, "path": path, "kind": FILE_TOOLS[name],
                                               "tool": name, "state": "ERROR" if failed else "DONE"})
                if failed:
                    continue
                if self._is_scratch_workspace_path(record.get("project", ""), path):
                    if path not in record["scratch_files_changed"]:
                        record["scratch_files_changed"].append(path)
                    continue
                if path not in record["files_changed"]:
                    record["files_changed"].append(path)
                if record.get("sandbox") == "read-only":
                    record["unauthorized_write_detected"] = True
                    if path not in record["unauthorized_files_changed"]:
                        record["unauthorized_files_changed"].append(path)
                    self._error(record, "sandbox_guard", "unauthorized_readonly_write",
                                f"Read-only Claude run modified file without write permission: {path}",
                                tool=name)


def _tool_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return ""


def _compact(event):
    """Events kept on the record: drop the bulky init inventory."""
    if event.get("type") == "system" and event.get("subtype") == "init":
        return {k: event.get(k) for k in ("type", "subtype", "session_id", "model", "tools",
                                         "mcp_servers", "permissionMode", "claude_code_version")}
    return event
