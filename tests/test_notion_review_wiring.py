import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from core.agent_chat import AgentChatService
import gui


class ReviewWiringTests(unittest.TestCase):
    def test_chat_status_never_advertises_unimplemented_remote_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            service = MagicMock()
            chat = AgentChatService(service, Path(folder) / 'conversation.json')
            status = chat.status()
            self.assertEqual(status['notion_tools']['availability'], 'unavailable')
            self.assertEqual(status['notion_tools']['capabilities'], [])
            self.assertIsNone(status['notion_tools']['task'])
            service.dispatch_notion.assert_not_called()

    def test_archived_notion_tools_do_not_mount_in_main_chat(self):
        self.assertNotIn('syncNotionTools(', gui._HTML)
        self.assertNotIn('quartz-notion-tools', gui._HTML)
        self.assertNotIn('data-notion-permission', gui._HTML)
