"""Codex project-read over app-server: the verified session is the one that gets the prompt."""
import json
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.codex_project_session import inventory_state
from core.codex_runtime import CodexRuntime

TOOLS = {"project_list": {}, "project_read": {}, "project_search": {}}


class FakeAppServer:
    """A scripted `codex app-server`: answers JSON-RPC requests and emits turn notifications."""

    def __init__(self, *, inventory=None, items=None, turn_status="completed", server_request=False,
                 sandbox="readOnly"):
        self.pid = 7777
        self.sent = []
        self._out = queue.Queue()
        self.inventory = inventory if inventory is not None else [
            {"name": "node_repl", "runtimeStatus": "disabled", "tools": {}},
            {"name": "quartz_project", "runtimeStatus": "connected", "tools": TOOLS}]
        self.items = items if items is not None else [
            {"type": "mcpToolCall", "server": "quartz_project", "tool": "project_read", "status": "completed"},
            {"type": "agentMessage", "text": "17 paket var.", "phase": "final_answer"}]
        self.turn_status = turn_status
        self.server_request = server_request
        self.sandbox = sandbox
        self.stdin = self
        self.stdout = self
        self.returncode = None

    # stdin side
    def write(self, data):
        for line in data.splitlines():
            message = json.loads(line)
            self.sent.append(message)
            self._answer(message)

    def flush(self):
        pass

    def close(self):
        pass

    def _emit(self, message):
        self._out.put(json.dumps(message) + "\n")

    def _answer(self, message):
        method, rid = message.get("method"), message.get("id")
        if rid is None or "method" not in message:
            return
        if method == "initialize":
            self._emit({"id": rid, "result": {"userAgent": "fake"}})
        elif method == "thread/start":
            self._emit({"id": rid, "result": {"thread": {"id": "t-1"}, "sandbox": {"type": self.sandbox},
                                              "approvalPolicy": "never"}})
        elif method == "mcpServerStatus/list":
            self._emit({"id": rid, "result": {"data": self.inventory, "nextCursor": None}})
        elif method == "turn/start":
            self._emit({"id": rid, "result": {"turn": {"id": "u-1", "status": "inProgress"}}})
            if self.server_request:
                self._emit({"id": 99, "method": "item/commandExecution/requestApproval", "params": {}})
            for item in self.items:
                self._emit({"method": "item/completed", "params": {"item": item}})
            self._emit({"method": "turn/completed", "params": {"turn": {"id": "u-1", "status": self.turn_status}}})

    # stdout side
    def __iter__(self):
        return self

    def __next__(self):
        while True:
            if self.returncode is not None and self._out.empty():
                raise StopIteration
            try:
                return self._out.get(timeout=0.05)
            except queue.Empty:
                continue

    # process side
    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = 1

    kill = terminate

    def methods(self):
        return [m.get("method") for m in self.sent if "method" in m]


class InventoryStateTests(unittest.TestCase):
    def test_only_quartz_tools_with_everything_else_disabled_is_ok(self):
        ok = [{"name": "quartz_project", "runtimeStatus": "connected", "tools": TOOLS},
              {"name": "node_repl", "runtimeStatus": "disabled"}]
        self.assertEqual(inventory_state(ok), "ok")
        self.assertEqual(inventory_state([{"name": "quartz_project", "runtimeStatus": "starting", "tools": {}}]), "starting")

    def test_refusals(self):
        for rows in ([{"name": "quartz_project", "runtimeStatus": "connected", "tools": TOOLS},
                      {"name": "node_repl", "runtimeStatus": "connected"}],
                     [{"name": "quartz_project", "runtimeStatus": "connected", "tools": TOOLS},
                      {"name": "x", "runtimeStatus": None}],
                     [{"name": "quartz_project", "runtimeStatus": "connected", "tools": {**TOOLS, "shell": {}}}],
                     [{"name": "quartz_project", "runtimeStatus": "failed", "tools": TOOLS}],
                     [{"runtimeStatus": "disabled"}], []):
            with self.subTest(rows=rows):
                self.assertNotIn(inventory_state(rows), {"ok", "starting"})


class ProjectSessionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.exe = root / "codex.exe"; self.exe.touch()
        self.project = root / "project"; self.project.mkdir()
        self.work = root / "work"; self.work.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_read(self, fake, **options):
        runtime = CodexRuntime(self.exe)
        with patch.object(CodexRuntime, "_project_read_config", return_value=["-c", "features.shell_tool=false"]), \
                patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen, \
                patch("core.codex_runtime.bind_kill_on_close_job", return_value=True), \
                patch("core.codex_runtime.stop_process_tree", side_effect=lambda p, timeout=5: p.terminate()):
            run = runtime.start("README ne diyor?", self.work, project_read=self.project, **options)
            for _ in range(400):
                if runtime.get(run["id"])["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)
        return runtime, runtime.get(run["id"]), popen

    def test_verified_session_receives_the_prompt_and_result_is_recorded(self):
        fake = FakeAppServer()
        runtime, run, popen = self.run_read(fake)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["result"], "17 paket var.")
        self.assertEqual(run["thread_id"], "t-1")
        self.assertIn("app-server", popen.call_args.args[0])
        methods = fake.methods()
        self.assertLess(methods.index("mcpServerStatus/list"), methods.index("turn/start"))
        self.assertEqual(fake.sent[methods.index("mcpServerStatus/list")]["params"]["threadId"], "t-1")
        start = next(m for m in fake.sent if m.get("method") == "thread/start")["params"]
        self.assertEqual((start["sandbox"], start["approvalPolicy"]), ("read-only", "never"))
        self.assertEqual(runtime._processes, {})

    def test_extra_enabled_server_means_no_prompt(self):
        fake = FakeAppServer(inventory=[{"name": "quartz_project", "runtimeStatus": "connected", "tools": TOOLS},
                                        {"name": "node_repl", "runtimeStatus": "connected"}])
        _, run, _ = self.run_read(fake)
        self.assertEqual(run["status"], "failed")
        self.assertNotIn("turn/start", fake.methods())

    def test_writable_thread_means_no_prompt(self):
        fake = FakeAppServer(sandbox="workspaceWrite")
        _, run, _ = self.run_read(fake)
        self.assertEqual(run["status"], "failed")
        self.assertNotIn("turn/start", fake.methods())

    def test_action_outside_quartz_tools_fails_the_turn(self):
        for item in ({"type": "mcpToolCall", "server": "node_repl", "tool": "eval"},
                     {"type": "commandExecution", "command": "dir"}):
            with self.subTest(item=item):
                fake = FakeAppServer(items=[item, {"type": "agentMessage", "text": "x", "phase": "final_answer"}])
                _, run, _ = self.run_read(fake)
                self.assertEqual(run["status"], "failed")

    def test_server_requests_are_refused(self):
        fake = FakeAppServer(server_request=True)
        _, run, _ = self.run_read(fake)
        refusal = next(m for m in fake.sent if m.get("id") == 99)
        self.assertIn("error", refusal)
        self.assertEqual(run["status"], "completed")

    def test_stop_before_the_prompt_sends_no_turn(self):
        fake = FakeAppServer()
        calls = iter([False, False, True])  # start ok, first inventory ok, then Stop
        _, run, _ = self.run_read(fake, should_abort=lambda: next(calls, True))
        self.assertIn(run["status"], {"cancelled", "failed"})
        self.assertNotIn("turn/start", fake.methods())


if __name__ == "__main__":
    unittest.main()
