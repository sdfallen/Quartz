"""Evidence provenance, independence, idempotency and cache-hit context.

Closes the handoff gaps with real files and negative/mutation cases. These are
SOURCE/STATIC and local-persistence tests; no binary is executed and no live
application or UI is driven."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

from core.investigation.contracts import InvestigationError, Target, validate_finding
from core.investigation.evidence import EvidenceRepository
from core.investigation.memory import InvestigationMemory
from core.investigation.session import InvestigationSession
from core.application_knowledge import ApplicationKnowledge, ApplicationLearning
from core.artifact_diagnostics import ArtifactDiagnosticsService
from tests.test_rea_learning import pe_bytes


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target_path = self.root / 'subject.exe'
        self.target_path.write_bytes(pe_bytes())
        self.event = threading.Event()
        self.deadline = time.monotonic() + 20
        self.store = self.root / 'private-evidence'

    def session(self, **kw):
        return InvestigationSession(self.target_path, root=self.store, event=self.event,
            deadline=self.deadline, tool_identity=kw.pop('tool_identity', {'version': 'integrity-test'}), **kw)

    def finished(self):
        s = self.session()
        s.finish([{'id': 'artifact', 'status': 'PASS', 'evidence': {'sha256': s.target.sha256}},
                  {'id': 'pe', 'status': 'PASS', 'evidence': {'architecture': 'x64'}}])
        return s

    def knowledge_file(self):
        return next((self.store / 'knowledge').glob('*.json'))

    def procedure(self, session, *, dup=False):
        refs = [session.evidence.add_json({'run': i}, kind='verification-fixture',
                origin='host-verification', level='LIVE')['evidence_id'] for i in range(2)]
        if dup:
            refs = [refs[0], refs[0]]
        return {'claim_id': 'procedure.open_settings', 'claim': 'Test prosedürü.',
                'claim_type': 'verified_procedure', 'evidence_ids': refs, 'counter_evidence_ids': [],
                'confidence_basis': 'Two host verification fixtures.', 'reproducible': True,
                'limitations': ['SOURCE fixture'],
                'procedure': {'steps': [{'operation': 'find_control', 'locator': {'automation_id': 'settings'}}],
                              'preconditions': {'target_sha256': session.target.sha256, 'required_grants': ['desktop_input']},
                              'success_check': {'operation': 'verify_control', 'expected': True}}}


class ManifestAttestation(Base):
    """Gap 1: hashing the artifact is not enough; the record's level/origin must
    match the session manifest, so editing only the portable knowledge JSON can
    never promote static evidence to host-verified."""

    def test_editing_knowledge_level_and_origin_does_not_promote(self):
        s = self.finished(); s.publish()
        path = self.knowledge_file()
        record = json.loads(path.read_text())
        # Flip every stored evidence entry to look like a live host verification
        # without touching the artifact bytes (digest stays valid).
        for item in record['evidence'].values():
            item['level'] = 'LIVE'
            item['origin'] = 'host-verification'
        path.write_text(json.dumps(record))
        # The manifest still says SOURCE/host-static-parser, so the tampered
        # record is a cache miss rather than a trusted live record.
        self.assertIsNone(self.session().previous)

    def test_verify_record_rejects_mismatched_kind(self):
        s = self.finished()
        record = deepcopy(next(iter(s.evidence.records.values())))
        record['kind'] = 'rea-full-artifact'  # manifest says host-static-checks
        with self.assertRaises(InvestigationError):
            EvidenceRepository.verify_record(self.store, record, self.event, self.deadline)

    def test_missing_manifest_is_not_verifiable(self):
        s = self.finished()
        record = deepcopy(next(iter(s.evidence.records.values())))
        (self.store / 'evidence' / s.evidence.id / 'manifest.json').unlink()
        with self.assertRaises(InvestigationError):
            EvidenceRepository.verify_record(self.store, record, self.event, self.deadline)


class Independence(Base):
    """Gap 2: citing one artifact twice is not two independent verifications."""

    def test_duplicate_evidence_ref_rejected(self):
        s = self.session()
        with self.assertRaises(InvestigationError):
            validate_finding(self.procedure(s, dup=True), s.evidence.records)

    def test_two_distinct_live_refs_accepted(self):
        s = self.session()
        validate_finding(self.procedure(s), s.evidence.records)  # does not raise


class ForgedInventory(Base):
    """Gap 4: a reusable inventory can only claim coverage it actually carries."""

    def test_inventory_without_coverage_is_rejected(self):
        s = self.finished()
        s.report['reusable_inventory'] = {'status': 'PASS', 'message': 'forged',
                                          'evidence': {'artifact_sha256': s.target.sha256,
                                                       'source_evidence_sha256': '0' * 64}}
        # coverage lacks static_inventory and no rea-full-artifact backs it
        with self.assertRaises(InvestigationError):
            s.memory.prepare(s.target, s.question, s.tool_fingerprint, s.report, self.event, self.deadline)

    def test_nan_in_report_is_a_typed_failure(self):
        s = self.finished()
        s.report['findings'][0]['extra'] = float('nan')
        with self.assertRaises(InvestigationError):
            s.memory.prepare(s.target, s.question, s.tool_fingerprint, s.report, self.event, self.deadline)


class Idempotency(Base):
    """Gap 6: republishing an identical report must not grow the store."""

    def test_identical_republish_is_deduped(self):
        s = self.finished()
        first = s.publish()
        second = s.publish()
        self.assertEqual(first['observed_at'], second['observed_at'])
        self.assertEqual(len(list((self.store / 'knowledge').glob('*.json'))), 1)

    def test_concurrent_identical_commit_writes_once(self):
        s = self.finished(); s.prepare_publication()
        barrier = threading.Barrier(4)
        errors = []

        def worker():
            try:
                barrier.wait(); s.memory.commit(s.target, s.prepared, self.event, self.deadline)
            except Exception as exc:  # noqa: BLE001 - surfaced via errors list
                errors.append(exc)
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join(5)
        self.assertEqual(errors, [])
        self.assertEqual(len(list((self.store / 'knowledge').glob('*.json'))), 1)


class CacheHitContext(Base):
    """Gap 3: a cache hit in ApplicationLearning still surfaces prior context
    instead of silently dropping it because the service never re-ran."""

    def _diagnose(self, app_store, inv_root):
        rea = Mock(); rea.inspect.return_value = {'status': 'NOT_TESTED', 'used': False, 'message': 'source double'}
        service = ArtifactDiagnosticsService(self.target_path, knowledge=app_store, rea=rea,
            reports=self.root / 'reports', investigation_root=inv_root)
        self.addCleanup(service.shutdown)
        job = service.start(); service.threads[job['id']].join(5)
        self.assertEqual(service.status(job['id'])['state'], 'completed')

    def test_cache_hit_recovers_investigation_context(self):
        app_store = ApplicationKnowledge(self.root / 'app-knowledge')
        inv_root = self.root / 'app-investigations'
        self._diagnose(app_store, inv_root)
        self.assertIsNotNone(app_store.get(self.target_path))  # cache will hit

        learning = ApplicationLearning(app_store.root, investigation_root=inv_root)
        self.addCleanup(learning.stop)
        learning.start(self.target_path)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and learning.context()[0]['state'] in {'queued', 'running'}:
            time.sleep(0.02)
        entry = learning.context()[0]
        self.assertEqual(entry['state'], 'completed')
        context = entry.get('investigation')
        self.assertIsNotNone(context)  # not dropped on the cache-hit path
        self.assertIs(context['instruction_authority'], False)
        self.assertTrue(context['requires_current_grant'])
        self.assertNotIn(str(self.root), json.dumps(context))  # path-free

    def test_absent_investigation_root_is_backward_compatible(self):
        app_store = ApplicationKnowledge(self.root / 'app-knowledge')
        self._diagnose(app_store, self.root / 'app-investigations')
        learning = ApplicationLearning(app_store.root, investigation_root=self.root / 'does-not-exist')
        self.addCleanup(learning.stop)
        learning.start(self.target_path)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and learning.context()[0]['state'] in {'queued', 'running'}:
            time.sleep(0.02)
        entry = learning.context()[0]
        self.assertEqual(entry['state'], 'completed')
        self.assertNotIn('investigation', entry)  # no context, but no error


if __name__ == '__main__':
    unittest.main()
