import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.desktop_agents import DesktopAgentService, codex_mcp_override, connection_environment, ensure_antigravity_tool_grants
from tests.test_desktop_broker import FakeBackend
from tests.test_codex_runtime import FakeProcess as CodexProcess
from tests.test_antigravity_runtime import FakeProcess as AgyProcess
from core.codex_runtime import CodexRuntime
from core.antigravity_runtime import AntigravityRuntime


class DesktopRuntimeTests(unittest.TestCase):
    def test_codex_scope_is_per_run_and_token_is_not_in_command(self):
        connection = {"url": "http://127.0.0.1:1234/tool", "token": "secret-capability"}
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "codex.exe"; exe.touch()
            runtime = CodexRuntime(exe)
            fake = CodexProcess('{"type":"turn.completed","usage":{}}\n')
            with patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen:
                runtime.start("test", directory, desktop_connection=connection)
            command = popen.call_args.args[0]
            self.assertIn("read-only", command)
            self.assertIn("mcp_servers.quartz_desktop", " ".join(command))
            self.assertNotIn("secret-capability", " ".join(command))
            self.assertEqual(popen.call_args.kwargs["env"]["QUARTZ_DESKTOP_TOKEN"], "secret-capability")
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
            self.assertIn("features.shell_tool=false",command)
            self.assertIn("features.computer_use=false",command)

    def test_antigravity_keeps_sandbox_and_does_not_auto_approve(self):
        connection = {"url": "http://127.0.0.1:1234/tool", "token": "secret-capability"}
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "agy.exe"; exe.touch()
            runtime = AntigravityRuntime(exe)
            fake = AgyProcess('{"event":"result","result":{"status":"SUCCESS","response":"ok"}}\n')
            with patch("core.antigravity_runtime.subprocess.Popen", return_value=fake) as popen:
                runtime.start("test", directory, desktop_connection=connection)
            command = popen.call_args.args[0]
            self.assertIn("--sandbox", command)
            self.assertIn("auto", command)
            self.assertNotIn("--dangerously-skip-permissions", command)
            self.assertEqual(popen.call_args.kwargs["env"]["QUARTZ_DESKTOP_TOKEN"], "secret-capability")

    def test_environment_does_not_mutate_parent(self):
        with patch.dict(os.environ, {"QUARTZ_DESKTOP_TOKEN": "parent"}):
            env = connection_environment({"url": "url", "token": "child"})
            self.assertEqual(os.environ["QUARTZ_DESKTOP_TOKEN"], "parent")
            self.assertEqual(env["QUARTZ_DESKTOP_TOKEN"], "child")

    def test_override_is_valid_toml_without_secret(self):
        import tomllib
        value = codex_mcp_override({"url": "url", "token": "hidden"})
        parsed = tomllib.loads(value)["mcp_servers"]["quartz_desktop"]
        self.assertIn("QUARTZ_DESKTOP_TOKEN", parsed["env_vars"])
        self.assertEqual(parsed["default_tools_approval_mode"], "approve")
        self.assertEqual(set(parsed["enabled_tools"]), {"desktop_focus", "desktop_observe", "desktop_act", "desktop_windows", "desktop_switch", "desktop_launch",
            "task_context", "desktop_request_access", "task_wait", "task_message", "task_read_log", "desktop_verify",
            "warband_status","warband_request_access","warband_source","warband_run","warband_log","warband_verify","warband_observe","warband_start_game","warband_act",
            "jarvis_open_app", "jarvis_media_web", "jarvis_system_info", "jarvis_input"})
        self.assertNotIn("hidden", value)

    def test_agy_rules_are_exact_and_preserve_denials_and_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            original = {"other": 42, "permissions": {"deny": ["command(*)"], "allow": ["read_file(./*)"]}}
            path.write_text(json.dumps(original), encoding="utf-8")
            ensure_antigravity_tool_grants(path)
            result = json.loads(path.read_text())
            self.assertEqual(result["other"], 42)
            self.assertEqual(result["permissions"]["deny"], ["command(*)"])
            rules = result["permissions"]["allow"]
            self.assertEqual(len(rules), 26)
            self.assertNotIn("mcp(*)", rules)
            self.assertNotIn("command(*)", rules)
            backups = list(path.parent.glob("settings.before-*.json"))
            self.assertEqual(json.loads(backups[0].read_text()), original)
            ensure_antigravity_tool_grants(path)
            self.assertEqual(len(list(path.parent.glob("settings.before-*.json"))), 1)


class DesktopServiceTests(unittest.TestCase):
    def test_missing_confirmation_never_creates_capability(self):
        service = DesktopAgentService(FakeBackend())
        with self.assertRaises(PermissionError):
            service.start("codex", 1, "test", "gpt-6-luna", "low", confirmed="true")
        self.assertFalse(service.broker.status()["active"])
        service.close()

    def test_start_failure_releases_capability(self):
        service = DesktopAgentService(FakeBackend())
        with patch("core.codex_runtime.CodexRuntime") as runtime:
            runtime.SUPPORTED_EFFORTS = ["low"]
            runtime.return_value.start.side_effect = RuntimeError("cannot start")
            with self.assertRaises(RuntimeError):
                service.start("codex", 1, "test", "gpt-6-luna", "low", confirmed=True)
        self.assertFalse(service.broker.status()["active"])
        service.close()

    def test_gui_desktop_permission_is_not_routed_through_unauthenticated_ipc(self):
        import gui
        api = gui.Api()
        service = MagicMock(); api._desktop_agents = service
        with patch("gui.ipc_send") as ipc:
            api.desktop_operator_start("codex", 1, "test", "gpt-6-luna", "low", "true")
        self.assertFalse(service.start.call_args.kwargs["confirmed"])
        ipc.assert_not_called()

