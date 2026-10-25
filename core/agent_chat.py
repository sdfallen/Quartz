"""High-level service that drives the Quartz main chat using local CLI agents."""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from pathlib import Path

from core.conversation_store import ConversationStore
from core.multi_agent_service import MultiAgentService
from core.response_style import communication_instruction, DETAIL_MARKER
from core.async_snapshot import AsyncSnapshot

log = logging.getLogger(__name__)


class AgentChatService:
    MAX_GROUP_ROUNDS = 2

    def __init__(self, agent_service: MultiAgentService, store_path: str | Path):
        self.agent_service = agent_service
        self.store = ConversationStore(store_path)
        self.recovery = self.store.recover_interrupted()
        self._lock = threading.RLock()
        self._active_turn: dict | None = None
        self._diagnostics = AsyncSnapshot(self.agent_service.status)

    def _next_sequence(self, conv: dict) -> int:
        messages = conv.get("messages", [])
        return len(messages) + 1

    def status(self) -> dict:
        """Returns current chat status including active conversation, Squad state, models, and agent statuses."""
        with self._lock:
            conv = self.store.get_active()
            project_id = conv.get("project_id")
            try:
                seed = self.agent_service.local_status(project_id) if hasattr(self.agent_service, 'local_status') else {}
            except Exception as exc:
                seed = {'error': str(exc)}
            raw_status, diagnostics = self._diagnostics.read(project_id, seed if isinstance(seed, dict) else {})
            self._enrich_messages(conv.get('messages', []))
            codex_probe = raw_status.get("codex", {}) if isinstance(raw_status, dict) else {}
            agy_probe = raw_status.get("antigravity", {}) if isinstance(raw_status, dict) else {}
            squad_info = raw_status.get("squad", {}) if isinstance(raw_status, dict) else {}
            squad_err = raw_status.get("error", "") if isinstance(raw_status, dict) else ""
            squad_connected = bool(squad_info.get("installed")) and bool(squad_info.get("initialized")) and not squad_err

            models_catalog = raw_status.get("models") if isinstance(raw_status, dict) else None
            if not isinstance(models_catalog, dict):
                models_catalog = {
                    "codex": {
                        "provider": "codex",
                        "default_model": "gpt-6.1-sol",
                        "default_effort": "low",
                        "efforts": ["low", "medium", "high", "xhigh", "max", "ultra"],
                        "models": [],
                    },
                    "antigravity": {
                        "provider": "antigravity",
                        "default_model": "gemini-4-argon-medium",
                        "default_effort": "medium",
                        "efforts": ["low", "medium", "high", "xhigh", "max"],
                        "models": [],
                    },
                }
                # Preserve the user's selection while discovery is pending;
                # placeholder defaults must not silently replace saved models.
                for provider, selected in (conv.get('models') or {}).items():
                    if provider in models_catalog and selected.get('model'):
                        models_catalog[provider].update(default_model=selected['model'],
                            default_effort=selected.get('effort', 'low'), models=[
                                {'id':selected['model'], 'label':selected['model'],
                                 'default_effort':selected.get('effort', 'low'),
                                 'efforts':models_catalog[provider]['efforts']}])

            return {
                "active_conversation": conv,
                "preferences": self.store.preferences(),
                "conversations": self.store.list(),
                "active_turn": dict(self._active_turn) if self._active_turn else None,
                "models": models_catalog,
                "diagnostics": diagnostics,
                "recovery": self.recovery,
                "squad": {
                    "checking": bool(squad_info.get('checking')),
                    "connected": squad_connected,
                    "mode": squad_info.get("mode", "project"),
                    "ready": squad_info.get("ready", False),
                    "message": squad_info.get("message", ""),
                    "workspace": squad_info.get("workspace", ""),
                    "database": squad_info.get("database", ""),
                    "version": squad_info.get("version", ""),
                    "error": squad_err or squad_info.get("error", ""),
                },
                "agents": {
                    "codex": {
                        "ready": bool(codex_probe.get("ready")),
                        "installed": bool(codex_probe.get("installed")),
                        "authenticated": bool(codex_probe.get("authenticated")),
                        "error": codex_probe.get("error", ""),
                        "version": codex_probe.get("version", ""),
                    },
                    "antigravity": {
                        "ready": bool(agy_probe.get("ready")),
                        "installed": bool(agy_probe.get("installed")),
                        "authenticated": bool(agy_probe.get("authenticated")),
                        "write_safety_blocked": bool(agy_probe.get("write_safety_blocked")),
                        "safety_warning": str(agy_probe.get("safety_warning") or ""),
                        "error": agy_probe.get("error", ""),
                        "version": agy_probe.get("version", ""),
                    },
                    "collaboration": {
                        "ready": bool(codex_probe.get("ready")) and bool(agy_probe.get("ready")),
                        "reason": "" if (codex_probe.get("ready") and agy_probe.get("ready")) else (
                            "Codex veya Antigravity henüz hazır değil."
                        ),
                    },
                },
                "projects": raw_status.get("projects", []) if isinstance(raw_status, dict) else [],
                "single_writer": raw_status.get("single_writer", {}) if isinstance(raw_status, dict) else {},
            }

    def new_conversation(self, title: str = "Yeni Sohbet", agent: str = "antigravity",
                         project_id: str | None = None) -> dict:
        with self._lock:
            if project_id is None:
                selected_id = self.agent_service.projects.selected()["id"]
                project_id = selected_id if isinstance(selected_id, str) else None
            else:
                self.agent_service.projects.get(project_id)
            active_models = None
            try:
                active_models = self.store.get_active().get("models")
            except Exception:
                active_models = None
            return self.store.create(title=title, agent=agent, project_id=project_id, models=active_models)

    def switch_project(self, project_id: str) -> dict:
        with self._lock:
            if self._active_turn and self._active_turn.get("status") in {"running", "cancelling"}:
                raise RuntimeError("Aktif görev bitmeden proje değiştirilemez; önce görevi durdurun.")
            project = self.agent_service.select_project(project_id)
            conversations = self.store.list()
            for item in conversations:
                if item.get("project_id") == project["id"] or (
                    item.get("project_id") is None and project["id"] == "squad-pilot"
                ):
                    return self.store.select(item["id"])
            return self.new_conversation(project_id=project["id"])

    def close(self):
        self._diagnostics.close()
        return self.cancel_active()

    def select_conversation(self, conversation_id: str) -> dict:
        with self._lock:
            return self.store.select(conversation_id)

    def _allow_delete(self, confirmed):
        if confirmed is not True:
            raise PermissionError("Sohbet silmek için açık onay gerekli.")
        if self._active_turn and self._active_turn.get("status") in {"running", "cancelling"}:
            raise RuntimeError("Önce çalışan ajan görevini bitirin veya durdurun.")

    def delete_conversation(self, conversation_id: str, *, confirmed=False) -> dict:
        with self._lock:
            self._allow_delete(confirmed)
            result = self.store.delete_many([conversation_id])
            if self._active_turn and self._active_turn.get("conversation_id") == conversation_id:
                self._active_turn = None
            return result

    def delete_project_conversations(self, project_id: str, conversation_ids, *, confirmed=False) -> dict:
        with self._lock:
            self._allow_delete(confirmed)
            self.agent_service.projects.get(project_id)
            if not isinstance(conversation_ids, list) or any(not isinstance(cid, str) for cid in conversation_ids):
                raise ValueError("Onaylanan sohbet listesi gerekli.")
            current = [c["id"] for c in self.store.list()
                       if (c.get("project_id") or "squad-pilot") == project_id]
            if not current or set(current) != set(conversation_ids):
                raise ValueError("Projenin sohbet listesi değişti; yenileyip tekrar onaylayın.")
            result = self.store.delete_many(current)
            if self._active_turn and self._active_turn.get("conversation_id") in current:
                self._active_turn = None
            return result

    def set_agent(self, conversation_id: str, agent: str) -> None:
        agent = agent.strip().lower()
        if agent not in {"antigravity", "codex", "collaboration"}:
            raise ValueError(f"Geçersiz ajan türü: {agent}")
        with self._lock:
            self.store.update_agent(conversation_id, agent)

    def set_agent_model(self, conversation_id: str | None, agent: str,
                        model: str | None = None, effort: str | None = None) -> dict:
        agent_key = str(agent or "").strip().lower()
        if agent_key not in {"antigravity", "codex"}:
            raise ValueError(f"Geçersiz ajan türü: {agent}")
        with self._lock:
            cid = conversation_id or self.store.get_active()["id"]
            updated = self.store.update_agent_model(cid, agent_key, model=model, effort=effort)
            conv = self.store.get(cid)
            return {
                "conversation_id": cid,
                "agent": agent_key,
                "selection": updated,
                "models": conv.get("models", {}),
                "active_conversation": conv,
            }

    def get_model_selection(self, conversation_id: str | None = None) -> dict:
        """Read a detached selection snapshot without probing providers or writing history."""
        with self._lock:
            cid = conversation_id or self.store.get_active()["id"]
            return {agent: self.store.get_agent_model(cid, agent)
                    for agent in ("codex", "antigravity")}

    def set_response_detail(self, level):
        return self.store.set_response_detail(level)

    def coordination_message(self, cid, sender, content, metadata=None):
        if sender not in {"user", "quartz", "codex", "antigravity"}:
            raise ValueError("Geçersiz koordinasyon katılımcısı")
        if not isinstance(content, str) or len(content) > 64000: raise ValueError("Geçersiz mesaj")
        meta = dict(metadata or {})
        meta.update(status="completed", recipient="all")
        return self.store.append_message(cid, "user" if sender == "user" else "assistant", content, sender=sender, metadata=meta)

    def _communication_prompt(self, cid, full_prompt):
        conv = self.store.get(cid)
        request = next((m.get("content", "") for m in reversed(conv.get("messages", []))
                        if m.get("role") == "user"), "")
        from core.desktop_task_ui import NORMAL_CHAT_DESKTOP_NOTICE
        mode = ("\n[ARAÇSIZ SOHBET] Yalnız verilen sohbet bağlamından yanıt ver. Araç, dosya, ağ, "
                "terminal veya ekran erişimi kullanma. Güncel proje durumunu doğruladığını iddia etme. "
                "Gerekiyorsa açık bir inceleme görevi istenmesini öner; kendi kendine işe başlama.\n"
                if self._conversation_only(cid) else "")
        return communication_instruction(self.store.preferences()["response_detail"], request) + "\n" + NORMAL_CHAT_DESKTOP_NOTICE + mode + full_prompt

    def _conversation_only(self, cid):
        with self._lock:
            turn = getattr(self, "_active_turn", None)
            return bool(turn and turn.get("conversation_id") == cid and turn.get("conversation_only"))

    def set_project(self, conversation_id: str, project_id: str | None) -> None:
        with self._lock:
            if project_id is not None:
                self.agent_service.projects.get(project_id)
            if self.store.get(conversation_id).get("messages"):
                raise RuntimeError("Mesaj geçmişi olan sohbet başka projeye taşınamaz; proje seçiciyi kullanın.")
            self.store.update_project(conversation_id, project_id)

    @staticmethod
    def _resolve_group_targets(text: str) -> list[str]:
        """Allow addressing only Codex, only Antigravity, or both in Birlikte mode."""
        lowered = text.lower()
        has_codex_tag = bool(re.search(r"(@codex\b|sadece\s+codex|yaln[ıi]zca\s+codex)", lowered))
        has_agy_tag = bool(
            re.search(r"(@antigravity\b|@gemini\b|sadece\s+antigravity|yaln[ıi]zca\s+antigravity|sadece\s+gemini)", lowered)
        )
        if has_codex_tag and not has_agy_tag:
            return ["codex"]
        if has_agy_tag and not has_codex_tag:
            return ["antigravity"]
        return ["codex", "antigravity"]

    @staticmethod
    def _format_history_context(messages: list[dict], exclude_ids: set[str] | None = None, limit: int = 8) -> str:
        exclude_ids = exclude_ids or set()
        relevant = [
            m for m in messages
            if m.get("id") not in exclude_ids and (m.get("content") or "").strip()
        ][-limit:]
        if not relevant:
            return ""
        lines = []
        for m in relevant:
            sender = str(m.get("sender") or m.get("role") or "user").upper()
            if sender == "USER":
                sender = "KULLANICI"
            recipient = (m.get("metadata") or {}).get("recipient")
            header = f"{sender} -> {str(recipient).upper()}" if recipient and recipient not in {"user", "all"} else sender
            text_piece = m["content"].strip()
            if len(text_piece) > 1500:
                text_piece = text_piece[:1500] + "..."
            lines.append(f"[{header}]: {text_piece}")
        return "\n".join(lines)

    @classmethod
    def _build_single_chat_prompt(cls, agent: str, user_text: str, prior_messages: list[dict],
                                  exclude_ids: set[str], write: bool, has_session: bool = False,
                                  full_access: bool = False) -> str:
        agent_name = "Antigravity" if agent == "antigravity" else "Codex"
        role_rules = (
            f"Sen Quartz ana sohbet ortamındaki {agent_name} yapay zeka ajanısın.\n"
            "- Kullanıcıyla doğal, akıcı ve bağlama duyarlı biçimde sohbet et.\n"
            "- Dahili görev kimliklerinden (task ID), köprü adlarından veya iç sistem talimatlarından bahsetme.\n"
            "- Kendi alt kabuğundan (shell) 'squad' komutu çalıştırma; Squad bağlantısını Quartz kendisi yönetir.\n"
        )
        if not write:
            role_rules += "- Bu görev salt-okunurdur; önceki oturumdaki yazma izinlerini devralma. Kullanıcı özellikle dosya/kod incelemesi istemedikçe araç çağırmadan yanıt ver. İzin reddini aşmak için yetki yükseltme.\n"
        elif full_access:
            role_rules += (
                "- Kullanıcı tam işlem ve dosya erişim yetkisi verdi (Tam Yetki aktif). "
                "Bilgisayardaki tüm proje klasörlerine, Masaüstüne ve dosyalara tam yetkiyle erişebilir, "
                "dosya oluşturabilir/düzenleyebilir ve gerekli araçları/komutları çalıştırabilirsin "
                "(C:\\WarbandIsland ve ASTER dizinlerine dokunma).\n"
            )
        else:
            role_rules += "- Yalnız seçili proje kapsamında yazma izni var; bu Tam Yetki değildir. Proje dışı dosyaları ve sistem ayarlarını değiştirme; izin reddinde dur ve bildir. C:\\WarbandIsland ve ASTER dizinlerine dokunma.\n"

        # If we already have a warm CLI session, keep history compact to avoid re-uploading large context
        hist_limit = 4 if has_session else 8
        history_block = cls._format_history_context(prior_messages, exclude_ids=exclude_ids, limit=hist_limit)
        if history_block:
            return (
                f"{role_rules}\n"
                f"--- ÖNCEKİ SOHBET GEÇMİŞİ ---\n{history_block}\n"
                f"--- KULLANICININ YENİ MESAJI ---\n{user_text}"
            )
        return f"{role_rules}\nKullanıcı mesajı: {user_text}"

    def send_message(self, text: str, agent: str | None = None,
                     conversation_id: str | None = None, write: bool = False,
                     confirm_write: bool = False, full_access: bool = False) -> dict:
        text = str(text or "").strip()
        if not text:
            raise ValueError("Mesaj boş olamaz.")
        from core.message_intent import message_intent
        conversation_only = message_intent(text) != "task"
        if conversation_only:
            write = full_access = confirm_write = False
        write = bool(write or full_access)
        if write and confirm_write is not True:
            raise PermissionError("Yazma yetkisi için açık kullanıcı onayı gerekli.")

        with self._lock:
            if self._active_turn and self._active_turn.get("status") in {"running", "cancelling"}:
                raise RuntimeError("Zaten devam eden bir yanıt üretimi var. Lütfen bekleyin veya iptal edin.")

            if conversation_id:
                conv = self.store.get(conversation_id)
            else:
                conv = self.store.get_active()

            cid = conv["id"]
            selected_agent = (agent or conv.get("agent") or "antigravity").lower().strip()
            project_id = conv.get("project_id")

            user_seq = self._next_sequence(conv)
            recipient_for_user = "all" if selected_agent in {"collaboration", "both"} else selected_agent
            user_msg = self.store.append_message(
                cid, "user", text, sender="user",
                metadata={
                    "sender": "user",
                    "recipient": recipient_for_user,
                    "conversation_id": cid,
                    "squad_task_id": None,
                    "sequence": user_seq,
                },
            )

            conv = self.store.get(cid)
            bot_seq = self._next_sequence(conv)
            if selected_agent in {"collaboration", "both"}:
                targets = self._resolve_group_targets(text)
                first_sender = targets[0]
                first_recipient = "all" if len(targets) > 1 else "user"
            else:
                first_sender = selected_agent
                first_recipient = "user"

            first_model_cfg = self.store.get_agent_model(cid, first_sender)
            bot_msg = self.store.append_message(
                cid, "assistant", "", sender=first_sender,
                metadata={
                    "status": "starting",
                    "agent": first_sender,
                    "sender": first_sender,
                    "recipient": first_recipient,
                    "conversation_id": cid,
                    "squad_task_id": None,
                    "sequence": bot_seq,
                    "round": 1,
                    "model": first_model_cfg.get("model"),
                    "effort": first_model_cfg.get("effort"),
                    "progress": [],
                },
            )

            turn_state = {
                "conversation_only": conversation_only,
                "turn_id": "turn-" + uuid.uuid4().hex,
                "conversation_id": cid,
                "message_id": bot_msg["id"],
                "message_ids": [bot_msg["id"]],
                "user_message_id": user_msg["id"],
                "agent": selected_agent,
                "status": "running",
                "run_id": None,
                "run_ids": [],
                "collaboration_id": None,
                "progress_step": "Yanıt hazırlanıyor...",
                "started_at": time.time(),
            }
            self._active_turn = turn_state

        threading.Thread(
            target=self._run_chat_turn,
            args=(cid, bot_msg["id"], selected_agent, text, project_id, write, confirm_write, full_access),
            name=f"agent-chat-{cid[:8]}",
            daemon=True,
        ).start()

        return {
            "conversation_id": cid,
            "user_message": user_msg,
            "assistant_message": bot_msg,
            "agent": selected_agent,
        }

    def continue_discussion(self, conversation_id: str | None = None) -> dict:
        """Trigger 1 additional mutual evaluation round between Codex and Antigravity in Birlikte mode."""
        with self._lock:
            if self._active_turn and self._active_turn.get("status") in {"running", "cancelling"}:
                raise RuntimeError("Zaten devam eden bir yanıt üretimi var. Lütfen bekleyin veya iptal edin.")
            conv = self.store.get(conversation_id) if conversation_id else self.store.get_active()
            cid = conv["id"]
            project_id = conv.get("project_id")
            messages = conv.get("messages", [])
            assistant_msgs = [m for m in messages if m.get("role") == "assistant" and (m.get("content") or "").strip()]
            if len(assistant_msgs) < 2:
                raise RuntimeError("Tartışmayı sürdürmek için önce Birlikte modunda en az bir tur tamamlanmış olmalıdır.")

            last_round = max(
                int((m.get("metadata") or {}).get("round") or 1)
                for m in assistant_msgs
            )
            next_round = last_round + 1
            last_task_id = next(
                ((m.get("metadata") or {}).get("squad_task_id") for m in reversed(assistant_msgs) if (m.get("metadata") or {}).get("squad_task_id")),
                None,
            )

            codex_model_cfg = self.store.get_agent_model(cid, "codex")
            codex_msg = self.store.append_message(
                cid, "assistant", "", sender="codex",
                metadata={
                    "status": "starting",
                    "agent": "codex",
                    "sender": "codex",
                    "recipient": "antigravity",
                    "conversation_id": cid,
                    "squad_task_id": last_task_id,
                    "sequence": self._next_sequence(conv),
                    "round": next_round,
                    "collaboration": True,
                    "model": codex_model_cfg.get("model"),
                    "effort": codex_model_cfg.get("effort"),
                    "progress": [],
                },
            )

            turn_state = {
                "turn_id": "turn-" + uuid.uuid4().hex,
                "conversation_id": cid,
                "message_id": codex_msg["id"],
                "conversation_only": all((m.get("metadata") or {}).get("conversation_only", True)
                                         for m in assistant_msgs[-2:]),
                "message_ids": [codex_msg["id"]],
                "user_message_id": None,
                "agent": "collaboration",
                "status": "running",
                "run_id": None,
                "run_ids": [],
                "collaboration_id": None,
                "progress_step": f"Tur {next_round} · Ajanlar tartışmayı sürdürüyor...",
                "started_at": time.time(),
            }
            self._active_turn = turn_state

        threading.Thread(
            target=self._run_continue_discussion_turn,
            args=(cid, codex_msg["id"], next_round, last_task_id, project_id),
            name=f"agent-cont-{cid[:8]}",
            daemon=True,
        ).start()

        return {
            "conversation_id": cid,
            "assistant_message": codex_msg,
            "round": next_round,
            "agent": "collaboration",
        }

    def cancel_active(self) -> dict:
        with self._lock:
            if not self._active_turn or self._active_turn.get("status") != "running":
                return {"cancelled": False, "message": "Aktif bir işlem yok"}
            turn = dict(self._active_turn)
            self._active_turn["status"] = "cancelling"
            self._active_turn["cancel_requested"] = True

        collab_id = turn.get("collaboration_id")
        if collab_id:
            try:
                self.agent_service.cancel_collaboration(collab_id)
            except Exception as exc:
                log.warning("Cancel collaboration failed: %s", exc)

        run_ids_to_cancel: list[str] = []
        for rid in turn.get("run_ids", []):
            if isinstance(rid, str) and rid and rid not in run_ids_to_cancel:
                run_ids_to_cancel.append(rid)
        single_rid = turn.get("run_id")
        if isinstance(single_rid, str) and single_rid and single_rid not in run_ids_to_cancel:
            run_ids_to_cancel.append(single_rid)

        for rid in run_ids_to_cancel:
            try:
                self.agent_service.cancel(rid)
            except Exception as exc:
                log.warning("Cancel run %s failed: %s", rid, exc)

        with self._lock:
            if self._active_turn and self._active_turn.get("turn_id") == turn.get("turn_id"):
                self._active_turn["status"] = "cancelled"
            cid = turn["conversation_id"]
            all_mids = list(turn.get("message_ids") or [])
            if turn.get("message_id") and turn["message_id"] not in all_mids:
                all_mids.append(turn["message_id"])
            try:
                conv = self.store.get(cid)
                for mid in all_mids:
                    msg = next((m for m in conv.get("messages", []) if m["id"] == mid), None)
                    if not msg:
                        continue
                    meta = dict(msg.get("metadata") or {})
                    if meta.get("status") in {"completed", "failed"}:
                        continue
                    existing = (msg.get("content") or "").strip()
                    cancel_text = existing + "\n\n⏹️ *İşlem kullanıcı tarafından iptal edildi.*" if existing else "⏹️ *İşlem kullanıcı tarafından iptal edildi.*"
                    meta["status"] = "cancelled"
                    self.store.update_message_content(cid, mid, cancel_text, metadata=meta)
            except Exception:
                pass
        return {"cancelled": True}

    def poll_active(self) -> dict:
        """Poll the state, current message, and full conversation message list of the active chat turn."""
        with self._lock:
            if not self._active_turn:
                return {"active": False}
            turn = dict(self._active_turn)
            cid = turn["conversation_id"]
            mid = turn["message_id"]

        try:
            conv = self.store.get(cid)
            messages = conv.get("messages", [])
            self._enrich_messages(messages)
            msg = next((m for m in messages if m["id"] == mid), None)
            meta = dict(msg["metadata"]) if (msg and msg.get("metadata")) else {}
            if turn.get("progress_step") and "progress_step" not in meta:
                meta["progress_step"] = turn["progress_step"]
            project_id = conv.get("project_id") or self.agent_service.projects.selected()["id"]
            writer_status = {}
            if isinstance(project_id, str) and hasattr(self.agent_service, "_writer_status"):
                writer_status = self.agent_service._writer_status(
                    self.agent_service.projects.get(project_id)["path"]
                )
            return {
                "active": turn.get("status") == "running",
                "status": turn.get("status"),
                "agent": turn.get("agent"),
                "conversation_id": cid,
                "message_id": mid,
                "content": msg["content"] if msg else "",
                "metadata": meta,
                "messages": messages,
                "single_writer": writer_status,
            }
        except Exception as exc:
            return {"active": False, "error": str(exc)}

    def _enrich_messages(self, messages):
        # Detached read model only. Polling neither rewrites history nor runs
        # project tests. An absent receipt is never treated as a passed check.
        for item in messages[-200:]:
            meta = item.get('metadata') or {}
            run_id = meta.get('run_id')
            if run_id and hasattr(self.agent_service, 'run_evidence'):
                evidence = self.agent_service.run_evidence(run_id)
                if isinstance(evidence, dict) and evidence:
                    meta['host_evidence'] = evidence

    def _is_turn_cancelled(self, initial_msg_id: str | None = None) -> bool:
        with self._lock:
            if not self._active_turn:
                return True
            if initial_msg_id and initial_msg_id not in self._active_turn.get("message_ids", [self._active_turn.get("message_id")]):
                return True
            return bool(
                self._active_turn.get("cancel_requested")
                or self._active_turn.get("status") in {"cancelling", "cancelled"}
            )

    def _set_turn_progress(self, step_text: str, current_msg_id: str | None = None, run_id: str | None = None,
                           *, owner_msg_id: str | None = None):
        with self._lock:
            if not self._active_turn or self._active_turn.get("status") != "running":
                return False
            owner = owner_msg_id or current_msg_id
            if not owner or self._is_turn_cancelled(owner):
                return False
            self._active_turn["progress_step"] = step_text
            if current_msg_id:
                self._active_turn["message_id"] = current_msg_id
                mids = self._active_turn.setdefault("message_ids", [])
                if current_msg_id not in mids:
                    mids.append(current_msg_id)
            if isinstance(run_id, str) and run_id:
                self._active_turn["run_id"] = run_id
                rids = self._active_turn.setdefault("run_ids", [])
                if run_id not in rids:
                    rids.append(run_id)
            return True

    def _finish_turn(self, owner_msg_id, status):
        """Only this generation's live owner can make its terminal transition."""
        if status not in {"completed", "failed"}:
            raise ValueError("Invalid worker terminal state")
        with self._lock:
            if not self._active_turn or self._active_turn.get("status") != "running" or self._is_turn_cancelled(owner_msg_id):
                return False
            self._active_turn["status"] = status
            self._active_turn["run_id"] = None
            return True

    def _publish_run_update(self, cid, msg_id, content, metadata, *, provider=None, session=None):
        """The cancellation fence and persistence share one ownership lock."""
        with self._lock:
            if not getattr(self, '_active_turn', None) or self._is_turn_cancelled(msg_id) or self._active_turn.get('status') != 'running':
                return False
            if provider and session:
                self.store.set_agent_session(cid, provider, session)
            if metadata is not None:
                self.store.update_message_content(cid, msg_id, content, metadata=metadata)
            return True

    def _run_chat_turn(self, cid: str, msg_id: str, agent: str, prompt: str,
                       project_id: str | None, write: bool, confirm_write: bool, full_access: bool = False):
        try:
            if agent == "antigravity":
                self._run_antigravity_turn(cid, msg_id, prompt, project_id, write, confirm_write, full_access)
            elif agent == "codex":
                self._run_codex_turn(cid, msg_id, prompt, project_id, write, confirm_write, full_access)
            elif agent in {"collaboration", "both"}:
                self._run_collaboration_turn(cid, msg_id, prompt, project_id, write=write, confirm_write=confirm_write, full_access=full_access)
            else:
                raise ValueError(f"Bilinmeyen ajan: {agent}")
        except Exception as exc:
            if self._is_turn_cancelled(msg_id):
                return
            log.warning("Chat turn error for agent %s: %s", agent, exc)
            log.debug("Chat turn error details", exc_info=True)
            err_text = self._format_error(agent, exc)
            with self._lock:
                target_mid = (self._active_turn or {}).get("message_id") or msg_id
                if self._finish_turn(msg_id, "failed"):
                    self.store.update_message_content(
                        cid, target_mid, err_text, metadata={"status": "failed", "error": str(exc)}
                    )
        finally:
            if agent in {"collaboration", "both"}:
                self._finish_group_task(cid, msg_id, project_id)

    def _finish_group_task(self, cid: str, first_msg_id: str, project_id: str | None) -> None:
        try:
            conv = self.store.get(cid)
            messages = conv.get("messages", [])
            first = next((m for m in messages if m.get("id") == first_msg_id), None)
            task_id = (first or {}).get("metadata", {}).get("squad_task_id")
            if not task_id:
                return
            related = [m for m in messages if m.get("role") == "assistant"
                       and (m.get("metadata") or {}).get("squad_task_id") == task_id]
            completed = (not self._is_turn_cancelled(first_msg_id) and bool(related)
                         and all((m.get("metadata") or {}).get("status") == "completed"
                                 for m in related))
            summary = "Grup incelemesi tamamlandı." if completed else "Grup incelemesi iptal edildi veya başarısız oldu."
            self.agent_service.squad_finish_group_task(
                task_id, project_id, completed=completed, summary=summary
            )
        except Exception as exc:
            log.warning("Squad group completion warning: %s", exc)

    @staticmethod
    def _extract_metrics(run: dict, bubble_started_at: float) -> dict:
        started = float(run.get("started_at") or bubble_started_at or time.time())
        finished = float(run.get("finished_at") or time.time())
        first_event = run.get("first_event_at")
        first_text = run.get("first_text_at")
        return {
            "first_event_ms": round((float(first_event) - started) * 1000, 1) if isinstance(first_event, (int, float)) else None,
            "first_text_ms": round((float(first_text) - started) * 1000, 1) if isinstance(first_text, (int, float)) else None,
            "total_ms": round((finished - bubble_started_at) * 1000, 1),
        }

    def _execute_antigravity_bubble(self, cid: str, msg_id: str, full_prompt: str,
                                    project_id: str | None, write: bool, confirm_write: bool,
                                    *, use_session: bool = True, squad_task_id: str | None = None,
                                    base_meta: dict | None = None, full_access: bool = False) -> str:
        """Run a single Antigravity message bubble, stream its output, and return final text."""
        bubble_t0 = time.time()
        conversation_only = self._conversation_only(cid)
        if conversation_only:
            write = full_access = confirm_write = use_session = False
        full_prompt = self._communication_prompt(cid, full_prompt)
        conv = self.store.get(cid)
        prev_session = conv.get("sessions", {}).get("antigravity") if use_session else None
        model_cfg = self.store.get_agent_model(cid, "antigravity")
        selected_model = model_cfg.get("model")
        selected_effort = model_cfg.get("effort")
        meta = dict(base_meta or {})
        meta["conversation_only"] = conversation_only
        meta["model"] = selected_model
        meta["effort"] = selected_effort

        if self._is_turn_cancelled(msg_id):
            return ""

        dispatch_kwargs = {
            "title": f"Chat · {full_prompt[:40]}",
            "project_id": project_id,
            "write": write,
            "confirm_write": confirm_write,
            "full_access": full_access,
            "conversation_id": prev_session,
        }
        if conversation_only:
            dispatch_kwargs["conversation_only"] = True
        dispatch_res = self.agent_service.dispatch_antigravity(
            full_prompt, chat_mode=True, squad_task_id=squad_task_id,
            model=selected_model, effort=selected_effort, **dispatch_kwargs
        )

        run_id = dispatch_res["run"]["id"]
        meta['run_id'] = run_id
        meta["checkpoint"] = dispatch_res["run"].get("checkpoint")
        meta["permission_level"] = "full" if full_access else ("project" if write else "read-only")
        squad_info = dispatch_res.get("squad") or {}
        if isinstance(squad_info, dict) and "connected" in squad_info:
            meta["squad_connected"] = bool(squad_info.get("connected"))
            if squad_info.get("error"):
                meta["squad_error"] = squad_info["error"]

        with self._lock:
            if self._is_turn_cancelled(msg_id):
                self.agent_service.cancel(run_id)
                return ""
            self._set_turn_progress("Antigravity yanıtlıyor...", current_msg_id=msg_id, run_id=run_id)

        run, status = self._stream_antigravity_run(cid, msg_id, run_id, meta, save_session=use_session)
        if self._is_turn_cancelled(msg_id) or status == "cancelled":
            return ""

        # Only a stale non-mutating session may retry, with unchanged permissions.
        if status != "completed":
            errors_str = "\n".join(str(x) for x in run.get("errors", [])).lower()
            is_quota_or_model_err = any(
                k in errors_str for k in ("quota", "rate limit", "429", "invalid model", "model not found", "unknown model")
            )
            has_perm_err = any(k in errors_str for k in ("permission", "denied", "jetski", "auto-denied"))
            # A denied group review may be retried from the supplied evidence only.
            # Do not escalate permissions or replay a potentially mutating task.
            if (not conversation_only and not write and not full_access and has_perm_err and not is_quota_or_model_err
                    and meta.get("collaboration") and status == "failed"):
                review_prompt = (
                    "Your previous attempt requested a command that headless read-only mode denied. "
                    "Review ONLY the evidence quoted below. Do not call any tool, command, terminal, "
                    "file reader, or network resource. State clearly which claims you cannot "
                    "independently verify from the supplied text. Never claim you inspected files.\n\n"
                    "--- SUPPLIED GROUP CONTEXT ---\n" + full_prompt
                )
                retry_res = self.agent_service.dispatch_antigravity(
                    review_prompt, chat_mode=True, squad_task_id=squad_task_id,
                    title="Group review from supplied text", project_id=project_id,
                    write=False, confirm_write=False, full_access=False,
                    conversation_id=None, model=selected_model, effort=selected_effort,
                )
                run_id = retry_res["run"]["id"]
                meta["run_id"] = run_id
                meta["review_scope"] = "supplied-text-only"
                self._set_turn_progress("Antigravity verilen metni araçsız inceliyor...", current_msg_id=msg_id, run_id=run_id)
                run, status = self._stream_antigravity_run(cid, msg_id, run_id, meta, save_session=False)
            elif (not write and not full_access and not has_perm_err and not is_quota_or_model_err
                  and prev_session and status == "failed"):
                retry_res = self.agent_service.dispatch_antigravity(
                    full_prompt, chat_mode=True, squad_task_id=squad_task_id,
                    title="Chat Retry", project_id=project_id, write=False, confirm_write=False,
                    full_access=False, conversation_id=None, model=selected_model, effort=selected_effort,
                )
                run_id = retry_res["run"]["id"]
                meta["run_id"] = run_id
                self._set_turn_progress("Antigravity salt-okunur yeni oturumla yanıtlıyor...", current_msg_id=msg_id, run_id=run_id)
                run, status = self._stream_antigravity_run(cid, msg_id, run_id, meta, save_session=use_session)

        if self._is_turn_cancelled(msg_id) or status == "cancelled":
            return ""

        if status == "completed":
            final_content = run.get("result", "").strip() or "İşlem tamamlandı ancak yanıt metni boş döndü."
            if meta.get("review_scope") == "supplied-text-only":
                final_content = (
                    "Not: Bu inceleme yalnız konuşmada sağlanan metne dayanır; "
                    "proje dosyaları bağımsız doğrulanmadı.\n\n" + final_content
                )
            meta.update({
                "status": "completed",
                "usage": run.get("usage"),
                "metrics": self._extract_metrics(run, bubble_t0),
            })
            return final_content if self._publish_run_update(cid, msg_id, final_content, meta) else ""

        errors = run.get("errors", [])
        err_msg = "\n".join(errors) if errors else "Antigravity görevi tamamlayamadı."
        raise RuntimeError(err_msg)

    def _stream_antigravity_run(self, cid: str, msg_id: str, run_id: str, meta: dict, save_session: bool = True):
        run = {}
        status = None
        last_content = None
        last_status = None
        last_session_saved = None
        while True:
            if self._is_turn_cancelled(msg_id):
                self.agent_service.cancel(run_id)
                return run, "cancelled"
            run = self.agent_service.antigravity.get(run_id)
            status = run.get("status")
            content = run.get("result", "")
            progress = run.get("progress_log", [])
            new_session = run.get("conversation_id")
            session = new_session if save_session and new_session != last_session_saved else None
            changed = content != last_content or status != last_status
            step_meta = None
            if changed:
                step_meta = dict(meta)
                step_meta.update({"status": status, "progress": progress})
            if not self._publish_run_update(cid, msg_id, content, step_meta, provider='antigravity', session=session):
                self.agent_service.cancel(run_id)
                return run, "cancelled"
            last_content, last_status = content, status
            if session: last_session_saved = session

            if status in self.agent_service.antigravity.TERMINAL:
                break
            time.sleep(0.15)
        return run, status

    def _run_antigravity_turn(self, cid: str, msg_id: str, prompt: str,
                              project_id: str | None, write: bool, confirm_write: bool, full_access: bool = False):
        conv = self.store.get(cid)
        user_mid = (self._active_turn or {}).get("user_message_id")
        exclude = {msg_id, user_mid} if user_mid else {msg_id}
        msg_obj = next((m for m in conv.get("messages", []) if m["id"] == msg_id), None)
        base_meta = dict((msg_obj or {}).get("metadata") or {})
        has_session = bool((conv.get("sessions") or {}).get("antigravity"))

        full_prompt = self._build_single_chat_prompt(
            "antigravity", prompt, conv.get("messages", []), exclude, write, has_session=has_session, full_access=full_access
        )
        self._execute_antigravity_bubble(
            cid, msg_id, full_prompt, project_id, write, confirm_write,
            use_session=True, base_meta=base_meta, full_access=full_access,
        )
        if self._is_turn_cancelled(msg_id):
            return
        with self._lock:
            self._finish_turn(msg_id, "completed")

    def _execute_codex_bubble(self, cid: str, msg_id: str, full_prompt: str,
                              project_id: str | None, write: bool, confirm_write: bool,
                              *, use_session: bool = True, squad_task_id: str | None = None,
                              base_meta: dict | None = None, full_access: bool = False) -> str:
        """Run a single Codex message bubble, stream its output, and return final text."""
        bubble_t0 = time.time()
        conversation_only = self._conversation_only(cid)
        if conversation_only:
            write = full_access = confirm_write = use_session = False
        full_prompt = self._communication_prompt(cid, full_prompt)
        conv = self.store.get(cid)
        prev_session = conv.get("sessions", {}).get("codex") if use_session else None
        model_cfg = self.store.get_agent_model(cid, "codex")
        selected_model = model_cfg.get("model")
        selected_effort = model_cfg.get("effort")
        meta = dict(base_meta or {})
        meta["conversation_only"] = conversation_only
        meta["model"] = selected_model
        meta["effort"] = selected_effort

        probe = self.agent_service.codex.probe()
        if not probe.get("ready"):
            raise RuntimeError(f"Codex CLI hazır değil: {probe.get('error', 'Giriş yapılmamış veya binary eksik')}")

        if self._is_turn_cancelled(msg_id):
            return ""

        dispatch_kwargs = {
            "title": f"Chat · {full_prompt[:40]}",
            "project_id": project_id,
            "write": write,
            "confirm_write": confirm_write,
            "full_access": full_access,
            "resume_thread_id": prev_session,
        }
        if conversation_only:
            dispatch_kwargs["conversation_only"] = True
        dispatch_res = self.agent_service.dispatch_codex(
            full_prompt, chat_mode=True, squad_task_id=squad_task_id,
            model=selected_model, effort=selected_effort, **dispatch_kwargs
        )

        run_id = dispatch_res["run"]["id"]
        meta['run_id'] = run_id
        meta["checkpoint"] = dispatch_res["run"].get("checkpoint")
        meta["permission_level"] = "full" if full_access else ("project" if write else "read-only")
        squad_info = dispatch_res.get("squad") or {}
        if isinstance(squad_info, dict) and "connected" in squad_info:
            meta["squad_connected"] = bool(squad_info.get("connected"))
            if squad_info.get("error"):
                meta["squad_error"] = squad_info["error"]

        with self._lock:
            if self._is_turn_cancelled(msg_id):
                self.agent_service.cancel(run_id)
                return ""
            self._set_turn_progress("Codex yanıtlıyor...", current_msg_id=msg_id, run_id=run_id)

        run, status = self._stream_codex_run(cid, msg_id, run_id, meta, save_session=use_session)
        if self._is_turn_cancelled(msg_id) or status == "cancelled":
            return ""

        # If resuming a stale thread_id failed (and not due to model/quota error), retry once with a fresh thread
        if status != "completed" and prev_session and not write and not full_access:
            errors_str = "\n".join(str(x) for x in run.get("errors", [])).lower()
            is_quota_or_model_err = any(
                k in errors_str for k in ("quota", "rate limit", "429", "invalid model", "model not found", "unknown model", "unsupported")
            )
            has_perm_err = any(k in errors_str for k in ("permission", "denied", "sandbox"))
            if not is_quota_or_model_err and not has_perm_err:
                retry_res = self.agent_service.dispatch_codex(
                    full_prompt, chat_mode=True, squad_task_id=squad_task_id,
                    title="Chat Retry", project_id=project_id,
                    write=False, confirm_write=False, full_access=False, resume_thread_id=None,
                    model=selected_model, effort=selected_effort,
                )
                run_id = retry_res["run"]["id"]
                meta["run_id"] = run_id
                self._set_turn_progress("Codex yeni oturumla yanıtlıyor...", current_msg_id=msg_id, run_id=run_id)
                run, status = self._stream_codex_run(cid, msg_id, run_id, meta, save_session=use_session)

        if self._is_turn_cancelled(msg_id) or status == "cancelled":
            return ""

        if status == "completed":
            final_content = run.get("result", "").strip() or "Codex görevi tamamlandı."
            meta.update({
                "status": "completed",
                "usage": run.get("usage"),
                "metrics": self._extract_metrics(run, bubble_t0),
            })
            return final_content if self._publish_run_update(cid, msg_id, final_content, meta) else ""

        errors = run.get("errors", [])
        err_msg = "\n".join(errors) if errors else "Codex görevi tamamlayamadı."
        raise RuntimeError(err_msg)

    def _stream_codex_run(self, cid: str, msg_id: str, run_id: str, meta: dict, save_session: bool = True):
        run = {}
        status = None
        last_content = None
        last_status = None
        last_thread_saved = None
        while True:
            if self._is_turn_cancelled(msg_id):
                self.agent_service.cancel(run_id)
                return run, "cancelled"
            run = self.agent_service.codex.get(run_id)
            status = run.get("status")
            content = run.get("result", "")
            new_thread = run.get("thread_id")
            session = new_thread if save_session and new_thread != last_thread_saved else None
            changed = content != last_content or status != last_status
            step_meta = None
            if changed:
                step_meta = dict(meta)
                step_meta.update({"status": status})
            if not self._publish_run_update(cid, msg_id, content, step_meta, provider='codex', session=session):
                self.agent_service.cancel(run_id)
                return run, "cancelled"
            last_content, last_status = content, status
            if session: last_thread_saved = session

            if status in self.agent_service.codex.TERMINAL:
                break
            time.sleep(0.15)
        return run, status

    def _run_codex_turn(self, cid: str, msg_id: str, prompt: str,
                        project_id: str | None, write: bool, confirm_write: bool, full_access: bool = False):
        conv = self.store.get(cid)
        user_mid = (self._active_turn or {}).get("user_message_id")
        exclude = {msg_id, user_mid} if user_mid else {msg_id}
        msg_obj = next((m for m in conv.get("messages", []) if m["id"] == msg_id), None)
        base_meta = dict((msg_obj or {}).get("metadata") or {})
        has_session = not self._conversation_only(cid) and bool((conv.get("sessions") or {}).get("codex"))

        full_prompt = self._build_single_chat_prompt(
            "codex", prompt, conv.get("messages", []), exclude, write, has_session=has_session, full_access=full_access
        )
        self._execute_codex_bubble(
            cid, msg_id, full_prompt, project_id, write, confirm_write,
            use_session=True, base_meta=base_meta, full_access=full_access,
        )
        if self._is_turn_cancelled(msg_id):
            return
        with self._lock:
            self._finish_turn(msg_id, "completed")

    def _create_group_bubble(self, cid: str, sender: str, recipient: str,
                             squad_task_id: str | None, round_num: int, *, owner_msg_id: str) -> dict:
        with self._lock:
            if self._is_turn_cancelled(owner_msg_id) or self._active_turn.get("status") != "running":
                raise RuntimeError("Eski/iptal edilmiş tur yeni mesaj oluşturamaz")
            return self._append_group_bubble(cid, sender, recipient, squad_task_id, round_num, owner_msg_id)

    def _append_group_bubble(self, cid, sender, recipient, squad_task_id, round_num, owner_msg_id):
        conv = self.store.get(cid)
        seq = self._next_sequence(conv)
        model_cfg = self.store.get_agent_model(cid, sender)
        msg = self.store.append_message(
            cid, "assistant", "", sender=sender,
            metadata={
                "status": "starting",
                "agent": sender,
                "sender": sender,
                "recipient": recipient,
                "conversation_id": cid,
                "squad_task_id": squad_task_id,
                "sequence": seq,
                "round": round_num,
                "collaboration": True,
                "model": model_cfg.get("model"),
                "effort": model_cfg.get("effort"),
                "progress": [],
            },
        )
        self._set_turn_progress(f"{sender.upper()} → {recipient.upper()} yanıtlıyor...", current_msg_id=msg["id"], owner_msg_id=owner_msg_id)
        return msg

    def _run_collaboration_turn(self, cid: str, first_msg_id: str, prompt: str, project_id: str | None,
                                write: bool = False, confirm_write: bool = False, full_access: bool = False):
        """Multi-participant group chat over Squad: parallel Round 1 + parallel Round 2 mutual evaluation."""
        if self._is_turn_cancelled(first_msg_id):
            return

        targets = self._resolve_group_targets(prompt)
        rounds = self.MAX_GROUP_ROUNDS
        if self._conversation_only(cid) and not re.search(r"tartış|değerlendir|karşılaştır|birbirin|review", prompt, re.I):
            rounds = 1
        conv = self.store.get(cid)
        user_mid = (self._active_turn or {}).get("user_message_id")
        history_block = self._format_history_context(
            conv.get("messages", []),
            exclude_ids={first_msg_id, user_mid} if user_mid else {first_msg_id},
            limit=8,
        )

        # 1. Squad koordinasyon görevi ve kullanıcı mesajının Squad'a iletilmesi
        squad_task_id = None
        squad_connected = False
        squad_error = ""
        try:
            conn_info = self.agent_service.check_squad_connection(project_id)
            if isinstance(conn_info, dict):
                squad_connected = bool(conn_info.get("connected"))
                squad_error = str(conn_info.get("error") or "")
            if squad_connected:
                task = self.agent_service.squad_create_group_task(
                    f"Grup Sohbeti · {prompt[:40]}", prompt, project_id=project_id
                )
                if isinstance(task, dict):
                    squad_task_id = task.get("id")
                self.agent_service.squad_send_message(
                    MultiAgentService.MANAGER_ID, "@all",
                    f"[Kullanıcı Mesajı]: {prompt}",
                    task_id=squad_task_id, project_id=project_id,
                )
        except Exception as exc:
            squad_error = str(exc)
            log.warning("Squad group setup warning: %s", exc)

        # Update user message metadata with squad_task_id if available
        if user_mid and squad_task_id:
            try:
                conv_now = self.store.get(cid)
                u_msg = next((m for m in conv_now.get("messages", []) if m["id"] == user_mid), None)
                if u_msg:
                    u_meta = dict(u_msg.get("metadata") or {})
                    u_meta["squad_task_id"] = squad_task_id
                    self.store.update_message_content(cid, user_mid, u_msg["content"], metadata=u_meta)
            except Exception:
                pass
        if squad_task_id:
            try:
                current = self.store.get(cid)
                first = next((m for m in current.get("messages", []) if m["id"] == first_msg_id), None)
                if first:
                    first_meta = dict(first.get("metadata") or {})
                    first_meta["squad_task_id"] = squad_task_id
                    self.store.update_message_content(cid, first_msg_id, first["content"], metadata=first_meta)
            except Exception:
                pass

        # If user addressed only a single agent inside Birlikte mode
        if len(targets) == 1:
            only_agent = targets[0]
            conv_now = self.store.get(cid)
            first_msg = next((m for m in conv_now.get("messages", []) if m["id"] == first_msg_id), None)
            base_meta = dict((first_msg or {}).get("metadata") or {})
            base_meta.update({
                "sender": only_agent,
                "recipient": "user",
                "squad_task_id": squad_task_id,
                "squad_connected": squad_connected,
                "squad_error": squad_error,
                "collaboration": True,
                "round": 1,
            })
            single_prompt = self._build_single_chat_prompt(
                only_agent, prompt, conv_now.get("messages", []),
                {first_msg_id, user_mid} if user_mid else {first_msg_id}, write=write,
                full_access=full_access,
            )
            if only_agent == "codex":
                reply = self._execute_codex_bubble(
                    cid, first_msg_id, single_prompt, project_id, write, confirm_write,
                    use_session=True, squad_task_id=squad_task_id, base_meta=base_meta, full_access=full_access,
                )
                if squad_connected and reply:
                    self.agent_service.squad_send_message(
                        MultiAgentService.CODEX_ID, "@all", reply, task_id=squad_task_id, project_id=project_id
                    )
            else:
                reply = self._execute_antigravity_bubble(
                    cid, first_msg_id, single_prompt, project_id, write, confirm_write,
                    use_session=True, squad_task_id=squad_task_id, base_meta=base_meta, full_access=full_access,
                )
                if squad_connected and reply:
                    self.agent_service.squad_send_message(
                        MultiAgentService.ANTIGRAVITY_ID, "@all", reply, task_id=squad_task_id, project_id=project_id
                    )
            with self._lock:
                self._finish_turn(first_msg_id, "completed")
            return

        # ── TUR 1: Codex ve Antigravity'nin Bağımsız Yanıtları (PARALEL BAŞLATILIR) ──
        conv_now = self.store.get(cid)
        first_msg = next((m for m in conv_now.get("messages", []) if m["id"] == first_msg_id), None)
        codex_r1_meta = dict((first_msg or {}).get("metadata") or {})
        codex_r1_meta.update({
            "sender": "codex",
            "recipient": "all",
            "conversation_id": cid,
            "squad_task_id": squad_task_id,
            "squad_connected": squad_connected,
            "squad_error": squad_error,
            "round": 1,
            "collaboration": True,
        })

        # Create Antigravity's Round 1 bubble immediately so both bubbles exist and stream in parallel
        agy_r1_msg = self._create_group_bubble(
            cid, sender="antigravity", recipient="all",
            squad_task_id=squad_task_id, round_num=1, owner_msg_id=first_msg_id,
        )
        agy_r1_id = agy_r1_msg["id"]
        agy_r1_meta = dict(agy_r1_msg.get("metadata") or {})
        agy_r1_meta.update({
            "squad_connected": squad_connected,
            "squad_error": squad_error,
        })

        history_section = f"\n--- ÖNCEKİ GRUP SOHBETİ GEÇMİŞİ ---\n{history_block}\n" if history_block else ""
        codex_tool_rule = (
            ("- Bu görevde tek yazıcı sensin. Açık Tam Yetki onayı var; korunan kayıt ve ASTER kurallarını koru.\n" if full_access else
             "- Bu görevde tek yazıcı sensin; yalnız seçili proje dosyalarını değiştir. Proje dışına yazma; izin reddinde dur.\n")
            if write else
            "- Hiçbir kabuk komutu çalıştırmadan doğrudan sohbet yanıtı ver.\n"
        )
        agy_tool_rule = (
            "- İncelemecisin, yazma iznin YOK. Codex'in tamamlanan yanıtını değerlendir. "
            "Gerekli olursa yalnız doğrudan salt-okunur dosya araçlarını kullan; command/terminal aracı çağırma. "
            "Dosyaları okuyamazsan bunu belirt; kendin düzenleme.\n"
            if write else
            "- Hiçbir araç (tool/command) çağırmadan doğrudan sohbet yanıtı ver.\n"
        )
        codex_r1_prompt = (
            "Quartz çok katılımcılı grup sohbetindesin. Katılımcılar: Kullanıcı, sen (Codex) ve Antigravity.\n"
            "- Kullanıcının mesajına kendi bağımsız değerlendirmenle, doğal ve net biçimde yanıt ver.\n"
            "- Antigravity de eş zamanlı olarak kendi ayrı mesajını yazıyor; gerekirse ona da doğrudan bir soru sorabilir veya fikrini isteyebilirsin.\n"
            "- Kendi kabuğundan 'squad' komutu çalıştırma ve dahili görev kimliklerinden bahsetme.\n"
            f"{codex_tool_rule}"
            f"{history_section}"
            f"\n--- KULLANICININ MESAJI ---\n{prompt}"
        )
        agy_r1_prompt = (
            "Quartz çok katılımcılı grup sohbetindesin. Katılımcılar: Kullanıcı, Codex ve sen (Antigravity).\n"
            "- Kullanıcının mesajına kendi bağımsız bakış açınla, doğal ve net biçimde yanıt ver.\n"
            "- Codex de eş zamanlı olarak kendi ayrı mesajını yazıyor; gerekirse ona da bir soru/değerlendirme yöneltebilirsin.\n"
            "- Dahili görev kimliklerinden veya köprü adlarından bahsetme.\n"
            f"{agy_tool_rule}"
            f"{history_section}"
            f"\n--- KULLANICININ MESAJI ---\n{prompt}"
        )

        self._set_turn_progress(
            f"Tur 1/{rounds} · Codex yazıyor, ardından Antigravity inceleyecek..." if write else
            f"Tur 1/{rounds} · Codex ve Antigravity paralel yanıt üretiyor...", current_msg_id=first_msg_id)
        r1_state = {"codex_text": "", "codex_ok": False, "agy_text": "", "agy_ok": False}

        def run_codex_r1():
            try:
                text_out = self._execute_codex_bubble(
                    cid, first_msg_id, codex_r1_prompt, project_id, write, confirm_write,
                    use_session=False, squad_task_id=squad_task_id, base_meta=codex_r1_meta, full_access=full_access,
                )
                r1_state["codex_text"] = text_out
                r1_state["codex_ok"] = bool(text_out.strip())
                if squad_connected and r1_state["codex_ok"]:
                    self.agent_service.squad_send_message(
                        MultiAgentService.CODEX_ID, MultiAgentService.ANTIGRAVITY_ID,
                        text_out, task_id=squad_task_id, project_id=project_id,
                    )
            except Exception as exc:
                if self._is_turn_cancelled(first_msg_id):
                    return
                err_msg = self._format_error("codex", exc)
                codex_r1_meta.update({"status": "failed", "error": str(exc)})
                self.store.update_message_content(cid, first_msg_id, err_msg, metadata=codex_r1_meta)

        def run_agy_r1():
            try:
                review_prompt = agy_r1_prompt
                if write:
                    codex_evidence = r1_state["codex_text"].strip()
                    review_prompt += (
                        "\n--- CODEX'İN BU GÖREVDEKİ TAMAMLANAN YANITI (DOĞRULANMAMIŞ KANIT) ---\n"
                        + (codex_evidence[:40_000] if codex_evidence else
                           "Codex yanıt üretemedi; bağımsız doğrulama yapamıyorsan bunu açıkça belirt.")
                        + "\n--- KANIT SONU ---\n"
                    )
                text_out = self._execute_antigravity_bubble(
                    cid, agy_r1_id, review_prompt, project_id, False, False,
                    use_session=False, squad_task_id=squad_task_id, base_meta=agy_r1_meta,
                )
                r1_state["agy_text"] = text_out
                r1_state["agy_ok"] = bool(text_out.strip())
                if squad_connected and r1_state["agy_ok"]:
                    self.agent_service.squad_send_message(
                        MultiAgentService.ANTIGRAVITY_ID, MultiAgentService.CODEX_ID,
                        text_out, task_id=squad_task_id, project_id=project_id,
                    )
            except Exception as exc:
                if self._is_turn_cancelled(first_msg_id):
                    return
                err_msg = self._format_error("antigravity", exc)
                agy_r1_meta.update({"status": "failed", "error": str(exc)})
                self.store.update_message_content(cid, agy_r1_id, err_msg, metadata=agy_r1_meta)

        t_codex_r1 = threading.Thread(target=run_codex_r1, name=f"collab-c1-{cid[:6]}", daemon=True)
        t_agy_r1 = threading.Thread(target=run_agy_r1, name=f"collab-a1-{cid[:6]}", daemon=True)
        t_codex_r1.start()
        if write:
            t_codex_r1.join()
            if not self._is_turn_cancelled(first_msg_id):
                t_agy_r1.start()
                t_agy_r1.join()
        else:
            t_agy_r1.start()
            t_codex_r1.join()
            t_agy_r1.join()

        if self._is_turn_cancelled(first_msg_id):
            return

        codex_r1_ok = r1_state["codex_ok"]
        agy_r1_ok = r1_state["agy_ok"]
        codex_r1_text = r1_state["codex_text"]
        agy_r1_text = r1_state["agy_text"]

        # ── TUR 2: Squad Üzerinden Karşılıklı Mesaj Okuma ve Birbirlerine Yanıt Verme (1 Değerlendirme Turu) ──
        if codex_r1_ok and agy_r1_ok and rounds >= 2:
            self._run_mutual_evaluation_round(
                cid=cid,
                round_num=2,
                user_prompt=prompt,
                codex_prev_text=codex_r1_text,
                agy_prev_text=agy_r1_text,
                squad_task_id=squad_task_id,
                squad_connected=squad_connected,
                project_id=project_id,
                precreated_codex_msg_id=None,
                owner_msg_id=first_msg_id,
            )

        if self._is_turn_cancelled(first_msg_id):
            return

        with self._lock:
            successful = (codex_r1_ok and agy_r1_ok) if write else (codex_r1_ok or agy_r1_ok)
            self._finish_turn(first_msg_id, "completed" if successful else "failed")

    def _run_mutual_evaluation_round(
        self,
        *,
        cid: str,
        round_num: int,
        user_prompt: str,
        codex_prev_text: str,
        agy_prev_text: str,
        squad_task_id: str | None,
        squad_connected: bool,
        project_id: str | None,
        owner_msg_id: str,
        precreated_codex_msg_id: str | None = None,
    ):
        """Run one controlled mutual evaluation round where both agents read Squad messages and respond in parallel."""
        if self._is_turn_cancelled(owner_msg_id):
            return
        received_for_codex = []
        received_for_agy = []
        if squad_connected:
            try:
                received_for_codex = self.agent_service.squad_receive_messages(
                    MultiAgentService.CODEX_ID, project_id=project_id
                )
            except Exception as exc:
                log.warning("Squad receive for codex failed: %s", exc)
            try:
                received_for_agy = self.agent_service.squad_receive_messages(
                    MultiAgentService.ANTIGRAVITY_ID, project_id=project_id
                )
            except Exception as exc:
                log.warning("Squad receive for antigravity failed: %s", exc)

        squad_agy_payload = agy_prev_text
        for item in reversed(received_for_codex):
            sender_from = str(item.get("from") or item.get("sender") or "")
            content_val = str(item.get("content") or item.get("body") or item.get("message") or "").strip()
            if "antigravity" in sender_from and content_val:
                squad_agy_payload = content_val
                break

        squad_codex_payload = codex_prev_text
        for item in reversed(received_for_agy):
            sender_from = str(item.get("from") or item.get("sender") or "")
            content_val = str(item.get("content") or item.get("body") or item.get("message") or "").strip()
            if "codex" in sender_from and content_val:
                squad_codex_payload = content_val
                break

        if precreated_codex_msg_id:
            conv_now = self.store.get(cid)
            codex_r2_msg = next((m for m in conv_now.get("messages", []) if m["id"] == precreated_codex_msg_id), None)
            codex_r2_id = precreated_codex_msg_id
            codex_r2_meta = dict((codex_r2_msg or {}).get("metadata") or {})
        else:
            codex_r2_msg = self._create_group_bubble(
                cid, sender="codex", recipient="antigravity",
                squad_task_id=squad_task_id, round_num=round_num, owner_msg_id=owner_msg_id,
            )
            codex_r2_id = codex_r2_msg["id"]
            codex_r2_meta = dict(codex_r2_msg.get("metadata") or {})

        codex_r2_meta.update({
            "squad_connected": squad_connected,
            "squad_received_count": len(received_for_codex),
        })

        agy_r2_msg = self._create_group_bubble(
            cid, sender="antigravity", recipient="codex",
            squad_task_id=squad_task_id, round_num=round_num, owner_msg_id=owner_msg_id,
        )
        agy_r2_id = agy_r2_msg["id"]
        agy_r2_meta = dict(agy_r2_msg.get("metadata") or {})
        agy_r2_meta.update({
            "squad_connected": squad_connected,
            "squad_received_count": len(received_for_agy),
        })

        codex_r2_prompt = (
            f"Quartz grup sohbetinin {round_num}. turundasın (Ajanlar arası karşılıklı değerlendirme turu).\n"
            f"Kullanıcının konusu/mesajı: {user_prompt}\n\n"
            f"Senin (Codex) önceki yanıtın:\n{codex_prev_text}\n\n"
            f"Antigravity'nin Squad üzerinden sana iletilen yanıtı:\n{squad_agy_payload}\n\n"
            "Görev: Antigravity'nin yanıtını doğrudan değerlendir. Katıldığın veya itiraz ettiğin noktaları belirt, "
            "varsa eksik/farklı gördüğün bir detayı ekle veya Antigravity'ye kısa bir soru/yorum yönelt. "
            "Doğrudan Antigravity'ye ve kullanıcıya hitap eden doğal, özlü bir grup sohbeti mesajı yaz. "
            "Kabuk komutu çalıştırma ve dahili görev kimliklerinden bahsetme."
        )

        agy_r2_prompt = (
            f"Quartz grup sohbetinin {round_num}. turundasın (Ajanlar arası karşılıklı değerlendirme turu).\n"
            f"Kullanıcının konusu/mesajı: {user_prompt}\n\n"
            f"Senin (Antigravity) önceki yanıtın:\n{agy_prev_text}\n\n"
            f"Codex'in Squad üzerinden sana iletilen yanıtı:\n{squad_codex_payload}\n\n"
            "Görev: Codex'in değerlendirmesine, sorusuna veya yaklaşımına doğrudan yanıt ver; "
            "katıldığın veya farklı düşündüğün noktaları belirt ve gerekirse ortak sentezi vurgula. "
            "Doğal ve özlü bir grup sohbeti mesajı yaz. Hiçbir araç (tool/command) çağırma ve dahili görev kimliklerinden bahsetme."
        )

        self._set_turn_progress(
            f"Tur {round_num} · Codex ve Antigravity birbirlerinin Squad mesajlarını değerlendiriyor...",
            current_msg_id=codex_r2_id,
        )

        def run_codex_eval():
            try:
                codex_r2_text = self._execute_codex_bubble(
                    cid, codex_r2_id, codex_r2_prompt, project_id, False, False,
                    use_session=False, squad_task_id=squad_task_id, base_meta=codex_r2_meta,
                )
                if squad_connected and codex_r2_text.strip():
                    self.agent_service.squad_send_message(
                        MultiAgentService.CODEX_ID, MultiAgentService.ANTIGRAVITY_ID,
                        codex_r2_text, task_id=squad_task_id, project_id=project_id,
                    )
            except Exception as exc:
                if self._is_turn_cancelled(owner_msg_id):
                    return
                err_msg = self._format_error("codex", exc)
                codex_r2_meta.update({"status": "failed", "error": str(exc)})
                self.store.update_message_content(cid, codex_r2_id, err_msg, metadata=codex_r2_meta)

        def run_agy_eval():
            try:
                agy_r2_text = self._execute_antigravity_bubble(
                    cid, agy_r2_id, agy_r2_prompt, project_id, False, False,
                    use_session=False, squad_task_id=squad_task_id, base_meta=agy_r2_meta,
                )
                if squad_connected and agy_r2_text.strip():
                    self.agent_service.squad_send_message(
                        MultiAgentService.ANTIGRAVITY_ID, MultiAgentService.CODEX_ID,
                        agy_r2_text, task_id=squad_task_id, project_id=project_id,
                    )
            except Exception as exc:
                if self._is_turn_cancelled(owner_msg_id):
                    return
                err_msg = self._format_error("antigravity", exc)
                agy_r2_meta.update({"status": "failed", "error": str(exc)})
                self.store.update_message_content(cid, agy_r2_id, err_msg, metadata=agy_r2_meta)

        t_c2 = threading.Thread(target=run_codex_eval, name=f"collab-c{round_num}-{cid[:6]}", daemon=True)
        t_a2 = threading.Thread(target=run_agy_eval, name=f"collab-a{round_num}-{cid[:6]}", daemon=True)
        t_c2.start()
        t_a2.start()
        t_c2.join()
        t_a2.join()

    def _run_continue_discussion_turn(self, cid: str, first_msg_id: str, round_num: int,
                                      squad_task_id: str | None, project_id: str | None):
        try:
            conv = self.store.get(cid)
            messages = conv.get("messages", [])
            user_msgs = [m for m in messages if m.get("role") == "user" and (m.get("content") or "").strip()]
            last_user_prompt = user_msgs[-1]["content"] if user_msgs else "Grup tartışması"

            codex_msgs = [
                m for m in messages
                if m.get("sender") == "codex" and m.get("id") != first_msg_id and (m.get("content") or "").strip()
            ]
            agy_msgs = [
                m for m in messages
                if m.get("sender") == "antigravity" and (m.get("content") or "").strip()
            ]
            codex_prev = codex_msgs[-1]["content"] if codex_msgs else ""
            agy_prev = agy_msgs[-1]["content"] if agy_msgs else ""

            conn_info = self.agent_service.check_squad_connection(project_id)
            squad_connected = bool(conn_info.get("connected")) if isinstance(conn_info, dict) else False

            self._run_mutual_evaluation_round(
                cid=cid,
                round_num=round_num,
                user_prompt=last_user_prompt,
                codex_prev_text=codex_prev,
                agy_prev_text=agy_prev,
                squad_task_id=squad_task_id,
                squad_connected=squad_connected,
                project_id=project_id,
                precreated_codex_msg_id=first_msg_id,
                owner_msg_id=first_msg_id,
            )
            if self._is_turn_cancelled(first_msg_id):
                return
            with self._lock:
                self._finish_turn(first_msg_id, "completed")
        except Exception as exc:
            if self._is_turn_cancelled(first_msg_id):
                return
            err_text = self._format_error("collaboration", exc)
            with self._lock:
                if self._finish_turn(first_msg_id, "failed"):
                    self.store.update_message_content(
                        cid, first_msg_id, err_text, metadata={"status": "failed", "error": str(exc)}
                    )

    @staticmethod
    def _format_error(agent: str, exc: Exception) -> str:
        msg = str(exc)
        lowered = msg.lower()
        if "rate limit" in lowered or "429" in lowered or "quota" in lowered or "usage limit" in lowered:
            return f"Başarısız. {agent.upper()} Kota Hatası: Kullanım sınırına takıldı. Modeli veya ücretli hizmeti değiştirmedim.\n\n{DETAIL_MARKER}\n{msg}"
        if "invalid model" in lowered or "model not found" in lowered or "unknown model" in lowered or "unsupported" in lowered:
            return f"Başarısız. Seçilen {agent.upper()} modeli şu anda kullanılamıyor. Başka modele geçmedim.\n\n{DETAIL_MARKER}\n{msg}"
        if "not ready" in lowered or "not found" in lowered or "unavailable" in lowered:
            return f"Başarısız. {agent.upper()} bağlantısı hazır değil. Önce bağlantıyı kontrol etmek gerekiyor.\n\n{DETAIL_MARKER}\n{msg}"
        return f"Başarısız. {agent.upper()} işlemi tamamlayamadı.\n\n{DETAIL_MARKER}\n{msg}"
