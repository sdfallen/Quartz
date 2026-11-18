"""Long jobs inside the chat service: each milestone is one ordinary Workspace turn.

The job never bypasses the chat's single writer, Stop or evidence rules: it waits until
no turn is running, sends the milestone as a confirmed project-write task in the job's
own conversation, and reads the turn's outcome from the conversation afterwards.
"""
from __future__ import annotations

import threading
import time

from core.long_job import (JobError, JobLedger, LongJob, PERSONA, milestone_prompt, resumable)

LIMIT_WORDS = ("kota hatası", "rate limit", "usage limit", "quota", "429", "kullanım sınırı")
# Not the work failing but the agent not being reachable (live 15 Nov).
UNREACHABLE_WORDS = ("reconnecting", "routing discovery failed", "timed out after", "bağlantısı hazır değil",
                     "connection refused", "connection reset", "econnreset", "network error")
POLL_SECONDS = 3.0
# The chat refuses a new turn while the previous one's processes are being confirmed stopped.
SETTLING_WORDS = ("süreçlerinin durduğu henüz doğrulanmadı", "çalışanı kapanıyor", "host test sürecinin kapanışı")
SETTLE_SECONDS = 10.0
SETTLE_TRIES = 30


def _duration(hours: float) -> str:
    """'40 dakika', '2 saat', '1 saat 30 dakika' (live 15 Nov: '0.666667 saat')."""
    minutes = round(hours * 60)
    whole, rest = divmod(minutes, 60)
    if not whole:
        return f"{rest} dakika"
    return f"{whole} saat" + (f" {rest} dakika" if rest else "")


class LongJobChatMixin:
    def _jobs(self) -> dict:
        return self.__dict__.setdefault("_long_jobs", {})

    # -- public API (IPC) -----------------------------------------------------------
    def job_start(self, spec: dict) -> dict:
        """Start a job the user approved in this conversation's project."""
        from core.space_policy import is_chat
        spec = dict(spec or {})
        conv = self.store.get(spec.get("conversation_id")) if spec.get("conversation_id") else self.store.get_active()
        if is_chat(conv):
            raise JobError("Uzun iş yalnız Workspace sohbetinde başlatılır.")
        project = self.agent_service.projects.get(conv.get("project_id")) if conv.get("project_id") else None
        if not isinstance(project, dict) or not project.get("path") or project.get("protected") \
                or project.get("workflow") == "warband":
            raise JobError("Bu sohbete bağlı, yazılabilir bir proje yok.")
        if any(job.ledger.data["status"] in {"running", "waiting_limit", "paused"} for job in self._jobs().values()):
            raise JobError("Zaten sürmekte olan bir uzun iş var; önce onu bitir ya da durdur.")
        spec["conversation_id"] = conv["id"]
        spec["project_path"] = project["path"]  # the conversation's project, never a free path
        # The models the user chose are recorded once; SpeS never switches them by itself.
        spec["models"] = {agent: self.store.get_agent_model(conv["id"], agent)
                          for agent in ("claude", "codex", "antigravity")}
        ledger = JobLedger.create(spec)
        job = self._make_job(ledger)
        self._jobs()[ledger.data["id"]] = job
        self._job_note(ledger, "Uzun iş başladı: " + ledger.data["goal"][:200] + " · "
                       + f"{len(ledger.data['milestones'])} kilometre taşı, en çok {_duration(ledger.data['hours'])}"
                       + (" · çökünce kendiliğinden devam eder" if ledger.data["auto_resume"] else "")
                       + (" · Tam Yetki: yazıcı komut çalıştırabilir" if ledger.data.get("permission_level") == "full"
                          else " · Proje izni: yazıcı yalnız dosya yazar, komut çalıştıramaz") + ".")
        job.start()
        return ledger.public()

    def _long_job_command(self, conv, text, spec, confirmed_write, full_access=False) -> dict:
        """'/uzun-iş' typed in the desktop chat with project writing allowed (never the phone)."""
        if spec.get("list"):
            jobs = self.job_list()
            lines = [f"{j['goal'][:60]} — {j['status']}" for j in jobs[:5]]
            return self._answer_without_agents(conv["id"], text, "Uzun işler: " + ("; ".join(lines) or "yok") + ".")
        if spec.get("note") and confirmed_write:
            # The reviewer's note reaches every later milestone through the ledger (15 Nov).
            job = next((j for j in self._jobs().values() if j.ledger.data.get("conversation_id") == conv["id"]
                        and j.ledger.data["status"] in {"running", "waiting_limit", "paused"}), None)
            if job is None:
                return self._answer_without_agents(conv["id"], text, "Bu sohbette sürmekte olan bir uzun iş yok.")
            job.add_note(spec["note"])
            return self._answer_without_agents(conv["id"], text, (
                "Not iş defterine eklendi; ekip bunu sıradaki her kilometre taşında okuyacak."))
        if not confirmed_write:
            return self._answer_without_agents(conv["id"], text, (
                "Uzun iş projeye saatlerce yazar; bu yüzden yalnız masaüstünde, yazma izni (Proje) açıkken "
                "başlatılabilir. İzni açıp komutu yeniden gönder."))
        # The chat's own permission level travels with the job (user decision 15 Nov: with
        # Tam Yetki the writer may run Blender/Godot; with Proje it only edits files).
        spec = {**spec, "permission_level": "full" if full_access else "project"}
        try:
            from core.long_job import validate_spec
            validate_spec({**spec, "project_path": spec.get("project_path") or "."})  # fail before any message
        except JobError as exc:
            return self._answer_without_agents(conv["id"], text, f"Uzun iş başlatılamadı: {exc}")
        with self._lock:
            user = self.store.append_message(conv["id"], "user", text, sender="user", metadata={
                "sender": "user", "recipient": "quartz", "long_job_command": True,
                "sequence": self._next_sequence(self.store.get(conv["id"]))})
        try:
            job = self.job_start({**spec, "conversation_id": conv["id"]})
        except (JobError, ValueError) as exc:
            note = self.store.append_message(conv["id"], "assistant", f"Uzun iş başlatılamadı: {exc}", sender="quartz",
                                             metadata={"sender": "quartz", "recipient": "user", "status": "completed",
                                                       "sequence": self._next_sequence(self.store.get(conv["id"]))})
            return {"conversation_id": conv["id"], "user_message": user, "assistant_message": note, "agent": "quartz"}
        note = next((m for m in reversed(self.store.get(conv["id"]).get("messages", []))
                     if (m.get("metadata") or {}).get("long_job") == job["id"]), None)
        return {"conversation_id": conv["id"], "user_message": user, "assistant_message": note,
                "agent": "quartz", "job": job}

    def job_control(self, job_id: str, action: str) -> dict:
        job = self._jobs().get(str(job_id or ""))
        if job is None:
            # Live 15 Nov: a job paused before a restart is on disk only; "Devam" must find it.
            ledger = next((l for l in JobLedger.all() if l.data["id"] == str(job_id or "")), None)
            if ledger is None or ledger.data.get("stopped") or ledger.data["status"] in {"done", "expired", "failed"}:
                raise JobError("Bu iş bulunamadı ya da bitmiş.")
            job = self._make_job(ledger)
            if action == "resume":
                job.recover_after_crash()
            self._jobs()[ledger.data["id"]] = job
        if action == "pause":
            job.pause()
        elif action == "resume":
            job.resume()
            if job.thread is None or not job.thread.is_alive():
                job.thread = None
                job.start()
        elif action == "stop":
            job.stop()
            with self._lock:
                turn = self._active_turn
                owned = turn and turn.get("long_job") == job.ledger.data["id"] and turn.get("status") == "running"
            if owned:
                self.cancel_active()
        else:
            raise JobError("Geçersiz iş eylemi.")
        return job.ledger.public()

    def job_list(self) -> list:
        known = {job_id: job.ledger.public() for job_id, job in self._jobs().items()}
        for ledger in JobLedger.all():
            known.setdefault(ledger.data["id"], ledger.public())
        return sorted(known.values(), key=lambda j: j.get("created_at") or 0, reverse=True)[:20]

    def resume_jobs_at_startup(self, now=None) -> list:
        """User decision 15 Nov: jobs started with auto_resume continue after a restart."""
        resumed = []
        now = time.time() if now is None else now
        for ledger in JobLedger.all():
            decision = resumable(ledger, now)
            if not decision or ledger.data["id"] in self._jobs():
                continue
            job = self._make_job(ledger)
            self._jobs()[ledger.data["id"]] = job
            if decision == "resume" and job.recover_after_crash() == "resume":
                self._job_note(ledger, "SpeS yeniden başladı; uzun iş kaldığı kilometre taşından sürüyor.", urgent=True)
                job.start()
                resumed.append(ledger.data["id"])
            else:
                with ledger._lock:
                    ledger.data["status"] = "paused"
                    ledger.save()
                self._job_note(ledger, "SpeS yeniden başladı; uzun iş duraklatıldı. Devam etmek için onayın gerekiyor.",
                               urgent=True)
        return resumed

    # -- internals ------------------------------------------------------------------
    def _make_job(self, ledger):
        from core.agent_limits import snapshot
        return LongJob(ledger, run_milestone=self._job_run_milestone, limits=snapshot,
                       notify=lambda text, urgent=False, report=False: self._job_note(ledger, text, urgent=urgent,
                                                                                      report=report))

    def _job_note(self, ledger, text, urgent=False, report=False):
        cid = ledger.data.get("conversation_id")
        try:
            conv = self.store.get(cid)
            self.store.append_message(cid, "assistant", text, sender="quartz", metadata={
                "sender": "quartz", "recipient": "user", "status": "completed", "long_job": ledger.data["id"],
                **({"notify": "call"} if urgent else {}),
                # The phone rings like a call for a report (mobile WatchService, "bitince haber ver").
                **({"report": True} if report else {}),
                "sequence": self._next_sequence(conv)})
        except Exception:
            pass

    def _job_turn_busy(self):
        with self._lock:
            turn = self._active_turn
            return bool(turn and (turn.get("status") in {"running", "cancelling"} or turn.get("worker_pending")))

    def _job_run_milestone(self, ledger, milestone, writer, stop: threading.Event) -> dict:
        cid = ledger.data["conversation_id"]
        while self._job_turn_busy():  # the user's own turn goes first
            if stop.wait(POLL_SECONDS):
                return {"status": "cancelled"}
        agent = "collaboration" if writer == "claude" and self._team_ready() else writer
        prompt = milestone_prompt(ledger, milestone, writer)
        sent, text = None, "SpeS yeni turu başlatamadı."
        for _ in range(SETTLE_TRIES):
            try:
                sent = self.send_message(prompt, agent=agent, conversation_id=cid, write=True, confirm_write=True,
                                         full_access=ledger.data.get("permission_level") == "full")
                break
            except Exception as exc:
                text = str(exc)
                # Live 15 Nov: the previous turn's processes were still being confirmed stopped
                # and the attempt was counted as failed. SpeS is settling, not the work failing.
                if any(w in text for w in SETTLING_WORDS):
                    if stop.wait(SETTLE_SECONDS):
                        return {"status": "cancelled"}
                    continue
                break
        if sent is None:
            if any(w in text for w in SETTLING_WORDS):
                return {"status": "failed", "summary": text, "unavailable": writer}
            limited = writer if any(w in text.lower() for w in LIMIT_WORDS) else None
            if not limited and any(w in text.lower() for w in UNREACHABLE_WORDS):
                return {"status": "failed", "summary": text, "unavailable": writer}
            return {"status": "failed", "summary": text, **({"limit": limited} if limited else {})}
        user_id = sent["user_message"]["id"]
        turn_id = (sent["user_message"].get("metadata") or {}).get("task_id")
        with self._lock:
            if self._active_turn and self._active_turn.get("turn_id") == turn_id:
                self._active_turn["long_job"] = ledger.data["id"]
        while True:
            with self._lock:
                turn = self._active_turn
                running = bool(turn and turn.get("turn_id") == turn_id
                               and (turn.get("status") in {"running", "cancelling"} or turn.get("worker_pending")))
                step_status = (turn or {}).get("step_status") if turn and turn.get("turn_id") == turn_id else None
            if not running:
                break
            if stop.is_set():
                self.cancel_active()
            stop.wait(POLL_SECONDS)
        if stop.is_set():
            return {"status": "cancelled"}
        return self._job_turn_outcome(cid, user_id, writer, step_status)

    def _job_turn_outcome(self, cid, user_id, writer, step_status):
        messages = self.store.get(cid).get("messages", [])
        index = next((i for i, m in enumerate(messages) if m.get("id") == user_id), None)
        user = messages[index] if index is not None else {}
        after = messages[index + 1:] if index is not None else []
        status = (user.get("metadata") or {}).get("instruction_state") or step_status or "failed"
        if status not in {"completed", "failed", "partial"}:
            status = step_status if step_status in {"completed", "failed", "partial"} else "failed"
        replies = [m for m in after if m.get("role") == "assistant" and m.get("sender") != "quartz"]
        blob = " ".join(str(m.get("content") or "") + " " + str((m.get("metadata") or {}).get("error") or "")
                        for m in replies).lower()
        if status != "completed" and any(w in blob for w in LIMIT_WORDS):
            limited = next((m.get("sender") for m in replies
                            if any(w in (str(m.get("content") or "") + str((m.get("metadata") or {}).get("error") or "")).lower()
                                   for w in LIMIT_WORDS)), writer)
            limited = limited if limited in PERSONA else writer
            # A reviewer at its limit does not move the writer role; the job's check decides.
            if limited == writer:
                return {"status": status, "limit": writer}
        if status == "failed":
            own = " ".join(str(m.get("content") or "") + " " + str((m.get("metadata") or {}).get("error") or "")
                           for m in replies if m.get("sender") == writer).lower()
            if any(w in own for w in UNREACHABLE_WORDS):
                return {"status": status, "unavailable": writer}
        summary = str(replies[-1].get("content") or "")[-1500:] if replies else ""
        return {"status": status, "summary": summary}
