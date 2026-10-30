"""First-run connection and CLI setup; secrets never enter chat/memory/logs."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json, _FILE_LOCK
from core.cli_installer import CliInstaller, app_root, cli_environment, node_command, resolve_cli
from core.gemini_auth import auth_method, oauth_status, task_environment


def _replace_text(path, text):
    fd, temporary = tempfile.mkstemp(prefix=".quartz-env-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


class OnboardingService:
    def __init__(self, base=None, installer=None, validate=None):
        self.base = Path(base) if base else app_root()
        self.installer = installer or CliInstaller()
        self.validate = validate or self._validate
        self.lock = threading.RLock()
        self.job = {"state": "idle", "message": "Bağlantı seçebilirsiniz"}
        self.login_processes = {}
        self._cached = None
        self._cached_at = 0

    def _load_connections(self) -> dict:
        result = {}
        for candidate in (self.base / ".quartz" / "cli_connections.json", self.base / "quartz_memory.json"):
            data = load_json(candidate, {})
            if isinstance(data, dict):
                conns = data.get("cli_connections") if candidate.name == "quartz_memory.json" else data
                if isinstance(conns, dict):
                    for k, v in conns.items():
                        if isinstance(v, dict) and k not in result:
                            result[k] = dict(v)
        return result

    @staticmethod
    def _cleanup_login_settings(process, path):
        try:
            if process is not None:
                process.wait()
        finally:
            try:
                path.unlink(missing_ok=True)
                path.parent.rmdir()
            except OSError:
                pass

    def status(self, force=False):
        pending = {provider: process.poll() is None for provider, process in self.login_processes.items()}
        with self.lock:
            was_pending = any(p.get("login_pending") for p in (self._cached or {}).get("providers", {}).values())
            if not force and not any(pending.values()) and not was_pending and self._cached and time.monotonic()-self._cached_at < 45:
                return {**self._cached, "job": dict(self.job)}
        from dotenv import dotenv_values
        values = dotenv_values(self.base / ".env")
        installed = self.installer.status()
        connections = self._load_connections()
        for provider, variable in (("codex", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")):
            raw_key = str(values.get(variable) or os.getenv(variable) or "").strip()
            credential = bool(raw_key)
            conn_meta = connections.get(provider, {})
            if provider == "gemini" and (conn_meta.get("backend") == "agy" or (not conn_meta and not credential)):
                try:
                    from core.antigravity_runtime import AntigravityRuntime
                    agy = AntigravityRuntime().probe(force=force)
                except (FileNotFoundError, OSError):
                    agy = {"installed": False, "ready": False}
                ready = bool(agy.get("ready"))
                installed[provider].update(
                    installed=bool(agy.get("installed")), executable=agy.get("executable"),
                    backend="agy", method="account", configured=ready or pending.get(provider, False),
                    connected=ready, auth_verified=ready, verification_status="verified" if ready else "unverified",
                    ready=ready, login_pending=bool(pending.get(provider) and not ready),
                    auth_message="Google hesabı Antigravity CLI ile bağlı" if ready else "Antigravity CLI Google girişini tamamlayın",
                    model_accessible="unknown", last_task_succeeded=None,
                )
                continue
            method = auth_method(conn_meta, {variable: raw_key}) if provider == "gemini" else conn_meta.get("method")
            key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest() if credential else ""
            key_verified = bool(
                credential
                and conn_meta.get("validated_at")
                and conn_meta.get("key_sha256") == key_hash
            )
            cached = False
            login_verified = False
            if provider == "codex" and installed[provider]["installed"]:
                try:
                    check = subprocess.run(node_command(installed[provider]["executable"], ["login", "status"]),
                                           env=cli_environment(), capture_output=True, text=True, timeout=10,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    cached = check.returncode == 0
                    login_verified = cached
                except Exception:
                    pass
            elif provider == "gemini":
                account = oauth_status(os.environ, self.base, verify=force) if method == "account" else {}
                cached = account.get("configured", False)
                login_verified = account.get("auth_verified", False)
                if method == "account":
                    credential = key_verified = False
                installed[provider]["auth_message"] = account.get("auth_message", "")
                # A legacy standalone agy login also satisfies an existing install.
                if not credential and not cached and not conn_meta.get("backend"):
                    try:
                        from core.antigravity_runtime import AntigravityRuntime
                        probe = AntigravityRuntime().probe()
                        cached = probe.get("ready", False)
                        login_verified = cached
                        if cached: installed[provider]["installed"] = True
                    except Exception:
                        pass
            configured = bool(credential or cached)
            auth_verified = bool(key_verified or login_verified)
            verification_status = "verified" if auth_verified else ("unverified" if configured else "missing")
            ready = bool(installed[provider]["installed"] and auth_verified)
            installed[provider].update(
                configured=configured,
                connected=configured,
                auth_verified=auth_verified,
                verification_status=verification_status,
                model_accessible=conn_meta.get("model_accessible", "unknown"),
                last_task_succeeded=conn_meta.get("last_task_succeeded"),
                backend=conn_meta.get("backend") or provider,
                method=method or ("api-key" if credential else ("account" if cached else "none")),
                ready=ready,
                login_pending=bool(pending.get(provider) and not ready),
            )
        with self.lock:
            result = {"providers": installed, "needs_setup": not any(p["ready"] for p in installed.values()),
                    "job": dict(self.job), "api_billing_note": "API anahtarı kullanımı sağlayıcının API kotasına tabidir; hesap girişi ayrı seçenektir."}
            self._cached, self._cached_at = result, time.monotonic()
            return result

    @staticmethod
    def _validate(provider, key):
        if provider == "codex":
            request = urllib.request.Request("https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + key})
        else:
            request = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", headers={"x-goog-api-key": key})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read(2 * 1024 * 1024))
            if not isinstance(payload, dict): raise ValueError()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403): raise ValueError("Anahtar kabul edilmedi; anahtarı ve hesap yetkisini kontrol edin") from None
            raise ValueError("Sağlayıcı bağlantıyı doğrulayamadı; kota veya servis durumunu kontrol edin") from None
        except Exception:
            raise ValueError("Bağlantı doğrulanamadı; internet bağlantısını kontrol edin") from None

    def _write_connection_metadata(self, provider, entry):
        memory_path = self.base / "quartz_memory.json"
        if memory_path.exists():
            raw = memory_path.read_text(encoding="utf-8-sig")
            try:
                memory = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                # Preserve corrupt original file untouched; store connection metadata in sidecar.
                backup_path = self.base / "quartz_memory.corrupt.json"
                if not backup_path.exists():
                    shutil.copy2(memory_path, backup_path)
                sidecar = self.base / ".quartz" / "cli_connections.json"
                sidecar.parent.mkdir(parents=True, exist_ok=True)
                conns = load_json(sidecar, {})
                if not isinstance(conns, dict):
                    conns = {}
                conns[provider] = entry
                atomic_write_json(sidecar, conns)
                return
            if not isinstance(memory, dict):
                raise ValueError("Hafıza dosyası nesne (JSON object) biçiminde değil")
        else:
            memory = {}
        conns = memory.get("cli_connections")
        if conns is not None and not isinstance(conns, dict):
            raise ValueError("cli_connections alanı geçersiz biçimde")
        memory.setdefault("cli_connections", {})[provider] = entry
        atomic_write_json(memory_path, memory)

    def _save(self, provider, key):
        variable = "OPENAI_API_KEY" if provider == "codex" else "GEMINI_API_KEY"
        clean_key = str(key).strip()
        entry = {
            "method": "api-key",
            "backend": provider,
            "validated_at": time.time(),
            "key_sha256": hashlib.sha256(clean_key.encode("utf-8")).hexdigest(),
        }
        with _FILE_LOCK:
            path = self.base / ".env"
            existed = path.exists()
            original = path.read_text(encoding="utf-8-sig") if existed else ""
            lines = [line for line in original.splitlines() if line.split("=", 1)[0].strip() != variable]
            lines.append(variable + "=" + json.dumps(clean_key))
            path.parent.mkdir(parents=True, exist_ok=True)
            _replace_text(path, "\n".join(lines) + "\n")
            try:
                self._write_connection_metadata(provider, entry)
            except Exception:
                if existed: _replace_text(path, original)
                elif path.exists(): path.unlink()
                raise

    def begin(self, operation, provider, key=""):
        if provider not in {"codex", "gemini"} or operation not in {"install", "install_agy", "key", "account", "account_agy"} or (operation in {"account_agy", "install_agy"} and provider != "gemini"):
            raise ValueError("Geçersiz bağlantı işlemi")
        if operation == "key" and (not isinstance(key, str) or not 10 <= len(key.strip()) <= 1024 or any(c in key for c in "\r\n\0")):
            raise ValueError("Geçerli API anahtarını girin")
        with self.lock:
            if self.job["state"] == "running": raise RuntimeError("Kurulum zaten sürüyor")
            if provider in self.login_processes and self.login_processes[provider].poll() is None:
                raise RuntimeError("Bu hesabın açık giriş penceresini tamamlayın veya kapatın")
            self.job = {"state": "running", "provider": provider, "message": "CLI ve bağlantı hazırlanıyor…"}
        thread = threading.Thread(target=self._work, args=(operation, provider, key.strip() if operation == "key" else ""), daemon=True, name="quartz-onboarding")
        thread.start()
        return {"started": True}

    def _work(self, operation, provider, key):
        try:
            if operation == "install_agy":
                self.installer.install("agy")
                with self.lock:
                    self._cached = None
                    self.job = {"state": "done", "provider": provider, "message": "Antigravity CLI hazır; Hesabımla bağlan ile Google girişini tamamlayın"}
                return
            if operation == "account_agy":
                from core.antigravity_runtime import AntigravityRuntime
                try:
                    runtime = AntigravityRuntime()
                except FileNotFoundError:
                    self.installer.install("agy")
                    runtime = AntigravityRuntime()
                probe = runtime.probe(force=True)
                if not probe.get("installed"):
                    raise RuntimeError("Antigravity CLI başlatılamadı; kurulumunu kontrol edin")
                with _FILE_LOCK:
                    self._write_connection_metadata("gemini", {
                        "method": "account", "backend": "agy", "selected_at": time.time(),
                    })
                if not probe.get("ready"):
                    env = task_environment(dict(cli_environment()), {"method": "account"})
                    self.login_processes[provider] = subprocess.Popen(
                        [runtime.executable], env=env, cwd=str(self.base),
                        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                    )
                with self.lock:
                    self._cached = None
                    self.job = {"state": "done", "provider": provider,
                                "message": "Google hesabı Antigravity CLI ile bağlı" if probe.get("ready") else "Resmî CLI girişini tamamlayın; bağlantı otomatik kontrol edilecek"}
                return
            if operation == "key": self.validate(provider, key)
            self.installer.install(provider)
            executable = resolve_cli(provider)
            if operation == "key":
                if provider == "codex":
                    login = subprocess.run(node_command(executable, ["login", "--with-api-key"]), input=key+"\n",
                                           env=cli_environment(), capture_output=True, text=True, timeout=30,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if login.returncode: raise RuntimeError("Codex anahtarı CLI hesabına bağlanamadı")
                self._save(provider, key)
            if operation == "account":
                env = dict(cli_environment())
                env.pop("GEMINI_API_KEY", None)
                env.pop("OPENAI_API_KEY", None)
                login_settings = None
                if provider == "gemini":
                    env = task_environment(env, {"method": "account"})
                    login_settings = Path(tempfile.mkdtemp(prefix="quartz-gemini-login-")) / "settings.json"
                    atomic_write_json(login_settings, {
                        "advanced": {"ignoreLocalEnv": True},
                        "security": {"auth": {"selectedType": "oauth-personal"}},
                        "ide": {"enabled": False}, "mcp": {"allowed": []}, "tools": {"core": []},
                    })
                    env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(login_settings)
                with _FILE_LOCK:
                    self._write_connection_metadata(provider, {
                        "method": "account",
                        "backend": provider,
                        "selected_at": time.time(),
                    })
                try:
                    process = subprocess.Popen(node_command(executable, ["login"] if provider == "codex" else []),
                                               env=env, cwd=str(self.base),
                                               creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
                except Exception:
                    if login_settings is not None:
                        self._cleanup_login_settings(None, login_settings)
                    raise
                if login_settings is not None:
                    threading.Thread(target=self._cleanup_login_settings, args=(process, login_settings),
                                     daemon=True, name="quartz-login-cleanup").start()
                self.login_processes[provider] = process
                message = "Açılan resmî CLI girişini tamamlayın; bağlantı otomatik kontrol edilecek."
            else:
                message = "Bağlantı hazır" if operation == "key" else "CLI kuruldu; hesabınızı veya anahtarınızı bağlayabilirsiniz"
            with self.lock:
                self._cached = None
                self.job = {"state": "done", "provider": provider, "message": message}
        except Exception as exc:
            # Never return provider stdout/stderr or submitted credentials to UI.
            message = str(exc).replace(key, "[gizli]") if key else str(exc)
            with self.lock: self.job = {"state": "error", "provider": provider, "message": message[:500]}
