from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from core.agent_chat import AgentChatService
from core.local_ipc import request_token
from core.repair_cycle import TestObservation
from core.repair_plan_entry import python_candidates
import main


class RepairPlanEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'test_value.py').write_text('raise RuntimeError("must not execute")\n',encoding='utf-8')
        (self.root/'expected.json').write_text('{"total":118}',encoding='utf-8')
        self.service=MagicMock()
        self.project={'id':'p','path':str(self.root),'protected':False}
        self.service.projects.get.side_effect=lambda pid: dict(self.project)
        self.service.pending_writer_runs.return_value=[]
        self.service.get_run.return_value={'process_exit_confirmed':True}
        self.chat=AgentChatService(self.service,self.root/'chat.json')
        self.cid=self.chat.store.create('fixture',agent='codex',project_id='p')['id']
        self.entry=self.chat.repair_plan_entry
        self.now=10.0
        self.entry.clock=lambda:self.now

    def tearDown(self):
        self.chat._diagnostics.close(); self.chat._environment_health.close(); self.temp.cleanup()

    def preview(self,**kwargs):
        data={'conversation_id':self.cid,'provider':'codex','test_files':['test_value.py'],
              'support_files':['expected.json'],'expected_tests':1,'python_executable':sys.executable,'max_repairs':2}
        data.update(kwargs)
        return self.entry.preview(**data)

    def register(self,preview=None):
        preview=preview or self.preview()
        return self.entry.register(preview['preview_id'],confirm=True)

    def test_preview_binds_explicit_dependency_directory_to_registered_adapter(self):
        with tempfile.TemporaryDirectory() as external:
            site_dir = Path(external) / 'site-packages'
            site_dir.mkdir()
            preview = self.preview(python_site_packages=str(site_dir))
            self.assertEqual(preview['python_site_packages'], str(site_dir.resolve()))
            self.assertEqual(self.chat._repair_plans, {})
            self.register(preview)
            self.assertEqual(self.chat._host_test_adapters[self.cid].python_site_packages,
                             str(site_dir.resolve()))

    def test_preview_never_starts_code_or_saves_plan(self):
        with patch('subprocess.Popen') as popen,patch('subprocess.run') as run:
            view=self.preview()
        popen.assert_not_called(); run.assert_not_called()
        self.assertEqual([p['role'] for p in view['files']],['support','test'])
        self.assertEqual(view['project_id'],'p')
        self.assertIsNone(self.entry.summary(self.cid))
        self.assertEqual(self.chat._repair_plans,{})
        self.service.dispatch_codex.assert_not_called()

    def test_confirmation_exact_true_one_use_and_ttl(self):
        view=self.preview()
        for value in (False,1,'true',None):
            with self.subTest(value=value),self.assertRaises(PermissionError):
                self.entry.register(view['preview_id'],confirm=value)
        summary=self.register(view)
        self.assertEqual((summary['status'],summary['files_count'],summary['support_count']),('ready',2,1))
        with self.assertRaises(ValueError): self.register(view)
        self.entry.clear(self.cid)
        view=self.preview(); self.now+=600
        with self.assertRaises(ValueError): self.register(view)
        self.assertEqual(self.chat._repair_plans,{})

    def test_hash_model_project_and_python_changes_rejected(self):
        for change in ('file','support','model','project','python'):
            with self.subTest(change=change):
                view=self.preview()
                if change in {'file','support'}:
                    path=self.root/('test_value.py' if change=='file' else 'expected.json')
                    path.write_text(path.read_text()+'\n')
                elif change=='model':
                    self.chat.store.update_agent_model(self.cid,'codex',model='other')
                elif change=='project':
                    self.project['path']=str(self.root/'missing')
                if change=='python':
                    with patch.object(self.entry,'_python_stat',return_value=(-1,-1)):
                        with self.assertRaises(ValueError): self.register(view)
                else:
                    with self.assertRaises((ValueError,PermissionError,OSError)): self.register(view)
                self.project['path']=str(self.root)
                self.assertEqual(self.chat._repair_plans,{})
                with self.assertRaises(ValueError): self.register(view)

    def test_running_worker_and_cleanup_reject_registration_and_clear(self):
        for turn in ({'status':'running'},{'status':'cancelling'},{'status':'completed','worker_pending':True},
                     {'status':'cancelled','stop_receipt':{'status':'pending'}}):
            with self.subTest(turn=turn):
                view=self.preview(); self.chat._active_turn=turn
                with self.assertRaises(RuntimeError): self.register(view)
                with self.assertRaises(RuntimeError): self.entry.clear(self.cid)
                self.chat._active_turn=None
        view=self.preview()
        self.chat._host_test_adapters['old']=type('Pending',(),{'cleanup_pending':True})()
        with self.assertRaises(RuntimeError): self.register(view)
        with self.assertRaises(RuntimeError): self.entry.clear(self.cid)

    def test_protected_invalid_paths_counts_and_multi_agent_are_rejected(self):
        for changes in ({'test_files':['../escape.py']},{'expected_tests':True},{'test_files':[]},
                        {'support_files':['test_value.py']},{'max_repairs':4},{'provider':'collaboration'}):
            with self.subTest(changes=changes),self.assertRaises((ValueError,PermissionError)):
                self.preview(**changes)
        self.project['protected']=True
        with patch('core.host_test_runner.HostUnittestAdapter._manifest') as read:
            with self.assertRaises(PermissionError): self.preview()
        read.assert_not_called()

    def test_new_preview_revokes_old_and_conversation_change_rejects(self):
        first=self.preview(); second=self.preview()
        with self.assertRaises(ValueError): self.register(first)
        self.chat.store.create('other',agent='codex',project_id='p')
        with self.assertRaises(ValueError): self.register(second)

    def test_clear_and_consumed_plan_status_lifecycle(self):
        self.register()
        self.chat._active_turn={'conversation_id':self.cid,'status':'running'}
        self.assertEqual(self.entry.summary(self.cid)['status'],'running')
        self.chat._repair_plans.pop(self.cid)
        self.assertEqual(self.entry.summary(self.cid)['status'],'running')
        self.chat._active_turn={'conversation_id':self.cid,'status':'completed'}
        self.assertIsNone(self.entry.summary(self.cid))
        self.register(); self.entry.clear(self.cid)
        self.assertIsNone(self.entry.summary(self.cid))
        self.assertEqual(self.chat._host_test_adapters,{})

    def test_second_manifest_capture_race_is_rejected(self):
        view=self.preview(); original=self.chat.register_host_unittest_plan
        def changed(*args,**kwargs):
            (self.root/'expected.json').write_text('changed')
            return original(*args,**kwargs)
        with patch.object(self.chat,'register_host_unittest_plan',side_effect=changed):
            with self.assertRaises(ValueError): self.register(view)
        self.assertEqual(self.chat._repair_plans,{})
        self.assertEqual(self.chat._host_test_adapters,{})

    def test_ready_scope_change_blocks_send_before_dispatch(self):
        self.register(); self.project['path']=str(self.root/'missing')
        with self.assertRaises((PermissionError,OSError)):
            self.chat.send_message('Dosyayı düzelt', 'codex', self.cid, write=True, confirm_write=True)
        self.service.dispatch_codex.assert_not_called()

    def test_chat_status_exposes_summary_without_private_preview(self):
        self.register()
        with patch.object(self.chat._diagnostics,'read',return_value=({},{})), \
             patch.object(self.chat._environment_health,'read',return_value={}), \
             patch.object(self.chat,'_notion_tools_payload',return_value={}):
            result=self.chat.status()['repair_plan']
        self.assertEqual(result['expected_tests'],1)
        self.assertNotIn('preview_id',result); self.assertNotIn('project_path',result)

    def test_frozen_candidates_are_passive_and_do_not_suggest_quartz(self):
        fake=self.root/'Quartz.exe'; fake.write_bytes(b'not-python')
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(fake)),patch('subprocess.Popen') as popen:
            candidates=python_candidates()
        self.assertNotIn(str(fake),candidates)
        self.assertTrue(all(Path(p).is_absolute() for p in candidates)); popen.assert_not_called()

    def test_ipc_authenticated_actions_and_strict_fields(self):
        server=main.IPCServer(MagicMock())
        with patch.object(server,'_get_agent_chat',return_value=self.chat):
            req={'action':'repair_plan_preview','data':{'conversation_id':self.cid,'provider':'codex',
                'test_files':['test_value.py'],'expected_tests':1,'python_executable':sys.executable}}
            self.assertEqual(server._dispatch(req)['status'],'error')
            req['auth']=request_token()
            reply=server._dispatch(req)
            self.assertEqual(reply['status'],'ok',reply)
            pid=reply['data']['preview_id']
            self.assertEqual(server._dispatch({'auth':request_token(),'action':'repair_plan_register',
                'data':{'preview_id':pid,'confirm':True}})['data']['status'],'ready')
            self.assertIsNone(server._dispatch({'auth':request_token(),'action':'repair_plan_clear',
                'data':{'conversation_id':self.cid}})['data'])
            req['data']['command']='dangerous'
            self.assertEqual(server._dispatch(req)['status'],'error')
