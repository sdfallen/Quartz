"""Real owned root/child Stop via runtime cancel/watcher. No provider or GUI calls."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import psutil
from core.codex_runtime import CodexRuntime
from core.antigravity_runtime import AntigravityRuntime


def run_case(cls, denied):
    child_code = 'import time; time.sleep(30)'
    parent_code = ('import subprocess,sys,time; '
        f'child=subprocess.Popen([sys.executable,"-I","-c",{child_code!r}]); '
        'print(child.pid,flush=True); time.sleep(30)')
    process = subprocess.Popen([sys.executable, '-I', '-c', parent_code],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    child = None;watcher = None;drains = []
    result = {'provider':cls.__name__, 'fault_injected':denied, 'root_pid':process.pid,
              'scope':'runtime cancel/watcher with controlled Python processes, not real CLI/model or GUI acceptance'}
    try:
        result['root_created_at'] = psutil.Process(process.pid).create_time()
        child_pid = int(process.stdout.readline().strip())
        child = psutil.Process(child_pid)
        if child.ppid() != process.pid:raise RuntimeError('Fixture child ownership mismatch')
        result.update(child_pid=child.pid, child_created_at=child.create_time())
        for pipe in (process.stdout, process.stderr):
            def drain(stream=pipe):
                try:
                    while stream.read(8192):pass
                finally:stream.close()
            thread = threading.Thread(target=drain, daemon=True);thread.start();drains.append(thread)
        runtime = cls.__new__(cls);runtime._lock = threading.RLock()
        runtime._runs = {'fixture':{'status':'running', 'cancel_requested':False,
            'timeout_seconds':None, 'errors':[], 'events':[], 'result':'',
            'remote_status':'running', 'denied_actions':[]}}
        runtime._processes = {'fixture':process};runtime._writers = {'fixture-project':'fixture'}
        watcher = threading.Thread(target=runtime._wait,
            args=('fixture',process,'fixture-project',*drains), daemon=True)
        watcher.start();started = time.monotonic()
        if denied:
            with patch('psutil.Process', side_effect=psutil.AccessDenied(process.pid)):
                runtime.cancel('fixture', timeout=1)
        else:
            runtime.cancel('fixture', timeout=1)
        watcher.join(10)
        state = runtime.get('fixture')
        result.update(elapsed_seconds=round(time.monotonic()-started,3),
            run=state, root_exited=process.poll() is not None,
            child_running_before_fixture_cleanup=child.is_running(),
            process_owner_retained='fixture' in runtime._processes,
            writer_retained='fixture-project' in runtime._writers,
            watcher_exited=not watcher.is_alive())
        if denied:
            passed=(result['root_exited'] and result['watcher_exited']
                and state.get('cleanup_error')=='tree_discovery_incomplete'
                and state.get('process_exit_confirmed') is False
                and result['process_owner_retained'] and result['writer_retained'])
        else:
            passed=(result['root_exited'] and result['watcher_exited']
                and not child.is_running() and state.get('status')=='cancelled'
                and state.get('process_exit_confirmed') is True
                and not result['process_owner_retained'] and not result['writer_retained'])
        result['status'] = 'VERIFIED' if passed else 'FAILED'
    except Exception as exc:
        result.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
    finally:
        # These are fixture-owned handles/creation-bound objects, never user PIDs.
        if child is not None and child.is_running():
            child.terminate()
            try:child.wait(timeout=3)
            except psutil.TimeoutExpired:child.kill();child.wait(timeout=3)
        if process.poll() is None:process.terminate()
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        if watcher is not None:watcher.join(3)
        for thread in drains:thread.join(3)
        result['fixture_cleanup']={'root_exited':process.poll() is not None,
            'child_exited':child is None or not child.is_running(),
            'watcher_exited':watcher is None or not watcher.is_alive(),
            'drains_exited':all(not t.is_alive() for t in drains)}
        if not all(result['fixture_cleanup'].values()):result['status']='FAILED'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output.absolute();output.mkdir(parents=True,exist_ok=False)
    cases=[run_case(cls,denied) for cls in (CodexRuntime,AntigravityRuntime) for denied in (False,True)]
    paths=('core/process_tree.py','core/codex_runtime.py','core/antigravity_runtime.py',
           'core/tool_workbench/execution.py')
    report={'status':'VERIFIED' if all(c['status']=='VERIFIED' for c in cases) else 'FAILED',
        'level':'REAL OWNED PROCESS RUNTIME CANCELLATION; DISCOVERY DENIAL IS FAULT-INJECTED',
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
        'pid':os.getpid(), 'cases':cases, 'no_real_provider_calls':True,'gui_acceptance':False}
    (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status']=='VERIFIED' else 1

if __name__=='__main__':raise SystemExit(main())
