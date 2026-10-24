"""Bounded passive checks. Never import/execute changed project code or tests."""
import ast
import hashlib
from pathlib import Path


def verify_changed_python(workspace, changed, *, warning='', max_bytes=1024 * 1024):
    root = Path(workspace).resolve()
    records = []
    consumed = 0
    for item in changed[:200]:
        path = Path(item)
        if not path.is_absolute(): path = root / path
        if path.suffix.lower() != '.py':
            continue
        record = {'path':str(path), 'status':'NOT TESTED'}
        records.append(record)
        try:
            if path.is_symlink() or root not in path.resolve().parents:
                raise ValueError('Path escaped approved project scope')
            if not path.exists():
                record.update(reason='file removed; syntax not applicable')
                continue
            if path.stat().st_size > max_bytes:
                raise ValueError('Passive source check size limit exceeded')
            if consumed + path.stat().st_size > 5 * max_bytes:
                raise ValueError('Total passive source check size limit exceeded')
            with path.open('rb') as source:
                content = source.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ValueError('File grew beyond passive check limit')
            consumed += len(content)
            # ast.parse accepts Python encoding cookies and does not execute.
            ast.parse(content, filename=path.name)
            record.update(status='VERIFIED', sha256=hashlib.sha256(content).hexdigest())
        except SyntaxError as exc:
            record.update(status='FAILED', reason='Python syntax error', line=exc.lineno, column=exc.offset)
        except (OSError, ValueError) as exc:
            record.update(reason=str(exc))
    all_checked = bool(records) and all(r['status'] == 'VERIFIED' for r in records) and not warning
    status = 'FAILED' if any(r['status'] == 'FAILED' for r in records) else 'VERIFIED' if all_checked else 'NOT TESTED'
    return {'level':'SOURCE/STATIC', 'check':'Python syntax only', 'status':status,
            'files':records, 'warning':warning, 'tests_executed':False,
            'goal_accepted':False, 'scope':'Only listed changed Python files; not build, runtime or whole-project correctness'}
