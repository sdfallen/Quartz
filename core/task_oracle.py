"""Host-declared postconditions, not a model verdict or a second task engine.

The host registers an immutable plan before execution. No MCP/CLI endpoint can
register checks. A receipt alone cannot authorize input or accept a user goal.
Only bounded files in the explicit fixture/project root are supported here;
semantic/UI goals stay NOT VERIFIED until a reviewed adapter exists.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import threading

_SEAL = object()


@dataclass(frozen=True)
class GoalEvaluation:
    task_id: str
    run_id: str
    verdict: str
    checks: tuple
    _seal: object = None

    def summary(self):
        return {'task_id': self.task_id, 'run_id': self.run_id,
                'verdict': self.verdict, 'checks': list(self.checks),
                'level': 'HOST POSTCONDITION', 'user_accepted': False}


def trusted_evaluation(value):
    return isinstance(value, GoalEvaluation) and value._seal is _SEAL


def _safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts:
        raise ValueError('Root-relative oracle path required')
    path = root / relative
    if not path.resolve().is_relative_to(root): raise ValueError('Oracle scope escape')
    # Reject Windows junctions as well as symbolic links; never use a linked
    # outside file to satisfy a scoped postcondition, even if it points inside.
    for part in (path, *path.parents):
        if part == root: break
        try: st = part.lstat()
        except FileNotFoundError: continue
        if part.is_symlink() or getattr(st, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Oracle path contains a reparse point')
    return path


class TaskOracle:
    def __init__(self):
        self._plans = {}
        self._lock = threading.RLock()

    def register(self, task_id, run_id, root, checks):
        root = Path(root).resolve(strict=True)
        if not root.is_dir(): raise ValueError('Oracle root must be a directory')
        if not task_id or not run_id or not isinstance(checks, (list, tuple)) or not 0 < len(checks) <= 64:
            raise ValueError('Bound task/run and nonempty checks required')
        frozen = []
        for check in checks:
            if set(check) != {'path', 'sha256'} and set(check) != {'path', 'text'} and set(check) != {'path', 'absent'}:
                raise ValueError('Only exact file text/hash/absence postconditions are reviewed')
            _safe_path(root, check['path'])
            mode = next(key for key in ('sha256', 'text', 'absent') if key in check)
            value = check[mode]
            if mode == 'sha256' and not re.fullmatch('[a-f0-9]{64}', str(value)):
                raise ValueError('Exact SHA256 required')
            if mode == 'text' and (not isinstance(value, str) or len(value.encode('utf-8')) > 4*1024*1024):
                raise ValueError('Bounded exact text required')
            if mode == 'absent' and value is not True: raise ValueError('absent must be true')
            frozen.append((str(check['path']), mode, value))
        with self._lock:
            if run_id in self._plans: raise ValueError('Oracle plan is immutable for this run')
            self._plans[run_id] = (str(task_id), root, tuple(frozen))

    def evaluate(self, task_id, run_id):
        with self._lock: plan = self._plans.get(run_id)
        if not plan: return None
        if plan[0] != task_id: raise PermissionError('Oracle belongs to another task')
        _, root, checks = plan
        observed = []
        for relative, mode, expected in checks:
            result = {'path': relative, 'kind': mode, 'passed': False}
            try:
                path = _safe_path(root, relative)
                if mode == 'absent':
                    result['passed'] = not path.exists()
                elif path.is_file() and path.stat().st_size <= 4*1024*1024:
                    # Recheck identity/mtime after reading; a concurrently edited
                    # file is not a stable result. This is evidence, not a sandbox.
                    before = path.stat()
                    with path.open('rb') as stream: data = stream.read(4*1024*1024+1)
                    after = path.stat()
                    stable = (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
                    _safe_path(root, relative)
                    digest = hashlib.sha256(data).hexdigest()
                    result['sha256'] = digest
                    result['passed'] = stable and len(data) <= 4*1024*1024 and (
                        digest == expected if mode == 'sha256' else data == expected.encode('utf-8'))
            except (OSError, ValueError):
                result['error'] = 'Postcondition unavailable or outside scope'
            observed.append(result)
        verdict = 'VERIFIED' if all(c['passed'] for c in observed) else 'FAILED'
        return GoalEvaluation(str(task_id), str(run_id), verdict, tuple(observed), _SEAL)
