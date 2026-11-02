"""Immutable bounded artifacts. Reports are data, never instructions or grants."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import threading
import time
import uuid

from core.atomic_json import atomic_write_json
from .contracts import InvestigationError, LEVELS, bounded_json, digest_file, guard, safe_path


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
            name = identity + '.artifact'
            path = safe_path(self.directory / name, exists=False)
            with path.open('xb') as stream:
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
            self._persist()
            return deepcopy(record)

    def add_json(self, value, **kwargs):
        value = bounded_json(value, maximum=2 * 1024 * 1024)
        return self.add_bytes(json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), **kwargs)

    def ingest_file(self, source, *, source_root, expected_sha256, kind='tool-artifact', origin='rea'):
        source_root = safe_path(source_root)
        source = safe_path(source)
        if source_root not in source.parents:
            raise InvestigationError('artifact-outside-workspace')
        if digest_file(source, self.event, self.deadline, maximum=self.MAX_FILE_BYTES) != expected_sha256:
            raise InvestigationError('artifact-digest-mismatch')
        # Read is bounded and verified again after copying, before publication.
        with source.open('rb') as stream:
            content = stream.read(self.MAX_FILE_BYTES + 1)
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise InvestigationError('artifact-changed')
        return self.add_bytes(content, kind=kind, origin=origin)

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

    @staticmethod
    def verify_record(root, record, event, deadline):
        if not isinstance(record, dict): raise InvestigationError('invalid-evidence-record')
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
        if digest_file(path, event, deadline, maximum=EvidenceRepository.MAX_FILE_BYTES) != record.get('digest'):
            raise InvestigationError('stored-artifact-changed')
        return path
