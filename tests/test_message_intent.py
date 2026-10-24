import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import gui
from core.agent_chat import AgentChatService
from core.message_intent import message_intent
from tests import test_multi_agent_service as service_tests


class MessageIntentTests(unittest.TestCase):
    def test_discussion_is_not_an_operation_even_in_a_project(self):
        for text in ('Merhaba', 'Nasılsınız beyler?', 'Warband hakkında ne düşünüyorsun?',
                     'Gate B nedir?', 'NCO nasıl çalışıyor?', 'Nasıl test edebiliriz?',
                     'Bunu düzeltmek için ne önerirsin?', 'Sadece sohbet edelim',
                     'Araç kullanma; projeyi incele', 'Şu kodu açıkla: ```düzelt()```',
                     '"dosyayı aç" komutu ne demek?', 'Teşekkürler'):
            with self.subTest(text=text): self.assertEqual(message_intent(text), 'conversation')

    def test_real_requests_are_tasks(self):
        for text in ('Bu warband modunu inceleyin', 'Dosyayı güncelle', 'Kaynakları incele ve düzelt',
                     'Ekranı açıp incele', 'Oyunu test et', 'Logları kontrol edebilir misin?',
                     'Projeyi derle', 'Bir test dosyası oluştur', 'Kodu yaz', 'Kaynağı inceleyip açıkla'):
            with self.subTest(text=text): self.assertEqual(message_intent(text), 'task')

    def test_continuation_is_separate_from_a_new_task(self):
        for text in ('Devam et', 'Evet', 'Durdur', 'İptal et'):
            self.assertEqual(message_intent(text), 'continuation')

    def test_project_selection_cannot_turn_greeting_into_tools(self):
        api = gui.Api()
        with patch.object(api, 'natural_start') as start, patch.object(gui, 'ipc_send') as ipc:
            result = api.coordination_route('Merhaba, Warband hakkında konuşalım', 'c', 'aster-warband', {})
            self.assertFalse(result['data']['handled'])
            self.assertEqual(result['data']['intent'], 'conversation')
            start.assert_not_called(); ipc.assert_not_called()

    def test_greeting_does_not_instruct_or_stop_existing_task(self):
        api = gui.Api()
        api._natural = MagicMock()
        result = api.coordination_route('Sence profesyonel ordu nasıl olmalı?', 'c', 'aster-warband', {})
        self.assertFalse(result['data']['handled'])
        api._natural.instruct.assert_not_called(); api._natural.stop.assert_not_called()

    def test_explicit_no_tools_revokes_an_active_task(self):
        api = gui.Api()
        api._natural = MagicMock()
        api._natural.status.return_value = {'active': True}
        result = api.coordination_route('Araç kullanma, sadece sohbet edelim', 'c', 'aster-warband', {})
        self.assertEqual(result['data']['intent'], 'conversation')
        api._natural.stop.assert_called_once()

    def test_discussing_tools_or_quoting_a_stop_is_not_a_stop_instruction(self):
        for text in ('Araç kullanmak neden geciktiriyor?', '"araç kullanma" talimatı ne demek?'):
            api = gui.Api(); api._natural = MagicMock()
            result = api.coordination_route(text, 'c', 'aster-warband', {})
            self.assertEqual(result['data']['intent'], 'conversation')
            api._natural.stop.assert_not_called()

    def test_warband_real_request_still_uses_um(self):
        api = gui.Api()
        project = {'id':'aster-warband', 'workflow':'warband'}
        with patch.object(gui, 'ipc_send', return_value={'status':'ok', 'data':{'projects':[project]}}), \
             patch.object(api, 'natural_start', return_value={'status':'ok'}) as start:
            api.coordination_route('Kaynakları incele', 'c', 'aster-warband', {})
            start.assert_called_once()

    def test_full_permission_dropdown_does_not_grant_tools_to_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = MagicMock()
            chat = AgentChatService(agents, Path(directory) / 'chats.json')
            with patch('core.agent_chat.threading.Thread') as worker:
                chat.send_message('Merhaba', agent='codex', write=True, full_access=True)
            args = worker.call_args.kwargs['args']
            self.assertEqual(args[-3:], (False, False, False))
            self.assertTrue(chat._active_turn['conversation_only'])

    def test_text_runtime_isolated_no_resume_write_checkpoint_or_squad(self):
        service, runtime, _ = service_tests.MultiAgentServiceTests().make_service()
        service.projects._projects['test']['protected'] = True
        runtime.start.return_value = {'id':'text-run', 'status':'completed'}
        runtime.get.return_value = {'status':'completed'}
        with patch.object(service, '_start_writer') as writer, patch.object(service, '_squad') as squad:
            result = service.dispatch_codex('Merhaba', project_id='test', chat_mode=True,
                conversation_only=True, resume_thread_id='old-tools-session', model='chosen', effort='low')
        opts = runtime.start.call_args.kwargs
        self.assertTrue(opts['tool_guard']); self.assertEqual(opts['sandbox'], 'read-only')
        self.assertEqual(opts['model'], 'chosen'); self.assertNotIn('resume_thread_id', opts)
        self.assertNotEqual(Path(runtime.start.call_args.args[1]).resolve(), Path('.').resolve())
        writer.assert_not_called(); squad.assert_not_called()
        self.assertTrue(result['run']['conversation_only'])

    def test_no_tools_cannot_be_used_as_a_protected_writer_backdoor(self):
        service, runtime, _ = service_tests.MultiAgentServiceTests().make_service()
        for opts in ({'write':True}, {'full_access':True}, {'chat_mode':False}):
            with self.assertRaises(PermissionError):
                service.dispatch_codex('hello', conversation_only=True, **{'chat_mode':True, **opts})
        runtime.start.assert_not_called()

    def test_chat_ui_ignores_write_selector_for_conversation(self):
        self.assertIn("const conversationOnly = coordinated.data?.intent === 'conversation'", gui._HTML)
        self.assertIn("conversationOnly ? 'read-only'", gui._HTML)

    def test_simple_group_chat_is_one_parallel_round_with_no_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = MagicMock()
            agents.codex.probe.return_value = {'ready': True}
            for name in ('codex', 'antigravity'):
                runtime = getattr(agents, name)
                runtime.TERMINAL = {'completed', 'failed', 'cancelled'}
                runtime.get.return_value = {'id':name, 'status':'completed', 'result':'Selam', 'errors':[]}
                getattr(agents, 'dispatch_' + name).return_value = {'run': {'id':name}}
            agents.check_squad_connection.return_value = {'connected': False}
            chat = AgentChatService(agents, Path(directory) / 'chats.json')
            chat.send_message('Selam beyler', agent='collaboration')
            deadline = time.monotonic() + 3
            while chat.poll_active().get('active') and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertFalse(chat.poll_active().get('active'))
            for name in ('codex', 'antigravity'):
                dispatch = getattr(agents, 'dispatch_' + name)
                dispatch.assert_called_once()
                self.assertTrue(dispatch.call_args.kwargs['conversation_only'])


if __name__ == '__main__': unittest.main()
