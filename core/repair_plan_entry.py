"""GUI-only, passive repair preview and explicit one-use registration."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import shutil
import sys
import time

from core.host_test_runner import HostUnittestAdapter


def python_candidates():
    """Filesystem discovery only: never run an interpreter, launcher or probe."""
    paths = []
    if not getattr(sys, 'frozen', False): paths.append(sys.executable)
    paths += [shutil.which(name) for name in ('python', 'python3', 'python3.13', 'python3.12')]
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')
    for parent, pattern in ((local/'Programs/Python', 'Python*/python.exe'),
                            (local/'Microsoft/WindowsApps', 'PythonSoftwareFoundation.Python.*/python.exe'),
                            (local/'Microsoft/WindowsApps', 'python*.exe')):
        paths += [str(p) for p in list(parent.glob(pattern))[:32]]
    result, seen = [], set()
    for value in paths:
        if not value: continue
        path = Path(value)
        if path.is_absolute() and path.is_file() and str(path).casefold() not in seen:
            result.append(str(path)); seen.add(str(path).casefold())
    return sorted(result, key=lambda p: 'windowsapps' in p.casefold())[:32]


class RepairPlanEntry:
    TTL = 600

    def __init__(self, chat, clock=time.monotonic):
        self.chat, self.clock = chat, clock
        self.previews, self.plans = {}, {}

    def _idle(self):
        turn = self.chat._active_turn or {}
        if (self.chat._closed or turn.get('status') in {'running', 'cancelling'}
                or turn.get('worker_pending') or turn.get('stop_receipt', {}).get('status') in {'pending', 'failed'}):
            raise RuntimeError('Önce çalışan görevi ve süreçlerin kapanışını tamamlayın.')
        if any(a.cleanup_pending for a in self.chat._host_test_adapters.values()):
            raise RuntimeError('Önceki test sürecinin kapanışı henüz doğrulanmadı.')

    def _scope(self, cid, provider):
        if not isinstance(cid, str) or not cid or self.chat.store.get_active()['id'] != cid:
            raise ValueError('Plan yalnız etkin sohbet için hazırlanabilir; paneli yeniden açın.')
        conv = self.chat.store.get(cid)
        if provider not in {'codex', 'antigravity'} or conv.get('agent') != provider:
            raise ValueError('Önce sohbette aynı tek ajanı seçin: Codex veya Antigravity.')
        project = self.chat.agent_service.projects.get(conv.get('project_id'))
        if project.get('protected') or project.get('workflow') == 'warband':
            raise PermissionError('Korumalı proje bu onarım girişinde kullanılamaz.')
        root = str(Path(project['path']).resolve(strict=True))
        if not Path(root).is_dir(): raise ValueError('Proje klasörü bulunamadı.')
        return {'conversation_id': cid, 'project_id': conv.get('project_id'), 'project_path': root,
                'provider': provider, 'model': deepcopy(self.chat.store.get_agent_model(cid, provider))}

    def preview(self, *, conversation_id, provider, test_files, expected_tests,
                support_files=(), python_executable=None, max_repairs=2, python_site_packages=None):
        with self.chat._lock:
            self._idle()
            scope = self._scope(conversation_id, provider)
            if type(max_repairs) is not int or not 1 <= max_repairs <= 3:
                raise ValueError('En çok onarım sayısı 1–3 arasında tam sayı olmalı.')
            candidates = python_candidates()
            selected = python_executable or (candidates[0] if candidates else None)
            if selected is not None and not isinstance(selected, str): raise ValueError('Geçersiz Python yolu.')
            try:
                adapter = HostUnittestAdapter(scope['project_path'], test_files, expected_tests=expected_tests,
                                               support_files=support_files, python_executable=selected,
                                               python_site_packages=python_site_packages)
            except (ValueError, OSError, TypeError):
                raise ValueError('Test/destek yollarını, dosya sınırlarını, pozitif test sayısını, mutlak Python yolunu ve proje dışındaki site-packages yolunu kontrol edin.') from None
            now = self.clock()
            self.previews = {key: item for key, item in self.previews.items()
                             if item['expires'] > now and item['scope']['conversation_id'] != conversation_id}
            if len(self.previews) >= 32: self.previews.pop(next(iter(self.previews)))
            pid = secrets.token_urlsafe(24)
            self.previews[pid] = {'scope': scope, 'adapter': adapter, 'expires': now+self.TTL,
                                  'max_repairs': max_repairs,
                                  'python_stat': self._python_stat(adapter.python)}
            warnings = ['Önizleme kod çalıştırmaz. Python ve testler yalnız sonraki onaylı görevde çalıştırılır.',
                        'Destek dosyalarını eksiksiz seçin; test başarısı bağımsız kod incelemesinin yerine geçmez.']
            if adapter.python_site_packages:
                warnings.append('Bu klasördeki Python paketleri güvenilen bağımlılıklar olarak yüklenir. İçerikleri hash’lenmez.')
            if not python_executable: warnings.append('Python yolu önerildi; plan henüz kaydedilmedi.')
            if 'windowsapps' in adapter.python.casefold(): warnings.append('WindowsApps Python takma adı seçildi; kullanılabilirliği henüz çalıştırılarak doğrulanmadı.')
            return {**deepcopy(scope), 'preview_id': pid,
                    'files': [{'path': p, 'role': 'test' if p in adapter.files else 'support', 'sha256': h}
                              for p, h in adapter.baseline_manifest],
                    'expected_tests': expected_tests, 'python_executable': adapter.python,
                    'python_candidates': candidates, 'max_repairs': max_repairs, 'warnings': warnings,
                    'python_site_packages': adapter.python_site_packages}

    @staticmethod
    def _python_stat(value):
        stat = Path(value).stat()
        return stat.st_size, stat.st_mtime_ns

    def register(self, preview_id, *, confirm=False):
        with self.chat._lock:
            if confirm is not True: raise PermissionError('Planı kaydetmek için açık onay gerekli.')
            if not isinstance(preview_id, str): raise ValueError('Geçersiz önizleme kimliği.')
            item = self.previews.pop(preview_id, None)
            if item is None or item['expires'] <= self.clock():
                raise ValueError('Önizleme kullanılmış veya 10 dakikalık süresi dolmuş; yeniden önizleyin.')
            self._idle()
            scope = item['scope']
            if self._scope(scope['conversation_id'], scope['provider']) != scope:
                raise PermissionError('Sohbet, proje veya model değişti; yeniden önizleyin.')
            before = item['adapter']
            try:
                before.validate_baseline()
                if self._python_stat(before.python) != item['python_stat']: raise ValueError('Python changed')
            except (ValueError, RuntimeError, OSError):
                raise ValueError('Dosya veya Python değişti; yeniden önizleyin.') from None
            cid = scope['conversation_id']
            if cid in self.chat._repair_plans:
                raise RuntimeError('Önce mevcut onarım planını kaldırın.')
            adapter = self.chat.register_host_unittest_plan(cid, project_id=scope['project_id'], provider=scope['provider'],
                test_files=before.files, support_files=tuple(p for p in before.manifest_files if p not in before.files),
                expected_tests=before.expected_tests, python_executable=before.python, max_repairs=item['max_repairs'],
                python_site_packages=before.python_site_packages)
            # Close the second capture race: it must still be the approved bytes.
            if (adapter.baseline_manifest != before.baseline_manifest
                    or adapter.dependency_identity != before.dependency_identity):
                self.chat._repair_plans.pop(cid, None); self.chat._host_test_adapters.pop(cid, None)
                raise ValueError('Dosyalar kayıt sırasında değişti; yeniden önizleyin.')
            self.plans[cid] = {**scope, 'status': 'ready', 'files_count': len(adapter.manifest_files),
                'support_count': len(adapter.manifest_files)-len(adapter.files), 'expected_tests': before.expected_tests,
                'max_repairs': item['max_repairs'], 'registered_at': datetime.now(timezone.utc).isoformat(),
                'python_stat': item['python_stat'], 'python_executable': before.python}
            return self.summary(cid)

    def validate_ready(self, cid):
        item = self.plans.get(cid)
        if item and self._scope(cid, item['provider']) != {k:item[k] for k in ('conversation_id','project_id','project_path','provider','model')}:
            raise PermissionError('Onarım planının proje/model kapsamı değişti; planı kaldırıp yeniden hazırlayın.')
        if item and self._python_stat(item['python_executable']) != item['python_stat']:
            raise PermissionError('Onaylanan Python dosyası değişti; planı yeniden hazırlayın.')

    def summary(self, cid):
        with self.chat._lock:
            item = self.plans.get(cid)
            if not item: return None
            turn = self.chat._active_turn or {}
            running = turn.get('conversation_id') == cid and turn.get('status') in {'running', 'cancelling'}
            if cid not in self.chat._repair_plans and not running:
                self.plans.pop(cid, None)
                return None
            return {k: ('running' if running else 'ready') if k == 'status' else item[k]
                    for k in ('status','provider','files_count','support_count','expected_tests','max_repairs','registered_at')}

    def clear(self, cid):
        with self.chat._lock:
            self._idle()
            if not isinstance(cid, str) or cid != self.chat.store.get_active()['id']:
                raise ValueError('Yalnız etkin sohbetin planı kaldırılabilir.')
            self.chat._repair_plans.pop(cid, None)
            self.chat._host_test_adapters.pop(cid, None)
            self.plans.pop(cid, None)
            self.previews = {k:v for k,v in self.previews.items() if v['scope']['conversation_id'] != cid}
            return None
