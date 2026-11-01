"""Acceptance driver state tests with mocked cloud; not LIVE acceptance."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import notion_worker_acceptance as driver
from core.notion_worker_bridge import sign, rich, store_bridge_key, load_bridge_key
from core.atomic_json import atomic_write_json

KEY=bytes.fromhex('12'*32)


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        file=root/'fixture.txt';file.write_text('actual test proof',encoding='utf-8');stat=file.stat()
        self.m={'task_id':'t','session_id':'s','project_id':'p','scope_ref':'scope','request_id':'r',
            'expires_at':driver.time.time()+300,'relative_path':'fixture.txt','root':str(root),
            'file_identity':[stat.st_dev,stat.st_ino,stat.st_size],
            'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'proof':'actual test proof',
            'agent_id':'agent','grant_page_id':'grant'}
        self.path=root/'manifest.json';atomic_write_json(self.path,self.m)
        request={k:self.m[k] for k in ('task_id','session_id','project_id','scope_ref','request_id','expires_at')}
        request.update(schema_version=1,tool_name='read_test_file',arguments={'relative_path':'fixture.txt'})
        self.api=Mock(queue_id='queue')
        self.api.query.return_value=[{'id':'request','parent':{'data_source_id':'queue'},
            'properties':{'Signed Request':rich(sign('request',request,KEY))}}]
        self.client=Mock();self.client.request.return_value={'status':'completed'}
        self.runtime=Mock();self.runtime._owned.return_value=True
        self.runtime.REMOTE_TERMINAL={'completed','failed','canceled','terminated'}
        self.runtime._events.return_value=[{'type':'agent.message','content':[{'type':'text','text':self.m['proof']+' '+self.m['sha256']}]}]
        self.context=patch.object(driver,'owned_context',return_value=(self.runtime,{'agent_id':'agent','workspace_id':'w'},{'queue_id':'queue'},KEY))
        self.context.start();self.addCleanup(self.context.stop)
        self.current=patch.object(driver,'current',side_effect=lambda:(self.path,json.loads(self.path.read_text())))
        self.current.start();self.addCleanup(self.current.stop)
        for attr,value in [('NotionQueueApi',self.api),('NotionCli',self.client)]:
            p=patch.object(driver,attr,return_value=value);p.start();self.addCleanup(p.stop)

    def test_success_and_resume_do_not_submit_again_or_reread(self):
        result=driver.run_acceptance()
        self.assertTrue(result['proof_in_cloud_response'])
        posts=lambda:sum(c.args[0]=='v1/sessions' for c in self.client.request.call_args_list)
        self.assertEqual(posts(),2)
        with patch.object(driver.ReadOnlyWorkerBridge,'_read_fixture',side_effect=AssertionError('No replay')):
            self.assertEqual(driver.run_acceptance()['status'],'observed')
        self.assertEqual(posts(),2)

    def test_requires_action_is_not_autoapproved_or_resent_on_resume(self):
        self.client.request.return_value={'status':'requires_action'}
        result=driver.run_acceptance()
        self.assertEqual(result['status'],'blocked')
        self.api.complete.assert_not_called()
        self.client.request.return_value={'status':'completed'}
        self.assertEqual(driver.run_acceptance()['status'],'observed')
        self.assertEqual(sum(c.args[0]=='v1/sessions' for c in self.client.request.call_args_list),2)

    def test_ambiguous_submit_is_persisted_before_network_boundary(self):
        self.client.request.side_effect=TimeoutError('synthetic')
        with self.assertRaises(TimeoutError):driver.run_acceptance()
        self.assertTrue(json.loads(self.path.read_text())['request_submitted'])
        self.client.request.side_effect=None
        self.assertEqual(driver.run_acceptance()['status'],'observed')
        # One ambiguous request and one result notice; no second initial request.
        self.assertEqual(sum(c.args[0]=='v1/sessions' for c in self.client.request.call_args_list),2)

    def test_stop_and_expiry_prevent_cloud_submit(self):
        stop=Path(self.m['root'])/'.stopped';stop.touch()
        with self.assertRaises(PermissionError):driver.run_acceptance()
        self.client.request.assert_not_called()

    def test_foreign_session_prevents_submit(self):
        self.runtime._owned.return_value=False
        with self.assertRaises(PermissionError):driver.run_acceptance()
        self.client.request.assert_not_called()


class CredentialFormatTests(unittest.TestCase):
    def test_win32_unicode_blob_roundtrip(self):
        cred=Mock(CRED_TYPE_GENERIC=1,CRED_PERSIST_LOCAL_MACHINE=2)
        cred.CredRead.return_value={'CredentialBlob':KEY.hex().encode('utf-16-le')}
        with patch.dict(sys.modules,{'win32cred':cred}):
            store_bridge_key('synthetic-fixture-target',KEY)
            self.assertEqual(cred.CredWrite.call_args.args[0]['CredentialBlob'],KEY.hex())
            self.assertEqual(load_bridge_key('synthetic-fixture-target'),KEY)
