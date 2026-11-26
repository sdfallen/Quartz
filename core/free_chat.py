"""Ücretsiz sohbet modu — SpeS for people who pay for no AI subscription (27 Nov 2026).

The user's own free accounts on official, documented APIs, for talking only: a conversation
marked free never reaches a coding agent, a tool, a file, a command, the desktop or a long job.
Fides's design review 27 Nov (ŞARTLI), first slice:

- Channels are API keys the user pastes: Gemini (Google AI Studio), OpenRouter (Kimi's free
  models) and Groq. No web session, cookie, scraping or borrowed CLI login, ever. The CLI
  channels (Codex, Antigravity) wait for a verified zero-tool profile.
- Each channel has two separate consents: "send my messages here" and "use it as a backup when
  another one is out of quota". Only consented channels are tried, in the user's order.
- Keys are stored per Windows user with DPAPI under LocalAppData, never in .env, logs, chat,
  memory or packages. Adding a key never changes the provider of SpeS's other features.
- No tools are ever sent and none returned are run; the reply is text only. Errors stay apart:
  quota, key, unreachable, refusal (never routed around by another model), other.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

CHANNELS = {
    "gemini": {
        "label": "Gemini (Google AI Studio)", "persona": "Eos",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_page": "https://aistudio.google.com/apikey",
        "privacy": "Google, ücretsiz katmanda yazdıklarını ürünlerini geliştirmek için kullanabilir.",
    },
    "openrouter": {
        "label": "OpenRouter (Kimi)", "persona": "Kimi",
        "base_url": "https://openrouter.ai/api/v1",
        "key_page": "https://openrouter.ai/keys",
        "privacy": "Ücretsiz modellerde modeli sunan şirket yazdıklarını kaydedebilir ya da eğitimde kullanabilir.",
    },
    "groq": {
        "label": "Groq (açık modeller)", "persona": "Lyra",
        "base_url": "https://api.groq.com/openai/v1",
        "key_page": "https://console.groq.com/keys",
        "privacy": "Groq yazdıklarını kendi koşullarına göre işler.",
    },
}
ORDER = ("gemini", "openrouter", "groq")
GROQ_PREFERRED = ("openai/gpt-oss-120b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b")
HISTORY_MESSAGES = 12
HISTORY_CHARS = 12000
MAX_OUTPUT_TOKENS = 1200
REQUEST_SECONDS = 60
KEY_MAX = 400


class FreeChatError(Exception):
    pass


# ── where things live ─────────────────────────────────────────────────────────────────
def home() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "Quartz" / "free_chat"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _protect(data: bytes, unprotect=False) -> bytes:
    """Windows DPAPI for the current user (Fides F3); no fallback to plain text."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    source = ctypes.create_string_buffer(data, len(data))
    blob_in, blob_out = Blob(len(data), source), Blob()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    entropy_bytes = b"SpeS free chat v1"
    entropy_buf = ctypes.create_string_buffer(entropy_bytes, len(entropy_bytes))
    entropy = Blob(len(entropy_bytes), entropy_buf)
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    fn = crypt32.CryptUnprotectData if unprotect else crypt32.CryptProtectData
    ok = (fn(ctypes.byref(blob_in), None, ctypes.byref(entropy), None, None, flags, ctypes.byref(blob_out))
          if unprotect else
          fn(ctypes.byref(blob_in), "SpeS", ctypes.byref(entropy), None, None, flags, ctypes.byref(blob_out)))
    if not ok:
        raise FreeChatError("Anahtar Windows kullanıcı şifrelemesiyle korunamadı.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


class SecretStore:
    """API keys, one per channel, DPAPI-protected per Windows user."""

    def __init__(self, root: Path | None = None, protect=None):
        self.path = Path(root or home()) / "keys.json"
        self.protect = protect or _protect
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.path)

    def set(self, channel: str, key: str):
        if channel not in CHANNELS:
            raise FreeChatError("Bilinmeyen kanal.")
        key = str(key or "").strip()
        if not key or len(key) > KEY_MAX or any(c.isspace() for c in key):
            raise FreeChatError("Anahtar boş, çok uzun ya da boşluk içeriyor.")
        with self._lock:
            data = self._read()
            data[channel] = base64.b64encode(self.protect(key.encode("utf-8"))).decode("ascii")
            self._write(data)

    def get(self, channel: str) -> str:
        with self._lock:
            raw = self._read().get(channel)
        if not raw:
            return ""
        try:
            return self.protect(base64.b64decode(raw), unprotect=True).decode("utf-8")
        except Exception:
            return ""

    def remove(self, channel: str):
        with self._lock:
            data = self._read()
            if data.pop(channel, None) is not None:
                self._write(data)

    def has(self, channel: str) -> bool:
        with self._lock:
            return bool(self._read().get(channel))


class Settings:
    """Per channel: send consent, backup consent, model; plus the order the user chose."""

    def __init__(self, root: Path | None = None):
        self.path = Path(root or home()) / "settings.json"
        self._lock = threading.Lock()

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        channels = data.get("channels") if isinstance(data.get("channels"), dict) else {}
        order = [c for c in (data.get("order") or []) if c in CHANNELS]
        order += [c for c in ORDER if c not in order]
        return {"channels": {c: {"send": bool((channels.get(c) or {}).get("send")),
                                 "backup": bool((channels.get(c) or {}).get("backup")),
                                 "model": str((channels.get(c) or {}).get("model") or "")[:120]}
                             for c in CHANNELS},
                "order": order}

    def update(self, channel: str, **values):
        if channel not in CHANNELS:
            raise FreeChatError("Bilinmeyen kanal.")
        with self._lock:
            data = self.read()
            for name in ("send", "backup"):
                if name in values:
                    data["channels"][channel][name] = bool(values[name])
            if "model" in values:
                data["channels"][channel]["model"] = str(values["model"] or "")[:120]
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
            return data

    def set_order(self, order):
        with self._lock:
            data = self.read()
            clean = [c for c in order if c in CHANNELS]
            data["order"] = clean + [c for c in ORDER if c not in clean]
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
            return data


# ── models and requests ───────────────────────────────────────────────────────────────
def _version(model_id: str) -> list:
    """The numbers in a model name, so k2.6 sorts after k2 and 3.8 after 3.6."""
    import re
    return [int(n) for n in re.findall(r"\d+", model_id)]


def choose_model(channel: str, ids) -> str:
    """The model SpeS uses on a channel. OpenRouter: only ":free" models (Fides: never a silent
    paid model), Kimi first. Gemini: a Flash model. Groq: a known open model."""
    ids = [str(i).removeprefix("models/") for i in ids if i]
    if channel == "openrouter":
        free = [i for i in ids if i.endswith(":free")]
        kimi = sorted((i for i in free if "kimi" in i.lower()), key=_version, reverse=True)
        return (kimi or free or [""])[0]
    if channel == "gemini":
        flash = [i for i in ids if "flash" in i and "image" not in i and "tts" not in i and "live" not in i
                 and "preview" not in i]
        flash.sort(key=lambda i: ("lite" in i, [-n for n in _version(i)]))
        return (flash or [""])[0]
    for preferred in GROQ_PREFERRED:
        if preferred in ids:
            return preferred
    return ""


def classify(exc) -> str:
    """quota | key | unreachable | refused | cancelled | other (Fides F2: never mixed)."""
    try:
        import openai
    except ImportError:  # pragma: no cover
        return "other"
    if isinstance(exc, openai.RateLimitError):
        return "quota"
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "key"
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError)):
        return "unreachable"
    if isinstance(exc, (openai.BadRequestError, openai.ContentFilterFinishReasonError,
                        openai.UnprocessableEntityError)):
        text = str(exc).lower()
        if any(w in text for w in ("safety", "policy", "content", "blocked", "moderation")):
            return "refused"
        return "other"
    if isinstance(exc, openai.APIStatusError) and getattr(exc, "status_code", 0) == 402:
        return "quota"  # OpenRouter: free credits or daily free limit used up
    return "other"


EXPLAIN = {
    "quota": "ücretsiz kotası doldu",
    "key": "anahtar geçersiz ya da yetkisiz",
    "unreachable": "şu an ulaşılamadı",
    "refused": "bu isteği yanıtlamayı reddetti",
    "cancelled": "durduruldu",
    "other": "beklenmeyen bir hata verdi",
    "no_model": "ücretsiz bir model bulunamadı",
}
FALLS_THROUGH = {"quota", "key", "unreachable", "no_model"}


def _client(channel, key):
    import openai
    return openai.OpenAI(base_url=CHANNELS[channel]["base_url"], api_key=key, timeout=REQUEST_SECONDS, max_retries=0)


class FreeChat:
    """Channels, consents and one text-only request at a time."""

    def __init__(self, store: SecretStore | None = None, settings: Settings | None = None, client=None):
        self.store = store or SecretStore()
        self.settings = settings or Settings()
        self.client = client or _client

    # status for the Bağlantılar screen: never a key, only that one exists
    def status(self) -> dict:
        data = self.settings.read()
        return {"order": data["order"], "channels": [
            {"id": c, **{k: CHANNELS[c][k] for k in ("label", "persona", "key_page", "privacy")},
             "connected": self.store.has(c), **data["channels"][c]} for c in data["order"]]}

    def connect(self, channel: str, key: str, send=True, backup=True) -> dict:
        """Check the key with one small request (the model list), then store it."""
        if channel not in CHANNELS:
            raise FreeChatError("Bilinmeyen kanal.")
        key = str(key or "").strip()
        try:
            ids = [m.id for m in self.client(channel, key).models.list()]
        except Exception as exc:
            raise FreeChatError(f"{CHANNELS[channel]['label']}: {EXPLAIN[classify(exc)]}.") from None
        model = choose_model(channel, ids)
        if not model:
            raise FreeChatError(f"{CHANNELS[channel]['label']}: {EXPLAIN['no_model']}.")
        self.store.set(channel, key)
        self.settings.update(channel, send=send, backup=backup, model=model)
        return self.status()

    def disconnect(self, channel: str) -> dict:
        self.store.remove(channel)
        self.settings.update(channel, send=False, backup=False, model="")
        return self.status()

    def consent(self, channel: str, send=None, backup=None) -> dict:
        values = {k: v for k, v in (("send", send), ("backup", backup)) if v is not None}
        self.settings.update(channel, **values)
        return self.status()

    def speakers(self) -> list:
        """Connected channels the user lets SpeS send to, in their order."""
        data = self.settings.read()
        return [c for c in data["order"] if data["channels"][c]["send"] and self.store.has(c)]

    def backups(self, exclude=()) -> list:
        data = self.settings.read()
        return [c for c in data["order"] if c not in exclude and data["channels"][c]["backup"]
                and self.store.has(c)]

    def ask(self, channel: str, messages: list, cancel: threading.Event) -> str:
        if cancel.is_set():
            raise FreeChatError("cancelled")
        key = self.store.get(channel)
        model = self.settings.read()["channels"][channel]["model"]
        if not key or not model:
            raise FreeChatError("key")
        # Fides: no tools, no functions, no web; a returned tool call is never run.
        response = self.client(channel, key).chat.completions.create(
            model=model, messages=messages, max_tokens=MAX_OUTPUT_TOKENS, temperature=0.7)
        choice = (getattr(response, "choices", None) or [None])[0]
        text = str(getattr(getattr(choice, "message", None), "content", "") or "").strip()
        if not text:
            raise FreeChatError("empty")
        return text

    def reply(self, channel: str, messages: list, cancel: threading.Event) -> dict:
        """One answer: the chosen channel, then the user's consented backups for quota, key and
        reachability errors only. Every attempt is recorded (Fides F2)."""
        attempts = []
        tried = [channel] + self.backups(exclude=(channel,))
        for name in tried:
            if cancel.is_set():
                attempts.append({"channel": name, "result": "cancelled"})
                return {"text": "", "channel": None, "attempts": attempts, "outcome": "cancelled"}
            started = time.time()
            try:
                text = self.ask(name, messages, cancel)
            except Exception as exc:
                kind = (str(exc) if isinstance(exc, FreeChatError) and str(exc) in EXPLAIN else classify(exc))
                if isinstance(exc, FreeChatError) and str(exc) == "empty":
                    kind = "other"
                attempts.append({"channel": name, "result": kind, "seconds": round(time.time() - started, 1)})
                if kind in FALLS_THROUGH:
                    continue
                return {"text": "", "channel": name, "attempts": attempts, "outcome": kind}
            attempts.append({"channel": name, "result": "ok", "seconds": round(time.time() - started, 1)})
            return {"text": text, "channel": name, "attempts": attempts, "outcome": "ok"}
        return {"text": "", "channel": None, "attempts": attempts, "outcome": "exhausted"}


# ── prompts ───────────────────────────────────────────────────────────────────────────
def system_prompt(persona: str, team: list | None = None) -> str:
    others = [p for p in (team or []) if p != persona]
    parts = [
        f"Sen {persona}'sın; SpeS adlı uygulamanın ücretsiz sohbet modunda konuşan bir yapay zekâ "
        "arkadaşısın. Kullanıcıyla Türkçe, sıcak, doğal ve net konuş. Sohbet et, fikir ver, tartış, "
        "problem çözmesine yardım et. Uydurma; emin olmadığını söyle.",
        "Bu modda dosya, komut, internet ya da bilgisayar kontrolü yok; bunları yapabiliyormuş gibi "
        "davranma. Kullanıcı böyle bir iş isterse, SpeS'in Workspace bölümünün ücretli bir yapay zekâ "
        "aboneliğiyle bunu yapabildiğini kısaca söyle.",
    ]
    if others:
        parts.append(f"Bu sohbette {', '.join(others)} da var. Onların yanıtlarını gördüğünde tekrar etme: "
                     "katıl, karşı çık ya da yeni bir açı ekle; adlarıyla hitap edebilirsin.")
    return "\n\n".join(parts)


def history_messages(messages: list, persona_of) -> list:
    """Only this free conversation's own user text and the free agents' replies; nothing from
    jobs, reviews, attachments or SpeS notes (Fides F4). Bounded by count and characters."""
    kept = []
    for m in messages:
        meta = m.get("metadata") or {}
        content = str(m.get("content") or "").strip()
        if not content or m.get("status") not in (None, "completed"):
            continue
        if m.get("role") == "user" and meta.get("free_chat"):
            kept.append({"role": "user", "content": content})
        elif m.get("role") == "assistant" and meta.get("free_chat") and meta.get("free_channel"):
            kept.append({"role": "assistant", "speaker": persona_of(meta["free_channel"]), "content": content})
    kept = kept[-HISTORY_MESSAGES:]
    total, out = 0, []
    for item in reversed(kept):
        total += len(item["content"])
        if total > HISTORY_CHARS:
            break
        out.append(item)
    return list(reversed(out))


def build_messages(persona: str, team: list, history: list, round_replies: list) -> list:
    """System + history (other speakers' lines marked with their names) + this round so far."""
    messages = [{"role": "system", "content": system_prompt(persona, team)}]
    for item in history:
        if item["role"] == "assistant" and item.get("speaker") != persona:
            messages.append({"role": "user", "content": f"[{item['speaker']}]: {item['content']}"})
        else:
            messages.append({"role": item["role"], "content": item["content"]})
    for speaker, text in round_replies:
        messages.append({"role": "user", "content": f"[{speaker}]: {text}"})
    return messages
