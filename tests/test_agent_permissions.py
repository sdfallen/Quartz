"""Permission regressions. No real model/CLI/UI process is launched."""
import tempfile
import threading
import time
import zipfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.agent_chat import AgentChatService
from core.multi_agent_service import MultiAgentService


class AgentPermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with patch('core.multi_agent_service.CodexRuntime'), patch('core.multi_agent_service.AntigravityRuntime'):
            self.service = MultiAgentService(projects=[{'id':'test', 'path':self.tmp.name}])
        self.service.codex.probe.return_value = {'ready':True}
        self.service.antigravity.probe.return_value = {'ready':True}
        self.service.codex.TERMINAL = {'completed','failed','cancelled'}
        self.service.antigravity.TERMINAL = {'completed','failed','cancelled'}
        self.service.codex.start.return_value = {'id':'mock-codex'}
        self.service.antigravity.start.return_value = {'id':'mock-agy'}
        self.service.check_squad_connection = MagicMock(return_value={'connected':False})

    def tearDown(self):
        self.tmp.cleanup()

    def writer_guards(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch('core.multi_agent_service.create_checkpoint', return_value={
            'status':'snapshot', 'complete':True, 'archive':'mock.zip', 'ref':'mock.zip'}))
        stack.enter_context(patch('core.multi_agent_service.snapshot_workspace_files', return_value={'files':{}, 'warning':''}))
        stack.enter_context(patch('core.multi_agent_service.threading.Thread'))
        return stack

    def test_chat_project_codex_keeps_sandbox_and_checkpoint(self):
        with self.writer_guards(), patch('core.multi_agent_service.create_checkpoint', return_value={
                'status':'snapshot', 'complete':True, 'archive':'mock.zip'}) as checkpoint:
            result = self.service.dispatch_codex('test', chat_mode=True, write=True, confirm_write=True)
        self.assertEqual(self.service.codex.start.call_args.kwargs['sandbox'], 'workspace-write')
        checkpoint.assert_called_once()
        self.assertEqual(result['run']['checkpoint']['archive'], 'mock.zip')

    def test_real_checkpoint_precedes_fake_local_writer_and_lock_releases(self):
        from core.workspace_checkpoint import create_checkpoint
        with tempfile.TemporaryDirectory() as backups:
            target=Path(self.tmp.name)/'fixture.txt';target.write_text('before',encoding='utf-8')
            def local_write(*args,**kwargs):
                target.write_text('after',encoding='utf-8')
                return {'id':'local-fake','status':'completed'}
            self.service.codex.start.side_effect=local_write
            self.service.codex.get.return_value={'id':'local-fake','status':'completed','files_changed':[]}
            with patch('core.multi_agent_service.create_checkpoint',side_effect=lambda root:create_checkpoint(root,backup_root=backups)):
                result=self.service.dispatch_codex('test',chat_mode=True,write=True,confirm_write=True)
                for _ in range(100):
                    if not self.service._writer_status(self.tmp.name)['locked']:break
                    time.sleep(.01)
            self.assertFalse(self.service._writer_status(self.tmp.name)['locked'])
            self.assertEqual(target.read_text(encoding='utf-8'),'after')
            with zipfile.ZipFile(result['run']['checkpoint']['archive']) as archive:
                self.assertEqual(archive.read('files/fixture.txt'),b'before')
            self.assertIn(str(target.resolve()),self.service.get_run('local-fake')['files_changed'])

    def test_explicit_full_codex_uses_guarded_full_mode(self):
        with self.writer_guards():
            self.service.dispatch_codex('test', chat_mode=True, full_access=True, confirm_write=True)
        self.assertEqual(self.service.codex.start.call_args.kwargs['sandbox'], 'danger-full-access')
        self.assertTrue(self.service._writer_status(self.tmp.name)['locked'])

    def test_explicit_full_agy_uses_checkpoint_and_shared_lock(self):
        with self.writer_guards():
            result = self.service.dispatch_antigravity('test', chat_mode=True, full_access=True, confirm_write=True)
            with self.assertRaises(RuntimeError):
                self.service.dispatch_codex('second', chat_mode=True, write=True, confirm_write=True)
        self.assertTrue(self.service.antigravity.start.call_args.kwargs['full_access'])
        self.assertIn('checkpoint', result['run'])
        self.service.codex.start.assert_not_called()

    def test_project_agy_rejected_before_probe_or_start(self):
        with self.assertRaises(PermissionError):
            self.service.dispatch_antigravity('test', chat_mode=True, write=True, confirm_write=True)
        self.service.antigravity.probe.assert_not_called()
        self.service.antigravity.start.assert_not_called()

    def test_readonly_needs_no_checkpoint_or_write_lock(self):
        with patch('core.multi_agent_service.create_checkpoint') as checkpoint:
            self.service.dispatch_codex('test', chat_mode=True)
        checkpoint.assert_not_called()
        self.assertFalse(self.service._writer_status(self.tmp.name)['locked'])

    def test_all_unverified_checkpoint_results_prevent_launch_and_release_lock(self):
        for checkpoint in ({'status':'not_git'}, {'status':'error', 'warning':'disk error'},
                           {'status':'snapshot', 'complete':False, 'archive':'x'},
                           {'status':'git', 'complete':True}):
            with self.subTest(checkpoint=checkpoint), patch('core.multi_agent_service.create_checkpoint', return_value=checkpoint):
                with self.assertRaises(RuntimeError):
                    self.service.dispatch_codex('test', chat_mode=True, write=True, confirm_write=True)
                self.assertFalse(self.service._writer_status(self.tmp.name)['locked'])
        self.service.codex.start.assert_not_called()

    def test_failed_start_releases_writer_reservation(self):
        self.service.codex.start.side_effect = OSError('mock start failure')
        with self.writer_guards(), self.assertRaises(OSError):
            self.service.dispatch_codex('test', chat_mode=True, write=True, confirm_write=True)
        self.assertFalse(self.service._writer_status(self.tmp.name)['locked'])

    def test_full_writer_blocks_other_project_and_nested_project(self):
        project = self.service.projects.selected()
        with self.writer_guards():
            self.service._start_writer('codex', project, lambda **kw:{'id':'one'}, sandbox='danger-full-access')
            other = {'path':str(Path(self.tmp.name).parent / 'other-project')}
            with self.assertRaises(RuntimeError):
                self.service._start_writer('antigravity', other, lambda:{'id':'two'})

    def test_project_writer_blocks_nested_writer(self):
        project = self.service.projects.selected()
        with self.writer_guards():
            self.service._start_writer('codex', project, lambda:{'id':'one'})
            with self.assertRaises(RuntimeError):
                self.service._start_writer('antigravity', {'path':str(Path(self.tmp.name) / 'child')}, lambda:{'id':'two'})

    def test_confirmation_must_be_true_not_truthy_string(self):
        for dispatch in (self.service.dispatch_codex, self.service.dispatch_antigravity):
            with self.assertRaises(PermissionError):
                dispatch('test', full_access=True, confirm_write='false', chat_mode=True)

    def bubble_chat(self):
        chat = AgentChatService.__new__(AgentChatService)
        chat.store = MagicMock()
        chat.store.preferences.return_value = {"response_detail": "short"}
        chat.store.get.return_value = {'sessions':{'antigravity':'old', 'codex':'old'}}
        chat.store.get_agent_model.return_value = {}
        chat.agent_service = self.service
        chat._lock = threading.RLock()
        chat._active_turn = {'status':'running', 'conversation_id':'c', 'message_id':'m',
                             'message_ids':['m'], 'run_ids':[]}
        chat._is_turn_cancelled = MagicMock(return_value=False)
        chat._set_turn_progress = MagicMock()
        chat._extract_metrics = MagicMock(return_value={})
        return chat

    def test_readonly_agy_denial_never_escalates_or_retries(self):
        chat = self.bubble_chat()
        chat._stream_antigravity_run = MagicMock(return_value=({'errors':['permission denied']}, 'failed'))
        self.service.dispatch_antigravity = MagicMock(return_value={'run':{'id':'fake'}})
        with self.assertRaises(RuntimeError):
            chat._execute_antigravity_bubble('c','m','test','test',False,False)
        self.service.dispatch_antigravity.assert_called_once()
        self.assertFalse(self.service.dispatch_antigravity.call_args.kwargs['full_access'])
        self.assertFalse(self.service.dispatch_antigravity.call_args.kwargs['write'])

    def test_group_agy_command_denial_retries_from_text_without_escalating(self):
        chat = self.bubble_chat()
        chat._stream_antigravity_run = MagicMock(side_effect=[
            ({'errors':['Antigravity permission policy denied: command']}, 'failed'),
            ({'result':'Codex görüşündeki eksik nokta budur.'}, 'completed'),
        ])
        self.service.dispatch_antigravity = MagicMock(side_effect=[
            {'run':{'id':'first'}}, {'run':{'id':'review-retry'}}])
        answer = chat._execute_antigravity_bubble(
            'c', 'm', 'Codex kanıtı: test özeti', 'test', False, False,
            use_session=False, base_meta={'collaboration':True},
        )
        self.assertIn('proje dosyaları bağımsız doğrulanmadı', answer)
        self.assertIn('Codex görüşündeki eksik nokta', answer)
        self.assertEqual(self.service.dispatch_antigravity.call_count, 2)
        self.assertEqual(chat._stream_antigravity_run.call_args.args[2], 'review-retry')
        self.assertEqual(chat._stream_antigravity_run.call_args.args[3]['run_id'], 'review-retry')
        retry_call = self.service.dispatch_antigravity.call_args
        self.assertIn('Do not call any tool, command', retry_call.args[0])
        self.assertIn('Codex kanıtı: test özeti', retry_call.args[0])
        for call in self.service.dispatch_antigravity.call_args_list:
            self.assertFalse(call.kwargs['write'])
            self.assertFalse(call.kwargs['confirm_write'])
            self.assertFalse(call.kwargs['full_access'])
        self.assertFalse(retry_call.kwargs['conversation_id'])

    def test_group_agy_repeated_denial_stops_after_one_safe_retry(self):
        chat = self.bubble_chat()
        chat._stream_antigravity_run = MagicMock(return_value=(
            {'errors':['Antigravity permission policy denied: command']}, 'failed'))
        self.service.dispatch_antigravity = MagicMock(return_value={'run':{'id':'fake'}})
        with self.assertRaisesRegex(RuntimeError, 'permission policy denied'):
            chat._execute_antigravity_bubble(
                'c', 'm', 'Codex kanıtı', 'test', False, False,
                use_session=False, base_meta={'collaboration':True},
            )
        self.assertEqual(self.service.dispatch_antigravity.call_count, 2)

    def test_readonly_agy_stale_session_retries_without_permissions(self):
        chat = self.bubble_chat()
        chat._stream_antigravity_run = MagicMock(side_effect=[({'errors':['stale session']}, 'failed'), ({'result':'ok'}, 'completed')])
        self.service.dispatch_antigravity = MagicMock(side_effect=[
            {'run':{'id':'first'}}, {'run':{'id':'agy-retry'}}])
        self.assertEqual(chat._execute_antigravity_bubble('c','m','test','test',False,False), 'ok')
        self.assertEqual(self.service.dispatch_antigravity.call_count, 2)
        self.assertEqual(chat._stream_antigravity_run.call_args.args[3]['run_id'], 'agy-retry')
        retry = self.service.dispatch_antigravity.call_args.kwargs
        self.assertFalse(retry['write']); self.assertFalse(retry['confirm_write']); self.assertFalse(retry['full_access'])

    def test_readonly_codex_denial_does_not_retry(self):
        chat=self.bubble_chat()
        chat._stream_codex_run=MagicMock(return_value=({'errors':['permission denied']},'failed'))
        self.service.dispatch_codex=MagicMock(return_value={'run':{'id':'fake'}})
        with self.assertRaises(RuntimeError):
            chat._execute_codex_bubble('c','m','test','test',False,False)
        self.service.dispatch_codex.assert_called_once()

    def test_readonly_codex_stale_session_stays_readonly(self):
        chat=self.bubble_chat()
        chat._stream_codex_run=MagicMock(side_effect=[({'errors':['stale session']},'failed'),({'result':'ok'},'completed')])
        self.service.dispatch_codex=MagicMock(side_effect=[
            {'run':{'id':'first'}}, {'run':{'id':'codex-retry'}}])
        self.assertEqual(chat._execute_codex_bubble('c','m','test','test',False,False),'ok')
        self.assertEqual(self.service.dispatch_codex.call_count,2)
        self.assertEqual(chat._stream_codex_run.call_args.args[3]['run_id'],'codex-retry')
        retry=self.service.dispatch_codex.call_args.kwargs
        self.assertFalse(retry['write']);self.assertFalse(retry['confirm_write']);self.assertFalse(retry['full_access'])

    def test_full_write_failure_not_automatically_replayed(self):
        chat = self.bubble_chat()
        chat._stream_antigravity_run = MagicMock(return_value=({'errors':['stale session']}, 'failed'))
        self.service.dispatch_antigravity = MagicMock(return_value={'run':{'id':'fake'}})
        with self.assertRaises(RuntimeError):
            chat._execute_antigravity_bubble('c','m','test','test',True,True,full_access=True)
        self.service.dispatch_antigravity.assert_called_once()

    def test_inner_typeerror_does_not_dispatch_again(self):
        chat = self.bubble_chat()
        self.service.dispatch_antigravity = MagicMock(side_effect=TypeError('internal failure'))
        with self.assertRaises(TypeError):
            chat._execute_antigravity_bubble('c','m','test','test',False,False)
        self.service.dispatch_antigravity.assert_called_once()

    def test_prompt_does_not_claim_full_access_for_project_permission(self):
        prompt = AgentChatService._build_single_chat_prompt('codex','test',[],set(),True)
        self.assertNotIn('Tam Yetki aktif', prompt)
        self.assertIn('yalnız', prompt.lower())

    def test_send_unconfirmed_write_does_not_append_history(self):
        chat = AgentChatService(self.service, Path(self.tmp.name) / 'conversation.json')
        before = chat.store.get_active()['messages']
        with self.assertRaises(PermissionError):
            chat.send_message('Dosyayı güncelle',write=True,confirm_write=False)
        self.assertEqual(chat.store.get_active()['messages'], before)

    def test_group_writer_finishes_before_readonly_reviewer(self):
        chat = AgentChatService(self.service, Path(self.tmp.name) / 'conversation.json')
        conv = chat.store.get_active();cid = conv['id']
        user = chat.store.append_message(cid,'user','test',sender='user')
        first = chat.store.append_message(cid,'assistant','',sender='codex')
        chat._active_turn={'status':'running','message_ids':[first['id']], 'user_message_id':user['id']}
        chat._run_mutual_evaluation_round = MagicMock()
        order=[]
        def writer(*args, **kwargs):
            order.append('write')
            self.assertTrue(args[4]); self.assertFalse(kwargs['full_access'])
            time.sleep(.02); order.append('written');return 'writer result'
        def review(*args, **kwargs):
            self.assertEqual(order[-1], 'written')
            self.assertFalse(args[4]); self.assertFalse(args[5]); self.assertFalse(kwargs.get('full_access',False))
            self.assertIn('command/terminal aracı çağırma', args[2])
            self.assertIn('writer result', args[2])
            order.append('review');return 'review result'
        chat._execute_codex_bubble=MagicMock(side_effect=writer)
        chat._execute_antigravity_bubble=MagicMock(side_effect=review)
        chat._run_collaboration_turn(cid,first['id'],'test','test',write=True,confirm_write=True)
        self.assertEqual(order,['write','written','review'])
        self.assertEqual(chat._active_turn['status'],'completed')

    def test_failed_group_writer_not_reported_complete_by_successful_review(self):
        chat=AgentChatService(self.service,Path(self.tmp.name)/'conversation.json')
        cid=chat.store.get_active()['id']
        first=chat.store.append_message(cid,'assistant','',sender='codex')
        chat._active_turn={'status':'running','message_ids':[first['id']]}
        chat._execute_codex_bubble=MagicMock(side_effect=RuntimeError('mock write failed'))
        chat._execute_antigravity_bubble=MagicMock(return_value='review')
        chat._run_mutual_evaluation_round=MagicMock()
        chat._run_collaboration_turn(cid,first['id'],'test','test',write=True,confirm_write=True)
        self.assertEqual(chat._active_turn['status'],'failed')


class ChatPermissionIPCTests(unittest.TestCase):
    def server(self):
        import main
        server = main.IPCServer.__new__(main.IPCServer)
        server._get_agent_chat=MagicMock()
        return server

    def test_project_and_full_are_separate(self):
        for level in ('project','full'):
            server=self.server()
            server._dispatch_action({'action':'chat_send','data':{'message':'test','permission_level':level,'confirm_write':True}})
            kwargs=server._get_agent_chat.return_value.send_message.call_args.kwargs
            self.assertTrue(kwargs['write']); self.assertEqual(kwargs['full_access'],level=='full')

    def test_readonly_overrides_legacy_write_flag(self):
        server=self.server()
        server._dispatch_action({'action':'chat_send','data':{'message':'test','permission_level':'read-only','write':True}})
        kwargs=server._get_agent_chat.return_value.send_message.call_args.kwargs
        self.assertFalse(kwargs['write']);self.assertFalse(kwargs['full_access'])

    def test_write_requires_confirmation_not_server_synthesized_consent(self):
        for value in (False,None,'true','false',1):
            server=self.server()
            with self.assertRaises(PermissionError):
                server._dispatch_action({'action':'chat_send','data':{'message':'test','permission_level':'project','confirm_write':value}})
            server._get_agent_chat.assert_not_called()

    def test_legacy_write_defaults_to_project_not_full(self):
        server=self.server()
        server._dispatch_action({'action':'chat_send','data':{'message':'test','write':True,'confirm_write':True}})
        self.assertFalse(server._get_agent_chat.return_value.send_message.call_args.kwargs['full_access'])

    def test_gui_defaults_to_readonly(self):
        import gui
        self.assertIn('<option value="read-only" selected>',gui._HTML)
        with patch('gui.ipc_send') as ipc:
            gui.Api.__new__(gui.Api).chat_send('test')
        data=ipc.call_args.args[1]
        self.assertEqual(data['permission_level'],'read-only');self.assertFalse(data['confirm_write'])
