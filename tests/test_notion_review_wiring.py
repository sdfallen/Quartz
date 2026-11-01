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
        sync = source[source.index('  function syncNotionTools(payload, conversationId)'):]
        self.assertIn('window.QuartzNotionTools?.update(payload', sync[:400])
        load = source[source.index('  async function loadActiveConversation()'):]
        self.assertIn('syncNotionTools(data.notion_tools, currentConvId)', load)
        self.assertIn('if (currentConvId !== conv.id) window.QuartzNotionTools?.reset()', load)
        poll = source[source.index('  async function pollUiEvents()'):]
        self.assertIn('if (switched) window.QuartzNotionTools?.reset()', poll)
        self.assertIn('syncNotionTools(st.data.notion_tools, currentConvId)', poll)
        # During an active turn the UI polls chat_poll, so the permission card
        # must be driven from there too.
        turn = source[source.index('  async function pollAgentTurn()'):]
        self.assertIn('syncNotionTools(data.notion_tools, currentConvId)', turn[:900])
