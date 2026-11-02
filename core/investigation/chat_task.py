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
from contextlib import nullcontext
from functools import wraps
import hashlib
import json
import re
import threading
from urllib.parse import urlsplit

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
    r'tespit\w*|bul\w*|çözümle\w*|cozumle\w*|denetle\w*|ara(?:yın|yin)?\b)')
_FIX = re.compile(r'\b(düzelt\w*|duzelt\w*|onar\w*|gider\w*|tamir\w*|çöz\w*|coz\w*)')
_REVIEW = re.compile(
    r'\b(diğer|diger|öbür|obur|ikinci)\s+(ajan\w*|model\w*|asistan\w*)|'
    r'\b(kontrol\s+etsin|incelesin|doğrulasın|dogrulasin|gözden\s+geçirsin)')
_STRINGS = re.compile(r'\b(?:string\w*|dize\w*)\b')
_LITERAL = re.compile(r'(?:["“]([^"”\r\n]{1,200})["”]|[\'‘]([^\'’\r\n]{1,200})[\'’]|`([^`\r\n]{1,200})`)\s+(?:ifadesini|metnini|dizesini)\b', re.I)
_NAMED_LITERAL = re.compile(r'\b([A-Za-z0-9_][A-Za-z0-9_.:/-]{0,199})\s+(?:ifadesini|metnini|dizesini)\b', re.I)


def classify_investigation_request(text):
    """Return a typed request for a natural application task, else ``None``.

    Classification authorizes nothing. ``needs_target`` stays true until the
    user's own native selection produces an owner, so this never turns chat
    prose into a file path or a grant.
    """
    from core.message_intent import instruction_text, message_intent, tools_disallowed
    raw = str(text or '')
    if not raw.strip() or len(raw) > MAX_QUESTION or tools_disallowed(raw):
        return None
    current = re.sub(r'```[\s\S]*?```', ' ', raw)
    value = instruction_text(re.sub(r"['‘][^'’\r\n]*['’]", ' ', current))
    if message_intent(raw) != 'task':
        return None
    if not _SUBJECT.search(value):
        return None
    diagnose, fix = bool(_DIAGNOSE.search(value)), bool(_FIX.search(value))
    if not (diagnose or fix):
        return None
    # A fix-only sentence with no problem and no diagnostic verb is a build or
    # feature request, not an investigation of an existing defect.
    if not diagnose and not _PROBLEM.search(value):
        return None
    literal_match = _LITERAL.search(current)
    named_match = _NAMED_LITERAL.search(current)
    literal = next((v for v in literal_match.groups() if v is not None), None) if literal_match else (
        named_match.group(1) if named_match else None)
    literal_search = literal is not None and bool(re.search(r'\b(?:ara(?:yın|yin)?|bul\w*)\b', value))
    search = diagnose and (bool(_STRINGS.search(value)) or literal_search)
    return {'schema_version': SCHEMA_VERSION, 'kind': REQUEST_KIND,
            'question': raw.strip(), 'needs_target': True,
            'diagnose_requested': diagnose, 'fix_requested': fix,
            'review_requested': bool(_REVIEW.search(value)),
            'search_requested': search,
            'search_pattern': re.escape(literal) if search and literal is not None else '[ -~]{4,}' if search else None,
            'search_literal': literal if search else None,
            'problem_reported': bool(_PROBLEM.search(value)),
            'instruction_authority': False}


def _scoped_lock(method):
    """Owner callbacks may hold owner.lock: always acquire that before task.lock."""
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            owner = self._owner
        with owner.lock if owner is not None else nullcontext():
            with self._lock:
                if self._owner is not owner:
                    raise InvestigationError('owner-changed')
                return method(self, *args, **kwargs)
    return call


class ChatInvestigationTask:
    """One main-chat task bound to one existing investigation owner."""

    OPEN_STATES = frozenset({'awaiting_target', 'awaiting_job', 'running', 'awaiting_permission', 'cancelling'})
    TERMINAL_STATES = frozenset({'completed', 'blocked', 'failed', 'cancelled'})

    def __init__(self, request, *, task_id, conversation_id, policy=None, max_rounds=MAX_ROUNDS):
        request = bounded_json(request, maximum=16 * 1024)
        if (not isinstance(request, dict) or request.get('kind') != REQUEST_KIND
                or type(request.get('schema_version')) is not int or request.get('schema_version') != SCHEMA_VERSION
                or not isinstance(request.get('question'), str) or not 1 <= len(request['question'].strip()) <= MAX_QUESTION
                or any(type(request.get(k, False)) is not bool for k in
                       ('diagnose_requested', 'fix_requested', 'review_requested', 'search_requested'))):
            raise InvestigationError('invalid-investigation-request')
        for name in (task_id, conversation_id):
            if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
                raise InvestigationError('invalid-task-identity')
        if type(max_rounds) is not int or not 1 <= max_rounds <= 64:
            raise InvestigationError('invalid-round-budget')
        self.request = deepcopy(request)
        self.task_id, self.conversation_id = task_id, conversation_id
        self.policy = InvestigationPolicy() if policy is None else policy
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
        self._lock = threading.RLock()
        self._owner = None
        self._job_id = None
        self._cancel_requested = False
        self._cancel_sent = False
        self._cancel_reason = None
        self._worker_pending = False
        self._cleanup_status = 'not_started'
        self._owner_job_state = None
        self._owner_error_type = None

    @property
    def owner(self):
        with self._lock:
            return self._owner

    @property
    def job_id(self):
        with self._lock:
            return self._job_id

    def _outcome(self, status, summary, *, source=False, stop_confirmed=False):
        return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'conversation_id': self.conversation_id, 'status': status,
                'summary': summary, 'evidence_ids': [], 'verified_by': None,
                'verification': 'SOURCE' if source else 'NOT VERIFIED',
                'fix_verified': False, 'stop_confirmed': stop_confirmed,
                'rounds': len(self.rounds), 'failed_methods': deepcopy(self.failed_methods),
                'granted_effects': sorted(self.granted_effects), 'instruction_authority': False}

    def _sync_owner(self):
        """Passive readback of this exact job. Caller holds owner then task lock."""
        if self._owner is None or self._job_id is None:
            return
        owner, identity = self._owner, self._job_id
        try:
            snapshot = owner.status(identity)
            if (not isinstance(snapshot, dict) or snapshot.get('id') != identity
                    or identity not in owner.jobs or tuple(owner.identity) != tuple(self.target_fingerprint)):
                raise InvestigationError('owner-job-mismatch')
            worker, event = owner.threads.get(identity), owner.events.get(identity)
            if not isinstance(worker, threading.Thread) or not isinstance(event, threading.Event):
                raise InvestigationError('missing-job-owner')
            alive = worker.is_alive()
            if type(alive) is not bool:
                raise InvestigationError('invalid-worker-readback')
            self._worker_pending = alive or worker.ident is None
            cleanup = getattr(owner, '_gateway_cleanup', {}).get(identity)
            tool_cleanup = snapshot.get('tool_cleanup')
            cleanups = [c for c in (cleanup, tool_cleanup) if c is not None]
            if not cleanups and identity in getattr(owner, '_gateways', {}):
                cleanups = [{'status': 'pending'}]
            states = [c.get('status') if isinstance(c, dict) else None for c in cleanups]
            self._cleanup_status = ('failed' if 'failed' in states else 'pending' if any(
                s != 'confirmed' for s in states) else 'confirmed')
            self._owner_job_state = snapshot.get('state')
            if self._owner_job_state not in {'running', 'completed', 'failed', 'cancelled'}:
                raise InvestigationError('invalid-owner-state')
            self._owner_error_type = None
            self._cancel_requested = (self._cancel_requested or self._owner_job_state == 'cancelled'
                or event.is_set() and self._owner_job_state != 'completed')
        except Exception as exc:
            self._owner_error_type = type(exc).__name__
            self._worker_pending = True
            self._cleanup_status = 'pending'
            if self._cancel_requested:
                self.state = 'cancelling'
            else:
                self.state = 'blocked'
            self.outcome = self._outcome(self.state, 'İnceleme işinin durumu doğrulanamadı.')
            return
        if self._cancel_requested:
            self._pending = None
            stopped = not self._worker_pending and self._cleanup_status == 'confirmed'
            self.state = 'cancelled' if stopped else 'cancelling'
            self.outcome = self._outcome(self.state, self._cancel_reason or (
                'İnceleme durduruldu.' if stopped else 'İncelemenin kapanışı bekleniyor.'), stop_confirmed=stopped)
            return
        if self._worker_pending or self._owner_job_state == 'running':
            if self.state not in {'awaiting_permission'}:
                self.state = 'running'
            return
        self._pending = None
        if self._cleanup_status != 'confirmed':
            self.state = 'blocked'
            self.outcome = self._outcome('blocked', 'İnceleme araçlarının kapanışı doğrulanamadı.')
        elif self._owner_job_state == 'failed':
            self.state = 'failed'
            self.outcome = self._outcome('failed', 'İnceleme tamamlanamadı.', stop_confirmed=True)
        else:
            tool_checks = [c for c in snapshot.get('checks', [])
                           if isinstance(c, dict) and c.get('id') == 'registered_tool']
            missing_tool = self.request.get('search_requested') and (
                not tool_checks or any(c.get('status') != 'PASS' for c in tool_checks))
            unsupported = missing_tool or self.request.get('fix_requested') or self.request.get('review_requested')
            self.state = 'blocked' if unsupported else 'completed'
            self.outcome = self._outcome(self.state,
                'Statik inceleme tamamlandı; istenen ek sonuç doğrulanmadı.' if unsupported else
                'Statik inceleme tamamlandı; uygulamanın çalışması veya bir düzeltme doğrulanmadı.',
                source=True, stop_confirmed=True)

    # ── target binding: the user's own selection is the only way in ──
    @_scoped_lock
    def bind_owner(self, owner):
        """Bind the host-built investigation owner (from the native picker)."""
        from core.artifact_diagnostics import ArtifactDiagnosticsService
        if self.state != 'awaiting_target':
            raise InvestigationError('target-already-bound')
        if not isinstance(owner, ArtifactDiagnosticsService):
            raise InvestigationError('invalid-investigation-owner')
        target, identity = owner.target, owner.identity
        if (not isinstance(identity, tuple) or len(identity) != 4
                or any(type(x) is not int for x in identity) or not str(target)):
            raise InvestigationError('invalid-investigation-owner')
        self._owner = owner
        self.owner_id = 'artifact:' + hashlib.sha256(
            str(target).encode('utf-8')).hexdigest()[:16]
        self.target_fingerprint = list(identity)
        self.state = 'awaiting_job'
        return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'state': self.state, 'owner_id': self.owner_id,
                'instruction_authority': False}

    @_scoped_lock
    def attach_job(self, job_id):
        """Attach a job the existing host started; never starts or retargets it."""
        if (self._owner is None or not isinstance(job_id, str) or not IDENTIFIER.fullmatch(job_id)
                or self._job_id is not None and self._job_id != job_id):
            raise InvestigationError('invalid-owner-job')
        if self._job_id is None:
            snapshot = self._owner.status(job_id)
            if (not isinstance(snapshot, dict) or snapshot.get('id') != job_id
                    or job_id not in self._owner.jobs or job_id not in self._owner.events
                    or job_id not in self._owner.threads):
                raise InvestigationError('invalid-owner-job')
            self._job_id = job_id
            self.state = 'running'
        if self._cancel_requested and not self._cancel_sent:
            self._owner.cancel(job_id)
            self._cancel_sent = True
        self._sync_owner()
        return self._summary()

    # ── permission: a question for the existing card, never a grant ──
    @_scoped_lock
    def request_scope(self, effect, reason):
        self._sync_owner()
        if self.state not in {'running', 'awaiting_permission'}:
            raise InvestigationError('task-not-running')
        if not isinstance(effect, str) or effect not in self.policy.effects:
            # The task cannot ask for more than its own policy already allows.
            raise InvestigationError('effect-outside-policy')
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise InvestigationError('invalid-permission-reason')
        if not (self._pending and self._pending['effect'] == effect and self._pending['reason'] == reason.strip()):
            self._generation += 1
            self._pending = {'request_id': self.task_id + '.scope.' + str(self._generation),
                             'generation': self._generation, 'effect': effect,
                             'reason': reason.strip()}
        self.state = 'awaiting_permission'
        return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'conversation_id': self.conversation_id, 'state': self.state,
                'pending_permission': deepcopy(self._pending),
                'continues_existing_task': True, 'instruction_authority': False}

    @_scoped_lock
    def grant_scope(self, *, request_id, generation, effect, granted=True):
        """Apply the card's answer to THIS task; a stale answer starts nothing."""
        if (not isinstance(request_id, str) or type(generation) is not int
                or not isinstance(effect, str) or type(granted) is not bool):
            raise InvestigationError('invalid-permission-answer')
        self._sync_owner()
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
    @_scoped_lock
    def record_round(self, *, action, observation, status):
        """Record one completed round; duplicate outcomes make no progress."""
        self._sync_owner()
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

    @_scoped_lock
    def rounds_exhausted(self):
        return len(self.rounds) >= self.max_rounds

    @_scoped_lock
    def stalled(self):
        """Two consecutive roundless outcomes mean the approach is not working."""
        recent = [r['made_progress'] for r in self.rounds[-2:]]
        return len(recent) == 2 and not any(recent)

    # ── capability gap -> external tool plan (no acquisition happens here) ──
    @_scoped_lock
    def plan_external_tool(self, missing, workbench):
        """Resolve a registered candidate for a real capability gap.

        Returns a typed ``unsupported`` result unless the task actually holds
        ``execute_tool`` and the policy allows acquisition. Resolution only
        names a candidate manifest; acquisition and execution stay with the
        workbench under the existing gateway contract.
        """
        self._sync_owner()
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
        from core.tool_workbench import ToolManifest, ToolWorkbench
        if not isinstance(workbench, ToolWorkbench):
            return {'schema_version': SCHEMA_VERSION, 'status': 'unsupported',
                    'reason': 'no-registered-tool', 'missing': list(missing),
                    'instruction_authority': False}
        candidates, unresolved = [], []
        for name in dict.fromkeys(missing):
            try:
                resolution = bounded_json(workbench.resolve({'capability_id': name}))
                manifest = resolution.get('manifest') if isinstance(resolution, dict) else None
                if not isinstance(manifest, dict):
                    raise InvestigationError('invalid-tool-selection')
                fields = ('tool_id', 'source_url', 'pinned_revision', 'package_digest')
                if any(not isinstance(manifest.get(k), str) or not manifest[k] for k in fields):
                    raise InvestigationError('invalid-tool-selection')
                source = urlsplit(manifest['source_url'])
                if (source.scheme != 'https' or not source.hostname or source.username or source.password
                        or source.fragment or not IDENTIFIER.fullmatch(manifest['tool_id'])
                        or not IDENTIFIER.fullmatch(manifest['pinned_revision'])
                        or not re.fullmatch(r'[a-f0-9]{64}', manifest['package_digest'])):
                    raise InvestigationError('invalid-tool-selection')
                registered = workbench.catalog_service.get(manifest['tool_id'])
                if (resolution.get('status') != 'resolved' or resolution.get('resolved') is not True
                        or resolution.get('capability_id') != name
                        or any(resolution.get(k) != manifest[k] for k in ('tool_id', 'pinned_revision', 'package_digest'))
                        or not isinstance(registered, ToolManifest) or registered.to_dict() != manifest
                        or name not in registered.capabilities
                        or not workbench.catalog_service.is_platform_compatible(registered)):
                    raise InvestigationError('unregistered-tool-selection')
            except Exception:
                # A catalog failure is an unresolved capability, not a crash and
                # not permission to search or run something else.
                unresolved.append(name)
                continue
            candidates.append({'capability_id': name, 'tool_id': manifest['tool_id'],
                               'source_url': manifest.get('source_url'),
                               'pinned_revision': manifest.get('pinned_revision'),
                               'package_digest': manifest.get('package_digest'),
                               'manifest': deepcopy(manifest)})
        if not candidates:
            return {'schema_version': SCHEMA_VERSION, 'status': 'unsupported',
                    'reason': 'no-registered-tool', 'missing': unresolved,
                    'instruction_authority': False}
        return {'schema_version': SCHEMA_VERSION, 'status': 'planned',
                'candidates': candidates, 'unresolved': unresolved,
                'requires_managed_acquisition': True, 'instruction_authority': False}

    # ── outcomes ──
    @_scoped_lock
    def record_failed_method(self, method, reason):
        if not isinstance(method, str) or not IDENTIFIER.fullmatch(method):
            raise InvestigationError('invalid-failed-method')
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise InvestigationError('invalid-failure-reason')
        entry = {'method': method, 'reason': reason.strip()}
        if entry not in self.failed_methods:
            self.failed_methods.append(entry)
        return deepcopy(entry)

    @_scoped_lock
    def conclude(self, status, *, summary, evidence_ids=(), verified_by=None):
        """Close the task. A model's claim is never an accepted verification."""
        if not isinstance(status, str) or status not in self.TERMINAL_STATES:
            raise InvestigationError('invalid-task-outcome')
        if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 2000:
            raise InvestigationError('invalid-task-summary')
        if not isinstance(evidence_ids, (list, tuple)):
            raise InvestigationError('invalid-task-evidence')
        refs = list(evidence_ids)
        if len(refs) > 64 or any(not isinstance(x, str) for x in refs):
            raise InvestigationError('invalid-task-evidence')
        self._sync_owner()
        if status == 'cancelled':
            return self.cancel(summary)
        if status == 'completed':
            # A string tag or arbitrary references cannot turn a static scan
            # into a verified fix. The actual owner job determines completion.
            if self.state != 'completed' or self.outcome is None or verified_by is not None or refs:
                raise InvestigationError('unverified-completion')
            return deepcopy(self.outcome)
        if self._cancel_requested or self.state in self.TERMINAL_STATES:
            if self.state == status and self.outcome is not None:
                return deepcopy(self.outcome)
            raise InvestigationError('task-already-terminal')
        if self._job_id is not None and (self._worker_pending or self._owner_job_state == 'running'):
            raise InvestigationError('owner-not-terminal')
        if verified_by is not None:
            raise InvestigationError('unverified-completion')
        self.state = status
        self._pending = None
        self.outcome = self._outcome(status, summary.strip())
        return deepcopy(self.outcome)

    @_scoped_lock
    def cancel(self, reason='cancelled'):
        """Stop fences the task. Pending work is never reported as confirmed."""
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise InvestigationError('invalid-cancel-reason')
        self._sync_owner()
        if (not self._cancel_requested and self.state in self.TERMINAL_STATES
                and not self._worker_pending and self._cleanup_status == 'confirmed'):
            return deepcopy(self.outcome)
        self._pending = None
        if self._cancel_reason is None:
            self._cancel_reason = reason.strip()
        self._cancel_requested = True
        self.state = 'cancelling' if self._owner is not None else 'cancelled'
        self.outcome = self._outcome(self.state, self._cancel_reason, stop_confirmed=self._owner is None)
        if self._job_id is not None and not self._cancel_sent:
            try:
                self._owner.cancel(self._job_id)
                self._cancel_sent = True
            except Exception as exc:
                self._owner_error_type = type(exc).__name__
                return deepcopy(self.outcome)
        self._sync_owner()
        return deepcopy(self.outcome)

    @_scoped_lock
    def summary(self):
        self._sync_owner()
        return self._summary()

    def _summary(self):
        return {'schema_version': SCHEMA_VERSION, 'task_id': self.task_id,
                'conversation_id': self.conversation_id, 'state': self.state,
                'job_id': self._job_id, 'owner_job_state': self._owner_job_state,
                'worker_pending': self._worker_pending, 'cleanup_status': self._cleanup_status,
                'owner_error_type': self._owner_error_type,
                'verification': (self.outcome or {}).get('verification', 'NOT VERIFIED'),
                'fix_verified': False,
                'stop_confirmed': (self.outcome or {}).get('stop_confirmed', False),
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
