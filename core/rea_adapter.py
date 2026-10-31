"""Optional REA 6.8 static artifact adapter. No setup/config writes or target execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time

from core.cli_installer import managed_root
from core.process_tree import stop_process_tree


class ReaAdapter:
    MAX_OUTPUT = 2 * 1024 * 1024
    SUPPORTED_VERSION = '6.8.0'
    _CACHE_LOCK = threading.RLock()
    _SCRIPT_HASH_CACHE: dict[str, tuple[tuple[int, int, int, int], str]] = {}
    _VERIFIED_RUNTIME_CACHE: set[tuple[tuple[str, ...], tuple[int, int, int, int], tuple[int, int, int, int]]] = set()

    def __init__(self, command=None):
        self.command = command  # Internal test harness injection; never accepted via IPC.

    @staticmethod
    def _file_fingerprint(path: Path) -> tuple[int, int, int, int] | None:
        try:
            if path.is_symlink() or not path.is_file():
                return None
            st = path.stat()
            return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
        except OSError:
            return None

    @classmethod
    def _cached_script_sha256(cls, candidate: Path) -> str:
        fp = cls._file_fingerprint(candidate)
        key = str(candidate)
        if fp is not None:
            with cls._CACHE_LOCK:
                cached = cls._SCRIPT_HASH_CACHE.get(key)
                if cached and cached[0] == fp:
                    return cached[1]
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if fp is not None:
            with cls._CACHE_LOCK:
                cls._SCRIPT_HASH_CACHE[key] = (fp, digest)
        return digest

    @classmethod
    def _runtime_cache_key(cls, command: list[str]):
        if len(command) < 2:
            return None
        node_fp = cls._file_fingerprint(Path(command[0]))
        script_fp = cls._file_fingerprint(Path(command[1]))
        if node_fp is None or script_fp is None:
            return None
        return (tuple(command), node_fp, script_fp)

    @classmethod
    def clear_runtime_cache(cls):
        with cls._CACHE_LOCK:
            cls._SCRIPT_HASH_CACHE.clear()
            cls._VERIFIED_RUNTIME_CACHE.clear()

    @staticmethod
    def discover():
        local = (Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Quartz/tools/rea').resolve()
        script = os.environ.get('QUARTZ_REA_SCRIPT')
        recorded_node = None
        receipt = local / 'tool.json'
        if not script and receipt.exists():
            if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size >= 32 * 1024:
                raise ValueError('REA araç tanımı geçersiz')
            tool = json.loads(receipt.read_text(encoding='utf-8-sig'))
            candidate = Path(tool.get('script',''))
            expected = local/'node_modules/rea-agents/scripts/rea.mjs'
            # Windows Store Python can expose the same file through a virtualized
            # AppData path. Require file identity, not a relaxed string prefix.
            if (candidate.is_file() and expected.is_file() and candidate.samefile(expected)
                    and not candidate.is_symlink()
                    and tool.get('version') == ReaAdapter.SUPPORTED_VERSION
                    and ReaAdapter._cached_script_sha256(candidate) == tool.get('script_sha256')):
                script, recorded_node = str(candidate), tool.get('node')
            else:
                raise ValueError('REA giriş dosyası kayıtlı hash ile eşleşmiyor')
        if not script:
            prefixes = [local]
            wrapper = shutil.which('rea.cmd')
            if wrapper:
                prefixes.append(Path(wrapper).parent)
            for prefix in prefixes:
                candidate = prefix / 'node_modules/rea-agents/scripts/rea.mjs'
                if candidate.is_file(): script = str(candidate); break
        if not script or not Path(script).is_file():
            raise FileNotFoundError('REA kurulu değil')
        entry = Path(script).resolve()
        if entry.name != 'rea.mjs' or entry.parent.name != 'scripts':
            raise ValueError('REA giriş yolu doğrulanamadı')
        meta = json.loads((entry.parent.parent / 'package.json').read_text(encoding='utf-8'))
        if meta.get('name') != 'rea-agents' or meta.get('version') != ReaAdapter.SUPPORTED_VERSION:
            raise ValueError('REA sürümü bu adaptörde doğrulanmadı')
        candidates = [os.environ.get('QUARTZ_REA_NODE'), recorded_node, managed_root() / 'node/node.exe', shutil.which('node.exe'), shutil.which('node')]
        node = next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()), None)
        if not node: raise FileNotFoundError('REA için Node bulunamadı')
        return [node, str(entry)]

    def _run(self, command, event, deadline, cwd):
        """Bound both pipes, wait in worker, stop only the owned process tree."""
        env = {k: v for k, v in os.environ.items() if not any(
            part in k.upper() for part in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD'))
            and not k.upper().startswith(('REA_', 'CODEX_', 'NPM_CONFIG_'))
            and k.upper() not in {'NODE_OPTIONS', 'NODE_PATH'}}
        env.update(TEMP=str(cwd), TMP=str(cwd), XDG_CACHE_HOME=str(cwd / 'cache'))
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        chunks = {'stdout': bytearray(), 'stderr': bytearray()}
        lock, overflow = threading.Lock(), threading.Event()
        def drain(name, stream):
            try:
                while block := stream.read(8192):
                    with lock:
                        if sum(map(len, chunks.values())) + len(block) > self.MAX_OUTPUT:
                            overflow.set()
                        else: chunks[name].extend(block)
            finally:
                stream.close()
        threads = [threading.Thread(target=drain, args=(name, getattr(process, name)), daemon=True)
                   for name in chunks]
        for thread in threads: thread.start()
        reason = None
        try:
            while process.poll() is None:
                if event.is_set(): reason = 'cancelled'; break
                if overflow.is_set(): reason = 'output-limit'; break
                if time.monotonic() > deadline: reason = 'deadline'; break
                event.wait(.05)
            if reason: stop_process_tree(process)
            process.wait(timeout=6)
        finally:
            if process.poll() is None: stop_process_tree(process)
            for thread in threads: thread.join(timeout=2)
        if overflow.is_set(): reason = 'output-limit'
        return {'exit': process.returncode, 'stdout': bytes(chunks['stdout']),
                'stderr': bytes(chunks['stderr']), 'reason': reason}

    @staticmethod
    def node_supported(text):
        match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)\s*', text)
        if not match: return False
        version = tuple(map(int, match.groups()))
        return ((version[0] == 22 and version >= (22, 23, 4))
                or (version[0] == 24 and version >= (24, 22, 1))
                or version >= (26, 12, 1))

    def inspect(self, target, *, event, deadline):
        try:
            command = list(self.command or self.discover())
        except (OSError, ValueError, KeyError, TypeError):
            return {'status': 'NOT_TESTED', 'message': 'Doğrulanmış REA 6.8.0 ve uyumlu Node bulunamadı; yerel paket kontrolleri korunuyor.', 'used': False}
        # No shell, package runner, downloads, provider engine or arbitrary commands.
        if target.is_symlink() or target.stat().st_size > 512 * 1024 * 1024:
            return {'status': 'NOT_TESTED', 'message': 'REA hedefi salt okunur inceleme sınırını aşıyor.', 'used': False}
        with target.open('rb') as stream:
            target_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        with tempfile.TemporaryDirectory(prefix='quartz-rea-readonly-') as directory:
            working = Path(directory)
            runtime_key = self._runtime_cache_key(command)
            with self._CACHE_LOCK:
                cached_runtime = bool(runtime_key and runtime_key in self._VERIFIED_RUNTIME_CACHE)
            if not cached_runtime:
                node = self._run([command[0], '--version'], event, min(deadline, time.monotonic()+15), working)
                if node['reason'] or node['exit'] or not self.node_supported(node['stdout'].decode('utf-8', 'replace')):
                    return {'status': 'NOT_TESTED', 'message': 'Node sürümü veya hazırlık kontrolü REA koşullarını karşılamadı.', 'used': False}
                version = self._run([*command, '--version'], event, min(deadline, time.monotonic()+30), working)
                if version['reason'] or version['exit'] or self.SUPPORTED_VERSION not in version['stdout'].decode('utf-8', 'replace'):
                    return {'status': 'UNKNOWN', 'message': 'REA başlangıç/sürüm kontrolü tamamlanamadı.', 'used': False}
                if runtime_key is not None:
                    with self._CACHE_LOCK:
                        self._VERIFIED_RUNTIME_CACHE.add(runtime_key)
            started_at = time.monotonic()
            source_evidence = working / 'artifact-evidence.json'
            result = self._run([*command, 'inspect-artifact', str(target), '--detail', 'summary',
                                '--evidence_output', str(source_evidence), '--json'],
                               event, deadline, working)
            elapsed_ms = max(0, int((time.monotonic() - started_at) * 1000))
            evidence = {'rea_version': self.SUPPORTED_VERSION, 'exit_code': result['exit'],
                        'output_sha256': hashlib.sha256(result['stdout']).hexdigest(), 'artifact_sha256': target_hash,
                        'cached_runtime': cached_runtime, 'elapsed_ms': elapsed_ms}
            if result['reason'] or result['exit']:
                evidence['reason'] = result['reason'] or 'tool-error'
                return {'status': 'UNKNOWN', 'message': 'REA incelemesi tamamlanamadı; bu durum hedef uygulamanın hatalı olduğunu kanıtlamaz.', 'used': True, 'evidence': evidence}
            try:
                payload = json.loads(result['stdout'])
            except (ValueError, UnicodeError):
                return {'status': 'UNKNOWN', 'message': 'REA yanıt biçimi doğrulanamadı.', 'used': True, 'evidence': evidence}
            if source_evidence.is_symlink() or not source_evidence.is_file() or source_evidence.stat().st_size > 64 * 1024 * 1024:
                return {'status': 'UNKNOWN', 'message': 'REA tam kanıt dosyası doğrulanamadı.', 'used': True, 'evidence': evidence}
            with source_evidence.open('rb') as stream:
                evidence['source_evidence_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
            with target.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != target_hash:
                    return {'status': 'UNKNOWN', 'message': 'Hedef inceleme sırasında değişti; sonuç kabul edilmedi.', 'used': True, 'evidence': evidence}
            return self.summarize(payload, evidence)

    @staticmethod
    def summarize(payload, evidence):
        """Validate real 6.8.0 summary envelope; copy only typed, bounded facts."""
        unknown = {'status': 'UNKNOWN', 'message': 'REA yanıtı veya kapsamı doğrulanamadı; statik inceleme kabul edilmedi.', 'used': True, 'evidence': evidence}
        try:
            view = payload['summary']
            normalized = view['normalized_result']
            summary = normalized['summary']
            manifest = summary['manifest']
            expected = evidence.get('artifact_sha256')
            if view['subject']['format'] == 'pe':
                if (not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected)
                        or view['subject']['digest']['sha256'] != expected
                        or normalized['artifact']['sha256'] != expected
                        or manifest['root_sha256'] != expected or manifest['root_format'] != 'pe'
                        or normalized['kind'] != 'summary' or normalized['parent_operation'] != 'inspect_artifact'):
                    return unknown
                counts = summary['available_counts']
                numbers = [manifest['node_count'], counts['integrity_contradictions']]
                if any(type(n) is not int or not 0 <= n <= 1_000_000 for n in numbers):
                    return unknown
                pe_hashes = summary.get('available_hash_status_counts')
                verified_hashes = pe_hashes.get('verified') if isinstance(pe_hashes, dict) else None
                if type(verified_hashes) is int and 0 <= verified_hashes <= 1_000_000:
                    evidence['verified_member_hashes'] = verified_hashes
                pe_meta = summary.get('root_format_metadata')
                entry_count = pe_meta.get('entry_count') if isinstance(pe_meta, dict) else None
                if type(entry_count) is int and 0 <= entry_count <= 1_000_000:
                    evidence['archive_entries'] = entry_count
                evidence.update(format='pe', nodes=manifest['node_count'],
                                integrity_contradictions=counts['integrity_contradictions'],
                                source_complete=summary.get('source_complete') is True,
                                analysis_scope='root-inventory', runtime_tested=False)
                if counts['integrity_contradictions']:
                    return {'status':'FAIL','message':'REA dosya envanterinde çelişki buldu.','used':True,'evidence':evidence}
                if summary.get('source_complete') is not True or summary['source_coverage']['status'] != 'complete':
                    return unknown
                return {'status':'PASS','message':'REA Windows PE dosyasının sınırlı statik envanterini doğruladı; iç kod, arayüz ve çalışma davranışı test edilmedi.', 'used':True,'evidence':evidence}
            metadata = summary['root_format_metadata']
            if (not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected)
                    or view['subject']['format'] != 'pyinstaller'
                    or view['subject']['digest']['sha256'] != expected
                    or normalized['artifact']['sha256'] != expected
                    or manifest['root_sha256'] != expected or manifest['root_format'] != 'pyinstaller'
                    or normalized['kind'] != 'summary' or normalized['parent_operation'] != 'inspect_artifact'
                    or metadata['kind'] != 'pyinstaller'):
                return unknown
            counts = summary['available_counts']
            hashes = summary['available_hash_status_counts']
            numbers = [metadata['entry_count'], manifest['node_count'], counts['integrity_contradictions'],
                       hashes['verified'], hashes['mismatched'], hashes['unavailable'], hashes['not-hashed']]
            if any(type(n) is not int or not 0 <= n <= 1_000_000 for n in numbers):
                return unknown
            evidence.update(format='pyinstaller', archive_entries=metadata['entry_count'],
                            nodes=manifest['node_count'], verified_member_hashes=hashes['verified'],
                            integrity_contradictions=counts['integrity_contradictions'],
                            source_complete=summary.get('source_complete') is True)
            if counts['integrity_contradictions'] or hashes['mismatched']:
                return {'status': 'FAIL', 'message': 'REA statik paket bütünlüğünde çelişki bildirdi; çalışma zamanı nedeni ayrıca araştırılmalı.', 'used': True, 'evidence': evidence}
            if (summary.get('source_complete') is not True
                    or summary['source_coverage']['status'] != 'complete'
                    or hashes['unavailable'] or hashes['not-hashed']):
                return unknown
            return {'status': 'PASS', 'message': 'REA bu PyInstaller paketinin sınırlı statik envanterini doğruladı; uygulama davranışı test edilmedi.', 'used': True, 'evidence': evidence}
        except (KeyError, TypeError, ValueError):
            return unknown
