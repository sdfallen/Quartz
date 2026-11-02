"""Actual GUI bridge + real disposable diagnostics; providers/desktop are not run."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import gui
from core.application_services import ApplicationServices, ServiceFactories
from core.artifact_diagnostics import ArtifactDiagnosticsService
from core.investigation.chat_task import classify_investigation_request


class BridgeReview(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.target=self.root/'app.zip'
        with zipfile.ZipFile(self.target,'w') as z:z.writestr('package.json','{"name":"fixture"}')
        class Fast(ArtifactDiagnosticsService):
            def start(instance,include_rea=True):return super(Fast,instance).start(False)
        def factory(path,**options):
            return Fast(path,knowledge=False,reports=self.root/'reports',investigation_root=self.root/'evidence',**options)
        self.api=gui.Api(services=ApplicationServices(ServiceFactories(artifact_diagnostics=factory)))
        self.addCleanup(self.api._services.shutdown)
        self.state={'status':'ok','data':{'active_conversation':{'id':'current'},'active_turn':None}}
        self.ipc=patch('gui.ipc_send',side_effect=lambda *a,**k:self.state);self.ipc.start();self.addCleanup(self.ipc.stop)
        self.window=Mock();self.window.create_file_dialog.return_value=[str(self.target)]
        self.windows=patch.object(gui.webview,'windows',[self.window]);self.windows.start();self.addCleanup(self.windows.stop)

    def test_fix_and_review_request_keeps_real_writer_route(self):
        text='Bu uygulamadaki hatayı incele ve düzelt; diğer ajan kontrol etsin.'
        with patch.object(self.api,'natural_start',return_value={'status':'ok','data':{'handled':True}}) as start, \
             patch.object(self.api,'diagnostics_select_application',side_effect=AssertionError('lost writer request')):
            self.assertEqual(self.api.coordination_route(text,'current','p',{},'full')['status'],'ok')
        start.assert_called_once_with(text,'current','p',{},'full')
        self.assertFalse(self.api._services.open_chat_tasks())

    def test_readonly_job_reconciles_to_source_completion(self):
        text='Bu uygulamadaki kaydetme hatasını incele'
        result=self.api.coordination_route(text,'current','p',{},'full')
        self.assertEqual(result['status'],'ok',result)
        data=result['data'];job=data['diagnostics'];service=self.api._artifact_diagnostics
        service.threads[job['id']].join(10)
        view=self.api.diagnostics_status(job['id'])
        self.assertEqual(view['status'],'ok',view)
        task=view['data']['chat_task']
        self.assertEqual(task['state'],'completed')
        self.assertEqual(task['verification'],'SOURCE')
        self.assertFalse(task['fix_verified'])
        self.assertEqual(self.api._services.open_chat_tasks(),[])

    def test_code_fix_keeps_existing_file_writer_route(self):
        text='Bu uygulamanın fonksiyonunu düzelt ve kodunu incele'
        with patch.object(self.api,'natural_start',side_effect=AssertionError('file task forced into UI')), \
             patch.object(self.api,'diagnostics_select_application',side_effect=AssertionError('file task consumed')):
            response=self.api.coordination_route(text,'current','p',{},'full')
        self.assertEqual(response['status'],'ok',response)
        self.assertFalse(response['data']['handled'])
        self.assertEqual(response['data']['intent'],'task')

    def test_stale_or_forged_context_never_opens_picker(self):
        text='Bu uygulamadaki kaydetme hatasını incele'
        request=classify_investigation_request(text)
        self.state['data']['active_conversation']['id']='another'
        result=self.api.diagnostics_select_application(text,request,'current')
        self.assertEqual(result['status'],'error')
        self.window.create_file_dialog.assert_not_called()
        self.state['data']['active_conversation']['id']='current'
        result=self.api.diagnostics_select_application(text,dict(request,fix_requested=True),'current')
        self.assertEqual(result['status'],'error')
        self.window.create_file_dialog.assert_not_called()

    def test_search_denial_resumes_same_job_without_installation(self):
        text='Bu pakette "QUARTZ_MARKER" dizesini ara'
        result=self.api.coordination_route(text,'current','p',{},'full')
        self.assertEqual(result['status'],'ok',result)
        data=result['data'];job=data['diagnostics'];task=data['investigation_task'];pending=task['pending_permission']
        service=self.api._artifact_diagnostics
        self.assertIsNone(service._owned_workbench)
        args=(task['task_id'],pending['request_id'],pending['generation'],pending['effect'],False,'current')
        for generation in (True,str(pending['generation']),1.0):
            invalid=list(args);invalid[2]=generation
            self.assertEqual(self.api.investigation_grant_scope(*invalid)['status'],'error')
        self.assertEqual(self.api.investigation_grant_scope(*args)['status'],'ok')
        self.assertEqual(self.api.investigation_grant_scope(*args)['status'],'error')
        service.threads[job['id']].join(10)
        self.assertIsNone(service._owned_workbench)
        state=self.api.diagnostics_status(job['id'])
        self.assertEqual(state['data']['chat_task']['state'],'blocked')
        self.assertTrue(any(c['id']=='registered_tool' and c['status']=='NOT_TESTED' for c in state['data']['checks']))

    def test_conversation_change_blocks_approval_and_readback(self):
        result=self.api.coordination_route('Bu pakette stringleri incele','current','p',{},'full')
        self.assertEqual(result['status'],'ok',result)
        job=result['data']['diagnostics'];task=result['data']['investigation_task'];p=task['pending_permission']
        self.state['data']['active_conversation']['id']='another'
        response=self.api.investigation_grant_scope(task['task_id'],p['request_id'],p['generation'],p['effect'],True,'current')
        self.assertEqual(response['status'],'error')
        self.assertEqual(self.api.diagnostics_status(job['id'])['status'],'error')
        self.assertIsNone(self.api._artifact_diagnostics._owned_workbench)

    def test_changed_target_is_rejected_before_tool_creation(self):
        import time
        result=self.api.coordination_route('Bu pakette stringleri incele','current','p',{},'full')
        self.assertEqual(result['status'],'ok',result)
        job=result['data']['diagnostics'];task=result['data']['investigation_task'];pending=task['pending_permission']
        service=self.api._artifact_diagnostics
        until=time.monotonic()+5
        while service.status(job['id'])['phase']!='tool_permission' and time.monotonic()<until:time.sleep(.01)
        self.assertEqual(service.status(job['id'])['phase'],'tool_permission')
        self.target.write_bytes(b'changed after selection')
        self.assertEqual(self.api.investigation_grant_scope(task['task_id'],pending['request_id'],
            pending['generation'],pending['effect'],True,'current')['status'],'ok')
        service.threads[job['id']].join(10)
        self.assertEqual(service.status(job['id'])['state'],'failed')
        self.assertIsNone(service._owned_workbench)

if __name__=='__main__':unittest.main()
