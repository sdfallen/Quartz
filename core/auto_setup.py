"""Autonomous setup (27 Nov 2026): SpeS brings its own tools.

The user asked that nobody installing SpeS should have to install or open anything else: every
resource is set up with SpeS and removed with SpeS; what is left to the person is signing in to
their accounts and using the app. SpeS installs, by itself and in the background, the official
command-line tools its agents use into its own private folder (``%LOCALAPPDATA%\\Quartz\\bin``):

- Codex CLI (``@openai/codex``) and Claude Code (``@anthropic-ai/claude-code``) from the npm
  registry with a private Node.js runtime from nodejs.org (core.cli_installer: pinned hosts,
  ``--ignore-scripts``, a ``--version`` gate; Claude's signed native program);
- Antigravity CLI from Google's manifest (SHA-512 + Google Authenticode + ``--version``).

Fides 27 Nov (FS6): one clear first choice. "Geliştirme araçlarını hazırla" (with the download
size said beforehand) authorises the setup, and SpeS then finishes it by itself on later starts
too; "Yalnız ücretsiz sohbet" downloads nothing. Reading the status never starts anything. A stop
request ends the setup after the tool being installed (a running npm/download is not torn
midway); the uninstaller removes the private folder (installer/Quartz.iss).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json

TOOLS = (("python", "Python (SpeS'in kendi)"), ("codex", "Codex (Fides)"), ("agy", "Antigravity (Eos)"),
         ("claude", "Claude Code (Fatum)"))
RETRY_SECONDS = 6 * 3600
# Measured 27 Nov: Claude Code's native program alone is ~400 MB; Antigravity ~200 MB.
DOWNLOAD_TEXT = "yaklaşık 850 MB indirir, diskte yaklaşık 1,6 GB yer kaplar"


class AutoSetup:
    def __init__(self, installer, state_path: Path | None = None, clock=time.time, resolve=None):
        from core.cli_installer import managed_root, resolve_cli

        def default_resolve(tool):
            if tool == "python":
                from core.managed_python import published
                found = published()
                if found is None:
                    raise FileNotFoundError("SpeS'in Python'u henüz kurulu değil")
                return str(found)
            return resolve_cli(tool)
        self.installer = installer
        self.state_path = Path(state_path or (managed_root() / "auto_setup.json"))
        self.clock = clock
        self.resolve = resolve or default_resolve
        self.lock = threading.Lock()
        self.thread = None
        self.stop_event = threading.Event()
        self.live = {"state": "idle", "current": None, "done": [], "failed": {}}

    def _state(self) -> dict:
        state = load_json(self.state_path, {})
        return state if isinstance(state, dict) else {}

    def _save(self, state):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.state_path, state)
        except OSError:
            pass

    def consented(self) -> bool:
        return bool(self._state().get("consent"))

    def missing(self) -> list:
        result = []
        for tool, _label in TOOLS:
            try:
                self.resolve(tool)
            except (FileNotFoundError, ValueError, OSError):
                result.append(tool)
        return result

    def _recently_failed(self, tool) -> bool:
        failed = (self._state().get("failed") or {}).get(tool) or {}
        return bool(failed.get("at")) and self.clock() - float(failed["at"]) < RETRY_SECONDS

    def start(self, consent: bool = False) -> dict:
        """Start (or continue) the setup: with the user's choice now, or with the one recorded
        earlier. Never twice at once; never without a choice."""
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return self._status_locked()
            state = self._state()
            if consent and not state.get("consent"):
                state["consent"] = {"at": self.clock()}
                self._save(state)
            if not state.get("consent"):
                self.live["state"] = "needs_choice" if self.missing() else "ready"
                return self._status_locked()
            todo = [t for t in self.missing() if consent or not self._recently_failed(t)]
            if not todo:
                self.live.update(state="ready" if not self.missing() else "waiting", current=None)
                return self._status_locked()
            self.stop_event.clear()
            self.live = {"state": "running", "current": None, "done": [], "failed": {}, "todo": todo}
            self.thread = threading.Thread(target=self._run, args=(todo,), daemon=True, name="spes-auto-setup")
            self.thread.start()
            return self._status_locked()

    def stop(self) -> dict:
        """Ends the setup after the tool being installed now; its staging stays unpublished."""
        self.stop_event.set()
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                self.live["state"] = "stopping"
            return self._status_locked()

    def forget_choice(self):
        """Fides RFS3: also stops the tools still waiting; the one being installed may finish."""
        self.stop_event.set()
        state = self._state()
        state.pop("consent", None)
        self._save(state)
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                self.live["state"] = "stopping"

    def _run(self, todo):
        for tool in todo:
            if self.stop_event.is_set() or not self.consented():
                break
            with self.lock:
                self.live["current"] = tool
            try:
                self.installer.install(tool)
                outcome = None
            except Exception as exc:  # recorded and retried later; never blocks the app
                outcome = str(exc)[:200]
            state = self._state()
            failed = state.setdefault("failed", {})
            if outcome is None:
                failed.pop(tool, None)
            else:
                failed[tool] = {"at": self.clock(), "message": outcome}
            self._save(state)
            with self.lock:
                if outcome is None:
                    self.live["done"].append(tool)
                else:
                    self.live["failed"][tool] = outcome
        with self.lock:
            stopped = self.stop_event.is_set() and len(self.live["done"]) + len(self.live["failed"]) < len(todo)
            self.live.update(state="stopped" if stopped else "done" if not self.live["failed"] else "partial",
                             current=None)

    def _status_locked(self) -> dict:
        labels = dict(TOOLS)
        live = json.loads(json.dumps(self.live))
        live["current_label"] = labels.get(live.get("current"))
        live["total"] = len(live.get("todo") or [])
        live["labels"] = labels
        live["download"] = DOWNLOAD_TEXT
        return live

    def status(self) -> dict:
        """Read only: never starts or stops anything (Fides FS6)."""
        with self.lock:
            if self.live["state"] == "idle":
                if not self.consented():
                    self.live["state"] = "needs_choice" if self.missing() else "ready"
                elif not self.missing():
                    self.live["state"] = "ready"
            return self._status_locked()
