"""Chat/observer (tool_guard) and desktop Codex runs prove their effective MCP set.

Disabling only config.toml names left plugin servers such as node_repl (which
can run code) enabled; the listing Codex reports is the source of truth.
"""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.codex_runtime import CodexRuntime
from tests import test_codex_runtime as codex_tests
from tests.test_project_read import mcp_listing

STREAM = '{"type":"turn.completed","usage":{}}\n'
CONNECTION = {"url": "http://127.0.0.1:1234/tool", "token": "secret-capability"}


class GuardedMcpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exe = self.root / "codex.exe"; self.exe.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, listings, **options):
        runtime = CodexRuntime(self.exe)
        with patch("core.codex_runtime.subprocess.run", side_effect=listings) as probe, \
                patch("core.codex_runtime.subprocess.Popen",
                      return_value=codex_tests.FakeProcess(STREAM)) as popen:
            run = runtime.start("merhaba", self.root, **options)
            for _ in range(200):
                if runtime.get(run["id"])["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)
        return runtime, probe, popen

    def test_plugin_server_is_disabled_by_name_on_the_chat_path(self):
        _, probe, popen = self.start([mcp_listing("node_repl", "cua_repl"), mcp_listing()], tool_guard=True)
        self.assertEqual(probe.call_count, 2)
        joined = " ".join(popen.call_args.args[0])
        self.assertIn("mcp_servers.node_repl.enabled=false", joined)
        self.assertIn("mcp_servers.cua_repl.enabled=false", joined)
        for feature in CodexRuntime.GUARD_FEATURES_OFF:
            self.assertIn(f"features.{feature}=false", joined)
        # The probe saw the same flags the run receives.
        self.assertIn("features.shell_tool=false", " ".join(probe.call_args_list[0].args[0]))

    def test_nothing_extra_means_one_probe(self):
        _, probe, popen = self.start([mcp_listing()], tool_guard=True)
        self.assertEqual(probe.call_count, 1)
        self.assertNotIn(".enabled=false", " ".join(popen.call_args.args[0]))

    def test_desktop_keeps_only_quartz_desktop(self):
        _, probe, popen = self.start([mcp_listing("quartz_desktop", "node_repl"), mcp_listing("quartz_desktop")],
                                     desktop_connection=CONNECTION)
        command = popen.call_args.args[0]
        joined = " ".join(command)
        self.assertIn("mcp_servers.node_repl.enabled=false", joined)
        self.assertNotIn("mcp_servers.quartz_desktop.enabled=false", joined)
        self.assertEqual(sum(a.startswith("mcp_servers.quartz_desktop=") for a in command), 1)
        self.assertNotIn("secret-capability", joined)
        self.assertNotIn("secret-capability", " ".join(probe.call_args_list[0].args[0]))

    def test_unprovable_sets_refuse_before_any_record(self):
        cases = [
            ({"tool_guard": True}, [mcp_listing("node_repl"), mcp_listing("node_repl")]),  # stays enabled
            ({"tool_guard": True}, [mcp_listing(returncode=1)]),                           # cannot verify
            ({"tool_guard": True}, [mcp_listing("bad name!")]),                            # unsafe name
            ({"desktop_connection": CONNECTION}, [mcp_listing("node_repl")]),              # ours missing
        ]
        for options, listings in cases:
            with self.subTest(options=list(options), listings=[l.stdout for l in listings]):
                runtime = CodexRuntime(self.exe)
                with patch("core.codex_runtime.subprocess.run", side_effect=listings), \
                        patch("core.codex_runtime.subprocess.Popen") as popen:
                    with self.assertRaises(RuntimeError):
                        runtime.start("x", self.root, **options)
                    popen.assert_not_called()
                self.assertEqual(runtime._runs, {})
                self.assertEqual(runtime._writers, {})

    def test_plain_project_run_is_not_probed(self):
        # Normal task runs keep the user's own Codex integrations.
        _, probe, popen = self.start([], sandbox="workspace-write", approval="on-request")
        probe.assert_not_called()
        popen.assert_called_once()

    def test_stop_before_the_probe_starts_nothing(self):
        runtime = CodexRuntime(self.exe)
        with patch("core.codex_runtime.subprocess.run") as probe, \
                patch("core.codex_runtime.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError):
                runtime.start("x", self.root, tool_guard=True, should_abort=lambda: True)
        probe.assert_not_called(); popen.assert_not_called()
        self.assertEqual(runtime._runs, {})


if __name__ == "__main__":
    unittest.main()
