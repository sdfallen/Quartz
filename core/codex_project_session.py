"""Codex project-read turns over `codex app-server` (stdio JSON-RPC).

Why not `exec`: a separate `codex mcp list` probe cannot prove what the real
session loads (Codex owner review). Here the SAME session is opened first,
its effective MCP inventory is read with that session's thread id, and only
when it is exactly Quartz's three read tools (every other server disabled)
is the user's prompt delivered with `turn/start`. Server requests (approvals,
elicitations) are refused; any tool call outside quartz_project ends the turn.
"""
from __future__ import annotations

import json
import threading
import time

ALLOWED_SERVER = "quartz_project"
ALLOWED_TOOLS = frozenset({"project_list", "project_read", "project_search"})
REQUEST_TIMEOUT = 60
STARTUP_TIMEOUT = 45


class SessionRefused(RuntimeError):
    """The session could not be proven safe; no prompt was delivered."""


class AppServerSession:
    def __init__(self, process, *, on_event=None):
        self.process = process
        self.on_event = on_event or (lambda message: None)
        self._next_id = 0
        self._responses = {}
        self._notifications = []
        self._cond = threading.Condition()
        self._closed = False
        self._reader = threading.Thread(target=self._read, name="codex-appserver-read", daemon=True)
        self._reader.start()

    # -- transport -------------------------------------------------------
    def _send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _read(self):
        try:
            for raw in self.process.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                if "method" in message and "id" in message:
                    # A server->client request (approval, elicitation, user input):
                    # a read-only project turn never grants anything.
                    try:
                        self._send({"jsonrpc": "2.0", "id": message["id"],
                                    "error": {"code": -32000, "message": "Quartz project read: request refused"}})
                    except Exception:
                        pass
                    self.on_event({"kind": "server_request_refused", "method": str(message.get("method"))[:80]})
                    continue
                with self._cond:
                    if "id" in message and ("result" in message or "error" in message):
                        self._responses[message["id"]] = message
                    elif "method" in message:
                        self._notifications.append(message)
                    self._cond.notify_all()
        finally:
            with self._cond:
                self._closed = True
                self._cond.notify_all()

    def request(self, method, params, timeout=REQUEST_TIMEOUT):
        with self._cond:
            self._next_id += 1
            request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        with self._cond:
            while request_id not in self._responses:
                remaining = deadline - time.monotonic()
                if self._closed or remaining <= 0:
                    raise SessionRefused(f"No response to {method}")
                self._cond.wait(min(remaining, 0.5))
            response = self._responses.pop(request_id)
        if "error" in response:
            raise SessionRefused(f"{method} failed: {str(response['error'].get('message'))[:200]}")
        return response.get("result") or {}

    def notify(self, method, params=None):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def next_notification(self, timeout):
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self._notifications:
                remaining = deadline - time.monotonic()
                if self._closed or remaining <= 0:
                    return None
                self._cond.wait(min(remaining, 0.5))
            return self._notifications.pop(0)

    # -- protocol --------------------------------------------------------
    def open_verified_thread(self, *, cwd, model=None, should_abort=None, expected_root=None):
        """initialize -> config gate -> thread/start -> prove the thread's tool set. Returns the thread id."""
        self.request("initialize", {"clientInfo": {"name": "quartz", "version": "1"}})
        self.notify("initialized")
        # Start gate: the effective config of THIS app-server, read before any
        # thread exists, must already allow only Quartz's server (so no other
        # MCP server can be launched by thread/start). Codex owner review.
        config = self.request("config/read", {"cwd": str(cwd)}).get("config")
        refusal = config_refusal(config, expected_root)
        if refusal:
            raise SessionRefused(f"Codex config would start more than Quartz's read tools ({refusal})")
        if should_abort and should_abort():
            raise SessionRefused("Cancelled before the thread was started")
        params = {"cwd": str(cwd), "sandbox": "read-only", "approvalPolicy": "never", "ephemeral": True}
        if model:
            params["model"] = model
        started = self.request("thread/start", params)
        thread = started.get("thread") if isinstance(started, dict) else None
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise SessionRefused("Codex did not return a thread id")
        sandbox = json.dumps(started.get("sandbox")).lower()
        if "read" not in sandbox or "write" in sandbox or "danger" in sandbox or "full" in sandbox:
            raise SessionRefused("Codex thread is not read-only")
        if str(started.get("approvalPolicy")).lower() not in {"never", '"never"'}:
            raise SessionRefused("Codex thread approval policy is not 'never'")
        self.verify_tools(thread_id, should_abort=should_abort)
        return thread_id

    def verify_tools(self, thread_id, should_abort=None):
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while True:
            if should_abort and should_abort():
                raise SessionRefused("Cancelled before the prompt was delivered")
            rows, cursor = [], None
            while True:
                page = self.request("mcpServerStatus/list", {"threadId": thread_id, "detail": "toolsAndAuthOnly",
                                                            **({"cursor": cursor} if cursor else {})})
                data = page.get("data")
                if not isinstance(data, list):
                    raise SessionRefused("Unexpected MCP inventory")
                rows.extend(data)
                cursor = page.get("nextCursor")
                if not cursor:
                    break
            state = inventory_state(rows)
            if state == "ok":
                return
            if state != "starting" or time.monotonic() >= deadline:
                raise SessionRefused(f"Codex tool set is not Quartz's read-only set ({state})")
            time.sleep(0.5)


def config_refusal(config, expected_root=None):
    """None when the effective config can only start quartz_project; else a reason."""
    if not isinstance(config, dict):
        return "config unreadable"
    features = config.get("features")
    if not isinstance(features, dict):
        return "features unreadable"
    for name in ("plugins", "apps", "hooks", "shell_tool", "unified_exec", "computer_use", "browser_use",
                 "multi_agent", "memories"):
        if features.get(name) is not False:
            return f"feature {name} not off"
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        return "mcp_servers unreadable"
    for name, server in servers.items():
        if not isinstance(server, dict):
            return f"server {str(name)[:40]} unreadable"
        if name == ALLOWED_SERVER:
            if server.get("enabled") is False:
                return "quartz_project disabled"
            args = server.get("args")
            if not isinstance(args, list) or "--project-read-server" not in args:
                return "quartz_project is not Quartz's read server"
            if expected_root is not None and str(expected_root) not in [str(a) for a in args]:
                return "quartz_project serves a different root"
        elif server.get("enabled") is not False:
            return f"server {str(name)[:40]} enabled"
    if ALLOWED_SERVER not in servers:
        return "quartz_project missing"
    return None


def inventory_state(rows):
    """'ok', 'starting' (Quartz tools not ready yet) or a refusal reason."""
    ours = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            return "unknown row"
        status = row.get("runtimeStatus")
        if row["name"] == ALLOWED_SERVER:
            ours.append(row)
            continue
        if status != "disabled":
            return f"extra server {row['name'][:40]} is {status}"
    if not ours:
        return "quartz_project missing"
    if len(ours) > 1:
        return "quartz_project listed twice"
    ours = ours[0]
    status = ours.get("runtimeStatus")
    if status in {"notStarted", "starting", None}:
        return "starting"
    if status != "connected":
        return f"quartz_project {status}"
    tools = ours.get("tools")
    names = set(tools.keys()) if isinstance(tools, dict) else {
        t.get("name") for t in tools if isinstance(t, dict)} if isinstance(tools, list) else set()
    if names != ALLOWED_TOOLS:
        return "quartz_project tools differ"
    return "ok"
