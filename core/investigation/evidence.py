"""Immutable bounded artifacts. Reports are data, never instructions or grants."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import threading
import time
import uuid

from core.atomic_json import atomic_write_json
from .contracts import EFFECTS, InvestigationError, LEVELS, SHA256, bounded_json, digest_file, fingerprint, guard, safe_path


class EvidenceRepository:
    MAX_FILE_BYTES = 64 * 1024 * 1024
    MAX_TOTAL_BYTES = 256 * 1024 * 1024
    MAX_ARTIFACTS = 128
    MAX_SESSIONS = 256

    def __init__(self, root, target, event, deadline, *, investigation_id=None):
        self.root = safe_path(root, exists=False)
        self.target = target
        self.event, self.deadline = event, deadline
        self.id = investigation_id or uuid.uuid4().hex
        if len(self.id) != 32 or any(c not in '0123456789abcdef' for c in self.id):
            raise InvestigationError('invalid-investigation-id')
        self.directory = self.root / 'evidence' / self.id
        parent = safe_path(self.directory.parent, exists=False)
        if parent.exists() and len(list(parent.iterdir())) >= self.MAX_SESSIONS:
            raise InvestigationError('evidence-store-limit')
        self.directory.mkdir(parents=True, exist_ok=False)
        self.lock = threading.RLock()
        self.records = {}
        self.bytes = 0
        self.state = 'running'
        self._persist()

    def _persist(self):
        safe_path(self.directory)
        atomic_write_json(self.directory / 'manifest.json', {
            'schema_version': 1, 'investigation_id': self.id, 'state': self.state,
            'target_sha256': self.target.sha256, 'records': self.records,
            'instruction_authority': False})

    def _rollback_publication(self, path, identity, size, *, created, recorded):
        """Called under the owner lock, only for this call's newly created file."""
        manifest_error = cleanup_error = False
        if recorded:
            self.records.pop(identity, None)
            self.bytes -= size
            try:
                # Also repairs a persist which completed before a late failure
                # or cancellation. Rollback is allowed after Stop.
                self._persist()
            except Exception:
                manifest_error = True
        if created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                cleanup_error = True
        if cleanup_error and manifest_error:
            raise InvestigationError('evidence-cleanup-and-manifest-rollback-failed')
        if cleanup_error:
            raise InvestigationError('evidence-cleanup-failed')
        if manifest_error:
            raise InvestigationError('evidence-manifest-rollback-failed')

    def add_bytes(self, content, *, kind, origin, level='SOURCE'):
        if not isinstance(content, bytes):
            raise InvestigationError('invalid-artifact-content')
        with self.lock:
            guard(self.event, self.deadline)
            if self.state != 'running' or level not in LEVELS:
                raise InvestigationError('closed-evidence')
            if level != 'SOURCE' and origin != 'host-verification':
                raise InvestigationError('untrusted-evidence-level')
            if not isinstance(kind, str) or len(kind) > 96 or not isinstance(origin, str) or len(origin) > 160:
                raise InvestigationError('invalid-provenance')
            if len(content) > self.MAX_FILE_BYTES or self.bytes + len(content) > self.MAX_TOTAL_BYTES or len(self.records) >= self.MAX_ARTIFACTS:
                raise InvestigationError('evidence-limit')
            identity = uuid.uuid4().hex
            if identity in self.records:
                raise InvestigationError('evidence-identity-collision')
            name = identity + '.artifact'
            path = safe_path(self.directory / name, exists=False)
            created = recorded = False
            try:
                with path.open('xb') as stream:
                    created = True
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                guard(self.event, self.deadline)
                digest = hashlib.sha256(content).hexdigest()
                if digest_file(path, self.event, self.deadline, maximum=self.MAX_FILE_BYTES) != digest:
                    raise InvestigationError('artifact-write-mismatch')
                record = {'evidence_id': identity, 'target_fingerprint': self.target.sha256,
                          'kind': kind, 'origin': origin, 'level': level, 'observed_at': time.time(),
                          'artifact_relative_path': f'evidence/{self.id}/{name}',
                          'digest': digest, 'bytes': len(content), 'scope': list(self.target.approved_scope)}
                self.records[identity] = record
                self.bytes += len(content)
                recorded = True
                self._persist()
                guard(self.event, self.deadline)
                return deepcopy(record)
            except BaseException as exc:
                try:
                    self._rollback_publication(path, identity, len(content), created=created, recorded=recorded)
                except InvestigationError as cleanup:
                    raise cleanup from exc
                if isinstance(exc, Exception) and not isinstance(exc, InvestigationError):
                    raise InvestigationError('artifact-publication-failed') from exc
                raise

    def add_json(self, value, **kwargs):
        value = bounded_json(value, maximum=2 * 1024 * 1024)
        return self.add_bytes(json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), **kwargs)

    def ingest_file(self, source, *, source_root, expected_sha256, kind='tool-artifact', origin='rea'):
        source_root = safe_path(source_root)
        source = safe_path(source)
        if source_root not in source.parents:
            raise InvestigationError('artifact-outside-workspace')
        if not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256):
            raise InvestigationError('invalid-artifact-digest')
        before = fingerprint(source)
        with self.lock:
            guard(self.event, self.deadline)
            if self.state != 'running': raise InvestigationError('closed-evidence')
            if not isinstance(kind, str) or len(kind) > 96 or not isinstance(origin, str) or len(origin) > 160:
                raise InvestigationError('invalid-provenance')
            if (not source.is_file() or before[2] > self.MAX_FILE_BYTES or self.bytes + before[2] > self.MAX_TOTAL_BYTES
                    or len(self.records) >= self.MAX_ARTIFACTS):
                raise InvestigationError('evidence-limit')
            identity = uuid.uuid4().hex
            if identity in self.records:
                raise InvestigationError('evidence-identity-collision')
            path = safe_path(self.directory / (identity + '.artifact'), exists=False)
            digest, size = hashlib.sha256(), 0
            created = recorded = False
            try:
                # Stream directly into the owned artifact. read(MAX+1) allocated
                # 64MiB even for a 3KiB snapshot on Windows CPython.
                with source.open('rb') as incoming, path.open('xb') as outgoing:
                    created = True
                    while block := incoming.read(256 * 1024):
                        guard(self.event, self.deadline)
                        size += len(block)
                        if size > before[2] or size > self.MAX_FILE_BYTES or self.bytes + size > self.MAX_TOTAL_BYTES:
                            raise InvestigationError('evidence-limit')
                        digest.update(block)
                        outgoing.write(block)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                guard(self.event, self.deadline)
                if size != before[2] or fingerprint(source) != before:
                    raise InvestigationError('artifact-changed')
                if digest.hexdigest() != expected_sha256:
                    raise InvestigationError('artifact-digest-mismatch')
                if digest_file(path, self.event, self.deadline, maximum=self.MAX_FILE_BYTES) != expected_sha256:
                    raise InvestigationError('artifact-write-mismatch')
                record = {'evidence_id': identity, 'target_fingerprint': self.target.sha256,
                    'kind': kind, 'origin': origin, 'level': 'SOURCE', 'observed_at': time.time(),
                    'artifact_relative_path': f'evidence/{self.id}/{identity}.artifact',
                    'digest': expected_sha256, 'bytes': size, 'scope': list(self.target.approved_scope)}
                self.records[identity] = record
                self.bytes += size
                recorded = True
                self._persist()
                guard(self.event, self.deadline)
                return deepcopy(record)
            except BaseException as exc:
                try:
                    self._rollback_publication(path, identity, size, created=created, recorded=recorded)
                except InvestigationError as cleanup:
                    raise cleanup from exc
                if isinstance(exc, Exception) and not isinstance(exc, InvestigationError):
                    raise InvestigationError('artifact-publication-failed') from exc
                raise

    def finalize(self, state):
        with self.lock:
            if self.state != 'running':
                if state == self.state:
                    return
                raise InvestigationError('evidence-already-finalized')
            if state not in {'completed', 'cancelled', 'failed'}:
                raise InvestigationError('invalid-final-state')
            if state == 'completed':
                guard(self.event, self.deadline)
                self.target.revalidate(self.event, self.deadline)
            self.state = state
            self._persist()

    # Provenance fields fixed when the artifact was produced; the trust root for
    # them is the per-session manifest, not the portable knowledge JSON.
    ATTESTED_FIELDS = ('evidence_id', 'level', 'origin', 'kind', 'digest', 'bytes', 'target_fingerprint',
                       'artifact_relative_path', 'scope', 'observed_at')

    @staticmethod
    def verify_record(root, record, event, deadline):
        if not isinstance(record, dict): raise InvestigationError('invalid-evidence-record')
        if (not isinstance(record.get('evidence_id'), str) or len(record['evidence_id']) != 32
                or any(c not in '0123456789abcdef' for c in record['evidence_id'])
                or record.get('level') not in LEVELS or not isinstance(record.get('origin'), str)
                or not isinstance(record.get('kind'), str) or not isinstance(record.get('digest'), str)
                or not SHA256.fullmatch(record['digest']) or type(record.get('bytes')) is not int
                or not 0 <= record['bytes'] <= EvidenceRepository.MAX_FILE_BYTES
                or not isinstance(record.get('scope'), list)
                or any(not isinstance(s, str) or s not in EFFECTS for s in record['scope'])
                or type(record.get('observed_at')) not in (int, float) or not math.isfinite(record['observed_at'])
                or not isinstance(record.get('target_fingerprint'), str) or not SHA256.fullmatch(record['target_fingerprint'])):
            raise InvestigationError('invalid-evidence-record')
        rel = record.get('artifact_relative_path', '')
        if not isinstance(rel, str): raise InvestigationError('invalid-artifact-path')
        parts = PurePosixPath(rel)
        if (not isinstance(rel, str) or '\\' in rel or parts.is_absolute() or len(parts.parts) != 3
                or parts.parts[0] != 'evidence' or any(x in {'', '.', '..'} or ':' in x for x in parts.parts)):
            raise InvestigationError('invalid-artifact-path')
        root = safe_path(root)
        path = safe_path(root.joinpath(*parts.parts))
        if root not in path.parents:
            raise InvestigationError('artifact-outside-store')
        # Hashing the artifact only proves the bytes are unchanged. It does NOT
        # prove the record's claimed level/origin/kind: editing just the
        # knowledge JSON to say level=LIVE, origin=host-verification would keep
        # the digest valid and could promote a static artifact into a
        # procedure-verifying one. Cross-check the attestation against the
        # session manifest written when the artifact was first produced. This
        # is internal consistency, not protection against a writer that also
        # rewrites the manifest (full local-account compromise is out of scope).
        EvidenceRepository._attest_from_manifest(root, parts.parts[1], record, event, deadline)
        if digest_file(path, event, deadline, maximum=EvidenceRepository.MAX_FILE_BYTES) != record.get('digest'):
            raise InvestigationError('stored-artifact-changed')
        return path

    @staticmethod
    def _attest_from_manifest(root, session_id, record, event, deadline):
        guard(event, deadline)
        if not isinstance(session_id, str) or len(session_id) != 32 or any(c not in '0123456789abcdef' for c in session_id):
            raise InvestigationError('invalid-artifact-path')
        manifest_path = safe_path(root / 'evidence' / session_id / 'manifest.json', exists=False)
        if root not in manifest_path.parents or not manifest_path.is_file() or manifest_path.is_symlink():
            raise InvestigationError('missing-attestation')
        if manifest_path.stat().st_size > 8 * 1024 * 1024:
            raise InvestigationError('attestation-limit')
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise InvestigationError('invalid-attestation') from exc
        evidence_id = record.get('evidence_id')
        records = manifest.get('records') if isinstance(manifest, dict) else None
        if (not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
                or manifest.get('investigation_id') != session_id or manifest.get('target_sha256') != record.get('target_fingerprint')
                or manifest.get('instruction_authority') is not False
                or not isinstance(records, dict) or not isinstance(evidence_id, str)
                or evidence_id not in records):
            raise InvestigationError('evidence-attestation-mismatch')
        attested = records[evidence_id]
        if not isinstance(attested, dict):
            raise InvestigationError('evidence-attestation-mismatch')
        for field in EvidenceRepository.ATTESTED_FIELDS:
            if record.get(field) != attested.get(field):
                raise InvestigationError('evidence-attestation-mismatch')
        if attested.get('level') != 'SOURCE' and attested.get('origin') != 'host-verification':
            raise InvestigationError('untrusted-evidence-level')
