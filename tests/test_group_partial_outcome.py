import tempfile
from pathlib import Path
import time
import unittest
from unittest.mock import MagicMock, patch
from core.agent_chat import AgentChatService


class GroupPartialOutcomeTests(unittest.TestCase):
    def test_second_round_failure_is_not_hidden_by_first_round_success(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MagicMock(); service.check_squad_connection.return_value = {'connected':False}
            chat = AgentChatService(service, Path(directory)/'conversations.json')
            with patch.object(chat, '_execute_codex_bubble', return_value='Codex response'), \
                 patch.object(chat, '_execute_antigravity_bubble', side_effect=['first response', RuntimeError('second round timeout')]):
                chat.send_message('İkiniz bu yaklaşımı değerlendirin', agent='collaboration')
                deadline = time.monotonic()+3
                while chat._active_turn.get('status') == 'running' and time.monotonic() < deadline: time.sleep(.02)
            turn = chat._active_turn
            self.assertEqual(turn['status'], 'partial')
            self.assertEqual(turn['participant_statuses'], {'codex':'completed', 'antigravity':'failed'})
            self.assertEqual(chat.poll_active()['outcome']['goal_verdict'], 'PARTIAL')
            chat._diagnostics.close()

    def test_first_round_failure_does_not_run_a_second_round(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MagicMock(); service.check_squad_connection.return_value = {'connected':False}
            chat = AgentChatService(service, Path(directory)/'conversations.json')
            with patch.object(chat, '_execute_codex_bubble', return_value='Codex response'), \
                 patch.object(chat, '_execute_antigravity_bubble', side_effect=RuntimeError('quota')), \
                 patch.object(chat, '_run_mutual_evaluation_round') as second:
                chat.send_message('İkiniz bu yaklaşımı değerlendirin', agent='collaboration')
                deadline=time.monotonic()+3
                while chat._active_turn.get('status') == 'running' and time.monotonic()<deadline: time.sleep(.02)
                second.assert_not_called()
            self.assertEqual(chat._active_turn['status'], 'partial')
            chat._diagnostics.close()
