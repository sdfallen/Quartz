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
            return {"status": "ok", "data": self._onboarding_service().status(force=force)}
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

    def coordination_route(self, text, conversation_id, project_id, models, permission_level='read-only'):
        try:
            import re
            from core.message_intent import message_intent, tools_disallowed
            from core.desktop_task_ui import desktop_intent, desktop_help
            if permission_level not in {'read-only','project','full'}: raise ValueError('Geçersiz dosya yetkisi seçimi')
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


_HTML = r"""
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Quartz</title>
<style>
  :root {
    --bg-void:   #030608;
    --glass:     rgba(14, 26, 38, 0.55);
    --glass-brd: rgba(52, 234, 255, 0.14);
    --cyan:      #34eaff;
    --violet:    #7c6cff;
    --amber:     #ffb454;
    --red:       #ff5c72;
    --mint:      #34ffc0;
    --txt:       #eaf6ff;
    --txt-dim:   #6d8ea3;
    --txt-faint: #3d5b6c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    height: 100%; width: 100%;
    background: radial-gradient(ellipse at 50% -10%, #0b1620 0%, #030608 55%, #010203 100%);
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
    color: var(--txt);
    overflow: hidden;
    user-select: none;
  }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-thumb { background: rgba(52,234,255,0.15); border-radius: 3px; }

  .shell {
    display: flex; flex-direction: column;
    height: 100vh; width: 100vw;
    border: 1px solid rgba(52,234,255,0.18);
  }

  /* ── Title bar (drag region) ─────────────────────────── */
  .titlebar {
    display: flex; align-items: center; gap: 12px;
    height: 46px; flex-shrink: 0;
    padding: 0 10px 0 16px;
    background: rgba(8, 16, 24, 0.7);
    border-bottom: 1px solid rgba(52,234,255,0.1);
  }
  .orb-wrap { position: relative; width: 26px; height: 26px; flex-shrink: 0; }
  .orb-ring {
    position: absolute; inset: -5px; border-radius: 50%;
    background: conic-gradient(from 0deg, transparent 0%, var(--cyan) 10%, transparent 26%, transparent 100%);
    animation: spin 3.2s linear infinite;
  }
  .orb-core {
    position: absolute; inset: 0; border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #8ff6ff 0%, #17b7d6 45%, #063a47 100%);
    box-shadow: 0 0 14px 2px rgba(52,234,255,0.55), 0 0 28px 8px rgba(52,234,255,0.16);
    animation: breathe 2.6s ease-in-out infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes breathe {
    0%, 100% { transform: scale(1); filter: brightness(1); }
    50%      { transform: scale(1.08); filter: brightness(1.18); }
  }
  body.ui-idle .orb-ring, body.ui-idle .orb-core,
  body.low-spec:not(.thinking-active) .orb-ring, body.low-spec:not(.thinking-active) .orb-core {
    animation-play-state: paused;
  }
  .brand {
    font-family: 'Rajdhani', sans-serif; font-weight: 700;
    font-size: 15px; letter-spacing: 0.14em; color: var(--txt);
  }
  .status-pill {
    display: flex; align-items: center; gap: 6px;
    font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: 11px; letter-spacing: 0.06em; color: var(--txt-dim);
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 20px; padding: 3px 12px;
    margin-left: 6px;
  }
  .status-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--amber); }
  .status-pill.online .dot { background: var(--mint); box-shadow: 0 0 6px var(--mint); }
  .status-pill.offline .dot { background: var(--red); box-shadow: 0 0 6px var(--red); }

  .titlebar-spacer { flex: 1; }
  .clock {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; color: var(--txt-dim); letter-spacing: 0.03em;
    margin-right: 8px; text-align: right; line-height: 1.3;
  }
  .win-btn {
    -webkit-app-region: no-drag;
    width: 30px; height: 30px; border-radius: 8px;
    border: none; background: transparent; color: var(--txt-dim);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; font-size: 13px; transition: all .15s ease;
  }
  .win-btn:hover { background: rgba(255,255,255,0.06); color: var(--txt); }
  .win-btn.close:hover { background: var(--red); color: #1a0407; }

  /* ── Body layout ──────────────────────────────────────── */
  .body { flex: 1; display: flex; min-height: 0; padding: 10px; gap: 10px; }

  .rail { width: 158px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
  .rail.right { width: 172px; }

  .card {
    background: var(--glass);
    border: 1px solid var(--glass-brd);
    border-radius: 12px;
    backdrop-filter: blur(14px);
    padding: 10px;
  }
  .card-label {
    font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: 10.5px; letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--txt-faint); margin-bottom: 8px;
  }

  .qa-btn {
    -webkit-app-region: no-drag;
    width: 100%; text-align: left;
    font-family: 'Rajdhani', sans-serif; font-weight: 600; font-size: 12.5px;
    letter-spacing: 0.02em; color: var(--txt-dim);
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px; padding: 8px 10px; margin-bottom: 6px;
    cursor: pointer; transition: all .15s ease;
    display: flex; align-items: center; gap: 8px;
  }
  .qa-btn:last-child { margin-bottom: 0; }
  .qa-btn:hover { color: var(--cyan); border-color: rgba(52,234,255,0.3); background: rgba(52,234,255,0.05); }
  .qa-btn .ic { font-size: 13px; opacity: 0.85; }
  .qa-btn.quartz-mode { color:#bdb5ff; border-color:rgba(124,108,255,.2); background:rgba(124,108,255,.06); }
  .qa-btn.quartz-mode:hover { color:#e2ddff; border-color:rgba(124,108,255,.55); background:rgba(124,108,255,.14); box-shadow:0 0 16px rgba(124,108,255,.10); }

  .stat-row { margin-bottom: 9px; }
  .stat-row:last-child { margin-bottom: 0; }
  .stat-top {
    display: flex; justify-content: space-between; align-items: baseline;
    font-family: 'JetBrains Mono', monospace; font-size: 10.5px;
    color: var(--txt-dim); margin-bottom: 4px;
  }
  .stat-top .val { color: var(--cyan); font-weight: 500; }
  .stat-bar { height: 4px; border-radius: 2px; background: rgba(255,255,255,0.06); overflow: hidden; }
  .stat-fill { height: 100%; border-radius: 2px; background: var(--cyan); width: 0%; transition: width .4s ease; }
  .stat-fill.warn { background: var(--amber); }
  .stat-fill.crit { background: var(--red); }

  .sess-row {
    display: flex; justify-content: space-between;
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--txt-dim); padding: 3px 0;
  }
  .sess-row .val { color: var(--cyan); }

  .log-box {
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
    color: var(--txt-faint); line-height: 1.7;
    max-height: 130px; overflow-y: auto;
  }
  .log-box div span { color: #3d5b6c; }

  /* ── Chat column ──────────────────────────────────────── */
  .chat-col { flex: 1; display: flex; flex-direction: column; min-width: 0; position: relative; }
  .chat {
    flex: 1; overflow-y: auto; overflow-anchor: none;
    display: flex; flex-direction: column; gap: 10px;
    padding: 6px 4px 14px;
  }
  .msg { display: flex; max-width: 82%; }
  .msg.user { align-self: flex-end; }
  .msg.bot  { align-self: flex-start; }
  .msg.sys  { align-self: center; max-width: 90%; }
  .bubble {
    padding: 10px 14px; border-radius: 13px;
    font-size: 13.5px; line-height: 1.55;
    backdrop-filter: blur(12px);
    white-space: pre-wrap;
  }
  .msg.bot .bubble {
    background: rgba(20,38,50,0.55);
    border: 1px solid rgba(52,234,255,0.12);
    border-left: 2px solid var(--cyan);
    color: #d7f2fb; border-top-left-radius: 4px;
  }
  .msg.user .bubble {
    background: rgba(52,234,255,0.1);
    border: 1px solid rgba(52,234,255,0.22);
    color: var(--txt); border-top-right-radius: 4px;
  }
  .msg.sys .bubble {
    background: transparent; border: none;
    color: var(--txt-faint); font-size: 11px; font-style: italic;
    text-align: center; padding: 2px 8px;
  }
  .msg.err .bubble {
    background: rgba(255,92,114,0.08);
    border: 1px solid rgba(255,92,114,0.3);
    color: #ffc2ca;
  }
  .msg-meta {
    font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--txt-faint); margin-bottom: 3px; padding: 0 2px;
  }

  .thinking-row {
    display: flex; align-items: center; gap: 6px;
    font-family: 'Rajdhani', sans-serif; font-size: 11px;
    color: var(--amber); padding: 0 6px 6px; height: 16px;
    opacity: 0; transition: opacity .2s ease;
  }
  .thinking-row.show { opacity: 1; }
  .thinking-row .d { width: 4px; height: 4px; border-radius: 50%; background: var(--amber); animation: pulse 1s infinite ease-in-out; }
  .thinking-row .d:nth-child(2) { animation-delay: .15s; }
  .thinking-row .d:nth-child(3) { animation-delay: .3s; }
  @keyframes pulse { 0%,100% { opacity: .3; } 50% { opacity: 1; } }

  .inputbar {
    display: flex; align-items: center; gap: 8px;
    background: rgba(15,28,38,0.65);
    border: 1px solid rgba(52,234,255,0.15);
    border-radius: 22px; padding: 5px 6px 5px 16px;
    backdrop-filter: blur(16px);
    transition: border-color .2s ease, box-shadow .2s ease;
  }
  .inputbar:focus-within { border-color: rgba(52,234,255,0.55); box-shadow: 0 0 0 3px rgba(52,234,255,0.08); }
  .inputbar input {
    flex: 1; background: none; border: none; outline: none;
    color: var(--txt); font-family: 'Inter', sans-serif; font-size: 13.5px;
  }
  .inputbar input::placeholder { color: #43606e; }
  .icon-btn {
    -webkit-app-region: no-drag;
    width: 32px; height: 32px; border-radius: 50%; border: none;
    display: flex; align-items: center; justify-content: center;
    color: var(--txt-dim); background: rgba(255,255,255,0.04);
    cursor: pointer; transition: all .15s ease; flex-shrink: 0;
  }
  .icon-btn:hover { color: var(--cyan); background: rgba(52,234,255,0.1); }
  .icon-btn.send { color: #04222a; background: var(--cyan); }
  .icon-btn.send:hover { background: #6ff2ff; }
  .icon-btn.disabled { opacity: 0.4; pointer-events: none; }
  .icon-btn.mic.listening {
    color: #04222a; background: var(--violet);
    animation: mic-pulse 1s infinite ease-in-out;
  }
  @keyframes mic-pulse {
    0%,100% { box-shadow: 0 0 0 0 rgba(124,108,255,0.5); }
    50%     { box-shadow: 0 0 0 8px rgba(124,108,255,0); }
  }

  .voice-toggle {
    -webkit-app-region: no-drag;
    display: flex; align-items: center; gap: 4px;
    font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: 10.5px; letter-spacing: 0.05em; color: var(--txt-dim);
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px; padding: 4px 10px;
    cursor: pointer; transition: all .15s ease; margin-right: 4px;
  }
  .voice-toggle:hover { border-color: rgba(52,234,255,0.25); }
  .voice-toggle.active {
    color: #1c1030; background: var(--violet); border-color: var(--violet);
  }
  .action-card {
    align-self: stretch; margin: 2px 16px; padding: 12px;
    border-radius: 12px; border: 1px solid rgba(255,180,84,.45);
    background: rgba(70,45,12,.35); color: var(--txt); font-size: 12px;
  }
  .action-card .actions { display:flex; gap:8px; margin-top:10px; }
  .action-card button, .control-btn {
    border: 1px solid rgba(52,234,255,.3); border-radius: 8px;
    background: rgba(52,234,255,.08); color: var(--cyan);
    padding: 6px 10px; cursor:pointer;
  }
  .action-card button.danger { color:#ffc2ca; border-color:rgba(255,92,114,.4); }
  .control-btn.active { background: var(--mint); color:#04221a; }
  .mobile-access-card { border-color:rgba(52,234,255,.22)!important; background:linear-gradient(135deg,rgba(11,34,46,.88),rgba(10,20,30,.75))!important; }
  .mobile-access-card .mobile-label { font-family:'Rajdhani',sans-serif; color:var(--txt-faint); font-size:10px; letter-spacing:.13em; margin:10px 0 4px; }
  .mobile-access-card .mobile-label:first-child { margin-top:0; }
  .mobile-access-card .mobile-value { color:var(--txt-dim); font-family:'JetBrains Mono',monospace; font-size:11px; overflow-wrap:anywhere; }
  .mobile-access-card .mobile-token { color:var(--cyan); padding:8px 9px; border:1px solid rgba(52,234,255,.18); border-radius:8px; background:rgba(3,10,15,.45); }
  .mobile-card-action { display:inline-flex; align-items:center; gap:6px; margin-top:11px; border:1px solid rgba(52,234,255,.3); border-radius:8px; background:rgba(52,234,255,.08); color:var(--cyan); padding:7px 10px; font-family:'Rajdhani',sans-serif; font-size:11px; font-weight:700; letter-spacing:.06em; cursor:pointer; transition:all .15s ease; }
  .mobile-card-action:hover { background:rgba(52,234,255,.16); border-color:rgba(52,234,255,.55); }
  .mobile-card-action:disabled { opacity:.7; cursor:default; }

  .agent-overlay {
    position:fixed; inset:46px 0 0; z-index:80; display:none;
    align-items:center; justify-content:center; padding:18px;
    background:rgba(1,4,7,.9); backdrop-filter:blur(18px);
  }
  .agent-overlay.show { display:flex; }
  .agent-panel {
    width:min(900px,96vw); height:min(620px,88vh); min-height:480px;
    display:flex; flex-direction:column; gap:11px; padding:16px;
    border:1px solid rgba(52,234,255,.24); border-radius:16px;
    background:linear-gradient(145deg,rgba(9,22,31,.98),rgba(3,9,14,.98));
    box-shadow:0 26px 90px rgba(0,0,0,.6),0 0 36px rgba(52,234,255,.05);
  }
  .agent-head { display:flex; align-items:center; gap:10px; }
  .agent-head h2 { font:700 18px 'Rajdhani',sans-serif; letter-spacing:.12em; }
  .agent-head .agent-sub { color:var(--txt-faint); font-size:10px; flex:1; }
  .agent-select, .agent-input, .agent-prompt {
    border:1px solid rgba(52,234,255,.16); border-radius:9px;
    background:#061017; color:var(--txt); outline:none; padding:8px 10px;
    font:11px 'Inter',sans-serif; user-select:text;
  }
  .agent-select:focus, .agent-input:focus, .agent-prompt:focus { border-color:rgba(52,234,255,.55); }
  .agent-status-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
  .agent-status-card { padding:9px; border:1px solid rgba(255,255,255,.06); border-radius:10px; background:rgba(255,255,255,.025); }
  .agent-status-card strong { display:block; font:600 11px 'Rajdhani',sans-serif; color:var(--cyan); letter-spacing:.08em; }
  .agent-status-card span { display:block; margin-top:4px; color:var(--txt-dim); font:10px 'JetBrains Mono',monospace; white-space:pre-wrap; }
  .agent-compose { display:grid; grid-template-columns:1fr 150px; gap:8px; }
  .agent-prompt { resize:none; min-height:68px; }
  .agent-compose-side { display:flex; flex-direction:column; gap:7px; }
  .agent-check { color:var(--amber); font-size:10px; display:flex; gap:6px; align-items:flex-start; }
  .agent-check input { accent-color:var(--amber); }
  .agent-columns { flex:1; min-height:0; display:grid; grid-template-columns:1.15fr 1fr 1fr; gap:8px; }
  .agent-column { min-height:0; display:flex; flex-direction:column; padding:9px; border:1px solid rgba(52,234,255,.09); border-radius:10px; background:rgba(1,7,11,.42); }
  .agent-column h3 { font:600 10px 'Rajdhani',sans-serif; letter-spacing:.11em; color:var(--txt-faint); margin-bottom:7px; }
  .agent-scroll { overflow:auto; min-height:0; color:var(--txt-dim); font:10px/1.55 'JetBrains Mono',monospace; }
  .agent-row { padding:7px 0; border-bottom:1px solid rgba(255,255,255,.045); overflow-wrap:anywhere; }
  .agent-row strong { color:var(--txt); font-weight:500; }
  .agent-row .ok { color:var(--mint); } .agent-row .bad { color:var(--red); } .agent-row .wait { color:var(--amber); }
  .agent-error { min-height:15px; color:#ffc2ca; font-size:10px; }
  body.compact .agent-overlay { display:none!important; }

  /* ── Chat Top Bar & Agent Selector ──────────────────── */
  .rail { display: none; }
  body.show-panels .rail { display: flex; }
  body:not(.show-panels):not(.compact) .chat-col {
    max-width: 920px; margin: 0 auto; width: 100%;
  }
  .chat-header {
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 10px;
    padding: 10px 14px; margin-bottom: 8px;
    background: rgba(8, 20, 30, 0.78); border: 1px solid rgba(52, 234, 255, 0.18);
    border-radius: 14px; backdrop-filter: blur(12px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
  }
  .chat-title-group { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .chat-conv-title {
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 14px;
    color: var(--txt); letter-spacing: 0.05em; max-width: 200px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .agent-seg-group {
    display: inline-flex; align-items: center; gap: 4px;
    background: rgba(3, 10, 16, 0.9);
    border: 1px solid rgba(52, 234, 255, 0.22);
    border-radius: 11px; padding: 3px;
  }
  .agent-seg-btn {
    -webkit-app-region: no-drag;
    border: none; background: transparent; color: var(--txt-dim);
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 12px;
    letter-spacing: 0.06em; padding: 5px 12px; border-radius: 8px;
    cursor: pointer; transition: all .15s ease;
  }
  .agent-seg-btn:hover { color: var(--txt); background: rgba(255, 255, 255, 0.05); }
  .agent-seg-btn.active[data-agent="antigravity"] {
    background: rgba(52, 234, 255, 0.18); color: var(--cyan);
    box-shadow: 0 0 12px rgba(52, 234, 255, 0.2);
  }
  .agent-seg-btn.active[data-agent="codex"] {
    background: rgba(124, 108, 255, 0.22); color: #d5cdff;
    box-shadow: 0 0 12px rgba(124, 108, 255, 0.22);
  }
  .agent-seg-btn.active[data-agent="collaboration"] {
    background: rgba(255, 180, 84, 0.2); color: var(--amber);
    box-shadow: 0 0 12px rgba(255, 180, 84, 0.2);
  }
  .chat-controls-group { display: flex; align-items: center; gap: 8px; }
  .agent-badge-select {
    display: flex; align-items: center; gap: 5px;
    background: rgba(4, 12, 18, 0.85); border: 1px solid rgba(52, 234, 255, 0.22);
    border-radius: 18px; padding: 2px 8px; font-family: 'Rajdhani', sans-serif;
    font-weight: 600; font-size: 11px; color: var(--cyan);
  }
  .agent-badge-select select {
    background: transparent; border: none; color: var(--cyan);
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 11.5px;
    letter-spacing: 0.05em; outline: none; cursor: pointer;
  }
  .agent-badge-select select option { background: #06111a; color: var(--txt); }
  .chat-tool-btn {
    background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px; color: var(--txt-dim); font-size: 11px;
    padding: 5px 10px; cursor: pointer; font-family: 'Inter', sans-serif;
    transition: all .15s ease;
  }
  .chat-tool-btn:hover { background: rgba(52, 234, 255, 0.12); color: var(--cyan); border-color: rgba(52, 234, 255, 0.3); }
  .project-tag {
    font-size: 10px; color: var(--cyan); font-family: 'JetBrains Mono', monospace;
    background: rgba(52, 234, 255, 0.08); padding: 2px 7px; border-radius: 5px; border: 1px solid rgba(52, 234, 255, 0.2);
  }
  .project-picker {
    max-width: 145px; background: rgba(52,234,255,.08); color: var(--cyan);
    border: 1px solid rgba(52,234,255,.24); border-radius: 5px;
    font: 10px 'JetBrains Mono', monospace; padding: 3px 5px;
  }
  .project-picker option { background: #07141b; color: #d5faff; }
  .squad-badge {
    font-size: 10px; font-family: 'JetBrains Mono', monospace;
    padding: 2px 7px; border-radius: 5px;
    background: rgba(61, 220, 151, 0.12); color: #3ddc97;
    border: 1px solid rgba(61, 220, 151, 0.3);
  }
  .squad-badge.warn {
    background: rgba(255, 92, 114, 0.14); color: #ff8c9c;
    border-color: rgba(255, 92, 114, 0.36);
  }
  .msg-progress-box {
    margin-top: 6px; padding: 6px 8px; border-radius: 6px;
    background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(52, 234, 255, 0.08);
    font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--txt-dim);
  }
  .msg-sender-tag {
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 10px;
    letter-spacing: 0.08em; text-transform: uppercase; margin-right: 6px;
  }
  .msg-seq-tag {
    display: inline-block; font-family: 'JetBrains Mono', monospace;
    font-size: 9px; color: var(--txt-faint); margin-right: 6px;
  }
  .msg-model-tag {
    display: inline-block; font-family: 'JetBrains Mono', monospace;
    font-size: 9px; color: var(--txt-dim); background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 4px;
    padding: 0 5px; margin-right: 6px;
  }
  .chat-models-bar {
    width: 100%; display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 8px; padding-top: 7px;
    border-top: 1px solid rgba(52, 234, 255, 0.1);
  }
  .model-selector-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 9px; border-radius: 9px;
    background: rgba(3, 10, 16, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.09);
    font-family: 'Rajdhani', sans-serif; font-size: 11px; color: var(--txt-dim);
    transition: all .15s ease;
  }
  .model-selector-pill.active-agy {
    border-color: rgba(52, 234, 255, 0.36);
    background: rgba(52, 234, 255, 0.06);
  }
  .model-selector-pill.active-codex {
    border-color: rgba(124, 108, 255, 0.42);
    background: rgba(124, 108, 255, 0.08);
  }
  .model-selector-pill .pill-agent-name {
    font-weight: 700; letter-spacing: 0.06em; font-size: 10.5px;
  }
  .model-selector-pill.active-agy .pill-agent-name { color: var(--cyan); }
  .model-selector-pill.active-codex .pill-agent-name { color: #d5cdff; }
  .model-selector-pill select {
    -webkit-app-region: no-drag;
    background: rgba(8, 20, 30, 0.9); color: var(--txt);
    border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px;
    padding: 2px 6px; font-family: 'JetBrains Mono', monospace; font-size: 10.5px;
    outline: none; cursor: pointer;
  }
  .model-selector-pill select:hover,
  .model-selector-pill select:focus {
    border-color: rgba(52, 234, 255, 0.45);
  }
  .model-selector-pill select option { background: #06111a; color: var(--txt); }
  .model-selector-pill .pill-sep { color: var(--txt-faint); font-size: 10px; }
  .jump-bottom-btn {
    -webkit-app-region: no-drag;
    position: absolute; right: 18px; bottom: 72px; z-index: 30;
    display: none; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 18px;
    background: rgba(8, 24, 36, 0.95);
    border: 1px solid rgba(52, 234, 255, 0.5);
    color: var(--cyan); font-family: 'Rajdhani', sans-serif;
    font-weight: 700; font-size: 12px; letter-spacing: 0.06em;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.6), 0 0 14px rgba(52, 234, 255, 0.24);
    cursor: pointer; transition: all .15s ease;
  }
  .jump-bottom-btn.show { display: inline-flex; }
  .jump-bottom-btn:hover { background: rgba(52, 234, 255, 0.2); color: #fff; }
  .tag-antigravity { background: rgba(52, 234, 255, 0.16); color: var(--cyan); border: 1px solid rgba(52, 234, 255, 0.34); }
  .tag-codex { background: rgba(124, 108, 255, 0.18); color: #d5cdff; border: 1px solid rgba(124, 108, 255, 0.38); }
  .tag-collaboration { background: rgba(255, 180, 84, 0.15); color: var(--amber); border: 1px solid rgba(255, 180, 84, 0.3); }
  .tag-user { background: rgba(255, 255, 255, 0.1); color: var(--txt); }
  .msg.bot.sender-antigravity .bubble {
    border-left: 3px solid rgba(52, 234, 255, 0.65);
  }
  .msg.bot.sender-codex .bubble {
    border-left: 3px solid rgba(124, 108, 255, 0.75);
    background: rgba(16, 14, 34, 0.78);
  }

  /* Compact companion: same visual language, chat-only footprint. */
  body.compact .shell {
    border-color: rgba(52,234,255,.32);
    box-shadow: inset 0 0 34px rgba(52,234,255,.025);
  }
  body.compact .titlebar { height: 48px; padding-left: 14px; }
  body.compact .titlebar .status-pill,
  body.compact .titlebar .voice-toggle,
  body.compact .titlebar .clock { display: none; }
  body.compact .body { padding: 9px; }
  body.compact .rail { display: none !important; }
  body.compact .chat { gap: 8px; padding: 4px 2px 10px; }
  body.compact .msg { max-width: 92%; }
  body.compact .bubble { font-size: 12.5px; padding: 8px 11px; }
  body.compact .msg-meta { font-size: 9px; }
  body.compact .inputbar { padding-left: 13px; }
  body.compact .inputbar input { font-size: 12.5px; }
  body.compact #btnMic { display: none; }
  body.compact #btnMin {
    color: var(--cyan); background: rgba(52,234,255,.08);
  }
  .signature-main {
    position: fixed; right: 14px; bottom: 7px; z-index: 5;
    font-family: 'Rajdhani', sans-serif; font-size: 11px;
    font-weight: 500; letter-spacing: .1em; color: rgba(157,190,208,.68);
    padding: 3px 7px; border-radius: 7px;
    background: rgba(3,8,12,.42);
    width: 172px; text-align: center; line-height: 1.25;
    pointer-events: none;
  }
  .signature-main span, .signature-main strong { display: block; }
  .signature-main strong {
    color: rgba(52,234,255,.82); font-weight: 700; margin-top: 2px;
  }
  .signature-mark {
    display: none; align-items: center; justify-content: center;
    width: 25px; height: 25px; border-radius: 8px;
    border: 1px solid rgba(52,234,255,.22);
    color: rgba(52,234,255,.78); background: rgba(52,234,255,.045);
    font-family: 'Rajdhani', sans-serif; font-weight: 700;
    font-size: 10px; letter-spacing: .08em; margin-right: 2px;
  }
  body.compact .signature-main,
  body:not(.show-panels) .signature-main { display: none; }
  body.compact .signature-mark,
  body:not(.show-panels) .signature-mark { display: flex; }
  .signature-intro {
    position: fixed; inset: 0; z-index: 100;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: radial-gradient(circle at center, rgba(11,28,38,.98), rgba(1,2,3,.995) 68%);
    pointer-events: none; animation: signature-reveal 1.8s ease forwards;
  }
  .signature-intro .intro-brand {
    font-family: 'Rajdhani', sans-serif; font-weight: 700;
    font-size: 26px; letter-spacing: .28em; color: var(--txt);
    text-shadow: 0 0 22px rgba(52,234,255,.32);
  }
  .signature-intro .intro-credit {
    margin-top: 12px; font-family: 'Rajdhani', sans-serif;
    font-size: 11px; letter-spacing: .18em; color: var(--txt-dim);
  }
  .signature-intro .intro-credit strong { color: var(--cyan); font-weight: 600; }
  @keyframes signature-reveal {
    0% { opacity: 0; }
    14%, 70% { opacity: 1; }
    100% { opacity: 0; visibility: hidden; }
  }
  .api-setup {
    position: fixed; inset: 0; z-index: 90; display: none;
    align-items: center; justify-content: center; padding: 22px;
    background: radial-gradient(circle at 50% 28%, rgba(11,31,42,.97), rgba(1,3,5,.99) 72%);
  }
  .api-setup.show { display: flex; }
  .api-panel {
    width: min(430px, 100%); padding: 28px; border-radius: 18px;
    background: rgba(10,22,30,.88); border: 1px solid rgba(52,234,255,.22);
    box-shadow: 0 24px 80px rgba(0,0,0,.55), 0 0 40px rgba(52,234,255,.06);
  }
  .api-panel h2 { font-family:'Rajdhani',sans-serif; letter-spacing:.12em; font-size:21px; }
  .api-panel p { color:var(--txt-dim); font-size:12.5px; line-height:1.55; margin:9px 0 18px; }
  .api-panel label { display:block; color:var(--txt-dim); font-size:10px; letter-spacing:.1em; margin:12px 0 6px; }
  .api-panel select, .api-panel input {
    width:100%; border:1px solid rgba(52,234,255,.16); border-radius:10px;
    background:#071017; color:var(--txt); padding:11px 12px; outline:none;
  }
  .api-panel input:focus, .api-panel select:focus { border-color:rgba(52,234,255,.55); }
  .api-submit {
    width:100%; margin-top:16px; padding:11px; border:0; border-radius:10px;
    background:var(--cyan); color:#03171d; font-weight:700; cursor:pointer;
  }
  .api-submit:disabled { opacity:.5; cursor:wait; }
  .api-error { min-height:18px; margin-top:10px; color:#ffc2ca; font-size:11px; }
  .privacy-note { color:var(--txt-faint)!important; font-size:10.5px!important; margin-bottom:0!important; }
  @keyframes quartz-control-pulse {
    0%, 100% { box-shadow: inset 0 0 28px rgba(52,234,255,.16), 0 0 18px rgba(52,234,255,.22); border-color: rgba(52,234,255,.68); }
    50% { box-shadow: inset 0 0 46px rgba(52,234,255,.28), 0 0 28px rgba(52,234,255,.38); border-color: rgba(52,234,255,.95); }
  }
  body.screen-control-active .shell {
    animation: quartz-control-pulse 2.2s infinite ease-in-out;
  }
  .screen-control-hud {
    -webkit-app-region: no-drag;
    position: fixed; top: 12px; left: 14px; z-index: 9999;
    display: inline-flex; align-items: center; gap: 12px;
    padding: 7px 12px 7px 14px; border-radius: 12px;
    background: rgba(5, 13, 21, 0.94);
    border: 1.5px solid rgba(52, 234, 255, 0.78);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.65), 0 0 20px rgba(52, 234, 255, 0.25);
    backdrop-filter: blur(10px);
  }
  .screen-control-hud[hidden] { display: none !important; }
  .screen-control-hud .hud-dot {
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--cyan); box-shadow: 0 0 10px var(--cyan);
  }
  .screen-control-hud .hud-meta { display: flex; flex-direction: column; line-height: 1.15; }
  .screen-control-hud .hud-title {
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 11.5px;
    letter-spacing: 0.08em; color: var(--cyan);
  }
  .screen-control-hud .hud-sub { font-size: 10px; color: var(--txt-dim); }
  .screen-control-hud .hud-stop-btn {
    padding: 6px 12px; border-radius: 8px; border: 1px solid rgba(255, 110, 128, 0.65);
    background: linear-gradient(180deg, #e12d4b, #b81d38); color: #fff;
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 11.5px;
    letter-spacing: 0.06em; cursor: pointer; transition: all .15s ease;
  }
  .screen-control-hud .hud-stop-btn:hover {
    background: linear-gradient(180deg, #ff3b5c, #d42240);
    box-shadow: 0 0 14px rgba(255, 59, 92, 0.55);
  }
</style>
</head>
<body>

<div class="screen-control-hud" id="screenControlHud" hidden>
  <span class="hud-dot"></span>
  <div class="hud-meta">
    <span class="hud-title" id="screenControlHudTitle">QUARTZ KONTROLDE</span>
    <span class="hud-sub" id="screenControlHudSub">Yalnız bu tuşla durdurulur</span>
  </div>
  <button type="button" class="hud-stop-btn" id="btnHudStopTask">⏹ GÖREVİ DURDUR</button>
</div>

<div class="shell">

  <div class="titlebar pywebview-drag-region">
    <div class="orb-wrap" id="orbWrap">
      <div class="orb-ring"></div>
      <div class="orb-core" id="orbCore"></div>
    </div>
    <div class="brand">QUARTZ</div>
    <div class="status-pill offline" id="statusPill">
      <div class="dot"></div><span id="statusText">CONNECTING</span>
    </div>
    <div class="titlebar-spacer"></div>
    <div class="signature-mark" title="Ali Mehdi">AM</div>
    <button class="voice-toggle" id="btnPanels" title="Yan panelleri ve sistem araçlarını göster/gizle">☰ Araçlar</button>
    <button class="voice-toggle" id="btnWake" title="Uyandırma kelimesi: &quot;Hey Quartz&quot;">◎ Wake</button>
    <button class="voice-toggle active" id="btnTts" title="Sesli yanıt aç/kapat">🔊 TTS</button>
    <div class="clock" id="clock">--:--:--</div>
    <button class="win-btn" id="btnMin" title="Küçült">─</button>
    <button class="win-btn close" id="btnClose" title="Kapat">✕</button>
  </div>

  <div class="body">

    <div class="rail left">
      <div class="card">
        <div class="card-label">Hızlı İşlemler</div>
        <button class="qa-btn" data-action="screenshot"><span class="ic">⬡</span> Ekran Görüntüsü</button>
        <button class="qa-btn" data-action="sysinfo"><span class="ic">⬡</span> Sistem Bilgisi</button>
        <button class="qa-btn" data-action="windows"><span class="ic">▣</span> Açık Pencereler</button>
        <button class="qa-btn" data-action="desktop" style="display:none"><span class="ic">⬡</span> Masaüstünü Listele</button>
        <button class="qa-btn" data-action="plugins" style="display:none"><span class="ic">⬡</span> Eklentiler</button>
        <button class="qa-btn" data-action="update_all" style="display:none"><span class="ic">⬡</span> Hepsini Güncelle</button>
        <button class="qa-btn quartz-mode" data-action="quartz_mode"><span class="ic">◉</span> Quartz Mode</button>
        <button class="qa-btn" id="btnAdvisor"><span class="ic">◌</span> Ekran Rehberi: KAPALI</button>
        <button class="qa-btn" id="btnAgentCenter"><span class="ic">◇</span> Ajan Merkezi</button>
        <button class="qa-btn" id="btnMobile"><span class="ic">◇</span> Mobil Erişim</button>
        <button class="qa-btn" id="btnClear"><span class="ic">⬡</span> Sohbeti Temizle</button>
      </div>
      <div class="card">
        <div class="card-label">Güvenlik</div>
        <button class="control-btn" id="btnSafe">Güvenli Mod: KAPALI</button>
        <div class="log-box" id="pluginPermissions" style="margin-top:8px"></div>
      </div>
    </div>

    <div class="chat-col">
      <div class="chat-header">
        <div class="chat-title-group">
          <span class="chat-conv-title" id="chatConvTitle">Yeni Sohbet</span>
          <select class="project-picker" id="mainProjectSelect" title="Aktif Proje" aria-label="Aktif Proje"></select>
          <button class="chat-tool-btn" id="btnAddProject" title="Windows klasör seçicisiyle proje ekle">＋ Proje</button>
          <span class="project-tag" id="writerBadge" style="display:none"></span>
          <details id="writerRecoveryPanel" hidden style="max-width:720px;font-size:12px">
            <summary>Kesilen yazıcı görevi — inceleme gerekli</summary><div id="writerRecoveryBody"></div>
          </details>
          <span class="project-tag" id="chatProjectTag" title="Çalışma Alanı" style="display:none">SquadPilot</span>
          <span class="squad-badge" id="squadBadge" title="Squad Mesajlaşma Altyapısı">Squad: Bağlı</span>
        </div>
        <div class="agent-seg-group" id="agentSegGroup" role="tablist" aria-label="Ajan Seçici">
          <button type="button" class="agent-seg-btn active" data-agent="antigravity">◈ Antigravity</button>
          <button type="button" class="agent-seg-btn" data-agent="codex">◈ Codex</button>
          <button type="button" class="agent-seg-btn" data-agent="collaboration">◈ Birlikte</button>
        </div>
        <div class="chat-controls-group">
          <select class="project-picker" id="mainPermissionLevel" title="Tam Yetki (Tek Yetki Sistemi)" aria-label="İşlem Yetkisi" style="display:none">
            <option value="full" selected>Tam Yetki</option>
          </select>
          <input type="checkbox" id="mainWriteToggle" style="display:none" checked>
          <span id="permissionSelectionHint" aria-live="polite" style="font-size:11px;max-width:280px;color:#34eaff;font-weight:600">◉ Tam Yetki Aktif</span>
          <div class="agent-badge-select" title="Aktif Ajan" style="display:none">
            <span style="font-size:10px">◈</span>
            <select id="mainAgentSelect">
              <option value="antigravity">Antigravity</option>
              <option value="codex">Codex</option>
              <option value="collaboration">Birlikte (Squad)</option>
            </select>
          </div>
          <button class="chat-tool-btn" id="btnContinueCollab" style="display:none" title="Birlikte modunda ajanlar arası tartışmayı 1 tur daha sürdür">⇄ +1 Tur</button>
          <button type="button" class="chat-tool-btn" id="btnSelfDiagnostics" title="Quartz öz teşhisini bu sohbette başlat">◈ Öz Teşhis</button>
          <button class="chat-tool-btn" id="btnNewChat" title="Yeni Sohbet Başlat">＋ Yeni</button>
        </div>
        <div class="chat-models-bar" id="chatModelsBar">
          <div class="model-selector-pill active-agy" id="agyModelPill" title="Antigravity Model ve Düşünme Seviyesi Seçimi">
            <span class="pill-agent-name">ANTIGRAVITY</span>
            <select id="agyModelSelect" aria-label="Antigravity Modeli">
              <option value="gemini-4-argon-medium">Gemini 4 Argon (Medium)</option>
              <option value="gemini-4-argon-high">Gemini 4 Argon (High)</option>
              <option value="gemini-4-argon-low">Gemini 4 Argon (Low)</option>
              <option value="gemini-3.8-flash-high">Gemini 3.8 Flash (High)</option>
              <option value="gemini-3.8-flash-medium">Gemini 3.8 Flash (Medium)</option>
              <option value="gemini-3.8-flash-low">Gemini 3.8 Flash (Low)</option>
              <option value="claude-opus-5-5-medium">Claude Opus 5.5 (Medium)</option>
              <option value="claude-sonnet-5-5-medium">Claude Sonnet 5.5 (Medium)</option>
              <option value="gpt-oss-120b-medium">GPT-OSS 120B (Medium)</option>
            </select>
            <span class="pill-sep">·</span>
            <select id="agyEffortSelect" aria-label="Antigravity Düşünme Seviyesi" title="Antigravity Düşünme Seviyesi (--effort)">
              <option value="low">low</option>
              <option value="medium" selected>medium</option>
              <option value="high">high</option>
              <option value="xhigh">xhigh</option>
              <option value="max">max</option>
            </select>
          </div>
          <div class="model-selector-pill" id="codexModelPill" title="Codex Model ve Düşünme Seviyesi Seçimi">
            <span class="pill-agent-name">CODEX</span>
            <select id="codexModelSelect" aria-label="Codex Modeli">
              <option value="gpt-6.1-sol">GPT-6.1-Sol</option>
              <option value="gpt-6-astra">GPT-6-Astra</option>
              <option value="gpt-6-sol">GPT-6-Sol</option>
              <option value="gpt-6-luna">GPT-6-Luna</option>
              <option value="gpt-5.6-sol">GPT-5.6-Sol</option>
              <option value="gpt-5.6-terra">GPT-5.6-Terra</option>
              <option value="gpt-5.6-luna">GPT-5.6-Luna</option>
            </select>
            <span class="pill-sep">·</span>
            <select id="codexEffortSelect" aria-label="Codex Düşünme Seviyesi" title="Codex Düşünme Seviyesi (model_reasoning_effort)">
              <option value="low" selected>low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="xhigh">xhigh</option>
              <option value="max">max</option>
              <option value="ultra">ultra</option>
            </select>
          </div>
        </div>
      </div>
      <div class="desktop-task-bar" id="desktopTaskBar" data-state="normal">
        <div class="desktop-task-copy" aria-live="polite">
          <strong id="desktopTaskLabel">Normal sohbet</strong>
          <span id="desktopTaskDetail">Dosya erişimi ayrı; masaüstü kontrolü görev onayı gerektirir.</span>
        </div>
        <button type="button" class="control-btn" id="btnDesktopTaskStop" hidden>Görevi durdur</button>
      </div>
      <div class="chat" id="chat"></div>
      <button type="button" class="jump-bottom-btn" id="btnJumpBottom" title="En son mesaja git">Yeni mesajlar ↓</button>
      <div class="thinking-row" id="thinkingRow">
        <div class="d"></div><div class="d"></div><div class="d"></div>
        <span id="thinkingText">işleniyor...</span>
        <button class="control-btn" id="btnCancel" style="display:none">İptal</button>
      </div>
      <div class="inputbar">
        <input type="text" id="msgInput" aria-label="Ekibe yazın veya görev verin" aria-keyshortcuts="Control+L" title="Sohbete odaklan: Ctrl+L · Gönder: Enter" placeholder="Antigravity veya Codex'e mesaj yaz..." autofocus>
        <button class="icon-btn mic" id="btnMic" title="Konuş (push-to-talk)">🎤</button>
        <button class="icon-btn send" id="btnSend">➤</button>
      </div>
    </div>

    <div class="rail right">
      <div class="card">
        <div class="card-label">Yanıt Ayrıntısı</div>
        <select class="agent-select" id="responseDetail" aria-label="Yanıt Ayrıntısı" style="width:100%">
          <option value="short" selected>Kısa (varsayılan)</option>
          <option value="normal">Normal</option>
          <option value="technical">Teknik</option>
        </select>
        <div style="font-size:11px;opacity:.7;margin-top:5px">Codex, Antigravity ve Birlikte için geçerlidir.</div>
      </div>
      <div class="card">
        <div class="card-label">Sistem</div>
        <div class="stat-row">
          <div class="stat-top"><span>CPU</span><span class="val" id="cpuVal">--%</span></div>
          <div class="stat-bar"><div class="stat-fill" id="cpuFill"></div></div>
        </div>
        <div class="stat-row">
          <div class="stat-top"><span>RAM</span><span class="val" id="memVal">--%</span></div>
          <div class="stat-bar"><div class="stat-fill" id="memFill"></div></div>
        </div>
        <div class="stat-row">
          <div class="stat-top"><span>DISK</span><span class="val" id="diskVal">--%</span></div>
          <div class="stat-bar"><div class="stat-fill" id="diskFill"></div></div>
        </div>
      </div>
      <div class="card">
        <div class="card-label">Sağlayıcı Yöneticisi</div>
        <div class="log-box" id="providerStatus">Kontrol ediliyor...</div>
        <button class="control-btn" id="btnProviderProbe" style="margin-top:7px;width:100%">Bağlantıyı Test Et</button>
        <button class="control-btn" id="btnCliConnections" style="margin-top:7px;width:100%">Hesaplar ve CLI kurulumu</button>
      </div>
      <div class="card">
        <div class="card-label">Oturum</div>
        <div class="sess-row"><span>Mesaj</span><span class="val" id="sessMsgs">0</span></div>
        <div class="sess-row"><span>Süre</span><span class="val" id="sessUptime">00:00:00</span></div>
        <div class="sess-row"><span>Durum</span><span class="val" id="sessStatus">—</span></div>
      </div>
      <div class="card">
        <div class="card-label">Aktif Operasyon</div>
        <div class="log-box" id="operationStatus">Aktif görev yok</div>
        <div style="display:flex;gap:6px;margin-top:7px">
          <button class="control-btn" id="btnLearnOperation" style="display:none">Öğren</button>
          <button class="control-btn" id="btnFinishOperation" style="display:none">Bitir</button>
        </div>
      </div>
      <div class="card">
        <div class="card-label">Görevler</div>
        <div class="log-box" id="taskList">Henüz görev yok</div>
      </div>
      <div class="card" style="flex:1; min-height:0; display:flex; flex-direction:column;">
        <div class="card-label">Log</div>
        <div class="log-box" id="logBox"></div>
      </div>
    </div>

  </div>
  <div class="signature-main">
    <span>DESIGNED &amp; ENGINEERED BY</span><strong>ALI MEHDI</strong>
  </div>
</div>

<div class="signature-intro" id="signatureIntro" aria-hidden="true">
  <div class="intro-brand">QUARTZ</div>
  <div class="intro-credit">CREATED BY <strong>ALI MEHDI</strong></div>
</div>

<div class="api-setup" id="cliSetup" role="dialog" aria-modal="true" aria-labelledby="cliWelcome">
  <div class="api-panel" style="max-width:570px;max-height:90vh;overflow:auto">
    <h2 id="cliWelcome">Quartz'a Hoş Geldiniz</h2>
    <p>Tek bir hesapla başlayabilirsiniz. Codex veya Antigravity masaüstü uygulaması gerekmez. Hafif CLI araçlarını Quartz sizin için kurar.</p>
    <label for="cliProvider">BAĞLANTI</label>
    <select id="cliProvider"><option value="codex">Codex / OpenAI</option><option value="gemini">Gemini / Google</option></select>
    <div id="cliProviderState" class="log-box" aria-live="polite">Bağlantılar kontrol ediliyor…</div>
    <button class="api-submit" id="cliAccount">Hesabımla bağlan</button>
    <p>Google hesabı bağımsız Antigravity CLI ile bağlanır; Desktop gerekmez. API anahtarı Gemini CLI ve ayrı API kotasını kullanır.</p>
    <label for="cliKey">VEYA API ANAHTARI</label>
    <input id="cliKey" type="password" autocomplete="off" spellcheck="false" placeholder="Anahtarınız yalnız bu bilgisayarda saklanır">
    <button class="api-submit" id="cliValidate">Doğrula ve bağlan</button>
    <button class="control-btn" id="cliInstall">Hesap için CLI kur (Desktop gerekmez)</button>
    <button class="control-btn" id="cliCheck">Bağlantıyı kontrol et</button>
    <div id="cliMessage" class="api-error" role="status" aria-live="polite"></div>
    <button class="api-submit" id="cliContinue" disabled>Sohbete geç</button>
    <button class="control-btn" id="cliLater">Şimdi değil</button>
    <p class="privacy-note">Anahtar .env dosyasında; yalnız bağlantı bilgisi Quartz belleğinde tutulur. Sohbete ve günlüklere anahtar yazılmaz. Kurulum Quartz'a özel klasördedir; sistem PATH ayarı değişmez.</p>
  </div>
</div>

<div class="api-setup" id="apiSetup">
  <div class="api-panel">
    <h2>QUARTZ BAĞLANTISI</h2>
    <p>Asistanı kullanmaya başlamak için API anahtarını bir kez doğrula. Sonraki açılışlarda bu ekran tekrar gösterilmez.</p>
    <label for="apiProvider">SAĞLAYICI</label>
    <select id="apiProvider">
      <option value="nvidia">NVIDIA — GPT-OSS 20B</option>
      <option value="groq">Groq — GPT OSS 120B</option>
      <option value="github">GitHub Models</option>
    </select>
    <label for="apiKey">API ANAHTARI</label>
    <input id="apiKey" type="password" autocomplete="off" spellcheck="false" placeholder="Anahtarını buraya yapıştır">
    <button class="api-submit" id="apiSubmit">DOĞRULA VE BAŞLAT</button>
    <div class="api-error" id="apiError"></div>
    <p class="privacy-note">Anahtar yalnızca bu bilgisayardaki .env dosyasında saklanır; sohbet geçmişine ve loglara yazılmaz.</p>
  </div>
</div>

<div class="agent-overlay" id="agentOverlay">
  <div class="agent-panel">
    <div class="agent-head">
      <h2>AJAN MERKEZİ</h2>
      <div class="agent-sub">SQUAD KOORDİNASYONU · YEREL ABONELİK CLI ÇALIŞMA ZAMANI</div>
      <select class="agent-select" id="agentProject"></select>
      <button class="control-btn" id="btnAgentRefresh">Yenile</button>
      <button class="win-btn close" id="btnAgentClose">✕</button>
    </div>
    <div class="agent-status-grid">
      <div class="agent-status-card"><strong>SQUAD</strong><span id="agentSquadStatus">Kontrol ediliyor...</span></div>
      <div class="agent-status-card"><strong>CODEX</strong><span id="agentCodexStatus">Kontrol ediliyor...</span></div>
      <div class="agent-status-card"><strong>GEMINI / ANTIGRAVITY</strong><span id="agentGeminiStatus">Doğrulanmadı</span></div>
    </div>
    <div class="agent-compose">
      <textarea class="agent-prompt" id="agentPrompt" placeholder="Gerçek ajanlara görev ver..."></textarea>
      <div class="agent-compose-side">
        <select class="agent-select" id="agentProvider">
          <option value="codex">Codex</option>
          <option value="antigravity">Antigravity</option>
          <option value="collaboration">Codex + Antigravity</option>
        </select>
        <select class="agent-select" id="agentWrite" aria-label="Görev Yetkisi" style="display:none">
          <option value="full" selected>Tam Yetki</option>
          <!-- <option value="read-only" selected> -->
        </select>
        <button class="control-btn" id="btnAgentDispatch">AJANA ATA</button>
        <div class="agent-error" id="agentModelSelection">Üstteki sohbet model seçimleri kullanılır.</div>
        <div class="agent-error" id="agentError"></div>
      </div>
    </div>
    <div style="padding:12px;border:1px solid #3a6670;margin:8px 0">
      <strong>BİLGİSAYAR OPERATÖRÜ · AYRI OTURUM İZNİ</strong>
      <p style="font-size:12px">Yalnız seçili pencere. Aynı anda tek ajan. Başka pencereye geçmek girdiyi keser.
      Kimlik doğrulama, güvenlik, silme/ödeme ve kayıt üzerine yazma kapsam dışıdır.
      Deneysel: Windows UIA ve yerel WebView fare/tuş testi geçti; her uygulama için ayrıca doğrulama gerekir.
      Warband girişi Universal Modder koruma adaptörü tamamlanana kadar kapalıdır.</p>
      <select class="agent-select" id="desktopWindow" aria-label="Kontrol edilecek pencere"></select>
      <button class="control-btn" id="btnDesktopWindows">Pencereleri Getir</button>
      <button class="control-btn" id="btnDesktopStart">Seçili Ajanla Kontrol Et</button>
      <button class="control-btn" id="btnDesktopStop" style="color:#ff8888">KONTROLÜ DURDUR</button>
      <pre id="desktopOperatorStatus" style="white-space:pre-wrap;max-height:180px;overflow:auto">KAPALI · Görev açıklamasını yukarıya yazın. Model seçimleri sohbet seçicilerinden alınır.</pre>
    </div>
    <div class="agent-columns">
      <div class="agent-column"><h3>GERÇEK ÇALIŞMA ZAMANLARI</h3><div class="agent-scroll" id="agentRuns"></div></div>
      <div class="agent-column"><h3>SQUAD GÖREVLERİ / AJANLAR</h3><div class="agent-scroll" id="agentTasks"></div></div>
      <div class="agent-column"><h3>MESAJ GEÇMİŞİ</h3><div class="agent-scroll" id="agentHistory"></div></div>
    </div>
  </div>
</div>

<script>
  const chatEl      = document.getElementById('chat');
  const inputEl     = document.getElementById('msgInput');
  const sendBtn     = document.getElementById('btnSend');
  const micBtn      = document.getElementById('btnMic');
  const wakeBtn     = document.getElementById('btnWake');
  const ttsBtn      = document.getElementById('btnTts');
  const thinkingRow = document.getElementById('thinkingRow');
  const orbCore     = document.getElementById('orbCore');
  const statusPill  = document.getElementById('statusPill');
  const statusText  = document.getElementById('statusText');
  const clockEl     = document.getElementById('clock');
  const logBox      = document.getElementById('logBox');
  const safeBtn     = document.getElementById('btnSafe');
  const advisorBtn  = document.getElementById('btnAdvisor');
  const cancelBtn   = document.getElementById('btnCancel');
  const thinkingText= document.getElementById('thinkingText');
  const taskList     = document.getElementById('taskList');
  const operationStatus = document.getElementById('operationStatus');
  const providerStatus = document.getElementById('providerStatus');
  const providerProbeBtn = document.getElementById('btnProviderProbe');
  const learnOperationBtn = document.getElementById('btnLearnOperation');
  const finishOperationBtn = document.getElementById('btnFinishOperation');
  const signatureIntro = document.getElementById('signatureIntro');
  const apiSetup = document.getElementById('apiSetup');
  const apiKey = document.getElementById('apiKey');
  const apiSubmit = document.getElementById('apiSubmit');
  const apiError = document.getElementById('apiError');
  const agentOverlay = document.getElementById('agentOverlay');
  const agentProject = document.getElementById('agentProject');
  const agentPrompt = document.getElementById('agentPrompt');
  const agentWrite = document.getElementById('agentWrite');
  const agentProvider = document.getElementById('agentProvider');
  const agentError = document.getElementById('agentError');
  const mainAgentSelect = document.getElementById('mainAgentSelect');
  const chatConvTitle = document.getElementById('chatConvTitle');
  const chatProjectTag = document.getElementById('chatProjectTag');
  const mainProjectSelect = document.getElementById('mainProjectSelect');
  const btnAddProject = document.getElementById('btnAddProject');
  const writerBadge = document.getElementById('writerBadge');
  const btnNewChat = document.getElementById('btnNewChat');
  let currentConvId = null;
  let chatPollInterval = null;
  let activeBotBubble = null;
  let antigravitySafetyWarning = '';
  let antigravityWarningAccepted = false;

  let agentPollToken = 0;

  function updateAntigravitySafety(status) {
    antigravitySafetyWarning = String(status?.safety_warning || '');
    for (const [agent, label] of [['antigravity', '◈ Antigravity'], ['collaboration', '◈ Birlikte']]) {
      const button = document.querySelector(`.agent-seg-btn[data-agent="${agent}"]`);
      if (!button) continue;
      button.textContent = label + (antigravitySafetyWarning ? ' ⚠' : '');
      button.title = antigravitySafetyWarning;
    }
  }

  function confirmAntigravitySafety() {
    if (!antigravitySafetyWarning || antigravityWarningAccepted) return true;
    const accepted = window.confirm('ANTIGRAVITY WINDOWS UYARISI\n\n' + antigravitySafetyWarning +
      '\n\nBu oturumda inceleme görevlerine devam etmek istiyor musun?');
    if (accepted) antigravityWarningAccepted = true;
    return accepted;
  }

  signatureIntro.addEventListener('animationend', () => signatureIntro.remove());

  async function checkApiSetup() {
    try {
      const response = await window.pywebview.api.onboarding_status();
      if (response.status !== 'ok') return;
      renderCliStatus(response.data);
      if (response.data.needs_setup) document.getElementById('cliSetup').classList.add('show');
    } catch (_) {}
  }

  let cliPollTimer = null;
  let cliState = null;
  function renderCliStatus(data) {
    cliState = data;
    const providers = data.providers || {};
    document.getElementById('cliProviderState').textContent = ['codex','gemini'].map(p => {
      const state = providers[p] || {};
      const label = state.ready ? 'Bağlı' : !state.installed ? 'CLI kurulacak' : state.configured ? 'Bağlantı doğrulanmalı' : 'Hesap bağlantısı bekleniyor';
      const name = p === 'codex' ? 'Codex' : state.backend === 'agy' ? 'Gemini · Antigravity CLI' : 'Gemini CLI';
      return `${name}: ${label}${state.auth_message ? '\n' + state.auth_message : ''}`;
    }).join('\n');
    document.getElementById('cliMessage').textContent = data.job?.message || '';
    const busy = data.job?.state === 'running';
    ['cliValidate','cliAccount','cliInstall'].forEach(id => document.getElementById(id).disabled = busy);
    document.getElementById('cliContinue').disabled = !Object.values(providers).some(p=>p.ready);
    document.querySelectorAll('.agent-seg-btn[data-agent]').forEach(button => {
      const agent = button.dataset.agent;
      const ready = agent === 'collaboration' ? providers.codex?.ready && providers.gemini?.ready : providers[agent === 'antigravity' ? 'gemini' : 'codex']?.ready;
      button.disabled = !ready;
      button.title = ready ? '' : 'Hesaplar ve CLI kurulumu bölümünden bu ajanı bağlayabilirsiniz';
    });
    clearTimeout(cliPollTimer);
    if ((busy || Object.values(providers).some(p=>p.login_pending)) && document.getElementById('cliSetup').classList.contains('show')) cliPollTimer = setTimeout(()=>refreshCliStatus(false), 1500);
  }
  async function refreshCliStatus(force=true) {
    try {
      const response = await window.pywebview.api.onboarding_status(force);
      if (response.status !== 'ok') throw Error(response.data);
      renderCliStatus(response.data);
    } catch (e) { document.getElementById('cliMessage').textContent = String(e.message || e); }
  }
  async function beginCli(operation) {
    const input = document.getElementById('cliKey');
    const key = operation === 'key' ? input.value.trim() : '';
    input.value = '';
    try {
      const response = await window.pywebview.api.onboarding_begin(operation, document.getElementById('cliProvider').value, key);
      if (response.status !== 'ok') throw Error(response.data);
      await refreshCliStatus(false);
    } catch (e) { document.getElementById('cliMessage').textContent = String(e.message || e); }
  }
  document.getElementById('cliAccount').onclick = ()=>beginCli(document.getElementById('cliProvider').value === 'gemini' ? 'account_agy' : 'account');
  document.getElementById('cliValidate').onclick = ()=>beginCli('key');
  document.getElementById('cliInstall').onclick = ()=>beginCli(document.getElementById('cliProvider').value === 'gemini' ? 'install_agy' : 'install');
  document.getElementById('cliCheck').onclick = ()=>refreshCliStatus(true);
  document.getElementById('btnCliConnections').onclick = async()=>{ document.getElementById('cliSetup').classList.add('show'); await refreshCliStatus(true); };
  document.getElementById('cliLater').onclick = ()=>{ clearTimeout(cliPollTimer); document.getElementById('cliSetup').classList.remove('show'); };
  document.getElementById('cliContinue').onclick = async()=>{
    const result = await window.pywebview.api.onboarding_refresh();
    if (result.status !== 'ok') { document.getElementById('cliMessage').textContent=result.data; return; }
    document.getElementById('cliSetup').classList.remove('show');
    const provider = cliState?.providers?.gemini?.ready ? 'antigravity' : 'codex';
    if (currentConvId) await window.pywebview.api.chat_set_agent(currentConvId, provider);
    syncAgentUI(provider);
    await loadActiveConversation();
  };

  apiSubmit.addEventListener('click', async () => {
    const key = apiKey.value.trim();
    if (!key) { apiError.textContent = 'Lütfen API anahtarını gir.'; return; }
    apiSubmit.disabled = true;
    apiSubmit.textContent = 'DOĞRULANIYOR...';
    apiError.textContent = '';
    try {
      const result = await window.pywebview.api.configure_api(
        document.getElementById('apiProvider').value, key);
      apiKey.value = '';
      if (result.status !== 'ok') throw new Error(result.data || 'Anahtar doğrulanamadı');
      apiSetup.classList.remove('show');
      appendMsg('bot', 'QUARTZ', 'API bağlantısı doğrulandı. Quartz kullanıma hazır.');
    } catch (error) {
      apiError.textContent = 'Doğrulama başarısız: ' + String(error.message || error);
    } finally {
      apiSubmit.disabled = false;
      apiSubmit.textContent = 'DOĞRULA VE BAŞLAT';
    }
  });
  apiKey.addEventListener('keydown', event => {
    if (event.key === 'Enter') apiSubmit.click();
  });

  let ttsEnabled = true;

  let thinking   = false;
  let msgCount   = 0;
  let startTime  = Date.now();
  let inpHistory = [];
  let histCursor = -1;
  let safeMode = false;
  let advisorEnabled = false;
  let requestStarted = 0;
  let requestTimer = null;

  const orbStates = {
    idle:      { core: 'radial-gradient(circle at 35% 30%, #8ff6ff 0%, #17b7d6 45%, #063a47 100%)', glow: 'rgba(52,234,255,0.55)',  speed: '2.6s' },
    listening: { core: 'radial-gradient(circle at 35% 30%, #c9b8ff 0%, #7c6cff 45%, #2a1f66 100%)', glow: 'rgba(124,108,255,0.6)',  speed: '1.1s' },
    thinking:  { core: 'radial-gradient(circle at 35% 30%, #ffe6a8 0%, #ffb454 45%, #6b3d05 100%)', glow: 'rgba(255,180,84,0.6)',   speed: '0.9s' },
    error:     { core: 'radial-gradient(circle at 35% 30%, #ffb3ba 0%, #ff5c72 45%, #5c0d17 100%)', glow: 'rgba(255,92,114,0.6)',   speed: '2.6s' },
  };
  function setOrb(state) {
    const s = orbStates[state] || orbStates.idle;
    orbCore.style.background = s.core;
    orbCore.style.boxShadow = `0 0 14px 2px ${s.glow}, 0 0 28px 8px ${s.glow}`;
    orbCore.style.animationDuration = s.speed;
  }

  function tick() {
    const d = new Date();
    clockEl.textContent = d.toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    const up = Math.floor((Date.now() - startTime) / 1000);
    const h = String(Math.floor(up/3600)).padStart(2,'0');
    const m = String(Math.floor((up%3600)/60)).padStart(2,'0');
    const s = String(up%60).padStart(2,'0');
    document.getElementById('sessUptime').textContent = `${h}:${m}:${s}`;
  }
  setInterval(tick, 1000); tick();

  function logLine(msg) {
    const ts = new Date().toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    const line = document.createElement('div');
    const stamp = document.createElement('span'); stamp.textContent = `[${ts}] `;
    line.append(stamp, document.createTextNode(String(msg)));
    logBox.appendChild(line);
    logBox.scrollTop = logBox.scrollHeight;
    while (logBox.children.length > 80) logBox.removeChild(logBox.firstChild);
  }

  // ── Scroll Position State Controller ───────────────────
  const btnJumpBottom = document.getElementById('btnJumpBottom');
  const SCROLL_BOTTOM_THRESHOLD = 38;
  let userPinnedToBottom = true;
  let unreadWhileScrolledUp = 0;
  let programmaticScroll = false;

  function isNearBottom() {
    if (!chatEl) return true;
    const distance = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight;
    return distance <= SCROLL_BOTTOM_THRESHOLD;
  }

  function updateJumpBottomBtn() {
    if (!btnJumpBottom) return;
    if (!userPinnedToBottom && unreadWhileScrolledUp > 0) {
      btnJumpBottom.textContent = unreadWhileScrolledUp > 1
        ? `Yeni mesajlar (${unreadWhileScrolledUp}) ↓`
        : 'Yeni mesajlar ↓';
      btnJumpBottom.classList.add('show');
    } else {
      btnJumpBottom.classList.remove('show');
    }
  }

  function scrollToBottom(force = false) {
    if (!chatEl) return;
    if (!force && !userPinnedToBottom) return;
    programmaticScroll = true;
    chatEl.scrollTop = chatEl.scrollHeight;
    userPinnedToBottom = true;
    unreadWhileScrolledUp = 0;
    updateJumpBottomBtn();
    requestAnimationFrame(() => { programmaticScroll = false; });
  }

  chatEl.addEventListener('wheel', (e) => {
    if (e.deltaY < 0) {
      userPinnedToBottom = false;
    } else if (e.deltaY > 0 && isNearBottom()) {
      userPinnedToBottom = true;
      unreadWhileScrolledUp = 0;
      updateJumpBottomBtn();
    }
  }, { passive: true });

  chatEl.addEventListener('scroll', () => {
    if (programmaticScroll) return;
    if (isNearBottom()) {
      userPinnedToBottom = true;
      unreadWhileScrolledUp = 0;
      updateJumpBottomBtn();
    } else {
      userPinnedToBottom = false;
    }
  }, { passive: true });

  if (btnJumpBottom) {
    btnJumpBottom.addEventListener('click', () => {
      scrollToBottom(true);
    });
  }

  function formatMessageLabel(m) {
    if (!m) return 'QUARTZ';
    const sender = (m.sender || (m.role === 'user' ? 'user' : 'quartz')).toLowerCase();
    const recipient = (m.recipient || (m.metadata && m.metadata.recipient) || '').toLowerCase();
    if (sender === 'user' || m.role === 'user') {
      if (recipient && recipient !== 'all' && recipient !== 'user') {
        return `SEN → ${recipient.toUpperCase()}`;
      }
      return 'SEN';
    }
    const senderUp = sender.toUpperCase();
    if (recipient === 'codex' || recipient === 'antigravity') {
      return `${senderUp} → ${recipient.toUpperCase()}`;
    }
    if (recipient === 'all') {
      return `${senderUp} · GRUP`;
    }
    return senderUp;
  }

  function formatModelTagText(m) {
    if (!m || m.role === 'user') return '';
    const meta = m.metadata || {};
    const model = meta.model || m.model || '';
    const effort = meta.effort || m.effort || '';
    if (!model) return '';
    return effort ? `${model} · ${effort}` : model;
  }

  function agentMessageView(text, msg, detailLevel) {
    text = String(text || '');
    if (msg?.role === 'user') return {summary:text, details:'', state:''};
    const meta = msg?.metadata || {};
    const marker = /\r?\n\s*---TEKNIK_AYRINTILAR---\r?\n/;
    const match = marker.exec(text);
    const summary = match ? text.slice(0, match.index).trimEnd() : text;
    let details = match ? text.slice(match.index + match[0].length) : '';
    let state = ({failed:'Başarısız', cancelled:'Durduruldu', interrupted:'Önceki oturum kesildi; otomatik sürdürülmedi', blocked:'Henüz doğrulanmadı',
      awaiting_approval:'Kullanıcı onayı bekleniyor'})[msg?.status || meta.status] || '';
    if ((msg?.status || meta.status) === 'completed' && ['project','full'].includes(meta.permission_level)) {
      const check = meta.host_evidence?.source_validation;
      state = check?.status === 'FAILED' ? 'Ajan bitti; kaynak sözdizimi kontrolü başarısız.'
        : check?.status === 'VERIFIED' ? 'Python sözdizimi doğrulandı; çalışma/test başarısı doğrulanmış değil.'
        : 'Ajan yanıtı tamamlandı; bağımsız çalışma/test kanıtı yok.';
      if (meta.host_evidence?.historical) state = 'Önceki oturumun kaynak kanıtı: ' + state;
    }
    const evidence = {};
    for (const key of ['error','run_id','squad_task_id','checkpoint','files_changed','performance','permission_level','review_scope','host_evidence']) {
      if (meta[key] != null && meta[key] !== '') evidence[key] = meta[key];
    }
    if (Object.keys(evidence).length) details += (details ? '\n\n' : '') + JSON.stringify(evidence, null, 2);
    return {summary, details, state, open:detailLevel === 'technical'};
  }

  function renderMessageBody(bubble, text, msg) {
    const level = document.getElementById('responseDetail')?.value || 'short';
    const view = agentMessageView(text, msg, level);
    const key = JSON.stringify([text, view.details, view.state, level]);
    if (bubble.dataset.renderKey === key) return false;
    bubble.dataset.renderKey = key;
    bubble.replaceChildren();
    if (view.state) {
      const state = document.createElement('div'); state.textContent = view.state;
      state.style.cssText = 'font-size:11px;opacity:.8;margin-bottom:5px'; bubble.append(state);
    }
    const body = document.createElement('div'); body.textContent = view.summary; bubble.append(body);
    if (msg?.status === 'interrupted' && msg.id) {
      const resume = document.createElement('button'); resume.className = 'control-btn';
      resume.textContent = 'Yeni görev taslağı hazırla';
      resume.onclick = async () => {
        const result = await window.pywebview.api.chat_prepare_resume(currentConvId, msg.id);
        if (result.status !== 'ok') { logLine(String(result.data || 'Taslak hazırlanamadı')); return; }
        const fresh = await window.pywebview.api.chat_new('Devam taslağı',result.data.agent,result.data.project_id || '');
        if (fresh.status !== 'ok') { logLine(String(fresh.data || 'Yeni taslak sohbeti açılamadı')); return; }
        await loadActiveConversation(); // New conversation has no provider sessions.
        document.getElementById('mainPermissionLevel').value = 'read-only';
        updatePermissionSelectionHint();
        window.__writeConfirmed = false;
        inputEl.value = result.data.draft; inputEl.focus();
        logLine(result.data.warning); // Deliberately no sendAgentMessage call.
      };
      bubble.append(resume);
    }
    if (view.details) {
      const details = document.createElement('details'); details.className = 'technical-details'; details.open = view.open;
      const title = document.createElement('summary'); title.textContent = 'Teknik ayrıntılar';
      const full = document.createElement('pre'); full.textContent = view.details;
      full.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font:inherit';
      details.append(title, full); bubble.append(details);
    }
    return true;
  }

  function appendMsg(kind, label, text, msgId='', sender='bot', msgObj=null, skipScroll=false, forceScroll=false) {
    if (!programmaticScroll && !isNearBottom()) {
      userPinnedToBottom = false;
    }
    const prevScrollTop = chatEl.scrollTop;
    const wrap = document.createElement('div');
    const cleanSender = (sender || 'bot').toLowerCase();
    wrap.className = `msg ${kind} sender-${cleanSender}`;
    if (msgId) wrap.dataset.msgId = msgId;
    let ts = new Date().toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    if (msgObj && msgObj.timestamp) {
      try {
        const rawTs = msgObj.timestamp < 1e12 ? msgObj.timestamp * 1000 : msgObj.timestamp;
        ts = new Date(rawTs).toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
      } catch (_) {}
    }
    const seqNum = msgObj && (msgObj.sequence || (msgObj.metadata && msgObj.metadata.sequence));
    const escapeTag = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const seqHtml = seqNum ? `<span class="msg-seq-tag">#${escapeTag(seqNum)}</span>` : '';
    const modelTagText = formatModelTagText(msgObj);
    const modelHtml = modelTagText ? `<span class="msg-model-tag">${escapeTag(modelTagText)}</span>` : '';
    if (kind === 'sys') {
      wrap.innerHTML = '<div class="bubble"></div>';
      wrap.querySelector('.bubble').textContent = text;
    } else {
      const tagClass = 'tag-' + cleanSender;
      const senderHtml = label ? `<span class="msg-sender-tag ${escapeTag(tagClass)}">${escapeTag(label)}</span>` : '';
      wrap.innerHTML = `<div><div class="msg-meta">${senderHtml}${seqHtml}${modelHtml}<span class="msg-ts">${ts}</span></div><div class="bubble"></div></div>`;
      renderMessageBody(wrap.querySelector('.bubble'), text, msgObj);
    }
    chatEl.appendChild(wrap);
    if (!skipScroll) {
      if (forceScroll || userPinnedToBottom) {
        scrollToBottom(true);
      } else {
        chatEl.scrollTop = prevScrollTop;
        unreadWhileScrolledUp++;
        updateJumpBottomBtn();
      }
    }
    return wrap;
  }

  let activeTaskSquad = null;
  function updateSquadBadge(squad, conversationId = currentConvId) {
    const badge = document.getElementById('squadBadge');
    if (!badge || !squad) return;
    if (activeTaskSquad?.conversation_id === conversationId) squad = activeTaskSquad;
    if (squad.checking && !activeTaskSquad) {
      badge.classList.remove('warn');
      badge.textContent = 'Squad: Kontrol ediliyor';
      badge.title = 'Sohbet kullanılabilir; bağlantı arka planda doğrulanıyor.';
    } else if (squad.connected) {
      badge.classList.remove('warn');
      badge.textContent = 'Squad: Bağlı';
      badge.title = `Squad veritabanı aktif (${squad.version || 'v0.7.6'}) · ${squad.database || squad.db_path || ''}`;
    } else if (squad.mode === 'task-isolated' && squad.ready && !squad.error) {
      badge.classList.remove('warn');
      badge.textContent = 'Squad: Görevle bağlanır';
      badge.title = squad.message || 'Görev başladığında ayrı Squad veritabanı oluşturulur; mod klasörüne yazılmaz.';
    } else {
      badge.classList.add('warn');
      badge.textContent = 'Squad: Bağlantı Sorunu';
      badge.title = squad.error || squad.message || 'Squad veritabanına erişilemiyor';
    }
  }

  function syncConversationMessages(messages, replaceAll=false) {
    if (!Array.isArray(messages)) return;
    if (replaceAll) {
      chatEl.innerHTML = '';
      userPinnedToBottom = true;
      unreadWhileScrolledUp = 0;
      updateJumpBottomBtn();
    } else {
      if (!programmaticScroll && !isNearBottom()) {
        userPinnedToBottom = false;
      }
      chatEl.querySelectorAll('[data-welcome="1"]').forEach(el => el.remove());
    }
    const savedScrollTop = chatEl.scrollTop;
    let hadNewOrUpdatedContent = false;

    for (const m of messages) {
      if (!m || !m.id) continue;
      const cleanSender = (m.sender || (m.role === 'user' ? 'user' : 'bot')).toLowerCase();
      const statusVal = m.status || (m.metadata && m.metadata.status) || '';
      const kind = m.role === 'user' ? 'user' : (statusVal === 'failed' ? 'err' : 'bot');
      const label = formatMessageLabel(m);
      const displayContent = m.content || (statusVal === 'running' || statusVal === 'starting' ? '...' : '');
      let wrap = chatEl.querySelector(`.msg[data-msg-id="${m.id}"]`);
      if (!wrap) {
        wrap = appendMsg(kind, label, displayContent, m.id, cleanSender, m, true, false);
        hadNewOrUpdatedContent = true;
      } else {
        const desiredClass = `msg ${kind} sender-${cleanSender}`;
        if (wrap.className !== desiredClass) wrap.className = desiredClass;
        const tagEl = wrap.querySelector('.msg-sender-tag');
        if (tagEl) {
          const desiredTagClass = `msg-sender-tag tag-${cleanSender}`;
          if (tagEl.className !== desiredTagClass) tagEl.className = desiredTagClass;
          if (tagEl.textContent !== label) tagEl.textContent = label;
        }
        const seqNum = m.sequence || (m.metadata && m.metadata.sequence);
        let seqEl = wrap.querySelector('.msg-seq-tag');
        if (seqNum) {
          if (!seqEl) {
            seqEl = document.createElement('span');
            seqEl.className = 'msg-seq-tag';
            const metaEl = wrap.querySelector('.msg-meta');
            const tsEl = wrap.querySelector('.msg-ts');
            if (metaEl && tsEl) metaEl.insertBefore(seqEl, tsEl);
          }
          const seqText = `#${seqNum}`;
          if (seqEl.textContent !== seqText) seqEl.textContent = seqText;
        }
        const modelTagText = formatModelTagText(m);
        let modelEl = wrap.querySelector('.msg-model-tag');
        if (modelTagText) {
          if (!modelEl) {
            modelEl = document.createElement('span');
            modelEl.className = 'msg-model-tag';
            const metaEl = wrap.querySelector('.msg-meta');
            const tsEl = wrap.querySelector('.msg-ts');
            if (metaEl && tsEl) metaEl.insertBefore(modelEl, tsEl);
          }
          if (modelEl.textContent !== modelTagText) modelEl.textContent = modelTagText;
        }
        const bubbleEl = wrap.querySelector('.bubble');
        if (bubbleEl && renderMessageBody(bubbleEl, displayContent, m)) {
          hadNewOrUpdatedContent = true;
        }
      }
    }

    if (replaceAll || userPinnedToBottom) {
      scrollToBottom(true);
    } else {
      chatEl.scrollTop = savedScrollTop;
      if (hadNewOrUpdatedContent) {
        unreadWhileScrolledUp++;
        updateJumpBottomBtn();
      }
    }
  }

  function setThinking(v) {
    thinking = v;
    document.body.classList.toggle('thinking-active', !!v);
    thinkingRow.classList.toggle('show', v);
    sendBtn.classList.toggle('disabled', v);
    const btnCont = document.getElementById('btnContinueCollab');
    if (btnCont) btnCont.disabled = v;
    setOrb(v ? 'thinking' : 'idle');
    cancelBtn.style.display = v ? 'inline-block' : 'none';
    if (v) {
      requestStarted = Date.now();
      clearInterval(requestTimer);
      requestTimer = setInterval(() => {
        const sec = Math.floor((Date.now() - requestStarted) / 1000);
        thinkingText.textContent = `görev yürütülüyor... ${sec}s`;
      }, 1000);
    } else {
      clearInterval(requestTimer);
      thinkingText.textContent = 'işleniyor...';
    }
  }

  function appendActionCard(event) {
    const prevScrollTop = chatEl.scrollTop;
    const card = document.createElement('div'); card.className = 'action-card';
    const tools = event.tools || [event.tool];
    const title = document.createElement('div');
    title.textContent = `Onay gerekli [${event.risk}]: ${tools.filter(Boolean).join(', ')}`;
    const actions = document.createElement('div'); actions.className = 'actions';
    const approve = document.createElement('button'); approve.textContent = 'Onayla';
    const reject = document.createElement('button'); reject.textContent = 'İptal'; reject.className = 'danger';
    approve.onclick = async () => { card.remove(); await sendDirect(`onayla ${event.code}`); };
    reject.onclick = async () => { card.remove(); await sendDirect('iptal'); };
    actions.append(approve, reject); card.append(title, actions);
    chatEl.appendChild(card);
    if (userPinnedToBottom) scrollToBottom(true);
    else chatEl.scrollTop = prevScrollTop;
  }

  function renderUiEvents(events=[]) {
    for (const event of events) {
      if (event.type === 'confirmation') appendActionCard(event);
      else if (event.type === 'tool_running') logLine(`Araç: ${event.tool} çalışıyor`);
      else if (event.type === 'tool_completed') logLine(`✓ ${event.tool}: tamamlandı`);
      else if (event.type === 'tool_failed') logLine(`✗ ${event.tool}: ${event.error}`);
      else if (event.type === 'blocked') appendMsg('sys', '', `Güvenli Mod engelledi: ${(event.tools || [event.tool]).join(', ')}`);
      else if (event.type === 'cancelled') appendMsg('sys', '', 'İstek iptal edildi.');
      else if (event.type === 'rate_limit') appendMsg('sys', '', `API kotası doldu; ${Math.ceil(event.seconds)} saniye bekleniyor. İptal edebilirsin.`);
      else if (event.type === 'screen_advice') appendMsg('sys', '', `Ekran Rehberi: ${event.text}`);
      else if (event.type === 'task_created' || event.type === 'task_updated') renderTasks([event.task]);
    }
  }

  function renderTasks(tasks=[]) {
    if (!tasks.length) { taskList.textContent = 'Henüz görev yok'; return; }
    taskList.innerHTML = '';
    for (const task of tasks.slice(0, 5)) {
      const row = document.createElement('div'); row.style.marginBottom = '8px';
      const done = task.steps.filter(s => s.status === 'completed').length;
      const title = document.createElement('div');
      title.textContent = `${task.status === 'completed' ? '✓' : '◈'} ${task.title}`;
      const meta = document.createElement('div');
      meta.textContent = `${done}/${task.steps.length} adım · ${task.status}`;
      meta.style.color = 'var(--txt-faint)';
      row.append(title, meta);
      if (!['completed','failed','cancelled'].includes(task.status)) {
        const stop = document.createElement('button'); stop.className = 'control-btn';
        stop.textContent = 'İptal';
        stop.onclick = async () => { await window.pywebview.api.cancel_task(task.id); pollTasks(); };
        row.appendChild(stop);
      }
      taskList.appendChild(row);
    }
  }

  function renderResponse(resp) {
    renderUiEvents(resp.ui_events || []);
    if (resp.status === 'ok') appendMsg('bot', 'QUARTZ', resp.data);
    else appendMsg('err', 'HATA', resp.data || 'Bilinmeyen hata');
  }

  async function sendDirect(text) {
    setThinking(true);
    const resp = await window.pywebview.api.send_chat(text);
    setThinking(false);
    renderResponse(resp);
  }

  // ── Agent Chat & Model Selection Integration ────────────
  let conversationLoaded = false;
  const btnPanels = document.getElementById('btnPanels');
  const agyModelPill = document.getElementById('agyModelPill');
  const codexModelPill = document.getElementById('codexModelPill');
  const agyModelSelect = document.getElementById('agyModelSelect');
  const agyEffortSelect = document.getElementById('agyEffortSelect');
  const codexModelSelect = document.getElementById('codexModelSelect');
  const codexEffortSelect = document.getElementById('codexEffortSelect');
  const btnContinueCollab = document.getElementById('btnContinueCollab');

  if (btnPanels) {
    btnPanels.addEventListener('click', () => {
      const shown = document.body.classList.toggle('show-panels');
      btnPanels.classList.toggle('active', shown);
    });
  }

  function populateSelectOptions(selectEl, items, valueKey='id', labelKey='label') {
    if (!selectEl || !Array.isArray(items) || !items.length) return;
    if (document.activeElement === selectEl) return;
    const prevValue = selectEl.value;
    const sig = items.map(it => typeof it === 'string' ? it : `${it[valueKey]}:${it[labelKey]}`).join('|');
    if (selectEl.dataset.optionsSig === sig) return;
    selectEl.dataset.optionsSig = sig;
    selectEl.innerHTML = '';
    for (const item of items) {
      const opt = document.createElement('option');
      if (typeof item === 'string') {
        opt.value = item;
        opt.textContent = item;
      } else {
        opt.value = item[valueKey];
        opt.textContent = item[labelKey] || item[valueKey];
        if (item.description) opt.title = item.description;
      }
      selectEl.appendChild(opt);
    }
    if (prevValue && Array.from(selectEl.options).some(o => o.value === prevValue)) {
      selectEl.value = prevValue;
    }
  }

  function syncModelCatalogAndSelection(modelsCatalog, convModels) {
    if (modelsCatalog) {
      if (modelsCatalog.antigravity) {
        populateSelectOptions(agyModelSelect, modelsCatalog.antigravity.models || []);
        populateSelectOptions(agyEffortSelect, modelsCatalog.antigravity.efforts || []);
      }
      if (modelsCatalog.codex) {
        populateSelectOptions(codexModelSelect, modelsCatalog.codex.models || []);
        populateSelectOptions(codexEffortSelect, modelsCatalog.codex.efforts || []);
      }
    }
    if (convModels) {
      if (convModels.antigravity) {
        if (agyModelSelect && document.activeElement !== agyModelSelect && convModels.antigravity.model) {
          if (!Array.from(agyModelSelect.options).some(o => o.value === convModels.antigravity.model)) {
            const extra = document.createElement('option');
            extra.value = convModels.antigravity.model;
            extra.textContent = convModels.antigravity.model;
            agyModelSelect.appendChild(extra);
          }
          agyModelSelect.value = convModels.antigravity.model;
        }
        if (agyEffortSelect && document.activeElement !== agyEffortSelect && convModels.antigravity.effort) {
          agyEffortSelect.value = convModels.antigravity.effort;
        }
      }
      if (convModels.codex) {
        if (codexModelSelect && document.activeElement !== codexModelSelect && convModels.codex.model) {
          if (!Array.from(codexModelSelect.options).some(o => o.value === convModels.codex.model)) {
            const extra = document.createElement('option');
            extra.value = convModels.codex.model;
            extra.textContent = convModels.codex.model;
            codexModelSelect.appendChild(extra);
          }
          codexModelSelect.value = convModels.codex.model;
        }
        if (codexEffortSelect && document.activeElement !== codexEffortSelect && convModels.codex.effort) {
          codexEffortSelect.value = convModels.codex.effort;
        }
      }
    }
  }

  async function saveAgentModelSelection(agent, changedFromModelSelect=false) {
    if (!currentConvId) return;
    let modelVal = '';
    let effortVal = '';
    if (agent === 'antigravity') {
      modelVal = agyModelSelect ? agyModelSelect.value : '';
      if (changedFromModelSelect && agyEffortSelect && modelVal) {
        for (const eff of ['low', 'medium', 'high', 'xhigh', 'max']) {
          if (modelVal.endsWith('-' + eff)) {
            agyEffortSelect.value = eff;
            break;
          }
        }
      }
      effortVal = agyEffortSelect ? agyEffortSelect.value : '';
    } else if (agent === 'codex') {
      modelVal = codexModelSelect ? codexModelSelect.value : '';
      effortVal = codexEffortSelect ? codexEffortSelect.value : '';
    }
    try {
      await window.pywebview.api.chat_set_model(currentConvId, agent, modelVal, effortVal);
      logLine(`${agent.toUpperCase()} modeli güncellendi: ${modelVal} (${effortVal})`);
    } catch (e) {
      logLine(`Model kaydetme hatası: ${e}`);
    }
  }

  if (agyModelSelect) agyModelSelect.addEventListener('change', () => saveAgentModelSelection('antigravity', true));
  if (agyEffortSelect) agyEffortSelect.addEventListener('change', () => saveAgentModelSelection('antigravity', false));
  if (codexModelSelect) codexModelSelect.addEventListener('change', () => saveAgentModelSelection('codex', true));
  if (codexEffortSelect) codexEffortSelect.addEventListener('change', () => saveAgentModelSelection('codex', false));

  function syncAgentUI(agent) {
    if (!agent) return;
    if (mainAgentSelect) mainAgentSelect.value = agent;
    document.querySelectorAll('.agent-seg-btn[data-agent]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.agent === agent);
    });
    const isCollab = agent === 'collaboration';
    if (agyModelPill) {
      agyModelPill.classList.toggle('active-agy', agent === 'antigravity' || isCollab);
    }
    if (codexModelPill) {
      codexModelPill.classList.toggle('active-codex', agent === 'codex' || isCollab);
    }
    if (btnContinueCollab) {
      btnContinueCollab.style.display = isCollab ? 'inline-block' : 'none';
    }
  }

  document.querySelectorAll('.agent-seg-btn[data-agent]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const agent = btn.dataset.agent;
      syncAgentUI(agent);
      if (currentConvId) {
        await window.pywebview.api.chat_set_agent(currentConvId, agent);
      }
      logLine('Aktif ajan değiştirildi: ' + agent.toUpperCase());
    });
  });

  if (btnContinueCollab) {
    btnContinueCollab.addEventListener('click', async () => {
      if (thinking || !currentConvId) return;
      try {
        setThinking(true);
        thinkingText.textContent = 'Ajanlar tartışmayı 1 tur daha sürdürüyor...';
        const resp = await window.pywebview.api.chat_continue(currentConvId);
        if (resp.status !== 'ok') {
          setThinking(false);
          appendMsg('err', 'HATA', resp.data || 'Tartışma sürdürülemedi');
          return;
        }
        await pollAgentTurn();
        if (chatPollInterval) clearInterval(chatPollInterval);
        chatPollInterval = setInterval(pollAgentTurn, 120);
      } catch (e) {
        setThinking(false);
        logLine('Tartışma sürdürme hatası: ' + String(e));
      }
    });
  }

  let writerRecoveryKey = '';
  function renderWriterRecovery(data) {
    data = data || {};
    const key = JSON.stringify(data); if (key === writerRecoveryKey) return;
    writerRecoveryKey = key;
    const panel = document.getElementById('writerRecoveryPanel');
    const body = document.getElementById('writerRecoveryBody');
    panel.hidden = !data.blocked; body.replaceChildren();
    if (data.error) { const text=document.createElement('p'); text.textContent='Yazıcı kaydı okunamıyor: '+data.error; body.append(text); }
    for (const claim of data.claims || []) {
      const row=document.createElement('div'); const label=document.createElement('p');
      label.textContent=`${claim.provider || 'Ajan'} · ${claim.project} · ${claim.stage}`;
      const inspect=document.createElement('button'); inspect.className='control-btn'; inspect.textContent='Süreç durumunu incele';
      const details=document.createElement('pre'); details.style.whiteSpace='pre-wrap';
      const confirmation=document.createElement('label'); const check=document.createElement('input'); check.type='checkbox';
      confirmation.append(check,document.createTextNode('Harici süreçleri ve dosya durumunu kontrol ettim.'));
      const ack=document.createElement('button'); ack.className='control-btn'; ack.textContent='İncelemeyi onayla; engeli kaldır'; ack.disabled=true;
      let inspected=false; check.onchange=()=>{ ack.disabled=!inspected || !check.checked; };
      inspect.onclick=async()=>{
        const result=await window.pywebview.api.writer_recovery_inspect(claim.id);
        details.textContent=JSON.stringify(result.data,null,2); inspected=result.status==='ok';
        ack.disabled=!inspected || !check.checked;
      };
      ack.onclick=async()=>{
        if (!inspected || !check.checked || !window.confirm('Eski görev yeniden çalıştırılmayacak; izin verilmeyecek. Harici etkinliği kontrol ettiyseniz yalnız engel kaydını kaldırın.')) return;
        const result=await window.pywebview.api.writer_recovery_acknowledge(claim.id,true,true);
        if (result.status!=='ok') { details.textContent=String(result.data); return; }
        await loadActiveConversation();
      };
      row.append(label,inspect,details,confirmation,ack); body.append(row);
    }
  }

  function agentProgressText(progress) {
    const names={codex:'Codex',antigravity:'Antigravity'};
    const states={running:'çalışıyor',completed:'tamamlandı',failed:'başarısız',cancelling:'durduruluyor',cancelled:'durduruldu'};
    return Object.entries(progress || {}).filter(([key])=>key in names)
      .map(([key,value])=>`${names[key]}: ${states[value.status] || 'hazırlanıyor'}${value.status==='running' && value.step ? ' — '+value.step : ''}`).join(' | ');
  }

  async function loadActiveConversation() {
    try {
      const resp = await window.pywebview.api.chat_status();
      if (resp.status !== 'ok') return false;
      const data = resp.data;
      renderWriterRecovery(data.writer_recovery);
      document.getElementById('responseDetail').value = data.preferences?.response_detail || 'short';
      savedResponseDetail = document.getElementById('responseDetail').value;
      updateAntigravitySafety(data.agents?.antigravity);
      if (data.squad) updateSquadBadge(data.squad, data.active_conversation?.id);
      const conv = data.active_conversation;
      const projects = Array.isArray(data.projects) ? data.projects : [];
      mainProjectSelect.replaceChildren();
      for (const project of projects) {
        const option = document.createElement('option');
        option.value = project.id;
        option.textContent = project.name;
        option.title = project.path;
        mainProjectSelect.append(option);
      }
      if (!conv) return false;
      conversationLoaded = true;
      currentConvId = conv.id;
      renderConversationNavigation(data.conversations || []);
      chatConvTitle.textContent = conv.title || 'Yeni Sohbet';
      if (conv.agent) syncAgentUI(conv.agent);
      syncModelCatalogAndSelection(data.models, conv.models);
      const activeProjectId = conv.project_id || 'squad-pilot';
      mainProjectSelect.value = activeProjectId;
      if (chatProjectTag) chatProjectTag.textContent = projects.find(p => p.id === activeProjectId)?.name || activeProjectId;
      const permSelect = document.getElementById('mainPermissionLevel');
      if (permSelect) {
        permSelect.value = conv.permission_level || data.preferences?.permission_level || 'full';
        updatePermissionSelectionHint();
        window.__writeConfirmed = true;
      }
      const writer = data.single_writer || {};
      writerBadge.style.display = writer.locked ? 'inline-block' : 'none';
      writerBadge.textContent = writer.locked ? `Yazıcı: ${writer.agent || 'ajan'}` : '';

      // Sohbet mesajlarını render et
      chatEl.innerHTML = '';
      userPinnedToBottom = true;
      unreadWhileScrolledUp = 0;
      updateJumpBottomBtn();
      if (!conv.messages || !conv.messages.length) {
        const welcome = appendMsg('bot', 'QUARTZ', 'Merhaba! Ben Quartz. Doğrudan Antigravity ve Codex ajanlarıyla çalışıyorum.\nÜstteki seçiciden Antigravity, Codex veya Birlikte modunu seçip mesaj gönderebilirsin.', '', 'quartz');
        welcome.dataset.welcome = '1';
      } else {
        syncConversationMessages(conv.messages, true);
      }
      return true;
    } catch (e) {
      logLine('Sohbet yüklenemedi: ' + String(e));
      return false;
    }
  }

  let chatPollBusy = false;
  async function pollAgentTurn() {
    if (chatPollBusy) return;
    chatPollBusy = true;
    try {
      const poll = await window.pywebview.api.chat_poll();
      if (poll.status !== 'ok') return;
      const data = poll.data;
      if (!data) return;
      const writer = data.single_writer || {};
      writerBadge.style.display = writer.locked ? 'inline-block' : 'none';
      writerBadge.textContent = writer.locked ? `Yazıcı: ${writer.agent || 'ajan'}` : '';

      if (Array.isArray(data.messages) && data.messages.length > 0) {
        syncConversationMessages(data.messages, false);
      } else if (activeBotBubble && data.content) {
        const prevScrollTop = chatEl.scrollTop;
        renderMessageBody(activeBotBubble, data.content, {metadata:data.metadata});
        if (userPinnedToBottom) scrollToBottom(true);
        else chatEl.scrollTop = prevScrollTop;
      }

      if (data.metadata) {
        if (Object.keys(data.agent_progress || {}).length) {
          thinkingText.textContent = agentProgressText(data.agent_progress);
        } else if (data.metadata.progress_step) {
          thinkingText.textContent = data.metadata.progress_step;
        } else if (Array.isArray(data.metadata.progress) && data.metadata.progress.length > 0) {
          thinkingText.textContent = data.metadata.progress[data.metadata.progress.length - 1];
        }
      }

      // İşlem aktif değilse (tamamlandı / iptal / hata) en son metin işlendikten sonra polling'i kapat
      if (!data.active) {
        if (chatPollInterval) {
          clearInterval(chatPollInterval);
          chatPollInterval = null;
        }
        setThinking(false);
        activeBotBubble = null;
      }
    } catch (_) {}
    finally { chatPollBusy = false; }
  }

  let savedResponseDetail = 'short';
  document.getElementById('responseDetail').addEventListener('change', async (event) => {
    const selected = event.target.value;
    try {
      const result = await window.pywebview.api.chat_response_detail(selected);
      if (result.status !== 'ok') throw new Error(result.data || 'Ayar kaydedilemedi');
      savedResponseDetail = selected;
      document.querySelectorAll('.technical-details').forEach(item => { item.open = selected === 'technical'; });
    } catch (error) {
      event.target.value = savedResponseDetail;
      logLine('Yanıt ayrıntısı kaydedilemedi: ' + String(error));
    }
  });

  btnNewChat.addEventListener('click', async () => {
    try {
      if (chatPollInterval) {
        clearInterval(chatPollInterval);
        chatPollInterval = null;
      }
      setThinking(false);
      activeBotBubble = null;
      const agent = mainAgentSelect.value || 'antigravity';
      const resp = await window.pywebview.api.chat_new('Yeni Sohbet', agent, mainProjectSelect.value);
      if (resp.status === 'ok') {
        await loadActiveConversation();
        logLine('Yeni sohbet başlatıldı.');
      }
    } catch (e) { logLine('Hata: ' + String(e)); }
  });

  mainProjectSelect.addEventListener('change', async () => {
    const response = await window.pywebview.api.project_select(mainProjectSelect.value);
    if (response.status !== 'ok') {
      logLine('Proje değiştirilemedi: ' + response.data);
    }
    await loadActiveConversation();
  });

  btnAddProject.addEventListener('click', async () => {
    btnAddProject.disabled = true;
    try {
      const response = await window.pywebview.api.project_pick_add();
      if (response.status === 'ok') await loadActiveConversation();
      else if (response.status !== 'cancelled') logLine('Proje eklenemedi: ' + response.data);
    } catch (error) { logLine('Proje eklenemedi: ' + String(error)); }
    finally { btnAddProject.disabled = false; }
  });

  mainAgentSelect.addEventListener('change', async () => {
    const agent = mainAgentSelect.value;
    syncAgentUI(agent);
    if (!currentConvId) return;
    await window.pywebview.api.chat_set_agent(currentConvId, agent);
    logLine('Aktif ajan değiştirildi: ' + agent.toUpperCase());
  });

  cancelBtn.addEventListener('click', async () => {
    cancelBtn.disabled = true;
    thinkingText.textContent = 'iptal ediliyor...';
    try {
      await window.pywebview.api.chat_cancel();
      await window.pywebview.api.cancel_request();
    } catch (_) {}
    setTimeout(() => { cancelBtn.disabled = false; setThinking(false); }, 1000);
  });

  function updatePermissionSelectionHint() {
    const select=document.getElementById('mainPermissionLevel');
    const hint=document.getElementById('permissionSelectionHint');
    const labels={'read-only':'Tam Yetki',project:'Proje Yetkisi',full:'◉ Tam Yetki Aktif'};
    const level=select?.value || 'full';
    if(hint){hint.textContent=`${labels[level] || labels['full']}`;
      hint.title='Tek Yetki Sistemi (Tam Yetki) kalıcı olarak aktiftir.';}
    window.__writeConfirmed=false;
  }
  const permissionSelect=document.getElementById('mainPermissionLevel');
  if(permissionSelect){permissionSelect.addEventListener('change',updatePermissionSelectionHint);updatePermissionSelectionHint();}

  let coordinationRouting = false;
  window.__writeConfirmed = true;
  async function sendAgentMessage() {
    const text = inputEl.value.trim();
    if (!text || coordinationRouting) return;
    // Freeze the selected mode for THIS submitted message, not a later poll
    // or a dropdown edit while routing is awaiting the backend.
    const selectedPermissionLevel=document.getElementById('mainPermissionLevel')?.value || 'read-only';
    coordinationRouting = true;
    const wasThinking = typeof thinking !== 'undefined' ? thinking : false;
    if (!wasThinking && typeof setThinking === 'function') {
      setThinking(true);
      if (typeof thinkingText !== 'undefined' && thinkingText) thinkingText.textContent = 'Görev hazırlanıyor...';
    }
    let coordinated;
    try { coordinated = await window.pywebview.api.coordination_route(text, currentConvId, mainProjectSelect.value,
      {codex:{model:codexModelSelect.value,effort:codexEffortSelect.value},antigravity:{model:agyModelSelect.value,effort:agyEffortSelect.value}},selectedPermissionLevel); }
    catch(e) { appendMsg('err','QUARTZ',String(e)); return; }
    finally {
      coordinationRouting = false;
      if (!wasThinking && typeof setThinking === 'function') setThinking(false);
    }
    if (coordinated.status !== 'ok') { appendMsg('err','QUARTZ',coordinated.data); return; }
    if (coordinated.data?.handled) {
      inputEl.value = '';
      if (coordinated.data.diagnostics_repair) {
        appendMsg('user', 'SEN', coordinated.data.user_text, '', 'user', null, false, true);
        renderRepairPlan(coordinated.data.repair_plan);
        return;
      }
      if (coordinated.data.diagnostics_knowledge) {
        appendMsg('user', 'SEN', coordinated.data.user_text, '', 'user', null, false, true);
        if (typeof renderLearnedApplicationsCard === 'function') {
          renderLearnedApplicationsCard(coordinated.data.learned_items || []);
        }
        return;
      }
      if (coordinated.data.diagnostics_started || coordinated.data.diagnostics_cancelled || coordinated.data.diagnostics_status) {
        if (coordinated.data.user_text && typeof appendMsg === 'function') appendMsg('user', 'SEN', coordinated.data.user_text, '', 'user', null, false, true);
        const diagJob = coordinated.data.diagnostics || coordinated.data.diagnostics_status;
        if (!diagJob) appendMsg('bot', 'QUARTZ', 'Dosya seçimi iptal edildi; inceleme başlatılmadı.');
        if (typeof renderSelfDiagnosticsCard === 'function' && diagJob) renderSelfDiagnosticsCard(diagJob);
        if (typeof scheduleSelfDiagnosticsPoll === 'function' && diagJob?.state === 'running' && diagJob?.id) scheduleSelfDiagnosticsPoll(diagJob.id);
        return;
      }
      if(coordinated.data.permission_status || coordinated.data.desktop_help || coordinated.data.continuation_status) await loadActiveConversation();
      else if(!coordinated.data.natural_started) appendMsg('bot','QUARTZ',coordinated.data.stopped ? 'Görev durduruldu.' : 'Talimat iletildi; yetki kapsamı değişmedi.');
      await refreshDesktopTaskState();
      await pollNaturalTask();
      return;
    }
    if (thinking) return;

    const writeSelect = document.getElementById('mainPermissionLevel');
    const conversationOnly = coordinated.data?.intent === 'conversation';
    const permissionLevel = conversationOnly ? 'read-only' : selectedPermissionLevel;
    const isWrite = permissionLevel === 'full' || permissionLevel === 'project';
    const confirmWrite = isWrite;
    const agent = mainAgentSelect ? mainAgentSelect.value : 'antigravity';
    if (isWrite && !window.__writeConfirmed) {
      const ok = window.confirm(permissionLevel === 'full'
        ? 'Bu görev için TAM sistem erişimi verilsin mi? Ajan proje dışındaki dosyalara da erişebilir. Yazma öncesi proje checkpoint’i alınır; bu tüm bilgisayarın yedeği değildir.'
        : 'Bu görev için proje dosyalarını değiştirme yetkisi verilsin mi? Önce checkpoint alınır. Birlikte modunda Codex yazar, Antigravity inceleme yapar.');
      if (!ok) return;
      window.__writeConfirmed = true;
    }

    inputEl.value = '';
    inpHistory.push(text);
    histCursor = -1;
    msgCount++;
    document.getElementById('sessMsgs').textContent = msgCount;

    chatEl.querySelectorAll('[data-welcome="1"]').forEach(el => el.remove());
    const userWrap = appendMsg('user', 'SEN', text, '', 'user', null, false, true);
    setThinking(true);

    logLine(`Ajan (${agent.toUpperCase()}) göreve başladı...`);

    const initialSender = agent === 'collaboration' ? 'codex' : agent;
    const initialLabel = agent === 'collaboration' ? 'CODEX · GRUP' : agent.toUpperCase();
    const botWrap = appendMsg('bot', initialLabel, '...', '', initialSender, null, false, true);
    activeBotBubble = botWrap.querySelector('.bubble');

    try {
      const resp = await window.pywebview.api.chat_send(text, agent, currentConvId, isWrite, confirmWrite, permissionLevel, selectedPermissionLevel);
      if (resp.status !== 'ok') {
        setThinking(false);
        activeBotBubble.textContent = 'Hata: ' + (resp.data || 'Bilinmeyen hata');
        setOrb('error');
        setTimeout(() => setOrb('idle'), 2500);
        return;
      }
      if (resp.data) {
        if (resp.data.conversation_id) currentConvId = resp.data.conversation_id;
        if (resp.data.user_message && resp.data.user_message.id) {
          userWrap.dataset.msgId = resp.data.user_message.id;
        }
        if (resp.data.assistant_message && resp.data.assistant_message.id) {
          botWrap.dataset.msgId = resp.data.assistant_message.id;
          const firstMsg = resp.data.assistant_message;
          const tagEl = botWrap.querySelector('.msg-sender-tag');
          if (tagEl && firstMsg.sender) {
            tagEl.className = `msg-sender-tag tag-${firstMsg.sender}`;
            tagEl.textContent = formatMessageLabel(firstMsg);
          }
        }
      }
      await pollAgentTurn();
      if (chatPollInterval) clearInterval(chatPollInterval);
      chatPollInterval = setInterval(pollAgentTurn, 120);
    } catch (e) {
      setThinking(false);
      activeBotBubble.textContent = 'Hata: ' + String(e);
    }
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || thinking) return;
    inputEl.value = '';
    inpHistory.push(text);
    histCursor = -1;
    msgCount++;
    document.getElementById('sessMsgs').textContent = msgCount;
    appendMsg('user', 'SEN', text);
    setThinking(true);
    logLine('Gönderildi: ' + text.slice(0, 50));
    try {
      const resp = await window.pywebview.api.send_chat(text);
      setThinking(false);
      if (resp.status === 'ok') {
        renderResponse(resp);
        logLine('Yanıt alındı (' + resp.data.length + ' karakter)');
      } else {
        appendMsg('err', 'HATA', resp.data || 'Bilinmeyen hata');
        setOrb('error');
        logLine('HATA: ' + (resp.data || '').slice(0, 50));
        setTimeout(() => setOrb('idle'), 2000);
      }
    } catch (e) {
      setThinking(false);
      appendMsg('err', 'HATA', String(e));
    }
  }

  sendBtn.addEventListener('click', sendAgentMessage);

  let navigationConversations = [];
  let deletionPending = false;
  async function requestChatDeletion(conversations, projectId = null) {
    if (deletionPending || thinking || !conversations.length) return;
    const projectName = mainProjectSelect.selectedOptions[0]?.textContent || 'Seçili proje';
    const message = projectId
      ? `“${projectName}” projesinin ${conversations.length} sohbeti silinsin mi?`
      : `“${conversations[0].title || 'Yeni sohbet'}” sohbeti silinsin mi?`;
    if (!window.confirm(message + '\nProje dosyaları silinmez. Sohbetlerin yerel kurtarma yedeği tutulur.')) return;
    deletionPending = true;
    try {
      const result = projectId
        ? await window.pywebview.api.chat_delete_project(projectId, conversations.map(c => c.id), true)
        : await window.pywebview.api.chat_delete(conversations[0].id, true);
      if (result.status !== 'ok') throw new Error(result.data || 'Sohbet silinemedi');
      if (chatPollInterval) { clearInterval(chatPollInterval); chatPollInterval = null; }
      activeBotBubble = null;
      await loadActiveConversation();
      logLine(`${result.data.deleted_count} sohbet silindi; yerel kurtarma yedeği oluşturuldu.`);
    } catch (error) {
      appendMsg('err', 'QUARTZ', String(error));
    } finally { deletionPending = false; }
  }

  function renderConversationNavigation(items) {
    const list=document.getElementById('conversationList'); if(!list)return;
    navigationConversations = items || [];
    const key=JSON.stringify([currentConvId,(items||[]).map(c=>[c.id,c.title,c.project_id])]);
    if(list.dataset.key===key)return;list.dataset.key=key;
    const top=list.scrollTop;list.replaceChildren();
    for(const conv of items||[]){
      const row=document.createElement('div');row.className='conversation-row';
      const button=document.createElement('button');button.className='conversation-entry'+(conv.id===currentConvId?' active':'');
      button.textContent=conv.title||'Yeni sohbet';button.title=button.textContent;
      button.onclick=async()=>{if(thinking||deletionPending)return;const result=await window.pywebview.api.chat_select(conv.id);if(result.status==='ok')await loadActiveConversation();};
      const remove=document.createElement('button');remove.className='conversation-delete';remove.textContent='×';
      remove.title='Sohbeti sil';remove.setAttribute('aria-label',`${button.textContent} sohbetini sil`);
      remove.onclick=()=>requestChatDeletion([conv]);row.append(button,remove);list.append(row);
    }
    list.scrollTop=top;
  }

  function initializeWorkspaceLayout() {
    const left=document.querySelector('.rail.left'), right=document.querySelector('.rail.right');
    const old=document.createElement('details');old.id='legacyTools';
    const summary=document.createElement('summary');summary.textContent='Eski araçlar ve gelişmiş teşhis';old.append(summary);
    [...left.children].forEach(item=>old.append(item));right.append(old);
    for(const id of ['btnWake','btnTts'])old.append(document.getElementById(id));
    const heading=document.createElement('div');heading.className='workspace-nav-title';heading.textContent='Çalışma alanı';
    const project=document.createElement('div');project.className='workspace-project';project.append(mainProjectSelect,document.getElementById('btnAddProject'));
    const newChat=document.createElement('button');newChat.className='conversation-entry';newChat.textContent='＋ Yeni sohbet';newChat.onclick=()=>document.getElementById('btnNewChat').click();
    const title=document.createElement('div');title.className='workspace-nav-title';title.textContent='Sohbetler';
    const clearProject=document.createElement('button');clearProject.id='btnDeleteProjectChats';
    clearProject.className='project-chats-delete';clearProject.textContent='Bu projenin sohbetlerini temizle';
    clearProject.onclick=()=>requestChatDeletion(navigationConversations.filter(c=>(c.project_id||'squad-pilot')===mainProjectSelect.value),mainProjectSelect.value);
    const history=document.createElement('div');history.id='conversationList';history.className='conversation-list';
    const setting=document.getElementById('responseDetail').closest('.card');
    left.append(heading,project,newChat,title,history,clearProject,setting);
    document.getElementById('btnPanels').textContent='Gelişmiş';
    document.getElementById('btnAgentCenter').textContent='Ajan tanılama';
    document.getElementById('signatureIntro')?.remove();
    inputEl.placeholder='Ekibe yazın veya görev verin…';
  }
  initializeWorkspaceLayout();

  let desktopView={code:'normal',stop_ref:null};
  function renderDesktopTaskState(view) {
    desktopView=view;
    document.getElementById('desktopTaskBar').dataset.state=view.code;
    document.getElementById('desktopTaskLabel').textContent=view.label;
    document.getElementById('desktopTaskDetail').textContent=(view.conversation_id&&view.conversation_id!==currentConvId?'Başka bir sohbetin görevi. ':'')+view.detail;
    const stop=document.getElementById('btnDesktopTaskStop');
    stop.hidden=!view.stop_ref;stop.disabled=!view.stop_ref;
    const isControlActive=(view.code==='active'||view.code==='preparing')&&!!view.stop_ref;
    document.body.classList.toggle('screen-control-active',isControlActive);
    const hud=document.getElementById('screenControlHud');
    if(hud){
      hud.hidden=!isControlActive;
      const hudSub=document.getElementById('screenControlHudSub');
      if(hudSub)hudSub.textContent=view.label||'Yalnız bu tuşla durdurulur';
    }
    for(const card of document.querySelectorAll('[data-desktop-plan]')) {
      const stillPending=card.dataset.desktopPlan===view.pending_id;
      const start=card.querySelector('[data-desktop-approve]');
      if(start&&!stillPending){start.disabled=true;start.title='Bu kart artık geçerli bir onay isteği değil.';}
      const abandon=card.querySelector('[data-desktop-abandon]');if(abandon)abandon.disabled=!stillPending;
    }
  }
  document.getElementById('btnHudStopTask')?.addEventListener('click',()=>{
    document.getElementById('btnDesktopTaskStop')?.click();
  });
  async function refreshDesktopTaskState() {
    try {
      const r=await window.pywebview.api.desktop_task_status();
      if(r.status!=='ok')throw new Error(r.data);
      renderDesktopTaskState(r.data);
    } catch(e) {
      document.getElementById('desktopTaskLabel').textContent='Masaüstü durumu okunamıyor';
      document.getElementById('desktopTaskDetail').textContent='Erişim var veya bırakıldı varsayılmıyor. '+String(e);
    }
  }
  document.getElementById('btnDesktopTaskStop').onclick=async()=>{
    const ref=desktopView.stop_ref;if(!ref)return;
    const r=await window.pywebview.api.desktop_task_stop(ref);
    if(r.status!=='ok')appendMsg('err','QUARTZ',r.data);
    await refreshDesktopTaskState();
  };

  let coordinationTimer=null;
  async function pollNaturalTask() {
    const r=await window.pywebview.api.natural_status();
    if(r.status!=='ok')return;
    const state=r.data, pending=state.pending;
    activeTaskSquad = state.active && state.squad && state.job?.conversation_id === currentConvId
      ? {...state.squad, conversation_id:state.job.conversation_id} : null;
    if (activeTaskSquad) updateSquadBadge(activeTaskSquad);
    for(const card of document.querySelectorAll('[data-natural-permission]')) {
      if(!pending||card.dataset.naturalPermission!==pending.id||pending.conversation_id!==currentConvId)card.remove();
    }
    if(!pending||pending.conversation_id!==currentConvId||document.querySelector(`[data-natural-permission="${pending.id}"]`))return;
    if(document.getElementById('mainPermissionLevel')?.value==='full' && !['warband','elevation'].includes(pending.kind)) {
      try {
        const autoReply=await window.pywebview.api.natural_approve(pending.id,true);
        if(autoReply.status==='ok'){
          logLine('Tam Yetki aktif: Masaüstü kapsamı otomatik onaylandı.');
          await refreshDesktopTaskState();
          return;
        }
      } catch(_) {}
    }
    const panel=document.createElement('section');panel.className='coordination-card';panel.dataset.naturalPermission=pending.id;
    panel.setAttribute('aria-label','Görev için uygulama izni');
    const title=document.createElement('strong');title.textContent=pending.kind==='warband'?'Warband görev izni gerekiyor':'Uygulama izni gerekiyor';
    const reason=document.createElement('p');reason.textContent=pending.reason;
    const summary=document.createElement('p');
    summary.textContent=`${pending.operator==='codex'?'Codex':'Gemini'} yalnız ${pending.targets.map(t=>t.title).join(', ')||'onaylı günlüklerde'} çalışacak. `+
      (pending.logs.length?`Salt okunur günlükler: ${pending.logs.join(', ')}. `:'')+
      'Süre bitince veya Durdur ile erişim bırakılır. Yeni kapsam ayrıca sorulur.';
    if(pending.kind==='warband') {
      const labels={inspect:'Kaynak, RGL ve test kanıtlarını inceleme',develop:'UM yedeği ardından kaynak düzeltme ve resmî derleme',play:'Gerçek oyun kontrolü ve geçici Standard150 ortak ayarı'};
      summary.textContent=(pending.capabilities||[]).map(c=>labels[c]||c).join(' · ')+'. Orijinal kayıtlar yazmaya karşı kilitlenir. İkinci ajan salt okunur inceleme yapar. Durdur girdiyi bırakır; açık oyun kapanana kadar ayar geri yükleme izleyicisi sürer.';
    }
    const details=document.createElement('details');const label=document.createElement('summary');label.textContent='İzin kapsamı ve teknik ayrıntılar';
    const trace=document.createElement('pre');trace.textContent=JSON.stringify({targets:pending.targets,logs:pending.logs,capabilities:pending.capabilities,expires_at:pending.expires_at},null,2);
    details.append(label,trace);
    const approve=document.createElement('button');approve.textContent='Bu görev için izin ver';
    const deny=document.createElement('button');deny.textContent='İzin verme';
    const status=document.createElement('p');
    if(pending.kind==='elevation') {
      title.textContent='Windows yönetici onayı gerekiyor';
      summary.textContent=(pending.launch?.exe || 'Doğrulanmış uygulama yolu bulunamadı')+
        '\nUAC onayını Windows ekranında siz verirsiniz. Quartz yönetici yapılmaz. Bu onay yalnız başlatma içindir; ajana ayar değiştirme talimatı vermez.';
      trace.textContent=JSON.stringify({launch:pending.launch,phase:pending.phase,expires_at:pending.expires_at},null,2);
      approve.textContent='Windows UAC isteğini aç';
      approve.disabled=pending.phase==='prompting'||!pending.launch;
      if(pending.phase==='prompting')status.textContent='Windows yanıtı bekleniyor. Açılmış UAC istemini iptal etmek için Windows ekranında Hayır seçin.';
    }
    const decide=async(accept)=>{
      approve.disabled=true;deny.disabled=true;
      let resolved=false;
      try {
        const reply=await window.pywebview.api[accept?'natural_approve':'natural_deny'](pending.id,...(accept?[true]:[]));
        if(!reply || reply.status!=='ok') throw new Error(reply?.data || 'İzin yanıtı alınamadı');
        resolved=true;panel.remove();
        await refreshDesktopTaskState();
        await pollNaturalTask();
      } catch(error) {
        status.textContent='İzin işlemi doğrulanamadı: '+String(error.message||error)+'. Güncel görev durumu yeniden okunmalı.';
      } finally {
        if(!resolved){approve.disabled=false;deny.disabled=false;}
      }
    };
    approve.onclick=()=>decide(true);deny.onclick=()=>decide(false);
    panel.append(title,reason,summary,details,approve,deny,status);chatEl.append(panel);scrollToBottom(true);
  }
  async function pollCoordination() {
    await refreshDesktopTaskState();
    const response=await window.pywebview.api.coordination_status();
    if(response.status!=='ok')return;
    if(response.data.job){
      const job=response.data.job;
      const state=document.querySelector(`[data-coordination-status="${job.id}"]`);
      if(state)state.textContent=({running:'Çalışıyor; ajan mesajları aşağıda.',starting:'Başlatılıyor.',completed:'Çalışma sona erdi; hedefin sonucunu ajan kanıtlarından kontrol edin.',failed:'Başarısız; ayrıntılar ajan mesajlarında.',cancelled:'Durduruldu.',expired:'Onaylanan süre doldu; kontrol bırakıldı.'})[job.status]||job.status;
      const stop=document.querySelector(`[data-coordination-stop="${job.id}"]`);if(stop)stop.disabled=!response.data.active;
    }
    const messages=await window.pywebview.api.chat_status();
    if(messages.status==='ok'&&messages.data.active_conversation?.id===currentConvId)
      syncConversationMessages(messages.data.active_conversation.messages,false);
    if(response.data.active)coordinationTimer=setTimeout(pollCoordination,1500);
    else if(coordinationTimer){clearTimeout(coordinationTimer);coordinationTimer=null;}
  }

  // ── Self-Diagnostics (REA-Supported Compact Chat Card) ──
  function renderRepairPlan(plan) {
    if (!plan) { appendMsg('bot', 'QUARTZ', 'Referans seçimi iptal edildi; dosya değiştirilmedi.'); return; }
    const card = document.createElement('div');
    card.className = 'coordination-card diagnostics-card';
    const title = document.createElement('strong'); title.textContent = 'Quartz kaynak onarımı';
    const description = document.createElement('p'); description.textContent = plan.message;
    const files = document.createElement('pre'); files.textContent = (plan.files || []).join('\n') || 'Onarılacak kaynak farkı yok.';
    card.append(title, description, files);
    if (plan.requires_confirmation) {
      const confirm = document.createElement('button'); confirm.type = 'button';
      confirm.textContent = 'Bu referansa güveniyorum — yedekle ve onar';
      const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.textContent = 'Vazgeç';
      dismiss.addEventListener('click', async () => {
        confirm.disabled = true; dismiss.disabled = true;
        description.textContent = 'Onarım uygulanmadı; dosyalar değişmedi.';
        await window.pywebview.api.diagnostics_discard_repair();
      });
      confirm.addEventListener('click', async () => {
        confirm.disabled = true; dismiss.disabled = true;
        description.textContent = 'Kaynaklar yedekleniyor ve doğrulanıyor…';
        try {
          const result = await window.pywebview.api.diagnostics_apply_repair(plan.id);
          description.textContent = result.status === 'ok' ? result.data.message : result.data;
          card.dataset.repairState = result.status === 'ok' ? result.data.state : 'failed';
        } catch (_) { description.textContent = 'Onarım yanıtı alınamadı; tekrar uygulamadan önce teşhis çalıştırın.'; }
      });
      card.append(confirm, dismiss);
    }
    chatEl.append(card);
  }
  const DIAG_PHASE_LABELS = {
    queued: 'Sıraya alındı',
    scope: 'Kapsam ve kimlik doğrulaması',
    resources: 'Gerekli kaynak bileşenleri kontrolü',
    manifest: 'Paket manifesti ve SHA-256 doğrulaması',
    rea: 'REA statik ikili / arşiv incelemesi',
    report: 'Teşhis kanıtları kaydediliyor',
    done: 'Ölçüm tamamlandı',
  };
  const DIAG_CHECK_TITLES = {
    scope: 'İncelenen uygulama kapsamı',
    artifact: 'Seçilen uygulama dosyası',
    pe: 'Windows PE mimarisi ve başlığı',
    resources: 'Gerekli paket bileşenleri',
    manifest: 'Paket manifesti ve bütünlük',
    rea: 'REA statik paket incelemesi',
    inspection: 'Teşhis yürütme durumu',
  };
  const DIAG_STATUS_BADGES = {
    PASS: 'PASS · GEÇTİ',
    FAIL: 'FAIL · BAŞARISIZ',
    UNKNOWN: 'UNKNOWN · BELİRSİZ',
    NOT_TESTED: 'NOT TESTED · TEST EDİLMEDİ',
  };
  const DIAG_STATUS_EXPLANATIONS = {
    PASS: 'Bu kontrol doğrulandı; beklenen yapı ve özet değerleriyle uyumlu.',
    FAIL: 'Bu kontrolde uyumsuzluk veya eksiklik saptandı; kanıt ayrıntılarını inceleyin.',
    UNKNOWN: 'Bu kontrolün sonucu mevcut çalışma koşulunda kesinleştirilemedi.',
    NOT_TESTED: 'Bu kontrol mevcut modda (ör. kaynak kodu modu veya REA seçilmemesi/bulunmaması) çalıştırılmadı.',
  };
  const DIAG_SCOPE_NOTICE = 'Not: Başarılı paket kontrolü; model erişimi, arayüz işlevleri, güvenlik veya tüm uygulamanın hatasız olduğu anlamına gelmez.';

  function normalizeDiagStatus(raw) {
    const val = String(raw || 'UNKNOWN').trim().toUpperCase().replace(/[\s-]+/g, '_');
    if (val === 'PASS') return 'PASS';
    if (val === 'FAIL') return 'FAIL';
    if (val === 'NOT_TESTED') return 'NOT_TESTED';
    return 'UNKNOWN';
  }

  function redactDiagText(text) {
    return String(text || '')
      .replace(/\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|nvapi-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9]{16,}|sk-(?:proj-)?[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,})\b/g, '[gizli]')
      .replace(/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, '[gizli-anahtar]');
  }

  function formatDiagEvidence(evidence) {
    if (!evidence || typeof evidence !== 'object') return '';
    const keys = Object.keys(evidence).filter(k => evidence[k] !== undefined && evidence[k] !== null && evidence[k] !== '');
    if (!keys.length) return '';
    const safeCopy = {};
    for (const key of keys) {
      if (/secret|token|password|api_key|report_path/i.test(key)) continue;
      safeCopy[key] = evidence[key];
    }
    if (!Object.keys(safeCopy).length) return '';
    return redactDiagText(JSON.stringify(safeCopy, null, 2));
  }

  function buildSelfDiagnosticsView(job) {
    if (!job || typeof job !== 'object') {
      return {
        id: 'invalid',
        state: 'failed',
        phase: 'done',
        phaseLabel: 'Geçersiz teşhis verisi',
        progress: 0,
        progressText: 'Başarısız (%0)',
        message: 'Teşhis durumu okunamadı.',
        verdictCode: 'UNKNOWN',
        badgeCode: 'UNKNOWN',
        badgeText: 'UNKNOWN · BELİRSİZ',
        fillCode: 'FAIL',
        isSuccessReady: false,
        canCancel: false,
        reaUsed: false,
        reaTagText: 'REA: Belirsiz',
        counts: { PASS: 0, FAIL: 0, UNKNOWN: 0, NOT_TESTED: 0 },
        checks: [],
        limitations: [],
        scopeNotice: DIAG_SCOPE_NOTICE,
        technicalSummaryText: '',
      };
    }
    const state = ['idle', 'running', 'completed', 'cancelled', 'failed'].includes(job.state) ? job.state : 'unknown';
    const phase = String(job.phase || 'queued');
    const phaseLabel = DIAG_PHASE_LABELS[phase] || phase;
    const rawProgress = Number(job.progress);
    const progress = Number.isFinite(rawProgress) ? Math.max(0, Math.min(100, Math.round(rawProgress))) : 0;
    const rawChecks = Array.isArray(job.checks) ? job.checks : [];
    const counts = { PASS: 0, FAIL: 0, UNKNOWN: 0, NOT_TESTED: 0 };
    const checks = rawChecks.map((item, idx) => {
      const c = item && typeof item === 'object' ? item : {};
      const checkId = String(c.id || `check-${idx + 1}`);
      const status = normalizeDiagStatus(c.status);
      counts[status] = (counts[status] || 0) + 1;
      const title = String(c.title || DIAG_CHECK_TITLES[checkId] || checkId);
      const rawMsg = redactDiagText(c.message || '');
      const explanation = rawMsg || DIAG_STATUS_EXPLANATIONS[status];
      return {
        id: checkId,
        status,
        statusBadge: DIAG_STATUS_BADGES[status],
        title,
        explanation,
        statusHint: DIAG_STATUS_EXPLANATIONS[status],
        evidenceText: formatDiagEvidence(c.evidence),
      };
    });

    const rawVerdict = String(job.verdict || 'UNKNOWN').trim().toUpperCase().replace(/[\s-]+/g, '_');
    const isRunning = state === 'running' || (state === 'idle' && Boolean(job.id));
    const isSuccessReady = (
      state === 'completed' &&
      rawVerdict === 'PASS' &&
      job.finished_at != null &&
      checks.length > 0 &&
      counts.FAIL === 0 &&
      counts.UNKNOWN === 0 &&
      counts.NOT_TESTED === 0
    );

    let verdictCode = 'UNKNOWN';
    let badgeCode = 'UNKNOWN';
    let badgeText = 'UNKNOWN · BELİRSİZ';
    let fillCode = 'UNKNOWN';

    if (isRunning) {
      verdictCode = 'UNKNOWN';
      badgeCode = 'RUNNING';
      badgeText = phase === 'queued' ? 'SIRADA' : 'ÇALIŞIYOR';
      fillCode = 'RUNNING';
    } else if (state === 'cancelled') {
      verdictCode = 'UNKNOWN';
      badgeCode = 'CANCELLED';
      badgeText = 'İPTAL EDİLDİ (UNKNOWN)';
      fillCode = 'CANCELLED';
    } else if (state === 'failed') {
      verdictCode = rawVerdict === 'FAIL' ? 'FAIL' : 'UNKNOWN';
      badgeCode = verdictCode;
      badgeText = verdictCode === 'FAIL' ? 'FAIL · BAŞARISIZ' : 'TAMAMLANAMADI (UNKNOWN)';
      fillCode = 'FAIL';
    } else if (state === 'completed') {
      if (rawVerdict === 'FAIL' || counts.FAIL > 0) {
        verdictCode = 'FAIL';
        badgeCode = 'FAIL';
        badgeText = 'FAIL · SORUN SAPTANDI';
        fillCode = 'FAIL';
      } else if (isSuccessReady) {
        verdictCode = 'PASS';
        badgeCode = 'PASS';
        badgeText = 'PASS · DOĞRULANDI';
        fillCode = 'PASS';
      } else if (rawVerdict === 'PARTIAL' || (rawVerdict === 'PASS' && !isSuccessReady)) {
        verdictCode = 'PARTIAL';
        badgeCode = 'PARTIAL';
        badgeText = 'PARTIAL · KISMİ KAPSAM';
        fillCode = 'PARTIAL';
      } else {
        verdictCode = 'UNKNOWN';
        badgeCode = 'UNKNOWN';
        badgeText = 'UNKNOWN · BELİRSİZ';
        fillCode = 'UNKNOWN';
      }
    }

    let progressText = `${phaseLabel} · %${progress}`;
    if (state === 'cancelled') {
      progressText = `İptal edildi (%${progress} aşamasında durduruldu; başarı sayılmadı)`;
    } else if (state === 'failed') {
      progressText = `Tamamlanamadı (%${progress} aşamasında kesildi)`;
    } else if (state === 'completed') {
      if (verdictCode === 'PASS') progressText = `Ölçüm tamamlandı (%${progress}) · Tüm kontroller geçti`;
      else if (verdictCode === 'PARTIAL') progressText = `Ölçüm tamamlandı (%${progress}) · Kısmi kapsam (test edilmeyen/belirsiz adım var)`;
      else if (verdictCode === 'FAIL') progressText = `Ölçüm tamamlandı (%${progress}) · Sorun bulgusu var`;
      else progressText = `Ölçüm tamamlandı (%${progress}) · Sonuç belirsiz`;
    }

    const reaCheck = checks.find(c => c.id === 'rea');
    const reaUsed = Boolean(job.rea_used);
    const reaTagText = reaUsed
      ? 'REA: Kullanıldı'
      : (reaCheck?.status === 'NOT_TESTED' ? 'REA: Test Edilmedi' : (isRunning ? 'REA: Hazırlanıyor' : 'REA: Devre Dışı'));

    const limitations = Array.isArray(job.limitations)
      ? job.limitations.map(item => redactDiagText(item)).filter(Boolean)
      : [];

    const knowledgeSaved = Boolean(job.knowledge_saved);
    const summaryMeta = {
      schema_version: job.schema_version ?? 1,
      job_id: job.id || null,
      state,
      phase,
      verdict: verdictCode,
      progress,
      rea_used: reaUsed,
      knowledge_saved: knowledgeSaved,
      counts,
      report_saved: Boolean(job.report_path),
    };

    return {
      id: String(job.id || 'latest'),
      state,
      phase,
      phaseLabel,
      progress,
      progressText,
      message: redactDiagText(job.message || ''),
      verdictCode,
      badgeCode,
      badgeText,
      fillCode,
      isSuccessReady,
      canCancel: state === 'running',
      reaUsed,
      reaTagText,
      knowledgeSaved,
      counts,
      checks,
      limitations,
      scopeNotice: DIAG_SCOPE_NOTICE,
      technicalSummaryText: JSON.stringify(summaryMeta, null, 2),
    };
  }

  let activeDiagJobId = null;
  let diagPollTimer = null;
  let diagPollBusy = false;
  const diagPollFailures = new Map();

  function hasActiveDiagnosticsJob() {
    return Boolean(activeDiagJobId && (diagPollFailures.get(activeDiagJobId) || 0) <= 3);
  }

  function renderLearnedApplicationsCard(items, targetContainer = null) {
    const container = targetContainer || (typeof chatEl !== 'undefined' ? chatEl : null);
    if (!container) return null;
    const card = document.createElement('section');
    card.className = 'coordination-card diagnostics-card';
    card.setAttribute('aria-label', 'Quartz Öğrenilen Uygulama Hafızası');
    const head = document.createElement('div');
    head.className = 'diag-head';
    const titleWrap = document.createElement('div');
    titleWrap.className = 'diag-title-wrap';
    const titleEl = document.createElement('strong');
    titleEl.className = 'diag-title';
    titleEl.textContent = 'QUARTZ UYGULAMA HAFIZASI (REA + DENEYİM)';
    const countTag = document.createElement('span');
    countTag.className = 'diag-rea-tag';
    countTag.textContent = `${Array.isArray(items) ? items.length : 0} Kayıtlı Profil`;
    titleWrap.append(titleEl, countTag);
    head.append(titleWrap);
    card.append(head);

    const checksBox = document.createElement('div');
    checksBox.className = 'diag-checks';
    if (!Array.isArray(items) || !items.length) {
      const empty = document.createElement('div');
      empty.className = 'diag-empty';
      empty.textContent = 'Henüz öğrenilmiş bir uygulama kaydı bulunmuyor. "Başka bir uygulamayı incele" komutuyla veya onaylı görevlerle uygulama profilleri öğrenilir.';
      checksBox.append(empty);
    } else {
      items.forEach((rec, idx) => {
        const row = document.createElement('div');
        row.className = 'diag-check-item';
        const status = normalizeDiagStatus(rec.verdict === 'PARTIAL' ? 'PASS' : rec.verdict);
        row.dataset.checkStatus = status;
        const top = document.createElement('div');
        top.className = 'diag-check-top';
        const cTitle = document.createElement('span');
        cTitle.className = 'diag-check-title';
        const shortHash = String(rec.sha256 || '').slice(0, 12);
        cTitle.textContent = `Uygulama #${idx + 1} · SHA-256: ${shortHash}…`;
        const cStatus = document.createElement('span');
        cStatus.className = 'diag-status-pill';
        cStatus.dataset.status = status;
        cStatus.textContent = String(rec.verdict || 'UNKNOWN');
        top.append(cTitle, cStatus);

        const facts = Array.isArray(rec.facts) ? rec.facts : [];
        const peFact = facts.find(f => f.source === 'pe')?.values || {};
        const reaFact = facts.find(f => f.source === 'rea')?.values || {};
        const opFact = facts.find(f => f.source === 'operational')?.values || {};
        const parts = [];
        if (peFact.architecture) parts.push(`Mimari: ${peFact.architecture}${peFact.pe_format ? ` (${peFact.pe_format})` : ''}`);
        if (peFact.subsystem) parts.push(`Alt sistem: ${peFact.subsystem}`);
        if (reaFact.format) parts.push(`REA biçimi: ${reaFact.format} (düğüm: ${reaFact.nodes ?? 0})`);
        if (opFact.verified_runs !== undefined) {
          parts.push(`Doğrulanmış görev: ${opFact.verified_runs}, Doğrulanmış eylem: ${opFact.verified_actions ?? 0}`);
        }
        if (opFact.requires_elevation) parts.push('UAC yükseltme gerekiyor');
        const cMsg = document.createElement('div');
        cMsg.className = 'diag-check-msg';
        cMsg.textContent = parts.length ? parts.join(' · ') : 'Statik dosya kimliği ve SHA-256 doğrulandı.';
        row.append(top, cMsg);

        const evDetails = document.createElement('details');
        evDetails.className = 'technical-details diag-evidence';
        const evSummary = document.createElement('summary');
        evSummary.textContent = 'Öğrenilen yapısal ve operasyonel kanıtlar';
        const evPre = document.createElement('pre');
        evPre.className = 'diag-evidence-pre';
        evPre.textContent = formatDiagEvidence(rec);
        evDetails.append(evSummary, evPre);
        row.append(evDetails);
        checksBox.append(row);
      });
    }
    card.append(checksBox);
    container.appendChild(card);
    if (typeof scrollToBottom === 'function' && typeof userPinnedToBottom !== 'undefined' && userPinnedToBottom) {
      scrollToBottom(true);
    }
    return card;
  }

  function renderSelfDiagnosticsCard(job, targetContainer = null) {
    const container = targetContainer || (typeof chatEl !== 'undefined' ? chatEl : null);
    if (!container) return null;
    const view = buildSelfDiagnosticsView(job);
    const selector = `[data-diagnostics-job="${view.id.replace(/["\\]/g, '')}"]`;
    let card = container.querySelector ? container.querySelector(selector) : null;
    const openDetailsKeys = new Set();
    if (card && card.querySelectorAll) {
      card.querySelectorAll('details[data-detail-key]').forEach(d => {
        if (d.open) openDetailsKeys.add(d.dataset.detailKey);
      });
    } else {
      card = document.createElement('section');
      card.className = 'coordination-card diagnostics-card';
      card.dataset.diagnosticsJob = view.id;
      card.setAttribute('aria-label', 'Quartz Öz Teşhis Kartı');
      container.appendChild(card);
    }

    card.dataset.state = view.state;
    card.dataset.verdict = view.verdictCode;
    card.classList.toggle('diag-complete-pass', view.isSuccessReady);
    card.replaceChildren();

    // 1. Header: Title + REA tag + Verdict Badge + Cancel Button
    const head = document.createElement('div');
    head.className = 'diag-head';
    const titleWrap = document.createElement('div');
    titleWrap.className = 'diag-title-wrap';
    const titleEl = document.createElement('strong');
    titleEl.className = 'diag-title';
    titleEl.textContent = job.scope === 'artifact' ? 'SEÇİLEN UYGULAMA İNCELEMESİ' : 'QUARTZ ÖZ TEŞHİS';
    const reaTag = document.createElement('span');
    reaTag.className = 'diag-rea-tag';
    reaTag.textContent = view.reaTagText;
    titleWrap.append(titleEl, reaTag);
    if (view.knowledgeSaved) {
      const learnTag = document.createElement('span');
      learnTag.className = 'diag-rea-tag';
      learnTag.textContent = 'ÖĞRENME: Hafızaya Kaydedildi';
      titleWrap.append(learnTag);
    }

    const actions = document.createElement('div');
    actions.className = 'diag-actions';
    const badge = document.createElement('span');
    badge.className = 'diag-badge';
    badge.dataset.badge = view.badgeCode;
    badge.textContent = view.badgeText;
    actions.append(badge);

    if (view.canCancel) {
      const cancelBtnEl = document.createElement('button');
      cancelBtnEl.type = 'button';
      cancelBtnEl.className = 'control-btn';
      cancelBtnEl.dataset.diagnosticsCancel = view.id;
      cancelBtnEl.textContent = 'İptal Et';
      cancelBtnEl.onclick = async () => {
        cancelBtnEl.disabled = true;
        cancelBtnEl.textContent = 'İptal ediliyor…';
        await cancelSelfDiagnostics(view.id);
      };
      actions.append(cancelBtnEl);
    }
    head.append(titleWrap, actions);
    card.append(head);

    // 2. Progress & Current Message
    const progRow = document.createElement('div');
    progRow.className = 'diag-progress-row';
    const phaseLine = document.createElement('div');
    phaseLine.className = 'diag-phase-line';
    const phaseText = document.createElement('span');
    phaseText.className = 'diag-phase-text';
    phaseText.textContent = view.message || view.progressText;
    const phasePct = document.createElement('span');
    phasePct.className = 'diag-phase-pct';
    phasePct.textContent = view.progressText;
    phaseLine.append(phaseText, phasePct);

    const bar = document.createElement('div');
    bar.className = 'diag-progress-bar';
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', '100');
    bar.setAttribute('aria-valuenow', String(view.progress));
    const fill = document.createElement('div');
    fill.className = 'diag-progress-fill';
    fill.dataset.fill = view.fillCode;
    fill.style.width = `${view.progress}%`;
    bar.append(fill);
    progRow.append(phaseLine, bar);
    card.append(progRow);

    // 3. Status Counts (PASS / FAIL / UNKNOWN / NOT TESTED)
    const countsRow = document.createElement('div');
    countsRow.className = 'diag-counts';
    for (const [code, label] of [
      ['PASS', `PASS (Geçti): ${view.counts.PASS}`],
      ['FAIL', `FAIL (Başarısız): ${view.counts.FAIL}`],
      ['UNKNOWN', `UNKNOWN (Belirsiz): ${view.counts.UNKNOWN}`],
      ['NOT_TESTED', `NOT TESTED (Test Edilmedi): ${view.counts.NOT_TESTED}`],
    ]) {
      const pill = document.createElement('span');
      pill.className = 'diag-count-pill';
      pill.dataset.countStatus = code;
      pill.textContent = label;
      countsRow.append(pill);
    }
    card.append(countsRow);

    // 4. Checks List
    const checksBox = document.createElement('div');
    checksBox.className = 'diag-checks';
    if (!view.checks.length) {
      const empty = document.createElement('div');
      empty.className = 'diag-check-msg';
      empty.textContent = view.canCancel ? 'Kontrol adımları yürütülüyor…' : 'Bu koşuda kontrol adımı kaydı oluşmadı.';
      checksBox.append(empty);
    } else {
      for (const chk of view.checks) {
        const row = document.createElement('div');
        row.className = 'diag-check-row';
        row.dataset.checkId = chk.id;
        row.dataset.checkStatus = chk.status;

        const top = document.createElement('div');
        top.className = 'diag-check-top';
        const cTitle = document.createElement('span');
        cTitle.className = 'diag-check-title';
        cTitle.textContent = chk.title;
        const cStatus = document.createElement('span');
        cStatus.className = 'diag-status-pill';
        cStatus.dataset.status = chk.status;
        cStatus.textContent = chk.statusBadge;
        top.append(cTitle, cStatus);

        const cMsg = document.createElement('div');
        cMsg.className = 'diag-check-msg';
        cMsg.textContent = chk.explanation;
        row.append(top, cMsg);

        if (chk.evidenceText) {
          const evDetails = document.createElement('details');
          evDetails.className = 'technical-details diag-evidence';
          const detailKey = `ev:${chk.id}`;
          evDetails.dataset.detailKey = detailKey;
          evDetails.open = openDetailsKeys.has(detailKey);
          const evSummary = document.createElement('summary');
          evSummary.textContent = 'Kanıt ve teknik ayrıntılar';
          const evPre = document.createElement('pre');
          evPre.className = 'diag-evidence-pre';
          evPre.textContent = chk.evidenceText;
          evDetails.append(evSummary, evPre);
          row.append(evDetails);
        }
        checksBox.append(row);
      }
    }
    card.append(checksBox);

    // 5. Limitations & Scope Notice
    const limBox = document.createElement('div');
    limBox.className = 'diag-limitations';
    const noticeP = document.createElement('p');
    noticeP.textContent = view.scopeNotice;
    limBox.append(noticeP);
    if (view.limitations.length) {
      const ul = document.createElement('ul');
      for (const item of view.limitations) {
        const li = document.createElement('li');
        li.textContent = item;
        ul.append(li);
      }
      limBox.append(ul);
    }
    card.append(limBox);

    // 6. Card-level Technical Summary
    const metaDetails = document.createElement('details');
    metaDetails.className = 'technical-details diag-meta-details';
    metaDetails.dataset.detailKey = 'meta:summary';
    metaDetails.open = openDetailsKeys.has('meta:summary');
    const metaSummary = document.createElement('summary');
    metaSummary.textContent = 'Teşhis özeti ve teknik kayıt';
    const metaPre = document.createElement('pre');
    metaPre.textContent = view.technicalSummaryText;
    metaDetails.append(metaSummary, metaPre);
    card.append(metaDetails);

    if (typeof scrollToBottom === 'function' && typeof userPinnedToBottom !== 'undefined' && userPinnedToBottom) {
      scrollToBottom(true);
    }
    return card;
  }

  async function pollSelfDiagnostics(jobId = activeDiagJobId) {
    if (diagPollBusy || !jobId) return;
    diagPollBusy = true;
    let keepPolling = false;
    let terminal = false;
    try {
      const resp = await window.pywebview.api.diagnostics_status(jobId);
      if (!resp || resp.status !== 'ok' || !resp.data || resp.data.id !== jobId) throw new Error('diagnostics-status-unavailable');
      renderSelfDiagnosticsCard(resp.data);
      diagPollFailures.delete(jobId);
      keepPolling = resp.data.state === 'running';
      terminal = !keepPolling;
    } catch (_) {
      const failures = (diagPollFailures.get(jobId) || 0) + 1;
      diagPollFailures.set(jobId, failures);
      keepPolling = failures <= 3;
      showDiagnosticsPollError(jobId, keepPolling);
    } finally {
      diagPollBusy = false;
    }
    if (keepPolling) {
      scheduleSelfDiagnosticsPoll(jobId);
    } else if (terminal && activeDiagJobId === jobId) {
      activeDiagJobId = null;
      if (diagPollTimer) {
        clearTimeout(diagPollTimer);
        diagPollTimer = null;
      }
    }
  }

  function showDiagnosticsPollError(jobId, retrying) {
    const card = chatEl.querySelector(`[data-diagnostics-job="${String(jobId).replace(/["\\]/g, '')}"]`);
    if (!card) return;
    let warning = card.querySelector('.diag-connection-warning');
    if (!warning) {
      warning = document.createElement('div'); warning.className = 'diag-connection-warning';
      warning.setAttribute('role', 'alert'); card.append(warning);
    }
    warning.replaceChildren();
    const text = document.createElement('p');
    text.textContent = retrying ? 'Güncel teşhis durumu alınamadı; yeniden deneniyor…' :
      'Güncel sonuç doğrulanamadı. Yukarıdaki ilerleme son alınan bilgidir.';
    warning.append(text);
    if (!retrying) {
      const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'control-btn';
      retry.textContent = 'Durumu yeniden oku';
      retry.onclick = () => { diagPollFailures.delete(jobId); pollSelfDiagnostics(jobId); };
      warning.append(retry);
    }
  }

  function scheduleSelfDiagnosticsPoll(jobId) {
    if (!jobId) return;
    activeDiagJobId = jobId;
    if (diagPollTimer) {
      clearTimeout(diagPollTimer);
      diagPollTimer = null;
    }
    const hidden = typeof isUiHidden === 'function' && isUiHidden();
    const lowSpec = typeof lowSpecHardware !== 'undefined' && Boolean(lowSpecHardware);
    const delay = Math.max(hidden ? 4000 : (lowSpec ? 1800 : 900),
      diagPollFailures.has(jobId) ? Math.min(8000, 1000 * 2 ** diagPollFailures.get(jobId)) : 0);
    diagPollTimer = setTimeout(() => pollSelfDiagnostics(jobId), delay);
  }

  async function startSelfDiagnostics(includeRea = true) {
    try {
      const resp = await window.pywebview.api.diagnostics_start(Boolean(includeRea));
      if (!resp || resp.status !== 'ok' || !resp.data) {
        if (typeof appendMsg === 'function') appendMsg('err', 'QUARTZ', (resp && resp.data) || 'Öz teşhis başlatılamadı');
        return null;
      }
      if (typeof chatEl !== 'undefined' && chatEl?.querySelectorAll) {
        chatEl.querySelectorAll('[data-welcome="1"]').forEach(el => el.remove());
      }
      renderSelfDiagnosticsCard(resp.data);
      if (resp.data.state === 'running' && resp.data.id) {
        scheduleSelfDiagnosticsPoll(resp.data.id);
      }
      return resp.data;
    } catch (e) {
      if (typeof appendMsg === 'function') appendMsg('err', 'QUARTZ', String(e.message || e));
      return null;
    }
  }

  async function cancelSelfDiagnostics(jobId) {
    if (!jobId) return null;
    try {
      const resp = await window.pywebview.api.diagnostics_cancel(jobId);
      if (!resp || resp.status !== 'ok' || !resp.data) {
        if (typeof appendMsg === 'function') appendMsg('err', 'QUARTZ', (resp && resp.data) || 'Öz teşhis iptal edilemedi');
        return null;
      }
      renderSelfDiagnosticsCard(resp.data);
      if (resp.data.state !== 'running' && activeDiagJobId === jobId) {
        activeDiagJobId = null;
        if (diagPollTimer) {
          clearTimeout(diagPollTimer);
          diagPollTimer = null;
        }
      }
      return resp.data;
    } catch (e) {
      if (typeof appendMsg === 'function') appendMsg('err', 'QUARTZ', String(e.message || e));
      return null;
    }
  }

  document.getElementById('btnSelfDiagnostics')?.addEventListener('click', () => {
    startSelfDiagnostics(true);
  });
  document.addEventListener('visibilitychange', () => {
    if (typeof isUiHidden === 'function' && !isUiHidden() && activeDiagJobId && !diagPollBusy) {
      pollSelfDiagnostics(activeDiagJobId);
    }
  });

  safeBtn.addEventListener('click', async () => {
    const r = await window.pywebview.api.set_safe_mode(!safeMode);
    safeMode = !!(r.data && r.data.enabled);
    safeBtn.classList.toggle('active', safeMode);
    safeBtn.textContent = `Güvenli Mod: ${safeMode ? 'AÇIK' : 'KAPALI'}`;
  });

  providerProbeBtn.addEventListener('click', async () => {
    providerProbeBtn.disabled = true;
    providerStatus.textContent = 'Bağlantı test ediliyor...';
    try {
      const response = await window.pywebview.api.provider_probe();
      if (response.status !== 'ok') throw new Error(response.data || 'Test başarısız');
      renderProvider(response.data);
    } catch (error) {
      providerStatus.textContent = `Test başarısız: ${error.message || error}`;
    } finally { providerProbeBtn.disabled = false; }
  });

  function addAgentRow(container, title, details, status='') {
    const row = document.createElement('div'); row.className = 'agent-row';
    const head = document.createElement('strong'); head.textContent = title;
    if (status) head.className = status;
    const body = document.createElement('div'); body.textContent = details || '';
    row.append(head, body); container.appendChild(row);
    return row;
  }

  function renderAgentCenter(data) {
    if (!data) return;
    const squad = data.squad || {}, codex = data.codex || {}, antigravity = data.antigravity || {};
    updateAntigravitySafety(antigravity);
    document.getElementById('agentSquadStatus').textContent =
      `${squad.initialized ? 'HAZIR' : 'BAŞLATILMADI'} · ${squad.version || 'sürüm yok'}\n${squad.workspace || ''}`;
    document.getElementById('agentCodexStatus').textContent =
      `${codex.ready ? 'HAZIR' : (codex.authenticated ? 'YÜKLÜ' : 'GİRİŞ GEREKİYOR')} · ${codex.version || ''}\nOturum: ${codex.authentication || 'bilinmiyor'}`;
    document.getElementById('agentGeminiStatus').textContent =
      `${antigravity.ready ? 'HAZIR · ⚠ SINIRLI YALITIM' : (antigravity.installed ? 'GİRİŞ GEREKİYOR' : 'YÜKLÜ DEĞİL')} · ${antigravity.version || ''}\n${antigravity.bridge === 'squad-cli' ? 'Squad CLI köprüsü' : ''}${antigravity.safety_warning ? `\n${antigravity.safety_warning}` : ''}${antigravity.error ? `\n${antigravity.error}` : ''}`;
    const selected = agentProject.value;
    const writer = data.single_writer || {};
    agentProject.innerHTML = '';
    for (const project of (data.projects || [])) {
      const option = document.createElement('option'); option.value = project.id;
      option.textContent = `${project.name} · ${project.squad_initialized ? 'Squad hazır' : 'Squad yok'}`;
      option.selected = project.selected || project.id === selected;
      agentProject.appendChild(option);
    }

    const runs = document.getElementById('agentRuns'); runs.innerHTML = '';
    for (const run of (data.runs || [])) {
      const stateClass = run.status === 'completed' ? 'ok' : (['failed','cancelled'].includes(run.status) ? 'bad' : 'wait');
      const recentErrors = (run.errors || []).slice(-3).join('\n');
      const coordination = run.coordination_status && run.coordination_status !== 'not_linked'
        ? `\nSquad raporu: ${run.coordination_status}` : '';
      const coordinationError = run.coordination_error ? `\nSquad hatası: ${run.coordination_error}` : '';
      const commandEvidence = (run.commands || []).slice(-5).map(command =>
        `\nKomut: ${command.command || '—'} · çıkış: ${command.exit_code ?? 'bilinmiyor'}${command.output ? `\n${command.output.slice(0, 500)}` : ''}`).join('');
      const changedFiles = (run.files_changed || []).length
        ? `\nDeğişen dosyalar:\n${run.files_changed.join('\n')}` : '';
      const checkpoint = run.checkpoint?.ref ? `\nGit checkpoint: ${run.checkpoint.ref}`
        : (run.checkpoint?.warning ? `\nCheckpoint uyarısı: ${run.checkpoint.warning}` : '');
      const evidenceWarning = run.evidence_warning ? `\nDeğişiklik kaydı: ${run.evidence_warning}` : '';
      const row = addAgentRow(runs, `${(run.provider || 'codex').toUpperCase()} · ${run.status.toUpperCase()} · PID ${run.pid || '—'}`,
        `İstenen model: ${run.model || 'eski kayıt / belirtilmemiş'} · ${run.effort || 'belirtilmemiş'}\n${run.sandbox} · ${run.squad_task_id || 'Squad görevi yok'} · çıkış: ${run.exit_code ?? 'bekleniyor'}${coordination}${run.result ? `\n${run.result}` : ''}${commandEvidence}${changedFiles}${checkpoint}${evidenceWarning}${recentErrors ? `\nHata kaydı:\n${recentErrors}` : ''}${coordinationError}`, stateClass);
      if (!['completed','failed','cancelled'].includes(run.status)) {
        const stop = document.createElement('button'); stop.className = 'control-btn'; stop.textContent = 'Durdur';
        stop.onclick = async () => { await window.pywebview.api.agent_center_cancel(run.id); refreshAgentCenter(); };
        row.appendChild(stop);
      }
    }
    for (const collaboration of (data.collaborations || [])) {
      const stateClass = collaboration.status === 'completed' ? 'ok' : (collaboration.status === 'failed' ? 'bad' : 'wait');
      const selectedModels = Object.entries(collaboration.models || {}).map(([agent, cfg]) =>
        `${agent}: ${cfg.model} (${cfg.effort})`).join(' · ');
      addAgentRow(runs, `İŞ BİRLİĞİ · ${collaboration.status.toUpperCase()}`,
        `${selectedModels}\n${collaboration.run_ids.length} çalışma · ${collaboration.messages.length} Squad mesajı${collaboration.result ? `\n${collaboration.result}` : ''}${collaboration.error ? `\nHata: ${collaboration.error}` : ''}`, stateClass);
    }
    if (!runs.children.length) addAgentRow(runs, 'Çalışan ajan yok', 'Yeni görev verdiğinde gerçek PID burada görünür.');

    const tasks = document.getElementById('agentTasks'); tasks.innerHTML = '';
    for (const agent of (data.agents || [])) addAgentRow(tasks, `AJAN · ${agent.id}`, `${agent.role} · ${agent.effective_client_type} · ${agent.status}`);
    for (const task of (data.tasks || [])) {
      const taskResult = task.result ? `\nSonuç: ${String(task.result).slice(0, 600)}` : '';
      addAgentRow(tasks, `${task.status || 'task'} · ${task.title || task.id}`, `${task.assigned_to || 'atanmadı'} · ${task.id}${taskResult}`);
    }
    if (!tasks.children.length) addAgentRow(tasks, 'Kayıt yok', data.error || 'Squad verisi bulunamadı.');

    const history = document.getElementById('agentHistory'); history.innerHTML = '';
    for (const msg of [...(data.history || [])].reverse()) addAgentRow(history, `${msg.from} → ${msg.to}`, `${msg.timestamp}\n${msg.content}`);
    if (!history.children.length) addAgentRow(history, 'Mesaj yok', 'Squad geçmişi boş.');
    agentError.textContent = data.error || (writer.locked ? `Aktif yazıcı: ${writer.agent || writer.owner || 'ajan'}` : '');
  }

  async function refreshAgentCenter() {
    if (!agentOverlay.classList.contains('show')) return;
    try {
      const response = await window.pywebview.api.agent_center_status(agentProject.value || '');
      if (response.status !== 'ok') throw new Error(response.data || 'Ajan durumu alınamadı');
      renderAgentCenter(response.data);
    } catch (error) { agentError.textContent = String(error.message || error); }
  }

  async function pollAgentCenter(token) {
    if (token !== agentPollToken || !agentOverlay.classList.contains('show')) return;
    await refreshAgentCenter();
    setTimeout(() => pollAgentCenter(token), 2500);
  }

  document.getElementById('btnAgentCenter').addEventListener('click', () => {
    agentOverlay.classList.add('show');
    const token = ++agentPollToken;
    pollAgentCenter(token);
  });
  document.getElementById('btnAgentClose').addEventListener('click', () => {
    agentOverlay.classList.remove('show'); agentPollToken++;
  });
  document.getElementById('btnAgentRefresh').addEventListener('click', refreshAgentCenter);
  agentProject.addEventListener('change', refreshAgentCenter);
  agentProvider.addEventListener('change', () => {
    const collaborative = agentProvider.value === 'collaboration';
    agentWrite.disabled = collaborative;
    if (collaborative) agentWrite.value = 'read-only';
  });
  document.getElementById('btnAgentDispatch').addEventListener('click', async () => {
    const prompt = agentPrompt.value.trim();
    if (!prompt) { agentError.textContent = 'Görev açıklaması boş olamaz.'; return; }
    const models = {
      codex: {model: codexModelSelect.value, effort: codexEffortSelect.value},
      antigravity: {model: agyModelSelect.value, effort: agyEffortSelect.value},
    };
    document.getElementById('agentModelSelection').textContent = Object.entries(models)
      .map(([agent, cfg]) => `${agent}: ${cfg.model} (${cfg.effort})`).join(' · ');
    const write = agentWrite.value === 'project';
    const provider = agentProvider.value || 'codex';
    if (write && provider === 'antigravity') {
      agentError.textContent = 'Antigravity için Proje Yetkisiyle yazma Windows güvenlik sınırı doğrulanana kadar kapalı. Codex seç.';
      return;
    }
    if (provider === 'collaboration' && write) {
      agentError.textContent = 'İki ajanlı iş birliği bu sürümde salt-okunur çalışır.'; return;
    }
    if ((provider === 'antigravity' || provider === 'collaboration') && !confirmAntigravitySafety()) return;
    let confirmed = false;
    if (write) {
      confirmed = window.confirm(`Bu görev seçili proje dosyalarını değiştirebilir. Tek yazıcı kilidiyle ${provider} ajanına yazma yetkisi verilsin mi?`);
      if (!confirmed) return;
    }
    const button = document.getElementById('btnAgentDispatch');
    button.disabled = true; agentError.textContent = 'Görev Squad kuyruğuna ekleniyor...';
    try {
      const response = await window.pywebview.api.agent_center_dispatch(
        prompt, prompt.slice(0, 70), agentProject.value || '', write, confirmed, provider,
        models, currentConvId || '');
      if (response.status !== 'ok') throw new Error(response.data || 'Görev başlatılamadı');
      agentPrompt.value = ''; agentError.textContent = `${provider === 'collaboration' ? 'İki ajanlı iş birliği' : provider} başlatıldı.`;
      refreshAgentCenter();
    } catch (error) { agentError.textContent = String(error.message || error); }
    finally { button.disabled = false; }
  });

  let desktopPolling = false;
  const desktopStatus = document.getElementById('desktopOperatorStatus');
  document.getElementById('btnDesktopWindows').addEventListener('click', async () => {
    const response = await window.pywebview.api.desktop_operator_windows();
    if (response.status !== 'ok') { desktopStatus.textContent = response.data; return; }
    const select = document.getElementById('desktopWindow'); select.innerHTML = '';
    for (const target of response.data || []) {
      const option = document.createElement('option'); option.value = target.handle;
      option.textContent = `${target.title} · PID ${target.pid}`; select.appendChild(option);
    }
    desktopStatus.textContent = 'Pencereyi seçin; görev için ayrıca onay istenecek.';
  });
  async function pollDesktopOperator() {
    try {
      const response = await window.pywebview.api.desktop_operator_status();
      const data = response.data || {}; const run = data.run || {};
      desktopStatus.textContent = `${data.session?.active ? 'KONTROL AÇIK' : 'KONTROL KAPALI'} · ${run.status || 'bekliyor'}\n` +
        `${run.model || ''}\n${run.result || ''}\n${(run.errors || []).join('\n')}`;
      if (data.session?.active || ['running','starting','cancelling'].includes(run.status)) {
        setTimeout(pollDesktopOperator, 1000); return;
      }
    } catch (error) { desktopStatus.textContent = String(error); }
    desktopPolling = false;
  }
  document.getElementById('btnDesktopStart').addEventListener('click', async () => {
    const provider = agentProvider.value;
    if (!['codex','antigravity'].includes(provider)) { desktopStatus.textContent = 'Tek operatör seçin: Codex veya Antigravity.'; return; }
    const handle = document.getElementById('desktopWindow').value;
    const prompt = agentPrompt.value.trim();
    if (!handle || !prompt) { desktopStatus.textContent = 'Önce pencere seçin ve görev açıklaması yazın.'; return; }
    const cfg = provider === 'codex' ? {model:codexModelSelect.value,effort:codexEffortSelect.value} : {model:agyModelSelect.value,effort:agyEffortSelect.value};
    if (provider === 'antigravity' && !window.confirm('Antigravity Windows istemcisi katı dosya/terminal sandbox garantisi vermiyor. Bu köprü pencere girdisini sınırlar; genel CLI dosya erişimini işletim sistemi düzeyinde yalıtmaz. Bu sınırlamayla yalnız bu masaüstü görevi başlatılsın mı?')) return;
    if (!window.confirm('Bu görev için seçili pencereye ekran okuma ve sınırlı klavye/fare izni verilsin mi? Görüntüler seçili model sağlayıcısına gönderilir. Başka pencereye geçmek kontrolü durdurur. Dosya yazma yetkisi verilmez.')) return;
    const response = await window.pywebview.api.desktop_operator_start(provider, handle, prompt, cfg.model, cfg.effort, true);
    if (response.status !== 'ok') { desktopStatus.textContent = response.data; return; }
    if (!desktopPolling) { desktopPolling = true; pollDesktopOperator(); }
  });
  document.getElementById('btnDesktopStop').addEventListener('click', async () => {
    await window.pywebview.api.desktop_operator_stop();
    if (!desktopPolling) { desktopPolling = true; pollDesktopOperator(); }
  });

  function renderProvider(p) {
    if (!p) return;
    const labels = {ready:'HAZIR',checking:'KONTROL',unchecked:'BEKLİYOR',
      degraded:'YAVAŞ/SINIRLI',error:'HATA',missing_key:'ANAHTAR YOK'};
    const latency = p.latency_ms == null ? '—' : `${p.latency_ms} ms`;
    providerStatus.textContent = `${p.provider || '—'} · ${labels[p.status] || p.status}\n${p.model || '—'}\nGecikme: ${latency} · Hata: ${p.failures || 0}` +
      (p.last_error ? `\n${p.last_error}` : '');
  }
  advisorBtn.addEventListener('click', async () => {
    const r = await window.pywebview.api.set_screen_advisor(!advisorEnabled);
    advisorEnabled = !!(r.data && r.data.enabled);
    advisorBtn.classList.toggle('active', advisorEnabled);
    advisorBtn.innerHTML = `<span class="ic">${advisorEnabled ? '◉' : '◌'}</span> Ekran Rehberi: ${advisorEnabled ? 'AÇIK' : 'KAPALI'}`;
    logLine(`Ekran Rehberi ${advisorEnabled ? 'açıldı' : 'kapatıldı'}`);
  });
  learnOperationBtn.addEventListener('click', () => sendDirect('bu işi öğren'));
  finishOperationBtn.addEventListener('click', () => sendDirect('görevi bitir'));
  // Keyboard access remains available when pointer geometry cannot be captured.
  document.addEventListener('keydown', (e) => {
    if (!e.ctrlKey || e.altKey || e.shiftKey || e.metaKey || e.isComposing || String(e.key).toLowerCase() !== 'l') return;
    if (Array.from(document.querySelectorAll('[aria-modal="true"], dialog[open]')).some(el => el.getClientRects().length > 0)) return;
    if (inputEl.disabled || !inputEl.getClientRects().length) return;
    e.preventDefault();
    inputEl.focus();
  });
  inputEl.addEventListener('keydown', (e) => {
    if (e.isComposing || e.repeat) return;
    if (e.key === 'Enter') { e.preventDefault(); sendAgentMessage(); }
    else if (e.key === 'ArrowUp') {
      if (!inpHistory.length) return;
      histCursor = Math.min(histCursor + 1, inpHistory.length - 1);
      inputEl.value = inpHistory[inpHistory.length - 1 - histCursor];
    } else if (e.key === 'ArrowDown') {
      if (histCursor <= 0) { histCursor = -1; inputEl.value = ''; return; }
      histCursor--;
      inputEl.value = inpHistory[inpHistory.length - 1 - histCursor];
    }
  });

  document.querySelectorAll('.qa-btn[data-action]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const action = btn.dataset.action;
      appendMsg('sys', '', 'Çalıştırılıyor: ' + btn.textContent.trim());
      setThinking(true);
      const resp = await window.pywebview.api.quick_action(action);
      setThinking(false);
      renderResponse(resp);
    });
  });

  document.getElementById('btnClear').addEventListener('click', async () => {
    chatEl.innerHTML = '';
    msgCount = 0;
    document.getElementById('sessMsgs').textContent = 0;
    await window.pywebview.api.clear_history();
    logLine('Sohbet temizlendi');
  });

  document.getElementById('btnMobile').addEventListener('click', async () => {
    const response = await window.pywebview.api.mobile_access();
    if (response.status !== 'ok') { appendMsg('err', 'HATA', response.data); return; }
    const data = response.data;
    appendMsg('bot', 'MOBİL ERİŞİM', '');
    const bubble = chatEl.lastElementChild.querySelector('.bubble');
    bubble.classList.add('mobile-access-card');
    const addDetail = (label, value, token=false) => {
      const heading = document.createElement('div'); heading.className = 'mobile-label'; heading.textContent = label;
      const content = document.createElement('div'); content.className = `mobile-value${token ? ' mobile-token' : ''}`; content.textContent = value;
      bubble.append(heading, content);
    };
    addDetail('YEREL ADRES', data.local_url);
    addDetail('CİHAZ ANAHTARI', data.token, true);
    addDetail('TAILSCALE YAYINI', data.tailscale_command);
    const copyButton = document.createElement('button');
    copyButton.type = 'button'; copyButton.className = 'mobile-card-action';
    copyButton.textContent = '▣ ANAHTARI KOPYALA';
    copyButton.onclick = async () => {
      copyButton.disabled = true;
      const result = await window.pywebview.api.copy_mobile_token();
      copyButton.textContent = result.status === 'ok' ? '✓ KOPYALANDI' : '! KOPYALANAMADI';
      if (result.status !== 'ok') logLine(result.data);
      setTimeout(() => { copyButton.disabled = false; copyButton.textContent = '▣ ANAHTARI KOPYALA'; }, 1800);
    };
    bubble.appendChild(copyButton);
  });

  let compactMode = false;
  document.getElementById('btnMin').addEventListener('click', async () => {
    compactMode = !compactMode;
    const button = document.getElementById('btnMin');
    try {
      const result = await window.pywebview.api.set_compact(compactMode);
      compactMode = !!result.compact;
      document.body.classList.toggle('compact', compactMode);
      button.textContent = compactMode ? '□' : '─';
      button.title = compactMode ? 'Tam arayüze dön' : 'Kompakt sohbete geç';
      inputEl.focus();
    } catch (e) {
      compactMode = !compactMode;
      logLine('Kompakt mod açılamadı: ' + String(e));
    }
  });
  document.getElementById('btnClose').addEventListener('click', () => window.pywebview.api.close());

  // ── Voice: push-to-talk ─────────────────────────────────
  micBtn.addEventListener('click', async () => {
    if (thinking || micBtn.classList.contains('listening')) return;
    micBtn.classList.add('listening');
    setOrb('listening');
    logLine('Dinleniyor (push-to-talk)...');
    try {
      const resp = await window.pywebview.api.push_to_talk();
      micBtn.classList.remove('listening');
      if (resp.transcript) appendMsg('user', 'SEN (sesli)', resp.transcript);
      if (resp.status === 'ok') {
        renderResponse(resp);
        setOrb('idle');
      } else {
        appendMsg('err', 'HATA', resp.data || 'Bilinmeyen hata');
        setOrb('error');
        setTimeout(() => setOrb('idle'), 2000);
      }
    } catch (e) {
      micBtn.classList.remove('listening');
      setOrb('idle');
      appendMsg('err', 'HATA', String(e));
    }
  });

  // ── Voice: wake-word toggle ──────────────────────────────
  wakeBtn.addEventListener('click', async () => {
    const enabling = !wakeBtn.classList.contains('active');
    const r = await window.pywebview.api.toggle_wake_word(enabling);
    if (!r.available) {
      logLine('Mikrofon yok — wake-word açılamadı');
      return;
    }
    wakeBtn.classList.toggle('active', r.enabled);
    wakeBtn.textContent = r.enabled ? '◉ Wake ON' : '◎ Wake';
    logLine(r.enabled ? '"Hey Quartz" dinleniyor...' : 'Wake-word kapatıldı');
  });

  // ── Voice: TTS toggle ────────────────────────────────────
  ttsBtn.addEventListener('click', async () => {
    ttsEnabled = !ttsEnabled;
    await window.pywebview.api.set_tts_enabled(ttsEnabled);
    ttsBtn.classList.toggle('active', ttsEnabled);
    ttsBtn.textContent = ttsEnabled ? '🔊 TTS' : '🔇 TTS';
  });

  // ── Voice: callbacks pushed from the Python wake-word thread ──
  window.onWakeDetected = function() {
    setOrb('listening');
    logLine('"Quartz" duyuldu, dinleniyor...');
  };
  window.onWakeTimeout = function() {
    setOrb('idle');
    logLine('Komut algılanamadı.');
  };
  window.onVoiceResult = function(resp) {
    setOrb('idle');
    if (resp.transcript) appendMsg('user', 'SEN (sesli)', resp.transcript);
    renderResponse(resp);
  };

  let lastUserActivityAt = Date.now();
  let lowSpecHardware = false;
  let idleDesktopTick = 0;
  function markUserActivity() { lastUserActivityAt = Date.now(); }
  function isUiHidden() { return !!(document.hidden || document.visibilityState === 'hidden'); }
  function hasActiveDesktopTask() { return !!desktopView.stop_ref; }
  function isUiIdle() {
    return !thinking && !chatPollInterval && !hasActiveDesktopTask() && (typeof hasActiveDiagnosticsJob === 'function' ? !hasActiveDiagnosticsJob() : true) && (Date.now() - lastUserActivityAt > 20000);
  }
  ['mousedown', 'keydown', 'focus'].forEach(ev => window.addEventListener(ev, markUserActivity, { passive: true }));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      markUserActivity();
      pollUiEvents();
    }
  });

  async function pollPing() {
    let nextDelay = 600;
    try {
      nextDelay = isUiHidden() ? 10000 : (isUiIdle() || lowSpecHardware ? 7500 : 5000);
      const r = await window.pywebview.api.ping();
      statusPill.classList.toggle('online', r.online);
      statusPill.classList.toggle('offline', !r.online);
      statusText.textContent = r.online ? 'ÇEVRİMİÇİ' : 'ÇEVRİMDIŞI';
      document.getElementById('sessStatus').textContent = r.online ? 'ONLINE' : 'OFFLINE';
      if (!r.online) {
        nextDelay = 600;
      } else {
        if (!conversationLoaded) {
          await loadActiveConversation();
        }
        if (r.health && r.health.components) {
          const c = r.health.components;
          renderProvider(c.provider_manager);
          safeMode = !!c.safe_mode;
          safeBtn.classList.toggle('active', safeMode);
          safeBtn.textContent = `Güvenli Mod: ${safeMode ? 'AÇIK' : 'KAPALI'}`;
          advisorEnabled = !!(c.screen_advisor && c.screen_advisor.enabled);
          advisorBtn.classList.toggle('active', advisorEnabled);
          advisorBtn.innerHTML = `<span class="ic">${advisorEnabled ? '◉' : '◌'}</span> Ekran Rehberi: ${advisorEnabled ? 'AÇIK' : 'KAPALI'}`;
          const operation = c.operation && c.operation.active;
          if (operation) {
            const actionCount = (operation.actions || []).length;
            operationStatus.textContent = `${operation.root_goal}\n${actionCount} eylem · ${operation.app_context || 'uygulama belirsiz'}`;
            learnOperationBtn.style.display = 'inline-block';
            finishOperationBtn.style.display = 'inline-block';
          } else {
            operationStatus.textContent = 'Aktif görev yok';
            learnOperationBtn.style.display = 'none';
            finishOperationBtn.style.display = 'none';
          }
          statusPill.title = `LLM: ${c.llm.status} (${c.llm.provider}) | MCP: ${c.mcp.status} | Vision: ${c.vision.status}`;
        }
      }
    } catch (e) {
      nextDelay = 600;
      statusPill.classList.remove('online');
      statusPill.classList.add('offline');
      statusText.textContent = 'ÇEVRİMDIŞI';
    } finally {
      setTimeout(pollPing, nextDelay);
    }
  }

  function fillClass(pct) {
    if (pct > 80) return 'crit';
    if (pct > 60) return 'warn';
    return '';
  }
  let statsPollBusy = false;
  async function pollStats() {
    if (!statsPollBusy && !isUiHidden()) {
      statsPollBusy = true;
      try {
        const s = await window.pywebview.api.get_stats();
        if (typeof s.low_spec === 'boolean') {
          lowSpecHardware = s.low_spec;
          document.body.classList.toggle('low-spec', lowSpecHardware);
        }
        for (const [key, id] of [['cpu','cpu'], ['mem','mem'], ['disk','disk']]) {
          const val = s[key] || 0;
          document.getElementById(id + 'Val').textContent = val.toFixed(1) + '%';
          const fill = document.getElementById(id + 'Fill');
          fill.style.width = Math.min(100, val) + '%';
          fill.className = 'stat-fill ' + fillClass(val);
        }
      } catch (e) { /* ignore */ }
      finally { statsPollBusy = false; }
    }
    const statsDelay = isUiHidden() ? 10000 : (isUiIdle() || lowSpecHardware ? 6000 : 3000);
    setTimeout(pollStats, statsDelay);
  }

  let tasksPollBusy = false;
  async function pollTasks() {
    if (!tasksPollBusy && !isUiHidden()) {
      tasksPollBusy = true;
      try {
        const response = await window.pywebview.api.tasks();
        if (response.status === 'ok') renderTasks(response.data || []);
      } catch (e) { /* ignore */ }
      finally { tasksPollBusy = false; }
    }
    const tasksDelay = isUiHidden() ? 12000 : (isUiIdle() || lowSpecHardware ? 9000 : 6000);
    setTimeout(pollTasks, tasksDelay);
  }

  let uiEventsPollBusy = false;
  async function pollUiEvents() {
    document.body.classList.toggle('ui-idle', isUiIdle());
    if (!uiEventsPollBusy) {
      uiEventsPollBusy = true;
      try {
        idleDesktopTick = (idleDesktopTick + 1) % 2;
        if (hasActiveDesktopTask() || !isUiIdle() || idleDesktopTick === 0) {
          await refreshDesktopTaskState();
        }
        const response = await window.pywebview.api.ui_events();
        if (response.status === 'ok') renderUiEvents(response.data || []);
        if (!chatPollInterval && (!isUiIdle() || !conversationLoaded || idleDesktopTick === 0)) {
          const st = await window.pywebview.api.chat_status();
          if (st.status === 'ok' && st.data) {
            updateAntigravitySafety(st.data.agents?.antigravity);
            if (st.data.squad) updateSquadBadge(st.data.squad, st.data.active_conversation?.id);
            const conv = st.data.active_conversation;
            if (conv) {
              const switched = currentConvId !== conv.id;
              currentConvId = conv.id;
              renderConversationNavigation(st.data.conversations || []);
              chatConvTitle.textContent = conv.title || 'Yeni Sohbet';
              if (conv.agent) syncAgentUI(conv.agent);
              syncModelCatalogAndSelection(st.data.models, conv.models);
              if (switched) {
                const permSelect = document.getElementById('mainPermissionLevel');
                if (permSelect) {
                  permSelect.value = conv.permission_level || st.data.preferences?.permission_level || 'full';
                  updatePermissionSelectionHint();
                  window.__writeConfirmed = true;
                }
              }
              if (Array.isArray(conv.messages) && conv.messages.length > 0) {
                syncConversationMessages(conv.messages, switched);
              } else if (switched) {
                await loadActiveConversation();
              }
            }
            if (st.data.active_turn && st.data.active_turn.status === 'running') {
              setThinking(true);
              await pollAgentTurn();
            } else if (thinking) {
              setThinking(false);
            }
          }
        }
        if (hasActiveDesktopTask() || !isUiIdle() || idleDesktopTick === 0) {
          await pollNaturalTask();
        }
      } catch (_) { /* backend may still be starting */ }
      finally { uiEventsPollBusy = false; }
    }
    const uiDelay = (isUiHidden() && !thinking && !hasActiveDesktopTask())
      ? 4500
      : (isUiIdle() ? (lowSpecHardware ? 3200 : 2200) : (lowSpecHardware ? 1800 : 1200));
    setTimeout(pollUiEvents, uiDelay);
  }

  window.addEventListener('pywebviewready', async () => {
    const welcome = appendMsg('bot', 'QUARTZ', 'Merhaba! Ben Quartz. Doğrudan Antigravity ve Codex ajanlarıyla çalışıyorum.\nÜstteki seçiciden Antigravity, Codex veya Birlikte modunu seçip mesaj gönderebilirsin.', '', 'quartz');
    welcome.dataset.welcome = '1';
    logLine('Quartz UI başlatıldı');
    await loadActiveConversation();
    pollPing();
    pollStats();
    pollTasks();
    pollUiEvents();
    checkApiSetup();
    updatePermissionSelectionHint();
    window.__writeConfirmed = true;
    inputEl.focus();
    try {
      const perms = await window.pywebview.api.tool_permissions();
      const box = document.getElementById('pluginPermissions');
      box.innerHTML = '';
      for (const group of (perms.data || []).filter(x => x.source.startsWith('plugin:'))) {
        const btn = document.createElement('button'); btn.className = 'control-btn';
        btn.textContent = `${group.enabled ? '✓' : '○'} ${group.source.replace('plugin:','')}`;
        btn.onclick = async () => {
          await window.pywebview.api.set_tool_source(group.source, !group.enabled);
          group.enabled = !group.enabled;
          btn.textContent = `${group.enabled ? '✓' : '○'} ${group.source.replace('plugin:','')}`;
        };
        box.appendChild(btn);
      }
      // Voice is a legacy advanced feature: do not initialize microphone/TTS
      // merely by opening the development workspace.
      document.getElementById('btnPanels').addEventListener('click', async () => {
      if (window.__voiceChecked) return; window.__voiceChecked = true;
      const v = await window.pywebview.api.voice_status();
      if (!v.mic) {
        micBtn.classList.add('disabled');
        micBtn.title = 'Mikrofon bulunamadı';
        wakeBtn.classList.add('disabled');
        logLine('Mikrofon bulunamadı — sesli komut devre dışı');
      }
      if (!v.tts) {
        ttsEnabled = false;
        ttsBtn.classList.remove('active');
        ttsBtn.textContent = '🔇 TTS';
        logLine('TTS motoru bulunamadı');
      }
      });
    } catch (e) { /* ignore */ }
  });
</script>

</body>
</html>
"""


_ASSET_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
_HTML = _HTML.replace('</head>', '<style>' + (_ASSET_ROOT/'workspace.css').read_text(encoding='utf-8') + '</style></head>')
_BRAND_MARK = _ASSET_ROOT/'branding/quartz-q-48.png'
if _BRAND_MARK.is_file():
    import base64
    _HTML = _HTML.replace('<div class="brand">QUARTZ</div>',
        '<div class="brand"><img class="brand-icon" alt="Quartz Q" width="28" height="28" src="data:image/png;base64,' +
        base64.b64encode(_BRAND_MARK.read_bytes()).decode('ascii') + '">QUARTZ</div>')


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
