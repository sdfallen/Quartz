"""Main-chat investigation task binding: request -> existing owner -> bounded rounds.

The chat already owns conversations, the permission card and Stop. The existing
diagnostics worker already owns investigation sessions, evidence, cancellation
and publication. The external tool authority already lives in ToolWorkbench.
This module is only the missing binding between them, so one natural main-chat
task can keep running across capability gaps and permission grants.

It is deliberately NOT a second task engine:

* It spawns nothing, executes nothing and touches no file. Callers (the existing
  host/gateway/workbench) perform every side effect and hand back receipts.
* It creates no permission. ``request_scope`` only produces a pending question
  for the existing chat permission card; ``grant_scope`` records the answer the
  host already validated. A stale or replayed answer never starts a new task
  and never widens scope.
* The native picker stays the target grant: a task binds to a target only
  through an owner object the host built from that selection.
* Model prose is data. Classification uses the existing conservative routing
  helpers, and a hypothesis is never promoted to a verified procedure here.
* Every round is budgeted and deduplicated, so a failing approach stops with a
  typed outcome instead of retrying forever.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from .contracts import IDENTIFIER, InvestigationError, bounded_json
from .planning import InvestigationPolicy

SCHEMA_VERSION = 1
REQUEST_KIND = 'application_investigation'
MAX_ROUNDS = 8
MAX_QUESTION = 2000

# An investigation request needs a real subject and a real diagnostic verb in
# the user's own current prose. Quoted text, code blocks and "just chat"
# messages are removed by instruction_text/tools_disallowed before matching.
_SUBJECT = re.compile(
    r'\b(uygulama\w*|program\w*|yazılım\w*|exe\b|\.exe\b|dll\b|paket\w*|oyun\w*|'
    r'kurulum\w*|derleme\w*|build\b)')
_PROBLEM = re.compile(
    r'\b(hata\w*|bug\b|sorun\w*|ariza\w*|arıza\w*|çökme\w*|cokme\w*|donma\w*|'
    r'kaydetmiyor\w*|kaydedilmiyor\w*|açılmıyor\w*|acilmiyor\w*|çalışmıyor\w*|'
    r'calismiyor\w*|bozuk\w*|yanlış\w*|yanlis\w*)')
_DIAGNOSE = re.compile(
    r'\b(incele\w*|araştır\w*|arastir\w*|teşhis\w*|teshis\w*|analiz\w*|'
    r'tespit\w*|bul\w*|çözümle\w*|cozumle\w*|denetle\w*)')
_FIX = re.compile(r'\b(düzelt\w*|duzelt\w*|onar\w*|gider\w*|tamir\w*|çöz\w*|coz\w*)')
_REVIEW = re.compile(
    r'\b(diğer|diger|öbür|obur|ikinci)\s+(ajan\w*|model\w*|asistan\w*)|'
    r'\b(kontrol\s+etsin|incelesin|doğrulasın|dogrulasin|gözden\s+geçirsin)')


def classify_investigation_request(text):
    """Return a typed request for a natural application task, else ``None``.

    Classification authorizes nothing. ``needs_target`` stays true until the
    user's own native selection produces an owner, so this never turns chat
    prose into a file path or a grant.
    """
    from core.message_intent import instruction_text, tools_disallowed
    raw = str(text or '')
    if not raw.strip() or len(raw) > MAX_QUESTION or tools_disallowed(raw):
        return None
    value = instruction_text(raw)
    if not _SUBJECT.search(value):
        return None
    diagnose, fix = bool(_DIAGNOSE.search(value)), bool(_FIX.search(value))
    if not (diagnose or fix):
        return None
    # A fix-only sentence with no problem and no diagnostic verb is a build or
    # feature request, not an investigation of an existing defect.
    if not diagnose and not _PROBLEM.search(value):
        return None
    return {'schema_version': SCHEMA_VERSION, 'kind': REQUEST_KIND,
            'question': raw.strip(), 'needs_target': True,
            'diagnose_requested': diagnose, 'fix_requested': fix,
            'review_requested': bool(_REVIEW.search(value)),
            'problem_reported': bool(_PROBLEM.search(value)),
            'instruction_authority': False}


class ChatInvestigationTask:
    """One main-chat task bound to one existing investigation owner."""

    OPEN_STATES = frozenset({'awaiting_target', 'running', 'awaiting_permission'})
    TERMINAL_STATES = frozenset({'completed', 'blocked', 'failed', 'cancelled'})

    def __init__(self, request, *, task_id, conversation_id, policy=None, max_rounds=MAX_ROUNDS):
        request = bounded_json(request, maximum=16 * 1024)
        if (not isinstance(request, dict) or request.get('kind') != REQUEST_KIND
                or request.get('schema_version') != SCHEMA_VERSION
                or not isinstance(request.get('question'), str)):
            raise InvestigationError('invalid-investigation-request')
        for name in (task_id, conversation_id):
            if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
                raise InvestigationError('invalid-task-identity')
        if type(max_rounds) is not int or not 1 <= max_rounds <= 64:
            raise InvestigationError('invalid-round-budget')
        self.request = deepcopy(request)
        self.task_id, self.conversation_id = task_id, conversation_id
        self.policy = policy or InvestigationPolicy()
        if not isinstance(self.policy, InvestigationPolicy):
            raise InvestigationError('missing-policy')
        self.max_rounds = max_rounds
        self.state = 'awaiting_target'
        self.owner_id = None
        self.target_fingerprint = None
        # Scope actually granted for THIS task. Never seeded from the request.
        self.granted_effects = frozenset()
        self.rounds = []
        self.failed_methods = []
        self.outcome = None
        self._pending = None
        self._generation = 0
        self._consumed = set()
        self._outcome_keys = set()

    # ── target binding: the user's own selection is the only way in ──
    def bind_owner(self, owner):
        """Bind the host-built investigation owner (from the native picker)."""
        if self.state != 'awaiting_target':
            raise InvestigationError('target-already-bound')
        target = getattr(owner, 'target', None)
        identity = getattr(owner, 'identity', None)
        if target is None or identity is None:
            raise InvestigationError('invalid-investigation-owner')
        self.owner_id = str(getattr(owner, 'scope', 'artifact')) + ':' + hashlib.sha256(
            str(target).encode('utf-8')).hexdigest()[:16]
        self.target_fingerprint = list(identity)
        self.state = 'running'
        return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'state': self.state, 'owner_id': self.owner_id,
                'instruction_authority': False}

    # ── permission: a question for the existing card, never a grant ──
    def request_scope(self, effect, reason):
        if self.state not in {'running', 'awaiting_permission'}:
            raise InvestigationError('task-not-running')
        if effect not in self.policy.effects:
            # The task cannot ask for more than its own policy already allows.
            raise InvestigationError('effect-outside-policy')
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise InvestigationError('invalid-permission-reason')
        self._generation += 1
        self._pending = {'request_id': self.task_id + '.scope.' + str(self._generation),
                         'generation': self._generation, 'effect': effect,
                         'reason': reason.strip()}
        self.state = 'awaiting_permission'
        return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'conversation_id': self.conversation_id, 'state': self.state,
                'pending_permission': deepcopy(self._pending),
                'continues_existing_task': True, 'instruction_authority': False}

    def grant_scope(self, *, request_id, generation, effect, granted=True):
        """Apply the card's answer to THIS task; a stale answer starts nothing."""
        if (not isinstance(request_id, str) or type(generation) is not int
                or not isinstance(effect, str)):
            raise InvestigationError('invalid-permission-answer')
        if request_id in self._consumed:
            raise InvestigationError('stale-approval')
        pending = self._pending
        if (self.state != 'awaiting_permission' or pending is None
                or request_id != pending['request_id'] or generation != pending['generation']
                or effect != pending['effect']):
            raise InvestigationError('stale-approval')
        self._consumed.add(request_id)
        self._pending = None
        if granted is not True:
            # A refusal does not fail the task; the loop continues without the
            # effect and must reach an explicit unsupported outcome instead.
            self.state = 'running'
            return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                    'state': self.state, 'granted': False, 'effect': effect,
                    'resumed_same_task': True, 'instruction_authority': False}
        self.granted_effects = frozenset(self.granted_effects | {effect})
        self.state = 'running'
        return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'state': self.state, 'granted': True, 'effect': effect,
                'granted_effects': sorted(self.granted_effects),
                'resumed_same_task': True, 'owner_id': self.owner_id,
                'instruction_authority': False}

    # ── bounded rounds ──
    def record_round(self, *, action, observation, status):
        """Record one completed round; duplicate outcomes make no progress."""
        if self.state != 'running':
            raise InvestigationError('task-not-running')
        if not isinstance(action, str) or not IDENTIFIER.fullmatch(action):
            raise InvestigationError('invalid-round-action')
        if status not in {'completed', 'failed', 'unsupported', 'blocked', 'cancelled'}:
            raise InvestigationError('invalid-round-status')
        if len(self.rounds) >= self.max_rounds:
            raise InvestigationError('round-budget')
        observation = bounded_json(observation, maximum=32 * 1024)
        key = hashlib.sha256(json.dumps(
            [action, status, observation], sort_keys=True, default=str).encode()).hexdigest()
        progress = key not in self._outcome_keys
        self._outcome_keys.add(key)
        self.rounds.append({'round': len(self.rounds) + 1, 'action': action,
                            'status': status, 'made_progress': progress})
        return {'schema_version': SCHEMA_VERSION, 'round': len(self.rounds),
                'made_progress': progress, 'rounds_left': self.max_rounds - len(self.rounds),
                'instruction_authority': False}

    def rounds_exhausted(self):
        return len(self.rounds) >= self.max_rounds

    def stalled(self):
        """Two consecutive roundless outcomes mean the approach is not working."""
        recent = [r['made_progress'] for r in self.rounds[-2:]]
        return len(recent) == 2 and not any(recent)

    # ── capability gap -> external tool plan (no acquisition happens here) ──
    def plan_external_tool(self, missing, workbench):
        """Resolve a registered candidate for a real capability gap.

        Returns a typed ``unsupported`` result unless the task actually holds
        ``execute_tool`` and the policy allows acquisition. Resolution only
        names a candidate manifest; acquisition and execution stay with the
        workbench under the existing gateway contract.
        """
        if self.state != 'running':
            raise InvestigationError('task-not-running')
        if (not isinstance(missing, list) or not missing or len(missing) > 16
                or any(not isinstance(x, str) or not IDENTIFIER.fullmatch(x) for x in missing)):
            raise InvestigationError('invalid-capability-gap')
        if 'execute_tool' not in self.granted_effects:
            return {'schema_version': SCHEMA_VERSION, 'status': 'unsupported',
                    'reason': 'tool-scope-not-granted', 'missing': list(missing),
                    'instruction_authority': False}
        if not self.policy.allow_acquire:
            return {'schema_version': SCHEMA_VERSION, 'status': 'unsupported',
                    'reason': 'acquisition-not-allowed', 'missing': list(missing),
                    'instruction_authority': False}
        if workbench is None:
            return {'schema_version': SCHEMA_VERSION, 'status': 'unsupported',
                    'reason': 'no-tool-workbench', 'missing': list(missing),
                    'instruction_authority': False}
        candidates, unresolved = [], []
        for name in dict.fromkeys(missing):
            try:
                resolution = bounded_json(workbench.resolve({'capability_id': name}))
            except Exception:
                # A catalog failure is an unresolved capability, not a crash and
                # not permission to search or run something else.
                unresolved.append(name)
                continue
            manifest = resolution.get('tool_manifest') if isinstance(resolution, dict) else None
            if (not isinstance(resolution, dict) or resolution.get('status') != 'resolved'
                    or not isinstance(manifest, dict) or not isinstance(manifest.get('tool_id'), str)):
                unresolved.append(name)
                continue
            candidates.append({'capability_id': name, 'tool_id': manifest['tool_id'],
                               'source_url': manifest.get('source_url'),
                               'pinned_revision': manifest.get('pinned_revision'),
                               'package_digest': manifest.get('package_digest')})
        if not candidates:
            return {'schema_version': SCHEMA_VERSION, 'status': 'unsupported',
                    'reason': 'no-registered-tool', 'missing': unresolved,
                    'instruction_authority': False}
        return {'schema_version': SCHEMA_VERSION, 'status': 'planned',
                'candidates': candidates, 'unresolved': unresolved,
                'requires_managed_acquisition': True, 'instruction_authority': False}

    # ── outcomes ──
    def record_failed_method(self, method, reason):
        if not isinstance(method, str) or not IDENTIFIER.fullmatch(method):
            raise InvestigationError('invalid-failed-method')
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise InvestigationError('invalid-failure-reason')
        entry = {'method': method, 'reason': reason.strip()}
        if entry not in self.failed_methods:
            self.failed_methods.append(entry)
        return deepcopy(entry)

    def conclude(self, status, *, summary, evidence_ids=(), verified_by=None):
        """Close the task. A model's claim is never an accepted verification."""
        if status not in self.TERMINAL_STATES:
            raise InvestigationError('invalid-task-outcome')
        if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 2000:
            raise InvestigationError('invalid-task-summary')
        refs = list(evidence_ids)
        if len(refs) > 64 or any(not isinstance(x, str) for x in refs):
            raise InvestigationError('invalid-task-evidence')
        if status == 'completed' and verified_by not in {'rerun', 'fresh_observation'}:
            # "It is fixed" is not an outcome; a completed fix needs a real
            # re-run or a fresh observation recorded by the host.
            raise InvestigationError('unverified-completion')
        self.state = status
        self._pending = None
        self.outcome = {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                        'conversation_id': self.conversation_id, 'status': status,
                        'summary': summary.strip(), 'evidence_ids': refs,
                        'verified_by': verified_by, 'rounds': len(self.rounds),
                        'failed_methods': deepcopy(self.failed_methods),
                        'granted_effects': sorted(self.granted_effects),
                        'instruction_authority': False}
        return deepcopy(self.outcome)

    def cancel(self, reason='cancelled'):
        """Stop fences the task. Pending work is never reported as confirmed."""
        self._pending = None
        if self.state in self.TERMINAL_STATES:
            return deepcopy(self.outcome) if self.outcome else {
                'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'status': self.state, 'instruction_authority': False}
        self.state = 'cancelled'
        self.outcome = {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                        'conversation_id': self.conversation_id, 'status': 'cancelled',
                        'summary': str(reason)[:500], 'evidence_ids': [],
                        'verified_by': None, 'rounds': len(self.rounds),
                        'failed_methods': deepcopy(self.failed_methods),
                        'granted_effects': sorted(self.granted_effects),
                        'instruction_authority': False}
        return deepcopy(self.outcome)

    def summary(self):
        return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'conversation_id': self.conversation_id, 'state': self.state,
                'owner_id': self.owner_id, 'question': self.request['question'],
                'rounds': len(self.rounds), 'rounds_left': max(0, self.max_rounds - len(self.rounds)),
                'granted_effects': sorted(self.granted_effects),
                'pending_permission': deepcopy(self._pending),
                'failed_methods': deepcopy(self.failed_methods),
                'outcome': deepcopy(self.outcome), 'instruction_authority': False}


def reusable_procedures(record, *, target_sha256, current_grants):
    """Prior verified procedures still valid for this target and current grant.

    Thin wrapper over the existing memory contract so the chat path cannot
    invent its own reuse rule or revive a procedure whose grant is gone.
    """
    from .memory import InvestigationMemory
    return InvestigationMemory.procedure_candidates(
        record, target_sha256=target_sha256, current_grants=current_grants)
