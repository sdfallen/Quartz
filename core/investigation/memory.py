"""Versioned evidence memory. No task/permission/process state is restored."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from core.atomic_json import atomic_write_json
from .contracts import IDENTIFIER, InvestigationError, SHA256, bounded_json, fingerprint, guard, safe_path, validate_finding
from .evidence import EvidenceRepository


@dataclass(frozen=True)
class PreparedPublication:
    owner: object
    record: dict
    digest: str


class InvestigationMemory:
    TTL = 30 * 86400
    MAX_RECORDS = 200
    MAX_RECORD_BYTES = 512 * 1024
    _lock = threading.RLock()

    def __init__(self, root):
        self.root = safe_path(root, exists=False)
        self._publication_owner = object()

    @staticmethod
    def key(target, question, tool_fingerprint):
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
            raise InvestigationError('invalid-question')
        if not isinstance(tool_fingerprint, str) or not SHA256.fullmatch(tool_fingerprint):
            raise InvestigationError('invalid-tool-fingerprint')
        return hashlib.sha256(json.dumps([target.target_id, ' '.join(question.casefold().split()),
                                          tool_fingerprint], ensure_ascii=False).encode()).hexdigest()

    @contextmanager
    def _publication(self):
        """Short OS-held lock; no stale-lock deletion or process authority."""
        with self._lock:
            safe_path(self.root, exists=False)
            folder = self.root / 'knowledge'
            folder.mkdir(parents=True, exist_ok=True)
            safe_path(folder)
            lock_path = safe_path(folder / '.publish.lock', exists=False)
            with lock_path.open('a+b') as handle:
                handle.seek(0, 2)
                if handle.tell() == 0:
                    handle.write(b'0'); handle.flush()
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    yield folder
                finally:
                    handle.seek(0)
                    if os.name == 'nt': msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def prepare(self, target, question, tool_fingerprint, report, event, deadline):
        guard(event, deadline)
        target.revalidate(event, deadline)
        report = bounded_json(report, maximum=self.MAX_RECORD_BYTES)
        if not isinstance(report, dict) or report.get('status') != 'completed' or report.get('target', {}).get('sha256') != target.sha256:
            raise InvestigationError('incomplete-knowledge')
        evidence = report.get('evidence')
        findings = report.get('findings')
        if not isinstance(evidence, dict) or len(evidence) > 128 or not isinstance(findings, list) or len(findings) > 128:
            raise InvestigationError('invalid-knowledge')
        for key, record in evidence.items():
            if record.get('evidence_id') != key or record.get('target_fingerprint') != target.sha256:
                raise InvestigationError('evidence-target-mismatch')
            EvidenceRepository.verify_record(self.root, record, event, deadline)
        findings = [validate_finding(item, evidence) for item in findings]
        # Host-controlled inventory flag is not generalized to runtime success.
        coverage = report.get('coverage', [])
        if not isinstance(coverage, list) or len(coverage)>64 or any(not isinstance(x,str) or not IDENTIFIER.fullmatch(x) for x in coverage):
            raise InvestigationError('invalid-coverage')
        # A reusable inventory may only claim coverage it actually carries, and
        # must be a bounded typed summary (no NaN/exotic objects survive
        # bounded_json, but nested shape and the coverage/summary agreement are
        # checked here so a forged inventory cannot be promoted on reload).
        inventory = report.get('reusable_inventory')
        if inventory is not None:
            if not isinstance(inventory, dict) or set(inventory) - {'status', 'message', 'evidence'}:
                raise InvestigationError('invalid-reusable-inventory')
            if inventory.get('status') != 'PASS' or 'static_inventory' not in coverage:
                raise InvestigationError('invalid-reusable-inventory')
            meta = inventory.get('evidence')
            if not isinstance(meta, dict) or meta.get('artifact_sha256') != target.sha256:
                raise InvestigationError('invalid-reusable-inventory')
            source_ref = meta.get('source_evidence_sha256')
            if not any(item.get('kind') == 'rea-full-artifact' and item.get('digest') == source_ref
                       for item in evidence.values()):
                raise InvestigationError('invalid-reusable-inventory')
        elif 'static_inventory' in coverage:
            raise InvestigationError('invalid-coverage')
        record = {'schema_version': 1, 'key': self.key(target, question, tool_fingerprint),
                  'target_sha256': target.sha256, 'target_fingerprint': list(target.version_fingerprint),
                  'tool_fingerprint': tool_fingerprint, 'observed_at': time.time(),
                  'findings': findings, 'evidence': evidence, 'coverage': coverage,
                  'limitations': report.get('limitations', []),
                  'reusable_inventory': report.get('reusable_inventory'),
                  'instruction_authority': False, 'requires_current_grant': True}
        record = bounded_json(record, maximum=self.MAX_RECORD_BYTES)
        digest = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return PreparedPublication(self._publication_owner, record, digest)

    def commit(self, target, prepared, event, deadline):
        if (not isinstance(prepared, PreparedPublication) or prepared.owner is not self._publication_owner
                or hashlib.sha256(json.dumps(prepared.record, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != prepared.digest):
            raise InvestigationError('invalid-publication')
        record = deepcopy(prepared.record)
        with self._publication() as folder:
            guard(event, deadline)
            existing = sorted(folder.glob(record['key'] + '.*.json'),
                              key=lambda p: p.stat().st_mtime_ns, reverse=True)
            # Idempotency: republishing an identical report must not grow the
            # store without bound. If the newest record for this key has the
            # same content digest (observed_at excluded), reuse it in place.
            for candidate in existing[:1]:
                try:
                    if candidate.stat().st_size <= self.MAX_RECORD_BYTES:
                        prior = json.loads(candidate.read_text(encoding='utf-8'))
                        if isinstance(prior, dict) and self._content_digest(prior) == self._content_digest(record):
                            return deepcopy(prior)
                except (OSError, ValueError):
                    pass
            if len(list(folder.glob('*.json'))) >= self.MAX_RECORDS:
                raise InvestigationError('knowledge-limit')
            # Check just before the write; parent job publishes memory only after
            # its cancellation fence. Failed/cancelled analysis never calls us.
            if target.version_fingerprint != fingerprint(safe_path(target.canonical_path)):
                raise InvestigationError('target-changed')
            path = folder / (record['key'] + '.' + uuid.uuid4().hex + '.json')
            atomic_write_json(path, record)
        return deepcopy(record)

    @staticmethod
    def _content_digest(record):
        """Identity of a knowledge record ignoring its observation timestamp."""
        payload = {k: v for k, v in record.items() if k != 'observed_at'}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def publish(self, target, question, tool_fingerprint, report, event, deadline):
        prepared = self.prepare(target, question, tool_fingerprint, report, event, deadline)
        return self.commit(target, prepared, event, deadline)

    def _load_valid_record(self, path, target, event, deadline, *, require_key=None, require_tool=None):
        """Return a verified, invalidation-applied record, or None on any defect.

        ``require_key``/``require_tool`` are enforced for the question-scoped
        lookup; target-scoped reads pass None and match on target identity only.
        Malformed, modified, expired, cross-target or unverifiable records are
        rejected — a cache miss, never a crash or a silent wrong hit."""
        safe_path(path)
        if path.stat().st_size > self.MAX_RECORD_BYTES: return None
        record = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(record, dict): return None
        if (record.get('schema_version') != 1
                or (require_key is not None and record.get('key') != require_key)
                or (require_tool is not None and record.get('tool_fingerprint') != require_tool)
                or record.get('target_sha256') != target.sha256
                or record.get('target_fingerprint') != list(target.version_fingerprint)
                or record.get('instruction_authority') is not False
                or not 0 <= time.time() - record.get('observed_at', 0) <= self.TTL):
            return None
        evidence = record['evidence']
        if not isinstance(evidence, dict) or len(evidence) > 128: return None
        for identity, item in evidence.items():
            if item.get('target_fingerprint') != target.sha256 or item.get('evidence_id') != identity:
                raise InvestigationError('evidence-target-mismatch')
            EvidenceRepository.verify_record(self.root, item, event, deadline)
        if not isinstance(record.get('findings'), list) or len(record['findings']) > 128: return None
        for item in record['findings']: validate_finding(item, evidence)
        target.revalidate(event, deadline)
        invalidated = []
        for item in record['findings']:
            failure = self.root / 'outcomes' / (target.target_id + '.' + item['claim_id'] + '.json')
            if failure.exists():
                # A failed later procedure must not be retried just because its
                # earlier success was valid. Corrupt outcome data fails closed
                # for this procedure only.
                try:
                    safe_path(failure)
                    if failure.stat().st_size > 32 * 1024: raise InvestigationError('outcome-limit')
                    outcome = json.loads(failure.read_text(encoding='utf-8'))
                    if (outcome.get('target_sha256') != target.sha256 or outcome.get('claim_id') != item['claim_id']):
                        raise InvestigationError('invalid-outcome')
                    EvidenceRepository.verify_record(self.root, outcome['evidence'], event, deadline)
                    if outcome['observed_at'] >= record['observed_at']: invalidated.append(item['claim_id'])
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    invalidated.append(item['claim_id'])
        if invalidated:
            record['findings'] = [f for f in record['findings'] if f['claim_id'] not in invalidated]
            record['invalidated_claim_ids'] = invalidated
            if 'static.rea' in invalidated:
                record['coverage'] = [x for x in record['coverage'] if x != 'static_inventory']
                record['reusable_inventory'] = None
        return deepcopy(record) | {'historical': True, 'instruction_authority': False,
                                   'requires_current_grant': True}

    def lookup(self, target, question, tool_fingerprint, event, deadline):
        """Malformed, modified, expired or unverifiable records are cache misses."""
        try:
            guard(event, deadline)
            target.revalidate(event, deadline)
            folder = self.root / 'knowledge'
            if not folder.is_dir(): return None
            safe_path(folder)
            key = self.key(target, question, tool_fingerprint)
            candidates = list(folder.glob(key + '.*.json'))
            if len(candidates) > self.MAX_RECORDS: return None
            candidates.sort(key=lambda p:p.stat().st_mtime_ns, reverse=True)
            for path in candidates:
                guard(event, deadline)
                try:
                    record = self._load_valid_record(path, target, event, deadline,
                                                     require_key=key, require_tool=tool_fingerprint)
                    if record is not None: return record
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    guard(event, deadline)
                    continue
            return None
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            guard(event, deadline)
            return None

    def context_for_target(self, target, event, deadline, *, maximum_scan=64):
        """Bounded, path-free context of the most recent valid record for this
        target, independent of the question/tool key.

        For the application-knowledge layer, whose scope is the executable
        itself, not one question. The result is historical and carries no
        grant or instruction authority; it never restores scope or a task.
        A failed-verification outcome still drops the stale procedure."""
        try:
            guard(event, deadline)
            target.revalidate(event, deadline)
            folder = self.root / 'knowledge'
            if not folder.is_dir(): return None
            safe_path(folder)
            candidates = sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            if len(candidates) > self.MAX_RECORDS: candidates = candidates[:self.MAX_RECORDS]
            scanned = 0
            for path in candidates:
                guard(event, deadline)
                # Cheap pre-filter so an unrelated target's records do not each
                # cost a full verification pass.
                try:
                    if path.stat().st_size > self.MAX_RECORD_BYTES: continue
                    head = json.loads(path.read_text(encoding='utf-8'))
                    if not isinstance(head, dict) or head.get('target_sha256') != target.sha256:
                        continue
                except (OSError, ValueError):
                    continue
                scanned += 1
                if scanned > maximum_scan: break
                try:
                    record = self._load_valid_record(path, target, event, deadline)
                    if record is not None:
                        return self.context(record)
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    guard(event, deadline)
                    continue
            return None
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            guard(event, deadline)
            return None

    def record_failed_verification(self,target,claim_id,evidence,event,deadline):
        if (not isinstance(claim_id,str) or not IDENTIFIER.fullmatch(claim_id)
                or evidence.get('origin')!='host-verification' or evidence.get('level')!='LIVE'
                or evidence.get('target_fingerprint')!=target.sha256):
            raise InvestigationError('unverified-failure')
        target.revalidate(event,deadline)
        EvidenceRepository.verify_record(self.root,evidence,event,deadline)
        with self._publication():
            guard(event,deadline)
            directory=safe_path(self.root/'outcomes',exists=False);directory.mkdir(exist_ok=True)
            atomic_write_json(directory/(target.target_id+'.'+claim_id+'.json'),{
                'schema_version':1,'target_sha256':target.sha256,'claim_id':claim_id,
                'observed_at':time.time(),'outcome':'verification_failed','evidence':evidence,
                'instruction_authority':False})
    @staticmethod
    def context(record, *, maximum_findings=12):
        if not record: return None
        # No canonical filesystem paths, raw artifact strings, commands, grants
        # or executable recipes are put into the provider's shared context.
        return {'schema_version': 1, 'target_sha256': record['target_sha256'],
                'observed_at': record['observed_at'], 'historical': True,
                'findings': [{k:f[k] for k in ('claim_id','claim','claim_type','confidence_basis','limitations')
                              if k in f} for f in record['findings'][:maximum_findings]],
                'coverage': record['coverage'], 'instruction_authority': False,
                'requires_current_grant': True}

    @staticmethod
    def procedure_candidates(record, *, target_sha256, current_grants):
        """Data only; the current Broker/task retains all replay authority."""
        if not record or record.get('target_sha256') != target_sha256: return []
        result=[]
        for finding in record.get('findings',[]):
            if finding.get('claim_type')!='verified_procedure':continue
            validate_finding(finding,record['evidence'])
            pre=finding['procedure']['preconditions']
            if pre['target_sha256']==target_sha256 and set(pre['required_grants']) <= set(current_grants):
                result.append(deepcopy(finding) | {'instruction_authority':False,'requires_current_grant':True})
        return result
