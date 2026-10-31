"""Explicit, same-build static-resource repair with private backup and rollback.

The selected reference is a user trust decision, NOT publisher authentication.
No executable, settings, chat history, manifest or arbitrary path is writable.
"""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from core.self_diagnostics import safe_member
from core.atomic_json import atomic_write_json


class PackageRepair:
    ALLOWED = ('_internal/assets/workspace.css', '_internal/assets/branding/quartz-q.ico')
    MAX_BYTES = 8 * 1024 * 1024

    def __init__(self, base, backups):
        for root in (Path(base).absolute(), Path(backups).absolute()):
            for part in (root, *root.parents):
                if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
                    raise ValueError('Onarım veya yedek yolu bağlantı olamaz')
        self.base = Path(base).resolve()
        self.backups = Path(backups).resolve()
        if self.backups == self.base or self.base in self.backups.parents:
            raise ValueError('Onarım yedeği paket dışında olmalı')
        self.lock = threading.RLock()
        self.plan = None

    @staticmethod
    def digest(path):
        if not path.exists():
            return None
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()

    def prepare(self, reference):
        with self.lock:
            self.plan = None
            root = Path(reference).absolute()
            for part in (root, *root.parents):
                if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
                    raise ValueError('Referans klasörü bağlantı olamaz')
            root = root.resolve(strict=True)
            if root == self.base:
                raise ValueError('Ayrı, bilinen sağlam bir paket seçilmeli')
            target_exe = safe_member(self.base, 'Quartz.exe')
            reference_exe = safe_member(root, 'Quartz.exe')
            if any(not p.is_file() or p.stat().st_size > 512 * 1024 * 1024
                   for p in (target_exe, reference_exe)):
                raise ValueError('Paket EXE dosyası eksik veya inceleme sınırını aşıyor')
            build = self.digest(target_exe)
            if build is None or build != self.digest(reference_exe):
                raise ValueError('Referans aynı Quartz EXE sürümüyle eşleşmiyor')
            manifest = root / 'release-manifest.json'
            if manifest.is_symlink() or manifest.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('Referans manifesti geçersiz')
            files = json.loads(manifest.read_text(encoding='utf-8')).get('files', {})
            if files.get('Quartz.exe') != build:
                raise ValueError('Referans EXE manifestle eşleşmiyor')
            changes = []
            for name in self.ALLOWED:
                source = safe_member(root, name)
                target = safe_member(self.base, name)
                if not source.is_file() or source.stat().st_size > self.MAX_BYTES:
                    raise ValueError('Referans kaynağı eksik veya çok büyük')
                if target.exists() and (not target.is_file() or target.stat().st_size > self.MAX_BYTES):
                    raise ValueError('Hedef kaynak güvenli onarım sınırını aşıyor')
                data = source.read_bytes()
                if len(data) > self.MAX_BYTES:
                    raise ValueError('Kaynak okuma sınırı aşıldı')
                expected = hashlib.sha256(data).hexdigest()
                if expected != files.get(name):
                    raise ValueError('Referans kaynağı manifestle eşleşmiyor')
                before = self.digest(target)
                if before != expected:
                    changes.append({'name': name, 'before': before, 'after': expected, 'data': data})
            self.plan = {'id': uuid.uuid4().hex, 'expires': time.monotonic() + 300,
                         'build': build, 'changes': changes}
            return {'id': self.plan['id'], 'files': [c['name'] for c in changes],
                    'message': 'Yalnız seçtiğiniz aynı sürüm referansındaki CSS ve Q simgesi geri yüklenecek. '
                               'Referansın güvenilirliği yayıncı imzasıyla doğrulanmadı; bildiğiniz sağlam paketi seçmelisiniz.',
                    'requires_confirmation': bool(changes)}

    @staticmethod
    def _replace(path, data):
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.repair')
        try:
            with temporary.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def apply(self, identity):
        with self.lock:
            plan, self.plan = self.plan, None  # One use; retries cannot apply twice.
            if not plan or identity != plan['id'] or time.monotonic() > plan['expires']:
                raise ValueError('Onarım planı geçersiz veya süresi dolmuş; yeniden inceleyin')
            if self.digest(safe_member(self.base, 'Quartz.exe')) != plan['build']:
                raise ValueError('Çalışan paket sürümü değişti; onarım uygulanmadı')
            originals = {}
            for item in plan['changes']:
                target = safe_member(self.base, item['name'])
                if self.digest(target) != item['before']:
                    raise ValueError('Hedef plan sonrası değişti; onarım uygulanmadı')
                if not target.parent.is_dir():
                    raise ValueError('Kaynak klasörü eksik; tam paket kurulumu gerekiyor')
                originals[item['name']] = target.read_bytes() if target.exists() else None
            if not originals:
                return {'state': 'unchanged', 'message': 'Desteklenen kaynaklarda onarılacak fark yok.'}
            folder = self.backups / plan['id']
            folder.mkdir(parents=True, exist_ok=False)
            receipt = {'id': plan['id'], 'build': plan['build'], 'state': 'backed_up', 'files': []}
            for index, item in enumerate(plan['changes']):
                data = originals[item['name']]
                if data is not None:
                    saved = folder / str(index)
                    saved.write_bytes(data)
                    if self.digest(saved) != item['before']:
                        raise OSError('Yedek hash doğrulaması başarısız')
                receipt['files'].append({k: item[k] for k in ('name', 'before', 'after')})
            atomic_write_json(folder / 'receipt.json', receipt)
            written = []
            try:
                for item in plan['changes']:
                    target = safe_member(self.base, item['name'])
                    if self.digest(target) != item['before']:
                        raise OSError('Onarım sırasında eşzamanlı değişiklik')
                    self._replace(target, item['data'])
                    written.append(item)
                    if self.digest(target) != item['after']:
                        raise OSError('Onarım sonrası hash eşleşmedi')
                receipt['state'] = 'verified'
                atomic_write_json(folder / 'receipt.json', receipt)
            except Exception:
                restored = True
                for item in reversed(written):
                    try:
                        target = safe_member(self.base, item['name'])
                        if self.digest(target) != item['after']:
                            restored = False  # Never overwrite another writer's work.
                            continue
                        data = originals[item['name']]
                        if data is None:
                            target.unlink()
                        else:
                            self._replace(target, data)
                        restored &= self.digest(target) == item['before']
                    except Exception:
                        restored = False
                receipt['state'] = 'rolled_back' if restored else 'recovery_required'
                atomic_write_json(folder / 'receipt.json', receipt)
                return {'state': receipt['state'], 'message': 'Onarım tamamlanamadı. ' + (
                    'Yapılan değişiklikler geri alındı.' if restored else 'Yedek korundu; elle kurtarma gerekiyor.')}
            return {'state': 'verified', 'message': 'Kaynaklar yedeklendi, geri yüklendi ve SHA-256 ile doğrulandı. '
                    'Görsel sonuç bir sonraki açılışta ayrıca kontrol edilmeli.'}
