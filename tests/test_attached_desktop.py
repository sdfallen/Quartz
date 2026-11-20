"""A Tam Yetki writer operates the desktop inside its own turn (user decision 20 Nov 2026).

SpeS gives the writer its desktop tools through the same broker a desktop task uses, so
Stop, the single-operator lease, the overlay and the denied-application list stay in force.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from core.desktop_broker import DesktopBroker
from core.desktop_native import NativeDesktopBackend
from core.natural_desktop import NaturalDesktopTask
from tests.test_desktop_broker import FakeBackend


class StrictBackend(FakeBackend):
    """The fake window, judged by the real denied-application rules."""

    def validate_target(self, target):
        NativeDesktopBackend.validate_target(target)


class FakeRun:
    TERMINAL = {"completed", "failed", "cancelled"}

    def __init__(self):
        self.status, self.cancelled = "running", []

    def get(self, _rid):
        return {"status": self.status, "result": "bitti"}

    def cancel(self, rid):
        self.cancelled.append(rid)
        self.status = "cancelled"


class AttachedDesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.backend = StrictBackend()
        self.broker = DesktopBroker(self.backend)
        self.events = []
        squad = Mock(initialized=True)
        squad.status.return_value = {"installed": True, "initialized": True}
        squad.create_task.return_value = {"id": "squad-task"}
        squad.receive.return_value = []
        self.task = NaturalDesktopTask(SimpleNamespace(broker=self.broker, windows=self.backend.windows),
                                       lambda *a: self.events.append(a), factories={},
                                       squad_factory=lambda root: squad, evidence_root=self.root / "evidence")
        self.overlay = patch("core.natural_desktop.overlay_manager")
        self.overlay_manager = self.overlay.start()

    def tearDown(self):
        self.task.stop()
        self.overlay.stop()
        self.broker.close()
        self.tmp.cleanup()

    def attach(self, provider="claude"):
        return self.task.attach("Oyunu aç ve modu test et", {"id": "p1", "path": str(self.root)}, "c1", provider,
                                {provider: {"model": "opus", "effort": "medium"}})

    def call(self, connection, name, args=None):
        return self.task.call(connection["token"], {"name": name, "arguments": args or {}})

    def test_attach_gives_the_writer_a_connection_and_launches_no_agent(self):
        result = self.attach()
        self.assertTrue(result["connection"]["url"].startswith("http://127.0.0.1:"))
        self.assertTrue(result["connection"]["token"])
        self.assertEqual(self.task.runs, {})
        self.assertEqual(self.task.job["roles"]["operator"], "claude")
        self.assertTrue(self.task.job["external"])
        self.overlay_manager.show.assert_not_called()  # nothing on screen until the screen is used

    def test_only_a_tam_yetki_writer_may_attach(self):
        with self.assertRaises(PermissionError):
            self.task.start("x", {"id": "p1", "path": str(self.root)}, "c1", {}, requested_permission_level="project",
                            external_operator="claude")

    def test_automatic_approval_still_refuses_denied_applications(self):
        connection = self.attach()["connection"]
        self.backend.target["exe"] = "keepass.exe"
        with self.assertRaises(PermissionError):
            self.call(connection, "desktop_request_access",
                      {"handles": [1], "log_paths": [], "reason": "Parola kasasını aç"})
        self.assertFalse(self.broker.status()["active"])

    def test_the_first_screen_tool_shows_the_overlay_once_and_grants_at_once(self):
        connection = self.attach()["connection"]
        result = self.call(connection, "desktop_request_access",
                           {"handles": [1], "log_paths": [], "reason": "Oyun penceresini test etmek"})
        self.assertEqual(result["status"], "approved")
        self.call(connection, "desktop_observe")
        self.assertEqual(self.overlay_manager.show.call_count, 1)

    def test_the_writers_run_ends_the_session_and_a_screenless_turn_stays_silent(self):
        self.attach()
        run = FakeRun()
        self.task.bind_run("claude", run, "run-1")
        run.status = "completed"
        for _ in range(100):
            if self.task.stopped.is_set():
                break
            time.sleep(0.05)
        self.assertEqual(self.task.job["status"], "completed")
        self.assertFalse([e for e in self.events if "Görev" in str(e[2])])  # no chat noise

    def test_stop_from_the_overlay_cancels_the_writer(self):
        self.attach()
        run = FakeRun()
        self.task.bind_run("claude", run, "run-1")
        self.task.stop("cancelled")
        self.assertEqual(run.cancelled, ["run-1"])


class WriterRuntimeTests(unittest.TestCase):
    def test_claude_full_access_writer_gets_operator_tools_beside_its_own(self):
        from core.claude_runtime import ClaudeRuntime, OPERATOR_MCP_TOOLS
        rt = ClaudeRuntime.__new__(ClaudeRuntime)
        args = rt.build_args("danger-full-access", desktop="operator")
        tools = args[args.index("--allowedTools") + 1].split(",")
        for name in ("Bash", "WebFetch", "mcp__quartz_desktop__desktop_observe", "mcp__quartz_desktop__desktop_act"):
            self.assertIn(name, tools)
        servers = json.loads(args[args.index("--mcp-config") + 1])["mcpServers"]
        self.assertNotIn("--collaborator-server", servers["quartz_desktop"]["args"])
        self.assertTrue(set(OPERATOR_MCP_TOOLS) <= set(tools))

    def test_claude_project_writer_cannot_take_the_desktop(self):
        from core.claude_runtime import ClaudeRuntime
        rt = ClaudeRuntime.__new__(ClaudeRuntime)
        rt.executable, rt._init_error = "claude.exe", ""
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(PermissionError):
            rt.start("iş", folder, sandbox="workspace-write", desktop_connection={"url": "u", "token": "t"})

    def test_codex_full_access_writer_keeps_its_shell_and_web_and_adds_the_desktop(self):
        from core.codex_runtime import CodexRuntime
        from tests.test_codex_runtime import FakeProcess
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "codex.exe"
            exe.touch()
            runtime = CodexRuntime(exe)
            fake = FakeProcess("")
            fake.wait = lambda timeout=None: time.sleep(0.05) or 0
            with patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen, \
                    patch.object(CodexRuntime, "_guarded_config", side_effect=AssertionError("guarded")):
                runtime.start("iş", folder, sandbox="danger-full-access",
                              desktop_connection={"url": "http://127.0.0.1:1/tool", "token": "t"})
            command = " ".join(popen.call_args.args[0])
            env = popen.call_args.kwargs["env"]
        self.assertIn("mcp_servers.quartz_desktop=", command)
        self.assertIn('web_search="live"', command)
        self.assertNotIn("features.shell_tool=false", command)
        self.assertNotIn("t", command.split())  # the token travels in the environment only
        self.assertEqual(env["QUARTZ_DESKTOP_TOKEN"], "t")


class DispatchAttachTests(unittest.TestCase):
    def service(self, folder):
        from core.multi_agent_service import MultiAgentService
        service = MultiAgentService.__new__(MultiAgentService)
        service.projects = MagicMock()
        service.projects.get.return_value = service.projects.selected.return_value = {
            "id": "p1", "path": str(folder), "name": "p"}
        service.claude = MagicMock()
        service.claude.probe.return_value = {"ready": True}
        service.claude.start.return_value = {"id": "cl-run", "status": "running"}
        import threading
        service._lock = threading.RLock()
        service._links = {}
        service.check_squad_connection = lambda project_id: {"connected": False}
        service._start_writer = lambda provider, project, start, *args, **kwargs: start(*args, **kwargs)
        session = {"connection": {"url": "u", "token": "t"}, "bind": Mock(), "stop": Mock()}
        service.desktop_attach = Mock(return_value=session)
        return service, session

    def test_a_full_access_writer_is_attached_and_its_run_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            service, session = self.service(folder)
            service.dispatch_claude("oyunu test et", chat_mode=True, write=True, confirm_write=True, full_access=True)
        self.assertEqual(service.claude.start.call_args.kwargs["desktop_connection"], {"url": "u", "token": "t"})
        session["bind"].assert_called_once_with("claude", service.claude, "cl-run")

    def test_project_writes_are_not_attached(self):
        with tempfile.TemporaryDirectory() as folder:
            service, session = self.service(folder)
            service.dispatch_claude("dosya yaz", chat_mode=True, write=True, confirm_write=True)
        service.desktop_attach.assert_not_called()
        self.assertNotIn("desktop_connection", service.claude.start.call_args.kwargs)

    def test_a_busy_screen_never_blocks_the_writer(self):
        with tempfile.TemporaryDirectory() as folder:
            service, _ = self.service(folder)
            service.desktop_attach.side_effect = RuntimeError("Another SpeS instance owns desktop input")
            service.dispatch_claude("derle", chat_mode=True, write=True, confirm_write=True, full_access=True)
        self.assertNotIn("desktop_connection", service.claude.start.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()


class SessionEndKeepsWriterTests(AttachedDesktopTests):
    def test_a_closed_target_ends_the_screen_session_but_not_the_writer(self):
        # Live 20 Nov: the agent closed the test window as asked; the session ended "blocked"
        # and cancelled the writer's turn, which then counted as a failed milestone.
        self.attach()
        run = FakeRun()
        self.task.bind_run("claude", run, "run-1")
        self.task.stop("blocked: target closed or inaccessible")
        self.assertEqual(run.cancelled, [])
