"""Under "Tam yetki" an agent works with its own full strength (user decision 20 Nov 2026).

SpeS should not stop an agent from doing what it can already do on its own: read the web
while building, and run a long build, render or game test without a short turn limit.
Project-scoped writes and read-only runs keep their narrower limits.
"""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.codex_runtime import CodexRuntime
from tests.test_codex_runtime import FakeProcess


class CodexFullAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exe = self.root / "codex.exe"
        self.exe.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def command_for(self, sandbox, **kwargs):
        runtime = CodexRuntime(self.exe)
        fake = FakeProcess("")
        fake.wait = lambda timeout=None: time.sleep(0.05) or 0
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen:
            runtime.start("iş", self.root, sandbox=sandbox, **kwargs)
        return popen.call_args.args[0]

    def test_full_access_searches_the_live_web(self):
        command = self.command_for("danger-full-access")
        index = command.index('web_search="live"')
        self.assertEqual(command[index - 1], "-c")

    def test_project_writes_and_reads_do_not_get_the_web(self):
        self.assertNotIn('web_search="live"', self.command_for("workspace-write", approval="on-request"))
        self.assertNotIn('web_search="live"', self.command_for("read-only"))


class AntigravityTurnLengthTests(unittest.TestCase):
    def service(self, root):
        from core.multi_agent_service import MultiAgentService
        service = MultiAgentService.__new__(MultiAgentService)
        service.projects = MagicMock()
        service.projects.get.return_value = service.projects.selected.return_value = {
            "id": "p1", "path": str(root), "name": "p"}
        service.antigravity = MagicMock()
        service.antigravity.probe.return_value = {"ready": True}
        service.antigravity.start.return_value = {"id": "agy-run", "status": "running"}
        service._lock = __import__("threading").RLock()
        service._links = {}
        service.check_squad_connection = lambda project_id: {"connected": False}
        service._writer_status = lambda path: {"locked": False}
        service._start_writer = lambda provider, project, start, *args, **kwargs: start(*args, **kwargs)
        return service

    def test_a_full_access_turn_may_run_two_hours(self):
        from core.multi_agent_service import FULL_ACCESS_TURN_TIMEOUT
        with tempfile.TemporaryDirectory() as folder:
            service = self.service(folder)
            service.dispatch_antigravity("derle", chat_mode=True, write=True, confirm_write=True, full_access=True)
            self.assertEqual(service.antigravity.start.call_args.kwargs["timeout"], FULL_ACCESS_TURN_TIMEOUT)
            self.assertEqual(FULL_ACCESS_TURN_TIMEOUT, "2h")
            service.antigravity.start.reset_mock()
            service.dispatch_antigravity("bak", chat_mode=True)  # read-only keeps the runtime default
            self.assertNotIn("timeout", service.antigravity.start.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
