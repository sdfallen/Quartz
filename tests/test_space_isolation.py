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


class SecurityAlertsStayInWorkspaceTests(unittest.TestCase):
    """Eos's findings are work: a medium one never lands in a Sohbet (live 24 Nov)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = AgentChatService(MagicMock(), Path(self.temp.name) / "chats.json")
        self.store = self.service.store
        self.task = self.store.create("Görev", project_id="p", space="work")
        self.chat = self.store.create("Sohbet", project_id="p", space="chat")
        self.store.select(self.chat["id"])

    def tearDown(self):
        self.temp.cleanup()

    def alert(self, severity):
        self.service._post_security_alert({"id": "a-" + severity, "severity": severity,
                                           "title": "Geçici klasörden program", "detail": "x.exe"})

    def texts(self, conv):
        return [m["content"] for m in self.store.get(conv["id"])["messages"]]

    def security_log(self):
        logs = [c for c in self.store.list() if self.store.get(c["id"]).get("kind") == "security"]
        self.assertEqual(len(logs), 1, "one log, reused")
        return self.store.get(logs[0]["id"])

    def test_a_medium_alert_goes_to_eos_own_workspace_log(self):
        # Live 24 Nov: 84 alerts had filled the user's 'Yeni Görev' task.
        self.alert("medium")
        self.alert("medium")
        log = self.security_log()
        self.assertEqual((log["title"], log["space"]), ("Eos · Güvenlik", "work"))
        self.assertEqual(sum("Güvenlik uyarısı (Orta)" in m["content"] for m in log["messages"]), 2)
        self.assertEqual(self.texts(self.chat), [])
        self.assertEqual(self.texts(self.task), [])
        self.assertEqual(self.store.get_active()["id"], self.chat["id"], "the user stays where they are")

    def test_a_high_alert_still_reaches_the_open_conversation(self):
        self.alert("high")
        self.assertTrue(any("Güvenlik uyarısı (Yüksek)" in t for t in self.texts(self.chat)))

    def test_the_log_survives_a_restart_and_is_reused(self):
        self.alert("medium")
        first = self.security_log()["id"]
        again = AgentChatService(MagicMock(), self.store.path)
        self.assertEqual(again.store.special_conversation("security", "Eos · Güvenlik"), first)

    def test_the_environment_check_is_hidden_in_sohbet(self):
        self.assertIn(':root[data-space="chat"] #envHealth { display: none !important; }', gui._HTML)


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
