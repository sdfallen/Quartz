"""Regression tests for Q01-Q10 review findings."""
import ast
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from agents.scheduler_agent import SchedulerAgent
from core.antigravity_runtime import AntigravityRuntime
from core.cli_installer import CliInstaller
from core.gemini_runtime import GeminiRuntime, google_runtime
from core.onboarding import OnboardingService
from scripts.audit_publish import forbidden_path
from tests.test_natural_desktop import NaturalTaskTests


class Q01ToQ10ReviewFixesTests(unittest.TestCase):
    def test_q01_and_q08_jarvis_system_info_and_redaction(self):
        functions = [
            n.name
            for n in ast.parse(Path("system_controller.py").read_text(encoding="utf-8")).body
            if isinstance(n, ast.FunctionDef)
        ]
        case = NaturalTaskTests()
        case.setUp()
        try:
            sysfake = SimpleNamespace(**{name: Mock(return_value="fake-info") for name in functions})
            advfake = SimpleNamespace(
                clipboard_copy=Mock(return_value="copied"),
                clipboard_paste=Mock(return_value="SENSITIVE_CLIPBOARD_DATA"),
            )
            case.task._controllers = lambda: (sysfake, advfake)

            res_tel = case.call("jarvis_system_info", {"action": "telemetry"})
            res_proc = case.call("jarvis_system_info", {"action": "processes"})
            self.assertEqual(res_tel["status"], "ok")
            self.assertEqual(res_proc["status"], "ok")
            sysfake.get_system_info.assert_called_once()
            sysfake.list_processes.assert_called_once()

            case.call("jarvis_system_info", {"action": "clipboard_set", "text": "SECRET_TEXT_VALUE"})
            logged_arg = case.task.job["jarvis_actions"][-1]["arguments"]["text"]
            self.assertNotEqual(logged_arg, "SECRET_TEXT_VALUE")
            self.assertIn("[redacted:", logged_arg)

            clip_res = case.call("jarvis_system_info", {"action": "clipboard_get"})
            self.assertEqual(clip_res["result"], "SENSITIVE_CLIPBOARD_DATA")
            logged_res = case.task.job["jarvis_actions"][-1]["result"]
            self.assertNotEqual(logged_res, "SENSITIVE_CLIPBOARD_DATA")
            self.assertIn("[redacted:", logged_res)
        finally:
            case.tearDown()

    def test_q02_unvalidated_credentials_are_configured_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".env").write_text("GEMINI_API_KEY=unvalidated-placeholder\n", encoding="utf-8")
            installer = Mock()
            installer.status.return_value = {
                "codex": {"installed": False, "executable": None},
                "gemini": {"installed": True, "executable": "fake.exe"},
            }
            with patch.dict(os.environ, {"USERPROFILE": d, "GEMINI_CLI_HOME": d}, clear=True):
                state = OnboardingService(root, installer=installer).status()
            gem = state["providers"]["gemini"]
            self.assertTrue(gem["configured"])
            self.assertFalse(gem["auth_verified"])
            self.assertEqual(gem["verification_status"], "unverified")
            self.assertFalse(gem["ready"])

    def test_q03_onboarding_rollback_on_invalid_memory_and_corrupt_json_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            installer = Mock()
            (root / ".env").write_text("OLD_SETTING=keep\n", encoding="utf-8")
            (root / "quartz_memory.json").write_text("[]", encoding="utf-8")
            service = OnboardingService(root, installer=installer, validate=Mock())
            with patch("core.onboarding.resolve_cli", return_value="fake.exe"):
                service._work("key", "gemini", "REVIEW_PLACEHOLDER_NOT_A_SECRET")
            self.assertEqual(service.job["state"], "error")
            self.assertNotIn("GEMINI_API_KEY=", (root / ".env").read_text(encoding="utf-8"))
            self.assertIn("OLD_SETTING=keep", (root / ".env").read_text(encoding="utf-8"))

            (root / "quartz_memory.json").write_text("{broken-json", encoding="utf-8")
            service._save("gemini", "REVIEW_PLACEHOLDER_NOT_A_SECRET")
            self.assertEqual((root / "quartz_memory.json").read_text(encoding="utf-8"), "{broken-json")
            self.assertTrue((root / "quartz_memory.corrupt.json").is_file())
            with patch.dict(os.environ, {"USERPROFILE": d, "GEMINI_CLI_HOME": d}, clear=True):
                installer.status.return_value = {
                    "codex": {"installed": False, "executable": None},
                    "gemini": {"installed": True, "executable": "fake.exe"},
                }
                state = service.status(force=True)
            self.assertTrue(state["providers"]["gemini"]["ready"])

    def test_q04_account_login_strips_api_keys_and_persists_backend_choice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            service = OnboardingService(root, installer=Mock(), validate=Mock())
            with patch("core.onboarding.resolve_cli", return_value="fake.exe"), patch(
                "core.onboarding.cli_environment", return_value={"GEMINI_API_KEY": "STALE_KEY"}
            ), patch("core.onboarding.subprocess.Popen") as launch:
                service._work("account", "gemini", "")
            self.assertNotIn("GEMINI_API_KEY", launch.call_args.kwargs["env"])
            self.assertFalse((root / ".env").exists())
            self.assertTrue((root / "quartz_memory.json").is_file())
            with patch("core.gemini_runtime.cli_environment", return_value={}), patch.dict(
                os.environ, {}, clear=True
            ), patch("core.gemini_runtime.GeminiRuntime") as gem_cls:
                google_runtime(base=root, legacy_factory=Mock())
                gem_cls.assert_called_once()

    def test_q05_cli_installer_reuses_only_after_health_probe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            exe = root / "gemini.exe"
            exe.touch()
            runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="0.66.0\n", stderr=""))
            with patch("core.cli_installer.resolve_cli", return_value=str(exe)):
                result = CliInstaller(root, run=runner).install("gemini")
            self.assertTrue(result["reused"])
            self.assertEqual(runner.call_count, 1)

    def test_q06_and_q07_host_timeout_and_gemini_tool_result_normalization(self):
        self.assertEqual(AntigravityRuntime._parse_timeout_seconds("2m"), 120.0)
        self.assertEqual(AntigravityRuntime._parse_timeout_seconds("45s"), 45.0)
        rt = object.__new__(GeminiRuntime)
        use_ev = rt._normalize_event(
            {
                "type": "tool_use",
                "tool_id": "call-1",
                "tool_name": "run_shell_command",
                "parameters": {"command": "echo test"},
            }
        )
        self.assertEqual(use_ev["step_update"]["state"], "RUNNING")
        res_ev = rt._normalize_event(
            {
                "type": "tool_result",
                "tool_id": "call-1",
                "status": "success",
                "output": "test\n",
                "exit_code": 0,
            }
        )
        self.assertEqual(res_ev["event"], "step_update")
        self.assertEqual(res_ev["step_update"]["state"], "DONE")
        self.assertEqual(res_ev["step_update"]["tool_name"], "run_shell_command")
        self.assertEqual(res_ev["step_update"]["tool_info"]["parameters"]["command"], "echo test")
        self.assertEqual(res_ev["step_update"]["tool_info"]["output"], "test\n")

    def test_q09_daily_scheduler_repeats_on_subsequent_days(self):
        scheduler = SchedulerAgent({})
        scheduler._tasks = [
            {
                "id": 1,
                "time": "12:00",
                "repeat": True,
                "done": False,
                "last_run": None,
                "run_count": 0,
                "command": "placeholder",
                "label": "review",
            }
        ]
        scheduler._execute_task = Mock()
        with patch("agents.scheduler_agent.datetime") as dates:
            dates.now.side_effect = [
                datetime(2026, 10, 28, 12, 0),
                datetime(2026, 10, 28, 12, 0),
                datetime(2026, 10, 29, 12, 0),
            ]
            scheduler._check_tasks()
            scheduler._check_tasks()  # Same minute on same day should not double-run
            scheduler._check_tasks()  # Next day same minute MUST run
        self.assertEqual(scheduler._execute_task.call_count, 2)

    def test_q10_publication_audit_allows_verified_squad_binary_only(self):
        self.assertFalse(forbidden_path("assets/bin/squad.exe"))
        self.assertTrue(forbidden_path("assets/bin/squad.exe", b"tampered-binary"))
        self.assertTrue(forbidden_path("dist/Quartz.exe"))

    def test_codex_resolve_cli_prefers_native_exe_and_unwraps_npm_cmd_without_cmd_shell(self):
        from core.cli_installer import resolve_cli
        from core.codex_runtime import CodexRuntime

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            npm_cmd = root / "npm" / "codex.cmd"
            npm_cmd.parent.mkdir(parents=True)
            npm_cmd.write_text("@echo off\n", encoding="utf-8")
            pkg_dir = npm_cmd.parent / "node_modules" / "@openai" / "codex"
            (pkg_dir / "bin").mkdir(parents=True)
            (pkg_dir / "bin" / "codex.js").write_text("// codex\n", encoding="utf-8")
            (pkg_dir / "package.json").write_text(
                json.dumps({"name": "@openai/codex", "bin": {"codex": "bin/codex.js"}}),
                encoding="utf-8",
            )
            native_exe = root / "OpenAI" / "Codex" / "bin" / "v1" / "codex.exe"
            native_exe.parent.mkdir(parents=True)
            native_exe.write_text("MZ", encoding="utf-8")
            node_exe = root / "node" / "node.exe"
            node_exe.parent.mkdir(parents=True)
            node_exe.write_text("MZ", encoding="utf-8")

            def fake_which(name):
                if name == "codex.cmd":
                    return str(npm_cmd)
                if name == "node":
                    return str(node_exe)
                return None

            with patch.dict(os.environ, {"LOCALAPPDATA": str(root), "QUARTZ_CLI_ROOT": str(root / "empty")}, clear=False), \
                 patch("core.cli_installer.app_root", return_value=root / "empty"), \
                 patch("core.cli_installer.shutil.which", side_effect=fake_which):
                # Native codex.exe in LOCALAPPDATA cache must win over codex.cmd on PATH
                self.assertEqual(resolve_cli("codex"), str(native_exe.resolve()))
                # And if npm codex.cmd is explicitly used, _command must unwrap to node.exe + codex.js (never cmd.exe /c)
                rt = CodexRuntime(str(npm_cmd))
                cmd = rt._command(["-c", 'mcp_servers.quartz_desktop={enabled_tools=["desktop_request_access"]}', "exec"])
                self.assertEqual(Path(cmd[0]).name.lower(), "node.exe")
                self.assertTrue(cmd[1].endswith("codex.js"))
                self.assertEqual(cmd[2], "-c")
                self.assertIn('"desktop_request_access"', cmd[3])

    def test_shared_probe_cache_and_mcp_registration_fast_path(self):
        from core.antigravity_runtime import AntigravityRuntime
        from core.desktop_agents import is_antigravity_mcp_registered

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "agy.exe"
            exe.write_text("MZ", encoding="utf-8")
            rt1 = AntigravityRuntime(exe)
            with patch.object(rt1, "_probe", side_effect=[
                {"returncode": 0, "stdout": "0.2.3\n", "stderr": ""},
                {"returncode": 0, "stdout": "gemini-4-argon-medium\n", "stderr": ""},
            ]) as probe_mock:
                res1 = rt1.probe()
                self.assertTrue(res1["ready"])
                self.assertEqual(probe_mock.call_count, 2)

            rt2 = AntigravityRuntime(exe)
            with patch.object(rt2, "_probe") as probe_mock2:
                res2 = rt2.probe()
                self.assertTrue(res2["ready"])
                probe_mock2.assert_not_called()

            mcp_cfg = root / "mcp_config.json"
            helper = str(root / "QuartzDesktopMCP.exe")
            mcp_cfg.write_text(
                json.dumps({"mcpServers": {"quartz-desktop": {"command": helper, "disabled": False}}}),
                encoding="utf-8",
            )
            self.assertTrue(is_antigravity_mcp_registered([helper], mcp_cfg))
            self.assertFalse(is_antigravity_mcp_registered([helper, "--other"], mcp_cfg))


if __name__ == "__main__":
    unittest.main()
