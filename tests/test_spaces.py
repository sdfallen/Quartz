"""Sohbet / Workspace: two spaces with different rules (user request 14 Nov)."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.conversation_store import ConversationStore
from core.space_policy import normalize, space_of, space_rule, team_chat_rule, voice
from tests.test_team_turn import TeamRun, make_chat


class PolicyTests(unittest.TestCase):
    def test_unknown_or_missing_space_is_workspace(self):
        for value in (None, "", "garip", {"space": "x"}):
            self.assertEqual(space_of(value if isinstance(value, dict) else {"space": value}), "work")
        self.assertEqual(normalize("CHAT"), "chat")

    def test_each_space_has_its_own_register(self):
        self.assertIn("SOHBET ALANI", space_rule("chat"))
        self.assertIn("WORKSPACE", space_rule("work"))
        self.assertIn("SOHBET MODU", team_chat_rule("chat"))
        self.assertIn("KISA YANIT", team_chat_rule("work"))
        for agent in ("claude", "codex", "antigravity"):
            self.assertIn("Sohbet alanındasın", voice(agent, "chat"))
            self.assertIn("Workspace'tesin", voice(agent, "work"))
        self.assertIn("orkestratör", voice("claude", "work"))


class StoreTests(unittest.TestCase):
    def test_space_is_stored_listed_and_defaults_for_old_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "c.json"
            store = ConversationStore(path)
            chat = store.create(space="chat")
            work = store.create()
            self.assertEqual((chat["space"], work["space"]), ("chat", "work"))
            listed = {c["id"]: c["space"] for c in store.list()}
            self.assertEqual((listed[chat["id"]], listed[work["id"]]), ("chat", "work"))
            self.assertEqual(store.latest_in_space("chat")["id"], chat["id"])
            # An older file has no space at all.
            data = json.loads(path.read_text(encoding="utf-8"))
            for record in data["conversations"].values() if isinstance(data.get("conversations"), dict) else data["conversations"]:
                record.pop("space", None)
            path.write_text(json.dumps(data), encoding="utf-8")
            old = ConversationStore(path)
            self.assertEqual({c["space"] for c in old.list()}, {"work"})
            self.assertIsNone(old.latest_in_space("chat"))


class ChatServiceTests(unittest.TestCase):
    def test_open_space_reuses_the_latest_or_creates_one(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            first = chat.open_space("chat")
            self.assertEqual(first["space"], "chat")
            self.assertEqual(first["agent"], "collaboration")
            work = chat.open_space("work")
            self.assertEqual(work["space"], "work")
            self.assertEqual(chat.open_space("chat")["id"], first["id"])
            self.assertEqual(chat.store.get_active()["id"], first["id"])
            chat._diagnostics.close()

    def test_sohbet_never_starts_work_and_offers_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            conversation = chat.new_conversation(agent="collaboration", space="chat")
            run = TeamRun(chat)
            run.run("Not defterine bir hesap makinesi kodu yaz", write=True, confirm_write=True, full_access=True)
            messages = chat.store.get(conversation["id"])["messages"]
            chat._diagnostics.close()
        self.assertTrue(run.calls)
        self.assertTrue(all(c["tool_less"] and not c["write"] for c in run.calls))
        self.assertTrue(all("SOHBET MODU" in c["prompt"] and "Sohbet alanındasın" in c["prompt"] for c in run.calls))
        user = next(m for m in messages if m["role"] == "user")
        self.assertEqual(user["metadata"]["space_hint"], "work")

    def test_workspace_small_talk_is_formal(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            chat.new_conversation(agent="collaboration", space="work")
            run = TeamRun(chat)
            run.run("Selam, nasılsınız?")
            chat._diagnostics.close()
        self.assertTrue(all("KISA YANIT" in c["prompt"] and "Workspace'tesin" in c["prompt"] for c in run.calls))

    def test_chat_space_message_has_no_workspace_hint_for_small_talk(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            conversation = chat.new_conversation(agent="collaboration", space="chat")
            TeamRun(chat).run("Bugün çok yorgunum")
            messages = chat.store.get(conversation["id"])["messages"]
            chat._diagnostics.close()
        self.assertNotIn("space_hint", next(m for m in messages if m["role"] == "user")["metadata"])

    def test_space_rule_reaches_single_agent_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            conversation = chat.new_conversation(agent="claude", space="chat")
            prompt = chat._communication_prompt(conversation["id"], "X")
            chat._diagnostics.close()
        self.assertIn("SOHBET ALANI", prompt)

    def test_desktop_task_in_sohbet_never_rings(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"NVIDIA_API_KEY": ""}):
            chat = make_chat(directory)
            cid = chat.new_conversation(space="chat")["id"]
            chat.coordination_message(cid, "user", "Hesap makinesi yaz, bitince haber ver", {})
            chat.coordination_message(cid, "quartz", "Başladı.", {"natural_task": "t", "task_status": "running"})
            chat.coordination_message(cid, "quartz", "Bitti.", {"natural_task": "t", "task_status": "completed", "final": True})
            time.sleep(.3)
            messages = chat.store.get(cid)["messages"]
            chat._diagnostics.close()
        self.assertFalse(any((m.get("metadata") or {}).get("report") for m in messages))


if __name__ == "__main__":
    unittest.main()
