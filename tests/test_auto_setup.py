"""Autonomous setup (core.auto_setup, 27 Nov): SpeS sets up its own agent tools, the uninstaller
removes them, and nothing installs in a source checkout or a test unless asked."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core.auto_setup import AutoSetup, RETRY_SECONDS, TOOLS

ROOT = Path(__file__).resolve().parents[1]


class FakeInstaller:
    def __init__(self, fail=()):
        self.fail, self.calls, self.installed = set(fail), [], set()

    def install(self, tool):
        self.calls.append(tool)
        if tool in self.fail:
            raise RuntimeError("ağ yok")
        self.installed.add(tool)
        return {"installed": True}


class AutoSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "auto_setup.json"
        self.now = [1000.0]

    def make(self, installer, present=()):
        present = set(present)

        def resolve(tool):
            if tool in present or tool in installer.installed:
                return f"C:/fake/{tool}.exe"
            raise FileNotFoundError(tool)
        return AutoSetup(installer, self.state, clock=lambda: self.now[0], resolve=resolve)

    def finish(self, setup):
        setup.thread.join(5)
        return setup.status()

    def test_fs6_nothing_starts_without_the_users_choice_and_status_only_reads(self):
        installer = FakeInstaller()
        setup = self.make(installer)
        self.assertEqual(setup.status()["state"], "needs_choice")
        self.assertEqual(setup.start()["state"], "needs_choice")
        self.assertIsNone(setup.thread)
        self.assertEqual(installer.calls, [])
        self.assertIn("MB", setup.status()["download"])

    def test_every_missing_tool_is_installed_once_after_the_choice(self):
        installer = FakeInstaller()
        setup = self.make(installer, present={"python", "codex"})
        self.assertEqual(setup.start(consent=True)["state"], "running")
        self.assertIn(setup.start()["state"], {"running", "done"})  # a second start never runs it twice
        status = self.finish(setup)
        self.assertEqual(status["state"], "done")
        self.assertEqual(installer.calls, ["agy", "claude"])
        later = self.make(installer, present={"python", "codex"})
        self.assertEqual(later.start()["state"], "ready")  # the recorded choice carries over

    def test_a_failed_tool_is_recorded_and_retried_only_later(self):
        installer = FakeInstaller(fail={"claude"})
        setup = self.make(installer)
        setup.start(consent=True)
        status = self.finish(setup)
        self.assertEqual(status["state"], "partial")
        self.assertIn("claude", status["failed"])
        again = self.make(installer)
        self.assertEqual(again.start()["state"], "waiting")  # within the retry window: nothing runs
        self.now[0] += RETRY_SECONDS + 1
        installer.fail.clear()
        again.start()
        self.assertEqual(self.finish(again)["state"], "done")
        self.assertEqual(installer.calls.count("claude"), 2)

    def test_fs6_stop_ends_after_the_current_tool(self):
        release = threading.Event()
        installer = FakeInstaller()
        original = installer.install
        installer.install = lambda tool: (release.wait(5), original(tool))[1]
        setup = self.make(installer)
        setup.start(consent=True)
        self.assertEqual(setup.stop()["state"], "stopping")
        release.set()
        status = self.finish(setup)
        self.assertEqual(status["state"], "stopped")
        self.assertEqual(installer.calls, ["python"])

    def test_rfs3_free_only_during_setup_stops_the_tools_still_waiting(self):
        release = threading.Event()
        installer = FakeInstaller()
        original = installer.install
        installer.install = lambda tool: (release.wait(5), original(tool))[1]
        setup = self.make(installer)
        setup.start(consent=True)
        setup.forget_choice()  # "Yalnız ücretsiz sohbet" while Codex is being installed
        self.assertEqual(setup.status()["state"], "stopping")
        release.set()
        self.finish(setup)
        self.assertEqual(installer.calls, ["python"])
        self.assertEqual(setup.start()["state"], "needs_choice")  # no choice, no new download

    def test_free_only_forgets_the_choice(self):
        setup = self.make(FakeInstaller())
        setup.start(consent=True)
        self.finish(setup)
        setup.forget_choice()
        self.assertFalse(setup.consented())

    def test_python_then_the_three_agent_tools_are_the_set(self):
        self.assertEqual([t for t, _ in TOOLS], ["python", "codex", "agy", "claude"])


class OnboardingAutoTests(unittest.TestCase):
    def test_a_source_checkout_never_installs_by_itself(self):
        from core.onboarding import OnboardingService
        service = OnboardingService(base=tempfile.mkdtemp(), installer=FakeInstaller())
        with patch.dict(os.environ, {"QUARTZ_AUTO_SETUP": ""}):
            self.assertEqual(service.auto_setup(), {"state": "off"})


class InstallerTests(unittest.TestCase):
    def test_claude_code_is_a_managed_package(self):
        from core import cli_installer
        self.assertEqual(cli_installer.PACKAGES["claude"], "@anthropic-ai/claude-code")
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"QUARTZ_CLAUDE_PATH": ""}), \
                    patch.object(cli_installer.shutil, "which", return_value=None), \
                    patch.object(cli_installer, "app_root", return_value=Path(folder)):
                with self.assertRaises(FileNotFoundError):
                    cli_installer.resolve_cli("claude", root=folder)

    def test_claude_uses_the_signed_native_program_never_the_npm_stub(self):
        import json
        from core import cli_installer
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / "node_modules" / "@anthropic-ai" / "claude-code-win32-x64"
            package.mkdir(parents=True)
            (package / "package.json").write_text(json.dumps({"name": "@anthropic-ai/claude-code-win32-x64"}),
                                                  encoding="utf-8")
            (package / "claude.exe").write_bytes(b"MZ")
            with patch.object(cli_installer.platform, "machine", return_value="AMD64"):
                self.assertEqual(cli_installer.claude_native(folder), (package / "claude.exe").resolve())
                (package / "package.json").write_text(json.dumps({"name": "evil"}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    cli_installer.claude_native(folder)

    def test_a_quoted_organization_with_a_comma_is_matched_exactly(self):
        import json
        import subprocess
        from core import install_security
        def fake(subject):
            return subprocess.CompletedProcess([], 0, json.dumps({"status": "Valid", "subject": subject}), "")
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            path = handle.name
        self.addCleanup(os.unlink, path)
        good = 'CN="Anthropic, PBC", O="Anthropic, PBC", L=San Francisco, C=US'
        with patch("core.cli_installer.owned_run", return_value=fake(good)):
            self.assertEqual(install_security.verify_publisher(path, "Anthropic, PBC")["status"], "Valid")
        for subject in ('CN=x, O="Anthropic, PBC Evil", C=US', 'CN="O=Anthropic, PBC", O=Evil'):
            with patch("core.cli_installer.owned_run", return_value=fake(subject)):
                with self.assertRaises(ValueError):
                    install_security.verify_publisher(path, "Anthropic, PBC")
        with patch("core.cli_installer.owned_run", return_value=fake("CN=Google LLC, O=Google LLC, C=US")):
            self.assertEqual(install_security.verify_publisher(path, "Google LLC")["status"], "Valid")
        # Fides FS5: text inside another field's quotes is never a field; a broken subject grants nothing.
        for subject in ('CN="Unrelated, O=Google LLC, trailing", O=Evil Corp, C=US', 'CN="x, O=Google LLC',
                        'garbage, O=Google LLC'):
            with patch("core.cli_installer.owned_run", return_value=fake(subject)):
                with self.assertRaises(ValueError):
                    install_security.verify_publisher(path, "Google LLC")

    @unittest.skipUnless(os.name == "nt", "Windows Job Object")
    def test_setup_processes_are_owned_and_a_timeout_ends_the_whole_tree(self):
        import subprocess
        import sys
        import time
        from core.cli_installer import owned_run
        done = owned_run([sys.executable, "-c", "print('hazir')"], capture_output=True, text=True, timeout=30)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "hazir"))
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "child.txt"
            child = ("import time,pathlib\n"
                     f"p=pathlib.Path(r'{marker}')\n"
                     "while True:\n    p.write_text(str(time.time()))\n    time.sleep(0.1)\n")
            parent = ("import subprocess,sys,time\n"
                      f"subprocess.Popen([sys.executable,'-c',{child!r}])\n"
                      "time.sleep(60)\n")
            with self.assertRaises(subprocess.TimeoutExpired):
                owned_run([sys.executable, "-c", parent], timeout=2)
            time.sleep(0.6)
            before = marker.read_text() if marker.exists() else ""
            time.sleep(0.6)
            after = marker.read_text() if marker.exists() else ""
            self.assertEqual(before, after, "the grandchild still runs after the timeout")

    def test_rfs4_the_signature_check_runs_owned_too(self):
        import json
        import subprocess
        from core import install_security
        calls = []

        def owned(cmd, **kwargs):
            calls.append(cmd[0])
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"status": "Valid", "subject": "O=Google LLC"}), "")
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            path = handle.name
        self.addCleanup(os.unlink, path)
        with patch("core.cli_installer.owned_run", side_effect=owned),                 patch.object(install_security.subprocess, "run", side_effect=AssertionError("unowned run")):
            self.assertEqual(install_security.verify_publisher(path, "Google LLC")["status"], "Valid")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].lower().endswith("powershell.exe"))

    def test_the_uninstaller_removes_what_spes_set_up(self):
        iss = (ROOT / "installer" / "Quartz.iss").read_text(encoding="utf-8")
        self.assertIn('Type: filesandordirs; Name: "{localappdata}\\Quartz\\bin"', iss)
        self.assertIn("DelTree(ExpandConstant('{localappdata}\\Quartz\\free_chat')", iss)

    def test_the_first_run_screen_offers_free_chat_and_says_setup_is_automatic(self):
        from ui.shell import SHELL_MARKUP
        self.assertIn('id="cliFree"', SHELL_MARKUP)
        self.assertIn('id="autoSetupLine"', SHELL_MARKUP)
        self.assertIn('<option value="claude">', SHELL_MARKUP)


if __name__ == "__main__":
    unittest.main()
