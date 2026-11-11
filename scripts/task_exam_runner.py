"""Offline-first task exam. Execution success and verified task success are separate.

Only reviewed adapters run. Claude's task list is supplied as JSON, not commands.
Logs/metrics stay in a new private directory outside every Git checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exam_process import ExamProcess


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def private_output(path):
    path = Path(path).resolve()
    if any((p / '.git').exists() for p in (path, *path.parents)):
        raise ValueError('Evidence must be outside Git checkouts')
    if path.exists(): raise ValueError('Use a new evidence directory')
    return path


def package_summary(path):
    if path is None: return {'status': 'NOT SUPPLIED'}
    exe = Path(path).resolve() / 'Quartz.exe'
    return {'status': 'HASHED, NOT LAUNCHED', 'exe_sha256': digest(exe),
            'exe_bytes': exe.stat().st_size}


def command_for(task, catalog, permissions):
    if set(task) - {'id', 'kind', 'modules', 'script', 'timeout_seconds'}:
        raise ValueError('Unknown task fields; commands and environment are not accepted')
    if task.get('kind') == 'regression':
        modules = task.get('modules', [])
        if not isinstance(modules, list) or not modules: raise ValueError('Select test modules')
        for name in modules:
            if not isinstance(name, str) or not re.fullmatch(r'tests\.test_[a-z0-9_]+', name):
                raise ValueError('Only safe-suite test module names are accepted')
            if not (ROOT / (name.replace('.', '/') + '.py')).is_file():
                raise ValueError('Unknown test module')
        return [sys.executable, '-X', 'utf8', '-B', str(ROOT/'scripts/run_safe_tests.py'), *modules], 'unittest'
    if task.get('kind') != 'script': raise ValueError('Unknown task kind')
    entry = catalog.get(task.get('script'))
    if not entry: raise ValueError('Unreviewed script')
    missing = set(entry['requires']) - set(permissions)
    if missing: raise PermissionError('Explicit permission required: ' + ', '.join(sorted(missing)))
    if not entry.get('adapter'):
        raise PermissionError('No isolated reviewed execution adapter; classification only')
    source = ROOT / entry['path']
    if digest(source) != entry['sha256']: raise PermissionError('Script changed; review catalog again')
    # No manifest-supplied shell command, executable, arguments, environment or cwd.
    return [sys.executable, '-X', 'utf8', '-B', str(source), '--json'], entry['adapter']


def verdict(adapter, stdout, code, stderr=''):
    if code != 0: return 'FAILED', None
    if adapter == 'unittest':
        # unittest reports to stderr; execution completion is tested, not GUI acceptance.
        match = re.search(r'^Ran (\d+) tests? in [^\n]+\n\s*OK(?: \(skipped=(\d+)\))?\s*$', stderr, re.MULTILINE)
        if not match: return 'NOT VERIFIED', None
        if int(match[1]) <= int(match[2] or 0): return 'NOT VERIFIED', None
        return 'VERIFIED', {'tests': int(match[1]), 'skipped': int(match[2] or 0)}
    if adapter == 'process-benchmark':
        try:
            data = json.loads(stdout)
            ok = data['stop_cancellation']['stop_verified'] is True
            return ('VERIFIED' if ok else 'FAILED'), None
        except (ValueError, KeyError, TypeError): return 'NOT VERIFIED', None
    return 'NOT VERIFIED', None


def run_task(task, directory, catalog, permissions=(), execute=False):
    result = {'id': task['id'], 'status': 'NOT TESTED', 'level': 'SOURCE',
              'duration_seconds': 0, 'step_count': None,
              'step_source': 'agent steps not instrumented', 'runner_processes': 0}
    started = time.monotonic()
    try:
        command, adapter = command_for(task, catalog, permissions)
        if not execute: return result
        timeout = task.get('timeout_seconds', 120)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 7200:
            raise ValueError('Invalid test timeout (not a gameplay deadline)')
        directory.mkdir()
        env = os.environ.copy()
        env.pop('QUARTZ_LIVE_TOOL_TESTS', None)
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', QUARTZ_TASK_EXAM_DIR=str(directory))
        with (directory/'stdout.log').open('wb') as out, (directory/'stderr.log').open('wb') as err:
            owner = ExamProcess()
            try:
                process = owner.launch(command, cwd=ROOT, env=env, stdout=out, stderr=err,
                                       stdin=subprocess.DEVNULL)
                result['runner_processes'] = 1
                code = process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                clean = owner.cleanup(force=True)
                result.update(status='FAILED' if clean else 'BLOCKED',
                              reason='test interrupted or timed out', cleanup_confirmed=clean,
                              interrupted=isinstance(exc, KeyboardInterrupt))
                return result
            finally:
                if not result.get('interrupted') and 'cleanup_confirmed' not in result:
                    result['cleanup_confirmed'] = owner.cleanup()
            if owner.interrupted:
                result.update(interrupted=True, status='FAILED', reason='Interrupted during cleanup')
                return result
            if not result['cleanup_confirmed']:
                result.update(status='BLOCKED', reason='Descendants remained or tree cleanup was unconfirmed')
                return result
        result.update(exit_code=code, level='TESTED')
        # Private logs may contain sensitive data; never copy them to repository reports.
        logs = (directory/'stdout.log').read_text(encoding='utf-8', errors='replace')
        stderr = (directory/'stderr.log').read_text(encoding='utf-8', errors='replace')
        result['status'], counts = verdict(adapter, logs, code, stderr)
        if counts: result.update(counts)
        metrics = directory/'steps.json'
        if metrics.is_file():
            measured = json.loads(metrics.read_text(encoding='utf-8'))
            steps = measured.get('step_count')
            if isinstance(steps, int) and not isinstance(steps, bool) and steps >= 0:
                result.update(step_count=steps, step_source='adapter steps.json',
                              steps_sha256=digest(metrics))
        result['log_sha256'] = {n: digest(directory/n) for n in ('stdout.log','stderr.log')}
    except (PermissionError, ValueError) as exc:
        result.update(status='BLOCKED', reason=str(exc))
    except OSError as exc:
        result.update(status='FAILED', reason=type(exc).__name__)
    finally:
        result['duration_seconds'] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--allow-account', action='store_true', help='Only after explicit user authorization')
    parser.add_argument('--allow-desktop', action='store_true', help='Only during the assigned operator slot')
    parser.add_argument('--allow-network', action='store_true')
    args = parser.parse_args()
    output = private_output(args.output)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    tasks = manifest['tasks']
    if not isinstance(tasks, list): raise ValueError('tasks must be a list')
    ids = [t['id'] for t in tasks]
    if len(set(ids)) != len(ids) or any(not isinstance(i,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',i) for i in ids):
        raise ValueError('Unique safe task identifiers required')
    catalog = json.loads((ROOT/'scripts/task_exam_catalog.json').read_text(encoding='utf-8'))
    package = package_summary(args.package)
    sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty = bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT,text=True))
    permissions = [n for n in ('account','desktop','network') if getattr(args,'allow_'+n)]
    output.mkdir(parents=True)
    report = {'source_sha': sha, 'source_dirty': dirty, 'manifest_sha256': digest(args.manifest),
              'package': package, 'gui_acceptance': False, 'tasks': []}
    for task in tasks:
        row = run_task(task, output/task['id'],catalog,permissions,args.execute)
        row.update(source_sha=sha, package=package)
        report['tasks'].append(row)
        (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:row[k] for k in ('id','status','level','duration_seconds','step_count')},ensure_ascii=False))
        if row.get('interrupted'): break  # Never launch another task after Ctrl+C.
    if not tasks: (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if tasks and all(t['status']=='VERIFIED' for t in report['tasks']) else 2


if __name__=='__main__': raise SystemExit(main())
