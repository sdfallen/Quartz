"""Real temporary conversation storage; provider/desktop calls are mocked."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from core.agent_chat import AgentChatService


class PublicationIdentityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.chat = AgentChatService(MagicMock(), Path(folder.name) / 'conversations.json')
        self.cid = self.chat.store.get_active()['id']
        self.message = self.chat.store.append_message(self.cid, 'assistant', 'original', sender='codex')
        self.chat._active_turn = {'turn_id': 'owned-turn', 'conversation_id': self.cid,
            'message_id': self.message['id'], 'message_ids': [self.message['id']], 'status': 'running'}

    def test_wrong_conversation_cannot_receive_session_before_message_check(self):
        other = self.chat.store.create(title='Other', agent='codex')
        before = self.chat.store.get(other['id'])
        result = self.chat._publish_run_update(other['id'], self.message['id'], 'late output',
                    {'agent': 'codex', 'status': 'completed'}, provider='codex', session='wrong-session')
        self.assertFalse(result)
        self.assertEqual(self.chat.store.get(other['id']), before)
        self.assertEqual(self.chat.store.get(self.cid)['messages'][-1]['content'], 'original')

    def test_owned_conversation_keeps_streaming_and_session_persistence(self):
        self.assertTrue(self.chat._publish_run_update(self.cid, self.message['id'], 'new output',
                    {'agent': 'codex', 'status': 'running'}, provider='codex', session='owned-session'))
        conv = self.chat.store.get(self.cid)
        self.assertEqual(conv['sessions']['codex'], 'owned-session')
        self.assertEqual(conv['messages'][-1]['content'], 'new output')

    def test_stopped_turn_cannot_publish_into_its_own_conversation(self):
        self.chat._active_turn['cancel_requested'] = True
        before = self.chat.store.get(self.cid)
        self.assertFalse(self.chat._publish_run_update(self.cid, self.message['id'], 'late',
                    {'status': 'completed'}, provider='codex', session='late-session'))
        self.assertEqual(self.chat.store.get(self.cid), before)
