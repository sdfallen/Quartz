"""JSON v1 boundaries shared by analysis, workbench and the existing job owner."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time

SCHEMA_VERSION = 1
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}\Z")
EFFECTS = frozenset({'read_target', 'write_workspace', 'execute_tool', 'attach_runtime', 'execute_target'})
LEVELS = frozenset({'SOURCE', 'BUILT', 'LIVE'})


class InvestigationError(ValueError):
    """Only stable codes leave the investigation boundary."""


class Cancelled(InvestigationError):
    pass


def guard(event: threading.Event, deadline: float):
    if event.is_set():
        raise Cancelled('cancelled')
    if not math.isfinite(deadline) or time.monotonic() >= deadline:
        raise InvestigationError('deadline')


def safe_path(value, *, exists=True) -> Path:
    path = Path(value).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise InvestigationError('linked-path')
    if any(p.casefold() in {'warbandisland', 'ai_island_test'} for p in path.parts):
        raise InvestigationError('excluded-target')
    return path.resolve(strict=exists)


def bounded_json(value, *, maximum=256 * 1024):
    """No default=str, NaN, exotic objects, unbounded nesting or implicit code."""
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(raw.encode('utf-8')) > maximum:
            raise InvestigationError('json-limit')
        return json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise InvestigationError('invalid-json') from exc


def fingerprint(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def digest_file(path, event, deadline, *, maximum=512 * 1024 * 1024):
    path = safe_path(path)
    before = fingerprint(path)
    if not path.is_file() or before[2] > maximum:
        raise InvestigationError('file-limit')
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        while chunk := stream.read(256 * 1024):
            guard(event, deadline)
            size += len(chunk)
            if size > maximum or size > before[2]:
                raise InvestigationError('file-limit')
            digest.update(chunk)
    guard(event, deadline)
    if size != before[2] or fingerprint(path) != before:
        raise InvestigationError('file-changed')
    return digest.hexdigest()


@dataclass(frozen=True)
class Target:
    target_id: str
    canonical_path: str
    sha256: str
    size: int
    format: str
    version_fingerprint: tuple
    approved_scope: tuple

    @classmethod
    def capture(cls, value, event, deadline, *, approved_scope=('read_target',)):
        scope = tuple(approved_scope)
        if not scope or not set(scope) <= EFFECTS:
            raise InvestigationError('invalid-scope')
        path = safe_path(value)
        before = fingerprint(path)
        digest = digest_file(path, event, deadline)
        if fingerprint(path) != before:
            raise InvestigationError('target-changed')
        with path.open('rb') as stream:
            magic = stream.read(4)
        kind = 'pe' if magic[:2] == b'MZ' else 'unknown'
        key = hashlib.sha256((os.path.normcase(str(path)) + '\0' + digest).encode()).hexdigest()
        return cls(key, str(path), digest, before[2], kind, before, scope)

    def revalidate(self, event, deadline):
        path = safe_path(self.canonical_path)
        if fingerprint(path) != self.version_fingerprint or digest_file(path, event, deadline) != self.sha256:
            raise InvestigationError('target-changed')

    def as_dict(self):
        return bounded_json(asdict(self))


def validate_finding(value, evidence):
    value = bounded_json(value, maximum=24 * 1024)
    if (not isinstance(value, dict) or not isinstance(value.get('claim_id'), str)
            or not IDENTIFIER.fullmatch(value['claim_id'])):
        raise InvestigationError('invalid-finding')
    kind = value.get('claim_type')
    if kind not in {'observation', 'hypothesis', 'verified_procedure'}:
        raise InvestigationError('invalid-claim-type')
    if not isinstance(value.get('claim'), str) or not 1 <= len(value['claim']) <= 4000:
        raise InvestigationError('invalid-claim')
    refs = value.get('evidence_ids')
    counters = value.get('counter_evidence_ids', [])
    if not isinstance(refs, list) or not 1 <= len(refs) <= 32 or not isinstance(counters, list) or len(counters) > 32:
        raise InvestigationError('invalid-evidence-links')
    if (not isinstance(evidence, dict) or any(not isinstance(ref, str) or ref not in evidence
            or not isinstance(evidence[ref], dict) for ref in refs + counters)):
        raise InvestigationError('unknown-evidence')
    # Independence is by distinct evidence id: citing one artifact twice is not
    # two verifications. Without this a procedure could be "verified" by
    # evidence_ids=[X, X] passing the len>=2 LIVE check below.
    if len(set(refs)) != len(refs) or len(set(counters)) != len(counters):
        raise InvestigationError('duplicate-evidence-link')
    if not isinstance(value.get('confidence_basis'), str) or not value['confidence_basis'] or len(value['confidence_basis']) > 2000:
        raise InvestigationError('missing-confidence-basis')
    if type(value.get('reproducible')) is not bool:
        raise InvestigationError('invalid-reproducibility')
    limitations = value.get('limitations', [])
    if not isinstance(limitations, list) or len(limitations) > 24 or any(not isinstance(x, str) or len(x) > 1000 for x in limitations):
        raise InvestigationError('invalid-limitations')
    if kind == 'verified_procedure':
        # External tool/model strings cannot promote static output to LIVE.
        live = [evidence[ref] for ref in refs if evidence[ref].get('level') == 'LIVE'
                and evidence[ref].get('origin') == 'host-verification']
        if len(live) < 2 or not value['reproducible']:
            raise InvestigationError('procedure-not-verified')
        procedure = value.get('procedure')
        if not isinstance(procedure, dict): raise InvestigationError('missing-procedure')
        steps = procedure.get('steps')
        if not isinstance(steps, list) or not 1 <= len(steps) <= 32:
            raise InvestigationError('invalid-procedure-steps')
        operations = {'observe_window','find_control','click_control','set_control_value',
                      'verify_control','read_scoped_file','inspect_artifact','compare_digest'}
        for step in steps:
            if (not isinstance(step, dict) or set(step) - {'operation','locator','value_ref','expected'}
                    or step.get('operation') not in operations):
                raise InvestigationError('unsafe-procedure-step')
            locator = step.get('locator', {})
            if (not isinstance(locator, dict) or set(locator) - {'automation_id','control_type','name','relative_file'}
                    or any(not isinstance(v,str) or len(v)>512 for v in locator.values())):
                raise InvestigationError('invalid-procedure-locator')
            relative=locator.get('relative_file')
            if relative is not None and (':' in relative or relative.startswith(('/', '\\'))
                    or '..' in relative.replace('\\','/').split('/')):
                raise InvestigationError('procedure-outside-scope')
            if 'expected' in step and (type(step['expected']) not in {str,int,bool}
                    or isinstance(step['expected'],str) and len(step['expected'])>1000):
                raise InvestigationError('invalid-procedure-expectation')
            if 'value_ref' in step and (not isinstance(step['value_ref'],str) or not IDENTIFIER.fullmatch(step['value_ref'])):
                raise InvestigationError('invalid-procedure-parameter')
        preconditions = procedure.get('preconditions')
        success = procedure.get('success_check')
        if (not isinstance(preconditions, dict) or not SHA256.fullmatch(str(preconditions.get('target_sha256','')))
                or not isinstance(preconditions.get('required_grants'), list)
                or any(not isinstance(x,str) or not IDENTIFIER.fullmatch(x) for x in preconditions['required_grants'])
                or not isinstance(success, dict) or set(success)-{'operation','locator','expected'}
                or success.get('operation') not in {'verify_control','compare_digest'}):
            raise InvestigationError('missing-procedure-preconditions')
        locator = success.get('locator', {})
        if (not isinstance(locator, dict) or set(locator) - {'automation_id','control_type','name','relative_file'}
                or any(not isinstance(v, str) or len(v) > 512 for v in locator.values())):
            raise InvestigationError('invalid-procedure-locator')
        relative = locator.get('relative_file')
        if relative is not None and (':' in relative or relative.startswith(('/', '\\'))
                or '..' in relative.replace('\\', '/').split('/')):
            raise InvestigationError('procedure-outside-scope')
        expected = success.get('expected')
        if (type(expected) not in (str, int, bool) or isinstance(expected, str) and len(expected) > 1000
                or success['operation'] == 'compare_digest' and (not isinstance(expected, str) or not SHA256.fullmatch(expected))):
            raise InvestigationError('invalid-procedure-expectation')
        if counters:
            raise InvestigationError('contradicted-procedure')
    return value
