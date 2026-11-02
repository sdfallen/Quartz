"""Capability selection and repeat detection, consumed by the existing task owner."""
from dataclasses import dataclass
from copy import deepcopy
import hashlib
import json

from .contracts import EFFECTS, IDENTIFIER, InvestigationError, bounded_json


@dataclass(frozen=True)
class InvestigationPolicy:
    effects: frozenset = frozenset({'read_target'})
    allow_acquire: bool = False
    max_steps: int = 24
    max_output_bytes: int = 2 * 1024 * 1024

    def __post_init__(self):
        if (not self.effects <= EFFECTS or type(self.allow_acquire) is not bool
                or type(self.max_steps) is not int or not 1 <= self.max_steps <= 128
                or type(self.max_output_bytes) is not int or not 1024 <= self.max_output_bytes <= 8 * 1024 * 1024):
            raise InvestigationError('invalid-policy')


def select_capabilities(required, catalog, policy):
    """A missing capability is not silently satisfied by a weaker static check."""
    if not isinstance(required, list) or not required or len(required) > 32 or any(
            not isinstance(x, str) or not IDENTIFIER.fullmatch(x) for x in required):
        raise InvestigationError('invalid-capability-request')
    catalog = bounded_json(catalog)
    if not isinstance(catalog, list) or len(catalog) > 256:
        raise InvestigationError('invalid-catalog')
    selected, missing, restricted = [], [], []
    for name in dict.fromkeys(required):
        candidates = [c for c in catalog if isinstance(c, dict) and c.get('capability_id') == name
                      and c.get('available') is True]
        allowed = [c for c in candidates if isinstance(c.get('effects'), list)
                   and all(isinstance(x,str) for x in c['effects']) and set(c['effects']) <= policy.effects]
        if allowed: selected.append(deepcopy(allowed[0]))
        elif candidates: restricted.append(name)
        else: missing.append(name)
    return {'selected':selected, 'missing':missing, 'restricted':restricted,
            'acquisition_allowed':policy.allow_acquire, 'instruction_authority':False}


class ProgressLedger:
    """Bounded per-investigation observations, not a persistent retry engine."""
    def __init__(self, maximum=24):
        self.maximum = maximum
        self.records = []
        self._outcomes = set()

    def record(self, request, receipt, *, evidence_ids=()):
        if len(self.records) >= self.maximum: raise InvestigationError('step-budget')
        query = {k:request.get(k) for k in ('operation','tool_id','options')}
        outcome = {'query':query, 'status':receipt.get('status'),
                   'artifact_digests':[a.get('sha256') for a in receipt.get('artifacts',[]) if isinstance(a,dict)],
                   'evidence_ids':list(evidence_ids)}
        # IDs and timestamps do not make a repeated unsuccessful attempt progress.
        key = hashlib.sha256(json.dumps({k:v for k,v in outcome.items() if k!='evidence_ids'},sort_keys=True).encode()).hexdigest()
        progress = key not in self._outcomes
        self._outcomes.add(key)
        self.records.append({'request_id':request.get('request_id'), 'made_progress':progress,
                             'status':receipt.get('status'), 'evidence_ids':list(evidence_ids)})
        return progress
