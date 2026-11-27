"""The "ChatGPT hesabın (Codex)" channel of Ücretsiz sohbet (27 Nov 2026, Fides design ŞARTLI KABUL).

Fake runtime and fake processes only: no Codex is run, no account is read or changed.
"""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core import free_chat as fc
from core.codex_runtime import CodexRuntime, account_only_environment
from core.free_chat_codex import AccountChatError, CodexAccountChannel, classify_record


def xor(data: bytes) -> bytes:
    return bytes(b ^ 0x5A for b in data)


class FakeRuntime:
    def __init__(self, method="chatgpt", installed=True):
        self.executable = "C:/fake/codex.exe" if installed else None
        self.method, self.installed = method, installed
        self.probes = 0
        self.starts, self.cancels = [], []
        self.record = {"status": "completed", "result": "Merhaba, ben Nova.", "process_exit_confirmed": True,
                       "cleanup_pending": False, "errors": [], "error_events": []}
        self.on_start = None
        self.gets = 0
        self.finish_after = 0

    def probe(self, force=False):
        self.probes += 1
        return {"installed": self.installed, "authenticated": self.method is not None,
                "authentication": self.method or "required"}

    def start(self, prompt, project_path, **kwargs):
        self.starts.append({"prompt": prompt, "room": project_path, **kwargs})
        assert Path(project_path).is_dir() and not any(Path(project_path).iterdir())
        if self.on_start:
            self.on_start()
        return {"id": f"r{len(self.starts)}"}

    def get(self, run_id):
        self.gets += 1
        if self.gets <= self.finish_after:
            return {"status": "running"}
        return dict(self.record)

    def cancel(self, run_id, timeout=5):
        self.cancels.append(run_id)
        return {"status": "cancelling"}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = FakeRuntime()
        self.clock = Clock()
        self.rooms = self.root / "codex-rooms"
        self.account = CodexAccountChannel(lambda: self.runtime, self.rooms, clock=self.clock, sleep=self.clock.sleep)
        self.free = fc.FreeChat(fc.SecretStore(self.root, protect=xor), fc.Settings(self.root),
                                client=lambda *a: self.fail("no HTTP for the account channel"), account=self.account)

    def ask(self, cancel=None):
        return self.free.reply("chatgpt", [{"role": "system", "content": "Sen Nova'sın."},
                                           {"role": "user", "content": "selam"}], cancel or threading.Event())


class ProfileTests(unittest.TestCase):
    def test_account_environment_drops_every_api_key_and_endpoint_but_keeps_codex_home(self):
        env = {"OPENAI_API_KEY": "sk", "codex_api_key": "x", "OPENAI_BASE_URL": "u", "CODEX_HOME": "h", "PATH": "p"}
        clean = account_only_environment(env)
        self.assertEqual(clean, {"CODEX_HOME": "h", "PATH": "p"})
        self.assertIn("OPENAI_API_KEY", env)  # the given dict is not changed

    def runtime(self):
        rt = CodexRuntime.__new__(CodexRuntime)
        rt.executable, rt._init_error = "C:/fake/codex.exe", ""
        return rt

    def test_the_account_profile_is_one_fixed_shape(self):
        rt = self.runtime()
        fixed = dict(sandbox="read-only", approval="never", tool_guard=True, account_chat=True)
        for change in ({"tool_guard": False}, {"sandbox": "workspace-write"}, {"approval": "on-request"},
                       {"web": True}, {"desktop_connection": object()}, {"project_read": True},
                       {"resume_thread_id": "t"}, {"model": "gpt-x"}, {"effort": "high"}):
            with self.subTest(change=change):
                with self.assertRaises((ValueError, PermissionError)):
                    rt.start("selam", ".", **{**fixed, **change})

    def test_preflight_and_exec_share_the_key_free_environment_and_exec_is_ephemeral(self):
        import core.codex_runtime as cr
        rt = CodexRuntime("C:/Windows/System32/cmd.exe") if os.name == "nt" else self.runtime()
        rt.executable = "C:/fake/codex.exe"
        seen = {}

        def guarded(cwd, desktop_connection=None, should_abort=None, env=None, web=False):
            seen["preflight_env"] = dict(env)
            return ["-c", "features.shell_tool=false"]

        class Stop(Exception):
            pass

        def popen(command, **kwargs):
            seen["command"], seen["env"] = list(command), dict(kwargs["env"])
            raise Stop()
        with tempfile.TemporaryDirectory() as room, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "CODEX_HOME": "h"}), \
                patch.object(rt, "_guarded_config", guarded), patch.object(rt, "_command", lambda a: list(a)), \
                patch.object(cr.subprocess, "Popen", popen):
            with self.assertRaises(Stop):
                rt.start("selam", room, sandbox="read-only", approval="never", tool_guard=True, account_chat=True)
            self.assertNotIn("OPENAI_API_KEY", seen["preflight_env"])
            self.assertNotIn("OPENAI_API_KEY", seen["env"])
            self.assertEqual(seen["env"].get("CODEX_HOME"), "h")
            cmd = seen["command"]
            after = cmd[cmd.index("exec") + 1:]
            self.assertIn("--ephemeral", after)
            self.assertIn("--ignore-user-config", after)
            self.assertNotIn("-m", cmd)
            self.assertIn("features.shell_tool=false", cmd)  # the verified tool cut, unchanged
            self.assertEqual(cmd[cmd.index("--sandbox") + 1], "read-only")
            # A normal run keeps its old shape.
            seen.clear()
            with self.assertRaises(Stop):
                rt.start("selam", room, sandbox="read-only", approval="never", tool_guard=True)
            self.assertNotIn("--ephemeral", seen["command"])


class StatusAndConnectTests(Base):
    def test_status_is_passive_and_starts_with_no_consent(self):
        status = self.free.status()
        self.assertEqual(self.runtime.probes, 0)
        chatgpt = next(c for c in status["channels"] if c["id"] == "chatgpt")
        self.assertEqual((chatgpt["kind"], chatgpt["connected"], chatgpt["send"], chatgpt["backup"]),
                         ("account", False, False, False))
        self.assertNotIn("ücretsiz", chatgpt["label"].lower())
        self.assertIn("Codex kullanım hakkından", chatgpt["privacy"])

    def test_without_a_codex_runtime_the_channel_is_not_offered(self):
        free = fc.FreeChat(fc.SecretStore(self.root, protect=xor), fc.Settings(self.root))
        self.assertNotIn("chatgpt", [c["id"] for c in free.status()["channels"]])
        self.assertFalse(free.allowed("chatgpt", as_backup=False))

    def test_connect_needs_codex_and_a_chatgpt_sign_in(self):
        self.runtime.installed, self.runtime.executable = False, None
        with self.assertRaises(fc.FreeChatError):
            self.free.connect("chatgpt", "", send=True)
        self.runtime.installed, self.runtime.executable = True, "C:/fake/codex.exe"
        self.runtime.method = "unknown"  # an API-key sign-in: separately billed, never used here
        with self.assertRaises(fc.FreeChatError):
            self.free.connect("chatgpt", "", send=True)
        self.assertFalse(self.free.settings.read()["channels"]["chatgpt"]["send"])
        self.runtime.method = "chatgpt"
        status = self.free.connect("chatgpt", "", send=True)
        chatgpt = next(c for c in status["channels"] if c["id"] == "chatgpt")
        self.assertTrue(chatgpt["connected"] and chatgpt["send"] and chatgpt["signed_in"])
        self.assertEqual(self.runtime.starts, [])  # connecting never sends a message

    def test_codex_installed_while_spes_runs_is_found_on_the_users_check(self):
        self.runtime.installed, self.runtime.executable = True, None
        self.runtime._find_executable = lambda: "C:/late/codex.exe"
        self.assertFalse(self.account.installed())  # passive: nothing looked up
        self.free.connect("chatgpt", "", send=True)
        self.assertEqual(self.runtime.executable, "C:/late/codex.exe")

    def test_disconnect_only_closes_the_consents(self):
        self.free.connect("chatgpt", "", send=True, backup=True)
        self.free.disconnect("chatgpt")
        saved = self.free.settings.read()["channels"]["chatgpt"]
        self.assertEqual((saved["send"], saved["backup"]), (False, False))
        self.assertTrue(self.account.last()["chatgpt"])  # Codex stays signed in (Fides uses it)


class AskTests(Base):
    def setUp(self):
        super().setUp()
        self.free.connect("chatgpt", "", send=True)

    def test_an_answer_runs_the_fixed_profile_in_a_new_owned_room_that_is_removed(self):
        result = self.ask()
        self.assertEqual((result["outcome"], result["text"]), ("ok", "Merhaba, ben Nova."))
        start = self.runtime.starts[0]
        self.assertEqual({k: start[k] for k in ("sandbox", "approval", "tool_guard", "web", "account_chat")},
                         {"sandbox": "read-only", "approval": "never", "tool_guard": True, "web": False,
                          "account_chat": True})
        self.assertEqual(Path(start["room"]).parent, self.rooms)
        self.assertFalse(Path(start["room"]).exists())  # exit confirmed: removed
        self.assertIn("<UNTRUSTED_HISTORY>", start["prompt"])
        self.assertTrue(start["prompt"].rstrip().endswith("selam"))
        self.ask()
        self.assertNotEqual(self.runtime.starts[0]["room"], self.runtime.starts[1]["room"])

    def test_a_room_whose_process_exit_is_not_confirmed_is_kept_not_reused(self):
        self.runtime.record.update(process_exit_confirmed=False, cleanup_pending=True)
        self.ask()
        self.assertTrue(Path(self.runtime.starts[0]["room"]).exists())
        self.ask()
        self.assertNotEqual(self.runtime.starts[0]["room"], self.runtime.starts[1]["room"])

    def test_every_message_checks_the_sign_in_method_again(self):
        self.runtime.method = "unknown"  # switched to an API key after the last check
        result = self.ask()
        self.assertEqual(result["attempts"][0]["result"], "account")
        self.assertEqual(self.runtime.starts, [])
        self.runtime.method = None  # signed out
        self.assertEqual(self.ask()["attempts"][0]["result"], "not_allowed")  # the fresh check closed access

    def test_a_consent_withdrawn_before_the_start_sends_nothing(self):
        original = self.account.check

        def check_then_withdraw():
            state = original()
            self.free.settings.update("chatgpt", send=False)
            return state
        self.account.check = check_then_withdraw
        result = self.ask()
        self.assertEqual(result["attempts"][0]["result"], "not_allowed")
        self.assertEqual(self.runtime.starts, [])

    def test_stop_during_the_run_cancels_it(self):
        cancel = threading.Event()
        self.runtime.finish_after = 1000
        self.runtime.on_start = cancel.set
        result = self.ask(cancel)
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(self.runtime.cancels, ["r1"])

    def test_stop_before_the_start_starts_nothing(self):
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(self.ask(cancel)["outcome"], "cancelled")
        self.assertEqual((self.runtime.starts, self.runtime.probes), ([], 1))  # only the connect's check

    def test_a_turn_past_the_ceiling_is_cancelled_and_unreachable(self):
        self.runtime.finish_after = 10 ** 6
        result = self.ask()
        self.assertEqual(result["attempts"][0]["result"], "unreachable")
        self.assertEqual(self.runtime.cancels, ["r1"])

    def test_errors_come_from_the_runtime_record_and_only_fall_through_to_a_consented_backup(self):
        self.runtime.record.update(status="failed", result="",
                                   error_events=[{"kind": "turn_failed", "message": "You've hit your usage limit."}])
        result = self.ask()
        self.assertEqual((result["outcome"], result["attempts"][0]["result"]), ("exhausted", "quota"))
        self.runtime.record.update(status="completed", result="kota doldu gibi görünen ama normal bir yanıt",
                                   error_events=[])
        self.assertEqual(self.ask()["outcome"], "ok")  # the answer's text is never classified

    def test_classify_record(self):
        self.assertEqual(classify_record({"error_events": [{"message": "401 Unauthorized"}]}), "key")
        self.assertEqual(classify_record({"errors": ["stream disconnected before completion"]}), "unreachable")
        self.assertEqual(classify_record({"errors": ["something odd"]}), "other")


class PageTests(unittest.TestCase):
    def test_the_account_card_has_no_key_field_and_signs_in_only_on_a_click(self):
        from ui.js_free import JAVASCRIPT
        start = JAVASCRIPT.index("ch.kind === 'account'")
        card = JAVASCRIPT[start:JAVASCRIPT.index("} else if (!ch.connected)", start)]
        self.assertNotIn("password", card)
        self.assertIn("onboarding_begin(operation, 'codex'", card)
        self.assertIn("addEventListener('click'", card)


if __name__ == "__main__":
    unittest.main()
