"""Asynchronous, bounded self-inspection. Never repairs or executes the target."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
import time
import uuid

from core.atomic_json import atomic_write_json
from core.cli_installer import app_root


class InspectionCancelled(Exception):
    pass


def safe_member(root, relative):
    """Manifest paths are untrusted. Never follow them to secrets or other projects."""
    path = PurePosixPath(relative)
    forbidden = {'.env', '.quartz', '.gemini', '.codex', 'cookies', 'auth.json',
                 'oauth_creds.json', 'quartz_memory.json', 'quartz_conversations.json',
                 'quartz_projects.json', 'mobile_access.json', 'credentials.json'}
    if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative
            or path.is_absolute() or '..' in path.parts
            or any(p.lower() in forbidden or p.startswith('.') for p in path.parts)
            or (path.parts[0] != '_internal' and relative not in {'Quartz.exe', 'README.txt'})):
        raise ValueError('Paket manifestinde izin verilmeyen yol var')
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise ValueError('Paket incelemesinde bağlantılı dosya izlenmez')
    if root not in current.resolve().parents:
        raise ValueError('Dosya uygulama kapsamı dışında')
    return current


class SelfDiagnosticsService:
    SCOPE = 'self'
    MAX_FILES = 6000
    MAX_BYTES = 1536 * 1024 * 1024
    DEADLINE_SECONDS = 180
    REQUIRED = ('Quartz.exe', '_internal/operator/QuartzDesktopMCP.exe',
                '_internal/assets/workspace.css', '_internal/assets/branding/quartz-q.ico',
                '_internal/assets/bin/squad.exe')

    def __init__(self, base=None, reports=None, rea=None):
        self.base = (Path(base) if base is not None else app_root()).resolve()
        self.reports = Path(reports) if reports is not None else Path(
            os.environ.get('LOCALAPPDATA') or Path.home()) / 'Quartz/diagnostics'
        self.rea = rea
        self.lock = threading.RLock()
        self.jobs = {}
        self.latest = None
        self.events = {}
        self.threads = {}

    def start(self, include_rea=True):
        if type(include_rea) is not bool:
            raise ValueError('include_rea true veya false olmalı')
        with self.lock:
            if self.latest and self.jobs[self.latest]['state'] == 'running':
                return deepcopy(self.jobs[self.latest])
            while len(self.jobs) >= 5:
                oldest = next(iter(self.jobs))
                self.jobs.pop(oldest); self.events.pop(oldest, None); self.threads.pop(oldest, None)
            identity = uuid.uuid4().hex
            self.latest = identity
            self.jobs[identity] = {
                'schema_version': 1, 'scope': self.SCOPE, 'id': identity, 'state': 'running', 'phase': 'queued',
                'progress': 0, 'message': 'Quartz öz teşhisi hazırlanıyor…', 'checks': [],
                'verdict': 'UNKNOWN', 'limitations': ['Salt okunur paket incelemesi; çalışma zamanı ve model erişimi testi değildir.',
                    'Manifest karşılaştırması kendi içinde tutarlılığı ölçer; yayıncı imzasını doğrulamaz.'],
                'started_at': time.time(), 'finished_at': None, 'report_path': None, 'rea_used': False}
            event = self.events[identity] = threading.Event()
            thread = self.threads[identity] = threading.Thread(target=self._work, args=(identity, event, include_rea),
                                                             name='quartz-self-diagnostics', daemon=True)
            thread.start()
            return deepcopy(self.jobs[identity])

    def status(self, job_id=None):
        with self.lock:
            identity = job_id or self.latest
            if identity is None:
                return {'schema_version': 1, 'id': None, 'state': 'idle', 'phase': 'queued',
                        'progress': 0, 'message': 'Henüz teşhis başlatılmadı', 'checks': [],
                        'verdict': 'UNKNOWN', 'limitations': [], 'started_at': None,
                        'finished_at': None, 'report_path': None, 'rea_used': False}
            if identity not in self.jobs:
                raise ValueError('Teşhis işi bulunamadı')
            return deepcopy(self.jobs[identity])

    def cancel(self, job_id):
        with self.lock:
            if not isinstance(job_id, str) or job_id not in self.jobs:
                raise ValueError('Teşhis işi bulunamadı')
            if self.jobs[job_id]['state'] == 'running':
                self.events[job_id].set()
                self.jobs[job_id]['message'] = 'Teşhis iptal ediliyor…'
            return deepcopy(self.jobs[job_id])

    def shutdown(self):
        with self.lock:
            threads = list(self.threads.values())
            for event in self.events.values(): event.set()
        for thread in threads:
            if thread is not threading.current_thread(): thread.join(timeout=6)

    def _update(self, identity, **values):
        with self.lock: self.jobs[identity].update(values)

    def _check(self, identity, name, status, title, message, **evidence):
        assert status in {'PASS', 'FAIL', 'UNKNOWN', 'NOT_TESTED'}
        with self.lock:
            self.jobs[identity]['checks'].append({'id': name, 'status': status, 'title': title,
                                                 'message': message, 'evidence': evidence})

    def _guard(self, event, deadline):
        if event.is_set(): raise InspectionCancelled()
        if time.monotonic() > deadline: raise TimeoutError()

    def _hash(self, path, event, deadline):
        self._guard(event, deadline)
        before = path.stat()
        digest, count = hashlib.sha256(), 0
        with path.open('rb') as stream:
            while chunk := stream.read(256 * 1024):
                self._guard(event, deadline)
                count += len(chunk)
                if count > before.st_size: raise RuntimeError('file-changed')
                digest.update(chunk)
        after = path.stat()
        if count != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('file-changed')
        return digest.hexdigest()

    def _manifest(self, identity, event, deadline):
        manifest = self.base / 'release-manifest.json'
        if not manifest.is_file():
            self._check(identity, 'manifest', 'NOT_TESTED', 'Paket manifesti',
                        'Bu kurulumda karşılaştırılabilir release-manifest.json yok.')
            return
        if manifest.is_symlink() or manifest.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('invalid-manifest')
        data = json.loads(manifest.read_text(encoding='utf-8'))
        files = data.get('files') if isinstance(data, dict) else None
        if not isinstance(files, dict) or not files or len(files) > self.MAX_FILES:
            raise ValueError('invalid-manifest')
        # Validate the ENTIRE path set before reading any referenced file.
        entries = []
        total = 0
        for name, expected in files.items():
            if not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected):
                raise ValueError('invalid-manifest')
            target = safe_member(self.base, name)
            if target.is_file(): total += target.stat().st_size
            entries.append((name, target, expected))
        if 'Quartz.exe' not in files or total > self.MAX_BYTES:
            raise ValueError('manifest-limit')
        mismatch, missing, count = [], [], 0
        for name, target, expected in entries:
            self._guard(event, deadline)
            if not target.is_file(): missing.append(name)
            elif self._hash(target, event, deadline) != expected: mismatch.append(name)
            count += 1
            if count % 50 == 0:
                self._update(identity, progress=20 + int(40 * count / len(entries)),
                             message=f'Paket dosyaları karşılaştırılıyor: {count}/{len(entries)}')
        self._check(identity, 'manifest', 'FAIL' if missing or mismatch else 'PASS', 'Paket bütünlüğü',
                    'Manifestteki dosyalarla fark bulundu.' if missing or mismatch else 'Manifestteki dosyaların SHA-256 değerleri eşleşiyor.',
                    compared=count, bytes=total, mismatch_count=len(mismatch), missing_count=len(missing),
                    mismatches=mismatch[:20], missing=missing[:20])

    def _inspect(self, identity, event, deadline, include_rea):
        self._update(identity, phase='scope', progress=5, message='Uygulama kapsamı doğrulanıyor…')
        self._guard(event, deadline)
        if self.base.is_symlink() or getattr(self.base, 'is_junction', lambda: False)():
            raise ValueError('unsafe-root')
        target = safe_member(self.base, 'Quartz.exe')
        if not target.is_file():
            self._check(identity, 'scope', 'NOT_TESTED', 'Çalışma biçimi',
                        'Kaynak modunda çalışılıyor; paket denetimi için paketlenmiş Quartz kullanılmalı.')
        else:
            digest = self._hash(target, event, deadline)
            self._check(identity, 'scope', 'PASS', 'İncelenen uygulama',
                        'Yalnız bu Quartz paketinin ikilisi seçildi; ikili çalıştırılmayacak.', sha256=digest, bytes=target.stat().st_size)
            self._update(identity, phase='resources', progress=15, message='Gerekli kaynaklar kontrol ediliyor…')
            missing = [name for name in self.REQUIRED if not safe_member(self.base, name).is_file()]
            self._check(identity, 'resources', 'FAIL' if missing else 'PASS', 'Gerekli bileşenler',
                        'Gerekli paket bileşenleri eksik.' if missing else 'Yardımcı araç, Q simgesi ve arayüz kaynakları mevcut.', missing=missing)
            self._update(identity, phase='manifest', progress=20, message='Paket manifesti inceleniyor…')
            self._manifest(identity, event, deadline)
            self._update(identity, phase='rea', progress=65, message='REA statik incelemesi hazırlanıyor…')
            if include_rea:
                from core.rea_adapter import ReaAdapter
                result = (self.rea or ReaAdapter()).inspect(target, event=event, deadline=deadline)
                self._guard(event, deadline)
                self._check(identity, 'rea', result['status'], 'REA paket incelemesi', result['message'], **result.get('evidence', {}))
                self._update(identity, rea_used=bool(result.get('used')))
            else:
                self._check(identity, 'rea', 'NOT_TESTED', 'REA paket incelemesi', 'Bu koşuda REA incelemesi seçilmedi.')

    def _on_completed(self, identity, snapshot):
        pass

    def _work(self, identity, event, include_rea):
        deadline = time.monotonic() + self.DEADLINE_SECONDS
        try:
            self._inspect(identity, event, deadline, include_rea)
            self._guard(event, deadline)
            checks = self.status(identity)['checks']
            verdict = 'FAIL' if any(c['status'] == 'FAIL' for c in checks) else 'PASS' if checks and all(c['status'] == 'PASS' for c in checks) else 'PARTIAL'
            self._update(identity, phase='report', progress=95, verdict=verdict, message='Teşhis kanıtları kaydediliyor…')
            self.reports.mkdir(parents=True, exist_ok=True)
            report = self.reports / (identity + '.json')
            self._guard(event, deadline)
            snapshot = self.status(identity)
            snapshot.update(state='completed', phase='done', progress=100, finished_at=time.time(), report_path=str(report),
                            message='Teşhis tamamlandı; kapsam ve bulguları inceleyebilirsiniz.')
            # Knowledge persistence may re-hash the target; keep it outside the
            # status lock so UI polling never stalls on large executables.
            self._on_completed(identity, snapshot)
            with self.lock:
                self._guard(event, deadline)
                atomic_write_json(report, snapshot)
                extra_keys = ('knowledge_saved',) if 'knowledge_saved' in snapshot else ()
                self._update(identity, **{k: snapshot[k] for k in ('state', 'phase', 'progress', 'finished_at', 'report_path', 'message', *extra_keys)})
        except InspectionCancelled:
            self._update(identity, state='cancelled', phase='done', verdict='UNKNOWN', finished_at=time.time(), message='Teşhis iptal edildi; yarım inceleme başarı sayılmadı.')
        except Exception as exc:
            # Never leak file contents, provider output, account data or raw exceptions.
            self._check(identity, 'inspection', 'UNKNOWN', 'Tamamlanamayan inceleme',
                        'İnceleme güvenli biçimde tamamlanamadı; kapsamı ve paket erişimini kontrol edin.', reason=type(exc).__name__)
            self._update(identity, state='failed', phase='done', verdict='UNKNOWN', finished_at=time.time(), message='Teşhis tamamlanamadı; uygulamanın hatalı olduğu sonucu çıkarılmadı.')
