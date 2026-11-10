"""Windows host-owned unittest adapter. Approved project code is not sandboxed.

Capture is passive and must occur before the first writer dispatch. No arbitrary
shell command or agent-provided test count is accepted by this adapter.
"""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import tempfile
import threading
import time

from core.process_tree import CREATE_SUSPENDED, bind_kill_on_close_job, close_process_job, stop_process_tree
from core.repair_cycle import TestObservation

_WORKER = r'''
import json, sys, unittest
from pathlib import Path
root, modules, receipt = sys.argv[1:]
sys.path.insert(0, root)
suite = unittest.defaultTestLoader.loadTestsFromNames(json.loads(modules))
result = unittest.TextTestRunner(verbosity=2).run(suite)
code = 0 if result.wasSuccessful() else 1
Path(receipt).write_text(json.dumps({'tests_run': result.testsRun,
    'skipped': len(result.skipped), 'exit_code': code}), encoding='utf-8')
sys.exit(code)
'''


def _active_job_count(handle):
    import ctypes
    from ctypes import wintypes
    class Accounting(ctypes.Structure):
        _fields_ = [('user', ctypes.c_longlong), ('kernel', ctypes.c_longlong),
                    ('period_user', ctypes.c_longlong), ('period_kernel', ctypes.c_longlong),
                    ('faults', wintypes.DWORD), ('total', wintypes.DWORD),
                    ('active', wintypes.DWORD), ('terminated', wintypes.DWORD)]
    query = ctypes.windll.kernel32.QueryInformationJobObject
    query.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID]
    query.restype = wintypes.BOOL
    info = Accounting()
    if not query(wintypes.HANDLE(handle), 1, ctypes.byref(info), ctypes.sizeof(info), None):
        raise OSError('Owned job accounting unavailable')
    return info.active


class HostUnittestAdapter:
    def __init__(self, project_root, test_files, *, expected_tests, python_executable=None,
                 timeout=30, max_output_bytes=256 * 1024):
        if type(expected_tests) is not int or expected_tests <= 0:
            raise ValueError('Positive host test count required')
        if not 0 < timeout <= 600 or not 1024 <= max_output_bytes <= 1024 * 1024:
            raise ValueError('Invalid test resource budget')
        self.root = Path(project_root).resolve(strict=True)
        if not self.root.is_dir() or not isinstance(test_files, (tuple, list)) or not 1 <= len(test_files) <= 64:
            raise ValueError('Explicit bounded test file list required')
        files = []
        for name in test_files:
            path = Path(name)
            if path.is_absolute() or PureWindowsPath(name).drive or '..' in path.parts or ':' in str(name):
                raise ValueError('Root-relative test path required')
            if path.suffix != '.py' or any(not re.fullmatch(r'[A-Za-z_]\w*', p) for p in path.with_suffix('').parts):
                raise ValueError('Importable Python test module required')
            files.append(path.as_posix())
        if len(set(files)) != len(files):
            raise ValueError('Duplicate host test file')
        self.files = tuple(sorted(files))
        self.expected_tests = expected_tests
        self.timeout, self.max_output_bytes = timeout, max_output_bytes
        executable = python_executable or (None if getattr(sys, 'frozen', False) else sys.executable)
        if not executable or not Path(executable).is_absolute() or not Path(executable).is_file():
            raise ValueError('Host Python executable required')
        self.python = str(Path(executable).resolve())
        self._baseline = self._manifest()
        self._lock = threading.RLock()
        self._call_lock = threading.Lock()
        self._process = None
        self.cleanup_pending = False

    @property
    def baseline_manifest(self):
        return self._baseline

    def _manifest(self):
        result, total = [], 0
        for name in self.files:
            candidate = self.root / name
            for part in (candidate, *candidate.parents):
                if part == self.root: break
                stat = part.lstat()
                if part.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('Host test links/reparse points are forbidden')
            if not candidate.resolve(strict=True).is_relative_to(self.root):
                raise ValueError('Host test escapes project')
            size = candidate.stat().st_size
            total += size
            if size > 1024 * 1024 or total > 8 * 1024 * 1024:
                raise ValueError('Host test manifest size exceeded')
            data = candidate.read_bytes()
            if len(data) > 1024 * 1024: raise ValueError('Host test grew while reading')
            result.append((name, hashlib.sha256(data).hexdigest()))
        return tuple(result)

    def validate_baseline(self):
        if self._manifest() != self._baseline:
            raise RuntimeError('Host tests changed since pre-write capture')

    def cleanup(self):
        """Only the Popen and Job Object created by this adapter are actionable."""
        with self._lock:
            proc = self._process
            if proc is None: return not self.cleanup_pending
            job = getattr(proc, '_quartz_job_handle', None)
            try:
                if job:
                    import ctypes
                    from ctypes import wintypes
                    terminate = ctypes.windll.kernel32.TerminateJobObject
                    terminate.argtypes = [wintypes.HANDLE, wintypes.UINT]
                    terminate.restype = wintypes.BOOL
                    if not terminate(wintypes.HANDLE(job), 1):
                        raise OSError('Owned job termination failed')
                    proc.wait(timeout=3)
                    deadline = time.monotonic() + 3
                    while _active_job_count(job):
                        if time.monotonic() >= deadline: raise RuntimeError('Owned descendants still active')
                        time.sleep(.02)
                    close_process_job(proc)
                    clean = True
                else:
                    clean = stop_process_tree(proc, timeout=1)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                clean = False
            self.cleanup_pending = not clean
            if clean: self._process = None
            return clean

    def __call__(self, stop):
        if os.name != 'nt': raise RuntimeError('Owned Windows Job Object runner required')
        if not self._call_lock.acquire(blocking=False): raise RuntimeError('Host test already running')
        try:
            if self.cleanup_pending: raise RuntimeError('Previous host test cleanup unconfirmed')
            self.validate_baseline()
            if stop.is_set(): raise RuntimeError('Host test cancelled before start')
            with tempfile.TemporaryDirectory(prefix='quartz-host-unittest-') as directory:
                receipt = Path(directory) / 'result.json'
                with (Path(directory) / 'output.log').open('w+b') as output:
                    args = [self.python, '-I', '-B', '-u', '-X', 'utf8', '-c', _WORKER,
                            str(self.root), json.dumps([p[:-3].replace('/', '.') for p in self.files]), str(receipt)]
                    env = {k: v for k, v in os.environ.items() if k.upper() in {
                        'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
                    proc = subprocess.Popen(args, cwd=self.root, stdin=subprocess.DEVNULL, stdout=output,
                                            stderr=subprocess.STDOUT, env=env,
                                            creationflags=CREATE_SUSPENDED | getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    with self._lock:
                        self._process = proc
                        self.cleanup_pending = True
                    try:
                        if not bind_kill_on_close_job(proc, resume=True):
                            raise RuntimeError('Host test Job Object ownership unavailable')
                        deadline = time.monotonic() + self.timeout
                        while proc.poll() is None:
                            if stop.is_set(): raise RuntimeError('Host test cancelled')
                            if time.monotonic() >= deadline: raise RuntimeError('Host test timeout')
                            if os.fstat(output.fileno()).st_size > self.max_output_bytes:
                                raise RuntimeError('Host test output budget exceeded')
                            stop.wait(.03)
                        code = proc.returncode
                        if os.fstat(output.fileno()).st_size > self.max_output_bytes:
                            raise RuntimeError('Host test output budget exceeded')
                        if not receipt.is_file() or receipt.stat().st_size > 4096:
                            raise RuntimeError('Host unittest receipt unavailable')
                        observed = json.loads(receipt.read_text(encoding='utf-8'))
                        if (type(observed.get('tests_run')) is not int or observed['tests_run'] < self.expected_tests
                                or observed.get('skipped') != 0 or type(observed.get('exit_code')) is not int
                                or code != observed['exit_code'] or code not in (0, 1)):
                            raise RuntimeError('Host unittest receipt/count/exit inconsistent')
                        self.validate_baseline()
                        output.seek(0)
                        text = output.read(self.max_output_bytes).decode('utf-8', errors='replace')
                        observation = TestObservation(code, observed['tests_run'], text, self._baseline)
                    finally:
                        if not self.cleanup(): raise RuntimeError('Host test process cleanup unconfirmed')
                return observation
        finally:
            self._call_lock.release()
