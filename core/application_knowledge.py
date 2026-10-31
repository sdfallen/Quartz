"""Local evidence memory for exact approved executables, never model-authored policy."""
from copy import deepcopy
import hashlib
import json
import os
import re
from pathlib import Path
import threading
import time

from core.atomic_json import atomic_write_json
from core.artifact_diagnostics import selected_executable, ArtifactDiagnosticsService
from core.path_identity import canonical_key


class ApplicationKnowledge:
    TTL = 30 * 86400
    ALLOWED_KEYS = {
        'sha256', 'bytes',
        'machine', 'sections', 'architecture', 'pe_format', 'subsystem',
        'is_dll', 'large_address_aware', 'dynamic_base', 'high_entropy_va',
        'nx_compat', 'has_resources', 'has_overlay', 'overlay_bytes',
        'format', 'nodes', 'archive_entries', 'verified_member_hashes',
        'integrity_contradictions', 'source_complete', 'rea_version',
        'analysis_scope', 'runtime_tested', 'cached_runtime', 'elapsed_ms',
        'verified_runs', 'verified_actions', 'focus_verified',
        'observation_verified', 'requires_elevation', 'uipi_restricted',
        'last_outcome',
    }
    ALLOWED_OUTCOMES = {'completed', 'partial', 'blocked', 'failed', 'cancelled'}

    def __init__(self, root=None):
        self.root = Path(root or Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'Quartz/application-knowledge')
        self.lock = threading.RLock()

    def location(self, path):
        identity = canonical_key(path)
        return self.root / (hashlib.sha256(identity.encode()).hexdigest() + '.json')

    @staticmethod
    def fingerprint(path):
        stat = path.stat()
        return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]

    @staticmethod
    def digest(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()

    @classmethod
    def _validate_facts(cls, facts):
        if not isinstance(facts, list) or len(facts) > 4:
            return False
        for fact in facts:
            if not isinstance(fact, dict) or not isinstance(fact.get('values'), dict) or len(fact['values']) > 16:
                return False
            if fact.get('source') not in {'artifact', 'pe', 'rea', 'operational'}:
                return False
            if fact.get('status') not in {'PASS', 'FAIL', 'UNKNOWN', 'NOT_TESTED'}:
                return False
            for key, value in fact.get('values', {}).items():
                if key not in cls.ALLOWED_KEYS:
                    return False
                if type(value) in {int, bool}:
                    continue
                if key == 'sha256' and isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value):
                    continue
                if key == 'format' and value in {'pe', 'pyinstaller'}:
                    continue
                if key == 'rea_version' and value == '6.8.0':
                    continue
                if key == 'analysis_scope' and value == 'root-inventory':
                    continue
                if key == 'architecture' and value in {'x64', 'x86', 'arm64', 'unknown'}:
                    continue
                if key == 'pe_format' and value in {'PE32', 'PE32+', 'unknown'}:
                    continue
                if key == 'subsystem' and value in {'windows_gui', 'windows_cui', 'native', 'efi', 'other'}:
                    continue
                if key == 'last_outcome' and value in cls.ALLOWED_OUTCOMES:
                    continue
                return False
        return True

    def get(self, value):
        try:
            return self._get(value)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _get(self, value):
        path = selected_executable(value)
        with self.lock:
            file = self.location(path)
            if not file.is_file() or file.is_symlink() or file.stat().st_size > 64 * 1024:
                return None
            data = json.loads(file.read_text(encoding='utf-8'))
            if (not isinstance(data, dict)
                    or data.get('verdict') not in {'PASS', 'FAIL', 'PARTIAL', 'UNKNOWN'}
                    or not self._validate_facts(data.get('facts'))):
                return None
            if (data.get('schema') != 1 or data.get('fingerprint') != self.fingerprint(path)
                    or not 0 <= time.time() - data.get('observed_at', 0) <= self.TTL
                    or self.digest(path) != data.get('sha256')
                    or data.get('fingerprint') != self.fingerprint(path)):
                return None
            return {k: data[k] for k in ('schema', 'sha256', 'fingerprint', 'observed_at', 'verdict', 'facts')} | {
                'scope': 'static-file-evidence; runtime/UI procedures not established',
                'instruction_authority': False,
            }

    def save(self, value, report):
        path = selected_executable(value)
        fingerprint = self.fingerprint(path)
        if report.get('state') != 'completed':
            raise ValueError('Yarım veya iptal edilmiş inceleme öğrenilmez')
        checks = report.get('checks', [])
        source = next((c for c in checks if c['id'] == 'artifact' and c['status'] == 'PASS'), None)
        if (not source or self.digest(path) != source['evidence']['sha256']
                or fingerprint != self.fingerprint(path)):
            raise ValueError('Dosya inceleme sonrası değişti; bilgi kaydedilmedi')
        # No strings from the binary, screenshot, log or model are admitted.
        facts = []
        for c in checks:
            if c['id'] not in {'artifact', 'pe', 'rea'}:
                continue
            values = {k: v for k, v in c.get('evidence', {}).items() if k in self.ALLOWED_KEYS and type(v) in {str, int, bool}}
            if c['status'] in {'PASS', 'FAIL', 'UNKNOWN', 'NOT_TESTED'}:
                facts.append({'source': c['id'], 'status': c['status'], 'values': values})
        with self.lock:
            existing = self.get(path)
            if existing and existing.get('sha256') == source['evidence']['sha256']:
                op_fact = next((f for f in existing.get('facts', []) if f.get('source') == 'operational'), None)
                if op_fact and not any(f.get('source') == 'operational' for f in facts):
                    facts.append(deepcopy(op_fact))
            record = {
                'schema': 1,
                'sha256': source['evidence']['sha256'],
                'fingerprint': fingerprint,
                'observed_at': time.time(),
                'verdict': report['verdict'],
                'facts': facts,
                'scope': 'static-file-evidence; runtime/UI procedures not established',
                'instruction_authority': False,
            }
            self.root.mkdir(parents=True, exist_ok=True)
            if not self.location(path).exists() and len(list(self.root.glob('*.json'))) >= 200:
                raise ValueError('Bilgi deposu sınırı doldu; eski bilgi silinmedi')
            atomic_write_json(self.location(path), record)
        return record

    def record_operation(self, value, *, outcome=None, verified_runs=0, verified_actions=0,
                         focus_verified=False, observation_verified=False,
                         requires_elevation=False, uipi_restricted=False):
        """Merge bounded, typed operational telemetry into a verified binary's knowledge record."""
        path = selected_executable(value)
        with self.lock:
            fingerprint = self.fingerprint(path)
            digest = self.digest(path)
            existing = self.get(path)
            if existing is None or existing.get('sha256') != digest or existing.get('fingerprint') != fingerprint:
                facts = [{'source': 'artifact', 'status': 'PASS', 'values': {'sha256': digest, 'bytes': int(fingerprint[2])}}]
                verdict = 'PARTIAL'
            else:
                facts = [deepcopy(f) for f in existing.get('facts', []) if f.get('source') != 'operational']
                verdict = existing.get('verdict', 'PARTIAL')
            prev_op = {}
            if existing and existing.get('sha256') == digest:
                found = next((f for f in existing.get('facts', []) if f.get('source') == 'operational'), None)
                if found and isinstance(found.get('values'), dict):
                    prev_op = dict(found['values'])
            op_values = {
                'verified_runs': max(0, int(prev_op.get('verified_runs', 0)) + max(0, int(verified_runs))),
                'verified_actions': max(0, int(prev_op.get('verified_actions', 0)) + max(0, int(verified_actions))),
                'focus_verified': bool(prev_op.get('focus_verified', False) or focus_verified),
                'observation_verified': bool(prev_op.get('observation_verified', False) or observation_verified),
                'requires_elevation': bool(prev_op.get('requires_elevation', False) or requires_elevation),
                'uipi_restricted': bool(prev_op.get('uipi_restricted', False) or uipi_restricted),
            }
            if outcome in self.ALLOWED_OUTCOMES:
                op_values['last_outcome'] = outcome
            elif prev_op.get('last_outcome') in self.ALLOWED_OUTCOMES:
                op_values['last_outcome'] = prev_op['last_outcome']
            if fingerprint != self.fingerprint(path) or self.digest(path) != digest:
                raise ValueError('Dosya işlem kaydı sırasında değişti; bilgi kaydedilmedi')
            facts.append({'source': 'operational', 'status': 'PASS', 'values': op_values})
            record = {
                'schema': 1,
                'sha256': digest,
                'fingerprint': fingerprint,
                'observed_at': time.time(),
                'verdict': verdict,
                'facts': facts,
                'scope': 'static-file-evidence; runtime/UI procedures not established',
                'instruction_authority': False,
            }
            self.root.mkdir(parents=True, exist_ok=True)
            if not self.location(path).exists() and len(list(self.root.glob('*.json'))) >= 200:
                raise ValueError('Bilgi deposu sınırı doldu; eski bilgi silinmedi')
            atomic_write_json(self.location(path), record)
            return record

    def list_learned(self, limit=50):
        """Return validated, path-free knowledge summaries from the store."""
        with self.lock:
            if not self.root.is_dir():
                return []
            items = []
            files = sorted(self.root.glob('*.json'), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
            for file in files[:max(1, min(int(limit), 200))]:
                try:
                    if not file.is_file() or file.is_symlink() or file.stat().st_size > 64 * 1024:
                        continue
                    data = json.loads(file.read_text(encoding='utf-8'))
                    if (not isinstance(data, dict)
                            or data.get('schema') != 1
                            or data.get('verdict') not in {'PASS', 'FAIL', 'PARTIAL', 'UNKNOWN'}
                            or not isinstance(data.get('sha256'), str)
                            or not re.fullmatch('[a-f0-9]{64}', data['sha256'])
                            or not 0 <= time.time() - data.get('observed_at', 0) <= self.TTL
                            or not self._validate_facts(data.get('facts'))):
                        continue
                    items.append({
                        'sha256': data['sha256'],
                        'observed_at': data['observed_at'],
                        'verdict': data['verdict'],
                        'facts': data['facts'],
                        'scope': 'static-file-evidence; runtime/UI procedures not established',
                        'instruction_authority': False,
                    })
                except (OSError, ValueError, KeyError, TypeError):
                    continue
            return items


class ApplicationLearning:
    """One bounded worker; does not block the task/permission/UI locks."""
    def __init__(self, root=None):
        self.store = ApplicationKnowledge(root)
        self.lock = threading.RLock()
        self.jobs = {}
        self.ops = {}
        self.cancel = threading.Event()
        self.worker_lock = threading.Lock()

    def start(self, value):
        path = selected_executable(value)
        key = str(path)
        with self.lock:
            if key in self.jobs:
                return
            self.jobs[key] = {'state': 'queued', 'knowledge': None}
        threading.Thread(target=self._work, args=(path,), daemon=True, name='quartz-app-learning').start()

    def note_operation(self, value, **kwargs):
        """Record verified runtime telemetry (elevation, UIPI, focus, observation, verified_actions)."""
        try:
            path = selected_executable(value)
        except (OSError, ValueError):
            return None
        key = str(path)
        flush_now = False
        with self.lock:
            acc = self.ops.setdefault(key, {
                'verified_runs': 0,
                'verified_actions': 0,
                'focus_verified': False,
                'observation_verified': False,
                'requires_elevation': False,
                'uipi_restricted': False,
                'outcome': None,
            })
            acc['verified_runs'] += max(0, int(kwargs.get('verified_runs', 0)))
            acc['verified_actions'] += max(0, int(kwargs.get('verified_actions', 0)))
            acc['focus_verified'] = bool(acc['focus_verified'] or kwargs.get('focus_verified', False))
            acc['observation_verified'] = bool(acc['observation_verified'] or kwargs.get('observation_verified', False))
            acc['requires_elevation'] = bool(acc['requires_elevation'] or kwargs.get('requires_elevation', False))
            acc['uipi_restricted'] = bool(acc['uipi_restricted'] or kwargs.get('uipi_restricted', False))
            if kwargs.get('outcome') in ApplicationKnowledge.ALLOWED_OUTCOMES:
                acc['outcome'] = kwargs['outcome']
            if key in self.jobs and self.jobs[key].get('state') == 'completed':
                flush_now = True
                pending_ops = dict(self.ops.pop(key))
        if flush_now:
            try:
                updated = self.store.record_operation(path, **pending_ops)
                with self.lock:
                    if key in self.jobs and self.jobs[key].get('state') == 'completed':
                        self.jobs[key]['knowledge'] = updated
                return updated
            except (OSError, ValueError):
                return None
        return None

    def finalize(self, outcome=None):
        """Flush any accumulated operational telemetry for learned executables."""
        with self.lock:
            keys = list(set(self.jobs.keys()) | set(self.ops.keys()))
        for key in keys:
            with self.lock:
                if self.jobs.get(key, {}).get('state') != 'completed':
                    continue
                pending = dict(self.ops.pop(key, {}))
            if outcome in ApplicationKnowledge.ALLOWED_OUTCOMES:
                pending['outcome'] = outcome
                # Only a completed task counts as a verified run; failures are
                # recorded as last_outcome without inflating success counters.
                if outcome == 'completed':
                    pending['verified_runs'] = max(1, int(pending.get('verified_runs', 0)))
            if not pending:
                continue
            try:
                updated = self.store.record_operation(Path(key), **pending)
                with self.lock:
                    if key in self.jobs and self.jobs[key].get('state') == 'completed':
                        self.jobs[key]['knowledge'] = updated
            except (OSError, ValueError):
                pass

    def _work(self, path):
        service = None
        key = str(path)
        try:
            with self.worker_lock:
                if self.cancel.is_set():
                    return
                with self.lock:
                    self.jobs[key]['state'] = 'running'
                cached = self.store.get(path)
                if self.cancel.is_set():
                    return
                if cached is None:
                    # The learner persists once below; avoid a duplicate save/hash.
                    service = ArtifactDiagnosticsService(path, knowledge=False)
                    job = service.start()
                    while service.status(job['id'])['state'] == 'running':
                        if self.cancel.wait(.2):
                            service.cancel(job['id'])
                            return
                    if self.cancel.is_set():
                        return
                    cached = self.store.save(path, service.status(job['id']))
                with self.lock:
                    pending_ops = dict(self.ops.pop(key, {})) if key in self.ops else None
                if pending_ops:
                    try:
                        cached = self.store.record_operation(path, **pending_ops)
                    except (OSError, ValueError):
                        pass
                with self.lock:
                    self.jobs[key] = {'state': 'completed', 'knowledge': cached}
        except Exception as exc:
            with self.lock:
                self.jobs[key] = {'state': 'unavailable', 'reason': type(exc).__name__, 'knowledge': None}
        finally:
            if service:
                service.shutdown()
            if self.cancel.is_set():
                with self.lock:
                    if self.jobs[key]['state'] != 'completed':
                        self.jobs[key] = {'state': 'cancelled', 'knowledge': None}

    def context(self):
        with self.lock:
            # No directory paths or arbitrary instructions in model context.
            result = []
            for p, j in self.jobs.items():
                item = deepcopy(j)
                if item.get('knowledge'):
                    try:
                        if self.store.fingerprint(Path(p)) != item['knowledge']['fingerprint']:
                            item = {'state': 'outdated', 'knowledge': None}
                    except OSError:
                        item = {'state': 'outdated', 'knowledge': None}
                result.append({'application': Path(p).name, **item})
            return result

    def stop(self):
        self.cancel.set()
