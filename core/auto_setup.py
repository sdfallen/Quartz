"""Autonomous setup (27 Nov 2026): SpeS brings its own tools.

The user asked that nobody installing SpeS should have to install or open anything else: every
resource is set up with SpeS and removed with SpeS; what is left to the person is signing in to
their accounts and using the app. On the first start (and on later starts while something is
still missing) SpeS installs, by itself and in the background, the official command-line tools
its agents use into its own private folder (``%LOCALAPPDATA%\\Quartz\\bin``):

- Codex CLI (``@openai/codex``) and Claude Code (``@anthropic-ai/claude-code``) from the npm
  registry with a private Node.js runtime from nodejs.org (core.cli_installer: pinned hosts,
  ``--ignore-scripts``, a ``--version`` gate);
- Antigravity CLI from Google's manifest (SHA-512 + Google Authenticode + ``--version``).

Nothing is added to PATH, the registry or another app; an existing working install is reused.
The uninstaller removes the private folder (installer/Quartz.iss). Signing in stays the user's:
SpeS opens each tool's own official sign-in when they choose, never enters a password.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json

TOOLS = (("codex", "Codex (Fides)"), ("agy", "Antigravity (Eos)"), ("claude", "Claude Code (Fatum)"))
RETRY_SECONDS = 6 * 3600


class AutoSetup:
    def __init__(self, installer, state_path: Path | None = None, clock=time.time, resolve=None):
        from core.cli_installer import managed_root, resolve_cli
        self.installer = installer
        self.state_path = Path(state_path or (managed_root() / "auto_setup.json"))
        self.clock = clock
        self.resolve = resolve or resolve_cli
        self.lock = threading.Lock()
        self.thread = None
        self.live = {"state": "idle", "current": None, "done": [], "failed": {}}

    def missing(self) -> list:
        result = []
        for tool, _label in TOOLS:
            try:
                self.resolve(tool)
            except (FileNotFoundError, ValueError, OSError):
                result.append(tool)
        return result

    def _recently_failed(self, tool) -> bool:
        state = load_json(self.state_path, {})
        failed = (state.get("failed") or {}).get(tool) or {}
        return bool(failed.get("at")) and self.clock() - float(failed["at"]) < RETRY_SECONDS

    def start(self) -> dict:
        """Start the background setup once per run when something is missing; never twice."""
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return self.status()
            todo = [t for t in self.missing() if not self._recently_failed(t)]
            if not todo:
                self.live.update(state="ready" if not self.missing() else "waiting", current=None)
                return self.status()
            self.live = {"state": "running", "current": None, "done": [], "failed": {}, "todo": todo}
            self.thread = threading.Thread(target=self._run, args=(todo,), daemon=True, name="spes-auto-setup")
            self.thread.start()
            return self.status()

    def _run(self, todo):
        state = load_json(self.state_path, {})
        state.setdefault("failed", {})
        for tool in todo:
            with self.lock:
                self.live["current"] = tool
            try:
                self.installer.install(tool)
                state["failed"].pop(tool, None)
                with self.lock:
                    self.live["done"].append(tool)
            except Exception as exc:  # recorded and retried later; never blocks the app
                message = str(exc)[:200]
                state["failed"][tool] = {"at": self.clock(), "message": message}
                with self.lock:
                    self.live["failed"][tool] = message
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(self.state_path, state)
            except OSError:
                pass
        with self.lock:
            self.live.update(state="done" if not self.live["failed"] else "partial", current=None)

    def status(self) -> dict:
        labels = dict(TOOLS)
        live = json.loads(json.dumps(self.live))
        live["current_label"] = labels.get(live.get("current"))
        live["total"] = len(live.get("todo") or [])
        live["labels"] = labels
        return live
