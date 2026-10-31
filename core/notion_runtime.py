"""Optional cloud Custom Agent runtime, scoped to explicitly selected workspace.

No local tools are granted. Remote tools/model remain the agent's Notion config.
Only sessions created by this adapter may be continued or canceled.
"""
from __future__ import annotations

from copy import deepcopy
import threading
import time
import uuid

from core.atomic_json import atomic_write_json, load_json
from core.notion_cli import NotionCli, NotionError, identifier, profile_root, resolve_ntn


class NotionRuntime:
    TERMINAL = {"completed", "failed", "cancelled", "blocked"}
    REMOTE_TERMINAL = {"completed", "failed", "canceled", "terminated"}

    def __init__(self, *, home=None, transport_factory=None, timeout=180, poll_interval=1):
        self.home = home or profile_root()
        from pathlib import Path
        self.home = Path(self.home)
        self.transport_factory = transport_factory or NotionCli
        self.timeout, self.poll_interval = timeout, poll_interval
        self._lock = threading.RLock()
        self._runs, self._threads, self._stops = {}, {}, {}
        self._busy_sessions = set()

    def configuration(self):
        config = load_json(self.home / "connection.json", {})
        return {key: config.get(key) for key in ("workspace_id", "agent_id", "agent_name")}

    def configure(self, workspace_id, agent_id):
        workspace_id, agent_id = identifier(workspace_id), identifier(agent_id)
        with self._lock:
            if any(r["status"] not in self.TERMINAL for r in self._runs.values()):
                raise RuntimeError("Notion görevi sürerken bağlantı değiştirilemez.")
            agents = self.transport_factory(workspace_id).agents()
            agent = next((a for a in agents if identifier(a.get("id")) == agent_id), None)
            if agent is None:
                raise ValueError("Seçilen ajan bu çalışma alanındaki erişilebilir ajanlar arasında yok.")
            config = {"workspace_id": workspace_id, "agent_id": agent_id,
                      "agent_name": str(agent.get("name") or "Notion ajanı")[:200]}
            atomic_write_json(self.home / "connection.json", config)
            return config

    def probe(self):
        # Local readiness only: no network on the UI polling path.
        config = self.configuration()
        try:
            resolve_ntn()
            installed = True
        except FileNotFoundError:
            installed = False
        configured = bool(config["workspace_id"] and config["agent_id"])
        return {"provider": "notion", "installed": installed, "configured": configured,
                "ready": installed and configured, "authentication": "not_checked",
                "agent_name": config["agent_name"],
                "error": "" if installed and configured else
                "Notion bağlantısı hazır değil. scripts/notion_agent.py ile kurulum, giriş ve ajan seçimi yapın."}

    def _owned(self, session_id, config):
        session_id = identifier(session_id)
        record = load_json(self.home / "sessions" / (session_id + ".json"), {})
        return isinstance(record, dict) and all(record.get(k) == config[k] for k in ("workspace_id", "agent_id"))

    def _remember(self, session_id, config):
        with self._lock:
            session_id = identifier(session_id)
            folder = self.home / "sessions"
            path = folder / (session_id + ".json")
            if not path.exists() and sum(1 for _ in folder.glob("*.json")) >= 1000:
                raise RuntimeError("Notion oturum kaydı sınırına ulaşıldı; eski kayıtları inceleyin.")
            # One immutable binding per session: another process adding its own
            # session cannot overwrite a shared read/modify/write inventory.
            atomic_write_json(path, {k: config[k] for k in ("workspace_id", "agent_id")})

    @staticmethod
    def _events(client, session_id):
        events, cursor, seen = [], None, set()
        for _ in range(20):
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = client.request(f"v1/sessions/{session_id}/events/query", body)
            events.extend(data.get("results", []))
            if not data.get("has_more"):
                return events
            cursor = data.get("next_cursor")
            if not cursor or cursor in seen:
                break
            seen.add(cursor)
        raise NotionError("Notion oturum olayları tamamen okunamadı.")

    def start(self, prompt, *, session_id=None):
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 64000:
            raise ValueError("Notion mesajı boş olamaz ve 64000 karakteri aşamaz.")
        config = self.configuration()
        if not config["workspace_id"] or not config["agent_id"]:
            raise RuntimeError(self.probe()["error"])
        config = {**config, "workspace_id": identifier(config["workspace_id"]),
                  "agent_id": identifier(config["agent_id"])}
        if session_id:
            session_id = identifier(session_id)
        with self._lock:
            if session_id and not self._owned(session_id, config):
                raise PermissionError("Bu Notion oturumu seçili Quartz bağlantısına ait değil.")
            if session_id in self._busy_sessions or any(r["status"] not in self.TERMINAL for r in self._runs.values()):
                raise RuntimeError("Devam eden Notion görevi bitmeden yeni görev başlatılamaz.")
            rid = "notion-" + uuid.uuid4().hex
            self._runs[rid] = {"id": rid, "provider": "notion", "status": "running", "result": "",
                               "session_id": session_id, "started_at": time.time(), "errors": [],
                               "agent_id": config["agent_id"], "workspace_id": config["workspace_id"],
                               "local_tools": False, "progress_log": []}
            self._stops[rid] = threading.Event()
            self._busy_sessions.add(session_id)
            worker = threading.Thread(target=self._execute, args=(rid, config, prompt, session_id),
                                      name=rid[:24], daemon=True)
            self._threads[rid] = worker
            worker.start()
            return deepcopy(self._runs[rid])

    def _update(self, rid, **values):
        with self._lock:
            self._runs[rid].update(values)

    @staticmethod
    def _validate_session(session, session_id, agent_id):
        if (session.get("object") != "session" or identifier(session.get("id")) != session_id or
                identifier(session.get("agent_id")) != agent_id):
            raise NotionError("Notion oturum kimliği eşleşmiyor; işlem durduruldu.", uncertain=True)

    def _request_stop(self, client, session_id, config):
        remote = client.request(f"v1/sessions/{session_id}/cancel", {})
        self._validate_session(remote, session_id, config["agent_id"])
        if remote.get("status") not in self.REMOTE_TERMINAL:
            remote = client.request(f"v1/sessions/{session_id}")
            self._validate_session(remote, session_id, config["agent_id"])
        if remote.get("status") not in self.REMOTE_TERMINAL:
            raise NotionError("Yerel görev durdu; uzaktaki Notion işleminin durduğu doğrulanamadı.", uncertain=True)
        return remote["status"]

    def _execute(self, rid, config, prompt, session_id):
        stop = self._stops[rid]
        original_session = session_id
        submitted = False
        try:
            client = self.transport_factory(config["workspace_id"])
            baseline = 0
            if session_id:
                existing = client.request(f"v1/sessions/{session_id}")
                self._validate_session(existing, session_id, config["agent_id"])
                if identifier(existing.get("agent_id")) != config["agent_id"] or existing.get("status") not in self.REMOTE_TERMINAL:
                    raise NotionError("Notion oturumu başka ajana ait veya hâlâ çalışıyor.")
                baseline = max((e.get("sequence", 0) for e in self._events(client, session_id)), default=0)
            if stop.is_set():
                self._update(rid, status="cancelled")
                return
            body = {"message": prompt}
            body["session_id" if session_id else "agent_id"] = session_id or config["agent_id"]
            session = client.request("v1/sessions", body)
            submitted = True
            returned_id = identifier(session.get("id"))
            if (session_id and returned_id != session_id) or identifier(session.get("agent_id")) != config["agent_id"]:
                raise NotionError("Notion yanıtındaki oturum/ajan kimliği eşleşmiyor.", uncertain=True)
            session_id = returned_id
            # Retain the remote handle even if local ledger persistence fails.
            self._update(rid, session_id=session_id)
            self._remember(session_id, config)
            deadline = time.monotonic() + self.timeout
            while True:
                if stop.is_set() or time.monotonic() >= deadline:
                    status = self._request_stop(client, session_id, config)
                    self._update(rid, status="cancelled" if stop.is_set() else "failed",
                                 remote_status=status, error="" if stop.is_set() else "Notion görevi süre sınırına ulaştı.")
                    return
                state = session.get("status")
                if state not in self.REMOTE_TERMINAL | {"queued", "in_progress", "requires_action"}:
                    raise NotionError("Notion oturum durumu tanınmıyor.", uncertain=True)
                events = self._events(client, session_id)
                messages = {}
                for event in events:
                    seq = event.get("sequence", 0)
                    if event.get("type") == "agent.message" and seq > baseline:
                        parts = event.get("content", [])
                        messages[(seq, event["id"])] = "".join(
                            p.get("text", "") for p in parts if p.get("type") == "text" and isinstance(p.get("text"), str))
                text = "\n\n".join(value for _, value in sorted(messages.items()) if value)
                self._update(rid, result=text, remote_status=state)
                if state == "requires_action":
                    self._update(rid, status="blocked", error="Notion ajanı onay bekliyor. Notion'da bu oturumu kontrol edin.",
                                 required_actions=True)
                    return
                if state in self.REMOTE_TERMINAL:
                    if state == "completed" and text:
                        self._update(rid, status="completed")
                    elif state in {"canceled", "terminated"}:
                        self._update(rid, status="cancelled")
                    else:
                        raise NotionError("Notion görevi başarısız oldu veya doğrulanabilir metin yanıtı gelmedi.")
                    return
                stop.wait(self.poll_interval)
                session = client.request(f"v1/sessions/{session_id}")
                self._validate_session(session, session_id, config["agent_id"])
        except Exception as exc:
            safe = str(exc) if isinstance(exc, NotionError) else "Notion işlemi tamamlanamadı; bağlantıyı ve yerel oturum kaydını kontrol edin."
            self._update(rid, status="failed", error=safe, errors=[safe],
                         remote_uncertain=bool(getattr(exc, "uncertain", False) or
                                               (submitted and self.get(rid).get("remote_status") not in self.REMOTE_TERMINAL)))
        finally:
            self._update(rid, finished_at=time.time())
            with self._lock:
                self._busy_sessions.discard(original_session)

    def get(self, run_id):
        with self._lock:
            return deepcopy(self._runs[run_id])

    def list(self):
        with self._lock:
            return deepcopy(list(self._runs.values()))

    def cancel(self, run_id):
        with self._lock:
            run = self._runs[run_id]
            # A blocked turn can still own live work remotely. Cancel it through
            # the same authenticated endpoint, never approve its pending actions.
            if run["status"] == "blocked":
                run["status"] = "cancelling"
                worker = threading.Thread(target=self._cancel_blocked, args=(run_id,),
                                          name=run_id[:20] + "-stop", daemon=True)
                self._threads[run_id] = worker
                worker.start()
                return deepcopy(run)
            if run["status"] not in self.TERMINAL:
                run["status"] = "cancelling"
                self._stops[run_id].set()
            return deepcopy(run)

    def _cancel_blocked(self, run_id):
        run = self.get(run_id)
        config = {key: run[key] for key in ("workspace_id", "agent_id")}
        try:
            if not self._owned(run["session_id"], config):
                raise NotionError("Notion oturum sahipliği doğrulanamadı.", uncertain=True)
            client = self.transport_factory(config["workspace_id"])
            state = self._request_stop(client, run["session_id"], config)
            self._update(run_id, status="cancelled", remote_status=state, required_actions=False)
        except Exception:
            self._update(run_id, status="failed", remote_uncertain=True,
                         error="Notion işleminin durduğu doğrulanamadı. Notion'da oturumu kontrol edin.")
        finally:
            self._update(run_id, finished_at=time.time())

    def shutdown(self):
        for run in self.list():
            if run["status"] not in self.TERMINAL or run["status"] == "blocked":
                self.cancel(run["id"])
        deadline = time.monotonic() + 3
        for thread in tuple(self._threads.values()):
            thread.join(max(0, deadline - time.monotonic()))
        if any(t.is_alive() for t in self._threads.values()):
            raise RuntimeError("Uzaktaki Notion görevlerinin durması henüz doğrulanmadı.")
