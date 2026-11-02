"""Explicit live acceptance: one pinned official tool, one generated local file.

No provider, user project, UI, account, PATH or system setting is changed.
Results are saved under the explicitly supplied private evidence directory.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import psutil
from core.investigation.session import InvestigationSession
from core.investigation.gateway import InvestigationToolGateway
from core.investigation.planning import InvestigationPolicy
from core.tool_workbench import ToolWorkbench


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence-root',required=True,type=Path)
    args=parser.parse_args()
    root=args.evidence_root.resolve()
    root.mkdir(exist_ok=False,parents=True)
    target=root/'generated-target.bin'
    target.write_bytes((b'ZERO\x00QUARTZ_TOOL_ACCEPTANCE=42\x00END\n')*4096)
    before=hashlib.sha256(target.read_bytes()).hexdigest()
    environment=dict(os.environ)
    workspace=root/'workspace';workspace.mkdir()
    event=threading.Event()
    session=InvestigationSession(target,root=root/'knowledge',event=event,
        deadline=time.monotonic()+100,tool_identity={'official-ripgrep':'14.1.1'})
    workbench=ToolWorkbench(managed_dir=root/'managed',workspace_dir=workspace)
    manifest=workbench.catalog_service.get('ripgrep')
    gateway=InvestigationToolGateway(session,workbench,workspace=workspace,
        policy=InvestigationPolicy(effects=frozenset({'read_target','write_workspace','execute_tool'}),allow_acquire=True),
        tool_specs={'ripgrep':{'source_url':manifest.source_url,'pinned_revision':manifest.pinned_revision,
            'package_digest':manifest.package_digest,'operations':['search','strings'],
            'effects':['read_target','write_workspace','execute_tool']}})
    done=threading.Event(); samples=[]
    def monitor():
        owner=psutil.Process()
        while not done.is_set():
            row=[]
            for proc in [owner]+owner.children(recursive=True):
                try:
                    cpu=proc.cpu_times()
                    row.append({'pid':proc.pid,'rss':proc.memory_info().rss,'cpu_seconds':cpu.user+cpu.system})
                except psutil.Error:pass
            samples.append({'monotonic':time.monotonic(),'processes':row})
            done.wait(.01)
    observer=threading.Thread(target=monitor);observer.start()
    result={'schema_version':1,'kind':'explicit-live-tool-acceptance','source_commit':None,
        'target_sha256':before,'manifest':manifest.to_dict(),'scope':'generated single file; official tool only',
        'limitations':['Process metrics sampled every10ms; very short child peaks may be missed.',
            'This is a CLI/host test, not packaged Quartz GUI acceptance or engine semantic analysis.']}
    try:
        started=time.monotonic()
        result['acquisition']=workbench.acquire(manifest,cancel_event=event)
        result['acquisition_seconds']=time.monotonic()-started
        receipts=[]
        for index in range(2):
            request={'investigation_id':session.evidence.id,'step_id':'search-'+str(index),
                'operation':'strings','tool_id':'ripgrep','target':session.target.as_dict(),
                'workspace':str(workspace),'options':{'pattern':'QUARTZ_TOOL_ACCEPTANCE=42','fixed_strings':False}}
            # strings schema intentionally excludes arbitrary flags.
            request['options'].pop('fixed_strings')
            receipt=gateway.execute(request,event)
            assert receipt['status']=='completed' and receipt['exit_code']==0
            assert receipt['cleanup_receipt']['status']=='confirmed'
            assert any(b'QUARTZ_TOOL_ACCEPTANCE=42' in (workspace/a['path']).read_bytes() for a in receipt['artifacts'])
            again=gateway.execute(request,event)
            assert again['replayed_receipt'] and again['process_identity']==receipt['process_identity']
            receipts.append(receipt)
        result['receipts']=receipts
        result['replay_spawn_count']=0
        result['target_unchanged']=hashlib.sha256(target.read_bytes()).hexdigest()==before
        result['parent_environment_unchanged']=dict(os.environ)==environment
        session.finish([])
        result['evidence_records']=session.evidence.records
        result['status']='VERIFIED' if result['target_unchanged'] and result['parent_environment_unchanged'] else 'FAILED'
    except BaseException as exc:
        result['status']='FAILED';result['error']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        result['gateway_cleanup']=gateway.close()
        result['workbench_cleanup']=workbench.close()
        session.close()
        done.set();observer.join(5)
        result['metrics']={'scope':'acceptance Python controller and its descendants',
            'sample_count':len(samples),'peak_tree_rss_bytes':max((sum(p['rss'] for p in s['processes']) for s in samples),default=0)}
        (root/'metrics.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
        result['source_hashes']={str(p.relative_to(Path(__file__).resolve().parents[2])):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in list((Path(__file__).resolve().parents[2]/'core/tool_workbench').glob('*.py'))+[Path(__file__)]}
        (root/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'evidence_root':str(root),
        'cleanup':result['workbench_cleanup']['status'],'metrics':result['metrics']}))

if __name__=='__main__':main()
