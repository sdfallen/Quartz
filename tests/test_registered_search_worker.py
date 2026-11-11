"""Same-worker permission boundary with actual installed fixture child execution.

Only acquisition transport is replaced in positive tests; the installed Python
fixture consumes real rg-style arguments and searches actual selected ZIP bytes.
These tests are not packaged GUI or official ripgrep acceptance.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

from core.artifact_diagnostics import ArtifactDiagnosticsService
from core.tool_workbench import ToolWorkbench
from core.tool_workbench.catalog import BUILTIN_MANIFESTS, ToolCatalog

MARKER = 'QUARTZ_REGISTERED_WORKER_REAL_MATCH'


class RecordingWorkbench(ToolWorkbench):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.acquisitions = []
        self.executions = []
        self.receipts = []
    def acquire(self, selection, *args, **kwargs):
        self.acquisitions.append({'selection':selection, 'deadline':kwargs.get('deadline_monotonic')})
        return super().acquire(selection, *args, **kwargs)
    def execute(self, request, *args, **kwargs):
        self.executions.append(deepcopy(request))
        receipt = super().execute(request, *args, **kwargs)
        self.receipts.append(deepcopy(receipt))
        return receipt


class RegisteredSearchWorker(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'selected.zip'
        with zipfile.ZipFile(self.target, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('package.json', json.dumps({'name':'registered-worker-fixture'}))
            archive.writestr('asset.txt', MARKER)
        self.before = hashlib.sha256(self.target.read_bytes()).hexdigest()
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('fixture_rg.py',
                'import pathlib,sys\n'
                'args=sys.argv[1:]\n'
                'assert args[:3]==["--no-config","--color","never"],args\n'
                'assert "-a" in args and "-e" in args,args\n'
                'needle=args[args.index("-e")+1].encode()\n'
                'data=pathlib.Path(args[-1]).read_bytes()\n'
                'found=needle in data\n'
                'if found: sys.stdout.buffer.write(needle+b"\\n")\n'
                'sys.exit(0 if found else 1)\n')
        self.archive = data.getvalue()
        self.manifest = replace(BUILTIN_MANIFESTS['ripgrep'], name='Registered test fixture (not official rg)',
            version='fixture1', pinned_revision='fixture1', source_url='https://github.com/quartz-tests/fixture/archive.zip',
            package_digest=hashlib.sha256(self.archive).hexdigest(), executable_subpath='fixture_rg.py', platform=['any'])
        self.created = []
        def create(*,workspace_dir):
            workbench = RecordingWorkbench(managed_dir=self.root/'managed', workspace_dir=workspace_dir,
                catalog=ToolCatalog({'ripgrep':self.manifest}))
            self.created.append(workbench)
            return workbench
        self.factory = Mock(side_effect=create)
        self.transport = patch('core.tool_workbench.acquisition.urllib.request.build_opener')
        self.opener = self.transport.start()
        self.addCleanup(self.transport.stop)
        def response(*args, **kwargs):
            stream = io.BytesIO(self.archive)
            stream.geturl = lambda:self.manifest.source_url
            return stream
        self.opener.return_value.open.side_effect = response

    def service(self, **kwargs):
        service = ArtifactDiagnosticsService(self.target, reports=self.root/'reports',
            investigation_root=self.root/'investigations', knowledge=False,
            registered_search={'pattern':MARKER}, workbench_factory=self.factory, **kwargs)
        self.addCleanup(service.shutdown)
        return service

    def waiting(self, service):
        job = service.start(include_rea=False)
        end = time.monotonic()+6
        while time.monotonic()<end:
            state=service.status(job['id'])
            if state['phase']=='tool_permission':return job
            if state['state']!='running':self.fail(state)
            time.sleep(.01)
        self.fail('worker did not reach permission phase')

    def complete(self, service, job):
        service.threads[job['id']].join(10)
        self.assertFalse(service.threads[job['id']].is_alive())
        return service.status(job['id'])

    def test_no_workbench_acquisition_or_process_before_explicit_approval(self):
        service = self.service()
        job = self.waiting(service)
        time.sleep(.05)
        self.factory.assert_not_called()
        self.opener.assert_not_called()
        self.assertEqual(self.created,[])
        self.assertEqual(service.status(job['id'])['state'],'running')
        self.assertTrue(any(item['id']=='analysis' and item['status']=='PASS' for item in service.status(job['id'])['checks']))
        service.cancel(job['id'])
        self.assertEqual(self.complete(service,job)['state'],'cancelled')
        self.assertEqual(service.shutdown()['status'],'confirmed')
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(),self.before)

    def test_denial_finishes_static_report_but_registered_search_is_not_tested(self):
        service=self.service();job=self.waiting(service)
        service.authorize_registered_tool(job['id'],False)
        state=self.complete(service,job)
        self.assertEqual(state['state'],'completed')
        result=next(c for c in state['checks'] if c['id']=='registered_tool')
        self.assertEqual(result['status'],'NOT_TESTED')
        self.factory.assert_not_called();self.opener.assert_not_called()
        self.assertTrue(Path(state['report_path']).is_file())
        self.assertEqual(service.shutdown()['status'],'confirmed')

    def test_actual_registered_fixture_output_persists_after_workspace_cleanup(self):
        service=self.service();job=self.waiting(service)
        service.authorize_registered_tool(job['id'],True)
        state=self.complete(service,job)
        self.assertEqual(state['state'],'completed',state)
        check=next(c for c in state['checks'] if c['id']=='registered_tool')
        self.assertEqual(check['status'],'PASS',state)
        self.assertEqual(check['evidence']['exit_code'],0)
        self.assertGreater(check['evidence']['stdout_bytes'],0)
        self.assertEqual(len(self.created),1)
        workbench=self.created[0]
        self.assertEqual(len(workbench.acquisitions),1)
        self.assertEqual(len(workbench.executions),1)
        receipt=workbench.receipts[0]
        self.assertEqual(receipt['cleanup_receipt']['status'],'confirmed')
        self.assertGreater(receipt['process_identity']['pid'],0)
        report=json.loads(Path(state['report_path']).read_text(encoding='utf-8'))
        self.assertEqual(report['id'],job['id'])
        session=service._investigations[job['id']]
        artifacts=[self.root/'investigations'/record['artifact_relative_path'] for record in session.evidence.records.values() if record['kind']=='tool-artifact']
        self.assertTrue(any(MARKER.encode() in artifact.read_bytes() for artifact in artifacts))
        self.assertTrue(all(record['level']=='SOURCE' for record in session.evidence.records.values() if record['origin']=='ripgrep'))
        self.assertEqual(service._workspaces[job['id']],set())
        self.assertTrue(all(not Path(item['workspace']).exists() for item in workbench.executions))
        self.assertTrue(state.get('investigation_knowledge_saved'))
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(),self.before)
        self.assertEqual(service.shutdown()['status'],'confirmed')
        self.assertTrue(all(not thread.is_alive() for thread in service.threads.values()))

    def test_worker_deadline_is_forwarded_to_both_acquisition_and_execution(self):
        service=self.service();service.DEADLINE_SECONDS=20
        before=time.monotonic();job=self.waiting(service)
        service.authorize_registered_tool(job['id'],True)
        self.assertEqual(self.complete(service,job)['state'],'completed')
        session=service._investigations[job['id']]
        self.assertGreaterEqual(session.deadline,before+19)
        self.assertEqual(self.created[0].acquisitions[0]['deadline'],session.deadline)
        self.assertEqual(self.created[0].executions[0]['deadline_monotonic'],session.deadline)

    def test_approval_is_single_use_and_wrong_job_or_nonboolean_is_rejected(self):
        service=self.service();job=self.waiting(service)
        for identity,value in ((job['id']+'wrong',True),(job['id'],1),(job['id'],'yes')):
            with self.assertRaises(ValueError):service.authorize_registered_tool(identity,value)
        service.authorize_registered_tool(job['id'],True)
        with self.assertRaises(ValueError):service.authorize_registered_tool(job['id'],True)
        state=self.complete(service,job)
        self.assertEqual(state['state'],'completed',state)
        self.assertEqual(len(self.created[0].executions),1)

    def test_cancel_during_permission_does_not_leak_owner_or_accept_late_approval(self):
        service=self.service();job=self.waiting(service)
        service.cancel(job['id'])
        with self.assertRaises(ValueError):service.authorize_registered_tool(job['id'],True)
        self.assertEqual(self.complete(service,job)['state'],'cancelled')
        self.assertIsNone(service._owned_workbench)
        self.assertEqual(service.shutdown()['status'],'confirmed')
        self.factory.assert_not_called()
        self.assertEqual(service._workspaces[job['id']],set())
        self.assertEqual(list((self.root/'investigations'/'knowledge').glob('*.json')),[])

    def test_cancel_during_acquisition_is_cancelled_without_spawn_or_owner_leak(self):
        entered,resume=threading.Event(),threading.Event()
        payload=self.archive
        source=self.manifest.source_url
        class BlockingResponse(io.BytesIO):
            def geturl(inner):return source
            def read(inner,amount):
                entered.set()
                if not resume.wait(5):raise TimeoutError('fixture wait expired')
                return super().read(amount)
        self.opener.return_value.open.side_effect=lambda *args,**kwargs:BlockingResponse(payload)
        service=self.service();job=self.waiting(service)
        service.authorize_registered_tool(job['id'],True)
        try:
            self.assertTrue(entered.wait(5))
            service.cancel(job['id'])
        finally:resume.set()
        state=self.complete(service,job)
        self.assertEqual(len(self.created),1)
        self.assertEqual(self.created[0].executions,[])
        self.assertEqual(service.shutdown()['status'],'confirmed')
        self.assertEqual(service._workspaces[job['id']],set())
        self.assertEqual(list((self.root/'investigations'/'knowledge').glob('*.json')),[])
        self.assertEqual(state['state'],'cancelled',state)

    def test_shutdown_while_waiting_rejects_late_approval_and_future_job(self):
        service=self.service();job=self.waiting(service)
        self.assertEqual(service.shutdown()['status'],'confirmed')
        self.assertEqual(service.status(job['id'])['state'],'cancelled')
        with self.assertRaises(ValueError):service.authorize_registered_tool(job['id'],True)
        with self.assertRaises(RuntimeError):service.start(include_rea=False)
        self.factory.assert_not_called()

    def test_pending_cleanup_keeps_workspace_until_stop_is_confirmed(self):
        # Negative ownership receipt fixture: no actual child/tool success claimed.
        class PendingWorkbench:
            pending=True
            def resolve(inner,*args):return {'status':'resolved','manifest':self.manifest.to_dict()}
            def acquire(inner,*args,**kwargs):return {'status':'cached'}
            def execute(inner,request,event):
                return {'request_id':request['request_id'],'tool_id':'ripgrep','status':'failed','exit_code':2,
                    'source_url':self.manifest.source_url,'pinned_revision':self.manifest.pinned_revision,
                    'package_digest':self.manifest.package_digest,'cleanup_receipt':{'status':'confirmed'},
                    'artifacts':[],'stdout_bytes':0,'stderr_bytes':1}
            def stop(inner,*args):return {'status':'pending' if inner.pending else 'confirmed'}
            def close(inner):return inner.stop()
        peer=PendingWorkbench()
        self.factory.side_effect=lambda **kwargs:peer
        service=self.service();job=self.waiting(service)
        service.authorize_registered_tool(job['id'],True)
        state=self.complete(service,job)
        self.assertEqual(state['state'],'completed')
        self.assertEqual(next(c for c in state['checks'] if c['id']=='registered_tool')['status'],'UNKNOWN')
        self.assertEqual(service._gateway_cleanup[job['id']]['status'],'pending')
        workspaces=list(service._workspaces[job['id']])
        self.assertTrue(workspaces)
        self.assertTrue(all(Path(folder).exists() for folder in workspaces))
        with self.assertRaises(RuntimeError):service.start(include_rea=False)
        self.assertEqual(service.shutdown()['status'],'pending')
        self.assertTrue(all(Path(folder).exists() for folder in workspaces))
        peer.pending=False
        self.assertEqual(service.shutdown()['status'],'confirmed')
        self.assertTrue(all(not Path(folder).exists() for folder in workspaces))

    def test_no_match_is_real_exit_one_with_empty_output_and_not_fabricated_matches(self):
        # Search content absent from target; Python fixture returns genuine exit1.
        service=self.service();service.registered_search={'pattern':'ABSENT_MARKER_NOT_IN_TARGET'}
        job=self.waiting(service);service.authorize_registered_tool(job['id'],True)
        state=self.complete(service,job)
        self.assertEqual(state['state'],'completed',state)
        result=next(c for c in state['checks'] if c['id']=='registered_tool')
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['evidence']['exit_code'],1)
        self.assertEqual(result['evidence']['stdout_bytes'],0)
        self.assertEqual(len(self.created[0].executions),1)


if __name__=='__main__':unittest.main()
