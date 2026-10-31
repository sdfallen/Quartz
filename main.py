"""
main.py  —  Quartz Backend
"""

import os
import sys
import platform
import threading
import time
import socket
import json
import signal
import uuid
from pathlib import Path

from logger import get_logger, request_context
def GitHubAssistant(*args, **kwargs):
    from assistant import GitHubAssistant as _GitHubAssistant
    return _GitHubAssistant(*args, **kwargs)
from core.multi_agent_service import MultiAgentService
from core.agent_chat import AgentChatService
from core.local_ipc import authorized
from config import (
    ASSISTANT_NAME,
    AUTO_START,
    BASE_DIR,
)

log = get_logger(__name__)

IPC_HOST = "127.0.0.1"
IPC_PORT = 55_123
BUFFER   = 1024 * 64


def _register_startup_windows() -> None:
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    if getattr(sys, "frozen", False):
        cmd = f'"{sys.executable}"'
    else:
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        launcher = os.path.join(BASE_DIR, "launcher.pyw")
        cmd = f'"{pythonw}" "{launcher}"'
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path,
            0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(
                key, ASSISTANT_NAME, 0, winreg.REG_SZ, cmd
            )
        log.info("Registered in Windows startup")
    except Exception as exc:
        log.warning("Could not register startup: %s", exc)


def _register_startup_linux() -> None:
    autostart_dir = Path.home() / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)
    desktop  = autostart_dir / "quartz_assistant.desktop"
    launcher = os.path.join(BASE_DIR, "launcher.pyw")
    desktop.write_text(
        f"[Desktop Entry]\nType=Application\n"
        f"Name={ASSISTANT_NAME}\n"
        f"Exec={sys.executable} {launcher}\n"
        f"Hidden=false\nNoDisplay=false\n"
        f"X-GNOME-Autostart-enabled=true\n"
    )
    log.info("Registered in Linux autostart")


def _register_startup_mac() -> None:
    plist_dir  = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_file = plist_dir / "com.quartz.assistant.plist"
    launcher   = os.path.join(BASE_DIR, "launcher.pyw")
    plist_file.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.quartz.assistant</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{launcher}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict>
</plist>"""
    )
    log.info("Registered in macOS LaunchAgent")


def register_startup() -> None:
    s = platform.system()
    if s == "Windows":
        _register_startup_windows()
    elif s == "Linux":
        _register_startup_linux()
    elif s == "Darwin":
        _register_startup_mac()


class IPCServer:

    _diagnostics_creation_lock = threading.Lock()

    def __init__(self, assistant=None):
        self._assistant_lock = threading.Lock()
        self._assistant_instance = assistant
        self._server    = None
        self._running   = False
        self._started_at = time.time()
        self._agent_center = None
        self._agent_center_lock = threading.Lock()
        self._agent_chat = None
        self._agent_chat_lock = threading.Lock()
        self._diagnostics = None

    def _get_diagnostics(self):
        with self._diagnostics_creation_lock:
            if getattr(self, '_diagnostics', None) is None:
                from core.self_diagnostics import SelfDiagnosticsService
                self._diagnostics = SelfDiagnosticsService()
            return self._diagnostics

    @property
    def _assistant(self):
        inst = getattr(self, "_assistant_instance", None)
        if inst is None:
            lock = getattr(self, "_assistant_lock", None)
            if lock is None:
                self._assistant_lock = lock = threading.Lock()
            with lock:
                inst = getattr(self, "_assistant_instance", None)
                if inst is None:
                    inst = GitHubAssistant()
                    self._assistant_instance = inst
        return inst

    @_assistant.setter
    def _assistant(self, value):
        self._assistant_instance = value

    @staticmethod
    def _lightweight_health_status() -> dict:
        from config import get_llm_provider
        provider = get_llm_provider()
        configured = bool(provider.get("api_key"))
        status_str = "configured" if configured else "unconfigured"
        snap = {
            "provider": provider.get("name", "nvidia"),
            "model": provider.get("model", ""),
            "configured": configured,
            "status": status_str,
            "last_latency_seconds": None,
            "last_error": None,
            "checked_at": None,
        }
        return {
            "llm": {
                "status": status_str,
                "configured": configured,
                "provider": snap["provider"],
                "model": snap["model"],
            },
            "provider_manager": snap,
            "memory": {"status": "ok"},
            "vision": {"status": "ok"},
            "mcp": {"status": "ok"},
            "history_messages": 0,
            "pending_confirmation": None,
            "safe_mode": False,
            "operation": {"active": None, "workflows": []},
            "screen_advisor": {"enabled": False, "mode": "active-task-only"},
            "tool_sources": {},
        }

    def _get_agent_center(self) -> MultiAgentService:
        if self._agent_center is None:
            with self._agent_center_lock:
                if self._agent_center is None:
                    self._agent_center = MultiAgentService(project_store=Path(BASE_DIR) / 'quartz_projects.json')
        return self._agent_center

    def _get_agent_chat(self) -> AgentChatService:
        if self._agent_chat is None:
            with self._agent_chat_lock:
                if self._agent_chat is None:
                    center = self._get_agent_center()
                    store_path = Path(BASE_DIR) / 'quartz_conversations.json'
                    self._agent_chat = AgentChatService(center, store_path)
        return self._agent_chat

    def start(self):
        self._server = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((IPC_HOST, IPC_PORT))
        self._server.listen(5)
        self._running = True
        log.info("IPC server listening on %s:%d",
                 IPC_HOST, IPC_PORT)

        while self._running:
            try:
                self._server.settimeout(1.0)
                conn, addr = self._server.accept()
                threading.Thread(
                    target=self._handle,
                    args=(conn, addr),
                    daemon=True,
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def stop(self):
        self._running = False
        if getattr(self, '_diagnostics', None) is not None:
            self._diagnostics.shutdown()
        if self._agent_chat is not None:
            self._agent_chat.close()
        if self._agent_center is not None:
            self._agent_center.shutdown()
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        log.info("IPC server stopped")

    def _handle(self, conn, addr):
        try:
            try:
                raw = b""
                conn.settimeout(15)
                while True:
                    chunk = conn.recv(BUFFER)
                    if not chunk:
                        break
                    raw += chunk
                    if len(raw) > 1024 * 1024:
                        raise ValueError("IPC request too large")
                    if raw.endswith(b"\n"):
                        break
                if not raw:
                    return
                request  = json.loads(raw.decode().strip())
                response = self._dispatch(request)
            except json.JSONDecodeError as exc:
                response = {
                    "status": "error",
                    "data": f"Invalid JSON: {exc}",
                }
            except Exception as exc:
                log.exception("IPC error")
                response = {"status": "error", "data": str(exc)}
            try:
                conn.sendall(
                    (json.dumps(response) + "\n").encode())
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _dispatch(self, req: dict) -> dict:
        if not isinstance(req, dict) or not authorized(req.get("auth")):
            return {"status": "error", "data": "Unauthorized local IPC request"}
        request_id = str(req.get("request_id") or uuid.uuid4().hex[:12])
        with request_context(request_id):
            log.info("IPC action=%s", req.get("action", ""))
            response = self._dispatch_action(req)
        response["request_id"] = request_id
        return response

    def _dispatch_action(self, req: dict) -> dict:
        action = req.get("action", "")

        # Desktop grants are GUI-local and cannot be requested via this socket,
        # even by an authenticated legacy client.
        if str(action).startswith(("desktop_", "desktop_operator_", "coordination_")):
            return {"status": "error", "data": "Desktop control requires a GUI-local task grant"}

        if action in {'diagnostics_start', 'diagnostics_status', 'diagnostics_cancel'}:
            data = req.get('data')
            if data is None:
                data = {}
            permitted = {'include_rea'} if action == 'diagnostics_start' else {'job_id'}
            if not isinstance(data, dict) or set(data) - permitted:
                return {'status': 'error', 'data': 'Geçersiz teşhis parametresi; dış hedef veya komut kabul edilmez'}
            try:
                service = self._get_diagnostics()
                if action == 'diagnostics_start':
                    result = service.start(include_rea=data.get('include_rea', True))
                elif action == 'diagnostics_cancel':
                    result = service.cancel(data.get('job_id'))
                else:
                    identity = data.get('job_id')
                    if identity is not None and not isinstance(identity, str):
                        raise ValueError('Geçersiz teşhis kimliği')
                    result = service.status(identity)
                return {'status': 'ok', 'data': result}
            except ValueError as exc:
                return {'status': 'error', 'data': str(exc)}

        if action == "notion_status":
            data = req.get("data") or {}
            return {"status": "ok", "data": self._get_agent_center().notion.connection_status(force=data.get("force") is True)}

        if action == "onboarding_refresh":
            from core.codex_runtime import CodexRuntime
            from core.gemini_runtime import google_runtime
            chat = self._get_agent_chat()
            service = chat.agent_service
            if (chat.status().get("active_turn") or {}).get("status") in {"running", "cancelling"}:
                return {"status": "error", "data": "Devam eden görevi bitirdikten sonra yeniden bağlanın"}
            service.codex = CodexRuntime()
            previous_backend = getattr(service.antigravity, "backend", "agy")
            try:
                service.antigravity = google_runtime()
                service._antigravity_error = ""
            except FileNotFoundError:
                service.antigravity = None
            current = chat.store.get_active()
            session = str((current.get("sessions") or {}).get("antigravity") or "")
            if getattr(service.antigravity, "backend", "agy") == "gemini" and (previous_backend != "gemini" or not session.startswith("gemini:")):
                chat.store.set_agent_session(current["id"], "antigravity", None)
                chat.store.update_agent_model(current["id"], "antigravity", model="auto", effort="medium")
            elif getattr(service.antigravity, "backend", "agy") == "agy" and (previous_backend == "gemini" or session.startswith("gemini:") or ((current.get("models") or {}).get("antigravity") or {}).get("model") == "auto"):
                from core.antigravity_runtime import AntigravityRuntime
                chat.store.set_agent_session(current["id"], "antigravity", None)
                chat.store.update_agent_model(current["id"], "antigravity", model=AntigravityRuntime.DEFAULT_MODEL, effort=AntigravityRuntime.DEFAULT_EFFORT)
            service._probe_cache = (0.0, None)
            service._antigravity_probe_cache = (0.0, None)
            return {"status": "ok", "data": {"refreshed": True}}

        if action == "chat_status":
            return {"status": "ok", "data": self._get_agent_chat().status()}

        if action == 'chat_prepare_resume':
            data = req.get('data') or {}
            return {'status':'ok', 'data':self._get_agent_chat().prepare_resume(data.get('conversation_id'), data.get('message_id'))}

        if action == 'writer_recovery_inspect':
            return {'status':'ok', 'data':self._get_agent_center().inspect_writer_recovery((req.get('data') or {}).get('claim_id'))}

        if action == 'writer_recovery_status':
            return {'status':'ok', 'data':self._get_agent_center().writer_recovery_status(refresh=True)}

        if action == 'writer_recovery_acknowledge':
            data = req.get('data') or {}
            return {'status':'ok', 'data':self._get_agent_center().acknowledge_writer_recovery(
                data.get('claim_id'), confirmed=data.get('confirmed') is True,
                external_review=data.get('external_review') is True)}

        if action == "chat_coordination_message":
            data = req.get("data") or {}
            return {"status":"ok", "data":self._get_agent_chat().coordination_message(
                data.get("conversation_id"), data.get("sender"), data.get("content"), data.get("metadata"))}

        if action == "chat_response_detail":
            level = (req.get("data") or {}).get("level")
            return {"status": "ok", "data": self._get_agent_chat().set_response_detail(level)}

        if action == "project_add":
            data = req.get("data", {}) or {}
            project = self._get_agent_center().add_project(data.get("path"), data.get("name"))
            conversation = self._get_agent_chat().switch_project(project["id"])
            return {"status": "ok", "data": {"project": project, "conversation": conversation}}

        if action == "project_select":
            data = req.get("data", {}) or {}
            conversation = self._get_agent_chat().switch_project(str(data.get("project_id") or ""))
            return {"status": "ok", "data": conversation}

        if action == "chat_new":
            data = req.get("data", {}) or {}
            res = self._get_agent_chat().new_conversation(
                title=str(data.get("title", "Yeni Sohbet")),
                agent=str(data.get("agent", "antigravity")),
                project_id=data.get("project_id")
            )
            return {"status": "ok", "data": res}

        if action == "chat_select":
            data = req.get("data", {}) or {}
            cid = str(data.get("conversation_id", ""))
            return {"status": "ok", "data": self._get_agent_chat().select_conversation(cid)}

        if action == "chat_delete":
            data = req.get("data", {}) or {}
            cid = str(data.get("conversation_id", ""))
            return {"status": "ok", "data": self._get_agent_chat().delete_conversation(
                cid, confirmed=data.get("confirmed") is True)}

        if action == "chat_delete_project":
            data = req.get("data", {}) or {}
            return {"status": "ok", "data": self._get_agent_chat().delete_project_conversations(
                str(data.get("project_id") or ""), data.get("conversation_ids"),
                confirmed=data.get("confirmed") is True)}

        if action == "chat_set_agent":
            data = req.get("data", {}) or {}
            cid = str(data.get("conversation_id", ""))
            agent = str(data.get("agent", "antigravity"))
            self._get_agent_chat().set_agent(cid, agent)
            return {"status": "ok", "data": "Updated agent"}

        if action == "chat_set_model":
            data = req.get("data", {}) or {}
            cid = str(data.get("conversation_id", "")).strip() or None
            agent = str(data.get("agent", "antigravity"))
            model = data.get("model")
            effort = data.get("effort")
            res = self._get_agent_chat().set_agent_model(cid, agent, model=model, effort=effort)
            return {"status": "ok", "data": res}

        if action == "chat_models":
            force = bool((req.get("data", {}) or {}).get("force", False))
            return {"status": "ok", "data": self._get_agent_center().list_models(force=force)}

        if action == "chat_set_project":
            data = req.get("data", {}) or {}
            cid = str(data.get("conversation_id", ""))
            pid = data.get("project_id")
            self._get_agent_chat().set_project(cid, pid)
            return {"status": "ok", "data": "Updated project"}

        if action == "chat_send":
            data = req.get("data", {}) or {}
            msg = str(data.get("message", "")).strip()
            if not msg:
                return {"status": "error", "data": "Mesaj boş olamaz"}
            level = str(data.get("permission_level") or ("project" if data.get("write") else "read-only"))
            if level not in {"read-only", "project", "full"}:
                raise ValueError("Geçersiz işlem yetkisi")
            is_write = level in {"project", "full"}
            confirmed = data.get("confirm_write") is True
            if is_write and not confirmed:
                raise PermissionError("Yazma yetkisi için açık kullanıcı onayı gerekli.")
            res = self._get_agent_chat().send_message(
                msg,
                agent=data.get("agent"),
                conversation_id=data.get("conversation_id"),
                write=is_write,
                confirm_write=confirmed,
                full_access=level == "full",
                requested_permission_level=data.get('requested_permission_level') or level,
            )
            return {"status": "ok", "data": res}

        if action == "chat_continue":
            data = req.get("data", {}) or {}
            cid = str(data.get("conversation_id", "")).strip() or None
            res = self._get_agent_chat().continue_discussion(conversation_id=cid)
            return {"status": "ok", "data": res}

        if action == "chat_poll":
            return {"status": "ok", "data": self._get_agent_chat().poll_active()}

        if action == "chat_cancel":
            return {"status": "ok", "data": self._get_agent_chat().cancel_active()}

        if action == "ping":
            return {"status": "ok", "data": "pong"}

        if action == "health":
            inst = getattr(self, "_assistant_instance", None)
            components = inst.health_status() if inst is not None else self._lightweight_health_status()
            return {
                "status": "ok",
                "data": {
                    "backend": "ok",
                    "uptime_seconds": round(time.time() - self._started_at, 1),
                    "pid": os.getpid(),
                    "python": sys.version.split()[0],
                    "components": components,
                },
            }

        if action == "provider_probe":
            return {"status": "ok", "data": self._assistant.probe_provider()}

        if action == "agent_center_status":
            data = req.get("data", {}) or {}
            return {
                "status": "ok",
                "data": self._get_agent_center().status(data.get("project_id")),
            }

        if action == "agent_center_dispatch":
            data = req.get("data", {}) or {}
            prompt = str(data.get("prompt", "")).strip()
            if not prompt:
                return {"status": "error", "data": "Görev açıklaması boş olamaz"}
            level = str(data.get("permission_level") or ("project" if data.get("write") else "read-only"))
            if level not in {"read-only", "project", "full"}:
                raise ValueError("Geçersiz işlem yetkisi")
            if level == "full":
                raise PermissionError("Tam Yetki için kritik eylem onay köprüsü henüz hazır değil.")
            provider = str(data.get("provider", "codex")).strip().lower()
            selections = data.get("models")
            if selections is None:
                selections = self._get_agent_chat().get_model_selection(
                    str(data.get("conversation_id") or "").strip() or None)
            center = self._get_agent_center()
            if provider in {"collaboration", "both", "codex-antigravity"}:
                model_kwargs = {"models": center.validate_model_selections(selections)}
            else:
                agent = "antigravity" if provider in {"antigravity", "agy"} else "codex"
                model_kwargs = center.validate_model_selections(selections, agents=(agent,))[agent]
            result = self._get_agent_center().dispatch(
                provider,
                prompt,
                title=str(data.get("title", "")).strip() or None,
                project_id=data.get("project_id"),
                write=level == "project",
                confirm_write=data.get("confirm_write") is True,
                **model_kwargs,
            )
            return {"status": "ok", "data": result}

        if action == "agent_center_cancel":
            run_id = str((req.get("data", {}) or {}).get("run_id", ""))
            return {
                "status": "ok",
                "data": self._get_agent_center().cancel(run_id),
            }

        if action == "chat":
            msg = req.get("data", "").strip()
            if not msg:
                return {
                    "status": "error",
                    "data": "Empty message",
                }
            answer = self._assistant.chat(msg)
            return {
                "status": "ok",
                "data": answer,
                "ui_events": getattr(
                    self._assistant, "drain_ui_events", lambda: [])(),
            }

        if action == "cancel_request":
            self._assistant.cancel_current()
            return {"status": "ok", "data": "Cancellation requested"}

        if action == "safe_mode":
            enabled = bool(req.get("data", {}).get("enabled"))
            return {"status": "ok", "data": {
                "enabled": self._assistant.set_safe_mode(enabled)}}

        if action == "screen_advisor":
            enabled = bool(req.get("data", {}).get("enabled"))
            return {"status": "ok", "data": {
                "enabled": self._assistant.set_screen_advisor(enabled)}}

        if action == "ui_events":
            inst = getattr(self, "_assistant_instance", None)
            return {"status": "ok", "data": inst.drain_ui_events() if inst is not None else []}

        if action == "configure_api":
            data = req.get("data", {})
            result = self._assistant.configure_api(
                str(data.get("provider", "nvidia")),
                str(data.get("api_key", "")))
            return {"status": "ok", "data": result}

        if action == "mobile_access":
            if _mobile_gateway is None:
                return {"status": "error", "data": "Mobil servis hazır değil"}
            return {"status": "ok", "data": _mobile_gateway.access_info()}

        if action == "tool_permissions":
            inst = getattr(self, "_assistant_instance", None)
            if inst is not None:
                return {"status": "ok", "data": inst.tool_permissions()}
            from core.tool_registry import get_tool_registry
            return {"status": "ok", "data": get_tool_registry().permissions()}

        if action == "set_tool_source":
            data = req.get("data", {})
            self._assistant.set_tool_source_enabled(
                str(data.get("source", "")), bool(data.get("enabled")))
            return {"status": "ok", "data": self._assistant.tool_permissions()}

        if action == "tasks":
            inst = getattr(self, "_assistant_instance", None)
            return {"status": "ok", "data": inst.list_tasks() if inst is not None else []}

        if action == "cancel_task":
            task_id = str(req.get("data", {}).get("task_id", ""))
            return {"status": "ok", "data": self._assistant.cancel_task(task_id)}

        if action == "clear_history":
            self._assistant.clear_history()
            return {"status": "ok", "data": "Cleared"}

        if action == "get_history":
            return {
                "status": "ok",
                "data": self._assistant.get_history(),
            }

        if action == "shutdown":
            threading.Thread(
                target=self._shutdown, daemon=True).start()
            return {"status": "ok", "data": "Shutting down"}

        return {
            "status": "error",
            "data": f"Unknown action: {action!r}",
        }

    @staticmethod
    def _shutdown():
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)


_ipc_server = None
_mobile_gateway = None


def _handle_signal(signum, _frame):
    log.info("Signal %d — shutting down", signum)
    if _ipc_server:
        _ipc_server.stop()
    sys.exit(0)


def main(register_signals=True):
    global _ipc_server, _mobile_gateway

    log.info("=" * 60)
    log.info("  %s  starting", ASSISTANT_NAME)
    log.info("  Python %s  |  PID %d",
             sys.version.split()[0], os.getpid())
    log.info("=" * 60)

    # Packaged installs let Setup own the user's startup preference.
    if AUTO_START and not getattr(sys, "frozen", False):
        register_startup()

    if register_signals:
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT,  _handle_signal)

    from core.low_spec_optimizer import LazyClientProxy
    _ipc_server = IPCServer(None)
    lazy_assistant = LazyClientProxy(lambda: _ipc_server._assistant)
    try:
        from mobile_server import MobileGateway
        _mobile_gateway = MobileGateway(lazy_assistant)
        threading.Thread(target=_mobile_gateway.start,
                         name="quartz-mobile", daemon=True).start()
    except Exception as exc:
        log.warning("Mobile gateway unavailable: %s", exc)

    try:
        _ipc_server.start()
    except KeyboardInterrupt:
        pass
    finally:
        _ipc_server.stop()
        log.info("%s stopped", ASSISTANT_NAME)


if __name__ == "__main__":
    main()
