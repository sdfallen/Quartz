"""Synthetic real-CLI chat through the host service; no GUI, game or user data.

This does not establish desktop-control acceptance. It records both providers,
actual CLI tool events, message lifecycle and host status response latency.
"""
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.agent_chat import AgentChatService
from core.multi_agent_service import MultiAgentService


def main():
    destination = ROOT/'labs'/('reliability-live-' + time.strftime('%Y%m%d-%H%M%S'))
    destination.mkdir(parents=True, exist_ok=False)
    report = {'scope':'Real synthetic CLI chat, not live desktop/UI acceptance', 'providers':{}}
    with tempfile.TemporaryDirectory(prefix='quartz-reliability-live-') as folder:
        service = MultiAgentService(projects=[{'id':'fixture','path':folder}])
        chat = AgentChatService(service, Path(folder)/'chat.json')
        try:
            started = time.monotonic(); initial = chat.status()
            report['first_status_seconds'] = time.monotonic() - started
            cid = initial['active_conversation']['id']
            chat.set_agent_model(cid, 'codex', model='gpt-6-luna', effort='low')
            chat.set_agent_model(cid, 'antigravity', model='gemini-3.8-flash-high', effort='high')
            chat.send_message('Merhaba! Sadece sohbet edelim. Bugün nasılsın? Tek cümle Türkçe cevap ver.',
                              agent='collaboration', conversation_id=cid)
            deadline = time.monotonic() + 180
            latencies = []
            while True:
                at = time.monotonic(); state = chat.poll_active()
                latencies.append(time.monotonic() - at)
                if not state.get('active'): break
                if time.monotonic() >= deadline:
                    chat.cancel_active(); report['timeout'] = True; break
                time.sleep(.25)
            conv = chat.store.get(cid)
            report['turn'] = dict(chat._active_turn or {})
            report['max_host_poll_seconds'] = max(latencies, default=0)
            report['messages'] = conv['messages']
            for provider in ('codex','antigravity'):
                messages = [m for m in conv['messages'] if m.get('sender') == provider]
                runs = [service.get_run(m['metadata']['run_id']) for m in messages if m.get('metadata',{}).get('run_id')]
                tool_events = [event for run in runs for event in run.get('events',[]) if
                    str(event.get('event','')).lower().startswith('tool') or
                    event.get('item',{}).get('type') in {'command_execution','mcp_tool_call','web_search','function_call'}]
                passed = (len(messages) == 1 and messages[0].get('status') == 'completed'
                          and bool(messages[0].get('content','').strip()) and bool(runs)
                          and not tool_events and all(not r.get('commands') and not r.get('files_changed') for r in runs))
                report['providers'][provider] = {'status':'VERIFIED' if passed else 'FAILED',
                    'tool_events':len(tool_events), 'runs':runs}
        except Exception as exc:
            report['error'] = str(exc)
        finally:
            chat.close(); service.shutdown()
            worker = chat._diagnostics.worker
            if worker: worker.join(45)
    report['status'] = 'VERIFIED' if len(report['providers']) == 2 and all(
        r['status'] == 'VERIFIED' for r in report['providers'].values()) else 'FAILED'
    (destination/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status':report['status'], 'evidence':str(destination/'result.json'),
        'first_status_seconds':report.get('first_status_seconds'),
        'providers':{p:{k:v for k,v in r.items() if k!='runs'} for p,r in report['providers'].items()}}, indent=2))
    return 0 if report['status'] == 'VERIFIED' else 1


if __name__ == '__main__': raise SystemExit(main())
