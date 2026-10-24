"""Real CLI text-only smoke; no game, project edits, GUI or user history.

Provider refusals/quota are recorded, not bypassed. Inspect raw tool events,
not just a model saying that no tools were used.
"""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.multi_agent_service import MultiAgentService


def main():
    destination = ROOT / 'labs' / ('text-chat-' + time.strftime('%Y%m%d-%H%M%S'))
    destination.mkdir(parents=True)
    service = MultiAgentService(projects=[{'id':'aster', 'path':'C:/WarbandIsland', 'protected':True}])
    rows = {}
    try:
        for provider, model in [('codex','gpt-6-luna'), ('antigravity','gemini-3.8-flash-low')]:
            try:
                result = service.dispatch(provider, 'Selam! Bugün nasılsın? Bir cümle Türkçe sohbet yanıtı ver.',
                    project_id='aster', chat_mode=True, conversation_only=True, model=model, effort='low')
                runtime = service.codex if provider == 'codex' else service.antigravity
                deadline = time.monotonic() + 150
                while runtime.get(result['run']['id'])['status'] not in runtime.TERMINAL:
                    if time.monotonic() > deadline:
                        runtime.cancel(result['run']['id']); break
                    time.sleep(.25)
                run = runtime.get(result['run']['id'])
                tool_events = [e for e in run.get('events', []) if
                    str(e.get('event', '')).lower().startswith('tool') or
                    e.get('item', {}).get('type') in {'command_execution','mcp_tool_call','web_search','function_call'}]
                passed = (run['status'] == 'completed' and bool(run.get('result','').strip())
                          and not tool_events and not run.get('commands') and not run.get('files_changed'))
                rows[provider] = {'status':'VERIFIED' if passed else 'FAILED', 'run':run,
                                  'tool_event_count':len(tool_events)}
                print(provider, rows[provider]['status'], str(run.get('result',''))[:220], flush=True)
            except Exception as exc:
                rows[provider] = {'status':'BLOCKED', 'error':str(exc)}
                print(provider, 'BLOCKED', str(exc), flush=True)
        (destination / 'acceptance.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        print('Evidence:', destination)
    finally:
        service.shutdown()


if __name__ == '__main__': main()
