"""Quality tiers derive from evidence structure, never from model prose."""
from pathlib import Path
import tempfile
import threading
import time
import unittest

from core.investigation.contracts import Target
from core.investigation.learning import assess_record, finding_quality, separate_by_type
from core.investigation.session import InvestigationSession
from tests.test_rea_learning import pe_bytes


class QualityBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target_path = self.root / 'subject.exe'; self.target_path.write_bytes(pe_bytes())
        self.event = threading.Event(); self.deadline = time.monotonic() + 20
        self.session = InvestigationSession(self.target_path, root=self.root / 'ev', event=self.event,
            deadline=self.deadline, tool_identity={'version': 'quality-test'})

    def live(self, n=2):
        return [self.session.evidence.add_json({'run': i}, kind='verification-fixture',
                origin='host-verification', level='LIVE')['evidence_id'] for i in range(n)]

    def source(self):
        return self.session.evidence.add_json({'x': 1}, kind='host-static-checks',
            origin='host-static-parser')['evidence_id']

    def verified(self):
        refs = self.live(2)
        return {'claim_id': 'procedure.open', 'claim': 'c', 'claim_type': 'verified_procedure',
                'evidence_ids': refs, 'counter_evidence_ids': [],
                'confidence_basis': 'model says great', 'reproducible': True, 'limitations': [],
                'procedure': {'steps': [{'operation': 'find_control', 'locator': {'automation_id': 's'}}],
                              'preconditions': {'target_sha256': self.session.target.sha256, 'required_grants': ['g']},
                              'success_check': {'operation': 'verify_control', 'expected': True}}}


class FindingQuality(QualityBase):
    def test_verified_tier_needs_two_independent_live(self):
        q = finding_quality(self.verified(), self.session.evidence.records)
        self.assertEqual(q['tier'], 'verified_procedure')
        self.assertEqual(q['basis']['independent_live_verifications'], 2)

    def test_model_confidence_text_never_sets_the_tier(self):
        # A hypothesis with glowing prose stays a hypothesis.
        f = {'claim_id': 'h.a', 'claim': 'c', 'claim_type': 'hypothesis', 'evidence_ids': [self.source()],
             'counter_evidence_ids': [], 'confidence_basis': 'absolutely certain, 100% proven',
             'reproducible': True, 'limitations': []}
        q = finding_quality(f, self.session.evidence.records)
        self.assertEqual(q['tier'], 'hypothesis')
        self.assertIn('hypothesis_not_verified', q['blocked_by'])
        self.assertEqual(q['stated_basis'], 'absolutely certain, 100% proven')

    def test_counter_evidence_marks_contradicted(self):
        counter = self.source()
        f = self.verified(); f['counter_evidence_ids'] = [counter]
        q = finding_quality(f, self.session.evidence.records)
        self.assertEqual(q['tier'], 'contradicted')
        self.assertIn('has_counter_evidence', q['blocked_by'])

    def test_single_live_is_not_verified(self):
        f = self.verified(); f['evidence_ids'] = self.live(1)
        q = finding_quality(f, self.session.evidence.records)
        self.assertEqual(q['tier'], 'unverified')
        self.assertIn('needs_two_independent_live_verifications', q['blocked_by'])

    def test_observation_tier(self):
        f = {'claim_id': 'o.a', 'claim': 'c', 'claim_type': 'observation', 'evidence_ids': [self.source()],
             'counter_evidence_ids': [], 'confidence_basis': 'b', 'reproducible': True, 'limitations': []}
        self.assertEqual(finding_quality(f, self.session.evidence.records)['tier'], 'observed')

    def test_no_numeric_confidence_percentage(self):
        q = finding_quality(self.verified(), self.session.evidence.records)
        self.assertNotIn('confidence', q['basis'])
        self.assertNotIn('score', q)


class RecordAssessment(QualityBase):
    def test_assess_counts_and_reusability(self):
        verified = self.verified()
        hypothesis = {'claim_id': 'h.b', 'claim': 'c', 'claim_type': 'hypothesis',
                      'evidence_ids': [self.source()], 'counter_evidence_ids': [],
                      'confidence_basis': 'b', 'reproducible': False, 'limitations': []}
        record = {'target_sha256': self.session.target.sha256,
                  'evidence': self.session.evidence.records,
                  'findings': [verified, hypothesis]}
        assessed = assess_record(record)
        self.assertEqual(assessed['tier_counts']['verified_procedure'], 1)
        self.assertEqual(assessed['tier_counts']['hypothesis'], 1)
        self.assertTrue(assessed['has_reusable_procedure'])
        self.assertIs(assessed['instruction_authority'], False)

    def test_separate_by_type_keeps_hypotheses_apart(self):
        verified = self.verified()
        hypothesis = {'claim_id': 'h.b', 'claim': 'c', 'claim_type': 'hypothesis',
                      'evidence_ids': [self.source()], 'counter_evidence_ids': [],
                      'confidence_basis': 'b', 'reproducible': True, 'limitations': []}
        buckets = separate_by_type({'target_sha256': self.session.target.sha256,
                                    'evidence': self.session.evidence.records,
                                    'findings': [verified, hypothesis]})
        self.assertEqual([e['claim_id'] for e in buckets['verified_procedures']], ['procedure.open'])
        self.assertEqual([e['claim_id'] for e in buckets['hypotheses']], ['h.b'])
        self.assertEqual(buckets['observations'], [])

    def test_mislabeled_procedure_is_not_reusable(self):
        # Record claims verified_procedure but cites only one live verification:
        # it must not appear among reusable procedures.
        weak = self.verified(); weak['evidence_ids'] = self.live(1)
        buckets = separate_by_type({'target_sha256': self.session.target.sha256,
                                    'evidence': self.session.evidence.records, 'findings': [weak]})
        self.assertEqual(buckets['verified_procedures'], [])


if __name__ == '__main__':
    unittest.main()
