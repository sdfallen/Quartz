"""Real parser/capture through the existing job owner; UI acceptance is separate."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
import zipfile

from core.application_services import ApplicationServices, ServiceFactories
from core.artifact_diagnostics import ArtifactDiagnosticsService, selected_artifact, selected_executable
from core.rea_analysis import AnalysisService


class InvestigationAnalysisIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.target=self.root/'application.zip'
        with zipfile.ZipFile(self.target,'w') as z:
            z.writestr('package.json',json.dumps({'name':'fixture','dependencies':{'electron':'1.0.0'}}))
            z.writestr('asset.txt','fixture data')

    def service(self,**kw):
        return ArtifactDiagnosticsService(self.target,reports=self.root/'reports',
            investigation_root=self.root/'investigations',knowledge=False,**kw)

    def test_real_parser_report_is_persisted_inside_existing_diagnostics_job(self):
        service=self.service();self.addCleanup(service.shutdown)
        job=service.start(include_rea=False);service.threads[job['id']].join(5)
        state=service.status(job['id'])
        self.assertEqual(state['state'],'completed')
        analysis=next(c for c in state['checks'] if c['id']=='analysis')
        self.assertEqual(analysis['status'],'PASS')
        self.assertIn('package-inventory',analysis['evidence']['capabilities'])
        context=state['investigation']['context']
        self.assertTrue(any(f['claim_id']=='analysis.package.inventory' for f in context['findings']))
        self.assertFalse(context['instruction_authority'])
        self.assertEqual(service.shutdown()['status'],'confirmed')
        self.assertTrue(all(not t.is_alive() for t in service.threads.values()))
        self.assertEqual(list((self.root/'investigations'/'workspaces').iterdir()),[])

    def test_new_artifact_picker_scope_does_not_weaken_legacy_exe_validation(self):
        self.assertEqual(selected_artifact(self.target),self.target.resolve())
        with self.assertRaises(ValueError):selected_executable(self.target)
        private=self.root/'.env';private.write_text('not read')
        with self.assertRaises(ValueError):selected_artifact(private)

    def test_cancelled_analysis_never_publishes_knowledge(self):
        entered,release=threading.Event(),threading.Event()
        class WaitingAnalyzer(AnalysisService):
            def analyze(inner,request,executor,cancel_event=None):
                entered.set();release.wait(3)
                return super().analyze(request,executor,cancel_event)
        service=self.service(analyzer=WaitingAnalyzer());self.addCleanup(service.shutdown)
        job=service.start(include_rea=False)
        try:
            self.assertTrue(entered.wait(2));service.cancel(job['id'])
        finally:release.set();service.threads[job['id']].join(4)
        self.assertEqual(service.status(job['id'])['state'],'cancelled')
        self.assertEqual(list((self.root/'investigations'/'knowledge').glob('*.json')),[])
        self.assertEqual(service.shutdown()['status'],'confirmed')

    def test_stop_fence_disallows_restart_of_closed_owner(self):
        service=self.service();self.assertEqual(service.shutdown()['status'],'confirmed')
        with self.assertRaises(RuntimeError):service.start()

    def test_pending_tool_cleanup_keeps_existing_application_owner(self):
        previous=Mock();previous.shutdown.return_value={'status':'pending'}
        previous.threads={}
        factory=Mock()
        owner=ApplicationServices(ServiceFactories(artifact_diagnostics=factory))
        owner.adopt('artifact_diagnostics',previous)
        with self.assertRaises(RuntimeError):owner.replace_artifact_diagnostics('new.exe')
        self.assertIs(owner.peek('artifact_diagnostics'),previous)
        self.assertEqual(owner.shutdown()['status'],'pending')
        factory.assert_not_called()

    def test_domain_scope_inventory_does_not_grow_past_job_inventory(self):
        service=self.service();self.addCleanup(service.shutdown)
        for _ in range(8):
            job=service.start(include_rea=False);service.threads[job['id']].join(3)
            self.assertEqual(service.status(job['id'])['state'],'completed')
        self.assertLessEqual(len(service.jobs),5)
        self.assertLessEqual(len(service._investigations),5)
        self.assertLessEqual(len(service._gateways),5)


if __name__=='__main__':unittest.main()
