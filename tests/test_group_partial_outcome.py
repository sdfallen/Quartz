import tempfile
from pathlib import Path
import time
import unittest
from unittest.mock import MagicMock, patch
from core.agent_chat import AgentChatService


class GroupPartialOutcomeTests(unittest.TestCase):
    def test_failed_second_round_squad_delivery_is_not_a_completed_group(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MagicMock(); service.check_squad_connection.return_value = {'connected':True}
            service.squad_create_group_task.return_value = {'id':'test-squad'}
            service.squad_receive_messages.return_value = []
            codex_sends = [0]
            def send(sender, *args, **kwargs):
                if sender == 'quartz-codex':
                    codex_sends[0] += 1
                    if codex_sends[0] == 2: raise RuntimeError('Squad delivery failed')
            service.squad_send_message.side_effect = send
            chat=AgentChatService(service,Path(directory)/'conversations.json')
            with patch.object(chat,'_execute_codex_bubble',return_value='response'), \
                 patch.object(chat,'_execute_antigravity_bubble',return_value='response'):
                chat.send_message('İkiniz bu yaklaşımı değerlendirin',agent='collaboration')
                deadline=time.monotonic()+3
                while chat._active_turn.get('status') == 'running' and time.monotonic()<deadline: time.sleep(.02)
            self.assertEqual(codex_sends[0],2)
            self.assertEqual(chat._active_turn['status'],'partial')
            chat._diagnostics.close()

    def test_partial_turn_is_recorded_on_the_owner_message_for_history(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MagicMock(); service.check_squad_connection.return_value = {'connected':False}
            chat = AgentChatService(service, Path(directory)/'conversations.json')
            with patch.object(chat, '_execute_codex_bubble', return_value='Codex response'), \
                 patch.object(chat, '_execute_antigravity_bubble', side_effect=['first response', RuntimeError('second round timeout')]):
                chat.send_message('İkiniz bu yaklaşımı değerlendirin', agent='collaboration')
                deadline = time.monotonic()+3
                while chat._active_turn.get('status') == 'running' and time.monotonic() < deadline: time.sleep(.02)
            cid = chat._active_turn['conversation_id']
            messages = chat.store.get(cid)['messages']
            owners = [m for m in messages if (m.get('metadata') or {}).get('turn_status')]
            self.assertEqual(len(owners), 1)
            self.assertEqual(owners[0]['metadata']['turn_status'], 'partial')
            self.assertEqual(owners[0]['metadata']['participants']['antigravity'], 'failed')
            enriched = [dict(m, metadata=dict(m.get('metadata') or {})) for m in messages]
            chat._enrich_messages(enriched)
            outcome = next(m for m in enriched if m['id'] == owners[0]['id'])['metadata']['outcome']
            self.assertEqual(outcome['goal_verdict'], 'PARTIAL')
            self.assertEqual(outcome['participants']['antigravity'], 'failed')
            chat._diagnostics.close()

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
