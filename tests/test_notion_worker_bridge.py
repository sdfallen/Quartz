import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.notion_worker_bridge import ReadOnlyWorkerBridge, NotionQueueApi, sign, verify, rich


KEY = bytes.fromhex('12' * 32)  # synthetic, not a deployed secret
QUEUE = '10000000-0000-0000-0000-000000000001'


class WorkerBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root/'fixture.txt'
        self.file.write_text('actual fixture bytes',encoding='utf-8')
        stat = self.file.stat()
        self.manifest = dict(task_id='t',session_id='s',project_id='p',scope_ref='local',request_id='r',
            root=str(self.root),relative_path='fixture.txt',file_identity=[stat.st_dev,stat.st_ino,stat.st_size],
            sha256=hashlib.sha256(self.file.read_bytes()).hexdigest(),expires_at=100)
        self.request = {k:self.manifest[k] for k in ('task_id','session_id','project_id','scope_ref','request_id','expires_at')}
        self.request.update(schema_version=1,tool_name='read_test_file',arguments={'relative_path':'fixture.txt'})
        self.api = Mock(queue_id=QUEUE)
        self.bridge = self.new_bridge()

    def new_bridge(self):
        return ReadOnlyWorkerBridge(self.api,KEY,self.manifest,self.root/'ledger.sqlite',clock=lambda:10)

    def page(self, request=None):
        return {'id':'page', 'parent':{'data_source_id':QUEUE},'properties':{
            'Signed Request':rich(sign('request',request or self.request,KEY))}}

    def test_real_read_and_fresh_instance_receipt_do_not_reread(self):
        result=self.bridge.process(self.page())
        self.assertEqual(result['output']['text'],'actual fixture bytes')
        self.assertEqual(result['verification'],'observed')
        fresh=self.new_bridge()
        fresh._read_fixture=Mock(side_effect=AssertionError('must not reread'))
        self.assertEqual(fresh.process(self.page()),result)
        fresh._read_fixture.assert_not_called()

    def test_tampered_signature_foreign_domain_and_scope_cannot_read(self):
        for change in ({'session_id':'foreign'},{'arguments':{'relative_path':'../secret.txt'}},
                       {'tool_name':'terminal'},{'expires_at':200},{'scope_ref':'other'}):
            with self.subTest(change=change),self.assertRaises((ValueError,PermissionError)):
                self.bridge.process(self.page({**self.request,**change}))
        self.api.complete.assert_not_called()
        raw=sign('grant',self.request,KEY)
        with self.assertRaises(ValueError): verify(raw,'request',KEY)
        env=json.loads(sign('request',self.request,KEY));env['body']+=' '
        with self.assertRaises(PermissionError):verify(json.dumps(env),'request',KEY)

    def test_stop_expiry_and_foreign_page_fail_closed(self):
        self.bridge.stop()
        with self.assertRaises(PermissionError):self.bridge.process(self.page())
        fresh=self.new_bridge();fresh.clock=lambda:101
        with self.assertRaises(PermissionError):fresh.process(self.page())
        page=self.page();page['parent']['data_source_id']='foreign'
        with self.assertRaises(PermissionError):self.new_bridge().process(page)

    def test_file_replacement_and_changed_bytes_never_read_as_success(self):
        self.file.unlink();self.file.write_text('replacement',encoding='utf-8')
        result=self.bridge.process(self.page())
        self.assertEqual(result['status'],'blocked')
        self.assertNotIn('output',result)

    def test_restart_with_claimed_uncertain_request_never_reexecutes(self):
        raw=self.page()['properties']['Signed Request']['rich_text'][0]['text']['content']
        with self.bridge._db() as db:
            db.execute('INSERT INTO requests VALUES (?,?,?,NULL)',('r',hashlib.sha256(raw.encode()).hexdigest(),'claimed'))
        with self.assertRaises(RuntimeError): self.new_bridge().process(self.page())
        self.api.complete.assert_not_called()

    def test_publish_timeout_retains_receipt_and_prevents_second_read(self):
        self.api.complete.side_effect=TimeoutError('synthetic network failure')
        with self.assertRaises(TimeoutError):self.bridge.process(self.page())
        self.api.complete.side_effect=None
        fresh=self.new_bridge();fresh._read_fixture=Mock(side_effect=AssertionError())
        self.assertEqual(fresh.process(self.page())['status'],'completed')
        fresh._read_fixture.assert_not_called()

    def test_queue_api_rejects_foreign_page_before_patch(self):
        api=NotionQueueApi(QUEUE,QUEUE)
        api._send=Mock(return_value={'parent':{'data_source_id':'other'}})
        with self.assertRaises(PermissionError):api.complete(QUEUE,'signed','completed')
        self.assertEqual(api._send.call_count,1)
