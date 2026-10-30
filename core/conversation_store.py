"""Persistent thread-safe store for multi-turn agent conversations."""

from __future__ import annotations

import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json


class ConversationStore:
    DEFAULT_MODELS = {
        "antigravity": {
            "model": "gemini-3.8-flash-medium",
            "effort": "medium",
        },
        "codex": {
            "model": "gpt-6.1-sol",
            "effort": "low",
        },
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conversations: dict[str, dict] = {}
        self._active_id: str | None = None
        self._preferences = {"response_detail": "short", "permission_level": "full"}
        self._load()

    @classmethod
    def _normalize_models(cls, raw_models: dict | None = None) -> dict:
        raw_models = raw_models if isinstance(raw_models, dict) else {}
        out = {}
        for agent, defaults in cls.DEFAULT_MODELS.items():
            entry = raw_models.get(agent) if isinstance(raw_models.get(agent), dict) else {}
            out[agent] = {
                "model": str(entry.get("model") or defaults["model"]).strip(),
                "effort": str(entry.get("effort") or defaults["effort"]).strip().lower(),
            }
        return out

    def _load(self):
        with self._lock:
            data = load_json(self.path, {})
            if isinstance(data, dict):
                self._conversations = data.get("conversations", {})
                self._active_id = data.get("active_id")
                prefs = data.get("preferences")
                level = prefs.get("response_detail", "short") if isinstance(prefs, dict) else "short"
                if level in {"short", "normal", "technical"}:
                    self._preferences["response_detail"] = level
                self._preferences["permission_level"] = "full"
            for cdata in self._conversations.values():
                if isinstance(cdata, dict):
                    cdata["models"] = self._normalize_models(cdata.get("models"))
                    cdata.setdefault("sessions", {"antigravity": None, "codex": None})
                    cdata["permission_level"] = "full"
            if not self._conversations:
                self.create(title="Yeni Sohbet")

    def _save(self):
        with self._lock:
            payload = {
                "active_id": self._active_id,
                "conversations": self._conversations,
                "preferences": self._preferences,
            }
            atomic_write_json(self.path, payload)

    def preferences(self):
        with self._lock:
            return dict(self._preferences)

    def recover_interrupted(self):
        """Mark abandoned messages, never replay work or restore permissions.

        Called only by the owning chat service at startup. Preserve the original
        JSON payload locally before atomically updating the conversation file.
        Failure leaves both memory and the old conversation file unchanged.
        """
        with self._lock:
            candidate = deepcopy(self._conversations)
            recovered = []
            now = time.time()
            active_states = {'starting', 'running', 'queued', 'pending', 'cancelling', 'awaiting_approval'}
            for cid, conv in candidate.items():
                # Natural desktop events are completed chat messages even while
                # their enclosing task is running. Only the LAST lifecycle event
                # for a task can establish whether it was abandoned.
                last_task_event = {}
                for msg in conv.get('messages', []):
                    meta = msg.get('metadata') or {}
                    if meta.get('natural_task') and 'task_status' in meta:
                        last_task_event[meta['natural_task']] = msg.get('id')
                for msg in conv.get('messages', []):
                    meta = msg.get('metadata') or {}
                    abandoned_task = (meta.get('natural_task') and
                        last_task_event.get(meta['natural_task']) == msg.get('id') and
                        meta.get('task_status') in active_states)
                    if msg.get('role') != 'assistant' or (msg.get('status') not in active_states and not abandoned_task):
                        continue
                    meta = msg.setdefault('metadata', {})
                    meta.update(status='interrupted', recovered_at=now,
                        recovery_reason='Application restarted before a terminal result',
                        automatic_replay=False, permissions_restored=False)
                    if abandoned_task: meta['task_status'] = 'interrupted'
                    msg['status'] = 'interrupted'
                    if not msg.get('content', '').strip():
                        msg['content'] = 'Önceki oturum kesildi. Görev otomatik sürdürülmedi; devam etmeden önce durumu kontrol edin.'
                    provider = msg.get('sender')
                    if provider in {'codex', 'antigravity'}:
                        conv.setdefault('sessions', {})[provider] = None
                    recovered.append({'conversation_id':cid, 'message_id':msg.get('id')})
            if not recovered:
                return {'status':'unchanged', 'messages':[], 'automatic_replay':False}
            backup = self.path.parent / '.quartz' / 'recovery' / (uuid.uuid4().hex + '.json')
            # Copy the original JSON rather than normalized/in-memory content.
            original = load_json(self.path, None)
            if not isinstance(original, dict):
                raise OSError('Cannot preserve conversation store before recovery')
            atomic_write_json(backup, original)
            payload = {'active_id':self._active_id, 'conversations':candidate,
                       'preferences':self._preferences}
            atomic_write_json(self.path, payload)
            self._conversations = candidate
            return {'status':'recovered', 'messages':recovered, 'backup':str(backup),
                    'automatic_replay':False, 'permissions_restored':False}

    def set_response_detail(self, level):
        if level not in {"short", "normal", "technical"}:
            raise ValueError("Geçersiz yanıt ayrıntısı")
        with self._lock:
            self._preferences["response_detail"] = level
            self._save()
            return dict(self._preferences)

    def list(self) -> list[dict]:
        with self._lock:
            result = []
            for cid, cdata in self._conversations.items():
                result.append({
                    "id": cid,
                    "title": cdata.get("title", "Sohbet"),
                    "created_at": cdata.get("created_at", 0),
                    "updated_at": cdata.get("updated_at", 0),
                    "agent": cdata.get("agent", "antigravity"),
                    "project_id": cdata.get("project_id"),
                    "permission_level": "full",
                    "models": self._normalize_models(cdata.get("models")),
                    "message_count": len(cdata.get("messages", [])),
                    "is_active": cid == self._active_id,
                })
            result.sort(key=lambda x: x["updated_at"], reverse=True)
            return result

    def create(self, title: str = "Yeni Sohbet", agent: str = "antigravity",
               project_id: str | None = None, models: dict | None = None) -> dict:
        with self._lock:
            cid = uuid.uuid4().hex
            now = time.time()
            record = {
                "id": cid,
                "title": title,
                "agent": agent,
                "project_id": project_id,
                "permission_level": "full",
                "created_at": now,
                "updated_at": now,
                "models": self._normalize_models(models),
                "sessions": {
                    "antigravity": None,  # conversation_id
                    "codex": None,        # thread_id
                },
                "messages": [],
            }
            self._conversations[cid] = record
            self._active_id = cid
            self._save()
            return dict(record)

    def get_active(self) -> dict:
        with self._lock:
            if not self._active_id or self._active_id not in self._conversations:
                if self._conversations:
                    self._active_id = next(iter(self._conversations))
                else:
                    return self.create()
            rec = self._conversations[self._active_id]
            rec["models"] = self._normalize_models(rec.get("models"))
            rec["permission_level"] = "full"
            return dict(rec)

    def get(self, conversation_id: str) -> dict:
        with self._lock:
            if conversation_id not in self._conversations:
                raise KeyError(f"Conversation not found: {conversation_id}")
            rec = self._conversations[conversation_id]
            rec["models"] = self._normalize_models(rec.get("models"))
            rec["permission_level"] = "full"
            return dict(rec)

    def select(self, conversation_id: str) -> dict:
        with self._lock:
            if conversation_id not in self._conversations:
                raise KeyError(f"Conversation not found: {conversation_id}")
            self._active_id = conversation_id
            rec = self._conversations[conversation_id]
            rec["models"] = self._normalize_models(rec.get("models"))
            rec["permission_level"] = "full"
            self._save()
            return dict(rec)

    def delete(self, conversation_id: str) -> dict:
        return self.delete_many([conversation_id])["active_conversation"]

    def delete_many(self, conversation_ids: list[str]) -> dict:
        """Remove only exact IDs, after a durable local recovery copy.

        No CLI session, project directory or external agent history is deleted.
        Commit to disk before changing memory, so a failed save is non-destructive.
        """
        with self._lock:
            ids = list(dict.fromkeys(conversation_ids))
            if not ids or any(not isinstance(cid, str) or cid not in self._conversations for cid in ids):
                raise ValueError("Sohbet listesi değişti; yenileyip tekrar deneyin.")
            removed = {cid: deepcopy(self._conversations[cid]) for cid in ids}
            active = self._active_id
            previous = self._conversations.get(active, {})
            remaining = {cid: rec for cid, rec in self._conversations.items() if cid not in removed}
            if active not in remaining:
                project = previous.get("project_id")
                candidates = [c for c in remaining.values() if
                              (c.get("project_id") or "squad-pilot") == (project or "squad-pilot")]
                if candidates:
                    active = max(candidates, key=lambda c: c.get("updated_at", 0))["id"]
                else:
                    active = uuid.uuid4().hex
                    now = time.time()
                    remaining[active] = {"id": active, "title": "Yeni Sohbet",
                        "agent": previous.get("agent", "antigravity"), "project_id": project,
                        "models": self._normalize_models(previous.get("models")),
                        "sessions": {"antigravity": None, "codex": None},
                        "created_at": now, "updated_at": now, "messages": []}
            backup = self.path.parent / "quartz_deleted_chats" / (uuid.uuid4().hex + ".json")
            atomic_write_json(backup, {"deleted_at": time.time(), "active_id": self._active_id,
                                      "conversations": removed})
            atomic_write_json(self.path, {"active_id": active, "conversations": remaining,
                                          "preferences": self._preferences})
            self._conversations, self._active_id = remaining, active
            return {"deleted_count": len(ids), "active_conversation": deepcopy(remaining[active]),
                    "backup": str(backup)}

    def update_agent(self, conversation_id: str, agent: str) -> None:
        with self._lock:
            if conversation_id in self._conversations:
                self._conversations[conversation_id]["agent"] = agent
                self._conversations[conversation_id]["updated_at"] = time.time()
                self._save()

    def update_agent_model(self, conversation_id: str, agent: str,
                           model: str | None = None, effort: str | None = None) -> dict:
        agent_key = str(agent or "").strip().lower()
        if agent_key not in self.DEFAULT_MODELS:
            raise ValueError(f"Unknown agent for model selection: {agent}")
        with self._lock:
            if conversation_id not in self._conversations:
                raise KeyError(f"Conversation not found: {conversation_id}")
            conv = self._conversations[conversation_id]
            models = self._normalize_models(conv.get("models"))
            if model is not None and str(model).strip():
                models[agent_key]["model"] = str(model).strip()
            if effort is not None and str(effort).strip():
                models[agent_key]["effort"] = str(effort).strip().lower()
            conv["models"] = models
            conv["updated_at"] = time.time()
            self._save()
            return dict(models[agent_key])

    def get_agent_model(self, conversation_id: str, agent: str) -> dict:
        agent_key = str(agent or "").strip().lower()
        with self._lock:
            conv = self.get(conversation_id)
            models = self._normalize_models(conv.get("models"))
            return dict(models.get(agent_key, self.DEFAULT_MODELS.get(agent_key, {})))

    def update_project(self, conversation_id: str, project_id: str | None) -> None:
        with self._lock:
            if conversation_id in self._conversations:
                if self._conversations[conversation_id].get("project_id") != project_id:
                    self._conversations[conversation_id]["sessions"] = {"antigravity": None, "codex": None}
                self._conversations[conversation_id]["project_id"] = project_id
                self._conversations[conversation_id]["updated_at"] = time.time()
                self._save()

    def set_agent_session(self, conversation_id: str, agent: str, session_id: str) -> None:
        with self._lock:
            if conversation_id in self._conversations:
                self._conversations[conversation_id].setdefault("sessions", {})[agent] = session_id
                self._conversations[conversation_id]["updated_at"] = time.time()
                self._save()

    def append_message(self, conversation_id: str, role: str, content: str,
                       sender: str = "", metadata: dict | None = None) -> dict:
        with self._lock:
            if conversation_id not in self._conversations:
                raise KeyError(f"Conversation not found: {conversation_id}")
            msg_id = uuid.uuid4().hex
            now = time.time()
            meta = dict(metadata or {})
            resolved_sender = sender or meta.get("sender") or role
            entry = {
                "id": msg_id,
                "conversation_id": conversation_id,
                "role": role,  # "user", "assistant", "system"
                "sender": resolved_sender,  # "user", "codex", "antigravity", "quartz"
                "recipient": meta.get("recipient", "user" if role == "assistant" else "all"),
                "sequence": meta.get("sequence"),
                "squad_task_id": meta.get("squad_task_id"),
                "status": meta.get("status", "completed" if role == "user" else "running"),
                "content": content,
                "timestamp": now,
                "metadata": meta,
            }
            conv = self._conversations[conversation_id]
            conv["messages"].append(entry)
            conv["updated_at"] = now
            if conv.get("title") == "Yeni Sohbet" and role == "user":
                clean_title = content.strip().split("\n")[0][:40]
                if clean_title:
                    conv["title"] = clean_title
            self._save()
            return entry

    def update_message_content(self, conversation_id: str, message_id: str, content: str,
                               metadata: dict | None = None) -> None:
        with self._lock:
            if conversation_id not in self._conversations:
                return
            found = False
            for msg in self._conversations[conversation_id].get("messages", []):
                if msg["id"] == message_id:
                    msg["content"] = content
                    if metadata:
                        msg["metadata"].update(metadata)
                        for key in ("sender", "recipient", "sequence", "squad_task_id", "status"):
                            if key in metadata and metadata[key] is not None:
                                msg[key] = metadata[key]
                    found = True
                    break
            if found:
                self._conversations[conversation_id]["updated_at"] = time.time()
                self._save()
