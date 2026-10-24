"""Provider-independent access to OpenAI-compatible chat backends."""

import time
import re
import threading
from core.request_budget import compact


class LLMGateway:
    def __init__(self, client, model: str, logger=None):
        self.client = client
        self.model = model
        self.log = logger
        self.cancel_event = threading.Event()
        self.on_wait = None
        self.on_result = None

    def complete(self, messages: list, *, max_tokens: int = 1024,
                 tools: list | None = None, max_retries: int = 2):
        last_error = None
        base_url = str(getattr(self.client, 'base_url', ''))
        groq = 'api.groq.com' in base_url
        nvidia = 'api.nvidia.com' in base_url
        if groq or nvidia:
            messages, tools = compact(messages, tools)
            max_tokens = min(max_tokens, 700 if tools else 256)
        for attempt in range(max_retries + 1):
            if self.cancel_event.is_set():
                raise RuntimeError('İstek iptal edildi.')
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                }
                if tools:
                    kwargs.update({"tools": tools, "tool_choice": "auto"})
                if (groq or nvidia) and self.model.startswith('openai/gpt-oss'):
                    kwargs['reasoning_effort'] = 'low'
                if nvidia and 'nemotron-3' in self.model:
                    kwargs['extra_body'] = {
                        'chat_template_kwargs': {'enable_thinking': False},
                        'reasoning_budget': 0,
                    }
                started = time.monotonic()
                response = self.client.chat.completions.create(**kwargs)
                elapsed = time.monotonic() - started
                if self.log:
                    self.log.info('LLM seconds=%.2f tools=%d usage=%s', elapsed,
                                  len(tools or []), getattr(response, 'usage', None))
                if self.on_result:
                    self.on_result(True, elapsed, getattr(response, 'usage', None))
                if not getattr(response, "choices", None):
                    raise ValueError("LLM returned no choices")
                return response.choices[0].message
            except Exception as exc:
                last_error = exc
                if self.on_result:
                    self.on_result(False, 0.0, exc)
                if "429" in str(exc) and attempt < max_retries:
                    headers = getattr(getattr(exc, 'response', None), 'headers', {})
                    match = re.search(r'try again in ([\d.]+)s', str(exc))
                    try:
                        delay = float(headers.get('retry-after') or (match.group(1) if match else 2 ** attempt))
                    except (TypeError, ValueError):
                        delay = 2 ** attempt
                    if delay > 60:
                        raise RuntimeError(f'Kota doldu. Yaklaşık {delay:.0f} saniye sonra yeniden dene.') from exc
                    delay = max(.1, delay) + .25
                    if self.on_wait:
                        self.on_wait(delay)
                    if self.log:
                        self.log.warning("Rate limited; retrying in %ds", delay)
                    if self.cancel_event.wait(delay):
                        raise RuntimeError('İstek iptal edildi.') from exc
                    continue
                break
        raise last_error

    @staticmethod
    def text(message) -> str:
        content = getattr(message, "content", None)
        return content.strip() if isinstance(content, str) and content.strip() else ""
