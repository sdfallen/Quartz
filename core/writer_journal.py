"""Durable writer exclusion, not process authority or an automatic replay engine."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import threading
import time
import uuid

from core.atomic_json import atomic_write_json


def process_identity(pid):
    import psutil
    try:
        proc = psutil.Process(int(pid))
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return {'state':'gone'}
        return {'state':'observed', 'pid':proc.pid, 'created':proc.create_time(),
                'exe':os.path.normcase(proc.exe())}
    except psutil.NoSuchProcess:
        return {'state':'gone'}
    except (psutil.Error, OSError, ValueError, TypeError):
        return {'state':'unknown'}


def identity_state(expected, probe=process_identity):
    if not expected or expected.get('state') != 'observed': return 'unknown'
    actual = probe(expected.get('pid'))
    if actual.get('state') != 'observed': return actual.get('state', 'unknown')
    return 'live' if all(actual.get(k) == expected.get(k) for k in ('pid','created','exe')) else 'replaced'


class WriterJournal:
    LIMIT = 128
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, path=None, *, probe=process_identity):
        self.path = Path(path) if path is not None else None
        self.probe = probe
        self.session = uuid.uuid4().hex
        self.owner = probe(os.getpid()) if self.path else {}
        self.lock = threading.RLock()
        self.claims = {}
        self.error = ''
        try: self._load()
        except (OSError, ValueError) as exc: self.error = str(exc)

    def _load(self):
        if not self.path or not self.path.exists():
            self.claims = {}; return
        if self.path.stat().st_size > self.MAX_BYTES: raise ValueError('Writer journal size limit exceeded')
        raw = json.loads(self.path.read_text(encoding='utf-8'))
        claims = raw.get('claims') if isinstance(raw, dict) and raw.get('version') == 1 else None
        if not isinstance(claims, dict) or len(claims) > self.LIMIT:
            raise ValueError('Invalid writer journal inventory')
        for key, value in claims.items():
            if not isinstance(value, dict) or value.get('id') != key or not isinstance(value.get('project'), str):
                raise ValueError('Invalid writer claim')
        self.claims = claims

    @contextmanager
    def _transaction(self, *, write=True):
        with self.lock:
            if self.error: raise OSError(self.error)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # OS-held, nonblocking single-byte lock; released by the OS on crash.
            # Atomic JSON replacement alone would not prevent two processes from
            # reserving against the same old inventory.
            with self.path.with_suffix('.lock').open('a+b') as handle:
                handle.seek(0, 2)
                if handle.tell() == 0: handle.write(b'0'); handle.flush()
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    try: self._load()
                    except (OSError, ValueError) as exc:
                        self.error = str(exc)
                        raise
                    candidate = deepcopy(self.claims)
                    yield candidate
                    if write: atomic_write_json(self.path, {'version':1, 'claims':candidate})
                    self.claims = candidate
                finally:
                    handle.seek(0)
                    if os.name == 'nt': msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def conflicts(project, exclusive, claim):
        old, new = Path(claim['project']), Path(project)
        return exclusive or claim.get('exclusive') or old == new or old in new.parents or new in old.parents

    def reserve(self, project, exclusive, provider):
        if self.path is None: return None  # Explicit ephemeral library use.
        with self._transaction() as claims:
            if any(self.conflicts(project, exclusive, c) for c in claims.values()):
                raise RuntimeError('Önceki/başka yazıcı durumu çözülmeden bu kapsamda yeni yazıcı başlatılamaz.')
            if len(claims) >= self.LIMIT: raise RuntimeError('Writer journal capacity reached')
            key = uuid.uuid4().hex
            claims[key] = {'id':key, 'project':project, 'exclusive':bool(exclusive), 'provider':provider,
                           'session':self.session, 'owner_process':self.owner, 'process':None,
                           'stage':'preparing', 'created_at':time.time()}
        return key

    def update(self, key, *, stage, run_id=None, pid=None):
        if key is None: return
        with self._transaction() as claims:
            claim = claims[key]
            if claim['session'] != self.session: raise PermissionError('Writer claim ownership changed')
            claim['stage'] = stage
            if run_id is not None: claim['run_id'] = run_id
            if pid is not None: claim['process'] = self.probe(pid)

    def finish(self, key, *, verify_process=False):
        if key is None: return
        with self._transaction() as claims:
            if key in claims:
                if claims[key]['session'] != self.session: raise PermissionError('Writer claim ownership changed')
                if verify_process:
                    proc = claims[key].get('process')
                    state = identity_state(proc, self.probe)
                    if not proc or (proc.get('state') != 'gone' and state not in {'gone','replaced'}):
                        raise RuntimeError('Terminal run status does not prove the owned writer process stopped.')
                del claims[key]

    def recovery_status(self):
        with self.lock:
            return {'blocked':bool(self.error) or bool(self.claims),
                    'error':self.error, 'claims':[deepcopy(c) for c in self.claims.values()],
                    'automatic_replay':False, 'processes_terminated':False}

    def refresh(self):
        if self.path is not None:
            with self._transaction(write=False): pass

    def inspect(self, key):
        if self.path is None: raise KeyError(key)
        with self._transaction(write=False) as claims:
            claim = deepcopy(claims[key])
        return {**claim, 'owner_state':identity_state(claim.get('owner_process'), self.probe),
                'process_state':identity_state(claim.get('process'), self.probe),
                'warning':'Root PID absence does not prove all descendants stopped. Review external activity and files.',
                'permissions_restored':False}

    def acknowledge(self, key, *, confirmed=False, external_review=False):
        if confirmed is not True or external_review is not True:
            raise PermissionError('Süreç/dosya incelemesi ve açık kullanıcı onayı gerekli.')
        if self.path is None: raise KeyError(key)
        with self._transaction() as claims:
            claim = claims[key]
            if claim.get('session') == self.session: raise PermissionError('Aktif yerel yazıcı bu akıştan bırakılamaz.')
            states = [identity_state(claim.get('owner_process'), self.probe), identity_state(claim.get('process'), self.probe)]
            if 'live' in states or any(state == 'unknown' for state, data in zip(states, [claim.get('owner_process'),claim.get('process')]) if data and data.get('state') == 'observed'):
                raise RuntimeError('Kayıtlı süreç hâlâ çalışıyor veya güvenle gözlenemiyor; kontrolü atlayamazsınız.')
            # Archive the exact claim before removing exclusion. This is NEVER
            # a grant, a kill operation, a replay, or restored process ownership.
            archive = self.path.parent/'writer-recovery'/(key+'-'+uuid.uuid4().hex+'.json')
            atomic_write_json(archive, {'claim':claim, 'acknowledged_at':time.time(), 'external_review':True})
            del claims[key]
        return {'released_claim':key, 'archive':str(archive), 'automatic_replay':False, 'permissions_restored':False}
