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
from core.codex_project_session import FEATURES_OFF as OFF  # noqa: E402


def good_config(root=None):
    if root is not None and Path(str(root)).exists():
        from core.project_read_mcp import expected_server
        server = expected_server(root)
        quartz = {"enabled": True, "command": server["command"], "args": server["args"]}
    else:
        quartz = {"enabled": True, "args": ["desktop_mcp.py", "--project-read-server"] + ([str(root)] if root else [])}
    return {"features": {name: False for name in OFF},
            "mcp_servers": {"quartz_project": quartz, "node_repl": {"enabled": False}}}


class FakeAppServer:
    """A scripted `codex app-server`: answers JSON-RPC requests and emits turn notifications."""

    def __init__(self, *, inventory=None, items=None, turn_status="completed", server_request=False,
                 sandbox="readOnly", config=None):
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
        self.config = config if config is not None else good_config()
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
        elif method == "config/read":
            self._emit({"id": rid, "result": {"config": self.config}})
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
                     [{"name": "quartz_project", "runtimeStatus": "connected", "tools": TOOLS}] * 2,
                     [{"name": "quartz_project", "runtimeStatus": "connected", "tools": {}}],
                     [{"runtimeStatus": "disabled"}], []):
            with self.subTest(rows=rows):
                self.assertNotIn(inventory_state(rows), {"ok", "starting"})

    def test_start_gate_on_effective_config(self):
        from core.codex_project_session import config_refusal
        self.assertIsNone(config_refusal(good_config("C:/p"), "C:/p"))
        bad = good_config("C:/p"); bad["mcp_servers"]["other"] = {"enabled": True}
        self.assertIsNotNone(config_refusal(bad, "C:/p"))
        unknown = good_config("C:/p"); unknown["mcp_servers"]["other"] = {}  # enabled not stated
        self.assertIsNotNone(config_refusal(unknown, "C:/p"))
        plugins = good_config("C:/p"); plugins["features"]["plugins"] = True
        self.assertIsNotNone(config_refusal(plugins, "C:/p"))
        self.assertIsNotNone(config_refusal(good_config("C:/other"), "C:/p"))
        self.assertIsNotNone(config_refusal(None))


class ProjectSessionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.exe = root / "codex.exe"; self.exe.touch()
        self.project = root / "project"; self.project.mkdir()
        self.work = root / "work"; self.work.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_read(self, fake, *, cleanup_ok=True, keep_config=False, **options):
        runtime = CodexRuntime(self.exe)
        if not keep_config:
            fake.config = good_config(self.project.resolve())

        def cleanup(process, report_pending):
            if not cleanup_ok:
                raise RuntimeError("tree discovery incomplete")
            return 0

        with patch.object(CodexRuntime, "_project_read_config", return_value=["-c", "features.shell_tool=false"]), \
                patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen, \
                patch("core.codex_runtime.bind_kill_on_close_job", return_value=True), \
                patch("core.codex_runtime.wait_for_owned_cleanup", side_effect=cleanup), \
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

    def test_config_gate_refuses_before_any_thread_starts(self):
        fake = FakeAppServer()
        fake.config = good_config(self.project.resolve())
        fake.config["mcp_servers"]["surprise"] = {"enabled": True}
        _, run, _ = self.run_read(fake, keep_config=True)
        self.assertEqual(run["status"], "failed")
        self.assertIn("config/read", fake.methods())
        self.assertNotIn("thread/start", fake.methods())
        self.assertNotIn("turn/start", fake.methods())

    def test_helper_identity_is_pinned(self):
        from core.codex_project_session import config_refusal
        from core.project_read_mcp import expected_server
        expected = expected_server(self.project)
        good = good_config(self.project.resolve())
        self.assertIsNone(config_refusal(good, str(self.project.resolve()), expected))
        for change in ({"command": "C:/evil/tool.exe"}, {"args": good["mcp_servers"]["quartz_project"]["args"] + ["--x"]},
                       {"type": "streamable_http"}):
            with self.subTest(change=change):
                bad = good_config(self.project.resolve())
                bad["mcp_servers"]["quartz_project"].update(change)
                self.assertIsNotNone(config_refusal(bad, str(self.project.resolve()), expected))

    def test_thread_start_pins_limits_and_a_new_server_meanwhile_is_refused(self):
        fake = FakeAppServer()
        _, run, _ = self.run_read(fake)
        start = next(m for m in fake.sent if m.get("method") == "thread/start")["params"]
        from core.codex_project_session import FEATURES_OFF
        self.assertEqual(start["config"]["features"], {name: False for name in FEATURES_OFF})
        for name in ("view_image", "image_generation", "in_app_browser", "multi_agent_v2", "browser_use_external"):
            self.assertIs(start["config"]["features"][name], False)  # the thread table replaces the earlier one
        self.assertEqual(set(CodexRuntime.PROJECT_READ_FEATURES_OFF), set(FEATURES_OFF))
        servers = start["config"]["mcp_servers"]
        self.assertEqual(set(servers), {"node_repl", "quartz_project"})  # the thread's whole table
        self.assertEqual(servers["node_repl"], {"enabled": False})
        self.assertIn("--project-read-server", servers["quartz_project"]["args"])
        self.assertFalse(start["config"]["features"]["plugins"])
        # A server name that appears between the two config reads stops everything before the prompt.
        fake2 = FakeAppServer()
        reads = []
        original = fake2._answer

        def answer(message):
            if message.get("method") == "config/read":
                reads.append(1)
                config = good_config(self.project.resolve())
                if len(reads) > 1:
                    config["mcp_servers"]["late"] = {"enabled": False}
                fake2._emit({"id": message["id"], "result": {"config": config}})
                return
            original(message)

        fake2._answer = answer
        _, run2, _ = self.run_read(fake2, keep_config=True)
        self.assertEqual(run2["status"], "failed")
        self.assertIn("thread/start", fake2.methods())
        self.assertNotIn("turn/start", fake2.methods())

    def test_stop_retries_an_unconfirmed_cleanup_and_frees_ownership(self):
        fake = FakeAppServer()
        runtime, run, _ = self.run_read(fake, cleanup_ok=False)
        self.assertIn(run["id"], runtime._processes)
        with patch("core.codex_runtime.stop_process_tree", side_effect=lambda p, timeout=5: p.terminate()), \
                patch("core.codex_runtime.owned_cleanup_pending", return_value=False), \
                patch("core.codex_runtime.close_process_job"):
            after = runtime.cancel(run["id"])
        self.assertFalse(after["cleanup_pending"])
        self.assertIs(after["process_exit_confirmed"], True)
        self.assertNotIn(run["id"], runtime._processes)

    def test_unlisted_tool_on_quartz_server_fails_the_turn(self):
        fake = FakeAppServer(items=[{"type": "mcpToolCall", "server": "quartz_project", "tool": "project_write"},
                                    {"type": "agentMessage", "text": "x", "phase": "final_answer"}])
        _, run, _ = self.run_read(fake)
        self.assertEqual(run["status"], "failed")

    def test_unconfirmed_cleanup_keeps_process_ownership(self):
        fake = FakeAppServer()
        runtime, run, _ = self.run_read(fake, cleanup_ok=False)
        self.assertEqual(run["status"], "failed")
        self.assertIn(run["id"], runtime._processes)
        self.assertTrue(run["cleanup_pending"])
        self.assertFalse(run["process_exit_confirmed"])

    def test_confirmed_exit_is_reported_for_every_ending(self):
        # The chat's stop receipt waits for process_exit_confirmed (Gemini review).
        for fake, options in ((FakeAppServer(), {}),
                              (FakeAppServer(sandbox="workspaceWrite"), {}),
                              (FakeAppServer(), {"should_abort": iter([False, False, True]).__next__})):
            with self.subTest(sandbox=fake.sandbox, options=bool(options)):
                _, run, _ = self.run_read(fake, **options)
                self.assertIs(run["process_exit_confirmed"], True)
                self.assertFalse(run["cleanup_pending"])

    def test_chat_accepts_the_next_message_after_a_codex_project_read(self):
        import tempfile as _tempfile
        from unittest.mock import MagicMock
        from core.agent_chat import AgentChatService
        runtime = CodexRuntime(self.exe)
        fakes = [FakeAppServer(), FakeAppServer()]
        for fake in fakes:
            fake.config = good_config(self.project.resolve())
        with _tempfile.TemporaryDirectory() as store, \
                patch.object(CodexRuntime, "_project_read_config", return_value=["-c", "x=1"]), \
                patch("core.codex_runtime.subprocess.Popen", side_effect=fakes), \
                patch("core.codex_runtime.bind_kill_on_close_job", return_value=True), \
                patch("core.codex_runtime.wait_for_owned_cleanup", return_value=0), \
                patch("core.codex_runtime.stop_process_tree", side_effect=lambda p, timeout=5: p.terminate()):
            from core.multi_agent_service import MultiAgentService
            with patch("core.multi_agent_service.CodexRuntime", return_value=runtime), \
                    patch("core.multi_agent_service.AntigravityRuntime"):
                service = MultiAgentService(projects=[{"id": "p1", "name": "Quartz", "path": str(self.project),
                                                       "protected": False}],
                                            squad_executable=__file__, codex_executable=__file__,
                                            antigravity_executable=__file__)
            service.codex = runtime
            runtime.probe = lambda force=False: {"ready": True, "authenticated": True, "error": ""}
            chat = AgentChatService(service, Path(store) / "chats.json")
            chat.set_project(chat.store.get_active()["id"], "p1")
            for question in ("README dosyasında ne yazıyor?", "requirements.txt içinde ne var?"):
                chat.send_message(question, agent="codex")  # second send raises if the stop receipt stays pending
                for _ in range(500):
                    if not chat.poll_active().get("active"):
                        break
                    time.sleep(0.01)
                self.assertFalse(chat.poll_active().get("active"))
            self.assertEqual(len([m for m in fakes if "turn/start" in m.methods()]), 2)

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
