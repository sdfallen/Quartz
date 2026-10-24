"""Read-only provider smoke test; never prints credentials or desktop contents."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from config import get_llm_provider
from core.desktop_control import desktop_windows
from core.tool_registry import ToolRegistry

def probe(model):
    provider = get_llm_provider()
    client = OpenAI(api_key=provider['api_key'], base_url=provider['base_url'],
                    timeout=40, max_retries=0)
    registry = ToolRegistry()
    registry.register('desktop_windows', desktop_windows)
    try:
        reply = client.chat.completions.create(model=model, max_tokens=1024,
            messages=[{'role': 'user', 'content': 'Reply with the word OK.'}])
        assert reply.choices[0].message.content, 'Empty chat reply'
        messages = [{'role': 'user', 'content': 'Use desktop_windows to list visible windows.'}]
        reply = client.chat.completions.create(model=model, max_tokens=1500,
            messages=messages, tools=registry.schemas(),
            tool_choice={'type': 'function', 'function': {'name': 'desktop_windows'}})
        message = reply.choices[0].message
        assert message.tool_calls and message.tool_calls[0].function.name == 'desktop_windows'
        messages.append(message.model_dump(exclude_none=True))
        for call in message.tool_calls:
            messages.append({'role': 'tool', 'tool_call_id': call.id,
                             'content': '{"windows": [], "test_fixture": true}'})
        reply = client.chat.completions.create(model=model, max_tokens=1024, messages=messages)
        assert reply.choices[0].message.content, 'Empty tool-result reply'
        print(model, 'PASS chat + forced tool + result continuation', flush=True)
    except Exception as exc:
        print(model, type(exc).__name__, str(exc)[:180], flush=True)

if __name__ == '__main__':
    models = sys.argv[1:] or ['meta/llama-3.3-70b-instruct',
        'nvidia/nemotron-3-ultra-550b-a55b', 'nvidia/nemotron-3.5-lightning-30b-a3b']
    list(ThreadPoolExecutor(max_workers=3).map(probe, models))
