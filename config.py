"""
config.py  —  Quartz Configuration
"""
import os
import sys
import logging
import tempfile
from dotenv import load_dotenv

load_dotenv(override=True)

log = logging.getLogger(__name__)

# ── GitHub Models (retiring 30 July 2026) ─────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_MODEL = os.getenv("GITHUB_MODEL", "openai/gpt-4o-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()

# ── NVIDIA NIM (free, OpenAI-compatible) ──────────────
NVIDIA_API_KEY    = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL      = os.getenv(
    "NVIDIA_MODEL", "openai/gpt-oss-20b")
NVIDIA_VISION_MODEL = os.getenv(
    "NVIDIA_VISION_MODEL",
    "meta/llama-3.2-90b-vision-instruct")
NVIDIA_BASE_URL   = "https://integrate.api.nvidia.com/v1"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# ── Voice (speech-to-text / text-to-speech) ───────────
VOICE_LANGUAGE = os.getenv("VOICE_LANGUAGE", "tr-TR")
VOICE_TTS_RATE = int(os.getenv("VOICE_TTS_RATE", "178"))


def get_llm_provider() -> dict:
    """
    Pick the text-chat backend. LLM_PROVIDER explicitly selects a configured
    provider; otherwise the legacy NVIDIA-first fallback remains in place.
    """
    nvidia_key = os.getenv("NVIDIA_API_KEY", NVIDIA_API_KEY)
    github_key = os.getenv("GITHUB_TOKEN", GITHUB_TOKEN)
    preferred = os.getenv("LLM_PROVIDER", LLM_PROVIDER).strip().lower()
    if preferred == "groq":
        return {"name": "groq", "base_url": GROQ_BASE_URL,
                "api_key": os.getenv("GROQ_API_KEY", GROQ_API_KEY),
                "model": os.getenv("GROQ_MODEL", GROQ_MODEL)}
    use_github = preferred == "github" and bool(github_key)
    use_nvidia = preferred == "nvidia" and bool(nvidia_key)
    if use_nvidia or (not use_github and nvidia_key):
        return {
            "name":     "nvidia",
            "base_url": NVIDIA_BASE_URL,
            "api_key":  nvidia_key,
            "model":    NVIDIA_MODEL,
        }
    return {
        "name":     "github",
        "base_url": "https://models.github.ai/inference",
        "api_key":  github_key,
        "model":    GITHUB_MODEL,
    }


def save_api_key(provider: str, api_key: str) -> None:
    """Persist one API key without exposing it to logs or chat history."""
    variable = {"nvidia": "NVIDIA_API_KEY", "github": "GITHUB_TOKEN",
                "groq": "GROQ_API_KEY"}[provider]
    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith(variable + "="):
            lines[index] = f"{variable}={api_key}"
            replaced = True
    if not replaced:
        lines.append(f"{variable}={api_key}")
    provider_replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith("LLM_PROVIDER="):
            lines[index] = f"LLM_PROVIDER={provider}"
            provider_replaced = True
    if not provider_replaced:
        lines.append(f"LLM_PROVIDER={provider}")
    fd, temporary = tempfile.mkstemp(prefix=".env-", dir=BASE_DIR, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines).rstrip() + "\n")
        os.replace(temporary, env_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def get_vision_provider() -> dict:
    """
    Same idea, but for screen_vision.py. NVIDIA's vision
    models use a different model id than the text one.
    """
    if NVIDIA_API_KEY:
        return {
            "name":     "nvidia",
            "base_url": NVIDIA_BASE_URL,
            "api_key":  NVIDIA_API_KEY,
            "model":    NVIDIA_VISION_MODEL,
        }
    return {
        "name":     "github",
        "base_url": "https://models.github.ai/inference",
        "api_key":  GITHUB_TOKEN,
        "model":    "openai/gpt-4o",
    }

# ── Assistant ─────────────────────────────────────────
ASSISTANT_NAME       = "Quartz"
MAX_HISTORY_MESSAGES = 20
COMMAND_TIMEOUT      = 30
MAX_OUTPUT_CHARS     = 4000

# ── Startup ───────────────────────────────────────────
AUTO_START = True

# ── Paths ─────────────────────────────────────────────
BASE_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
LOG_FILE     = os.path.join(BASE_DIR, "assistant.log")
HISTORY_FILE = os.path.join(BASE_DIR, "chat_history.json")
TASKS_FILE   = os.path.join(BASE_DIR, "quartz_tasks.json")
OPERATION_CONTEXT_FILE = os.path.join(BASE_DIR, "quartz_operation.json")
WORKFLOWS_FILE = os.path.join(BASE_DIR, "quartz_workflows.json")
SEARCH_INDEX_FILE = os.path.join(BASE_DIR, "local_search_index.json")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(2 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))


def validate_config() -> list:
    """Return list of configuration errors."""
    errors = []
    if not get_llm_provider().get("api_key"):
        errors.append(
            "Selected provider API key is missing in .env.")
    if not NVIDIA_API_KEY and not GITHUB_MODEL:
        errors.append(
            "GITHUB_MODEL not set in .env")
    if MAX_HISTORY_MESSAGES < 5:
        errors.append(
            "MAX_HISTORY_MESSAGES too low (min 5)")
    return errors


# ── Safe debug logging (no token leak) ───────────────
_active_provider = get_llm_provider()
if _active_provider["name"] == "nvidia" and NVIDIA_API_KEY:
    masked = NVIDIA_API_KEY[:6] + "****"
    log.debug(
        "Config loaded: provider=nvidia model=%s key=%s",
        NVIDIA_MODEL, masked)
elif _active_provider["name"] == "github" and GITHUB_TOKEN:
    masked = GITHUB_TOKEN[:4] + "****"
    log.debug(
        "Config loaded: provider=github model=%s token=%s",
        GITHUB_MODEL, masked)
elif _active_provider["name"] == "groq" and _active_provider.get("api_key"):
    log.debug("Config loaded: provider=groq model=%s", _active_provider["model"])
else:
    log.warning(
        "No LLM API key found in .env "
        "(set the selected provider's GROQ_API_KEY, NVIDIA_API_KEY or GITHUB_TOKEN)!")
