"""Isolated same-worker registered search with the official cached ripgrep.

No GUI/provider calls, selected application execution, or network download. This
is AUTONOMOUS LIVE (host/process), not user acceptance or packaged UI acceptance.
The managed cache must already contain the currently pinned official package.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from core.artifact_diagnostics import ArtifactDiagnosticsService
from core.tool_workbench import ToolWorkbench
from core.tool_workbench.acquisition import manifest_fingerprint
from core.tool_workbench.catalog import BUILTIN_MANIFESTS
from core.tool_workbench.contracts import AcquisitionPolicy

MARKER='QUARTZ_REGISTERED_SEARCH_LIVE_20261103'
EXPECTED_SOURCE='https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-pc-windows-msvc.zip'
EXPECTED_DIGEST='d0f534024c42afd6cb4d38907c25cd2b249b79bbe6cc1dbee8e3e37c2b6e25a1'


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')


class OfflineRecordedWorkbench(ToolWorkbench):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.acquisitions=[]
        self.requests=[]
        self.receipts=[]
    def acquire(self, selection, policy=None, cancel_event=None, *, deadline_monotonic=None):
        if policy is not None:raise ValueError('Harness does not allow policy replacement')
        result=super().acquire(selection,AcquisitionPolicy(allow_network=False,
            managed_dir=str(self.managed_dir)),cancel_event,deadline_monotonic=deadline_monotonic)
        self.acquisitions.append({'selection':selection,'deadline_monotonic':deadline_monotonic,
            'result':deepcopy(result),'allow_network':False})
        return result
    def execute(self,request,cancel_event=None):
        self.requests.append(deepcopy(request))
        result=super().execute(request,cancel_event)
        self.receipts.append(deepcopy(result))
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--managed',type=Path,required=True,help='Existing validated official tool cache (read-only contents)')
    parser.add_argument('--output',type=Path,required=True,help='New private evidence directory; must not exist')
    args=parser.parse_args()
    manifest=BUILTIN_MANIFESTS['ripgrep']
    if (manifest.source_url!=EXPECTED_SOURCE or manifest.pinned_revision!='14.1.1'
            or manifest.package_digest!=EXPECTED_DIGEST or manifest.executable_subpath!='ripgrep-14.1.1-x86_64-pc-windows-msvc/rg.exe'):
        raise ValueError('Current official ripgrep pin differs; review harness before running')
    managed=args.managed.resolve(strict=True)
    output=args.output.absolute()
    output.mkdir(parents=True,exist_ok=False)
    target=output/'selected-fixture.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('package.json',json.dumps({'name':'registered-search-live-fixture'}))
        archive.writestr('asset.txt',MARKER)
    before=digest(target)
    try:
        build=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    except (OSError,subprocess.SubprocessError):build='UNKNOWN'
    paths=['core/artifact_diagnostics.py','core/self_diagnostics.py','core/investigation/gateway.py',
        'core/investigation/session.py','core/investigation/evidence.py','core/investigation/memory.py',
        'core/tool_workbench/workbench.py','core/tool_workbench/execution.py','core/tool_workbench/acquisition.py',
        'core/tool_workbench/catalog.py','scripts/rea_validation/registered_search_live.py']
    result={'schema_version':1,'time_utc':datetime.now(timezone.utc).isoformat(),'build':build,
        'source_hashes':{name:digest(ROOT/name) for name in paths},'level':'AUTONOMOUS LIVE HOST/PROCESS',
        'not_verified':['packaged GUI','human acceptance','application repair','engine semantic analysis'],
        'registered_manifest':manifest.to_dict(),'manifest_fingerprint':manifest_fingerprint(manifest),
        'target':str(target),'target_sha256_before':before,'network_allowed':False,'events':[]}
    created=[]
    def create(*,workspace_dir):
        bench=OfflineRecordedWorkbench(managed_dir=managed,workspace_dir=workspace_dir)
        created.append(bench)
        result['events'].append({'event':'workbench_created','time_monotonic':time.monotonic()})
        return bench
    service=ArtifactDiagnosticsService(target,reports=output/'reports',investigation_root=output/'investigations',
        knowledge=False,registered_search={'pattern':MARKER},workbench_factory=create)
    job=None
    error=None
    try:
        job=service.start(include_rea=False)
        result['job_id']=job['id']
        result['events'].append({'event':'worker_started','job_id':job['id'],'time_monotonic':time.monotonic()})
        end=time.monotonic()+20
        while time.monotonic()<end:
            state=service.status(job['id'])
            if state['phase']=='tool_permission':break
            if state['state']!='running':raise RuntimeError('Worker terminated before permission')
            time.sleep(.02)
        else:raise TimeoutError('Permission state not reached')
        if created:raise RuntimeError('Workbench constructed before grant')
        result['preapproval_state']=state
        result['preapproval_workbench_count']=len(created)
        result['events'].append({'event':'technical_test_grant','job_id':job['id'],
            'scope':['read selected fixture','execute pinned registered tool','write owned evidence'],
            'authorization_source':'isolated technical harness, not HUMAN ACCEPTED','time_monotonic':time.monotonic()})
        service.authorize_registered_tool(job['id'],True)
        service.threads[job['id']].join(service.DEADLINE_SECONDS+5)
        if service.threads[job['id']].is_alive():raise TimeoutError('Worker did not terminate')
        state=service.status(job['id'])
        result['job_report']=state
        if state['state']!='completed':raise RuntimeError('Worker did not complete')
        check=next(item for item in state['checks'] if item['id']=='registered_tool')
        if check['status']!='PASS' or check['evidence']['exit_code']!=0:
            raise RuntimeError('Registered search did not match fixture')
        if len(created)!=1 or len(created[0].receipts)!=1:raise RuntimeError('Unexpected workbench/call count')
        bench=created[0]
        result['acquisitions']=bench.acquisitions
        result['tool_requests']=bench.requests
        result['tool_receipts']=bench.receipts
        session=service._investigations[job['id']]
        outputs=[]
        for record in session.evidence.records.values():
            if record['kind']=='tool-artifact':
                artifact=output/'investigations'/record['artifact_relative_path']
                outputs.append({'path':str(artifact),'sha256':digest(artifact),'bytes':artifact.stat().st_size,
                    'marker_present':MARKER.encode() in artifact.read_bytes()})
        result['persisted_outputs']=outputs
        if not any(item['marker_present'] for item in outputs):raise RuntimeError('No persisted matching output')
        result['workspace_cleanup']={job['id']:sorted(service._workspaces.get(job['id'],set()))}
        if service._workspaces.get(job['id']):raise RuntimeError('Workspace cleanup unconfirmed')
        result['status']='VERIFIED'
    except Exception as exc:
        error=exc
        result['status']='FAILED'
        result['failure_type']=type(exc).__name__
        result['failure_message']=str(exc)
        if job is not None:result['job_report']=service.status(job['id'])
    finally:
        shutdowns=[]
        until=time.monotonic()+10
        while True:
            receipt=service.shutdown();shutdowns.append(receipt)
            if receipt.get('status')=='confirmed' or time.monotonic()>=until:break
            time.sleep(.1)
        result['shutdown_receipts']=shutdowns
        result['owned_threads_alive']=[key for key,thread in service.threads.items() if thread.is_alive()]
        result['target_sha256_after']=digest(target)
        result['target_unchanged']=result['target_sha256_after']==before
        if receipt.get('status')!='confirmed' or result['owned_threads_alive'] or not result['target_unchanged']:
            result['status']='FAILED'
        if created:
            result['final_workbench_receipts']=[bench.close() for bench in created]
            if any(item.get('status')!='confirmed' for item in result['final_workbench_receipts']):result['status']='FAILED'
        save(output/'result.json',result)
    print(json.dumps({'status':result['status'],'report':str(output/'result.json'),
        'job_id':result.get('job_id'),'target_unchanged':result['target_unchanged'],
        'tool_calls':sum(len(bench.receipts) for bench in created),'shutdown':result['shutdown_receipts'][-1]['status']}))
    return 0 if result['status']=='VERIFIED' else 1


if __name__=='__main__':raise SystemExit(main())
