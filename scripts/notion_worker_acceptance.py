"""Explicit, disposable read-only Worker acceptance. No normal-chat tools enabled.

--prepare starts a cloud session and creates ONE signed test grant.
--run submits once, drains the owner-scoped queue and asks Notion to read the
signed result. Pending approvals are reported; never auto-approved or bypassed.
--stop revokes this fixture persistently. No API token or key is printed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.atomic_json import atomic_write_json, load_json
from core.notion_cli import NotionCli, NotionError, profile_root
from core.notion_runtime import NotionRuntime
from core.notion_worker_bridge import NotionQueueApi, ReadOnlyWorkerBridge, load_bridge_key, rich, sign


def owned_context():
    runtime = NotionRuntime()
    cfg = runtime.configuration()
    bridge = load_json(profile_root()/'worker-bridge.json', {})
    if bridge.get('workspace_id') != cfg.get('workspace_id') or bridge.get('mode') != 'readonly-fixture':
        raise RuntimeError('Scoped bridge configuration is unavailable')
    key = load_bridge_key(bridge['credential_target'])
    return runtime, cfg, bridge, key


def save(path, data):
    atomic_write_json(path, data)


def prepare():
    runtime, cfg, bridge, key = owned_context()
    run = runtime.start('Quartz salt okunur araç kabul oturumu. İmzalı test iznini sonraki mesajda vereceğim; şu anda araç çağırma.')
    while run['status'] not in runtime.TERMINAL:
        time.sleep(.2)
        run = runtime.get(run['id'])
    if run['status'] != 'completed': raise RuntimeError('Bootstrap cloud session did not complete')
    task = uuid.uuid4().hex
    folder = profile_root()/'worker-fixtures'/task
    folder.mkdir(parents=True, exist_ok=False)
    path = folder/'fixture.txt'
    proof = uuid.uuid4().hex + uuid.uuid4().hex
    path.write_text('Quartz yerel test dosyası. Okuma kanıtı: '+proof, encoding='utf-8')
    stat = path.stat()
    manifest = {'task_id':task,'session_id':run['session_id'],'project_id':'quartz-readonly-fixture',
        'scope_ref':uuid.uuid4().hex,'request_id':uuid.uuid4().hex,'relative_path':'fixture.txt',
        'expires_at':time.time()+900,'root':str(folder.resolve()),
        'file_identity':[stat.st_dev,stat.st_ino,stat.st_size],
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'proof':proof,
        'agent_id':cfg['agent_id'],'state':'preparing'}
    manifest_path = folder/'manifest.json'
    save(manifest_path, manifest)
    grant = {k:manifest[k] for k in ('task_id','session_id','project_id','scope_ref','request_id','relative_path','expires_at')}
    grant['tool_name']='read_test_file'
    api = NotionQueueApi(cfg['workspace_id'], bridge['queue_id'])
    row = api.create('grant:'+task, {'Task ID':rich(task),'Session ID':rich(run['session_id']),
        'Project ID':rich(manifest['project_id']), 'State':{'select':{'name':'completed'}},
        'Expires At':{'date':{'start':datetime.fromtimestamp(manifest['expires_at'],timezone.utc).isoformat()}},
        'Signed Result':rich(sign('grant',grant,key))})
    api.page(row['id'])  # verify persisted parent and owner scope
    manifest.update(grant_page_id=row['id'], state='prepared')
    save(manifest_path, manifest)
    # Pointer is local-only; does not replace any user conversation or preference.
    save(profile_root()/'worker-acceptance.json', {'manifest':str(manifest_path.resolve())})
    return {'status':'prepared','task_id':task,'session_id':run['session_id'], 'expires_in_seconds':900}


def current():
    pointer = load_json(profile_root()/'worker-acceptance.json', {})
    path = Path(pointer.get('manifest','')).resolve(strict=True)
    root = (profile_root()/'worker-fixtures').resolve(strict=True)
    if not path.is_relative_to(root) or path.name != 'manifest.json': raise PermissionError('Foreign fixture manifest')
    return path, load_json(path,{})


def run_acceptance():
    runtime, cfg, bridge, key = owned_context()
    manifest_path, manifest = current()
    if manifest['agent_id'] != cfg['agent_id'] or not runtime._owned(manifest['session_id'], cfg):
        raise PermissionError('Cloud session ownership changed')
    stop = Path(manifest['root'])/'.stopped'
    if stop.exists() or manifest['expires_at'] <= time.time(): raise PermissionError('Fixture stopped or expired')
    api = NotionQueueApi(cfg['workspace_id'],bridge['queue_id'])
    client = NotionCli(cfg['workspace_id'])
    local = ReadOnlyWorkerBridge(api,key,manifest,Path(manifest['root'])/'receipts.sqlite')
    sid = manifest['session_id']
    if not manifest.get('request_submitted'):
        # Persist BEFORE the uncertain API boundary. A crash never auto-resends.
        manifest['request_submitted']=True
        save(manifest_path,manifest)
        message = ('quartzReadTestFile aracını bir kez çağır. grant_page_id='+manifest['grant_page_id']+
            ', request_id='+manifest['request_id']+', relative_path=fixture.txt. '+
            'Bu yalnız onaylı test okumasıdır. Kuyruğa alındıysa sonucu uydurma; yerel okuyucunun hazır bildirimini bekle.')
        client.request('v1/sessions', {'session_id':sid,'message':message})
    end = min(time.time()+100,manifest['expires_at'])
    local_result = None
    finished_without_request = 0
    while time.time()<end:
        if stop.exists(): local.stop(); return {'status':'stopped'}
        remote = client.request('v1/sessions/'+sid)
        if remote.get('status')=='requires_action':
            return {'status':'blocked','reason':'Notion tool approval required','session_id':sid}
        for page in api.query(manifest['task_id'],sid):
            if page.get('properties',{}).get('Signed Request',{}).get('rich_text'):
                local_result=local.process(page)
                manifest['request_page_id']=page['id']
                manifest['local_result']=local_result
                save(manifest_path,manifest)
        if local_result and remote.get('status')=='completed': break
        if remote.get('status')=='completed' and not local_result:
            finished_without_request += 1
            if finished_without_request >= 2:
                return {'status':'not_verified','reason':'Remote tool turn completed without a signed queue request','session_id':sid}
        if remote.get('status') in {'failed','canceled','terminated'}:
            return {'status':'blocked','reason':'Remote session ended before tool acceptance','remote_status':remote['status']}
        time.sleep(2)
    if not local_result:
        return {'status':'not_verified','reason':'No signed Worker request observed','session_id':sid}
    if local_result.get('status')!='completed':
        return {'status':'failed','reason':'Local read rejected'}
    if not manifest.get('result_notice_submitted'):
        manifest['result_notice_submitted']=True
        save(manifest_path,manifest)
        client.request('v1/sessions',{'session_id':sid,'message':
            'Yerel okuyucu işlemi bitirdi. quartzReadResult aracını request_page_id='+manifest['request_page_id']+
            ' ile kullan. Dosyadaki okuma kanıtını ve sha256 değerini yalnız gerçek araç sonucundan okuyarak yaz.'})
    for _ in range(35):
        if stop.exists():local.stop();return {'status':'stopped'}
        remote=client.request('v1/sessions/'+sid)
        if remote.get('status')=='requires_action':return {'status':'blocked','reason':'Notion result tool approval required','session_id':sid}
        if remote.get('status') in runtime.REMOTE_TERMINAL: break
        time.sleep(2)
    events=runtime._events(client,sid)
    messages=[''.join(p.get('text','') for p in e.get('content',[]) if p.get('type')=='text')
              for e in events if e.get('type')=='agent.message']
    text='\n'.join(messages)
    evidence={'status':'observed' if manifest['proof'] in text else 'not_verified',
        'session_id':sid,'task_id':manifest['task_id'],'request_page_id':manifest['request_page_id'],
        'proof_in_cloud_response':manifest['proof'] in text,'sha256_in_cloud_response':manifest['sha256'] in text,
        'local_result':local_result,'remote_status':remote.get('status'),
        'event_types':sorted({e.get('type','') for e in events}),'agent_messages':messages}
    save(Path(manifest['root'])/'evidence.json',evidence)
    return {k:v for k,v in evidence.items() if k not in {'local_result','agent_messages'}}


def set_main_chat(enabled):
    """Explicit, per-profile opt-in for the main chat. Never flips an existing
    ``enabled: false`` decision and never copies config between profiles."""
    path = profile_root()/'worker-bridge.json'
    bridge = load_json(path, {})
    if enabled:
        owned_context()   # same checks as the CLI pilot: profile, workspace, Credential Manager key
        if bridge.get('enabled') is False:
            return {'status':'blocked','reason':'worker-bridge.json enabled=false; ana sohbet açılmadı. Bu kararı ayrıca değiştirin.'}
    bridge['main_chat'] = enabled is True
    save(path, bridge)
    return {'status':'enabled' if enabled else 'disabled', 'profile':str(profile_root())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true')
    group.add_argument('--run',action='store_true')
    group.add_argument('--stop',action='store_true')
    group.add_argument('--enable-main-chat',action='store_true')
    group.add_argument('--disable-main-chat',action='store_true')
    args=parser.parse_args()
    try:
        if args.enable_main_chat: result=set_main_chat(True)
        elif args.disable_main_chat: result=set_main_chat(False)
        elif args.prepare: result=prepare()
        elif args.run: result=run_acceptance()
        else:
            _,m=current();(Path(m['root'])/'.stopped').touch();result={'status':'stopped'}
        print(json.dumps(result,ensure_ascii=True))
        return 0 if result['status'] in {'prepared','observed','stopped','enabled','disabled'} else 2
    except Exception as exc:
        print(json.dumps({'status':'blocked','reason':str(exc) if isinstance(exc,NotionError) else 'Acceptance failed safely; no automatic request replay or secret output.',
            'error_type':type(exc).__name__, 'code':getattr(exc,'code',None) if isinstance(exc,NotionError) else None}))
        return 2


if __name__=='__main__': raise SystemExit(main())
