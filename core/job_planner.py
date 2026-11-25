"""The planning turn of a one-request job (user request 25 Nov 2026).

The first agent of the turn reads the project and writes a milestone plan; it writes nothing.
SpeS turns the plan into a long job with the user's own duration, SpeS's own check and the
permission the user switched on. A plan that cannot be read becomes a single milestone with
the user's request as its acceptance, so the request is never lost to a parsing problem.
"""
from __future__ import annotations

import threading
import time

from core.job_intent import MAX_MILESTONES, PLAN_RULE, job_spec, parse_plan
from core.long_job import JobError


def plan_text(milestones) -> str:
    lines = [f"{i}. {m['title']} — {m['acceptance']}" for i, m in enumerate(milestones, 1)]
    return "İş planı:\n" + "\n".join(lines)


class JobPlannerMixin:
    def _run_job_plan(self, cid, msg_id, request, project_id):
        planner = (self._active_turn or {}).get("job_plan", {}).get("planner") or "claude"
        from core.team_turn import persona_name
        self._set_turn_progress(f"{persona_name(planner)} işi kilometre taşlarına bölüyor…", current_msg_id=msg_id)
        reply = ""
        try:
            reply = self._team_say(
                cid, msg_id, planner,
                self._team_header(planner) + PLAN_RULE.format(max=MAX_MILESTONES)
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
        spec = job_spec(request["text"], milestones, path, time.strftime("%m%d-%H%M"))
        with self._lock:
            message = next((m for m in self.store.get(cid).get("messages", []) if m["id"] == msg_id), None)
            if message is not None:
                note = plan_text(spec["milestones"]) + ("" if milestones else
                                                        "\n(Plan okunamadı; istek tek kilometre taşı olarak yapılacak.)")
                self.store.update_message_content(cid, msg_id, note, metadata={
                    **(message.get("metadata") or {}), "job_plan": True, "status": "completed"})
            self._finish_turn(msg_id, "completed")
        threading.Thread(target=self._start_planned_job, name="spes-job-plan",
                         args=(cid, spec, request), daemon=True).start()

    def _start_planned_job(self, cid, spec, request, settle=0.5, tries=60):
        """The job starts once the planning turn has let go; it never runs beside a turn."""
        for _ in range(tries):
            if not self._job_turn_busy():
                break
            time.sleep(settle)
        try:
            self.job_start({**spec, "conversation_id": cid,
                            "permission_level": "full" if request.get("full_access") else "project"})
        except (JobError, ValueError) as exc:
            self.store.append_message(cid, "assistant", f"İş başlatılamadı: {exc}", sender="quartz", metadata={
                "sender": "quartz", "recipient": "user", "status": "completed",
                "sequence": self._next_sequence(self.store.get(cid))})

    # -- a conversation whose job is running: plain words, no commands -------------
    def _active_job_in(self, cid):
        return next((j for j in self._jobs().values() if j.ledger.data.get("conversation_id") == cid
                     and j.ledger.data["status"] in {"running", "waiting_limit", "paused"}), None)

    def _job_conversation_message(self, conv, text, job) -> dict:
        from core.job_intent import job_message_kind
        kind = job_message_kind(text)
        data = job.ledger.data
        if kind == "status":
            done = sum(1 for m in data["milestones"] if m["status"] == "done")
            current = job.ledger.current()
            answer = (f"İş: {data['goal'][:120]} · {done}/{len(data['milestones'])} kilometre taşı bitti"
                      + (f" · şimdi: {current['title']}" if current else "")
                      + f" · durum: {data['status']}.")
            return self._answer_without_agents(conv["id"], text, answer)
        if kind in {"skip", "add"}:
            # Live re-plan (Eos/Fides 25 Nov): the plan changes in plain words while the job runs.
            from core.job_intent import job_change
            from core.long_job import JobError
            _, value = job_change(text)
            try:
                if kind == "skip":
                    milestone = job.skip_milestone(value)
                    answer = f"{value}. adım ({milestone['title']}) plandan çıkarıldı; ekip ona geçmeyecek."
                else:
                    milestone = job.add_milestone(value)
                    answer = (f"Plana eklendi: {milestone['id'][1:]}. adım — {milestone['title']}. "
                              "Sıradaki adımlardan sonra yapılacak ve denetlenecek.")
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
