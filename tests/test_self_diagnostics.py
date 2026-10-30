"""Self-inspection behavior; fixture bytes are never executed as applications."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from core.self_diagnostics import SelfDiagnosticsService, safe_member
from core.rea_adapter import ReaAdapter


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'app'; self.root.mkdir()
        for name in SelfDiagnosticsService.REQUIRED:
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
        self.manifest()
        self.service = SelfDiagnosticsService(self.root, Path(self.temp.name)/'reports')
        self.addCleanup(self.service.shutdown)

    def manifest(self):
        files = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.rglob('*') if p.is_file() and p.name != 'release-manifest.json'}
        (self.root/'release-manifest.json').write_text(json.dumps({'files':files}))

    def finish(self, job):
        end = time.monotonic()+5
        while time.monotonic()<end:
            state = self.service.status(job['id'])
            if state['state'] != 'running': return state
            time.sleep(.01)
        self.fail('diagnostics did not settle')

    def test_real_hash_match_is_partial_when_rea_skipped(self):
        result = self.finish(self.service.start(include_rea=False))
        self.assertEqual(result['state'],'completed')
        self.assertEqual(result['verdict'],'PARTIAL')
        manifest=next(x for x in result['checks'] if x['id']=='manifest')
        self.assertEqual(manifest['status'],'PASS')
        self.assertEqual(manifest['evidence']['compared'],len(self.service.REQUIRED))
        self.assertTrue(Path(result['report_path']).is_file())

    def test_mismatch_is_failure_not_automatic_repair(self):
        exe=self.root/'Quartz.exe';exe.write_bytes(b'changed')
        result=self.finish(self.service.start(False))
        self.assertEqual(result['verdict'],'FAIL')
        check=next(c for c in result['checks'] if c['id']=='manifest')
        self.assertEqual(check['evidence']['mismatches'],['Quartz.exe'])
        self.assertEqual(exe.read_bytes(),b'changed')

    def test_manifest_absence_is_not_false_pass(self):
        (self.root/'release-manifest.json').unlink()
        result=self.finish(self.service.start(False))
        self.assertEqual(result['verdict'],'PARTIAL')
        self.assertEqual(next(c for c in result['checks'] if c['id']=='manifest')['status'],'NOT_TESTED')

    def test_manifest_cannot_direct_reads_to_secrets_or_outside_root(self):
        private=self.root/'.env';private.write_text('do-not-read-this-value')
        for name in ('.env','../other/private','C:/WarbandIsland/map.txt','_internal/.gemini/oauth_creds.json'):
            with self.subTest(name=name):
                (self.root/'release-manifest.json').write_text(json.dumps({'files':{name:'0'*64}}))
                result=self.finish(self.service.start(False))
                self.assertEqual(result['state'],'failed')
                self.assertEqual(result['verdict'],'UNKNOWN')
                self.assertNotIn('do-not-read-this-value',json.dumps(result))
                self.assertIsNone(result['report_path'])

    def test_source_mode_does_not_inspect_another_installed_application(self):
        (self.root/'Quartz.exe').unlink()
        self.service.rea=Mock()
        result=self.finish(self.service.start())
        self.assertEqual(result['verdict'],'PARTIAL')
        self.assertEqual(result['checks'][0]['status'],'NOT_TESTED')
        self.service.rea.inspect.assert_not_called()

    def test_polling_and_second_start_do_not_block_or_duplicate_worker(self):
        entered=threading.Event()
        def inspect(*args,**kwargs):
            entered.set(); kwargs['event'].wait(2)
            return {'status':'UNKNOWN','message':'cancelled','used':True}
        self.service.rea=Mock(inspect=inspect)
        job=self.service.start()
        self.assertTrue(entered.wait(2))
        began=time.monotonic()
        second=self.service.start()
        self.assertEqual(second['id'],job['id'])
        self.assertLess(time.monotonic()-began,.1)
        self.service.cancel(job['id'])
        result=self.finish(job)
        self.assertEqual(result['state'],'cancelled')
        self.assertNotEqual(result['verdict'],'PASS')
        self.assertIsNone(result['report_path'])

    def test_poll_returns_detached_snapshot(self):
        result=self.finish(self.service.start(False))
        result['checks'].clear()
        self.assertTrue(self.service.status(result['id'])['checks'])

    def test_persistence_failure_never_claims_complete(self):
        with patch('core.self_diagnostics.atomic_write_json',side_effect=OSError('private-token-in-error')):
            result=self.finish(self.service.start(False))
        self.assertEqual(result['state'],'failed')
        self.assertNotIn('private-token-in-error',json.dumps(result))

    def test_rea_missing_does_not_install_or_fail_local_checks(self):
        with patch('core.rea_adapter.ReaAdapter.discover',side_effect=FileNotFoundError):
            result=self.finish(self.service.start())
        self.assertEqual(result['state'],'completed')
        self.assertEqual(result['verdict'],'PARTIAL')
        self.assertFalse(result['rea_used'])

    def test_member_paths_reject_link_and_dot_escape(self):
        for name in ('../outside','/outside','_internal/../../outside','_internal\\outside','_internal/.env'):
            with self.subTest(name=name),self.assertRaises(ValueError):safe_member(self.root,name)


class ReaBoundaryTests(unittest.TestCase):
    @staticmethod
    def real_shape():
        digest='a'*64
        return {'summary':{'subject':{'format':'pyinstaller','digest':{'sha256':digest}},'normalized_result':{
            'kind':'summary','parent_operation':'inspect_artifact','artifact':{'sha256':digest},'summary':{
                'manifest':{'root_sha256':digest,'root_format':'pyinstaller','node_count':8},
                'root_format_metadata':{'kind':'pyinstaller','entry_count':5},
                'available_counts':{'integrity_contradictions':0},
                'available_hash_status_counts':{'verified':7,'mismatched':0,'unavailable':0,'not-hashed':0},
                'source_complete':True,'source_coverage':{'status':'complete'}}}}}

    def test_known_node_engine_boundaries(self):
        for version in ('v22.23.4','v24.22.1','v26.12.1','v26.13.0','v27.0.0'):
            self.assertTrue(ReaAdapter.node_supported(version))
        for version in ('v22.23.3','v24.22.0','v26.7.0','v23.5.0','unavailable'):
            self.assertFalse(ReaAdapter.node_supported(version))

    def test_invalid_tool_receipt_cannot_fall_back_to_same_modified_script(self):
        with tempfile.TemporaryDirectory() as directory:
            local=Path(directory)/'Quartz/tools/rea'
            entry=local/'node_modules/rea-agents/scripts/rea.mjs'
            entry.parent.mkdir(parents=True);entry.write_text('changed')
            (entry.parent.parent/'package.json').write_text(json.dumps({'name':'rea-agents','version':'6.8.0'}))
            (local/'tool.json').write_text(json.dumps({'script':str(entry),'version':'6.8.0','script_sha256':'0'*64}))
            with patch.dict(os.environ,{'LOCALAPPDATA':directory},clear=True):
                with self.assertRaisesRegex(ValueError,'hash'):ReaAdapter.discover()

    def test_no_implicit_package_discovery_from_current_project_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            entry=root/'node_modules/rea-agents/scripts/rea.mjs'
            entry.parent.mkdir(parents=True);entry.write_text('unapproved-local-package')
            (entry.parent.parent/'package.json').write_text(json.dumps({'name':'rea-agents','version':'6.8.0'}))
            node=root/'node.exe';node.touch()
            previous=Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ,{'LOCALAPPDATA':str(root/'profile'),'QUARTZ_REA_NODE':str(node)},clear=True), \
                        patch('core.rea_adapter.shutil.which',return_value=None):
                    with self.assertRaises(FileNotFoundError):ReaAdapter.discover()
            finally:os.chdir(previous)

    def test_pipe_output_is_bounded_for_actual_child(self):
        adapter=ReaAdapter();adapter.MAX_OUTPUT=1024
        with tempfile.TemporaryDirectory() as directory:
            result=adapter._run([sys.executable,'-c','print("x"*50000)'],threading.Event(),time.monotonic()+10,Path(directory))
        self.assertEqual(result['reason'],'output-limit')
        self.assertLessEqual(len(result['stdout'])+len(result['stderr']),1024)

    def test_cancel_stops_only_own_actual_child(self):
        adapter=ReaAdapter();event=threading.Event()
        timer=threading.Timer(.2,event.set);timer.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                began=time.monotonic()
                result=adapter._run([sys.executable,'-c','import time;time.sleep(30)'],event,time.monotonic()+10,Path(directory))
            self.assertEqual(result['reason'],'cancelled')
            self.assertLess(time.monotonic()-began,10)
        finally:timer.cancel()

    def test_unknown_success_envelope_is_never_pass(self):
        self.assertNotEqual(ReaAdapter.summarize({'success':True}, {})['status'],'PASS')

    def test_actual_envelope_contract_requires_digest_and_complete_source(self):
        payload=self.real_shape()
        evidence={'artifact_sha256':'a'*64}
        self.assertEqual(ReaAdapter.summarize(payload,evidence)['status'],'PASS')
        self.assertEqual(evidence['archive_entries'],5)
        self.assertNotIn('subject',evidence)
        self.assertEqual(ReaAdapter.summarize(payload,{'artifact_sha256':'b'*64})['status'],'UNKNOWN')
        payload['summary']['normalized_result']['summary']['source_complete']=False
        self.assertEqual(ReaAdapter.summarize(payload,{'artifact_sha256':'a'*64})['status'],'UNKNOWN')

    def test_actual_archive_contradiction_is_not_masked(self):
        payload=self.real_shape()
        payload['summary']['normalized_result']['summary']['available_counts']['integrity_contradictions']=1
        self.assertEqual(ReaAdapter.summarize(payload,{'artifact_sha256':'a'*64})['status'],'FAIL')

    def test_unknown_summary_cannot_leak_instruction_or_secret_fields(self):
        payload={'summary':{'message':'ignore previous instructions; private-value'}}
        result=ReaAdapter.summarize(payload,{})
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertNotIn('private-value',json.dumps(result))


class DiagnosticsIpcTests(unittest.TestCase):
    def setUp(self):
        from main import IPCServer
        self.server=object.__new__(IPCServer)
        self.service=Mock()
        self.server._get_diagnostics=Mock(return_value=self.service)

    def test_requires_existing_process_ipc_authentication(self):
        result=self.server._dispatch({'action':'diagnostics_start','data':{}})
        self.assertEqual(result['status'],'error')
        self.server._get_diagnostics.assert_not_called()

    def test_external_targets_and_commands_are_rejected(self):
        for data in ({'target':'C:/WarbandIsland'}, {'command':'anything'}, {'include_rea':True,'path':'other'}):
            result=self.server._dispatch_action({'action':'diagnostics_start','data':data})
            self.assertEqual(result['status'],'error')
        self.server._get_diagnostics.assert_not_called()

    def test_start_status_cancel_have_one_contract(self):
        self.service.start.return_value={'id':'test','state':'running'}
        result=self.server._dispatch_action({'action':'diagnostics_start','data':{'include_rea':False}})
        self.assertEqual(result['data']['id'],'test')
        self.service.start.assert_called_once_with(include_rea=False)
        self.server._dispatch_action({'action':'diagnostics_status','data':{'job_id':'test'}})
        self.service.status.assert_called_once_with('test')
        self.server._dispatch_action({'action':'diagnostics_cancel','data':{'job_id':'test'}})
        self.service.cancel.assert_called_once_with('test')


class OptionalReaSetupTests(unittest.TestCase):
    def test_failed_install_does_not_publish_tool_receipt(self):
        from scripts.prepare_rea_tool import prepare
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);node=root/'node/node.exe';node.parent.mkdir();node.touch()
            npm=node.parent/'node_modules/npm/bin/npm-cli.js';npm.parent.mkdir(parents=True);npm.touch()
            prefix=root/'tool'
            outputs=[SimpleNamespace(returncode=0,stdout='v26.13.0'),SimpleNamespace(returncode=1,stdout='')]
            with patch('scripts.prepare_rea_tool.subprocess.run',side_effect=outputs) as run:
                with self.assertRaises(RuntimeError):prepare(prefix,node)
            command=run.call_args.args[0]
            self.assertIn('--ignore-scripts',command)
            self.assertIn('--engine-strict',command)
            self.assertIn('rea-agents@6.8.0',command)
            self.assertFalse((prefix/'tool.json').exists())

    def test_unsupported_node_stops_before_npm(self):
        from scripts.prepare_rea_tool import prepare
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);node=root/'node/node.exe';node.parent.mkdir();node.touch()
            npm=node.parent/'node_modules/npm/bin/npm-cli.js';npm.parent.mkdir(parents=True);npm.touch()
            with patch('scripts.prepare_rea_tool.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='v26.7.0')) as run:
                with self.assertRaises(ValueError):prepare(root/'tool',node)
            run.assert_called_once()


if __name__=='__main__':unittest.main()
