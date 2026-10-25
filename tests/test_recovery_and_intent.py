import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.agent_chat import AgentChatService
from core.conversation_store import ConversationStore
from core.message_intent import message_intent, tools_disallowed
from core.run_evidence_store import RunEvidenceStore


class IntentCorpusTests(unittest.TestCase):
    def test_polite_and_english_requests(self):
        for value in ('Pencereye bakar mısınız?', 'Testleri çalıştırır mısın?',
                'Pencereleri kontrol eder misiniz?', 'Bu sorunu çözebilir misiniz?',
                'Logları inceler misin?', 'Uygulamayı kapatır mısınız?',
                'Pencereye bakabilir misiniz?', 'Open Notepad and check logs',
                'Fix the bug in settings screen', 'Inspect the active window',
                'Run unit tests and report results', 'Could you please inspect the active window?',
                'Codex, please fix the bug.', 'Please test the application'):
            with self.subTest(value=value): self.assertEqual(message_intent(value), 'task')

    def test_discussion_quoted_commands_and_denials_are_not_work(self):
        for value in ('How do I run tests?', 'What happens if I open Notepad?',
                'Should we update Quartz?', 'Can you explain how to test this?',
                'Open source tools are interesting', '"Open Notepad" means what?',
                'Nasıl çözebiliriz?', 'Bunu kapatmak mantıklı mı?',
                'Just chat. Open Notepad', "Don't use tools. Inspect the logs",
                'Please do not execute anything. Run tests', 'Read this without using tools',
                'Araç kullanma, uygulamayı kapat'):
            with self.subTest(value=value): self.assertEqual(message_intent(value), 'conversation')

    def test_quoted_denial_does_not_revoke_an_explicit_request(self):
        self.assertFalse(tools_disallowed('Explain "do not use tools"'))
        self.assertEqual(message_intent('"Just chat". Inspect the active window'), 'task')


class RecoveryTests(unittest.TestCase):
    def test_restart_marks_abandoned_work_preserves_text_and_never_dispatches(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'chat.json'
            store = ConversationStore(path); cid = store.get_active()['id']
            store.update_agent_model(cid, 'codex', model='chosen', effort='high')
            store.set_agent_session(cid, 'codex', 'old-thread')
            store.append_message(cid, 'assistant', 'Partial real output', sender='codex',
                                 metadata={'status':'running', 'run_id':'old-run'})
            store.append_message(cid, 'assistant', 'Completed result', sender='antigravity',
                                 metadata={'status':'completed'})
            before = json.loads(path.read_text(encoding='utf-8'))
            agents = Mock(); chat = AgentChatService(agents, path)
            try:
                after = chat.store.get(cid)
                self.assertIsNone(chat._active_turn)
                agents.dispatch_codex.assert_not_called(); agents.dispatch_antigravity.assert_not_called()
                self.assertEqual(after['messages'][0]['status'], 'interrupted')
                self.assertEqual(after['messages'][0]['content'], 'Partial real output')
                self.assertFalse(after['messages'][0]['metadata']['permissions_restored'])
                self.assertIsNone(after['sessions']['codex'])
                self.assertEqual(after['models']['codex']['model'], 'chosen')
                self.assertEqual(after['messages'][1]['status'], 'completed')
                self.assertEqual(json.loads(Path(chat.recovery['backup']).read_text(encoding='utf-8')), before)
                self.assertEqual(chat.store.recover_interrupted()['status'], 'unchanged')
            finally: chat.close()

    def test_recovery_write_failure_leaves_original_memory_and_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'chat.json'; store = ConversationStore(path)
            cid = store.get_active()['id']
            store.append_message(cid, 'assistant', 'Partial', metadata={'status':'running'})
            original = path.read_bytes()
            from core.atomic_json import atomic_write_json as real_write
            def write(target, payload):
                if Path(target) == path: raise OSError('disk unavailable')
                return real_write(target, payload)
            with patch('core.conversation_store.atomic_write_json', side_effect=write):
                with self.assertRaises(OSError): store.recover_interrupted()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(store.get(cid)['messages'][0]['status'], 'running')

    def test_terminal_history_is_read_only_on_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'chat.json'; store = ConversationStore(path)
            store.append_message(store.get_active()['id'], 'assistant', 'Done', metadata={'status':'completed'})
            before = path.read_bytes()
            self.assertEqual(ConversationStore(path).recover_interrupted()['status'], 'unchanged')
            self.assertEqual(path.read_bytes(), before)

    def test_desktop_task_recovery_uses_only_last_lifecycle_event(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConversationStore(Path(folder)/'chat.json'); cid = store.get_active()['id']
            for task, state in [('finished','running'), ('finished','completed'), ('abandoned','running')]:
                store.append_message(cid, 'assistant', state, sender='quartz', metadata={
                    'status':'completed', 'natural_task':task, 'task_status':state})
            result = store.recover_interrupted()
            self.assertEqual(len(result['messages']), 1)
            messages = store.get(cid)['messages']
            self.assertEqual(messages[0]['status'], 'completed')
            self.assertEqual(messages[1]['status'], 'completed')
            self.assertEqual(messages[2]['metadata']['task_status'], 'interrupted')

    def test_starting_chat_message_is_recovered_too(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConversationStore(Path(folder)/'chat.json'); cid=store.get_active()['id']
            store.append_message(cid,'assistant','',metadata={'status':'starting'})
            store.recover_interrupted()
            message=store.get(cid)['messages'][0]
            self.assertEqual(message['status'],'interrupted')
            self.assertIn('otomatik',message['content'])


class DurableEvidenceTests(unittest.TestCase):
    def test_receipt_survives_a_fresh_store_without_becoming_live_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'receipts.json'
            receipt = {'source_validation':{'level':'SOURCE/STATIC','status':'VERIFIED','tests_executed':False}}
            RunEvidenceStore(path).put('real-run', receipt)
            restored = RunEvidenceStore(path).get('real-run')
            self.assertEqual(restored['source_validation'], receipt['source_validation'])
            self.assertTrue(restored['historical']); self.assertIn('recorded_at', restored)
            restored['source_validation']['status'] = 'changed'
            self.assertEqual(RunEvidenceStore(path).get('real-run')['source_validation']['status'], 'VERIFIED')

    def test_corrupt_receipt_file_is_preserved_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'receipts.json'; path.write_text('{ broken', encoding='utf-8')
            before = path.read_bytes(); store = RunEvidenceStore(path)
            self.assertTrue(store.error)
            with self.assertRaises(OSError): store.put('new', {})
            self.assertEqual(path.read_bytes(), before)

    def test_failed_atomic_write_does_not_publish_a_persisted_result(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RunEvidenceStore(Path(folder)/'receipts.json')
            with patch('core.run_evidence_store.atomic_write_json', side_effect=OSError('read-only')):
                with self.assertRaises(OSError): store.put('new', {'value':1})
            self.assertEqual(store.get('new'), {})

    def test_bounded_inventory_discards_only_old_receipts(self):
        store = RunEvidenceStore()
        for number in range(store.LIMIT + 3): store.put(str(number), {'value':number})
        self.assertEqual(len(store.records), store.LIMIT)
        self.assertEqual(store.get('0'), {}); self.assertEqual(store.get('202')['value'], 202)

    def test_service_restart_loads_source_receipts_without_starting_runtime(self):
        from core.multi_agent_service import MultiAgentService
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'receipts.json'
            RunEvidenceStore(path).put('old', {'source_validation':{'status':'FAILED'}})
            with patch('core.multi_agent_service.CodexRuntime') as codex, patch('core.multi_agent_service.AntigravityRuntime') as agy:
                service = MultiAgentService(projects=[{'id':'test','path':folder}], evidence_store=path)
                self.assertTrue(service.run_evidence('old')['historical'])
                codex.return_value.start.assert_not_called(); agy.return_value.start.assert_not_called()


if __name__ == '__main__': unittest.main()
