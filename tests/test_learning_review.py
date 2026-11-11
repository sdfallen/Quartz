"""Windows review regressions: actual files, streaming, attestation and locks."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tracemalloc
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock

from core.investigation.contracts import Cancelled, InvestigationError, validate_finding
from core.investigation.evidence import EvidenceRepository
from core.investigation.learning import assess_record, finding_quality, separate_by_type
from core.investigation.memory import InvestigationMemory
from core.investigation.session import InvestigationSession
from core.application_knowledge import ApplicationLearning
from core.artifact_diagnostics import ArtifactDiagnosticsService
from tests.test_learning_integrity import Base


class LearningReview(Base):
    def _committed_state(self):
        s = self.session()
        existing = s.evidence.add_bytes(b'existing committed evidence', kind='review-fixture', origin='test')
        return s, existing, deepcopy(s.evidence.records), s.evidence.bytes

    def _assert_old_evidence_preserved(self, s, existing, records, count):
        self.event.clear()
        self.assertEqual(s.evidence.records, records)
        self.assertEqual(s.evidence.bytes, count)
        disk = json.loads((s.evidence.directory / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(disk['records'], records)
        self.assertEqual(len(list(s.evidence.directory.glob('*.artifact'))), 1)
        self.assertEqual(EvidenceRepository.verify_record(self.store, existing, self.event, self.deadline).read_bytes(), b'existing committed evidence')

    @staticmethod
    def _write_publication(repository, as_json):
        if as_json:
            return repository.add_json({'new': 'cancelled or failed'}, kind='review-fixture', origin='test')
        return repository.add_bytes(b'new cancelled or failed evidence', kind='review-fixture', origin='test')

    def test_add_bytes_and_json_cancel_after_write_remove_only_new_artifact(self):
        from core.investigation import evidence
        for as_json in (False, True):
            with self.subTest(as_json=as_json):
                s, existing, records, count = self._committed_state()
                original = evidence.os.fsync
                def cancel_after_fsync(handle):
                    original(handle)
                    self.event.set()
                with patch.object(evidence.os, 'fsync', side_effect=cancel_after_fsync):
                    with self.assertRaises(Cancelled):
                        self._write_publication(s.evidence, as_json)
                self._assert_old_evidence_preserved(s, existing, records, count)

    def test_late_cancellation_after_manifest_commit_rolls_back_disk_and_counters(self):
        for as_json in (False, True):
            with self.subTest(as_json=as_json):
                s, existing, records, count = self._committed_state()
                original, calls = s.evidence._persist, []
                def persist_then_cancel():
                    original()
                    calls.append(1)
                    if len(calls) == 1:
                        self.event.set()
                with patch.object(s.evidence, '_persist', side_effect=persist_then_cancel):
                    with self.assertRaises(Cancelled):
                        self._write_publication(s.evidence, as_json)
                self.assertEqual(len(calls), 2)
                self._assert_old_evidence_preserved(s, existing, records, count)

    def test_publication_fsync_error_is_typed_and_preserves_existing_evidence(self):
        from core.investigation import evidence
        for as_json in (False, True):
            with self.subTest(as_json=as_json):
                s, existing, records, count = self._committed_state()
                with patch.object(evidence.os, 'fsync', side_effect=OSError('test fsync failure')):
                    with self.assertRaisesRegex(InvestigationError, 'artifact-publication-failed'):
                        self._write_publication(s.evidence, as_json)
                self._assert_old_evidence_preserved(s, existing, records, count)

    def test_manifest_fail_before_or_after_commit_rolls_back_owned_record_and_file(self):
        for as_json in (False, True):
            for after_commit in (False, True):
                with self.subTest(as_json=as_json, after_commit=after_commit):
                    s, existing, records, count = self._committed_state()
                    original, calls = s.evidence._persist, []
                    def fail_once():
                        calls.append(1)
                        if len(calls) == 1:
                            if after_commit:
                                original()
                            raise OSError('test persist failure')
                        original()
                    with patch.object(s.evidence, '_persist', side_effect=fail_once):
                        with self.assertRaisesRegex(InvestigationError, 'artifact-publication-failed'):
                            self._write_publication(s.evidence, as_json)
                    self._assert_old_evidence_preserved(s, existing, records, count)

    def test_uuid_collision_does_not_delete_committed_or_preexisting_files(self):
        from core.investigation import evidence
        s, existing, records, count = self._committed_state()
        with patch.object(evidence.uuid, 'uuid4', return_value=SimpleNamespace(hex=existing['evidence_id'])):
            with self.assertRaisesRegex(InvestigationError, 'evidence-identity-collision'):
                self._write_publication(s.evidence, False)
        self._assert_old_evidence_preserved(s, existing, records, count)
        untracked = s.evidence.directory / ('f' * 32 + '.artifact')
        untracked.write_bytes(b'preexisting file owned by an earlier call')
        with patch.object(evidence.uuid, 'uuid4', return_value=SimpleNamespace(hex='f' * 32)):
            with self.assertRaisesRegex(InvestigationError, 'artifact-publication-failed'):
                self._write_publication(s.evidence, True)
            source = self.root / 'collision-source.bin'
            source.write_bytes(b'stream payload')
            with self.assertRaisesRegex(InvestigationError, 'artifact-publication-failed'):
                s.evidence.ingest_file(source, source_root=self.root, expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(untracked.read_bytes(), b'preexisting file owned by an earlier call')
        self.assertEqual(s.evidence.records, records)
        self.assertEqual(s.evidence.bytes, count)

    def test_cleanup_denial_is_a_typed_failure_and_never_claimed_success(self):
        from core.investigation import evidence
        s, existing, records, count = self._committed_state()
        original = evidence.os.fsync
        def cancel_after_fsync(handle):
            original(handle)
            self.event.set()
        with patch.object(evidence.os, 'fsync', side_effect=cancel_after_fsync), patch.object(Path, 'unlink', side_effect=PermissionError('test cleanup denial')):
            with self.assertRaisesRegex(InvestigationError, 'evidence-cleanup-failed'):
                self._write_publication(s.evidence, False)
        self.assertEqual(s.evidence.records, records)
        self.assertEqual(s.evidence.bytes, count)
        self.assertEqual(len(list(s.evidence.directory.glob('*.artifact'))), 2)

    def test_manifest_rollback_failure_is_typed_but_new_artifact_is_removed(self):
        for as_json in (False, True):
            with self.subTest(as_json=as_json):
                s, existing, records, count = self._committed_state()
                with patch.object(s.evidence, '_persist', side_effect=OSError('test repeated persist failure')):
                    with self.assertRaisesRegex(InvestigationError, 'evidence-manifest-rollback-failed'):
                        self._write_publication(s.evidence, as_json)
                self._assert_old_evidence_preserved(s, existing, records, count)

    def test_small_ingestion_streams_without_64mib_allocation(self):
        s = self.session()
        source = self.root / 'small.bin'
        source.write_bytes(b'x' * 3584)
        tracemalloc.start()
        try:
            item = s.evidence.ingest_file(source, source_root=self.root,
                expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 8 * 1024 * 1024, f'3.5KiB capture allocated {peak} bytes')
        self.assertEqual(item['bytes'], 3584)
        saved = EvidenceRepository.verify_record(self.store, item, self.event, self.deadline)
        self.assertEqual(saved.read_bytes(), source.read_bytes())

    def test_stream_mismatch_and_cancel_delete_partial_artifact(self):
        s = self.session()
        source = self.root / 'stream.bin'
        source.write_bytes(b'x' * (1024 * 1024))
        with self.assertRaises(InvestigationError):
            s.evidence.ingest_file(source, source_root=self.root, expected_sha256='0' * 64)
        self.assertEqual(list(s.evidence.directory.glob('*.artifact')), [])
        from core.investigation import evidence
        original, calls = evidence.guard, []
        def cancel_at_copy(event, deadline):
            calls.append(1)
            if len(calls) == 2:
                event.set()
            return original(event, deadline)
        with patch.object(evidence, 'guard', side_effect=cancel_at_copy):
            with self.assertRaises(Cancelled):
                s.evidence.ingest_file(source, source_root=self.root,
                    expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(list(s.evidence.directory.glob('*.artifact')), [])
        self.assertEqual(s.evidence.records, {})

    def test_attestation_binds_path_scope_timestamp_and_session(self):
        s = self.finished()
        item = next(iter(s.evidence.records.values()))
        for field, value in [('scope', ['execute_target']), ('observed_at', item['observed_at'] - 10)]:
            with self.subTest(field=field):
                forged = deepcopy(item)
                forged[field] = value
                with self.assertRaises(InvestigationError):
                    EvidenceRepository.verify_record(self.store, forged, self.event, self.deadline)
        manifest = s.evidence.directory / 'manifest.json'
        original = json.loads(manifest.read_text(encoding='utf-8'))
        corrupted = deepcopy(original)
        corrupted['investigation_id'] = '0' * 32
        manifest.write_text(json.dumps(corrupted), encoding='utf-8')
        with self.assertRaises(InvestigationError):
            EvidenceRepository.verify_record(self.store, item, self.event, self.deadline)

    def test_nested_malformed_reload_is_cache_miss(self):
        s = self.finished()
        s.publish()
        path = self.knowledge_file()
        original = json.loads(path.read_text(encoding='utf-8'))
        mutations = [dict(original, coverage=None), dict(original, coverage=['static_inventory']),
            dict(original, limitations={}), dict(original, evidence={'malformed': []}),
            dict(original, observed_at=float('nan')), dict(original, reusable_inventory={'status': 'PASS', 'evidence': []})]
        for value in mutations:
            with self.subTest(value=value.keys()):
                path.write_text(json.dumps(value), encoding='utf-8')
                self.assertIsNone(s.memory.lookup(s.target, s.question, s.tool_fingerprint, self.event, self.deadline))
                self.assertIsNone(s.memory.context_for_target(s.target, self.event, self.deadline))

    def test_nested_malformed_publication_is_typed_failure(self):
        s = self.finished()
        for change in [{'target': []}, {'evidence': {'bad': []}}, {'limitations': None}]:
            with self.subTest(change=change):
                report = deepcopy(s.report)
                report.update(change)
                with self.assertRaises(InvestigationError):
                    s.memory.prepare(s.target, s.question, s.tool_fingerprint, report, self.event, self.deadline)

    def _published_procedure(self):
        s = self.session()
        finding = self.procedure(s)
        s.accept_analysis({'schema_version': 1, 'target': s.target.as_dict(), 'capabilities_used': [],
            'findings': [finding]}, executed_capabilities=[])
        s.finish([])
        s.publish()
        return s, finding

    def test_identical_republish_preserves_failed_outcome(self):
        s, finding = self._published_procedure()
        later = self.session()
        failure = later.evidence.add_json({'success': False}, kind='verification-fixture', origin='host-verification', level='LIVE')
        later.memory.record_failed_verification(later.target, finding['claim_id'], failure, self.event, self.deadline)
        s.publish()
        current = s.memory.lookup(s.target, s.question, s.tool_fingerprint, self.event, self.deadline)
        self.assertIn(finding['claim_id'], current['invalidated_claim_ids'])
        self.assertEqual(InvestigationMemory.procedure_candidates(current, target_sha256=s.target.sha256, current_grants=['desktop_input']), [])
        self.assertEqual(len(list((self.store / 'knowledge').glob('*.json'))), 1)

    def test_nan_or_rewound_failure_timestamp_cannot_restore_procedure(self):
        s, finding = self._published_procedure()
        later = self.session()
        failure = later.evidence.add_json({'success': False}, kind='verification-fixture', origin='host-verification', level='LIVE')
        later.memory.record_failed_verification(later.target, finding['claim_id'], failure, self.event, self.deadline)
        path = next((self.store / 'outcomes').glob('*.json'))
        original = json.loads(path.read_text(encoding='utf-8'))
        for timestamp in (float('nan'), 0):
            value = dict(original, observed_at=timestamp)
            path.write_text(json.dumps(value), encoding='utf-8')
            current = s.memory.lookup(s.target, s.question, s.tool_fingerprint, self.event, self.deadline)
            self.assertIn(finding['claim_id'], current['invalidated_claim_ids'])

    def test_new_observation_cannot_republish_failed_old_procedure_as_verified(self):
        s, finding = self._published_procedure()
        later = self.session()
        failed = later.evidence.add_json({'success': False}, kind='verification-fixture', origin='host-verification', level='LIVE')
        later.memory.record_failed_verification(later.target, finding['claim_id'], failed, self.event, self.deadline)
        report = deepcopy(s.report)
        report['limitations'].append('New context does not reverify the old procedure.')
        s.memory.publish(s.target, s.question, s.tool_fingerprint, report, self.event, self.deadline)
        current = s.memory.lookup(s.target, s.question, s.tool_fingerprint, self.event, self.deadline)
        self.assertIn(finding['claim_id'], current['invalidated_claim_ids'])
        self.assertEqual(InvestigationMemory.procedure_candidates(current, target_sha256=s.target.sha256, current_grants=['desktop_input']), [])

    def test_older_failure_cannot_overwrite_later_failed_run(self):
        s, finding = self._published_procedure()
        later = self.session()
        old = later.evidence.add_json({'run': 1}, kind='verification-fixture', origin='host-verification', level='LIVE')
        new = later.evidence.add_json({'run': 2}, kind='verification-fixture', origin='host-verification', level='LIVE')
        later.memory.record_failed_verification(later.target, finding['claim_id'], new, self.event, self.deadline)
        later.memory.record_failed_verification(later.target, finding['claim_id'], old, self.event, self.deadline)
        outcome = json.loads(next((self.store / 'outcomes').glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(outcome['evidence']['evidence_id'], new['evidence_id'])

    def test_two_genuinely_new_verifications_can_restore_procedure_after_failure(self):
        s, finding = self._published_procedure()
        later = self.session()
        failed = later.evidence.add_json({'success': False}, kind='verification-fixture', origin='host-verification', level='LIVE')
        later.memory.record_failed_verification(later.target, finding['claim_id'], failed, self.event, self.deadline)
        fresh = [later.evidence.add_json({'new-run': i}, kind='verification-fixture', origin='host-verification', level='LIVE')['evidence_id'] for i in range(2)]
        report = deepcopy(s.report)
        report['evidence'].update(later.evidence.records)
        report['findings'][0]['evidence_ids'] = [finding['evidence_ids'][0], fresh[0]]
        s.memory.publish(s.target, s.question, s.tool_fingerprint, report, self.event, self.deadline)
        current = s.memory.lookup(s.target, s.question, s.tool_fingerprint, self.event, self.deadline)
        self.assertIn(finding['claim_id'], current['invalidated_claim_ids'])
        report['findings'][0]['evidence_ids'] = fresh
        s.memory.publish(s.target, s.question, s.tool_fingerprint, report, self.event, self.deadline)
        current = s.memory.lookup(s.target, s.question, s.tool_fingerprint, self.event, self.deadline)
        self.assertEqual(len(InvestigationMemory.procedure_candidates(current, target_sha256=s.target.sha256, current_grants=['desktop_input'])), 1)

    def test_dedupe_does_not_skip_changed_target_fence(self):
        s = self.finished()
        s.publish()
        self.target_path.write_bytes(b'changed after publication')
        with self.assertRaises(InvestigationError):
            s.publish()

    def test_success_check_is_as_typed_as_procedure_steps(self):
        s = self.session()
        finding = self.procedure(s)
        for success in [{'operation': 'verify_control', 'locator': [], 'expected': True},
                        {'operation': 'verify_control', 'expected': []},
                        {'operation': 'compare_digest', 'expected': True},
                        {'operation': 'verify_control', 'locator': {'relative_file': '../private'}, 'expected': True}]:
            finding['procedure']['success_check'] = success
            with self.assertRaises(InvestigationError):
                validate_finding(finding, s.evidence.records)

    def test_learning_nested_types_are_typed_failures_and_empty_observation_unverified(self):
        with self.assertRaises(ValueError):
            finding_quality({'evidence_ids': [[]]}, {})
        with self.assertRaises(ValueError):
            separate_by_type({'findings': {}}, maximum_per_type=10)
        with self.assertRaises(ValueError):
            assess_record({'invalidated_claim_ids': None})
        quality = finding_quality({'claim_type': 'observation'}, {})
        self.assertEqual(quality['tier'], 'unverified')

    def test_os_publication_lock_excludes_another_real_process(self):
        s = self.session()
        code = "from core.investigation.memory import InvestigationMemory; import sys\ntry:\n with InvestigationMemory(sys.argv[1])._publication():\n  print('unexpected-acquisition')\n  sys.exit(3)\nexcept OSError:\n print('blocked-by-os-lock')\n"
        with s.memory._publication():
            result = subprocess.run([sys.executable, '-B', '-c', code, str(self.store)],
                cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        self.assertIn(b'blocked-by-os-lock', result.stdout)

    def test_latest_context_scan_budget_counts_unrelated_records(self):
        s = self.finished()
        s.publish()
        original = self.knowledge_file()
        other = self.root / 'other.exe'
        other.write_bytes(self.target_path.read_bytes() + b'different target')
        another = InvestigationSession(other, root=self.store, event=self.event, deadline=self.deadline,
            tool_identity={'version': 'unrelated-context'})
        another.finish([])
        another.publish()
        newest = next(p for p in (self.store / 'knowledge').glob('*.json') if p != original)
        os.utime(original, ns=(1000000000, 1000000000))
        os.utime(newest, ns=(2000000000, 2000000000))
        self.assertIsNone(s.memory.context_for_target(s.target, self.event, self.deadline, maximum_scan=1))
        self.assertIsNotNone(s.memory.context_for_target(s.target, self.event, self.deadline, maximum_scan=2))

    def test_fresh_learning_uses_the_same_explicit_context_root_as_cache_hit(self):
        root = self.root / 'custom-investigations'
        learning = ApplicationLearning(self.root / 'application-cache', investigation_root=root)
        key = str(self.target_path)
        learning.jobs[key] = {'state': 'queued', 'knowledge': None}
        rea = Mock()
        rea.inspect.return_value = {'status': 'NOT_TESTED', 'used': False, 'message': 'SOURCE test double'}
        def construct(*args, **kwargs):
            kwargs['rea'] = rea
            return ArtifactDiagnosticsService(*args, **kwargs)
        with patch('core.application_knowledge.ArtifactDiagnosticsService', side_effect=construct):
            learning._work(self.target_path)
        self.assertEqual(learning.jobs[key]['state'], 'completed')
        self.assertTrue(list((root / 'knowledge').glob('*.json')))
        self.assertIsNotNone(learning._cached_investigation_context(self.target_path))


if __name__ == '__main__':
    unittest.main()
