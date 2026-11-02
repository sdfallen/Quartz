"""Real files and publication/cancel races; tool doubles are SOURCE tests only."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from core.investigation.contracts import Cancelled, InvestigationError, Target, validate_finding
from core.investigation.evidence import EvidenceRepository
from core.investigation.memory import InvestigationMemory
from core.investigation.session import DEFAULT_QUESTION, InvestigationSession
from core.artifact_diagnostics import ArtifactDiagnosticsService
from tests.test_rea_learning import pe_bytes


class InvestigationFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target_path = self.root / 'subject.exe'
        self.target_path.write_bytes(pe_bytes())
        self.event = threading.Event()
        self.deadline = time.monotonic() + 20
        self.target = Target.capture(self.target_path, self.event, self.deadline)
        self.store = self.root / 'private-evidence'

    def session(self, **kw):
        return InvestigationSession(self.target_path, root=self.store, event=self.event,
            deadline=self.deadline, tool_identity=kw.pop('tool_identity', {'version':'real-file-test'}), **kw)

    def finished(self):
        s = self.session()
        s.finish([{'id':'artifact','status':'PASS','evidence':{'sha256':s.target.sha256}},
                  {'id':'pe','status':'PASS','evidence':{'architecture':'x64'}}])
        return s

    def test_changed_target_rejects_result(self):
        self.target_path.write_bytes(b'changed')
        with self.assertRaises(InvestigationError): self.target.revalidate(self.event, self.deadline)

    def test_same_size_and_mtime_still_rehashes(self):
        stat = self.target_path.stat()
        data = bytearray(self.target_path.read_bytes()); data[-1] ^= 1
        self.target_path.write_bytes(data)
        os.utime(self.target_path, ns=(stat.st_atime_ns,stat.st_mtime_ns))
        with self.assertRaises(InvestigationError): self.target.revalidate(self.event, self.deadline)

    def test_protected_project_is_not_opened(self):
        with self.assertRaises(InvestigationError):
            Target.capture(self.root / 'WarbandIsland' / 'module.exe',self.event,self.deadline)

    def test_cancelled_capture_rejects(self):
        self.event.set()
        with self.assertRaises(Cancelled):Target.capture(self.target_path,self.event,self.deadline)

    def test_artifact_persists_after_tool_temp_directory_removed(self):
        s = self.session()
        with tempfile.TemporaryDirectory() as tool:
            source = Path(tool)/'artifact.json'; source.write_bytes(b'{"observed":42}')
            record=s.capture_rea(source,source_root=Path(tool),expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        path=EvidenceRepository.verify_record(self.store,s.evidence.records[record['evidence_id']],self.event,self.deadline)
        self.assertEqual(path.read_bytes(),b'{"observed":42}')

    def test_tool_cannot_read_neighbor_as_artifact(self):
        s=self.session(); elsewhere=self.root/'outside.json';elsewhere.write_bytes(b'private')
        inside=self.root/'tool';inside.mkdir()
        with self.assertRaises(InvestigationError):
            s.capture_rea(elsewhere,source_root=inside,expected_sha256=hashlib.sha256(b'private').hexdigest())

    def test_artifact_hash_mismatch_rejected(self):
        s=self.session();source=self.root/'artifact.json';source.write_bytes(b'actual')
        with self.assertRaises(InvestigationError):
            s.capture_rea(source,source_root=self.root,expected_sha256='0'*64)
        self.assertEqual(s.evidence.records,{})

    def test_path_traversal_rejected(self):
        with self.assertRaises(InvestigationError):
            EvidenceRepository.verify_record(self.store,{'artifact_relative_path':'../outside'},self.event,self.deadline)

    def test_static_tool_cannot_claim_live_evidence(self):
        s=self.session()
        with self.assertRaises(InvestigationError):
            s.evidence.add_bytes(b'fake live',kind='screenshot',origin='third-party-tool',level='LIVE')

    def test_artifact_limit_does_not_publish_oversize_file(self):
        s=self.session();s.evidence.MAX_FILE_BYTES=2
        with self.assertRaises(InvestigationError):s.evidence.add_bytes(b'xxx',kind='x',origin='test')
        self.assertEqual(s.evidence.records,{})

    def test_completed_evidence_is_immutable(self):
        s=self.finished()
        with self.assertRaises(InvestigationError):s.evidence.add_bytes(b'x',kind='x',origin='test')

    def test_memory_reload_reuses_only_verified_identity(self):
        first=self.finished();first.publish()
        second=self.session()
        self.assertIsNotNone(second.previous)
        context=InvestigationMemory.context(second.previous)
        self.assertNotIn(str(self.root),json.dumps(context))
        self.assertIs(context['instruction_authority'],False)
        self.assertTrue(context['requires_current_grant'])
        self.assertIsNone(second.cached_inventory()) # PE header is not full REA evidence.

    def test_changed_question_and_tool_invalidate_lookup(self):
        self.finished().publish()
        self.assertIsNone(self.session(question='Başka bir soru').previous)
        self.assertIsNone(self.session(tool_identity={'version':'new-tool'}).previous)

    def test_modified_evidence_invalidates_memory(self):
        s=self.finished();s.publish()
        record=next(iter(s.evidence.records.values()))
        path=self.store/record['artifact_relative_path'];path.write_bytes(b'tampered')
        self.assertIsNone(self.session().previous)

    def test_expired_and_malformed_record_is_cache_miss(self):
        s=self.finished();s.publish()
        path=next((self.store/'knowledge').glob('*.json'))
        record=json.loads(path.read_text());record['observed_at']=0;path.write_text(json.dumps(record))
        self.assertIsNone(self.session().previous)
        for value in ['[]','{"schema_version":1}','not json']:
            path.write_text(value)
            self.assertIsNone(self.session().previous)

    def test_publish_refuses_cancelled_and_incomplete_report(self):
        s=self.session()
        with self.assertRaises(InvestigationError):s.publish()
        s.finish([{'id':'artifact','status':'PASS','evidence':{}}]);s.prepare_publication()
        self.event.set()
        with self.assertRaises(Cancelled):s.publish()
        self.assertEqual(list((self.store/'knowledge').glob('*.json')),[])

    def test_mutating_prepared_record_and_wrong_owner_rejected(self):
        s=self.finished();s.prepare_publication()
        with self.assertRaises(InvestigationError):
            InvestigationMemory(self.store).commit(s.target,s.prepared,self.event,self.deadline)
        s.prepared.record['coverage']=['fake-live']
        with self.assertRaises(InvestigationError):s.publish()

    def test_static_evidence_cannot_promote_verified_procedure(self):
        s=self.finished();item=deepcopy(s.findings[0]);item['claim_type']='verified_procedure'
        with self.assertRaises(InvestigationError):validate_finding(item,s.evidence.records)

    def procedure(self,session):
        # Typed host evidence fixtures; this test is SOURCE, not real UI proof.
        refs=[session.evidence.add_json({'expected':True},kind='verification-fixture',
                origin='host-verification',level='LIVE')['evidence_id'] for _ in range(2)]
        return {'claim_id':'procedure.open_settings','claim':'Test prosedürü.',
            'claim_type':'verified_procedure','evidence_ids':refs,'counter_evidence_ids':[],
            'confidence_basis':'Two host verification fixtures.','reproducible':True,'limitations':['SOURCE test fixture'],
            'procedure':{'steps':[{'operation':'find_control','locator':{'automation_id':'settings'}},
                                  {'operation':'click_control','locator':{'automation_id':'settings'}}],
                         'preconditions':{'target_sha256':session.target.sha256,'required_grants':['desktop_input']},
                         'success_check':{'operation':'verify_control','expected':True}}}

    def test_verified_procedure_still_needs_current_target_and_grant(self):
        s=self.session();finding=self.procedure(s)
        s.accept_analysis({'schema_version':1,'target':s.target.as_dict(),'capabilities_used':['recipe'],
                           'findings':[finding]},executed_capabilities=['recipe'])
        s.finish([]);record=s.publish()
        self.assertEqual(InvestigationMemory.procedure_candidates(record,target_sha256=s.target.sha256,current_grants=[]),[])
        self.assertEqual(len(InvestigationMemory.procedure_candidates(record,target_sha256=s.target.sha256,current_grants=['desktop_input'])),1)
        self.assertEqual(InvestigationMemory.procedure_candidates(record,target_sha256='0'*64,current_grants=['desktop_input']),[])

    def test_arbitrary_command_and_traversal_cannot_be_a_learned_step(self):
        s=self.session();finding=self.procedure(s)
        for step in [{'operation':'shell','command':'anything'},
                     {'operation':'read_scoped_file','locator':{'relative_file':'../private'}},
                     {'operation':'set_control_value','value_ref':'a b'}]:
            finding['procedure']['steps']=[step]
            with self.assertRaises(InvestigationError):validate_finding(finding,s.evidence.records)

    def test_model_claim_cannot_invent_an_evidence_or_capability(self):
        s=self.session();finding=self.procedure(s)
        payload={'schema_version':1,'target':s.target.as_dict(),'capabilities_used':['not-executed'], 'findings':[finding]}
        with self.assertRaises(InvestigationError):s.accept_analysis(payload,executed_capabilities=[])
        payload['capabilities_used']=[];finding['evidence_ids']=['unknown']
        with self.assertRaises(InvestigationError):s.accept_analysis(payload,executed_capabilities=[])

    def test_later_failed_verification_invalidates_old_successful_recipe(self):
        first=self.session();finding=self.procedure(first)
        first.accept_analysis({'schema_version':1,'target':first.target.as_dict(),'capabilities_used':[],
                               'findings':[finding]},executed_capabilities=[])
        first.finish([]);first.publish()
        next_run=self.session()
        evidence=next_run.evidence.add_json({'success':False},kind='failed-verification-fixture',
                                            origin='host-verification',level='LIVE')
        next_run.memory.record_failed_verification(next_run.target,finding['claim_id'],evidence,self.event,self.deadline)
        current=self.session().previous
        self.assertIn(finding['claim_id'],current['invalidated_claim_ids'])
        self.assertEqual(InvestigationMemory.procedure_candidates(current,target_sha256=first.target.sha256,current_grants=['desktop_input']),[])

    def test_cancel_during_prepare_never_commits_memory(self):
        entered, release = threading.Event(), threading.Event()
        class SlowService(ArtifactDiagnosticsService):
            def _on_completed(inner,identity,snapshot):
                super()._on_completed(identity,snapshot)
                entered.set();release.wait(3)
        rea=Mock();rea.inspect.return_value={'status':'NOT_TESTED','used':False,'message':'source double'}
        service=SlowService(self.target_path,knowledge=False,rea=rea,reports=self.root/'reports',investigation_root=self.store)
        self.addCleanup(service.shutdown)
        job=service.start()
        try:
            self.assertTrue(entered.wait(3))
            service.cancel(job['id'])
        finally:release.set();service.threads[job['id']].join(3)
        self.assertEqual(service.status(job['id'])['state'],'cancelled')
        self.assertEqual(list((self.store/'knowledge').glob('*.json')),[])

    def test_existing_diagnostics_owns_new_evidence_worker(self):
        rea=Mock();rea.inspect.return_value={'status':'NOT_TESTED','used':False,'message':'source double'}
        service=ArtifactDiagnosticsService(self.target_path,knowledge=False,rea=rea,reports=self.root/'reports',investigation_root=self.store)
        self.addCleanup(service.shutdown)
        job=service.start();service.threads[job['id']].join(3)
        result=service.status(job['id'])
        self.assertEqual(result['state'],'completed')
        self.assertTrue(result['investigation_knowledge_saved'])
        self.assertGreater(result['investigation']['evidence_count'],0)
        self.assertEqual(len(service.threads),1)
        self.assertEqual(len(list((self.store/'knowledge').glob('*.json'))),1)


if __name__=='__main__': unittest.main()
