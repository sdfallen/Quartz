import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.long_job import JobError, JobLedger
from core.job_planner import JobPlannerMixin
from core.long_job_chat import LongJobChatMixin


class Store:
    def __init__(self, space="work"):
        self.conv = {"id": "c1", "project_id": "p1", "space": space, "messages": []}

    def get(self, cid=None):
        return self.conv

    def get_active(self):
        return self.conv

    def get_agent_model(self, cid, agent):
        return {"claude": {"model": "claude-opus-5-5", "effort": "medium"},
                "codex": {"model": "sol-6.1", "effort": "high"},
                "antigravity": {"model": "gemini-4-argon", "effort": "medium"}}[agent]

    def append_message(self, cid, role, content, sender=None, metadata=None):
        message = {"id": f"m{len(self.conv['messages'])}", "role": role, "content": content,
                   "sender": sender, "metadata": dict(metadata or {})}
        self.conv["messages"].append(message)
        return message


class Projects:
    def __init__(self, path, **extra):
        self.project = {"path": str(path), **extra}

    def get(self, pid):
        return self.project


class Service:
    def __init__(self, path, **extra):
        self.projects = Projects(path, **extra)


class FakeChat(LongJobChatMixin, JobPlannerMixin):
    """Just enough of AgentChatService for the long-job layer."""

    def __init__(self, project, *, replies, space="work", **project_extra):
        self.store = Store(space)
        self.agent_service = Service(project, **project_extra)
        self._lock = threading.RLock()
        self._active_turn = None
        self.replies = list(replies)
        self.sent = []
        self.cancelled = 0

    def _next_sequence(self, conv):
        return len(conv["messages"])

    def _team_ready(self):
        return True

    def cancel_active(self):
        self.cancelled += 1

    def _answer_without_agents(self, cid, text, answer):
        self.store.append_message(cid, "user", text, sender="user")
        note = self.store.append_message(cid, "assistant", answer, sender="quartz")
        return {"assistant_message": note}

    def send_message(self, text, agent=None, conversation_id=None, write=False, confirm_write=False, full_access=False,
                     origin=None):
        self.sent.append({"agent": agent, "write": write, "confirm": confirm_write, "text": text, "full": full_access,
                          "origin": origin})
        state, reply, sender = self.replies.pop(0)
        user = self.store.append_message("c1", "user", text, sender="user",
                                         metadata={"task_id": f"t{len(self.sent)}", "instruction_state": state})
        self.store.append_message("c1", "assistant", reply, sender=sender)
        return {"user_message": user}


class LongJobChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "game"
        self.project.mkdir()
        self.env = patch.dict(os.environ, {"QUARTZ_JOBS_HOME": str(Path(self.tmp.name) / "jobs")})
        self.env.start()
        # No real copies in ~/.quartz/checkpoints from tests.
        self.cp = [patch("core.long_job.baseline_checkpoint", return_value={"status": "snapshot", "ref": "b"}),
                   patch("core.long_job.milestone_checkpoint", return_value={"status": "snapshot", "ref": "m"}),
                   # Never this machine's real usage record (17 Nov: a "full" Claude record made
                   # the writer Fides and two tests failed).
                   patch("core.agent_limits.snapshot", return_value={})]
        for item in self.cp:
            item.start()

    def tearDown(self):
        for item in self.cp:
            item.stop()
        self.env.stop()
        self.tmp.cleanup()

    def spec(self, **extra):
        return {"goal": "Yol Hakkı animasyonları", "hours": 1,
                "milestones": [{"title": "Yürüme", "acceptance": "8 yön döngü"}], **extra}

    def wait_done(self, chat, job_id):
        for _ in range(200):
            status = chat._jobs()[job_id].ledger.data["status"]
            if status in {"done", "needs_user", "failed", "stopped"}:
                thread = chat._jobs()[job_id].thread
                if thread is not None:
                    thread.join(5)  # the last ledger write happens after the status
                return status
            time.sleep(0.02)
        return status

    def test_a_milestone_is_one_confirmed_workspace_write_turn(self):
        chat = FakeChat(self.project, replies=[("completed", "Yürüme döngüsü eklendi.", "claude")])
        with patch("core.long_job_chat.time"), patch("core.long_job.keep_awake"):
            job = chat.job_start(self.spec(project_path="C:/somewhere/else"))
        self.assertEqual(self.wait_done(chat, job["id"]), "done")
        sent = chat.sent[0]
        self.assertEqual((sent["agent"], sent["write"], sent["confirm"]), ("collaboration", True, True))
        self.assertIn("KABUL ÖLÇÜTÜ: 8 yön döngü", sent["text"])
        ledger = chat._jobs()[job["id"]].ledger
        self.assertEqual(ledger.data["project_path"], str(self.project.resolve()))  # never a free path
        self.assertEqual(ledger.data["models"]["claude"]["model"], "claude-opus-5-5")
        notes = [m["content"] for m in chat.store.conv["messages"] if m["sender"] == "quartz"]
        self.assertTrue(notes[0].startswith("Uzun iş başladı"))

    def test_writer_limit_hands_the_milestone_to_fides(self):
        chat = FakeChat(self.project, replies=[
            ("failed", "Başarısız. CLAUDE Kota Hatası: Kullanım sınırına takıldı.", "claude"),
            ("completed", "Tamam.", "codex")])
        with patch("core.long_job.keep_awake"):
            job = chat.job_start(self.spec())
        self.assertEqual(self.wait_done(chat, job["id"]), "done")
        self.assertEqual([s["agent"] for s in chat.sent], ["collaboration", "codex"])
        self.assertIn("Fides", chat.sent[1]["text"])
        notes = " ".join(m["content"] for m in chat.store.conv["messages"] if m["sender"] == "quartz")
        self.assertIn("Yazıcı Fatum → Fides", notes)

    def test_a_reviewer_at_its_limit_does_not_move_the_writer(self):
        chat = FakeChat(self.project, replies=[("partial", "Başarısız. ANTIGRAVITY Kota Hatası.", "antigravity")])
        with patch("core.long_job.keep_awake"):
            job = chat.job_start(self.spec())
        self.assertEqual(self.wait_done(chat, job["id"]), "done")
        self.assertEqual(len(chat.sent), 1)

    def test_only_workspace_and_a_writable_project(self):
        with self.assertRaises(JobError):
            FakeChat(self.project, replies=[], space="chat").job_start(self.spec())
        with self.assertRaises(JobError):
            FakeChat(self.project, replies=[], workflow="warband").job_start(self.spec())

    def test_startup_resumes_only_auto_resume_jobs(self):
        auto = JobLedger.create({**self.spec(auto_resume=True), "project_path": str(self.project), "conversation_id": "c1"})
        manual = JobLedger.create({**self.spec(), "project_path": str(self.project), "conversation_id": "c1"})
        stopped = JobLedger.create({**self.spec(auto_resume=True), "project_path": str(self.project), "conversation_id": "c1"})
        for ledger in (auto, manual, stopped):
            ledger.data["status"] = "running"
            ledger.data["milestones"][0]["status"] = "running"
            ledger.save()
        stopped.data.update(stopped=True, status="stopped")
        stopped.save()
        chat = FakeChat(self.project, replies=[("completed", "Tamam.", "claude")])
        with patch("core.long_job.keep_awake"):
            resumed = chat.resume_jobs_at_startup()
            self.assertEqual(resumed, [auto.data["id"]])
            self.assertEqual(self.wait_done(chat, auto.data["id"]), "done")
        self.assertEqual(chat._jobs()[manual.data["id"]].ledger.data["status"], "paused")
        self.assertNotIn(stopped.data["id"], chat._jobs())
        self.assertIn("yarıda kaldı", chat.sent[0]["text"])

    def test_stop_cancels_the_jobs_own_running_turn(self):
        chat = FakeChat(self.project, replies=[])
        ledger = JobLedger.create({**self.spec(), "project_path": str(self.project), "conversation_id": "c1"})
        job = chat._make_job(ledger)
        chat._jobs()[ledger.data["id"]] = job
        chat._active_turn = {"long_job": ledger.data["id"], "status": "running"}
        chat.job_control(ledger.data["id"], "stop")
        self.assertEqual(chat.cancelled, 1)
        self.assertTrue(JobLedger.load(ledger.path).data["stopped"])


    def test_there_is_no_typed_command_any_more(self):
        # User request 25 Nov: "/uzun-iş gibi komutları kaldır; tek istekle her şeyi yapsın".
        import core.long_job as long_job
        import core.long_job_chat as long_job_chat
        self.assertFalse(hasattr(long_job, "parse_command"))
        self.assertFalse(hasattr(long_job, "COMMAND"))
        self.assertFalse(hasattr(long_job_chat.LongJobChatMixin, "_long_job_command"))


if __name__ == "__main__":
    unittest.main()


class DurationTextTests(unittest.TestCase):
    def test_durations_read_like_a_person_wrote_them(self):
        from core.long_job_chat import _duration
        self.assertEqual(_duration(40 / 60), "40 dakika")  # live 15 Nov: "0.666667 saat"
        self.assertEqual(_duration(2), "2 saat")
        self.assertEqual(_duration(1.5), "1 saat 30 dakika")


class LongJobRoutingTests(unittest.TestCase):
    def test_a_big_build_request_never_reaches_the_desktop_router(self):
        # Live 15 Nov: milestone words like "kapı" and "el uzatıp" started a desktop task; a
        # one-request job names games and windows too (25 Nov).
        import gui
        api = gui.Api()
        text = "Baştan sona oynanabilir bir kapı açma oyunu yap; oyuncu el uzatıp kapıyı açsın, pencere de olsun"
        with patch.object(api, "_coordination_service", side_effect=AssertionError("desktop router reached")):
            result = api.coordination_route(text, "c1", "p1", {}, "project", "claude")
        self.assertEqual(result, {"status": "ok", "data": {"handled": False, "intent": "task"}})


class PausedJobAfterRestartTests(LongJobChatTests):
    def test_resume_finds_a_job_paused_before_the_restart(self):
        # Live 15 Nov: after a restart the paused job was on disk only and "Devam" said not found.
        ledger = JobLedger.create({**self.spec(), "project_path": str(self.project), "conversation_id": "c1"})
        ledger.data["status"] = "paused"
        ledger.save()
        chat = FakeChat(self.project, replies=[("completed", "Tamam.", "claude")])
        with patch("core.long_job.keep_awake"):
            chat.job_control(ledger.data["id"], "resume")
            self.assertEqual(self.wait_done(chat, ledger.data["id"]), "done")
        with self.assertRaises(JobError):
            chat.job_control("yok-boyle-bir-is", "resume")


class PermissionLevelTests(LongJobChatTests):
    def test_the_chats_permission_level_travels_with_the_job(self):
        # User decision 15 Nov: with Tam Yetki the writer may run Blender/Godot.
        from core.job_intent import job_spec
        spec = job_spec("Baştan sona yürüme animasyonu sistemi yap", [{"title": "Yürüme", "acceptance": "8 yön"}],
                        self.project, "1125-1200")
        for full, level in ((True, "full"), (False, "project")):
            chat = FakeChat(self.project, replies=[("completed", "Tamam.", "claude")])
            with patch("core.long_job.keep_awake"):
                chat._start_planned_job("c1", spec, {"full_access": full})
                job_id = next(iter(chat._jobs()))
                self.assertEqual(self.wait_done(chat, job_id), "done")
            self.assertEqual(chat._jobs()[job_id].ledger.data["permission_level"], level)
            self.assertEqual(chat.sent[0]["full"], full)
            # A milestone SpeS sends is never planned again or read as the user talking.
            self.assertEqual(chat.sent[0]["origin"], "long_job")
            start = next(m["content"] for m in chat.store.conv["messages"] if m["content"].startswith("Uzun iş başladı"))
            self.assertIn("Tam Yetki" if full else "Proje izni", start)


class TalkingToAJobTests(LongJobChatTests):
    def running(self, chat):
        ledger = JobLedger.create({**self.spec(), "project_path": str(self.project), "conversation_id": "c1"})
        ledger.data["status"] = "running"
        chat._jobs()[ledger.data["id"]] = chat._make_job(ledger)
        return ledger

    def test_a_plain_message_becomes_a_note_for_the_next_milestone(self):
        from core.long_job import milestone_prompt
        chat = FakeChat(self.project, replies=[])
        ledger = self.running(chat)
        job = chat._active_job_in("c1")
        answer = chat._job_conversation_message(chat.store.conv, "Kollar daha çok sallansın", job)
        self.assertIn("iş defterine", answer["assistant_message"]["content"])
        self.assertIn("Denetmen notu: Kollar daha çok sallansın",
                      milestone_prompt(ledger, ledger.data["milestones"][0], "claude"))

    def test_status_and_stop_in_plain_words(self):
        chat = FakeChat(self.project, replies=[])
        ledger = self.running(chat)
        job = chat._active_job_in("c1")
        status = chat._job_conversation_message(chat.store.conv, "ne durumda?", job)
        self.assertIn("0/1 kilometre taşı", status["assistant_message"]["content"])
        self.assertIn("Yürüme", status["assistant_message"]["content"])
        stopped = chat._job_conversation_message(chat.store.conv, "dur", job)
        self.assertIn("durduruldu", stopped["assistant_message"]["content"])
        self.assertTrue(JobLedger.load(ledger.path).data["stopped"])
        self.assertIsNone(chat._active_job_in("c1"))


class UnreachableWriterTests(LongJobChatTests):
    def test_a_lost_connection_is_not_a_failed_attempt(self):
        chat = FakeChat(self.project, replies=[
            ("failed", "Reconnecting... 5/5 (workspace routing discovery failed)", "codex")])
        outcome = None
        chat.send_message("x", agent="codex", conversation_id="c1", write=True, confirm_write=True)
        user_id = chat.store.conv["messages"][-2]["id"]
        outcome = chat._job_turn_outcome("c1", user_id, "codex", None)
        self.assertEqual(outcome.get("unavailable"), "codex")
        real = FakeChat(self.project, replies=[("failed", "Test kırık: walk_0 bulunamadı", "codex")])
        real.send_message("x", agent="codex", conversation_id="c1", write=True, confirm_write=True)
        user_id = real.store.conv["messages"][-2]["id"]
        self.assertNotIn("unavailable", real._job_turn_outcome("c1", user_id, "codex", None))


class FinishCallTests(LongJobChatTests):
    def test_the_end_of_a_job_rings_the_phone_with_a_report(self):
        # User request 15 Nov: "işler bitince arasınlar"; the phone rings for metadata.report.
        chat = FakeChat(self.project, replies=[("completed", "Tamam.", "claude")])
        with patch("core.long_job.keep_awake"):
            job = chat.job_start(self.spec(git_branch=None))
            self.assertEqual(self.wait_done(chat, job["id"]), "done")
        last = [m for m in chat.store.conv["messages"] if m["sender"] == "quartz"][-1]
        self.assertTrue(last["metadata"].get("report"))
        self.assertIn("Uzun iş bitti", last["content"])
        self.assertIn("✔ Yürüme", last["content"])


class SettlingTurnTests(LongJobChatTests):
    def test_a_settling_chat_is_waited_for_not_counted(self):
        # Live 15 Nov: "Önceki ajan süreçlerinin durduğu henüz doğrulanmadı" used up an attempt.
        chat = FakeChat(self.project, replies=[("completed", "Tamam.", "claude")])
        original, calls = chat.send_message, []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("Önceki ajan süreçlerinin durduğu henüz doğrulanmadı.")
            return original(*args, **kwargs)

        chat.send_message = flaky
        ledger = JobLedger.create({**self.spec(), "project_path": str(self.project), "conversation_id": "c1"})
        stop = threading.Event()
        with patch("core.long_job_chat.SETTLE_SECONDS", 0.01):
            result = chat._job_run_milestone(ledger, ledger.data["milestones"][0], "claude", stop)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(calls), 3)
