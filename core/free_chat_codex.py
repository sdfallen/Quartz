"""The "ChatGPT hesabın (Codex)" channel of Ücretsiz sohbet (27 Nov 2026).

Fides: design ŞARTLI KABUL (20261127-1613), implementation RED (1629, CG1-CG4), design 2 ŞARTLI KABUL
(1638, D2-1..D2-4). The channel stays closed in code (free_chat.ACCOUNT_CHANNEL_OPEN) until Fides's
independent review and the user's separately approved live acceptance.

- Its own Codex home ``free_chat\\codex-home`` (D2-2): every call - version, sign-in status, MCP
  listing, feature listing, sign-in and the turn - runs with that CODEX_HOME, without any API key or
  endpoint, and with the same policy + feature flags (core.codex_runtime.account_profile_flags:
  forced_login_method="chatgpt" and the file credential store on the command line, D2-1). The shared
  Codex home (Fides's own sign-in) is never passed to these calls.
- The sign-in is the user's own click on this channel's "ChatGPT ile giriş"; SpeS never reads,
  copies or logs the token.
- Before every turn, under the channel's lock, a fresh opening gate (D2-3): a supported CLI version
  and the launcher chain's SHA-256; the home's contents against a narrow allow-list (no config.toml,
  skills, hooks, AGENTS.md, plugins...; an unknown entry or a link closes it); `mcp list --json` is
  []; `features list` shows every ACCOUNT_FEATURES_OFF false and nothing outside
  ACCOUNT_FEATURES_ALLOWED_ON true; `login status` is exactly "Logged in using ChatGPT".
- Ownership (CG3/CG4, D2-4): the run id is chosen before the start; a turn whose process exit is not
  confirmed stays pending and blocks the next turn and sign-in until cancel()'s cleanup confirms it;
  a start failure deletes the room only when the runtime's record proves no process was created.
  The answer is returned only after the exit is confirmed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

TURN_SECONDS = 120
POLL_SECONDS = 0.4
SETTLE_SECONDS = 5
CALL_SECONDS = 30
LOGIN_SECONDS = 600
SUPPORTED_CLI = frozenset({"codex-cli 0.163.0"})
PROFILE_VERSION = "account-chat-2"
SIGNED_IN = "Logged in using ChatGPT"
# The home's allow-list (codex-cli 0.163.0). Entries a real sign-in adds are to be confirmed with
# Fides during the approved live acceptance; until then anything else keeps the channel closed.
_NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}"
HOME_ALLOWED = (
    (re.compile(r"auth\.json"), "file"),
    (re.compile(r"(version|models_cache)\.json"), "file"),
    (re.compile(r"tmp"), "dir"),
    (re.compile(r"tmp/arg0-windows"), "dir"),
    (re.compile(rf"tmp/arg0-windows/{_NAME}"), "any"),
    (re.compile(rf"tmp/arg0-windows/{_NAME}/{_NAME}"), "file"),
    (re.compile(r"log"), "dir"),
    (re.compile(r"log/codex-[A-Za-z0-9_.-]{0,60}\.log"), "file"),
)


class AccountChatError(Exception):
    """str() is a free_chat.EXPLAIN kind (busy, account, quota, unreachable, cancelled, other, closed)."""


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


def _is_link(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return True
    return path.is_symlink() or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def home_problem(home: Path) -> str:
    """'' when the home holds only allowed entries; else the first reason (names only, no content)."""
    if not home.is_dir() or _is_link(home):
        return "Codex evi yok ya da bir bağlantı"
    for folder, dirs, files in os.walk(home, followlinks=False):
        for name in sorted(dirs) + sorted(files):
            path = Path(folder) / name
            rel = path.relative_to(home).as_posix()
            if _is_link(path):
                return f"bağlantı: {rel}"
            kind = "dir" if path.is_dir() else "file"
            if not any(rx.fullmatch(rel) and want in (kind, "any") for rx, want in HOME_ALLOWED):
                return f"beklenmeyen: {rel}"
    return ""


def parse_features(text: str) -> dict | None:
    rows = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1] in {"true", "false"}:
            rows[parts[0]] = parts[-1] == "true"
    return rows or None


def features_problem(rows: dict | None) -> str:
    from core.codex_runtime import ACCOUNT_FEATURES_ALLOWED_ON, ACCOUNT_FEATURES_OFF
    if not rows:
        return "özellik listesi okunamadı"
    for name in ACCOUNT_FEATURES_OFF:
        if name in rows and rows[name]:
            return f"kapanmayan özellik: {name}"
    required = {"shell_tool", "unified_exec", "apps", "plugins", "hooks", "computer_use", "browser_use"}
    missing = sorted(n for n in required if n not in rows)
    if missing:
        return "özellik listesinde yok: " + ", ".join(missing)
    extra = sorted(n for n, on in rows.items() if on and n not in ACCOUNT_FEATURES_ALLOWED_ON)
    if extra:
        return "bilinmeyen açık özellik: " + ", ".join(extra)
    return ""


class CodexAccountChannel:
    def __init__(self, runtime_getter, base: Path, clock=time.monotonic, sleep=time.sleep, run=None,
                 environment=None):
        self._runtime = runtime_getter  # () -> CodexRuntime or None
        self.base = Path(base)
        self.home = self.base / "codex-home"
        self.rooms = self.base / "codex-rooms"
        self.clock, self.sleep = clock, sleep
        self._run = run
        self._environment = environment
        self._lock = threading.Lock()        # one turn, one sign-in, one settle at a time
        self._state_lock = threading.Lock()  # passive status never waits for the turn
        self._pending = None                 # {"run_id", "room"} until its exit is confirmed
        self._login_running = False
        self._last = {"installed": False, "chatgpt": False, "checked": None, "reason": "", "login": False}
        self._receipts = {}

    # ── passive state ────────────────────────────────────────────────────────────
    def last(self) -> dict:
        with self._state_lock:
            state = dict(self._last)
            state["login"] = self._login_running
            state["pending"] = self._pending is not None
            return state

    def installed(self) -> bool:
        runtime = self._runtime()
        return bool(runtime is not None and getattr(runtime, "executable", None))

    def _remember(self, **values):
        with self._state_lock:
            self._last.update(values)

    # ── calls in the channel's own home ─────────────────────────────────────────
    def env(self) -> dict:
        from core.codex_runtime import account_only_environment
        if self._environment is not None:
            base = self._environment()
        else:
            from core.cli_installer import cli_environment
            base = cli_environment()
        return account_only_environment(base, self.home)

    def _call(self, runtime, args, timeout=CALL_SECONDS):
        from core.codex_runtime import account_profile_flags
        run = self._run
        if run is None:
            from core.cli_installer import owned_run as run
        command = runtime._command([*account_profile_flags(), *args])
        import subprocess
        done = run(command, capture_output=True, text=True, timeout=timeout, env=self.env(), cwd=str(self.base),
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return int(done.returncode), str(done.stdout or ""), str(done.stderr or "")

    @staticmethod
    def _find_late_install(runtime) -> None:
        """Codex set up while SpeS runs is found by a path lookup on the user's explicit check."""
        if runtime is not None and not getattr(runtime, "executable", None):
            try:
                runtime.executable = runtime._find_executable()
                runtime._init_error = ""
            except Exception:
                pass

    def _receipt(self, runtime) -> str:
        """Fides: bound to the resolved launcher chain's SHA-256, the CLI version and the profile."""
        files = []
        for token in runtime._command(["--version"]):
            path = Path(str(token))
            if path.is_file():
                files.append(path.resolve())
        digest = hashlib.sha256()
        for path in files:
            with path.open("rb") as stream:
                digest.update(str(path).encode("utf-8") + b"\0" + hashlib.file_digest(stream, "sha256").digest())
        code, out, _err = self._call(runtime, ["--version"])
        version = out.strip()
        if code != 0 or version not in SUPPORTED_CLI:
            raise AccountChatError("closed:desteklenmeyen Codex sürümü")
        return f"{digest.hexdigest()}|{version}|{PROFILE_VERSION}"

    def _gate_locked(self, runtime) -> dict:
        """The full opening gate, fresh (D2-3). Never starts a model call."""
        state = {"installed": False, "chatgpt": False, "checked": time.time(), "reason": ""}
        if runtime is None or not getattr(runtime, "executable", None):
            state["reason"] = "Codex kurulu değil"
            return state
        state["installed"] = True
        try:
            receipt = self._receipt(runtime)
            problem = home_problem(self.home)
            if problem:
                raise AccountChatError("closed:" + problem)
            code, out, _err = self._call(runtime, ["mcp", "list", "--json"])
            try:
                servers = json.loads(out)
            except ValueError:
                servers = None
            if code != 0 or servers != []:
                raise AccountChatError("closed:Codex evinde araç sunucusu var ya da liste okunamadı")
            code, out, _err = self._call(runtime, ["features", "list"])
            problem = features_problem(parse_features(out) if code == 0 else None)
            if problem:
                raise AccountChatError("closed:" + problem)
            code, out, err = self._call(runtime, ["login", "status"])
            lines = [line.strip() for line in (out + "\n" + err).splitlines() if line.strip()
                     and not line.strip().startswith("WARNING:")]
            if code != 0 or lines != [SIGNED_IN]:
                raise AccountChatError("closed:ChatGPT ile giriş yapılmamış")
            problem = home_problem(self.home)  # the listings may write too: read it again
            if problem:
                raise AccountChatError("closed:" + problem)
            state.update(chatgpt=True, receipt=receipt)
        except AccountChatError as exc:
            state["reason"] = str(exc).removeprefix("closed:")
        except Exception:
            state["reason"] = "Codex denetimi tamamlanamadı"
        return state

    def check(self) -> dict:
        """The user's explicit "Kontrol et ve bağla"."""
        runtime = self._runtime()
        self._find_late_install(runtime)
        if not self._lock.acquire(blocking=False):
            return self.last()
        try:
            state = self._gate_locked(runtime)
        finally:
            self._lock.release()
        self._remember(**state)
        return state

    # ── the channel's own sign-in ────────────────────────────────────────────────
    def login(self) -> dict:
        """The user's click: `codex login` (ChatGPT, browser) in the channel's home. Never a turn at
        the same time; never an API key."""
        runtime = self._runtime()
        self._find_late_install(runtime)
        if runtime is None or not getattr(runtime, "executable", None):
            raise AccountChatError("closed:Codex kurulu değil")
        if not self._lock.acquire(blocking=False):
            raise AccountChatError("busy")
        try:
            self._settle_locked(runtime)
            self.home.mkdir(parents=True, exist_ok=True)
            if _is_link(self.home) or _is_link(self.base):
                raise AccountChatError("closed:Codex evi bir bağlantı")
        except BaseException:
            self._lock.release()
            raise
        with self._state_lock:
            self._login_running = True

        def work():
            try:
                self._call(runtime, ["login"], timeout=LOGIN_SECONDS)
            except Exception:
                pass
            finally:
                with self._state_lock:
                    self._login_running = False
                try:
                    state = self._gate_locked(runtime)
                finally:
                    self._lock.release()
                self._remember(**state)
        threading.Thread(target=work, daemon=True, name="spes-chatgpt-login").start()
        return {"started": True}

    # ── one turn ─────────────────────────────────────────────────────────────────
    def _confirmed(self, runtime, run_id) -> bool:
        try:
            record = runtime.get(run_id)
        except Exception:
            return False
        return record.get("process_exit_confirmed") is True and not record.get("cleanup_pending")

    def _settle_locked(self, runtime) -> None:
        """A pending turn blocks everything new until its exit is confirmed (CG3)."""
        pending = self._pending
        if pending is None:
            return
        if not self._confirmed(runtime, pending["run_id"]):
            try:
                runtime.cancel(pending["run_id"])  # retries the owned cleanup
            except Exception:
                pass
        if not self._confirmed(runtime, pending["run_id"]):
            raise AccountChatError("busy")
        self._release_room(pending["room"])
        self._pending = None

    def _release_room(self, room: Path) -> None:
        if room.parent == self.rooms and not _is_link(room):
            shutil.rmtree(room, ignore_errors=True)

    def ask(self, prompt: str, cancel: threading.Event, gate) -> str:
        """``gate()`` raises when Stop, the consent for this call's role or access is gone; it runs
        before the fresh opening gate and again right before the start."""
        runtime = self._runtime()
        if not self._lock.acquire(blocking=False):
            raise AccountChatError("busy")
        try:
            self._settle_locked(runtime)
            gate()
            state = self._gate_locked(runtime)
            self._remember(**state)
            if not state["chatgpt"]:
                raise AccountChatError("account")
            gate()
            self.rooms.mkdir(parents=True, exist_ok=True)
            room = Path(tempfile.mkdtemp(prefix="turn-", dir=self.rooms))
            run_id = uuid.uuid4().hex
            self._pending = {"run_id": run_id, "room": room}
            try:
                runtime.start(prompt, str(room), sandbox="read-only", approval="never", tool_guard=True,
                              web=False, should_abort=cancel.is_set, account_chat=True, codex_home=str(self.home),
                              run_id=run_id)
            except Exception:
                try:
                    record = runtime.get(run_id)
                except KeyError:
                    record = None  # the run never got a record: no process can exist
                except Exception:
                    record = {}  # unknown: keep it pending
                if record is None or (record.get("process_started") is not True
                                      and record.get("process_exit_confirmed") is True):
                    self._release_room(room)
                    self._pending = None
                raise AccountChatError("cancelled" if cancel.is_set() else "other") from None
            deadline = self.clock() + TURN_SECONDS
            while True:
                record = runtime.get(run_id)
                if record.get("status") in {"completed", "failed", "cancelled"}:
                    break
                if cancel.is_set():
                    runtime.cancel(run_id)
                    break
                if self.clock() >= deadline:
                    runtime.cancel(run_id)
                    self._wait_exit(runtime, run_id)
                    self._settle_quietly(runtime)
                    raise AccountChatError("unreachable")
                self.sleep(POLL_SECONDS)
            self._wait_exit(runtime, run_id)
            confirmed = self._settle_quietly(runtime)
            if cancel.is_set() or record.get("status") == "cancelled":
                raise AccountChatError("cancelled")
            if not confirmed:
                raise AccountChatError("busy")  # an answer is published only after a confirmed exit
            if record.get("status") == "failed":
                raise AccountChatError(classify_record(record))
            text = str(record.get("result") or "").strip()
            if not text:
                raise AccountChatError("other")
            return text
        finally:
            self._lock.release()

    def _wait_exit(self, runtime, run_id) -> None:
        until = self.clock() + SETTLE_SECONDS
        while not self._confirmed(runtime, run_id) and self.clock() < until:
            self.sleep(POLL_SECONDS)

    def _settle_quietly(self, runtime) -> bool:
        try:
            self._settle_locked(runtime)
            return True
        except AccountChatError:
            return False
