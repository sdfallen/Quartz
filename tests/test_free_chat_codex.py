"""The "ChatGPT hesabın (Codex)" channel of Ücretsiz sohbet (27-28 Nov 2026; Fides D2 + impl2 fixes).

Fake CLI, fake runtime and fake processes only: no Codex runs, no account is read or changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import codex_runtime as cr
from core import free_chat as fc
from core.codex_runtime import (ACCOUNT_FEATURES_ALLOWED_ON, ACCOUNT_FEATURES_OFF, ACCOUNT_REMOVED_BUILTIN_ON,
                                CodexRuntime, account_only_environment, account_profile_flags)
from core.free_chat_codex import (AccountChatError, CodexAccountChannel, SIGNED_IN, classify_record,
                                  features_problem, home_problem, parse_features, resolve_codex_target)


def xor(data: bytes, unprotect: bool = False) -> bytes:
    return bytes(b ^ 0x5A for b in data)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def feature_table(overrides=None, stages=None, omit=()):
    rows = {name: ("stable", False) for name in ACCOUNT_FEATURES_OFF}
    rows.update({name: ("stable", True) for name in ACCOUNT_FEATURES_ALLOWED_ON})
    rows.update({name: ("removed", True) for name in ACCOUNT_REMOVED_BUILTIN_ON})
    for name, on in (overrides or {}).items():
        stage = (stages or {}).get(name, rows.get(name, ("stable", False))[0])
        rows[name] = (stage, on)
    for name, stage in (stages or {}).items():
        if name in rows:
            rows[name] = (stage, rows[name][1])
    for name in omit:
        rows.pop(name, None)
    return "\n".join(f"{name:40} {stage:18} {'true' if on else 'false'}"
                     for name, (stage, on) in sorted(rows.items()))


class FakeCli:
    """Answers the commands the channel runs, by their arguments after the profile flags."""

    def __init__(self, home: Path):
        self.home = home
        self.version = "codex-cli 0.163.0"
        self.mcp = "[]"
        self.features = feature_table()
        self.status = SIGNED_IN
        self.calls = []
        self.login_gate = None

    def __call__(self, command, **kwargs):
        args = list(command[1:])
        self.calls.append({"exe": command[0], "args": args, "env": dict(kwargs["env"]),
                           "timeout": kwargs.get("timeout")})
        rest = args[len(account_profile_flags()):]
        out = ""
        if rest == ["--version"]:
            out = self.version
        elif rest == ["mcp", "list", "--json"]:
            out = self.mcp
        elif rest == ["features", "list"]:
            out = self.features
        elif rest == ["login", "status"]:
            out = self.status
        elif rest == ["login"]:
            if self.login_gate:
                self.login_gate.wait(5)
            (self.home / "auth.json").write_text("{}", encoding="utf-8")
            self.status = SIGNED_IN
        return subprocess.CompletedProcess(command, 0, out, "")


class FakeRuntime:
    def __init__(self, exe: Path):
        self.executable = str(exe)
        self.starts, self.cancels = [], []
        self.records = {}
        self.finish_after = 0
        self.answer = {"status": "completed", "result": "Merhaba, ben Nova.", "errors": [], "error_events": []}
        self.exit_confirmed = True
        self.confirm_on_cancel = True
        self.start_error = None
        self.on_start = None
        self.gets = 0

    def _command(self, args):
        return [self.executable, *args]

    def start(self, prompt, project_path, **kwargs):
        self.starts.append({"prompt": prompt, "room": project_path, **kwargs})
        assert Path(project_path).is_dir() and not any(Path(project_path).iterdir())
        if self.start_error:
            record, error = self.start_error
            if record is not None:
                self.records[kwargs["run_id"]] = record
            raise error
        self.records[kwargs["run_id"]] = {"status": "running"}
        if self.on_start:
            self.on_start()
        return {"id": kwargs["run_id"]}

    def get(self, run_id):
        if run_id not in self.records:
            raise KeyError(run_id)
        self.gets += 1
        record = self.records[run_id]
        if record.get("status") == "running" and self.gets > self.finish_after:
            record = self.records[run_id] = {**self.answer, "process_exit_confirmed": self.exit_confirmed,
                                             "cleanup_pending": not self.exit_confirmed}
        return dict(record)

    def cancel(self, run_id, timeout=5):
        self.cancels.append(run_id)
        record = self.records.get(run_id, {})
        record.update(status="cancelled" if record.get("status") == "running" else record.get("status"))
        if self.confirm_on_cancel:
            record.update(process_exit_confirmed=True, cleanup_pending=False)
        self.records[run_id] = record
        return dict(record)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ProfileTests(unittest.TestCase):
    def test_account_environment_drops_keys_and_uses_only_the_channels_home(self):
        env = {"OPENAI_API_KEY": "sk", "codex_api_key": "x", "OPENAI_BASE_URL": "u", "CODEX_HOME": "ortak",
               "PATH": "p"}
        self.assertEqual(account_only_environment(env, "C:/kanal"), {"CODEX_HOME": "C:/kanal", "PATH": "p"})
        self.assertEqual(env["CODEX_HOME"], "ortak")

    def test_profile_flags_carry_the_policy_and_cut_every_listed_feature(self):
        flags = account_profile_flags()
        for value in ('forced_login_method="chatgpt"', 'cli_auth_credentials_store="file"', "project_doc_max_bytes=0",
                      'web_search="disabled"', 'history.persistence="none"'):
            self.assertIn(value, flags)
        for name in ("shell_tool", "hooks", "plugins", "apps", "computer_use", "secret_auth_storage"):
            self.assertIn(f"features.{name}=false", flags)
        self.assertFalse(set(ACCOUNT_FEATURES_OFF) & ACCOUNT_FEATURES_ALLOWED_ON)

    def runtime(self, exe="C:/fake/codex.exe"):
        rt = CodexRuntime.__new__(CodexRuntime)
        rt.executable, rt._init_error = str(exe), ""
        rt.lock = rt._lock = threading.RLock()
        rt._runs, rt._processes, rt._writers = {}, {}, {}
        return rt

    def test_the_account_profile_is_one_fixed_shape_in_its_own_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "codex.exe"
            exe.write_bytes(b"MZ-pinned")
            sha = sha256_bytes(b"MZ-pinned")
            rt = self.runtime(exe)
            fixed = dict(sandbox="read-only", approval="never", tool_guard=True, account_chat=True,
                         codex_home="C:/k", account_executable=str(exe), account_executable_sha256=sha)
            for change in ({"tool_guard": False}, {"sandbox": "workspace-write"}, {"approval": "on-request"},
                           {"web": True}, {"desktop_connection": object()}, {"project_read": True},
                           {"resume_thread_id": "t"}, {"model": "gpt-x"}, {"effort": "high"}, {"codex_home": None},
                           {"account_executable": None}, {"account_executable_sha256": "00" * 32},
                           {"run_id": "kisa"}):
                with self.subTest(change=change):
                    with self.assertRaises((ValueError, PermissionError, RuntimeError)):
                        rt.start("selam", tmp, **{**fixed, **change})

    def start_capturing(self, rt, room, home, popen, exe: Path, sha: str):
        seen = {}

        def verified(flags, cwd, allowed, should_abort=None, env=None, executable=None):
            seen.update(preflight_flags=list(flags), preflight_env=dict(env), allowed=set(allowed),
                        preflight_exe=executable)
            return list(flags)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "CODEX_HOME": "C:/ortak-fides"}), \
                patch.object(rt, "_verified_mcp_flags", verified), \
                patch.object(cr.subprocess, "Popen", lambda command, **kw: popen(seen, command, kw)):
            run_id = "ab" * 16
            try:
                rt.start("selam", room, sandbox="read-only", approval="never", tool_guard=True, account_chat=True,
                         codex_home=home, account_executable=str(exe), account_executable_sha256=sha, run_id=run_id)
            except Exception as exc:
                seen["error"] = exc
        seen["run_id"] = run_id
        return seen

    def test_preflight_and_exec_share_the_home_the_keyless_env_the_policy_and_pinned_binary(self):
        class Stop(Exception):
            pass

        def popen(seen, command, kw):
            seen["command"], seen["env"] = list(command), dict(kw["env"])
            raise Stop()
        with tempfile.TemporaryDirectory() as room:
            exe = Path(room) / "codex.exe"
            exe.write_bytes(b"MZ-real")
            sha = sha256_bytes(b"MZ-real")
            work = Path(room) / "turn"
            work.mkdir()
            seen = self.start_capturing(self.runtime("C:/other/codex.cmd"), str(work), "C:/kanal-evi", popen, exe, sha)
        for env in (seen["preflight_env"], seen["env"]):
            self.assertEqual(env["CODEX_HOME"], "C:/kanal-evi")
            self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(seen["allowed"], set())
        self.assertEqual(seen["preflight_exe"], str(exe))
        cmd = seen["command"]
        self.assertEqual(cmd[0], str(exe))
        for flag in account_profile_flags():
            self.assertIn(flag, seen["preflight_flags"])
        self.assertIn('forced_login_method="chatgpt"', cmd)
        self.assertIn("features.hooks=false", cmd)
        after = cmd[cmd.index("exec") + 1:]
        self.assertIn("--ephemeral", after)
        self.assertIn("--ignore-user-config", after)
        self.assertNotIn("-m", cmd)

    def test_d24_no_process_is_a_verified_never_started(self):
        def popen(seen, command, kw):
            raise OSError("başlatılamadı")
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "codex.exe"
            exe.write_bytes(b"MZ")
            room = Path(tmp) / "room"
            room.mkdir()
            rt = self.runtime(exe)
            seen = self.start_capturing(rt, str(room), "C:/k", popen, exe, sha256_bytes(b"MZ"))
        record = rt.get(seen["run_id"])
        self.assertEqual((record["process_started"], record["process_exit_confirmed"]), (False, True))

    def test_d24_a_failure_after_the_process_exists_keeps_it_owned(self):
        process = SimpleNamespace(pid=4242, poll=lambda: None, stdin=None)

        def popen(seen, command, kw):
            return process
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "codex.exe"
            exe.write_bytes(b"MZ")
            room = Path(tmp) / "room"
            room.mkdir()
            rt = self.runtime(exe)
            with patch.object(cr, "bind_kill_on_close_job", side_effect=OSError("job")), \
                    patch.object(cr, "stop_process_tree", lambda *a, **k: False), \
                    patch.object(cr, "owned_cleanup_pending", lambda *a, **k: True):
                seen = self.start_capturing(rt, str(room), "C:/k", popen, exe, sha256_bytes(b"MZ"))
        record = rt.get(seen["run_id"])
        self.assertTrue(record["process_started"])
        self.assertEqual((record["process_exit_confirmed"], record["cleanup_pending"]), (False, True))
        self.assertIs(rt._processes[seen["run_id"]], process)  # cancel() can retry its cleanup

    def test_p2_4_partial_writer_start_retains_writer_lock_until_cancel_confirms_cleanup(self):
        """Fides P2 (20261128): unconfirmed partial writer keeps _writers locked until cancel() cleans it."""
        alive = [True]
        process = SimpleNamespace(pid=5151, poll=lambda: None if alive[0] else 1, stdin=None)
        with tempfile.TemporaryDirectory() as project:
            exe = Path(project) / "codex.exe"
            exe.write_bytes(b"MZ")
            rt = self.runtime(exe)
            run1 = "11" * 16
            with patch.object(cr.subprocess, "Popen", lambda *a, **k: process), \
                    patch.object(cr, "bind_kill_on_close_job", side_effect=OSError("job failed")), \
                    patch.object(cr, "stop_process_tree", lambda *a, **k: False), \
                    patch.object(cr, "owned_cleanup_pending", lambda *a, **k: alive[0]):
                with self.assertRaises(OSError):
                    rt.start("yaz", project, sandbox="workspace-write", approval="never", run_id=run1)
                self.assertIn(os.path.normcase(str(Path(project).resolve())), rt._writers)
                # Second writer must be blocked while first writer's tree is unconfirmed!
                with self.assertRaises(RuntimeError) as ctx:
                    rt.start("ikinci yaz", project, sandbox="workspace-write", approval="never", run_id="22" * 16)
                self.assertIn("already has an active write-capable agent", str(ctx.exception))
                # Retry cleanup while still alive keeps the lock.
                rt.cancel(run1)
                self.assertTrue(rt.get(run1)["cleanup_pending"])
                self.assertIn(os.path.normcase(str(Path(project).resolve())), rt._writers)
                # Once process tree exits, cancel() confirms cleanup and releases the writer lock.
                alive[0] = False
                rt.cancel(run1)
                self.assertTrue(rt.get(run1)["process_exit_confirmed"])
                self.assertFalse(rt.get(run1)["cleanup_pending"])
                self.assertEqual(rt._writers, {})


class GateFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "free_chat"
        self.base.mkdir()
        exe = Path(self.tmp.name) / "codex.exe"
        exe.write_bytes(b"MZ codex")
        self.exe = exe
        self.runtime = FakeRuntime(exe)
        self.cli = FakeCli(self.base / "codex-home")
        self.clock = Clock()
        self.account = CodexAccountChannel(lambda: self.runtime, self.base, clock=self.clock, sleep=self.clock.sleep,
                                           run=self.cli, environment=lambda: {"OPENAI_API_KEY": "sk", "PATH": "p",
                                                                              "CODEX_HOME": "C:/ortak"})
        (self.base / "codex-home").mkdir()
        (self.base / "codex-home" / "auth.json").write_text("{}", encoding="utf-8")


class GateTests(GateFixture):
    def closed_because(self, text):
        state = self.account.check()
        self.assertFalse(state["chatgpt"])
        self.assertIn(text, state["reason"])
        return state

    def test_the_happy_gate_runs_every_call_in_the_channels_home_without_keys(self):
        state = self.account.check()
        self.assertTrue(state["chatgpt"], state)
        names = [c["args"][len(account_profile_flags()):] for c in self.cli.calls]
        self.assertEqual(names, [["--version"], ["mcp", "list", "--json"], ["features", "list"], ["login", "status"]])
        for call in self.cli.calls:
            self.assertEqual(call["env"]["CODEX_HOME"], str(self.base / "codex-home"))
            self.assertNotIn("OPENAI_API_KEY", call["env"])
            self.assertEqual(call["args"][:len(account_profile_flags())], account_profile_flags())

    def test_each_failed_condition_keeps_it_closed(self):
        cases = [
            (lambda: setattr(self.cli, "version", "codex-cli 0.164.0"), "sürüm"),
            (lambda: setattr(self.cli, "mcp", '[{"name": "x"}]'), "araç sunucusu"),
            (lambda: setattr(self.cli, "mcp", "bozuk"), "araç sunucusu"),
            (lambda: setattr(self.cli, "features", feature_table({"hooks": True})), "hooks"),
            (lambda: setattr(self.cli, "features", feature_table({"unified_exec": True})), "unified_exec"),
            (lambda: setattr(self.cli, "features", feature_table({"yeni_arac": True})), "yeni_arac"),
            (lambda: setattr(self.cli, "features", feature_table(omit=("shell_tool",))), "shell_tool"),
            (lambda: setattr(self.cli, "features", feature_table(omit=("multi_agent",))), "multi_agent"),
            (lambda: setattr(self.cli, "status", "Logged in using an API key - sk-***"), "giriş"),
            (lambda: setattr(self.cli, "status", SIGNED_IN + "\nbaşka bir satır"), "giriş"),
            (lambda: setattr(self.cli, "status", "Logged in using ChatGPT (ayrıca)"), "giriş"),
        ]
        for change, reason in cases:
            with self.subTest(reason=reason):
                self.setUp()
                change()
                self.closed_because(reason)

    def test_p1_2_contradictory_duplicate_malformed_features_and_unreadable_subdirs_fail_closed(self):
        """Fides P1-2 (20261128): duplicate/contradictory rows, invalid rows, non-removed built-ins and scan errors."""
        # Contradictory duplicate: hooks true then hooks false (passed in 4e7a6ee!).
        dup = "hooks                                    stable             true\n" + feature_table()
        self.cli.features = dup
        self.closed_because("tekrarlı ya da çelişkili özellik: hooks")
        # Malformed line in features output.
        self.setUp()
        self.cli.features = feature_table() + "\nbozuk satir deger yok"
        self.closed_because("geçersiz satır")
        # A removed-only built-in reported as stable true is refused.
        self.setUp()
        self.cli.features = feature_table(stages={"collaboration_modes": "stable"})
        self.closed_because("collaboration_modes")
        # Unreadable subdirectory inside codex-home fails closed (os.walk swallowed this in 4e7a6ee!).
        self.setUp()
        sub = self.base / "codex-home" / "log"
        sub.mkdir()
        real_scandir = os.scandir

        def failing_scandir(path):
            if Path(path) == sub:
                raise PermissionError("erişim engellendi")
            return real_scandir(path)
        with patch("core.free_chat_codex.os.scandir", side_effect=failing_scandir):
            self.assertIn("okunamayan klasör: log", home_problem(self.base / "codex-home"))
            state = self.account.check()
            self.assertFalse(state["chatgpt"])
            self.assertEqual(self.cli.calls, [])  # home checked before any CLI invocation!

    def test_the_home_holds_nothing_unexpected_and_runs_before_any_cli_call(self):
        for name, make in (("config.toml", "file"), ("AGENTS.md", "file"), ("skills", "dir"), ("hooks.json", "file"),
                           ("plugins", "dir"), ("tmp/arg0-windows/a/b/c", "file")):
            with self.subTest(name=name):
                self.setUp()
                target = self.base / "codex-home" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.mkdir() if make == "dir" else target.write_text("x", encoding="utf-8")
                self.closed_because("beklenmeyen")
                self.assertEqual(self.cli.calls, [])  # P1-1: zero CLI calls on dirty home!
        self.setUp()
        home = self.base / "codex-home"
        (home / "tmp" / "arg0-windows" / "alias").mkdir(parents=True)
        (home / "tmp" / "arg0-windows" / "alias" / "apply_patch.exe").write_bytes(b"MZ")
        (home / "log").mkdir()
        (home / "log" / "codex-tui.log").write_text("", encoding="utf-8")
        self.assertEqual(home_problem(home), "")

    def test_the_receipt_is_bound_to_the_launchers_bytes(self):
        first = self.account.check()["receipt"]
        self.exe.write_bytes(b"MZ codex changed")
        self.assertNotEqual(self.account.check()["receipt"], first)

    def test_features_parsing(self):
        self.assertEqual(features_problem(feature_table()), "")
        self.assertEqual(features_problem(parse_features(feature_table())), "")
        self.assertIn("okunamadı", features_problem(parse_features("")))
        self.assertEqual(classify_record({"error_events": [{"message": "You've hit your usage limit"}]}), "quota")
        self.assertEqual(classify_record({"errors": ["401 Unauthorized"]}), "key")


class ChannelBase(GateFixture):
    def setUp(self):
        super().setUp()
        opened = patch.object(fc, "ACCOUNT_CHANNEL_OPEN", True)
        opened.start()
        self.addCleanup(opened.stop)
        self.free = fc.FreeChat(fc.SecretStore(self.base, protect=xor), fc.Settings(self.base),
                                client=lambda *a: self.fail("no HTTP for the account channel"), account=self.account)

    def ask(self, cancel=None):
        return self.free.reply("chatgpt", [{"role": "system", "content": "Sen Nova'sın."},
                                           {"role": "user", "content": "selam"}], cancel or threading.Event())


class ClosedTests(ChannelBase):
    def test_the_channel_is_closed_by_default(self):
        with patch.object(fc, "ACCOUNT_CHANNEL_OPEN", False):
            self.account.check()
            self.free.settings.update("chatgpt", send=True, backup=True, receipt="r")
            self.assertNotIn("chatgpt", [c["id"] for c in self.free.status()["channels"]])
            self.assertFalse(self.free.allowed("chatgpt", as_backup=False))
            for call in (lambda: self.free.connect("chatgpt", "", send=True), self.free.account_login):
                with self.assertRaises(fc.FreeChatError):
                    call()

    def test_status_is_passive(self):
        self.free.status()
        self.assertEqual(self.cli.calls, [])

    def test_p1_1_login_refuses_dirty_home_bad_rooms_and_unsupported_cli_with_zero_login_calls(self):
        """Fides P1-1 (20261128): login() validates home, ancestors and profile BEFORE starting login."""
        # Case 1: dirty home (config.toml present) -> zero CLI calls at all.
        (self.base / "codex-home" / "config.toml").write_text('model = "x"\n', encoding="utf-8")
        with self.assertRaises(fc.FreeChatError) as ctx:
            self.free.account_login()
        self.assertIn("config.toml", str(ctx.exception))
        self.assertEqual(self.cli.calls, [])
        # Case 2: rooms path is a regular file instead of a directory -> zero CLI calls.
        (self.base / "codex-home" / "config.toml").unlink()
        (self.base / "codex-rooms").write_text("not-a-dir", encoding="utf-8")
        with self.assertRaises(fc.FreeChatError):
            self.free.account_login()
        self.assertEqual(self.cli.calls, [])
        (self.base / "codex-rooms").unlink()
        # Case 3: unsupported CLI version -> version checked, zero ["login"] calls!
        self.cli.version = "codex-cli 0.171.0-alpha.13.2"
        with self.assertRaises(fc.FreeChatError) as ctx:
            self.free.account_login()
        self.assertIn("sürüm", str(ctx.exception))
        login_calls = [c for c in self.cli.calls if c["args"][-1:] == ["login"]]
        self.assertEqual(login_calls, [])

    def test_p1_3_npm_wrapper_resolves_native_binary_and_changed_binary_with_same_version_is_refused(self):
        """Fides P1-3 (20261128): npm .cmd -> bin/codex.js -> platform codex.exe; swapped binary invalidates receipt."""
        npm_prefix = Path(self.tmp.name) / "npm"
        pkg = npm_prefix / "node_modules" / "@openai" / "codex"
        (pkg / "bin").mkdir(parents=True)
        cmd_wrapper = npm_prefix / "codex.cmd"
        cmd_wrapper.write_text('@ECHO off\r\n"%~dp0\\node.exe" "%~dp0\\node_modules\\@openai\\codex\\bin\\codex.js" %*\r\n',
                               encoding="utf-8")
        (pkg / "package.json").write_text(json.dumps({"name": "@openai/codex", "bin": {"codex": "bin/codex.js"}}),
                                          encoding="utf-8")
        js_entry = pkg / "bin" / "codex.js"
        js_entry.write_text("// launcher\n", encoding="utf-8")
        plat_pkg = pkg / "node_modules" / "@openai" / "codex-win32-x64"
        native_dir = plat_pkg / "vendor" / "x86_64-pc-windows-msvc" / "codex"
        native_dir.mkdir(parents=True)
        # Real @openai/codex@0.163.0 uses npm package aliasing ("name": "@openai/codex", "version": "0.163.0-win32-x64").
        (plat_pkg / "package.json").write_text(json.dumps({
            "name": "@openai/codex",
            "version": "0.163.0-win32-x64",
            "os": ["win32"],
            "cpu": ["x64"],
        }), encoding="utf-8")
        (plat_pkg / "vendor" / "x86_64-pc-windows-msvc" / "codex-package.json").write_text(
            json.dumps({"version": "0.163.0"}), encoding="utf-8"
        )
        native_exe = native_dir / "codex.exe"
        native_exe.write_bytes(b"MZ-native-0.163.0-original")

        # Unrelated .cmd wrapper next to node_modules must fail closed.
        rogue_cmd = npm_prefix / "other.cmd"
        rogue_cmd.write_text("@echo off\r\necho hijacked\r\n", encoding="utf-8")

        with patch("core.free_chat_codex.platform.system", return_value="Windows"), \
                patch("core.free_chat_codex.platform.machine", return_value="AMD64"):
            with self.assertRaises(AccountChatError):
                resolve_codex_target(rogue_cmd)

            target = resolve_codex_target(cmd_wrapper)
            self.assertEqual(Path(target["executable"]), native_exe)
            self.assertEqual(target["sha256"], sha256_bytes(b"MZ-native-0.163.0-original"))

            self.runtime.executable = str(cmd_wrapper)
            status = self.free.connect("chatgpt", "", send=True)
            ch = next(c for c in status["channels"] if c["id"] == "chatgpt")
            self.assertTrue(ch["connected"])
            # Every preflight call ran the resolved native binary directly, not codex.cmd!
            self.assertTrue(all(Path(c["exe"]) == native_exe for c in self.cli.calls))

            ok = self.ask()
            self.assertEqual(ok["outcome"], "ok")
            self.assertEqual(Path(self.runtime.starts[0]["account_executable"]), native_exe)
            self.assertEqual(self.runtime.starts[0]["account_executable_sha256"],
                             sha256_bytes(b"MZ-native-0.163.0-original"))

            # Now mutate ONLY the underlying native platform binary while keeping codex.cmd, codex.js
            # AND the reported CLI version ("codex-cli 0.163.0") unchanged!
            self.runtime.starts.clear()
            native_exe.write_bytes(b"MZ-native-0.163.0-tampered")
            refused = self.ask()
            self.assertNotEqual(refused["outcome"], "ok")
            self.assertEqual(refused["attempts"][0]["result"], "account")
            self.assertEqual(self.runtime.starts, [])  # zero starts on stale compatibility receipt!
            self.assertFalse(self.free.allowed("chatgpt", as_backup=False))

            # Missing platform binary fails closed too.
            native_exe.unlink()
            with self.assertRaises(AccountChatError):
                resolve_codex_target(cmd_wrapper)

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_p1_3_junction_inside_npm_node_modules_or_real_npm_install_is_verified(self):
        import subprocess
        # 1. If a real @openai/codex npm wrapper exists on this machine, verify resolve_codex_target resolves its .exe.
        real_cmd = Path(os.environ.get("APPDATA") or "") / "npm" / "codex.cmd"
        if real_cmd.is_file() and not real_cmd.is_symlink():
            real_target = resolve_codex_target(real_cmd)
            self.assertTrue(real_target["executable"].lower().endswith("codex.exe"))
            self.assertEqual(len(real_target["sha256"]), 64)

        # 2. A directory junction inside node_modules/@openai/codex must fail closed before .resolve().
        prefix = Path(self.tmp.name) / "junc-npm"
        real_target_dir = Path(self.tmp.name) / "real-pkg"
        (real_target_dir / "bin").mkdir(parents=True)
        (real_target_dir / "package.json").write_text(
            json.dumps({"name": "@openai/codex", "bin": {"codex": "bin/codex.js"}}), encoding="utf-8"
        )
        (real_target_dir / "bin" / "codex.js").write_text("// js\n", encoding="utf-8")
        (prefix / "node_modules" / "@openai").mkdir(parents=True)
        cmd_file = prefix / "codex.cmd"
        cmd_file.write_text('@ECHO off\r\n"%~dp0\\node_modules\\@openai\\codex\\bin\\codex.js" %*\r\n', encoding="utf-8")
        junc_path = prefix / "node_modules" / "@openai" / "codex"
        mk = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junc_path), str(real_target_dir)],
                            capture_output=True, text=True)
        if mk.returncode == 0:
            self.addCleanup(lambda: subprocess.run(["cmd.exe", "/c", "rmdir", str(junc_path)], capture_output=True))
            with self.assertRaises(AccountChatError):
                resolve_codex_target(cmd_file)


class TurnTests(ChannelBase):
    def setUp(self):
        super().setUp()
        self.free.connect("chatgpt", "", send=True)
        self.cli.calls.clear()

    def test_an_answer_runs_in_the_channels_home_with_a_chosen_run_id_and_its_room_goes(self):
        result = self.ask()
        self.assertEqual((result["outcome"], result["text"]), ("ok", "Merhaba, ben Nova."))
        start = self.runtime.starts[0]
        self.assertEqual(start["codex_home"], str(self.base / "codex-home"))
        self.assertEqual(len(start["run_id"]), 32)
        self.assertTrue(start["account_chat"])
        self.assertEqual(Path(start["account_executable"]), self.exe)
        self.assertEqual(Path(start["room"]).parent, self.base / "codex-rooms")
        self.assertFalse(Path(start["room"]).exists())
        self.assertIn("<UNTRUSTED_HISTORY>", start["prompt"])
        self.assertEqual(len([c for c in self.cli.calls if c["args"][-2:] == ["login", "status"]]), 1)  # fresh

    def test_cg3_an_unconfirmed_exit_publishes_nothing_and_blocks_the_next_turn(self):
        self.runtime.exit_confirmed = False
        self.runtime.confirm_on_cancel = False
        first = self.ask()
        self.assertNotEqual(first["outcome"], "ok")
        self.assertEqual(first["attempts"][0]["result"], "busy")
        room = Path(self.runtime.starts[0]["room"])
        self.assertTrue(room.exists())
        second = self.ask()
        self.assertEqual(second["attempts"][0]["result"], "busy")
        self.assertEqual(len(self.runtime.starts), 1)  # nothing new while the old one is pending
        with self.assertRaises(fc.FreeChatError):
            self.free.account_login()  # sign-in is blocked too
        self.runtime.confirm_on_cancel = True  # the cleanup retry now confirms the exit
        self.runtime.exit_confirmed = True
        self.assertEqual(self.ask()["outcome"], "ok")
        self.assertFalse(room.exists())

    def test_cg3_a_timed_out_turn_stays_pending_until_its_exit_is_confirmed(self):
        self.runtime.finish_after = 10 ** 6
        self.runtime.confirm_on_cancel = False
        self.assertEqual(self.ask()["attempts"][0]["result"], "unreachable")
        self.assertEqual(self.ask()["attempts"][0]["result"], "busy")
        self.assertEqual(len(self.runtime.starts), 1)

    def test_cg4_a_start_failure_without_a_record_releases_the_room(self):
        self.runtime.start_error = (None, RuntimeError("başlamadı"))
        self.assertEqual(self.ask()["attempts"][0]["result"], "other")
        self.assertFalse(Path(self.runtime.starts[0]["room"]).exists())
        self.runtime.start_error = None
        self.assertEqual(self.ask()["outcome"], "ok")

    def test_cg4_a_partial_start_keeps_the_room_and_blocks(self):
        self.runtime.confirm_on_cancel = False
        self.runtime.start_error = ({"status": "failed", "process_started": True, "process_exit_confirmed": False,
                                     "cleanup_pending": True}, OSError("stdin"))
        self.ask()
        self.assertTrue(Path(self.runtime.starts[0]["room"]).exists())
        self.runtime.start_error = None
        self.assertEqual(self.ask()["attempts"][0]["result"], "busy")
        self.assertEqual(len(self.runtime.starts), 1)

    def test_cg4_a_verified_never_started_record_releases_the_room(self):
        self.runtime.start_error = ({"status": "failed", "process_started": False, "process_exit_confirmed": True},
                                    OSError("popen"))
        self.ask()
        self.assertFalse(Path(self.runtime.starts[0]["room"]).exists())

    def test_a_sign_in_and_a_turn_never_run_together(self):
        gate = threading.Event()
        self.cli.login_gate = gate
        self.free.account_login()
        self.assertTrue(self.account.last()["login"])
        self.assertEqual(self.ask()["attempts"][0]["result"], "busy")
        self.assertEqual(self.runtime.starts, [])
        gate.set()
        for _ in range(200):
            if not self.account.last()["login"]:
                break
            threading.Event().wait(0.01)
        login = [c for c in self.cli.calls if c["args"][-1:] == ["login"]][0]
        self.assertEqual(login["env"]["CODEX_HOME"], str(self.base / "codex-home"))
        self.assertIn('forced_login_method="chatgpt"', login["args"])
        self.assertNotIn("OPENAI_API_KEY", login["env"])

    def test_a_closed_gate_sends_nothing(self):
        self.cli.status = "Not logged in"
        self.assertEqual(self.ask()["attempts"][0]["result"], "account")
        self.assertEqual(self.runtime.starts, [])

    def test_a_consent_withdrawn_before_the_start_sends_nothing(self):
        original = self.account._gate_locked

        def gate_then_withdraw(runtime):
            state, target = original(runtime)
            self.free.settings.update("chatgpt", send=False)
            return state, target
        self.account._gate_locked = gate_then_withdraw
        self.assertEqual(self.ask()["attempts"][0]["result"], "not_allowed")
        self.assertEqual(self.runtime.starts, [])

    def test_stop_during_the_run_cancels_it(self):
        cancel = threading.Event()
        self.runtime.finish_after = 1000
        self.runtime.on_start = cancel.set
        self.assertEqual(self.ask(cancel)["outcome"], "cancelled")
        self.assertEqual(len(self.runtime.cancels), 1)

    def test_errors_come_from_the_record_only(self):
        self.runtime.answer = {"status": "failed", "result": "", "errors": [],
                               "error_events": [{"message": "You've hit your usage limit."}]}
        self.assertEqual(self.ask()["attempts"][0]["result"], "quota")
        self.runtime.answer = {"status": "completed", "result": "kota doldu gibi bir yanıt", "errors": [],
                               "error_events": []}
        self.assertEqual(self.ask()["outcome"], "ok")

    def test_disconnect_only_closes_the_consents_and_clears_receipt(self):
        self.free.disconnect("chatgpt")
        self.assertFalse(self.free.settings.read()["channels"]["chatgpt"]["send"])
        self.assertEqual(self.free.settings.read()["channels"]["chatgpt"]["receipt"], "")
        self.assertTrue((self.base / "codex-home" / "auth.json").exists())


class PageTests(unittest.TestCase):
    def test_the_card_has_no_key_field_and_signs_in_through_the_channels_own_action(self):
        from ui.js_free import JAVASCRIPT
        start = JAVASCRIPT.index("ch.kind === 'account'")
        card = JAVASCRIPT[start:JAVASCRIPT.index("} else if (!ch.connected)", start)]
        self.assertNotIn("password", card)
        self.assertIn("ChatGPT hesabımla bağlan", card)
        self.assertIn("freeCall('account_login'", card)
        self.assertNotIn("begin('account'", card)  # never the shared sign-in


if __name__ == "__main__":
    unittest.main()
