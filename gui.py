"""
gui.py  —  Quartz  |  Designed by Ali Mehdi
Modern glass/HUD interface rendered with pywebview
(HTML/CSS/JS) instead of tkinter. Replaces the old
radar/hex/core canvas UI with a single breathing
"core" indicator and a clean glassmorphism layout.
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import webview
from core.local_ipc import request_token
from ui.document import BRAND_MARK, asset_root, build_document
from ui.shell import SHELL_MARKUP
from ui.app_js import SCRIPT_DOCUMENT

# ── IPC ────────────────────────────────────────────────────────────────────
IPC_HOST = "127.0.0.1"
IPC_PORT = 55_123


def ipc_send(action: str, data=None) -> dict:
    req = {"action": action, "auth": request_token()}
    if data is not None:
        req["data"] = data
    try:
        long_action = action == "chat" or action.startswith("agent_center_")
        with socket.create_connection(
                (IPC_HOST, IPC_PORT), timeout=300 if long_action else 15) as s:
            s.settimeout(300 if long_action else 15)
            s.sendall((json.dumps(req) + "\n").encode())
            raw = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                raw += chunk
                if raw.endswith(b"\n"):
                    break
        return json.loads(raw.decode().strip())
    except ConnectionRefusedError:
        return {
            "status": "error",
            "data": "Quartz bağlantısı kapalı. Uygulamayı Quartz.exe veya quartz_entry.py ile birlikte başlatın.",
        }
    except Exception as exc:
        return {"status": "error", "data": str(exc)}


# ── Quick action → chat message map (same as before) ───────────────────────
_QUICK_ACTIONS = {
    "screenshot": "Take a screenshot and save it to my Desktop",
    "sysinfo":    "Show detailed system information",
    "desktop":    "List all files on my Desktop",
    "plugins":    "list plugins",
    "update_all": "update all plugins",
    "quartz_mode": "Quartz Mode",
    "windows": "pencereleri listele",
}


# ── JS <-> Python bridge ────────────────────────────────────────────────────
class Api:
    def __init__(self):
        self._voice_instance = None
        self._voice_lock = threading.Lock()
        self._compact = False
        self._desktop_agents = None
        self._desktop_lock = threading.Lock()
        self._coordination = None
        self._coordination_lock = threading.Lock()
        self._natural = None
        self._natural_start_lock = threading.Lock()
        self._onboarding = None
        self._artifact_diagnostics = None
        self._repair = None
        self._diagnostic_tools_lock = threading.RLock()

    def _onboarding_service(self):
        if self._onboarding is None:
            from core.onboarding import OnboardingService
            self._onboarding = OnboardingService()
        return self._onboarding

    def onboarding_status(self, force=False):
        try:
            data = self._onboarding_service().status(force=force)
            # Notion remains shared memory, not an onboarding/model provider.
            return {"status": "ok", "data": data}
        except Exception:
            return {"status": "error", "data": "Bağlantı durumu okunamadı; yeniden deneyin"}

    def onboarding_begin(self, operation, provider, key=""):
        try:
            return {"status": "ok", "data": self._onboarding_service().begin(operation, provider, key)}
        except Exception as exc:
            return {"status": "error", "data": str(exc)}

    def onboarding_refresh(self):
        return ipc_send("onboarding_refresh")

    def diagnostics_start(self, include_rea: bool = True) -> dict:
        if self._artifact_diagnostics and self._artifact_diagnostics.status()['state'] == 'running':
            return {'status': 'ok', 'data': self._artifact_diagnostics.status()}
        return ipc_send("diagnostics_start", {"include_rea": include_rea})

    def diagnostics_status(self, job_id: str | None = None) -> dict:
        if self._artifact_diagnostics and job_id in self._artifact_diagnostics.jobs:
            return {"status": "ok", "data": self._artifact_diagnostics.status(job_id)}
        payload = {"job_id": job_id} if job_id not in (None, "") else {}
        return ipc_send("diagnostics_status", payload)

    def diagnostics_cancel(self, job_id: str) -> dict:
        if self._artifact_diagnostics and job_id in self._artifact_diagnostics.jobs:
            return {"status": "ok", "data": self._artifact_diagnostics.cancel(job_id)}
        return ipc_send("diagnostics_cancel", {"job_id": job_id})

    def diagnostics_select_application(self):
        """GUI-local native picker is the grant; arbitrary IPC paths stay forbidden."""
        with self._diagnostic_tools_lock:
            try:
                if self._artifact_diagnostics and self._artifact_diagnostics.status()['state'] == 'running':
                    return {'status': 'ok', 'data': self._artifact_diagnostics.status()}
                if not webview.windows:
                    raise ValueError('Pencere hazır değil')
                selected = webview.windows[0].create_file_dialog(webview.FileDialog.OPEN,
                    allow_multiple=False, file_types=('Uygulama (*.exe)',))
                if not selected:
                    return {'status': 'ok', 'data': None}
                from core.artifact_diagnostics import ArtifactDiagnosticsService
                if self._artifact_diagnostics:
                    self._artifact_diagnostics.shutdown()
                self._artifact_diagnostics = ArtifactDiagnosticsService(selected[0])
                return {'status': 'ok', 'data': self._artifact_diagnostics.start()}
            except Exception:
                return {'status': 'error', 'data': 'Seçilen dosya güvenli inceleme için açılamadı. Normal bir EXE dosyası seçin.'}

    def diagnostics_prepare_repair(self):
        with self._diagnostic_tools_lock:
            self._repair = None
            try:
                if not webview.windows:
                    raise ValueError('Pencere hazır değil')
                selected = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
                if not selected:
                    return {'status': 'ok', 'data': None}
                from core.package_repair import PackageRepair
                from core.cli_installer import app_root
                from pathlib import Path
                import os
                self._repair = PackageRepair(app_root(), Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Quartz/repair-backups')
                return {'status': 'ok', 'data': self._repair.prepare(selected[0])}
            except ValueError as exc:
                return {'status': 'error', 'data': str(exc)}
            except Exception:
                return {'status': 'error', 'data': 'Onarım referansı doğrulanamadı. Aynı sürümün sağlam, manifestli paketini seçin.'}

    def diagnostics_apply_repair(self, plan_id):
        with self._diagnostic_tools_lock:
            try:
                if not self._repair:
                    raise ValueError('Önce bir onarım planı hazırlanmalı')
                return {'status': 'ok', 'data': self._repair.apply(plan_id)}
            except ValueError as exc:
                return {'status': 'error', 'data': str(exc)}
            except Exception:
                return {'status': 'error', 'data': 'Onarım tamamlanamadı; yedekleri koruyarak yeniden inceleyin.'}

    def diagnostics_discard_repair(self):
        with self._diagnostic_tools_lock:
            self._repair = None
        return {'status': 'ok', 'data': 'Onarım planı iptal edildi.'}

    def diagnostics_learned_applications(self):
        with self._diagnostic_tools_lock:
            try:
                from core.application_knowledge import ApplicationKnowledge
                return {'status': 'ok', 'data': ApplicationKnowledge().list_learned(20)}
            except Exception:
                return {'status': 'error', 'data': 'Öğrenilen uygulama hafızası okunamadı.'}

    def natural_start(self, text, conversation_id, project_id, models, permission_level='read-only'):
        """Start reasoning/tool selection, NOT a desktop grant."""
        try:
            with self._natural_start_lock:
                state = ipc_send("chat_status")
                if state.get("status") != "ok": raise RuntimeError("Sohbet bağlantısı hazır değil")
                data = state["data"]
                if (data.get("active_turn") or {}).get("status") == "running":
                    raise RuntimeError("Önce devam eden sohbet görevini bitirin veya durdurun")
                if (data.get("active_conversation") or {}).get("id") != conversation_id:
                    raise PermissionError("Sohbet değişti; güncel sohbetten gönderin")
                project = next((p for p in data["projects"] if p["id"] == project_id), None)
                if project is None: raise ValueError("Görev için mevcut bir proje seçilmeli")
                if self._natural and self._natural.status()["active"]: raise RuntimeError("Başka bir görev sürüyor")
                if self._coordination and self._coordination.status()["active"]: raise RuntimeError("Başka bir operatör sürüyor")
                from core.natural_desktop import NaturalDesktopTask
                def emit(cid, sender, content, metadata):
                    result = ipc_send("chat_coordination_message", {"conversation_id":cid,"sender":sender,"content":content,"metadata":metadata})
                    if result.get("status") != "ok": raise RuntimeError("Görev sohbet günlüğüne yazılamadı")
                emit(conversation_id, "user", text, {})
                self._natural = NaturalDesktopTask(self._desktop_service(), emit)
                context = '\n\n'.join(str(m.get('sender') or m.get('role')) + ': ' + str(m.get('content') or '')[:1200]
                    for m in (data.get('active_conversation',{}).get('messages') or [])[-8:])[-10000:]
                task_text = text
                selected_agent = (data.get('active_conversation') or {}).get('agent')
                if selected_agent in {'codex', 'antigravity'} and not re.search(r'\b(codex|gemini|antigravity)\b', text, re.I):
                    task_text = ('Codex, ' if selected_agent == 'codex' else 'Gemini, ') + text
                result = self._natural.start(task_text, project, conversation_id, models,
                    requested_permission_level=permission_level, conversation_context=context)
                return {"status":"ok", "data":{"handled":True, "natural_started":True, "task":result}}
        except Exception as exc: return {"status":"error", "data":str(exc)}

    def natural_status(self):
        return {"status":"ok", "data":self._natural.status() if self._natural else {"active":False}}

    def natural_approve(self, request_id, confirmed=False):
        try:
            if self._natural is None: raise PermissionError("Bekleyen görev yok")
            return {"status":"ok", "data":self._natural.approve(request_id, confirmed=confirmed is True)}
        except Exception as exc: return {"status":"error", "data":str(exc)}

    def natural_deny(self, request_id):
        try:
            if self._natural is None: raise PermissionError("Bekleyen görev yok")
            return {"status":"ok", "data":self._natural.deny(request_id)}
        except Exception as exc: return {"status":"error", "data":str(exc)}

    def _coordination_service(self):
        with self._coordination_lock:
            if self._coordination is None:
                from core.chat_coordination import ChatCoordination
                def emit(cid, sender, content, metadata):
                    result = ipc_send("chat_coordination_message", {"conversation_id":cid,"sender":sender,"content":content,"metadata":metadata})
                    if result.get("status") != "ok": raise RuntimeError("Sohbet günlüğü yazılamadı")
                self._coordination = ChatCoordination(self._desktop_service(), emit)
        return self._coordination

    def coordination_route(self, text, conversation_id, project_id, models, permission_level='read-only', agent=None):
        try:
            import re
            from core.message_intent import message_intent, tools_disallowed
            from core.desktop_task_ui import desktop_intent, desktop_help
            if permission_level not in {'read-only','project','full'}: raise ValueError('Geçersiz dosya yetkisi seçimi')
            if agent == 'notion' or re.match(r'^\s*@notion\b', text, re.I):
                # A cloud-agent message cannot start REA, desktop control or
                # become an instruction to a running local operator.
                return {'status':'ok','data':{'handled':False,'intent':'conversation'}}
            message_kind = message_intent(text)
            from core.diagnostics_intent import diagnostics_intent
            diagnostic_command = diagnostics_intent(text)
            if diagnostic_command == 'artifact':
                result = self.diagnostics_select_application()
                if result.get('status') != 'ok':
                    return result
                return {'status': 'ok', 'data': {'handled': True, 'diagnostics_started': True,
                    'diagnostics': result['data'], 'user_text': text}}
            if diagnostic_command == 'repair':
                result = self.diagnostics_prepare_repair()
                if result.get('status') != 'ok':
                    return result
                return {'status': 'ok', 'data': {'handled': True, 'diagnostics_repair': True,
                    'repair_plan': result['data'], 'user_text': text}}
            if diagnostic_command == 'knowledge':
                result = self.diagnostics_learned_applications()
                if result.get('status') != 'ok':
                    return result
                return {'status': 'ok', 'data': {'handled': True, 'diagnostics_knowledge': True,
                    'learned_items': result['data'], 'user_text': text}}
            if tools_disallowed(text):
                for service in (self._natural, self._coordination):
                    if service is not None and service.status().get("active"):
                        service.stop()
            # Scope introspection is host data, not a model guessing which
            # permissions the dropdown may have granted. No native service or
            # project work is started by this query.
            if (not tools_disallowed(text) and not re.search(r'masaüst|bilgisayar|pencere|ekran',text,re.I)
                    and re.search(r'\b(?:yetkilerinizi|yetkileriniz|yetkiniz|erişiminiz|izinleriniz)\b', text, re.I)
                    and re.search(r'kontrol|nedir|neler|var mı|varmı', text, re.I)):
                reply='Aktif yetki sistemi: Tam Yetki (tüm dosya ve bilgisayar erişimi). Bu kalıcı yetki yeni görevlere uygulanır; çalışan görevin yetkisini değiştirmez. '
                if self._natural and self._natural.status().get('active'):
                    reply+='Etkin görev kapsamlı MCP araçlarıyla çalışıyor; sol üstteki "Görevi Durdur" butonuna basılmadıkça görev kesilmez. '
                else:
                    reply+='Şu an bu sorgu yeni bir ajan veya bilgisayar kontrolü başlatmadı. '
                reply+='Yapılacak işi doğrudan bu sohbete yazabilirsiniz; Codex ve Antigravity Tam Yetki ile hazırdır.'
                for sender,content in (('user',text),('quartz',reply)):
                    result=ipc_send('chat_coordination_message',{'conversation_id':conversation_id,'sender':sender,'content':content})
                    if result.get('status')!='ok': raise RuntimeError('Yetki durumu sohbete yazılamadı')
                return {'status':'ok','data':{'handled':True,'permission_status':reply}}
            if (not tools_disallowed(text) and message_kind != "conversation"
                    and (diagnostic_command == 'self' or re.search(r'\b(öz\s*teşhis\w*|özteşhis\w*|self[\s-]*diagnos\w*|kendini\s+teşhis\s+et\w*|rea\s+(?:ile\s+)?teşhis\w*)\b', text, re.I))):
                if re.search(r'\b(dur|durdur|iptal)\b', text, re.I):
                    current = self.diagnostics_status()
                    if current.get("status") != "ok":
                        return current
                    job = current.get("data") or {}
                    if job.get("state") == "running" and job.get("id"):
                        cancelled = self.diagnostics_cancel(job["id"])
                        if cancelled.get("status") != "ok":
                            return cancelled
                        return {"status": "ok", "data": {"handled": True, "diagnostics_cancelled": True, "diagnostics": cancelled.get("data"), "user_text": text}}
                    return {"status": "ok", "data": {"handled": True, "diagnostics_status": job, "user_text": text}}
                include_rea = not bool(re.search(r'\brea\s*(?:olmadan|kapalı|hariç|yok)\b', text, re.I))
                started = self.diagnostics_start(include_rea=include_rea)
                if started.get("status") != "ok":
                    return started
                return {"status": "ok", "data": {"handled": True, "diagnostics_started": True, "diagnostics": started.get("data"), "user_text": text}}
            intent = desktop_intent(text)
            if intent == "help":
                view = self.desktop_task_status()["data"]
                reply = desktop_help(view)
                for sender,content in (("user",text),("quartz",reply)):
                    result=ipc_send("chat_coordination_message",{"conversation_id":conversation_id,"sender":sender,"content":content})
                    if result.get("status") != "ok": raise RuntimeError("Sohbet bağlantısı hazır değil")
                return {"status":"ok","data":{"handled":True,"desktop_help":reply,"view":view}}
            if message_kind == "conversation":
                return {"status":"ok", "data":{"handled":False, "intent":"conversation"}}
            if self._natural and self._natural.status()["active"]:
                job = self._natural.status()["job"]
                if job["conversation_id"] != conversation_id:
                    raise PermissionError("Başka sohbette görev sürüyor; önce o görevi durdurun")
                ipc_send("chat_coordination_message", {"conversation_id":conversation_id,"sender":"user","content":text})
                if re.fullmatch(r"\s*(dur|durdur|görevi durdur|kontrolü durdur|iptal et)[.!]?\s*", text, re.I):
                    return {"status":"ok", "data":{"handled":True,"stopped":self._natural.stop()}}
                self._natural.instruct(text, conversation_id)
                return {"status":"ok", "data":{"handled":True,"instructed":True}}
            service = self._coordination
            active = service is not None and service.status()["active"]
            if active and re.fullmatch(r"\s*(dur|durdur|görevi durdur|kontrolü durdur|iptal et)[.!]?\s*", text, re.I):
                ipc_send("chat_coordination_message", {"conversation_id":conversation_id,"sender":"user","content":text})
                return {"status":"ok","data":{"handled":True,"stopped":service.stop()}}
            if not active and message_kind == 'continuation' and re.fullmatch(
                    r'\s*(devam et|devam|sürdür|dur|durdur|görevi durdur|kontrolü durdur|iptal et)[.!]?\s*',text,re.I):
                state=ipc_send('chat_status')
                if state.get('status')!='ok': raise RuntimeError('Güncel görev durumu okunamadı')
                data=state.get('data') or {}
                if (data.get('active_conversation') or {}).get('id')!=conversation_id:
                    raise PermissionError('Sohbet değişti; güncel sohbetten gönderin')
                running=(data.get('active_turn') or {}).get('status') in {'running','cancelling'}
                if running:
                    reply='Dosya/sohbet ajanı hâlâ çalışıyor. Bu mesaj yeni bir görev başlatmadı; ilerlemeyi sohbetten izleyebilirsiniz.'
                elif re.search(r'dur|iptal',text,re.I):
                    reply='Şu anda durdurulacak etkin bir görev yok.'
                else:
                    reply='Şu anda devam eden bir görev yok. Kaldığımız işi kısaca belirtin; bu sohbette yeni görev olarak sürdürelim. Önceki işlem otomatik tekrarlanmadı.'
                for sender,content in (('user',text),('quartz',reply)):
                    result=ipc_send('chat_coordination_message',{'conversation_id':conversation_id,'sender':sender,'content':content})
                    if result.get('status')!='ok': raise RuntimeError('Görev durumu sohbete yazılamadı')
                return {'status':'ok','data':{'handled':True,'continuation_status':reply}}
            from core.chat_coordination import proposed_roles
            if intent == "task":
                if active:
                    if service.status()["job"]["conversation_id"] != conversation_id:
                        raise PermissionError("Başka sohbette görev sürüyor; önce o görevi durdurun")
                    service.instruct(text)
                    return {"status":"ok","data":{"handled":True,"instructed":True}}
                return self.natural_start(text,conversation_id,project_id,models,permission_level)
            project_state=ipc_send("chat_status")
            project_data=project_state.get("data") if project_state.get("status")=="ok" else {}
            if not isinstance(project_data,dict): project_data={}
            selected_project=next((p for p in project_data.get("projects",[])
                                   if p.get("id")==project_id),None)
            if selected_project and selected_project.get("workflow")=="warband" and message_kind == "task":
                return self.natural_start(text,conversation_id,project_id,models,permission_level)
            roles = proposed_roles(text)
            if roles is None:
                if active and service.status()["job"]["conversation_id"] == conversation_id:
                    ipc_send("chat_coordination_message", {"conversation_id":conversation_id,"sender":"user","content":text})
                    service.instruct(text)
                    return {"status":"ok","data":{"handled":True,"instructed":True}}
                return {"status":"ok","data":{"handled":False,"intent":"conversation" if message_kind != "task" else "task"}}
            return self.natural_start(text,conversation_id,project_id,models,permission_level)
        except Exception as exc:
            return {"status":"error","data":str(exc)}

    def coordination_prepare(self, text, conversation_id, project_id, models):
        """A GUI task request only prepares consent; never starts an operator."""
        try:
            if self._natural and self._natural.status()["active"]:
                raise RuntimeError("Ana sohbet görevi etkin; ikinci operatör başlatılamaz")
            state = ipc_send("chat_status")
            if state.get("status") != "ok": raise RuntimeError("Sohbet bağlantısı hazır değil")
            turn=state["data"].get("active_turn") or {}
            if turn.get("status") == "running": raise RuntimeError("Önce devam eden sohbet görevini tamamlayın veya iptal edin.")
            if (state["data"].get("active_conversation") or {}).get("id") != conversation_id:
                raise PermissionError("Sohbet değişti; güncel sohbette yeni görev hazırlayın.")
            project = next((p for p in state["data"]["projects"] if p["id"] == project_id),None)
            if project is None: raise ValueError("Önce geçerli bir proje seçin; gözlemci yalnız seçilen proje logunu okuyabilir.")
            service = self._coordination_service()
            plan = service.propose(text, project, conversation_id, models,allow_defaults=True)
            result=ipc_send("chat_coordination_message", {"conversation_id":conversation_id,"sender":"user","content":text})
            if result.get("status") != "ok":
                service.cancel_plan(plan["id"])
                raise RuntimeError("Görev sohbete kaydedilemedi; onay hazırlanmadı.")
            return {"status":"ok","data":{"handled":True,"plan":plan,"windows":plan["windows"]}}
        except Exception as exc:
            return {"status":"error","data":str(exc)}

    def desktop_task_status(self):
        from core.desktop_task_ui import desktop_view
        try:
            if self._natural and self._natural.job:
                state = self._natural.status()
                if state["active"]:
                    job, pending = state["job"], state.get("pending")
                    view = desktop_view(state, desktop=state["operator"])
                    view["stop_ref"] = "natural:" + job["id"]
                    if pending:
                        view.update(code="pending", label="Uygulama izni bekleniyor", control_active=False,
                                    pending_id=pending["id"], detail=pending["reason"])
                    elif state.get('stopping'):
                        view.update(code='released',label='Görev durduruluyor',detail='Yeni girdi kapalı; başlamış çağrı ve temizlik tamamlanıyor.')
                    elif not view["control_active"]:
                        view.update(code="preparing", label="Ajanlar çalışıyor", detail="Henüz ekran kontrol izni verilmedi; görev araçları değerlendiriliyor.")
                    if state.get("warband") and not pending:
                        wb=state["warband"]
                        view.update(label="Warband testi sürüyor" if wb.get("input_active") else "Universal Modder görevi",
                                    control_active=bool(wb.get("input_active")),
                                    detail="Kaynak, derleme ve canlı oyun kanıtları Universal Modder üzerinden toplanıyor.")
                    return {"status":"ok", "data":view}
            service=self._coordination
            if service is not None:
                with service.lock:
                    return {"status":"ok","data":desktop_view(service.status(),desktop=service.desktop.status(),pending=service.pending)}
            desktop=self._desktop_agents.status() if self._desktop_agents is not None else None
            return {"status":"ok","data":desktop_view(desktop=desktop)}
        except Exception as exc: return {"status":"error","data":str(exc)}

    def desktop_task_stop(self, stop_ref):
        # Server checks the exact generation. A stale toolbar must not stop a
        # new operator, including the legacy single-window diagnostics path.
        try:
            if not isinstance(stop_ref,str): raise PermissionError("Güncel görev kimliği gerekli")
            kind,identity=stop_ref.split(":",1)
            if kind=="natural":
                if self._natural is None or self._natural.job["id"] != identity: raise PermissionError("Eski görev kimliği")
                return {"status":"ok", "data":self._natural.stop()}
            if kind=="coord": return self.coordination_stop(identity)
            if kind!="desktop" or self._desktop_agents is None: raise PermissionError("Etkin masaüstü görevi yok")
            service=self._desktop_agents
            with service._lock:
                if service.broker.status().get("id") != identity: raise PermissionError("Eski oturum; güncel görev değiştirilmedi")
                return {"status":"ok","data":service.stop()}
        except Exception as exc: return {"status":"error","data":str(exc)}

    def coordination_cancel_plan(self, plan_id):
        try:
            if self._coordination is None: raise PermissionError("Bekleyen görev yok")
            self._coordination.cancel_plan(plan_id)
            return {"status":"ok","data":True}
        except Exception as exc: return {"status":"error","data":str(exc)}

    def coordination_pick_log(self):
        if not webview.windows: return {"status":"error","data":"Pencere hazır değil"}
        paths = webview.windows[0].create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False, file_types=('Günlük (*.log;*.txt;*.jsonl)',))
        return {"status":"ok","data":paths[0] if paths else None}

    def coordination_pick_app(self, plan_id):
        try:
            if not webview.windows: raise RuntimeError("Pencere hazır değil")
            paths = webview.windows[0].create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False, file_types=('Uygulama (*.exe)',))
            return {"status":"ok","data":self._coordination_service().add_launch(plan_id,paths[0]) if paths else None}
        except Exception as exc: return {"status":"error","data":str(exc)}

    def coordination_approve(self, plan_id, handle, log_path, seconds, confirmed=False, agy_ack=False, launch_ids=None):
        try:
            handles = [int(h) for h in handle] if isinstance(handle,list) else int(handle)
            return {"status":"ok","data":self._coordination_service().approve(plan_id, handles, log_path, int(seconds), confirmed=confirmed is True, agy_ack=agy_ack is True, launch_ids=launch_ids)}
        except Exception as exc: return {"status":"error","data":str(exc)}

    def coordination_status(self):
        return {"status":"ok","data":self._coordination_service().status()}

    def coordination_stop(self, plan_id=None):
        service=self._coordination_service()
        with service.lock:
            if plan_id is not None and (not service.job or service.job["id"]!=plan_id):
                return {"status":"error","data":"Bu kart eski bir göreve ait; etkin görev değiştirilmedi."}
            return {"status":"ok","data":service.stop()}

    def _desktop_service(self):
        with self._desktop_lock:
            if self._desktop_agents is None:
                from core.desktop_agents import DesktopAgentService
                self._desktop_agents = DesktopAgentService()
                self._desktop_agents.broker.admission_guard = self._writer_recovery_input_guard
            return self._desktop_agents

    def _writer_recovery_input_guard(self):
        result = ipc_send('writer_recovery_status')
        if result.get('status') != 'ok' or not isinstance(result.get('data'), dict):
            raise PermissionError('Yazıcı kurtarma durumu doğrulanmadan yeni masaüstü yetkisi verilemez.')
        if result['data'].get('blocked'):
            raise PermissionError('Önce kesilen yazıcı görevini inceleyin; yeni masaüstü yetkisi açılmadı.')

    def desktop_operator_windows(self):
        try:
            return {"status": "ok", "data": self._desktop_service().windows()}
        except Exception as exc:
            return {"status": "error", "data": str(exc)}

    def desktop_operator_start(self, provider, handle, prompt, model, effort, confirmed=False):
        try:
            if self._natural and self._natural.status()["active"]:
                raise RuntimeError("Ana sohbet görevi etkin; ikinci operatör başlatılamaz")
            return {"status": "ok", "data": self._desktop_service().start(
                provider, int(handle), prompt, model, effort, confirmed=confirmed is True)}
        except Exception as exc:
            return {"status": "error", "data": str(exc)}

    def desktop_operator_status(self):
        return {"status": "ok", "data": self._desktop_service().status()}

    def desktop_operator_stop(self):
        return {"status": "ok", "data": self._desktop_service().stop()}

    @property
    def _voice(self):
        """Load microphone/TTS only after the window is already visible."""
        if self._voice_instance is None:
            with self._voice_lock:
                if self._voice_instance is None:
                    from voice_system import VoiceSystem
                    self._voice_instance = VoiceSystem()
        return self._voice_instance

    def send_chat(self, message: str) -> dict:
        resp = ipc_send("chat", message)
        return resp

    def quick_action(self, key: str) -> dict:
        msg = _QUICK_ACTIONS.get(key)
        if not msg:
            return {"status": "error", "data": f"Unknown action: {key}"}
        return ipc_send("chat", msg)

    def clear_history(self) -> dict:
        return ipc_send("clear_history")

    def ping(self) -> dict:
        r = ipc_send("health")
        return {
            "online": r.get("status") == "ok",
            "health": r.get("data", {}),
            "request_id": r.get("request_id"),
        }

    def health(self) -> dict:
        return ipc_send("health")

    def provider_probe(self) -> dict:
        return ipc_send("provider_probe")

    def cancel_request(self) -> dict:
        return ipc_send("cancel_request")

    def ui_events(self) -> dict:
        return ipc_send("ui_events")

    def set_safe_mode(self, enabled: bool) -> dict:
        return ipc_send("safe_mode", {"enabled": enabled})

    def set_screen_advisor(self, enabled: bool) -> dict:
        return ipc_send("screen_advisor", {"enabled": enabled})

    def configure_api(self, provider: str, api_key: str) -> dict:
        return ipc_send("configure_api", {
            "provider": provider, "api_key": api_key})

    def mobile_access(self) -> dict:
        return ipc_send("mobile_access")

    def copy_mobile_token(self) -> dict:
        """Copy the active gateway token without exposing it to another process."""
        response = ipc_send("mobile_access")
        if response.get("status") != "ok":
            return {"status": "error", "data": response.get("data", "Anahtar alınamadı")}
        token = str(response.get("data", {}).get("token", "")).strip()
        if not token:
            return {"status": "error", "data": "Cihaz anahtarı bulunamadı"}
        try:
            subprocess.run(
                ["clip.exe"], input=token, text=True, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return {"status": "ok", "data": "Cihaz anahtarı kopyalandı"}
        except Exception as exc:
            return {"status": "error", "data": f"Anahtar kopyalanamadı: {exc}"}

    def tool_permissions(self) -> dict:
        return ipc_send("tool_permissions")

    def set_tool_source(self, source: str, enabled: bool) -> dict:
        return ipc_send("set_tool_source", {"source": source, "enabled": enabled})

    def tasks(self) -> dict:
        return ipc_send("tasks")

    def cancel_task(self, task_id: str) -> dict:
        return ipc_send("cancel_task", {"task_id": task_id})

    def agent_center_status(self, project_id: str = "") -> dict:
        return ipc_send("agent_center_status", {"project_id": project_id or None})

    def agent_center_dispatch(self, prompt: str, title: str = "",
                              project_id: str = "", write: bool = False,
                              confirm_write: bool = False,
                              provider: str = "codex", models=None,
                              conversation_id: str = "") -> dict:
        return ipc_send("agent_center_dispatch", {
            "prompt": prompt, "title": title,
            "project_id": project_id or None,
            "write": bool(write), "confirm_write": bool(confirm_write),
            "provider": provider or "codex",
            "models": models, "conversation_id": conversation_id or None,
        })

    def agent_center_cancel(self, run_id: str) -> dict:
        return ipc_send("agent_center_cancel", {"run_id": run_id})

    # ── Agent Chat API ──────────────────────────────────────
    def chat_status(self) -> dict:
        return ipc_send("chat_status")

    def chat_prepare_resume(self, conversation_id, message_id):
        try:
            self._chat_delete_guard()
            return ipc_send('chat_prepare_resume', {'conversation_id':conversation_id, 'message_id':message_id})
        except Exception as exc: return {'status':'error','data':str(exc)}

    def writer_recovery_inspect(self, claim_id):
        return ipc_send('writer_recovery_inspect', {'claim_id':claim_id})

    def writer_recovery_acknowledge(self, claim_id, confirmed=False, external_review=False):
        return ipc_send('writer_recovery_acknowledge', {'claim_id':claim_id,
            'confirmed':confirmed is True, 'external_review':external_review is True})

    def chat_response_detail(self, level: str) -> dict:
        return ipc_send("chat_response_detail", {"level": level})

    def project_pick_add(self) -> dict:
        window = webview.windows[0] if webview.windows else None
        if window is None:
            return {"status": "error", "data": "Quartz penceresi hazır değil"}
        folders = window.create_file_dialog(webview.FileDialog.FOLDER)
        if not folders:
            return {"status": "cancelled", "data": None}
        return ipc_send("project_add", {"path": folders[0]})

    def project_select(self, project_id: str) -> dict:
        return ipc_send("project_select", {"project_id": project_id})

    def chat_new(self, title: str = "Yeni Sohbet", agent: str = "antigravity", project_id: str = "") -> dict:
        return ipc_send("chat_new", {"title": title, "agent": agent, "project_id": project_id or None})

    def chat_select(self, conversation_id: str) -> dict:
        return ipc_send("chat_select", {"conversation_id": conversation_id})

    def _chat_delete_guard(self):
        for service in (self._natural, self._coordination):
            if service is not None and service.status().get("active"):
                raise RuntimeError("Önce çalışan bilgisayar görevini bitirin veya durdurun.")
        if self._desktop_agents is not None and self._desktop_agents.status().get("session", {}).get("active"):
            raise RuntimeError("Önce çalışan masaüstü oturumunu durdurun.")

    def chat_delete(self, conversation_id: str, confirmed: bool = False) -> dict:
        try:
            with self._natural_start_lock:
                self._chat_delete_guard()
                return ipc_send("chat_delete", {"conversation_id": conversation_id, "confirmed": confirmed is True})
        except Exception as exc:
            return {"status": "error", "data": str(exc)}

    def chat_delete_project(self, project_id: str, conversation_ids, confirmed: bool = False) -> dict:
        try:
            with self._natural_start_lock:
                self._chat_delete_guard()
                return ipc_send("chat_delete_project", {"project_id": project_id,
                    "conversation_ids": conversation_ids, "confirmed": confirmed is True})
        except Exception as exc:
            return {"status": "error", "data": str(exc)}

    def chat_set_agent(self, conversation_id: str, agent: str) -> dict:
        return ipc_send("chat_set_agent", {"conversation_id": conversation_id, "agent": agent})

    def chat_set_model(self, conversation_id: str, agent: str, model: str = "", effort: str = "") -> dict:
        return ipc_send("chat_set_model", {
            "conversation_id": conversation_id or None,
            "agent": agent,
            "model": model or None,
            "effort": effort or None,
        })

    def chat_models(self, force: bool = False) -> dict:
        return ipc_send("chat_models", {"force": bool(force)})

    def chat_continue(self, conversation_id: str = "") -> dict:
        return ipc_send("chat_continue", {"conversation_id": conversation_id or None})

    def chat_set_project(self, conversation_id: str, project_id: str = "") -> dict:
        return ipc_send("chat_set_project", {"conversation_id": conversation_id, "project_id": project_id or None})

    def chat_send(self, message: str, agent: str = "", conversation_id: str = "",
                  write: bool = False, confirm_write: bool = False,
                  permission_level: str = "read-only", requested_permission_level: str | None = None) -> dict:
        import re
        if agent == "notion" or re.match(r"^\s*@notion\b", message, re.I):
            return {"status": "error", "data": "Notion ajanı kaldırıldı. Codex veya Antigravity seçin; eski sohbetler korunur."}
        return ipc_send("chat_send", {
            "message": message, "agent": agent or None,
            "conversation_id": conversation_id or None,
            "write": bool(write), "confirm_write": bool(confirm_write),
            "permission_level": permission_level or ("project" if write else "read-only"),
            "requested_permission_level": requested_permission_level or permission_level,
        })

    def chat_poll(self) -> dict:
        return ipc_send("chat_poll")

    def chat_cancel(self) -> dict:
        return ipc_send("chat_cancel")

    def notion_tool_decide(self, pending_id, conversation_id, accept, confirmed=False) -> dict:
        """In-chat Notion test-file permission. The backend binds it to the live turn."""
        return ipc_send("notion_tool_decide", {"pending_id": str(pending_id or ""),
                                               "conversation_id": str(conversation_id or ""),
                                               "accept": accept is True, "confirmed": confirmed is True})

    def get_stats(self) -> dict:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            try:
                disk_path = "C:\\" if sys.platform == "win32" else "/"
                disk = psutil.disk_usage(disk_path)
                disk_pct = disk.percent
            except Exception:
                disk_pct = 0
            from core.low_spec_optimizer import (
                cleanup_stale_cli_artifacts,
                detect_hardware_profile,
                trim_working_set,
            )
            prof = detect_hardware_profile()
            if not getattr(self, "_startup_housekeeping_done", False):
                self._startup_housekeeping_done = True
                threading.Thread(
                    target=lambda: (
                        time.sleep(6.0),
                        trim_working_set(force=True, include_children=True),
                        cleanup_stale_cli_artifacts(),
                    ),
                    daemon=True,
                    name="quartz-low-spec-housekeeping",
                ).start()
            elif prof["low_spec_mode"]:
                trim_working_set(force=False, min_interval_sec=45.0, include_children=True)
            return {
                "cpu": round(cpu, 1),
                "mem": round(mem.percent, 1),
                "disk": round(disk_pct, 1),
                "low_spec": prof["low_spec_mode"],
            }
        except Exception:
            return {"cpu": 0, "mem": 0, "disk": 0}

    def minimize(self):
        if webview.windows:
            webview.windows[0].minimize()

    def set_compact(self, enabled: bool) -> dict:
        """Resize the main window into a draggable, chat-only companion."""
        self._compact = bool(enabled)
        if webview.windows:
            width, height = ((390, 520) if self._compact else (1160, 740))
            webview.windows[0].resize(width, height)
        return {"compact": self._compact}

    def close(self):
        if webview.windows:
            webview.windows[0].destroy()

    def cleanup_before_exit(self, *args):
        """
        Hooked onto the pywebview 'closing' event so it
        fires no matter HOW the window is closed (our
        custom close button, Alt+F4, taskbar, etc.) —
        not just the one JS path. Tells the backend
        process to shut down instead of leaving it
        orphaned in the background.
        """
        if self._artifact_diagnostics is not None:
            self._artifact_diagnostics.shutdown()
        if self._natural is not None:
            self._natural.stop()
        if self._coordination is not None:
            self._coordination.stop()
        if self._desktop_agents is not None:
            self._desktop_agents.close()
        if self._voice_instance is not None:
            try:
                self._voice_instance.stop_wake_loop()
                self._voice_instance.stop_speaking()
            except Exception:
                pass
        try:
            ipc_send("shutdown")
        except Exception:
            pass
        return True  # allow the window to actually close

    # ── Voice: status ───────────────────────────────────────

    def voice_status(self) -> dict:
        return {
            "mic":   self._voice.mic_available,
            "tts":   self._voice.tts_available,
            "wake":  self._voice.wake_active,
        }

    # ── Voice: push-to-talk ─────────────────────────────────

    def push_to_talk(self) -> dict:
        if not self._voice.mic_available:
            return {
                "status": "error",
                "data": (
                    "Mikrofon bulunamadı. "
                    "pip install SpeechRecognition pyaudio"
                ),
                "transcript": "",
            }
        was_waking = self._voice.wake_active
        if was_waking:
            self._voice.stop_wake_loop()

        text = self._voice.listen_once()

        if was_waking:
            self._start_wake_loop()

        if not text:
            return {
                "status": "error",
                "data": "Ses algılanamadı, tekrar dener misin?",
                "transcript": "",
            }

        resp = ipc_send("chat", text)
        if resp.get("status") == "ok":
            self._voice.speak(resp["data"])
        resp["transcript"] = text
        return resp

    # ── Voice: wake word toggle ──────────────────────────────

    def toggle_wake_word(self, enable: bool) -> dict:
        if enable:
            self._start_wake_loop()
        else:
            self._voice.stop_wake_loop()
        return {
            "enabled": self._voice.wake_active,
            "available": self._voice.mic_available,
        }

    def _start_wake_loop(self):
        self._voice.start_wake_loop(
            on_wake=self._on_wake_detected,
            on_command=self._on_wake_command,
        )

    def _on_wake_detected(self):
        self._push_js("onWakeDetected()")

    def _on_wake_command(self, command_text: str):
        # Runs on the wake-loop's background thread.
        if not command_text:
            command_text = self._voice.listen_once(
                timeout=5, phrase_time_limit=12)
        if not command_text:
            self._push_js("onWakeTimeout()")
            return
        resp = ipc_send("chat", command_text)
        resp["transcript"] = command_text
        self._voice.speak(resp.get("data", ""))
        self._push_js(
            f"onVoiceResult({json.dumps(resp)})")

    def set_tts_enabled(self, enabled: bool) -> dict:
        self._voice.set_tts_enabled(enabled)
        return {"enabled": enabled}

    def _push_js(self, code: str):
        try:
            if webview.windows:
                webview.windows[0].evaluate_js(code)
        except Exception:
            pass


# Application JavaScript. The body markup lives in ui/shell.py and the document
# head, shell and ordered script fragments live in ui/. The JavaScript checker
# reads that same static composition without importing this GUI bridge.
_HTML_BODY = SHELL_MARKUP + SCRIPT_DOCUMENT


_ASSET_ROOT = asset_root()
_BRAND_MARK = _ASSET_ROOT / BRAND_MARK
# Full document handed to pywebview; tests read this name.
_HTML = build_document(_HTML_BODY, _ASSET_ROOT)


class QuartzUI:
    """Thin wrapper that boots a pywebview window running the
    HTML/CSS/JS interface above, bridged to the backend via
    the Api class (which itself talks to the IPC socket)."""

    def __init__(self):
        from core.branding import set_windows_app_id
        set_windows_app_id()
        self._api = Api()
        self._window = webview.create_window(
            "Quartz",
            html=_HTML,
            js_api=self._api,
            width=1160,
            height=740,
            min_size=(360, 420),
            frameless=True,
            easy_drag=False,
            background_color="#141517",
        )
        # Fires on ANY close path (our button, Alt+F4,
        # taskbar "Close window", etc.) — not just the
        # custom close button's JS call.
        self._window.events.closing += (
            self._api.cleanup_before_exit)

    def run(self):
        from core.branding import application_icon
        from core.low_spec_optimizer import configure_webview_environment
        configure_webview_environment()
        icon=application_icon()
        webview.start(icon=str(icon) if icon.is_file() else None)


if __name__ == "__main__":
    app = QuartzUI()
    app.run()
