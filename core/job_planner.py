"""The planning turn of a one-request job (user request 25 Nov 2026).

The first agent of the turn reads the project and writes a milestone plan; it writes nothing.
SpeS turns the plan into a long job with the user's own duration, SpeS's own check and the
permission the user switched on. A plan that cannot be read becomes a single milestone with
the user's request as its acceptance, so the request is never lost to a parsing problem.
"""
from __future__ import annotations

import threading
import time

from core.job_intent import job_spec, parse_plan, plan_rule
from core.long_job import JobError


def plan_text(milestones) -> str:
    lines = [f"{i}. {m['title']} — {m['acceptance']}" for i, m in enumerate(milestones, 1)]
    return "İş planı:\n" + "\n".join(lines)


def create_project_folder(folder) -> bool:
    """The folder, a Git repository and one empty commit, so the job's branch has a base.

    True when the repository is ready; False when Git could not set it up (the folder stays
    and the job runs without commits, which the plan says)."""
    import os
    import subprocess
    from pathlib import Path
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Fides 26 Nov: GIT_CONFIG_COUNT/KEY/VALUE handed down by a parent process made "git init"
    # fail ("missing config value"). The new repository gets Git without them.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_CONFIG")}

    def git(*args):
        return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True,
                              timeout=60, check=False, creationflags=flags, env=env)
    if git("init", "-q").returncode != 0:
        return False
    # Identity for this repository only; the user's own Git settings are never touched.
    git("config", "user.name", "SpeS")
    git("config", "user.email", "spes@localhost")
    for _ in range(3):
        if git("commit", "-q", "--allow-empty", "-m", "SpeS: yeni proje").returncode == 0:
            return True
        time.sleep(0.5)
    raise RuntimeError("Yeni projenin ilk Git kaydı oluşturulamadı.")


class JobPlannerMixin:
    def _new_project_for_job(self, conv, text) -> dict | None:
        """Eos 25 Nov: a request for a new project gets its own folder and becomes this
        conversation's project before the plan is written."""
        from core.job_intent import new_project_folder
        folder = new_project_folder(text, time.strftime("%m%d-%H%M"))
        git_ready = create_project_folder(folder)
        project = self.agent_service.projects.add(str(folder))
        self.store.update_project(conv["id"], project["id"])
        return {**project, "git_ready": git_ready}

    def _run_job_plan(self, cid, msg_id, request, project_id):
        planner = (self._active_turn or {}).get("job_plan", {}).get("planner") or "claude"
        from core.team_turn import persona_name
        self._set_turn_progress(f"{persona_name(planner)} işi kilometre taşlarına bölüyor…", current_msg_id=msg_id)
        reply = ""
        try:
            reply = self._team_say(
                cid, msg_id, planner,
                self._team_header(planner) + plan_rule(request.get("kind"), request.get("sources") or ())
                + "\n--- KULLANICININ İSTEĞİ ---\n" + request["text"],
                project_id, step=1, limit=0, tool_less=False, project_scope=True, web=False)
        except Exception:
            reply = ""
        if self._is_turn_cancelled(msg_id):
            return
        milestones = parse_plan(self._full_reply(cid, msg_id) or reply)
        project = None
        try:
            project = self.agent_service.projects.get(project_id) if project_id else None
        except Exception:
            project = None
        path = (project or {}).get("path") or ""
        spec = job_spec(request["text"], milestones, path, time.strftime("%m%d-%H%M"),
                        full_access=bool(request.get("full_access")), kind=request.get("kind"),
                        sources=request.get("sources") or ())
        with self._lock:
            message = next((m for m in self.store.get(cid).get("messages", []) if m["id"] == msg_id), None)
            if message is not None:
                note = (f"Yeni proje klasörü açıldı: {request['new_project']}\n" if request.get("new_project") else "") \
                    + ("Git kurulamadı; adımlar commit'lenmeyecek.\n" if request.get("new_project_no_git") else "") \
                    + (("Dosya işi: çıktılar bu klasöre yazılır. Kaynaklara dokunmama kuralı ajanlara verilir"
                        + (" (Tam Yetki'de teknik bir engel değildir); SpeS kaynakların izini başta alır, iş "
                           "bitince değişip değişmediğini söyler: " + "; ".join(request["sources"])
                           if request.get("sources") else
                           "; isteğin kaynak yolu bulunamadı, SpeS kaynakları denetleyemeyecek")
                        + "."
                        + ("" if request.get("full_access") else
                           " Proje izninde komut çalışmaz; çıktılar metin (CSV/MD) olur, Excel CSV'yi açar.")
                        + "\n") if request.get("kind") == "data" else "") \
                    + plan_text(spec["milestones"]) + ("" if milestones else
                                                       "\n(Plan okunamadı; istek tek kilometre taşı olarak yapılacak.)")
                self.store.update_message_content(cid, msg_id, note, metadata={
                    **(message.get("metadata") or {}), "job_plan": True, "status": "completed"})
            self._finish_turn(msg_id, "completed")
            plan_turn = (self._active_turn or {}).get("turn_id")
            generation = self.__dict__.get("_plan_generation", 0)
        threading.Thread(target=self._start_planned_job, name="spes-job-plan",
                         args=(cid, spec, {**request, "plan_turn": plan_turn, "generation": generation}),
                         daemon=True).start()

    def _start_planned_job(self, cid, spec, request, settle=0.5, tries=60):
        """The job starts once the planning turn has let go; it never runs beside a turn.

        Fides 26 Nov (F5): never after SpeS began closing, never after the plan's turn was
        stopped, and never by waiting past a chat that stays busy."""
        def refuse(reason):
            self.store.append_message(cid, "assistant", f"İş başlatılmadı: {reason}", sender="quartz", metadata={
                "sender": "quartz", "recipient": "user", "status": "completed",
                "sequence": self._next_sequence(self.store.get(cid))})
        for _ in range(tries):
            if self.__dict__.get("_closed") or not self._job_turn_busy():
                break
            time.sleep(settle)
        with self._lock:
            if self.__dict__.get("_closed"):
                return
            turn = self._active_turn or {}
            # Fides re-review 26 Nov (F5): any Stop or close since the plan finished ends it,
            # even after another turn replaced the plan's; a missing generation is a refusal.
            stopped = (request.get("generation") is None
                       or request.get("generation") != self.__dict__.get("_plan_generation", 0)
                       or (request.get("plan_turn") and turn.get("turn_id") == request.get("plan_turn")
                           and turn.get("status") in {"cancelled", "cancelling"}))
        if stopped:
            return refuse("plan turu durduruldu.")
        if self._job_turn_busy():
            return refuse("sohbet hâlâ meşgul; isteği yeniden gönder.")
        try:
            self.job_start({**spec, "conversation_id": cid, "plan_generation": request.get("generation"),
                            "permission_level": "full" if request.get("full_access") else "project"})
        except (JobError, ValueError) as exc:
            self.store.append_message(cid, "assistant", f"İş başlatılamadı: {exc}", sender="quartz", metadata={
                "sender": "quartz", "recipient": "user", "status": "completed",
                "sequence": self._next_sequence(self.store.get(cid))})

    # -- a conversation whose job is running: plain words, no commands -------------
    def _expired_job_in(self, cid):
        """The conversation's latest job when it ran out of time with work left."""
        from core.long_job import JobLedger
        found = [l for l in JobLedger.all() if l.data.get("conversation_id") == cid]
        if not found:
            return None
        latest = max(found, key=lambda l: l.data.get("created_at") or 0)
        left = any(m["status"] in {"pending", "running"} for m in latest.data["milestones"])
        return latest if latest.data["status"] == "expired" and left and not latest.data.get("stopped") else None

    def _extend_expired_job(self, conv, text):
        """"15 dakika daha çalış" after the job ran out of time: it continues where it stopped."""
        from core.job_intent import extension_hours
        from core.long_job import JobError
        hours = extension_hours(text)
        ledger = self._expired_job_in(conv["id"]) if hours else None
        if ledger is None:
            return None
        if any(j.ledger.data["status"] in {"running", "waiting_limit", "paused"} for j in self._jobs().values()):
            return self._answer_without_agents(conv["id"], text, "Şu an başka bir uzun iş sürüyor; önce o bitmeli.")
        existing = self._jobs().get(ledger.data["id"])
        if existing is not None:
            if existing.thread is not None and existing.thread.is_alive():
                existing.thread.join(2.0)
            if existing.thread is not None and existing.thread.is_alive():
                return self._answer_without_agents(conv["id"], text, "İş tamamlanma kaydını kapatıyor; birkaç saniye sonra yeniden dene.")
            ledger = existing.ledger
        project = None
        try:
            project = self.agent_service.projects.get(conv.get("project_id")) if conv.get("project_id") else None
        except Exception:
            project = None
        from pathlib import Path as _Path
        same = isinstance(project, dict) and project.get("path") and \
            str(_Path(project["path"]).resolve()).lower() == str(_Path(ledger.data["project_path"]).resolve()).lower()
        if not same or project.get("protected") or project.get("workflow") == "warband":
            # Fides 26 Nov (F2): the writer would go to the chat's new project while the
            # checks and backups stayed on the old one.
            return self._answer_without_agents(conv["id"], text, (
                "Bu sohbetin projesi işin başladığı projeden farklı (ya da korumalı); süre uzatılmadı. "
                "İşin projesine dönüp yeniden dene ya da yeni bir istek gönder."))
        job = self._make_job(ledger)
        try:
            job.extend(hours)
        except JobError as exc:
            return self._answer_without_agents(conv["id"], text, str(exc))
        job.recover_after_crash()  # a milestone left "running" by the deadline is simply retried
        self._jobs()[ledger.data["id"]] = job
        left = [m for m in ledger.data["milestones"] if m["status"] in {"pending", "running"}]
        answer = self._answer_without_agents(conv["id"], text, (
            f"Süre {round(hours * 60)} dakika uzatıldı; iş kaldığı yerden sürüyor "
            f"({len(left)} adım kaldı: {left[0]['title']}…)."))
        job.start()
        return answer

    def _rewind_conversation_job(self, conv, text):
        """"2. adıma geri dön ve koyu tema yap" after a job finished/stopped/expired (28 Nov)."""
        from core.job_intent import job_change
        from core.long_job import JobError, JobLedger
        change = job_change(text)
        if not change or change[0] != "rewind":
            return None
        found = [l for l in JobLedger.all() if l.data.get("conversation_id") == conv["id"]]
        if not found:
            return None
        ledger = max(found, key=lambda l: l.data.get("created_at") or 0)
        if any(j.ledger.data["status"] in {"running", "waiting_limit", "paused"} for j in self._jobs().values()):
            return self._answer_without_agents(conv["id"], text, "Şu an başka bir uzun iş sürüyor; önce o bitmeli.")
        existing = self._jobs().get(ledger.data["id"])
        if existing is not None:
            if existing.thread is not None and existing.thread.is_alive():
                existing.thread.join(2.0)
            if existing.thread is not None and existing.thread.is_alive():
                return self._answer_without_agents(conv["id"], text, "İş tamamlanma kaydını kapatıyor; birkaç saniye sonra yeniden dene.")
            ledger = existing.ledger
        project = None
        try:
            project = self.agent_service.projects.get(conv.get("project_id")) if conv.get("project_id") else None
        except Exception:
            project = None
        from pathlib import Path as _Path
        same = isinstance(project, dict) and project.get("path") and \
            str(_Path(project["path"]).resolve()).lower() == str(_Path(ledger.data["project_path"]).resolve()).lower()
        if not same or project.get("protected") or project.get("workflow") == "warband":
            return self._answer_without_agents(conv["id"], text, (
                "Bu sohbetin projesi işin başladığı projeden farklı (ya da korumalı); geri sarılmadı."))
        job = self._make_job(ledger)
        try:
            info = job.rewind_milestone(change[1]["target"], note=change[1]["note"])
        except JobError as exc:
            return self._answer_without_agents(conv["id"], text, str(exc))
        self._jobs()[ledger.data["id"]] = job
        where = f"{info['to_step']}. adıma ({info['title']})" if info["to_step"] else "başlangıç durumuna"
        note_part = " Yeni talimatın iş defterine eklendi." if info["note"] else ""
        if info["expired"]:
            return self._answer_without_agents(conv["id"], text, (
                f"Zaman kapsülü: proje {where} geri sarıldı (önceki hali yedekte korundu).{note_part} "
                "İşin toplam 12 saat sınırı dolduğu için otomatik başlatılmadı."))
        job.start()
        return self._answer_without_agents(conv["id"], text, (
            f"Zaman kapsülü: proje {where} geri sarıldı (önceki hali yedekte korundu).{note_part} "
            f"Ekip {info['next_step']}. adımdan ({info['next_title']}) yeniden devam ediyor."))

    def _active_job_in(self, cid):
        return next((j for j in self._jobs().values() if j.ledger.data.get("conversation_id") == cid
                     and j.ledger.data["status"] in {"running", "waiting_limit", "paused"}), None)

    def _job_conversation_message(self, conv, text, job) -> dict:
        from core.job_intent import job_message_kind
        kind = job_message_kind(text)
        data = job.ledger.data
        from core.job_intent import extension_hours
        more = extension_hours(text) if kind not in {"stop", "pause"} else None
        if more:
            # "30 dakika daha çalış" while the job runs: the deadline moves (26 Nov).
            from core.long_job import JobError
            try:
                job.extend(more)
                answer = f"Süre {round(more * 60)} dakika uzatıldı."
            except JobError as exc:
                answer = str(exc)
            return self._answer_without_agents(conv["id"], text, answer)
        if kind == "status":
            done = sum(1 for m in data["milestones"] if m["status"] == "done")
            current = job.ledger.current()
            answer = (f"İş: {data['goal'][:120]} · {done}/{len(data['milestones'])} kilometre taşı bitti"
                      + (f" · şimdi: {current['title']}" if current else "")
                      + f" · durum: {data['status']}.")
            return self._answer_without_agents(conv["id"], text, answer)
        if kind in {"skip", "add", "rewind"}:
            # Live re-plan & Time Capsule (Eos/Fides 25-28 Nov): the plan changes in plain words.
            from core.job_intent import job_change
            from core.long_job import JobError
            _, value = job_change(text)
            try:
                if kind == "skip":
                    milestone = job.skip_milestone(value)
                    answer = f"{value}. adım ({milestone['title']}) plandan çıkarıldı; ekip ona geçmeyecek."
                elif kind == "add":
                    milestone = job.add_milestone(value)
                    answer = (f"Plana eklendi: {milestone['id'][1:]}. adım — {milestone['title']}. "
                              "Sıradaki adımlardan sonra yapılacak ve denetlenecek.")
                else:
                    info = job.rewind_milestone(value["target"], note=value["note"])
                    where = f"{info['to_step']}. adıma ({info['title']})" if info["to_step"] else "başlangıç durumuna"
                    note_part = " Yeni talimatın iş defterine eklendi." if info["note"] else ""
                    if data["status"] == "paused":
                        job.resume()
                        if job.thread is None or not job.thread.is_alive():
                            job.thread = None
                            job.start()
                    answer = (f"Zaman kapsülü: proje {where} geri sarıldı (önceki hali yedekte korundu).{note_part} "
                              f"Ekip {info['next_step']}. adımdan ({info['next_title']}) devam ediyor.")
            except JobError as exc:
                answer = str(exc)
            return self._answer_without_agents(conv["id"], text, answer)
        if kind in {"stop", "pause", "resume"}:
            if kind == "resume" and data["status"] != "paused":
                return self._answer_without_agents(conv["id"], text, "İş zaten sürüyor.")
            self.job_control(data["id"], kind)
            words = {"stop": "İş durduruldu; yapılan kilometre taşları yerinde duruyor.",
                     "pause": "İş duraklatıldı; 'devam' yazınca kaldığı yerden sürer.",
                     "resume": "İş kaldığı kilometre taşından sürüyor."}
            return self._answer_without_agents(conv["id"], text, words[kind])
        job.add_note(text)
        # Fides 25 Nov: "müşteri dosyasına dokunma" must not wait for the next milestone. The
        # writer of the running milestone gets it as an instruction now, with no wider rights.
        with self._lock:
            turn = self._active_turn
            if (turn and turn.get("long_job") == data["id"] and turn.get("status") == "running"
                    and turn.get("conversation_id") == conv["id"]):
                try:
                    return self._queue_instruction(text, turn.get("agent"), conv["id"], False, False)
                except (RuntimeError, PermissionError):
                    pass
        return self._answer_without_agents(conv["id"], text, (
            "Bunu iş defterine yazdım; ekip sıradaki her kilometre taşında okuyacak."))
