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

    def test_every_missing_tool_is_installed_in_the_background_once(self):
        installer = FakeInstaller()
        setup = self.make(installer, present={"codex"})
        started = setup.start()
        self.assertEqual(started["state"], "running")
        self.assertIn(setup.start()["state"], {"running", "done"})  # a second start never runs it twice
        status = self.finish(setup)
        self.assertEqual(status["state"], "done")
        self.assertEqual(installer.calls, ["agy", "claude"])
        self.assertEqual(setup.start()["state"], "ready")

    def test_a_failed_tool_is_recorded_and_retried_only_later(self):
        installer = FakeInstaller(fail={"claude"})
        setup = self.make(installer)
        setup.start()
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

    def test_the_three_agent_tools_are_the_set(self):
        self.assertEqual([t for t, _ in TOOLS], ["codex", "agy", "claude"])


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
        with patch.object(install_security.subprocess, "run", return_value=fake(good)):
            self.assertEqual(install_security.verify_publisher(path, "Anthropic, PBC")["status"], "Valid")
        for subject in ('CN=x, O="Anthropic, PBC Evil", C=US', 'CN="O=Anthropic, PBC", O=Evil', "O=Google LLC"):
            with patch.object(install_security.subprocess, "run", return_value=fake(subject)):
                with self.assertRaises(ValueError):
                    install_security.verify_publisher(path, "Anthropic, PBC")
        with patch.object(install_security.subprocess, "run", return_value=fake("CN=Google LLC, O=Google LLC, C=US")):
            self.assertEqual(install_security.verify_publisher(path, "Google LLC")["status"], "Valid")

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
