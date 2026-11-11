"""Contract tests. Workbench doubles are not claimed as actual GitHub execution."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import threading
import time
import unittest

from core.investigation.contracts import InvestigationError
from core.investigation.gateway import InvestigationToolGateway
from core.investigation.planning import InvestigationPolicy, select_capabilities
from core.investigation.session import InvestigationSession


class WorkbenchDouble:
    def __init__(self, workspace, spec):self.workspace,self.spec,self.calls=workspace,spec,0
    def execute(self, request, event):
        self.calls+=1
        self.workspace.joinpath('output.json').write_bytes(b'{"observed":42}')
        return {'request_id':request['request_id'],'tool_id':request['tool_id'],
                'status':'completed','exit_code':0,'cleanup_receipt':{'status':'confirmed'},
                **{k:self.spec[k] for k in ('source_url','pinned_revision','package_digest')},
                'artifacts':[{'path':'output.json','sha256':hashlib.sha256(b'{"observed":42}').hexdigest()}]}
    def stop(self, investigation_id):return {'status':'confirmed'}


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);target=self.root/'subject.exe';target.write_bytes(b'MZ-test-target')
        self.event=threading.Event()
        self.session=InvestigationSession(target,root=self.root/'evidence',event=self.event,
            deadline=time.monotonic()+20,tool_identity={'version':'test-double'})
        self.workspace=self.root/'tool-workspace';self.workspace.mkdir()
        self.spec={'operations':['inspect_artifact'],'effects':['read_target','execute_tool','write_workspace'],
                   'source_url':'https://github.com/example/source','pinned_revision':'a'*40,'package_digest':'b'*64}
        self.workbench=WorkbenchDouble(self.workspace,self.spec)
        self.gateway=InvestigationToolGateway(self.session,self.workbench,workspace=self.workspace,
            policy=InvestigationPolicy(effects=frozenset(self.spec['effects'])),tool_specs={'test-tool':self.spec})
        self.request={'investigation_id':self.session.evidence.id,'step_id':'inspect-1','tool_id':'test-tool',
                      'operation':'inspect_artifact','target':self.session.target.as_dict(),
                      'workspace':str(self.workspace),'options':{}}

    def test_real_artifact_file_is_saved_and_duplicate_request_is_not_executed(self):
        first=self.gateway.execute(self.request,self.event)
        second=self.gateway.execute(self.request,self.event)
        self.assertEqual(self.workbench.calls,1)
        self.assertTrue(second['replayed_receipt'])
        self.assertEqual(first['evidence_ids'],second['evidence_ids'])
        self.assertEqual(len(self.session.evidence.records),2)

    def test_conflicting_step_and_wrong_target_rejected(self):
        self.gateway.execute(self.request)
        request=deepcopy(self.request);request['options']={'detail':'different'}
        with self.assertRaises(InvestigationError):self.gateway.execute(request)
        request=deepcopy(self.request);request['target']['sha256']='0'*64
        with self.assertRaises(InvestigationError):self.gateway.execute(request)
        self.assertEqual(self.workbench.calls,1)

    def test_unknown_investigation_or_external_workspace_rejected(self):
        for key,value in [('investigation_id','different'),('workspace',str(self.root))]:
            request=deepcopy(self.request);request[key]=value
            with self.assertRaises(InvestigationError):self.gateway.execute(request)
        self.assertEqual(self.workbench.calls,0)

    def test_arbitrary_shell_nested_env_and_secrets_are_not_tool_options(self):
        for options in [{'shell':'anything'},{'nested':{'env':{}}},{'api_key':'private'}]:
            request=deepcopy(self.request);request['options']=options
            with self.assertRaises(InvestigationError):self.gateway.execute(request)
        self.assertEqual(self.workbench.calls,0)

    def test_workbench_exception_does_not_allow_same_step_to_execute_again(self):
        calls=[]
        def fail(request,event):calls.append(request);raise OSError('unknown after process start')
        self.workbench.execute=fail
        with self.assertRaises(OSError):self.gateway.execute(self.request)
        receipt=self.gateway.execute(self.request)
        self.assertTrue(receipt['replayed_receipt'])
        self.assertEqual(receipt['status'],'blocked')
        self.assertEqual(len(calls),1)

    def test_unconfirmed_cleanup_does_not_publish_verified_artifact(self):
        execute=self.workbench.execute
        def pending(request,event):
            receipt=execute(request,event);receipt['cleanup_receipt']={'status':'pending'};return receipt
        self.workbench.execute=pending
        with self.assertRaises(InvestigationError):self.gateway.execute(self.request)
        self.assertEqual(self.session.evidence.records,{})
        self.gateway.execute(self.request)
        self.assertEqual(self.workbench.calls,1)

    def test_lying_tool_provenance_is_rejected(self):
        execute=self.workbench.execute
        def changed(request,event):
            receipt=execute(request,event);receipt['package_digest']='c'*64;return receipt
        self.workbench.execute=changed
        with self.assertRaises(InvestigationError):self.gateway.execute(self.request)
        self.assertEqual(self.session.evidence.records,{})

    def test_tool_cannot_mutate_target_and_report_success(self):
        execute=self.workbench.execute
        def changed(request,event):
            receipt=execute(request,event);Path(self.session.target.canonical_path).write_bytes(b'changed');return receipt
        self.workbench.execute=changed
        with self.assertRaises(InvestigationError):self.gateway.execute(self.request)
        self.assertEqual(self.session.evidence.records,{})

    def test_cancellation_fences_late_tool_result(self):
        execute=self.workbench.execute
        def changed(request,event):
            receipt=execute(request,event);event.set();return receipt
        self.workbench.execute=changed
        with self.assertRaises(InvestigationError):self.gateway.execute(self.request)
        self.assertEqual(self.session.evidence.records,{})

    def test_new_tool_cannot_extend_readonly_policy(self):
        gateway=InvestigationToolGateway(self.session,self.workbench,workspace=self.workspace,
            policy=InvestigationPolicy(),tool_specs={'test-tool':self.spec})
        with self.assertRaises(InvestigationError):gateway.execute(self.request)
        self.assertEqual(self.workbench.calls,0)

    def test_second_parallel_call_is_not_another_operator(self):
        execute=self.workbench.execute;entered=threading.Event();release=threading.Event();errors=[]
        def wait(request,event):entered.set();release.wait(3);return execute(request,event)
        self.workbench.execute=wait
        def run():
            try:self.gateway.execute(self.request)
            except Exception as exc:errors.append(exc)
        worker=threading.Thread(target=run);worker.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(InvestigationError):self.gateway.execute(self.request)
        finally:release.set();worker.join(3)
        self.assertEqual(errors,[])
        self.assertEqual(self.workbench.calls,1)

    def test_secret_receipt_fields_are_not_persisted(self):
        execute=self.workbench.execute
        def secret(request,event):
            receipt=execute(request,event);receipt['token']='never-save-this-value';return receipt
        self.workbench.execute=secret
        result=self.gateway.execute(self.request)
        self.assertEqual(result['token'],'[gizli]')
        for p in self.session.evidence.directory.glob('*.artifact'):
            self.assertNotIn(b'never-save-this-value',p.read_bytes())

    def test_missing_native_capability_is_not_replaced_with_header(self):
        catalog=[{'capability_id':'pe_header','available':True,'effects':['read_target']}]
        plan=select_capabilities(['native_functions'],catalog,InvestigationPolicy())
        self.assertEqual(plan['selected'],[])
        self.assertEqual(plan['missing'],['native_functions'])

    def test_runtime_attach_requires_current_effect_authority(self):
        catalog=[{'capability_id':'trace','available':True,'effects':['attach_runtime']}]
        plan=select_capabilities(['trace'],catalog,InvestigationPolicy())
        self.assertEqual(plan['restricted'],['trace'])


if __name__=='__main__':unittest.main()
