"""Fatum (Claude) orchestrates desktop tasks: divides the work, follows it, never touches the screen."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import natural_desktop
from core.claude_runtime import COLLABORATOR_MCP_TOOLS, ClaudeRuntime
from core.desktop_broker import DesktopBroker
from core.desktop_mcp import handle
from core.natural_desktop import NaturalDesktopTask
from tests.test_claude_runtime import feed, record_for, runtime
from tests.test_desktop_broker import FakeBackend


class Runtime:
    TERMINAL = {"completed", "failed", "cancelled"}
    executable = "test-runtime.exe"

    def __init__(self, ready=True):
        self.states, self.started, self.ready = {}, [], ready

    def probe(self):
        return {"ready": self.ready}

    def start(self, prompt, workspace, **opts):
        rid = "run" + str(len(self.started) + 1)
        self.started.append((prompt, workspace, opts))
        self.states[rid] = {"id": rid, "status": "running", "result": "Plan: Fides yazsın, Eos doğrulasın."}
        return self.states[rid]

    def get(self, rid):
        return self.states[rid]

    def cancel(self, rid):
        self.states[rid]["status"] = "cancelled"


class OrchestratorTaskTests(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_coordination import MODELS
        self.models = MODELS
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = FakeBackend()
        self.broker = DesktopBroker(self.backend)
        self.desktop = SimpleNamespace(broker=self.broker, windows=self.backend.windows)
        self.events = []

    def tearDown(self):
        self.temp.cleanup()

    def start(self, claude):
        self.codex, self.gemini, self.claude = Runtime(), Runtime(), claude
        self.squad = Mock()
        self.squad.initialized = True
        self.squad.create_task.return_value = {"id": "task"}
        self.squad.receive.return_value = []
        task = NaturalDesktopTask(self.desktop, lambda *a: self.events.append(a),
                                  factories={"codex": lambda: self.codex, "antigravity": lambda: self.gemini,
                                             "claude": lambda: claude},
                                  squad_factory=lambda p: self.squad, evidence_root=self.root / "ev")
        with patch("core.natural_desktop.subprocess.run", return_value=SimpleNamespace(returncode=0)), \
             patch("core.natural_desktop.ensure_antigravity_tool_grants"), patch("core.natural_desktop.write_operator_hooks"):
            task.start("Codex not defterine hesap makinesi yaz. Gemini sonucu kontrol et.",
                       {"path": str(self.root)}, "chat", self.models)
        return task

    def test_fatum_starts_first_with_coordination_tools_only(self):
        task = self.start(Runtime())
        try:
            prompt, _, opts = self.claude.started[0]
            self.assertEqual(opts["sandbox"], "none")
            self.assertIn("ORCHESTRATOR", prompt)
            self.assertIn("hesap makinesi", prompt)
            tokens = {opts["desktop_connection"]["token"], self.codex.started[0][2]["desktop_connection"]["token"],
                      self.gemini.started[0][2]["desktop_connection"]["token"]}
            self.assertEqual(len(tokens), 3)
            self.assertIn("Fatum (Claude) divides the work", self.codex.started[0][0])
            self.assertIn(("quartz-claude-" + task.job["id"][:10],), [c.args[:1] for c in self.squad.join.call_args_list])
            self.assertEqual(self.squad.join.call_args_list[2].kwargs.get("client"), "claude")
            context = task.call(task.tokens["claude"], {"name": "task_context", "arguments": {}})
            self.assertEqual(context["role"], "orchestrator")
            self.assertEqual(context["team"]["operator"], "Fides")
        finally:
            task.stop()

    def test_fatum_cannot_touch_the_screen(self):
        task = self.start(Runtime())
        try:
            token = task.tokens["claude"]
            for request in ({"name": "desktop_request_access", "arguments": {"handles": [1], "reason": "Not Defteri"}},
                            {"name": "desktop_observe", "arguments": {}},
                            {"name": "jarvis_input", "arguments": {"action": "type", "text": "x"}}):
                with self.subTest(tool=request["name"]):
                    try:
                        result = task.call(token, request)
                    except (PermissionError, ValueError):
                        continue
                    self.assertNotEqual(result.get("status"), "approved")
                    self.assertTrue(result.get("error") or result.get("status") != "ok", result)
            self.assertFalse(self.broker.status()["active"])
        finally:
            task.stop()

    def test_fatum_message_reaches_both_agents(self):
        task = self.start(Runtime())
        try:
            task.call(task.tokens["claude"], {"name": "task_message",
                                               "arguments": {"text": "Fides yazsın; Eos 12+3 sonucunu doğrulasın."}})
            recipients = {c.args[1] for c in self.squad.send.call_args_list}
            self.assertEqual(recipients, {task.agent_ids["codex"], task.agent_ids["antigravity"]})
            self.assertTrue(any(e[1] == "claude" for e in self.events))
        finally:
            task.stop()

    def test_task_waits_briefly_for_the_verdict_then_ends(self):
        task = self.start(Runtime())
        try:
            self.codex.states["run1"]["status"] = "completed"
            self.gemini.states["run1"]["status"] = "completed"
            time.sleep(.8)
            self.assertTrue(task.status()["active"])  # Fatum is still writing its verdict
            self.claude.states["run1"]["status"] = "completed"
            deadline = time.time() + 3
            while task.status()["active"] and time.time() < deadline:
                time.sleep(.1)
            self.assertFalse(task.status()["active"])
            self.assertEqual(task.job["status"], "completed")  # Fatum is not a participant of the outcome
        finally:
            task.stop()

    def test_grace_expiry_ends_the_task(self):
        with patch.object(natural_desktop, "ORCHESTRATOR_GRACE_SECONDS", 0.3):
            task = self.start(Runtime())
            try:
                self.codex.states["run1"]["status"] = "completed"
                self.gemini.states["run1"]["status"] = "completed"
                deadline = time.time() + 4
                while task.status()["active"] and time.time() < deadline:
                    time.sleep(.1)
                self.assertFalse(task.status()["active"])
                self.assertEqual(self.claude.states["run1"]["status"], "cancelled")
            finally:
                task.stop()

    def test_without_claude_the_pair_still_works(self):
        task = self.start(Runtime(ready=False))
        try:
            self.assertIsNone(task.job["orchestrator"])
            self.assertEqual(len(self.codex.started), 1)
            self.assertTrue(any("Fatum bu göreve bağlanamadı" in str(e[2]) for e in self.events))
            self.assertNotIn("Fatum (Claude) divides the work", self.codex.started[0][0])
        finally:
            task.stop()


class CollaboratorServerTests(unittest.TestCase):
    def test_collaborator_server_lists_and_calls_only_coordination_tools(self):
        listed = [t["name"] for t in handle({"method": "tools/list"}, collaborator=True)["tools"]]
        self.assertEqual(sorted(listed), ["task_context", "task_message", "task_wait"])
        with self.assertRaises(ValueError):
            handle({"method": "tools/call", "params": {"name": "desktop_act", "arguments": {}}},
                   transport=lambda p: {"ok": True}, collaborator=True)
        self.assertGreater(len(handle({"method": "tools/list"})["tools"]), 3)  # the operator server is unchanged

    def test_claude_command_loads_only_the_collaborator_server_without_the_token(self):
        rt = runtime()
        args = rt.build_args("none", desktop=True)
        config = json.loads(args[args.index("--mcp-config") + 1])
        server = config["mcpServers"]["quartz_desktop"]
        self.assertEqual(server["args"][-1], "--collaborator-server")
        self.assertNotIn("env", server)
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertEqual(args[args.index("--allowedTools") + 1].split(","), list(COLLABORATOR_MCP_TOOLS))
        plain = rt.build_args("none")
        self.assertEqual(json.loads(plain[plain.index("--mcp-config") + 1]), {"mcpServers": {}})

    def test_desktop_profile_needs_the_tool_less_sandbox(self):
        rt = runtime()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(PermissionError):
                rt.start("x", folder, sandbox="web", desktop_connection={"url": "http://127.0.0.1:1/tool", "token": "t"})
        self.assertEqual(rt._runs, {})

    def test_init_must_show_exactly_the_collaborator_server_and_tools(self):
        good = {"type": "system", "subtype": "init", "session_id": "s", "tools": list(COLLABORATOR_MCP_TOOLS),
                "mcp_servers": [{"name": "quartz_desktop", "status": "connected"}], "permissionMode": "dontAsk"}
        cases = (({}, True),
                 ({"mcp_servers": [{"name": "quartz_desktop", "status": "failed"}]}, False),
                 ({"mcp_servers": []}, False),
                 ({"tools": [*COLLABORATOR_MCP_TOOLS, "mcp__quartz_desktop__desktop_act"]}, False))
        for extra, ok in cases:
            with self.subTest(extra=extra):
                rt = runtime()
                rec = record_for(rt, "none")
                rec["_expected_tools"] = sorted(COLLABORATOR_MCP_TOOLS)
                rec["_expected_servers"] = ["quartz_desktop"]
                stop = feed(rt, {**good, **extra}, {"type": "result", "subtype": "success", "is_error": False, "result": "x"})
                self.assertEqual(rec["tools_verified"], ok)
                self.assertEqual(stop.called, not ok)


if __name__ == "__main__":
    unittest.main()
