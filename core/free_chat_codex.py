"""The "ChatGPT hesabın (Codex)" channel of Ücretsiz sohbet (27-28 Nov 2026).

Fides: design ŞARTLI KABUL (20261127-1613), implementation RED (1629, CG1-CG4), design 2 ŞARTLI KABUL
(1638, D2-1..D2-4), implementation 2 RED (20261128, P1-1..P1-3, P2-4). The channel stays closed in code
(free_chat.ACCOUNT_CHANNEL_OPEN) until Fides's independent review and the user's separately approved
live acceptance.

- Its own Codex home ``free_chat\\codex-home`` (D2-2): every call - version, sign-in status, MCP
  listing, feature listing, sign-in and the turn - runs with that CODEX_HOME, without any API key or
  endpoint, and with the same policy + feature flags (core.codex_runtime.account_profile_flags:
  forced_login_method="chatgpt" and the file credential store on the command line, D2-1). The shared
  Codex home (Fides's own sign-in) is never passed to these calls.
- Real native binary resolution and receipt binding (P1-3): npm ``.cmd`` / ``bin/codex.js`` launchers
  are resolved through verified ``@openai/codex`` + ``@openai/codex-<platform>-<arch>`` packages to the
  actual native ``codex.exe`` binary; unresolvable wrappers or links fail closed. Both preflight/login
  calls and ``CodexRuntime.start`` execute that exact native binary directly, re-checking its SHA-256
  before spawning. ``connect()`` records the approved receipt; a binary change (even reporting the same
  CLI version string) invalidates the connection until re-checked.
- Pre-login and pre-turn gate (P1-1, P1-2, D2-3): before any CLI process runs (including ``login``),
  every existing ancestor of ``base``, ``home`` and ``rooms`` is checked against links/reparse points
  and ``home`` is scanned strictly with ``os.scandir`` (no swallowed ``os.walk`` errors); ``features list``
  is parsed line-by-line (rejecting malformed, duplicate or contradictory rows and requiring every
  ``ACCOUNT_FEATURES_OFF`` entry to be present and ``false``). ``login`` runs only after the full
  identity-free preflight passes.
- Ownership (CG3/CG4, D2-4, P2-4): the run id is chosen before the start; a turn whose process exit is
  not confirmed stays pending and blocks the next turn and sign-in until ``cancel()``'s cleanup confirms
  it; a start failure deletes the room only when the runtime's record proves no process was created.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
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
PROFILE_VERSION = "account-chat-3"
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
_FEATURE_ROW = re.compile(
    r"^([A-Za-z0-9_.-]+)\s+(stable|experimental|under development|deprecated|removed)\s+(true|false)$"
)
_PLATFORM_TARGETS = {
    ("windows", "amd64"): ("@openai/codex-win32-x64", "x86_64-pc-windows-msvc", "codex.exe", "win32", "x64"),
    ("windows", "x86_64"): ("@openai/codex-win32-x64", "x86_64-pc-windows-msvc", "codex.exe", "win32", "x64"),
    ("windows", "arm64"): ("@openai/codex-win32-arm64", "aarch64-pc-windows-msvc", "codex.exe", "win32", "arm64"),
    ("windows", "aarch64"): ("@openai/codex-win32-arm64", "aarch64-pc-windows-msvc", "codex.exe", "win32", "arm64"),
    ("linux", "x86_64"): ("@openai/codex-linux-x64", "x86_64-unknown-linux-musl", "codex", "linux", "x64"),
    ("linux", "amd64"): ("@openai/codex-linux-x64", "x86_64-unknown-linux-musl", "codex", "linux", "x64"),
    ("linux", "aarch64"): ("@openai/codex-linux-arm64", "aarch64-unknown-linux-musl", "codex", "linux", "arm64"),
    ("linux", "arm64"): ("@openai/codex-linux-arm64", "aarch64-unknown-linux-musl", "codex", "linux", "arm64"),
    ("darwin", "x86_64"): ("@openai/codex-darwin-x64", "x86_64-apple-darwin", "codex", "darwin", "x64"),
    ("darwin", "arm64"): ("@openai/codex-darwin-arm64", "aarch64-apple-darwin", "codex", "darwin", "arm64"),
}


class AccountChatError(Exception):
    """str() is a free_chat.EXPLAIN kind (busy, account, quota, unreachable, cancelled, other, closed:...)."""


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


def _ancestors_problem(path: Path, label: str, *, allow_leaf_file: bool = False) -> str:
    """Every existing ancestor (and the leaf if it exists) must be a real directory without links."""
    raw = Path(path)
    if not raw.is_absolute():
        return f"göreli yol: {label}"
    chain = []
    cur = raw
    while True:
        chain.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    for idx, node in enumerate(reversed(chain)):
        is_root = idx == 0
        is_leaf = node == raw
        try:
            exists = os.path.lexists(node)
        except OSError:
            return f"okunamayan yol: {label}"
        if not exists:
            continue
        if not is_root and _is_link(node):
            return f"bağlantı: {label}"
        try:
            st = os.lstat(node)
        except OSError:
            return f"okunamayan yol: {label}"
        import stat as _stat
        if is_leaf and allow_leaf_file:
            if not (_stat.S_ISREG(st.st_mode) or _stat.S_ISDIR(st.st_mode)):
                return f"geçersiz yol: {label}"
        elif not _stat.S_ISDIR(st.st_mode):
            return f"klasör değil: {label}"
    return ""


def home_problem(home: Path) -> str:
    """'' when the home holds only allowed entries; else the first reason (names only, no content).

    Fides P1-2: uses os.scandir explicitly so directory scan / permission errors fail closed instead
    of being silently skipped by os.walk.
    """
    import stat as _stat
    anc = _ancestors_problem(home, "Codex evi")
    if anc:
        return anc
    try:
        if not os.path.lexists(home):
            return "Codex evi yok ya da bir bağlantı"
    except OSError:
        return "Codex evi okunamadı"
    if _is_link(home) or not home.is_dir():
        return "Codex evi yok ya da bir bağlantı"
    stack = [home]
    while stack:
        folder = stack.pop()
        rel_folder = "." if folder == home else folder.relative_to(home).as_posix()
        try:
            with os.scandir(folder) as it:
                entries = sorted(list(it), key=lambda e: e.name)
        except OSError:
            return f"okunamayan klasör: {rel_folder}"
        dirs_next = []
        for entry in entries:
            entry_path = Path(folder) / entry.name
            rel = entry_path.relative_to(home).as_posix()
            if _is_link(entry_path):
                return f"bağlantı: {rel}"
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                return f"okunamayan: {rel}"
            if _stat.S_ISDIR(st.st_mode):
                kind = "dir"
                dirs_next.append(entry_path)
            elif _stat.S_ISREG(st.st_mode):
                kind = "file"
            else:
                return f"beklenmeyen tür: {rel}"
            if not any(rx.fullmatch(rel) and want in (kind, "any") for rx, want in HOME_ALLOWED):
                return f"beklenmeyen: {rel}"
        stack.extend(reversed(dirs_next))
    return ""


def roots_problem(base: Path, home: Path, rooms: Path, *, require_home: bool) -> str:
    """Fides P1-1: validate base, rooms, home and every existing parent before any CLI call."""
    for target, label in ((base, "taban klasör"), (rooms, "oda klasörü"), (home, "Codex evi")):
        problem = _ancestors_problem(target, label)
        if problem:
            return problem
    if require_home or os.path.lexists(home):
        return home_problem(home)
    return ""


class FeatureRows(dict):
    """dict[name -> bool] that also carries each feature's reported stage from `features list`."""

    def __init__(self, pairs: dict[str, tuple[str, bool]]):
        super().__init__({name: enabled for name, (_stage, enabled) in pairs.items()})
        self.stages = {name: stage for name, (stage, _enabled) in pairs.items()}


def parse_features_strict(text: str) -> tuple[FeatureRows | None, str]:
    """Fides P1-2: every non-empty line must be valid and unique; duplicates/contradictions fail."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return None, "özellik listesi okunamadı"
    pairs: dict[str, tuple[str, bool]] = {}
    for line in lines:
        match = _FEATURE_ROW.match(line)
        if not match:
            return None, "özellik listesinde geçersiz satır"
        name, stage, raw_val = match.group(1), match.group(2), match.group(3)
        if name in pairs:
            return None, f"tekrarlı ya da çelişkili özellik: {name}"
        pairs[name] = (stage, raw_val == "true")
    return FeatureRows(pairs), ""


def parse_features(text: str) -> FeatureRows | None:
    rows, problem = parse_features_strict(text)
    return None if problem else rows


def features_problem(source) -> str:
    """'' when every ACCOUNT_FEATURES_OFF entry is present and false, and nothing unexpected is true."""
    from core.codex_runtime import ACCOUNT_FEATURES_ALLOWED_ON, ACCOUNT_FEATURES_OFF, ACCOUNT_REMOVED_BUILTIN_ON
    if isinstance(source, str):
        strict_rows, problem = parse_features_strict(source)
        if problem or not strict_rows:
            return problem or "özellik listesi okunamadı"
        stages = strict_rows.stages
        rows = dict(strict_rows)
    elif isinstance(source, dict) and source:
        stages = dict(getattr(source, "stages", None) or {})
        rows = {}
        for name, val in source.items():
            if isinstance(val, tuple) and len(val) == 2 and isinstance(val[1], bool):
                stages[name] = str(val[0])
                rows[name] = val[1]
            elif isinstance(val, bool):
                stages.setdefault(name, "stable")
                rows[name] = val
            else:
                return "özellik listesi okunamadı"
    else:
        return "özellik listesi okunamadı"
    missing = sorted(name for name in ACCOUNT_FEATURES_OFF if name not in rows)
    if missing:
        return "özellik listesinde yok: " + ", ".join(missing)
    for name in ACCOUNT_FEATURES_OFF:
        if rows[name]:
            return f"kapanmayan özellik: {name}"
    extra = []
    for name, enabled in rows.items():
        if not enabled:
            continue
        stage = stages.get(name, "stable")
        if stage == "removed":
            if name not in ACCOUNT_REMOVED_BUILTIN_ON:
                extra.append(name)
        elif name not in ACCOUNT_FEATURES_ALLOWED_ON:
            extra.append(name)
    if extra:
        return "bilinmeyen açık özellik: " + ", ".join(sorted(extra))
    return ""


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _valid_platform_meta(plat_meta: dict, plat_pkg_name: str, plat_os: str, plat_cpu: str) -> bool:
    """Match either direct `@openai/codex-<os>-<cpu>` or OpenAI's official npm-aliased `@openai/codex` tarball."""
    if not isinstance(plat_meta, dict):
        return False
    name = plat_meta.get("name")
    if name == plat_pkg_name:
        return True
    if name != "@openai/codex":
        return False
    ver = plat_meta.get("version")
    os_list = plat_meta.get("os")
    cpu_list = plat_meta.get("cpu")
    return (
        isinstance(ver, str)
        and ver.endswith(f"-{plat_os}-{plat_cpu}")
        and (not os_list or (isinstance(os_list, list) and plat_os in os_list))
        and (not cpu_list or (isinstance(cpu_list, list) and plat_cpu in cpu_list))
    )


def resolve_codex_target(executable, *, system: str | None = None, machine: str | None = None) -> dict:
    """Fides P1-3: resolve npm .cmd/.js wrappers to the real native platform binary and hash the chain.

    Fails closed when any link/reparse point is in the lexical chain, when a wrapper is not the official
    ``@openai/codex`` layout, or when the platform binary is missing.
    """
    if not executable:
        raise AccountChatError("closed:Codex kurulu değil")
    raw = Path(str(executable))
    if not raw.is_absolute():
        raw = Path(os.path.abspath(str(raw)))
    anc = _ancestors_problem(raw, "Codex yürütücüsü", allow_leaf_file=True)
    if anc or not raw.is_file() or _is_link(raw):
        raise AccountChatError("closed:Codex yürütücüsü doğrulanamadı")
    suffix = raw.suffix.lower()
    chain = [raw]
    if suffix in {".bat", ".ps1", ".sh"}:
        raise AccountChatError("closed:desteklenmeyen Codex sarmalayıcısı")
    if suffix in {".cmd", ".js", ".mjs", ".cjs"}:
        if suffix == ".cmd":
            try:
                if raw.stat().st_size > 64 * 1024:
                    raise AccountChatError("closed:Codex sarmalayıcısı tanınmadı")
                wrapper_text = raw.read_text(encoding="utf-8", errors="replace").lower().replace("/", "\\")
            except OSError as exc:
                raise AccountChatError("closed:Codex sarmalayıcısı okunamadı") from exc
            if "@openai\\codex" not in wrapper_text:
                raise AccountChatError("closed:Codex sarmalayıcısı tanınmadı")
            pkg_root = raw.parent / "node_modules" / "@openai" / "codex"
            pkg_json = pkg_root / "package.json"
            if (_ancestors_problem(pkg_json, "Codex paketi", allow_leaf_file=True)
                    or not pkg_json.is_file() or _is_link(pkg_json)):
                raise AccountChatError("closed:Codex paketi doğrulanamadı")
            try:
                meta = json.loads(pkg_json.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise AccountChatError("closed:Codex paket bilgisi okunamadı") from exc
            if meta.get("name") != "@openai/codex":
                raise AccountChatError("closed:Codex paket kimliği uyuşmuyor")
            entry_def = meta.get("bin")
            rel_entry = entry_def.get("codex") if isinstance(entry_def, dict) else entry_def
            if not isinstance(rel_entry, str) or not rel_entry.strip():
                raise AccountChatError("closed:Codex giriş betiği tanımlı değil")
            rel_parts = [p for p in rel_entry.replace("\\", "/").split("/") if p not in ("", ".")]
            if not rel_parts or any(p == ".." for p in rel_parts):
                raise AccountChatError("closed:Codex giriş betiği doğrulanamadı")
            js_path = pkg_root.joinpath(*rel_parts)
            if (_ancestors_problem(js_path, "Codex giriş betiği", allow_leaf_file=True)
                    or not js_path.is_file() or _is_link(js_path)):
                raise AccountChatError("closed:Codex giriş betiği doğrulanamadı")
            chain.extend([js_path, pkg_json])
        else:
            js_path = raw
            pkg_root = js_path.parent.parent if js_path.parent.name == "bin" else js_path.parent
            pkg_json = pkg_root / "package.json"
            if (_ancestors_problem(pkg_json, "Codex paketi", allow_leaf_file=True)
                    or not pkg_json.is_file() or _is_link(pkg_json)):
                raise AccountChatError("closed:Codex paketi doğrulanamadı")
            try:
                meta = json.loads(pkg_json.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise AccountChatError("closed:Codex paket bilgisi okunamadı") from exc
            if meta.get("name") != "@openai/codex":
                raise AccountChatError("closed:Codex paket kimliği uyuşmuyor")
            chain.append(pkg_json)
        sys_key = (system or platform.system()).lower()
        arch_key = (machine or platform.machine()).lower()
        target_info = _PLATFORM_TARGETS.get((sys_key, arch_key))
        if not target_info:
            raise AccountChatError("closed:bu platform için Codex ikilisi tanımlı değil")
        plat_pkg_name, triple, bin_name, plat_os, plat_cpu = target_info
        short_name = plat_pkg_name.split("/", 1)[1]
        candidates = [
            pkg_root / "node_modules" / "@openai" / short_name,
            pkg_root.parent.parent / "@openai" / short_name,
        ]
        plat_root = next((c for c in candidates if os.path.lexists(c)), None)
        native = None
        vendor_root = None
        if plat_root is not None:
            plat_json = plat_root / "package.json"
            if (_ancestors_problem(plat_json, "Codex platform paketi", allow_leaf_file=True)
                    or not plat_json.is_file() or _is_link(plat_json)):
                raise AccountChatError("closed:Codex platform paketi doğrulanamadı")
            try:
                plat_meta = json.loads(plat_json.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise AccountChatError("closed:Codex platform paketi okunamadı") from exc
            if not _valid_platform_meta(plat_meta, plat_pkg_name, plat_os, plat_cpu):
                raise AccountChatError("closed:Codex platform paket kimliği uyuşmuyor")
            chain.append(plat_json)
            vendor_root = plat_root / "vendor" / triple
            native = vendor_root / "bin" / bin_name
            if not os.path.lexists(native):
                alt_native = vendor_root / "codex" / bin_name
                if os.path.lexists(alt_native):
                    native = alt_native
        else:
            vendor_root = pkg_root / "vendor" / triple
            vendor_native = vendor_root / "bin" / bin_name
            if os.path.lexists(vendor_native):
                native = vendor_native
            elif os.path.lexists(vendor_root / "codex" / bin_name):
                native = vendor_root / "codex" / bin_name
        if vendor_root is not None:
            vendor_meta = vendor_root / "codex-package.json"
            if os.path.lexists(vendor_meta):
                if (_ancestors_problem(vendor_meta, "Codex ikili paketi", allow_leaf_file=True)
                        or not vendor_meta.is_file() or _is_link(vendor_meta)):
                    raise AccountChatError("closed:Codex ikili paketi doğrulanamadı")
                chain.append(vendor_meta)
        if (native is None or _ancestors_problem(native, "Codex ikilisi", allow_leaf_file=True)
                or not native.is_file() or _is_link(native)):
            raise AccountChatError("closed:Codex platform ikilisi bulunamadı")
        chain.append(native)
        binary = native
    else:
        binary = raw
    try:
        binary_sha = _sha256_file(binary)
        combined = hashlib.sha256()
        seen = set()
        for item in chain:
            key = os.path.normcase(str(item))
            if key in seen:
                continue
            seen.add(key)
            combined.update(key.encode("utf-8") + b"\0" + bytes.fromhex(_sha256_file(item)))
    except OSError as exc:
        raise AccountChatError("closed:Codex ikilisi okunamadı") from exc
    return {"executable": str(binary), "sha256": binary_sha, "chain_sha256": combined.hexdigest()}


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
        self._last = {"installed": False, "chatgpt": False, "checked": None, "reason": "", "login": False,
                      "receipt": ""}

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

    def _call(self, binary_executable: str, args, timeout=CALL_SECONDS):
        from core.codex_runtime import account_profile_flags
        run = self._run
        if run is None:
            from core.cli_installer import owned_run as run
        command = [str(binary_executable), *account_profile_flags(), *args]
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

    def _preflight_locked(self, runtime, *, require_home: bool) -> tuple[str, dict]:
        """Identity-free home, binary, version, MCP and feature checks BEFORE login or turn (P1-1..P1-3)."""
        problem = roots_problem(self.base, self.home, self.rooms, require_home=require_home)
        if problem:
            raise AccountChatError("closed:" + problem)
        target = resolve_codex_target(getattr(runtime, "executable", None))
        if not require_home and not os.path.lexists(self.home):
            self.home.mkdir(parents=True, exist_ok=True)
            problem = roots_problem(self.base, self.home, self.rooms, require_home=True)
            if problem:
                raise AccountChatError("closed:" + problem)
        binary = target["executable"]
        code, out, _err = self._call(binary, ["--version"])
        version = out.strip()
        if code != 0 or version not in SUPPORTED_CLI:
            raise AccountChatError("closed:desteklenmeyen Codex sürümü")
        receipt = (f"{os.path.normcase(binary)}|{target['sha256']}|{target['chain_sha256']}|"
                   f"{version}|{PROFILE_VERSION}")
        code, out, _err = self._call(binary, ["mcp", "list", "--json"])
        try:
            servers = json.loads(out)
        except ValueError:
            servers = None
        if code != 0 or servers != []:
            raise AccountChatError("closed:Codex evinde araç sunucusu var ya da liste okunamadı")
        code, out, _err = self._call(binary, ["features", "list"])
        feat_err = features_problem(out if code == 0 else "")
        if feat_err:
            raise AccountChatError("closed:" + feat_err)
        problem = home_problem(self.home)
        if problem:
            raise AccountChatError("closed:" + problem)
        return receipt, target

    def _gate_locked(self, runtime) -> tuple[dict, dict | None]:
        """The full opening gate, fresh (D2-3, P1-1..P1-3). Never starts a model call."""
        state = {"installed": False, "chatgpt": False, "checked": time.time(), "reason": "", "receipt": ""}
        if runtime is None or not getattr(runtime, "executable", None):
            state["reason"] = "Codex kurulu değil"
            return state, None
        state["installed"] = True
        try:
            receipt, target = self._preflight_locked(runtime, require_home=True)
            code, out, err = self._call(target["executable"], ["login", "status"])
            lines = [line.strip() for line in (out + "\n" + err).splitlines() if line.strip()
                     and not line.strip().startswith("WARNING:")]
            if code != 0 or lines != [SIGNED_IN]:
                raise AccountChatError("closed:ChatGPT ile giriş yapılmamış")
            problem = home_problem(self.home)  # the listings may write too: read it again
            if problem:
                raise AccountChatError("closed:" + problem)
            state.update(chatgpt=True, receipt=receipt)
            return state, target
        except AccountChatError as exc:
            state["reason"] = str(exc).removeprefix("closed:")
        except Exception:
            state["reason"] = "Codex denetimi tamamlanamadı"
        return state, None

    def check(self) -> dict:
        """The user's explicit "Kontrol et ve bağla"."""
        runtime = self._runtime()
        self._find_late_install(runtime)
        if not self._lock.acquire(blocking=False):
            return self.last()
        try:
            state, _target = self._gate_locked(runtime)
            self._remember(**state)
        finally:
            self._lock.release()
        return state

    # ── the channel's own sign-in ────────────────────────────────────────────────
    def login(self) -> dict:
        """The user's click: `codex login` (ChatGPT, browser) in the channel's home.

        Fides P1-1: validates the channel's home, ancestors, native binary, CLI version, MCP list and
        feature cut BEFORE starting `codex login`. Never runs alongside a turn; never uses an API key.
        """
        runtime = self._runtime()
        self._find_late_install(runtime)
        if runtime is None or not getattr(runtime, "executable", None):
            raise AccountChatError("closed:Codex kurulu değil")
        if not self._lock.acquire(blocking=False):
            raise AccountChatError("busy")
        try:
            self._settle_locked(runtime)
            _receipt, target = self._preflight_locked(runtime, require_home=False)
        except BaseException as exc:
            if isinstance(exc, AccountChatError) and str(exc).startswith("closed:"):
                self._remember(installed=True, chatgpt=False, checked=time.time(),
                               reason=str(exc).removeprefix("closed:"), receipt="")
            self._lock.release()
            raise
        binary = target["executable"]
        with self._state_lock:
            self._login_running = True

        def work():
            try:
                self._call(binary, ["login"], timeout=LOGIN_SECONDS)
            except Exception:
                pass
            finally:
                with self._state_lock:
                    self._login_running = False
                try:
                    state, _ = self._gate_locked(runtime)
                    self._remember(**state)
                finally:
                    self._lock.release()
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

    def ask(self, prompt: str, cancel: threading.Event, gate, *, approved_receipt: str = "") -> str:
        """``gate()`` raises when Stop, the consent for this call's role or access is gone; it runs
        before the fresh opening gate and again right before the start."""
        runtime = self._runtime()
        if not self._lock.acquire(blocking=False):
            raise AccountChatError("busy")
        try:
            self._settle_locked(runtime)
            gate()
            state, target = self._gate_locked(runtime)
            if state["chatgpt"] and (not approved_receipt or state.get("receipt") != approved_receipt):
                # Fides P1-3: a binary changed since connect() cannot run on the old approval receipt.
                state = {**state, "chatgpt": False, "receipt": "",
                         "reason": "Codex yürütücüsü değişti; yeniden kontrol et ve bağla"}
                target = None
            self._remember(**state)
            if not state["chatgpt"] or target is None:
                raise AccountChatError("account")
            gate()
            if _ancestors_problem(self.rooms, "oda klasörü"):
                raise AccountChatError("account")
            self.rooms.mkdir(parents=True, exist_ok=True)
            if _is_link(self.rooms):
                raise AccountChatError("account")
            room = Path(tempfile.mkdtemp(prefix="turn-", dir=self.rooms))
            run_id = uuid.uuid4().hex
            self._pending = {"run_id": run_id, "room": room}
            try:
                runtime.start(prompt, str(room), sandbox="read-only", approval="never", tool_guard=True,
                              web=False, should_abort=cancel.is_set, account_chat=True, codex_home=str(self.home),
                              account_executable=target["executable"], account_executable_sha256=target["sha256"],
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
