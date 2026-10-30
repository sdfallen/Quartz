"""Shared Gemini credential selection; local files alone never verify OAuth."""
import hashlib
import json
import math
import os
import time
import urllib.request
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json

OAUTH_CHECK_TTL = 300


def load_connection(root):
    root = Path(root)
    for path in (root / ".quartz/cli_connections.json", root / "quartz_memory.json"):
        data = load_json(path, {})
        if not isinstance(data, dict):
            continue
        connections = data.get("cli_connections") if path.name == "quartz_memory.json" else data
        if isinstance(connections, dict) and isinstance(connections.get("gemini"), dict):
            return dict(connections["gemini"])
    return {}


def auth_method(metadata, env):
    selected = metadata.get("method")
    return selected if selected in {"account", "api-key"} else ("api-key" if env.get("GEMINI_API_KEY") else "account")


def task_environment(env, metadata):
    result = dict(env)
    # Gemini's Windows ACL validation invokes Windows PowerShell. A parent
    # PowerShell 7 module path can make Get-Acl unloadable. Prefer the native
    # modules in this child only; keep all inherited paths and security checks.
    system_root = result.get("SystemRoot") or result.get("SYSTEMROOT")
    if os.name == "nt" and system_root:
        native_modules = Path(system_root) / "System32/WindowsPowerShell/v1.0/Modules"
        if native_modules.is_dir():
            result["PSModulePath"] = str(native_modules) + os.pathsep + result.get("PSModulePath", "")
    if auth_method(metadata, result) == "account":
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"):
            result.pop(name, None)
    return result


def verify_google_account(token):
    """Validate identity through Google's documented UserInfo endpoint, not a model call.

    Never put credentials in URLs, logs or persisted metadata. Redirects are
    refused so Authorization cannot be forwarded to a different endpoint.
    """
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    request = urllib.request.Request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=5) as response:
            profile = json.loads(response.read(64 * 1024))
        return isinstance(profile, dict) and isinstance(profile.get("sub"), str) and bool(profile["sub"])
    except Exception:
        return False


def oauth_status(env, root, *, verify=False, validator=None):
    path = Path(env.get("GEMINI_CLI_HOME") or Path.home()) / ".gemini/oauth_creds.json"
    state = {"configured": path.is_file(), "auth_verified": False,
             "auth_message": "Google hesabını bağlayın"}
    if not state["configured"]:
        return state
    state["auth_message"] = "Google hesabı bağlantısı henüz doğrulanmadı; Bağlantıyı kontrol et'i kullanın"
    try:
        raw = path.read_bytes()
        if len(raw) > 64 * 1024:
            return state
        data = json.loads(raw)
        token = data.get("access_token") if isinstance(data, dict) else None
        expiry = float(data.get("expiry_date", 0)) / 1000 if isinstance(data, dict) else 0
        if not isinstance(token, str) or not token or not math.isfinite(expiry) or expiry <= time.time():
            state["auth_message"] = "Google oturumunun yenilenmesi gerekiyor; CLI girişini tamamlayıp bağlantıyı yeniden kontrol edin"
            return state
    except (OSError, ValueError, TypeError):
        return state

    fingerprint = hashlib.sha256(raw).hexdigest()
    cache_path = Path(root) / ".quartz/gemini-oauth-check.json"
    cached = load_json(cache_path, {})
    now = time.time()
    recheck = True
    if not verify and isinstance(cached, dict):
        try:
            age = now - float(cached.get("checked_at", 0))
            same_token = cached.get("fingerprint") == fingerprint
            interval = OAUTH_CHECK_TTL if cached.get("verified") is True else 15
            fresh = same_token and 0 <= age < interval
            state["auth_verified"] = fresh and cached.get("verified") is True
            # Complete a valid CLI login without requiring a second manual
            # verification click. Failed checks are briefly cached as well.
            recheck = not fresh
        except (ValueError, TypeError):
            pass
    if verify or recheck:
        try:
            state["auth_verified"] = bool((validator or verify_google_account)(token))
        except Exception:
            state["auth_verified"] = False
        # Cache only the outcome and a fingerprint; never tokens or identity.
        try:
            atomic_write_json(cache_path, {"fingerprint": fingerprint, "checked_at": now,
                                          "verified": state["auth_verified"]})
        except OSError:
            pass  # Current result remains valid even if cache persistence fails.
    if state["auth_verified"]:
        state["auth_message"] = "Google hesabı doğrulandı; model erişimi ve kota ayrıca değerlendirilir"
    elif verify or recheck:
        state["auth_message"] = "Google hesabı doğrulanamadı; bağlantıyı veya CLI oturumunu kontrol edin"
    return state
