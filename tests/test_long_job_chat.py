import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.long_job import JobError, JobLedger
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


class FakeChat(LongJobChatMixin):
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

    def send_message(self, text, agent=None, conversation_id=None, write=False, confirm_write=False):
        self.sent.append({"agent": agent, "write": write, "confirm": confirm_write, "text": text})
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
                   patch("core.long_job.milestone_checkpoint", return_value={"status": "snapshot", "ref": "m"})]
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


    def test_the_typed_command_starts_a_job_only_with_desktop_write_permission(self):
        from core.long_job import parse_command
        text = "\n".join(["/uzun-iş", "Hedef: Yürüme animasyonu", "Süre: 30 dakika", "Devam: evet",
                          'Kontrol: python -c "print(1)"', "Dal: spes/deneme-1",
                          "1. Yürüme | 8 yön döngü", "2. Koşma | 8 yön"])
        spec = parse_command(text)
        self.assertEqual(spec["goal"], "Yürüme animasyonu")
        self.assertAlmostEqual(spec["hours"], 0.5)
        self.assertTrue(spec["auto_resume"])
        self.assertEqual(spec["verify"], ["python", "-c", "print(1)"])
        self.assertEqual(spec["git_branch"], "spes/deneme-1")
        self.assertEqual([m["title"] for m in spec["milestones"]], ["Yürüme", "Koşma"])
        self.assertIsNone(parse_command("uzun iş hakkında ne düşünüyorsun?"))
        self.assertEqual(parse_command("/uzun-iş durum"), {"list": True})
        with self.assertRaises(JobError):
            parse_command("/uzun-iş\nNe: olur")
        chat = FakeChat(self.project, replies=[])
        answer = chat._long_job_command(chat.store.conv, text, spec, False)  # phone / no write permission
        self.assertIn("yazma izni", answer["assistant_message"]["content"])
        self.assertEqual(chat._jobs(), {})


if __name__ == "__main__":
    unittest.main()


class DurationTextTests(unittest.TestCase):
    def test_durations_read_like_a_person_wrote_them(self):
        from core.long_job_chat import _duration
        self.assertEqual(_duration(40 / 60), "40 dakika")  # live 15 Nov: "0.666667 saat"
        self.assertEqual(_duration(2), "2 saat")
        self.assertEqual(_duration(1.5), "1 saat 30 dakika")


class LongJobRoutingTests(unittest.TestCase):
    def test_the_command_never_reaches_the_desktop_router(self):
        # Live 15 Nov: milestone words like "kapı" and "el uzatıp" started a desktop task.
        import gui
        api = gui.Api()
        text = "/uzun-iş\nHedef: Kapıyı el uzatıp açma animasyonu\n1. Kapı | ekrana tıkla ve klavyede yaz"
        with patch.object(api, "_coordination_service", side_effect=AssertionError("desktop router reached")):
            result = api.coordination_route(text, "c1", "p1", {}, "project", "claude")
        self.assertEqual(result, {"status": "ok", "data": {"handled": False, "intent": "task"}})
