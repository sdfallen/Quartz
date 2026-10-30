"""Official Gemini CLI adapter, independent from Antigravity Desktop/agy."""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from core.antigravity_runtime import AntigravityRuntime
from core.cli_installer import app_root, resolve_cli, node_command, cli_environment
from core.atomic_json import atomic_write_json, load_json
from core.gemini_auth import load_connection, auth_method, task_environment, oauth_status


def _gemini_connection_meta(base=None) -> dict:
    return load_connection(Path(base) if base else app_root())


class GeminiRuntime(AntigravityRuntime):
    DEFAULT_MODEL = "auto"
    DEFAULT_EFFORT = "medium"
    backend = "gemini"

    def start(self, prompt, project_path, **kwargs):
        if kwargs.get("effort") not in (None, "", "medium"):
            raise ValueError("Gemini CLI düşünme seviyesini model yönetir; otomatik (medium) seçimini kullanın")
        return super().start(prompt, project_path, **kwargs)

    @staticmethod
    def _find_executable(explicit=None):
        return resolve_cli("gemini", explicit)

    def list_models(self, force=False):
        return {"provider": "antigravity", "backend": "gemini", "default_model": "auto",
                "default_effort": "medium", "efforts": list(self.SUPPORTED_EFFORTS),
                "models": [{"id": "auto", "label": "Gemini — otomatik model", "default_effort": "medium",
                            "efforts": ["medium"]}], "source": "gemini_cli", "error": ""}

    def probe(self, force=False):
        now = time.monotonic()
        meta = _gemini_connection_meta()
        env = task_environment(cli_environment(), meta)
        method = auth_method(meta, env)
        oauth = oauth_status(env, app_root(), verify=force) if method == "account" else {}
        raw_key = str(env.get("GEMINI_API_KEY") or "").strip()
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest() if raw_key else ""
        # Do not reuse a ready result from another method, token or key.
        auth_state = (method, key_hash, json.dumps(meta, sort_keys=True), json.dumps(oauth, sort_keys=True))
        cache_key = (*self._cache_key(), auth_state)
        if getattr(self, "_auth_probe_key", None) != cache_key:
            self._probe_cache, self._probe_cache_at = None, 0.0
            self._auth_probe_key = cache_key
        if self._probe_cache is None and self._probe_cache_at == 0.0:
            shared = self._SHARED_PROBE_CACHE.get(cache_key)
            if shared and (now - shared[0]) < self.PROBE_TTL:
                self._probe_cache_at, self._probe_cache = shared[0], dict(shared[1])
        if not force and self._probe_cache and now-self._probe_cache_at < self.PROBE_TTL:
            return dict(self._probe_cache)
        version = self._probe(["--version"])
        key_verified = bool(raw_key and meta.get("validated_at") and meta.get("key_sha256") == key_hash)
        configured = bool(raw_key) if method == "api-key" else oauth.get("configured", False)
        auth_verified = key_verified if method == "api-key" else oauth.get("auth_verified", False)
        authenticated = configured
        result = {"installed": version["returncode"] == 0, "version": version["stdout"].strip(),
                  "executable": self.executable, "configured": configured,
                  "authenticated": authenticated, "auth_verified": auth_verified,
                  "verification_status": "verified" if auth_verified else ("unverified" if configured else "missing"),
                  "authentication": "api-key" if method == "api-key" else "google-account",
                  "ready": version["returncode"] == 0 and auth_verified, "backend": "gemini",
                  "error": "" if auth_verified else (oauth.get("auth_message") or ("Gemini bağlantısı henüz doğrulanmadı" if configured else "Gemini hesabını veya API anahtarını bağlayın"))}
        self._probe_cache, self._probe_cache_at = result, now
        if result.get("ready"):
            self._SHARED_PROBE_CACHE[cache_key] = (now, dict(result))
        return dict(result)

    def _command(self, args):
        if "-p" not in args:
            return node_command(self.executable, args)
        def value(flag):
            return args[args.index(flag)+1] if flag in args else None
        command = ["-p", value("-p"), "--output-format", "stream-json"]
        model = value("--model")
        if model and model != "auto":
            command += ["--model", model]
        session = value("--conversation")
        if session and session.startswith("gemini:"):
            command += ["--resume", session.removeprefix("gemini:")]
        command += ["--approval-mode", "yolo" if "--dangerously-skip-permissions" in args or value("--mode") == "auto" else "plan"]
        return node_command(self.executable, command)

    def _process_options(self, options, project, desktop_connection, tool_guard):
        env = dict(cli_environment())
        env.update(options.get("env") or {})
        metadata = _gemini_connection_meta()
        method = auth_method(metadata, env)
        env = task_environment(env, metadata)
        # System-override settings apply to this child only; user config untouched.
        settings = {"advanced": {"ignoreLocalEnv": True}, "telemetry": {"enabled": False},
                    "ide": {"enabled": False}, "mcp": {"allowed": []}, "mcpServers": {}}
        settings["security"] = {"auth": {"selectedType": "gemini-api-key" if method == "api-key" else "oauth-personal"}}
        if desktop_connection is not None or tool_guard:
            settings["tools"] = {"core": []}
        if desktop_connection is not None:
            from core.desktop_agents import mcp_command
            from core.desktop_mcp import TOOLS
            cmd = mcp_command()
            # Gemini's core allowlist enforcement outranks trusted MCP rules.
            # Explicit names allow our capability without enabling shell/files.
            settings["tools"] = {"core": ["mcp_quartz-desktop_" + tool["name"] for tool in TOOLS]}
            settings["mcp"] = {"allowed": ["quartz-desktop"]}
            settings["mcpServers"] = {"quartz-desktop": {"command": cmd[0], "args": cmd[1:],
                "env": {"QUARTZ_DESKTOP_URL": "$QUARTZ_DESKTOP_URL", "QUARTZ_DESKTOP_TOKEN": "$QUARTZ_DESKTOP_TOKEN"}, "trust": True}}
        inherited = set()
        user_home = Path(env.get("GEMINI_CLI_HOME") or Path.home())
        for config in (user_home / ".gemini/settings.json", Path(project) / ".gemini/settings.json"):
            if config.is_file():
                try:
                    inherited.update(json.loads(config.read_text(encoding="utf-8")).get("mcpServers", {}))
                except (OSError, ValueError, TypeError):
                    raise ValueError("Gemini ayarları okunamadı; güvenli görev başlatılmadı") from None
        settings["mcp"]["excluded"] = sorted(inherited - ({"quartz-desktop"} if desktop_connection else set()))
        directory = tempfile.mkdtemp(prefix="quartz-gemini-config-")
        path = Path(directory) / "settings.json"
        atomic_write_json(path, settings)
        os.chmod(path, 0o600)
        env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(path)
        self._settings_paths = getattr(self, "_settings_paths", []) + [path]
        return {"env": env}

    def _probe(self, args, timeout=15):
        import subprocess
        try:
            result = subprocess.run(node_command(self.executable, args), env=cli_environment(), stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        except Exception:
            return {"returncode": -1, "stdout": "", "stderr": "Gemini CLI başlatılamadı"}

    def _normalize_event(self, event):
        kind = event.get("type")
        if kind == "init":
            session = event.get("session_id")
            return {"event": "init", "conversation_id": "gemini:" + session if session else None}
        if kind == "message" and event.get("role") == "assistant":
            return {"event": "step_update", "step_update": {"text_delta": event.get("content", "")}}
        if kind == "result":
            return {"event": "result", "result": {"status": "SUCCESS" if event.get("status") == "success" else "ERROR",
                    "usage": event.get("stats"), "error": event.get("error")}}
        if kind == "tool_use":
            tool_name = event.get("tool_name") or event.get("name")
            params = event.get("parameters") or event.get("args") or event.get("input") or {}
            tool_id = event.get("tool_id") or event.get("id")
            if tool_id:
                pending = getattr(self, "_pending_tools", None)
                if pending is None:
                    pending = {}
                    self._pending_tools = pending
                pending[tool_id] = {"tool_name": tool_name, "parameters": params}
            return {"event": "step_update", "step_update": {"tool_name": tool_name, "state": "RUNNING", "tool_info": {"parameters": params}}}
        if kind == "tool_result":
            tool_id = event.get("tool_id") or event.get("id")
            pending = getattr(self, "_pending_tools", {}).pop(tool_id, {}) if tool_id else {}
            tool_name = event.get("tool_name") or event.get("name") or pending.get("tool_name") or "tool"
            params = event.get("parameters") or event.get("args") or pending.get("parameters") or {}
            is_err = str(event.get("status") or "").lower() in {"error", "failed"} or bool(event.get("is_error")) or bool(event.get("error"))
            return {"event": "step_update", "step_update": {
                "tool_name": tool_name,
                "state": "ERROR" if is_err else "DONE",
                "tool_info": {
                    "parameters": params,
                    "exit_code": event.get("exit_code", 1 if is_err else 0),
                    "output": event.get("output") or event.get("result") or "",
                    "error": event.get("error") or "",
                },
            }}
        if kind == "error":
            return {"event": "result", "result": {"status": "ERROR", "error": event.get("message", "Gemini hatası")}}
        return {"event": "gemini_raw", "data": event}

    def shutdown(self):
        super().shutdown()
        for path in getattr(self, "_settings_paths", []):
            try:
                path.unlink(missing_ok=True)
                path.parent.rmdir()
            except OSError:
                pass


def google_runtime(executable=None, *, base=None, legacy_factory=AntigravityRuntime):
    # Existing accounts/selections remain usable; agy is optional, never installed.
    env = cli_environment()
    meta = _gemini_connection_meta(base)
    if meta.get("backend") == "agy" and meta.get("method") == "account":
        return legacy_factory(executable)
    if env.get("GEMINI_API_KEY") or os.getenv("QUARTZ_GOOGLE_BACKEND") == "gemini" or meta.get("backend") == "gemini":
        return GeminiRuntime(executable)
    try:
        return legacy_factory(executable)
    except FileNotFoundError:
        return GeminiRuntime(executable)
