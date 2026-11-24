"""Sohbet and Workspace are separate (user request 24 Nov 2026).

"Sohbet ekranında hâlâ Projeler arayüzü var ve Sohbet arayüzü daraltılmış görünüyor.
Sohbet ve Proje arayüzlerini birbirinden izole et."
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import gui
import main
from core.agent_chat import AgentChatService


class SpaceIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = AgentChatService(MagicMock(), Path(self.temp.name) / "chats.json")
        self.store = self.service.store

    def tearDown(self):
        self.temp.cleanup()

    def test_deleting_the_open_sohbet_stays_in_sohbet(self):
        task = self.store.create("Görev", project_id="p", space="work")
        other_chat = self.store.create("Başka sohbet", project_id="q", space="chat")
        chat = self.store.create("Sohbet", project_id="p", space="chat")
        self.store.select(chat["id"])
        result = self.service.delete_conversation(chat["id"], confirmed=True)
        self.assertEqual(result["active_conversation"]["id"], other_chat["id"],
                         "the next Sohbet, even from another project; never the Workspace task")
        self.assertNotEqual(result["active_conversation"]["id"], task["id"])

    def test_deleting_the_last_sohbet_opens_a_new_sohbet(self):
        self.store.create("Görev", project_id="p", space="work")
        chat = self.store.create("Sohbet", project_id="p", space="chat")
        self.store.select(chat["id"])
        active = self.service.delete_conversation(chat["id"], confirmed=True)["active_conversation"]
        self.assertEqual(active["space"], "chat")
        self.assertEqual(active["messages"], [])

    def test_workspace_cleanup_leaves_the_projects_sohbets_alone(self):
        a = self.store.create("A", project_id="p", space="work")
        b = self.store.create("B", project_id="p", space="work")
        chat = self.store.create("Sohbet", project_id="p", space="chat")
        self.store.select(a["id"])
        result = self.service.delete_project_conversations("p", [a["id"], b["id"]], confirmed=True, space="work")
        self.assertEqual(result["deleted_count"], 2)
        self.assertEqual(self.store.get(chat["id"])["title"], "Sohbet")
        self.assertEqual(result["active_conversation"]["space"], "work")

    def test_sohbet_cleanup_covers_every_sohbet_and_no_task(self):
        task = self.store.create("Görev", project_id="p", space="work")
        one = self.store.create("Bir", project_id="p", space="chat")
        two = self.store.create("İki", project_id="q", space="chat")
        chats = [c["id"] for c in self.store.list() if c["space"] == "chat"]
        self.assertTrue({one["id"], two["id"]} <= set(chats))
        with self.assertRaises(ValueError):
            self.service.delete_space_conversations("chat", [one["id"]], confirmed=True)  # stale list
        with self.assertRaises(PermissionError):
            self.service.delete_space_conversations("chat", chats)
        result = self.service.delete_space_conversations("chat", chats, confirmed=True)
        self.assertEqual(result["deleted_count"], len(chats))
        self.assertEqual(self.store.get(task["id"])["title"], "Görev")
        self.assertFalse(set(chats) & {c["id"] for c in self.store.list()})

    def test_ipc_space_cleanup_needs_confirmation(self):
        server = main.IPCServer(MagicMock())
        server._agent_chat = self.service
        chat = self.store.create("Sohbet", project_id="p", space="chat")
        ids = [c["id"] for c in self.store.list() if c["space"] == "chat"]
        with self.assertRaises(PermissionError):
            server._dispatch_action({"action": "chat_delete_space", "data": {"space": "chat", "conversation_ids": ids}})
        result = server._dispatch_action({"action": "chat_delete_space", "data": {
            "space": "chat", "conversation_ids": ids, "confirmed": True}})
        self.assertEqual(result["data"]["deleted_count"], len(ids))
        self.assertIn(chat["id"], ids)


class SpaceIsolationUiTests(unittest.TestCase):
    def test_sohbet_hides_the_project_picker_and_cleans_only_sohbets(self):
        html = gui._HTML
        self.assertIn('class="side-section space-work-only" id="projectSection"', html)
        self.assertIn("'Bütün sohbetleri temizle'", html)
        self.assertIn("requestChatDeletion(navigationConversations.slice(), '*chat')", html)
        self.assertIn("chat_delete_space('chat', ids, true)", html)

    def test_sohbet_column_is_not_squeezed(self):
        css = gui._HTML
        self.assertNotIn(':root[data-space="chat"] .chat { max-width: 760px', css)
        self.assertIn(':root[data-space="chat"] .chat { padding-inline: max(16px, calc((100% - var(--measure)) / 2)); }', css)


if __name__ == "__main__":
    unittest.main()
