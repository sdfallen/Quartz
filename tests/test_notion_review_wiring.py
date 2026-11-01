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

    def test_shipped_ui_consumes_status_and_resets_on_conversation_switch(self):
        source = gui._HTML
        load = source[source.index('  async function loadActiveConversation()'):]
        self.assertIn('window.QuartzNotionTools?.update(data.notion_tools', load)
        self.assertIn('if (currentConvId !== conv.id) window.QuartzNotionTools?.reset()', load)
        poll = source[source.index('  async function pollUiEvents()'):]
        self.assertIn('if (switched) window.QuartzNotionTools?.reset()', poll)
        self.assertIn('window.QuartzNotionTools?.update(st.data.notion_tools', poll)
