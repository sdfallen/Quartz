"""Live model-only latency probe. Does not execute desktop commands."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from openai import OpenAI
from core.llm_provider import LLMGateway
import assistant

cfg = dotenv_values(Path(__file__).resolve().parents[1] / 'dist/Quartz/.env')
client = OpenAI(api_key=cfg['GROQ_API_KEY'], base_url='https://api.groq.com/openai/v1', timeout=40, max_retries=0)
gateway = LLMGateway(client, cfg.get('GROQ_MODEL','openai/gpt-oss-120b'))
gateway.on_wait = lambda seconds: print('quota_wait',round(seconds,2),flush=True)
history = [{'role':'system','content':assistant.SYSTEM_PROMPT+'\nDESKTOP EXECUTION PROTOCOL: Observe before actions; verify results. Do not invent success.'}]
for prompt in ['naber', 'YouTube sitesini aç', 'YouTube içinde müzik ara']:
    history.append({'role':'user','content':prompt})
    start=time.monotonic()
    try:
        result=gateway.complete(history, tools=assistant._tool_registry.schemas())
        print('prompt=',prompt,'seconds=',round(time.monotonic()-start,2),
              'tools=',[c.function.name for c in result.tool_calls or []],
              'text=',bool(result.content),flush=True)
        # No tools are executed. Preserve only an explicit observation of this dry run.
        history.append({'role':'assistant','content':'Test: önerilen araç henüz çalıştırılmadı.'})
    except Exception as exc:
        print(type(exc).__name__,str(exc)[:160],flush=True)
