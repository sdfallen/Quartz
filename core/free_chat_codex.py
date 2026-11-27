"""The "ChatGPT hesabın (Codex)" channel of Ücretsiz sohbet (27 Nov 2026, Fides design: ŞARTLI KABUL).

A ChatGPT account has no API key, so this channel talks through the user's own Codex CLI sign-in,
on SpeS's existing CodexRuntime, in one fixed profile (``account_chat``): read-only, approval never,
every built-in tool off with the MCP set proven, no web, no desktop, no project, fresh (no resume),
no model or effort chosen by SpeS, ``--ephemeral`` (no session rollout files), ``--ignore-user-config``
and an environment without any API key or endpoint (core.codex_runtime.account_only_environment).

- The sign-in method is checked again right before every message: only "ChatGPT" opens it. An API-key
  sign-in (separately billed) or an output SpeS cannot read keeps it closed; nothing is logged out,
  switched or written in CODEX_HOME.
- Every turn gets its own new, SpeS-owned empty folder, removed only after the CLI's exit is confirmed.
- Stop cancels the owned run; a turn longer than TURN_SECONDS is cancelled and reported unreachable.
- Errors come from the runtime's own record (never from the answer's text).
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path

TURN_SECONDS = 120
POLL_SECONDS = 0.4


class AccountChatError(Exception):
    """str() is one of free_chat.EXPLAIN's kinds."""


def classify_record(record: dict) -> str:
    """quota | key | unreachable | other, from the runtime's error records only."""
    text = " ".join(str(e.get("message") or "") for e in record.get("error_events") or [])
    text = (text + " " + " ".join(str(e) for e in record.get("errors") or [])).lower()
    if any(w in text for w in ("usage limit", "rate limit", "429", "quota", "limit reached")):
        return "quota"
    if any(w in text for w in ("401", "403", "unauthorized", "forbidden", "not logged in", "login",
                                "sign in", "authentication", "plan does not", "not available on your plan")):
        return "key"
    if any(w in text for w in ("timed out", "timeout", "network", "connection", "stream disconnected",
                                "503", "502", "500", "unavailable", "overloaded")):
        return "unreachable"
    return "other"


class CodexAccountChannel:
    def __init__(self, runtime_getter, rooms: Path, clock=time.monotonic, sleep=time.sleep):
        self._runtime = runtime_getter  # () -> CodexRuntime or None
        self.rooms = Path(rooms)
        self.clock, self.sleep = clock, sleep
        self._lock = threading.Lock()
        self._last = {"installed": False, "chatgpt": False, "checked": None}

    # ── state ────────────────────────────────────────────────────────────────────
    def last(self) -> dict:
        """Passive: the last check SpeS made (never starts a process). Not a permission."""
        with self._lock:
            return dict(self._last)

    def installed(self) -> bool:
        runtime = self._runtime()
        return bool(runtime is not None and getattr(runtime, "executable", None))

    @staticmethod
    def _find_late_install(runtime) -> None:
        """Codex set up while SpeS runs (the channel's own "Codex'i kur") is found by a path lookup
        on the user's explicit check; no process starts."""
        if runtime is not None and not getattr(runtime, "executable", None):
            try:
                runtime.executable = runtime._find_executable()
                runtime._init_error = ""
            except Exception:
                pass

    def check(self) -> dict:
        """The user's explicit "Kontrol et" / connect, and every message's fresh gate: is Codex there
        and signed in WITH ChatGPT. Anything else - API key, unknown output - is not."""
        runtime = self._runtime()
        self._find_late_install(runtime)
        state = {"installed": False, "chatgpt": False, "checked": time.time()}
        if runtime is not None and getattr(runtime, "executable", None):
            try:
                probe = runtime.probe(force=True)
            except Exception:
                probe = {}
            state["installed"] = bool(probe.get("installed"))
            state["chatgpt"] = bool(probe.get("installed") and probe.get("authenticated")
                                    and probe.get("authentication") == "chatgpt")
        with self._lock:
            self._last = dict(state)
        return state

    # ── one turn ─────────────────────────────────────────────────────────────────
    def ask(self, prompt: str, cancel: threading.Event, gate) -> str:
        """``gate()`` raises when Stop, the consent for this call's role or access is gone; it is
        called right before the fresh sign-in check and again right before the run starts."""
        gate()
        if not self.check()["chatgpt"]:
            raise AccountChatError("key")
        runtime = self._runtime()
        gate()
        self.rooms.mkdir(parents=True, exist_ok=True)
        room = Path(tempfile.mkdtemp(prefix="turn-", dir=self.rooms))
        run_id = None
        try:
            try:
                started = runtime.start(prompt, str(room), sandbox="read-only", approval="never", tool_guard=True,
                                        web=False, should_abort=cancel.is_set, account_chat=True)
            except RuntimeError as exc:
                if cancel.is_set():
                    raise AccountChatError("cancelled") from None
                raise AccountChatError("other") from exc
            run_id = started["id"]
            deadline = self.clock() + TURN_SECONDS
            while True:
                record = runtime.get(run_id)
                if record.get("status") in {"completed", "failed", "cancelled"}:
                    break
                if cancel.is_set():
                    runtime.cancel(run_id)
                    raise AccountChatError("cancelled")
                if self.clock() >= deadline:
                    runtime.cancel(run_id)
                    raise AccountChatError("unreachable")
                self.sleep(POLL_SECONDS)
            if cancel.is_set() or record.get("status") == "cancelled":
                raise AccountChatError("cancelled")
            if record.get("status") == "failed":
                raise AccountChatError(classify_record(record))
            text = str(record.get("result") or "").strip()
            if not text:
                raise AccountChatError("other")
            return text
        finally:
            self._clean(runtime, run_id, room)

    def _clean(self, runtime, run_id, room: Path):
        """Fides: the room goes only once the CLI's exit is confirmed; otherwise it stays (owned,
        empty, never reused) rather than removing a folder a live process may still hold."""
        confirmed = run_id is None
        wait_until = self.clock() + 5
        while not confirmed:
            try:
                record = runtime.get(run_id)
                confirmed = record.get("process_exit_confirmed") is True and not record.get("cleanup_pending")
            except Exception:
                break
            if confirmed or self.clock() >= wait_until:
                break
            self.sleep(POLL_SECONDS)
        if confirmed and room.parent == self.rooms and not room.is_symlink():
            shutil.rmtree(room, ignore_errors=True)
