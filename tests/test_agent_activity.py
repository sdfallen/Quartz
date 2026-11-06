import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock

from core.agent_activity import describe_activity
from core.agent_chat import AgentChatService


def codex(*events): return {"events": list(events)}
def agy(*events): return {"events": list(events)}


class DescribeActivityTests(unittest.TestCase):
    def test_codex_events_become_short_turkish_lines(self):
        self.assertEqual(describe_activity("codex", codex({"type": "turn.started"})), "Düşünüyor…")
        self.assertEqual(describe_activity("codex", codex({"type": "item.started", "item": {"type": "command_execution", "command": "python -m pytest tests"}})),
                         "Komut çalıştırıyor: python -m pytest tests")
        self.assertEqual(describe_activity("codex", codex({"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": r"C:\Users\x\proj\core\app.py"}]}})),
                         "Dosya düzenliyor: app.py")
        self.assertEqual(describe_activity("codex", codex({"type": "item.started", "item": {"type": "mcp_tool_call", "server": "quartz", "tool": "desktop_observe"}})),
                         "Ekranı inceliyor")

    def test_antigravity_tools_show_the_leaf_path_or_query(self):
        step = lambda tool, **p: {"event": "step_update", "step_update": {"tool_name": tool, "state": "RUNNING", "tool_info": {"parameters": p}}}
        self.assertEqual(describe_activity("antigravity", agy(step("view_file", AbsolutePath="/home/u/secret-dir/agent_chat.py"))), "Dosya okuyor: agent_chat.py")
        self.assertEqual(describe_activity("antigravity", agy(step("grep_search", Query="describe_activity"))), "Kodda arıyor: describe_activity")
        self.assertEqual(describe_activity("antigravity", agy(step("mcp_quartz-desktop_desktop_act"))), "Pencerede işlem yapıyor")
        self.assertEqual(describe_activity("antigravity", agy(step("some_new_tool"))), "Araç kullanıyor: some_new_tool")
        self.assertEqual(describe_activity("antigravity", agy(step("quartz__desktop_act"))), "Pencerede işlem yapıyor")
        self.assertEqual(describe_activity("antigravity", agy({"event": "step_update", "step_update": {"text_delta": "Mer"}})), "Yanıt yazıyor…")

    def test_long_or_secret_bearing_commands_are_cut(self):
        line = describe_activity("codex", codex({"type": "item.started", "item": {"type": "command_execution",
            "command": "curl -H Authorization:Bearer-abc https://example.org/" + "x" * 80}}))
        self.assertNotIn("Bearer-abc", line)
        self.assertLessEqual(len(line), len("Komut çalıştırıyor: ") + 44)

    def test_latest_meaningful_event_wins_and_unknown_input_is_none(self):
        run = codex({"type": "item.started", "item": {"type": "reasoning"}}, {"type": "item.started", "item": {"type": "command_execution", "command": "ls"}},
                    {"type": "item.completed", "item": {"type": "unknown"}})
        self.assertEqual(describe_activity("codex", run), "Komut çalıştırıyor: ls")
        self.assertIsNone(describe_activity("notion", run))
        self.assertIsNone(describe_activity("codex", {"events": ["not a dict"]}))
        self.assertIsNone(describe_activity("codex", None))


class NoteActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.chat = AgentChatService(MagicMock(), Path(self.temp.name) / "c.json")
        self.chat._active_turn = {"status": "running", "message_ids": ["m1"], "message_id": "m1",
                                  "agent_progress": {"codex": {"message_id": "m1", "status": "running"}}}

    def tearDown(self):
        self.chat._diagnostics.close(); self.temp.cleanup()

    def test_activity_and_short_trail_live_only_on_the_running_turn(self):
        for command in ("ls", "git status", "ls", "pytest", "python a.py", "python b.py"):
            self.chat._note_activity("m1", "codex", codex({"type": "item.started", "item": {"type": "command_execution", "command": command}}))
        entry = self.chat._active_turn["agent_progress"]["codex"]
        self.assertEqual(entry["activity"], "Komut çalıştırıyor: python b.py")
        self.assertEqual(len(entry["activity_trail"]), 4)
        self.assertEqual(entry["activity_trail"][-1], entry["activity"])

    def test_other_message_stopped_turn_or_unknown_agent_change_nothing(self):
        run = codex({"type": "turn.started"})
        self.chat._note_activity("other", "codex", run)
        self.chat._note_activity("m1", "antigravity", run)
        self.chat._active_turn["status"] = "cancelled"
        self.chat._note_activity("m1", "codex", run)
        self.assertNotIn("activity", self.chat._active_turn["agent_progress"]["codex"])
        self.assertNotIn("antigravity", self.chat._active_turn["agent_progress"])


if __name__ == "__main__":
    unittest.main()
