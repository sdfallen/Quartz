"""SpeS opens what a job built and looks (core.launch_check) — Fides's design review 26 Nov.

Real processes are started (python scripts that never open a window), so ownership, crash,
timeout, Stop and cleanup are real; window finding and capture are faked so no test ever puts a
window on the user's screen."""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import launch_check as lc

WINDOWS = os.name == "nt"


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def test_the_one_gui_program_is_the_entry(self):
        self.write("main.py", "import tkinter as tk\nroot = tk.Tk()\n")
        self.write("helpers.py", "def f(): pass\n")
        entry, why = lc.detected_entry(self.root)
        self.assertEqual((entry.name, why), ("main.py", ""))

    def test_two_gui_programs_are_ambiguous_and_never_guessed(self):
        self.write("main.py", "import pygame\n")
        self.write("app.py", "from tkinter import Tk\n")
        entry, why = lc.detected_entry(self.root)
        self.assertIsNone(entry)
        self.assertIn("belirsiz giriş noktası", why)

    def test_a_commented_import_is_not_a_gui(self):
        self.write("main.py", "# import tkinter\nprint('merhaba')\n")
        entry, why = lc.detected_entry(self.root)
        self.assertIsNone(entry)
        self.assertTrue(why)

    def test_a_single_gui_script_with_another_name_is_found(self):
        self.write("yilan.py", "import pygame\n")
        self.write("test_yilan.py", "import pygame\n")
        self.assertEqual(lc.detected_entry(self.root)[0].name, "yilan.py")

    def test_only_a_milestone_that_asks_to_see_it_is_looked_at(self):
        self.assertTrue(lc.wants_look({"title": "Oyun penceresi", "acceptance": "pencere açılıyor"}))
        self.assertFalse(lc.wants_look({"title": "Skor hesabı", "acceptance": "testler geçiyor"}))


@unittest.skipUnless(WINDOWS, "Windows Job Object")
class ObserveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "p"
        self.project.mkdir()

    def run_script(self, text, stop=None, attempt="m1-deneme1", **kwargs):
        entry = self.project / "main.py"
        entry.write_text(text, encoding="utf-8")
        return lc.observe(entry, self.project, self.root / "kanit" / attempt, stop or threading.Event(),
                          sys.executable, **kwargs)

    @staticmethod
    def png(hwnd, result, verify):
        # A fake window: its owner is the test's own decision, so the real verify is not asked.
        result.update(state="captured", png=b"png")

    def test_a_program_that_fails_by_itself_is_a_crash(self):
        receipt = self.run_script("import sys\nprint('token=abc123')\nraise SystemExit('kirik')\n",
                                  windows=lambda pids: [])
        self.assertEqual(lc.verdict(receipt), "crashed")
        self.assertEqual(receipt["exit_code"], 1)
        self.assertIn("kirik", receipt["output_tail"])
        self.assertNotIn("abc123", receipt["output_tail"], "secrets are masked before any prompt")
        self.assertEqual(receipt["cleanup_state"], "confirmed")
        self.assertTrue((self.root / "kanit" / "m1-deneme1" / "receipt.json").is_file())

    def test_no_window_in_time_is_unproven_and_the_program_is_closed(self):
        marker = self.root / "hala-calisiyor.txt"
        receipt = self.run_script(f"import time\nwhile True:\n    open(r'{marker}', 'w').write('x')\n    time.sleep(0.1)\n",
                                  windows=lambda pids: [], watch=1.0)
        self.assertEqual(lc.verdict(receipt), "startup_timeout")
        self.assertEqual(receipt["cleanup_state"], "confirmed")
        marker.unlink(missing_ok=True)
        time.sleep(0.5)
        self.assertFalse(marker.exists(), "the program is really gone")

    def test_a_seen_window_is_captured_and_closed_by_spes(self):
        receipt = self.run_script("import time\ntime.sleep(30)\n",
                                  windows=lambda pids: [(1234, min(pids), "Yılan Oyunu")],
                                  settle=0.2, capture=self.png)
        self.assertEqual(lc.verdict(receipt), "window_seen")
        self.assertEqual(receipt["capture_state"], "captured")
        self.assertTrue(Path(receipt["screenshot"]).is_file())
        self.assertEqual(receipt["termination_reason"], "closed_by_spes")
        self.assertEqual(receipt["cleanup_state"], "confirmed")
        self.assertIn("etkileşim denenmedi", lc.evidence_text(receipt))

    def test_l4_a_window_no_longer_ours_is_never_captured(self):
        calls = []

        def capture(hwnd, result, verify):
            calls.append(verify())
            result["state"] = "owner_changed" if not calls[-1] else "captured"
        with patch.object(lc, "_owner_pid", return_value=999999):  # the HWND now belongs to someone else
            receipt = self.run_script("import time\ntime.sleep(30)\n",
                                      windows=lambda pids: [(1234, min(pids), "T")], settle=0.2, capture=capture)
        self.assertEqual(calls, [False])
        self.assertEqual(receipt["capture_state"], "owner_changed")
        self.assertEqual(receipt["screenshot"], "")

    def test_l3_a_late_capture_never_writes_evidence(self):
        release = threading.Event()

        def capture(hwnd, result, verify):
            release.wait(30)
            result.update(state="captured", png=b"late")
        began = time.monotonic()
        with patch.object(lc, "CAPTURE_SECONDS", 0.3):
            receipt = self.run_script("import time\ntime.sleep(30)\n",
                                      windows=lambda pids: [(1, min(pids), "T")], settle=0.1, capture=capture)
        self.assertEqual(receipt["capture_state"], "timeout")
        self.assertEqual(receipt["cleanup_state"], "pending", "the capture worker had not ended")
        release.set()
        time.sleep(0.3)
        self.assertFalse((Path(receipt["review_dir"]) / "window.png").exists(), "no evidence after the deadline")
        self.assertLess(time.monotonic() - began, 15)
        lc._UNCONFIRMED.clear()

    def test_l2_a_stop_given_before_starts_nothing(self):
        stop = threading.Event()
        stop.set()
        marker = self.root / "calisti.txt"
        with patch("subprocess.Popen") as popen, patch("core.process_tree.resume_process") as resume:
            receipt = self.run_script(f"open(r'{marker}', 'w').write('x')\n", stop=stop, windows=lambda pids: [])
        self.assertEqual((popen.call_count, resume.call_count), (0, 0))
        self.assertEqual(lc.verdict(receipt), "cancelled")
        self.assertTrue((self.root / "kanit" / "m1-deneme1" / "receipt.json").is_file())

    def test_l2_a_stop_during_binding_never_resumes(self):
        stop = threading.Event()
        marker = self.root / "calisti.txt"
        from core import process_tree

        real_bind = process_tree.bind_kill_on_close_job

        def bind(proc, resume=False):
            stop.set()  # Stop arrives while the program is being bound
            return real_bind(proc, resume=resume)
        with patch("core.process_tree.bind_kill_on_close_job", side_effect=bind), \
                patch("core.process_tree.resume_process") as resume:
            receipt = self.run_script(f"open(r'{marker}', 'w').write('x')\n", stop=stop, windows=lambda pids: [])
        self.assertEqual(resume.call_count, 0)
        self.assertEqual(lc.verdict(receipt), "cancelled")
        self.assertEqual(receipt["cleanup_state"], "confirmed")
        time.sleep(0.3)
        self.assertFalse(marker.exists())

    def test_stop_cancels_the_look_and_closes_the_program(self):
        stop = threading.Event()
        threading.Timer(0.5, stop.set).start()
        receipt = self.run_script("import time\ntime.sleep(30)\n", stop=stop, windows=lambda pids: [])
        self.assertEqual(lc.verdict(receipt), "cancelled")
        self.assertEqual(receipt["cleanup_state"], "confirmed")

    def test_l6_a_program_that_cannot_be_owned_never_runs_and_still_has_a_receipt(self):
        marker = self.root / "calisti.txt"
        with patch("core.process_tree.bind_kill_on_close_job", return_value=False):
            receipt = self.run_script(f"open(r'{marker}', 'w').write('x')\n", windows=lambda pids: [])
        self.assertEqual(lc.verdict(receipt), "blocked")
        self.assertEqual(receipt["termination_reason"], "job_object_unavailable")
        self.assertTrue((self.root / "kanit" / "m1-deneme1" / "receipt.json").is_file())
        time.sleep(0.5)
        self.assertFalse(marker.exists(), "the suspended program was never resumed")

    def test_l5_the_reviewers_folder_holds_no_raw_output(self):
        receipt = self.run_script("import time\nprint('password=gizli-deneme-123', flush=True)\ntime.sleep(30)\n",
                                  windows=lambda pids: [(1234, min(pids), "T")], settle=0.3, capture=self.png)
        review = Path(receipt["review_dir"])
        self.assertEqual([p.name for p in review.iterdir()], ["window.png"])
        for path in review.rglob("*"):
            self.assertNotIn(b"gizli-deneme-123", path.read_bytes())
        self.assertNotIn("gizli-deneme-123", receipt["output_tail"])

    def test_two_attempts_keep_their_own_evidence(self):
        first = self.run_script("raise SystemExit(2)\n", windows=lambda pids: [])
        second = self.run_script("raise SystemExit(2)\n", attempt="m1-deneme2", windows=lambda pids: [])
        self.assertNotEqual(first["evidence_dir"], second["evidence_dir"])
        self.assertTrue((Path(first["evidence_dir"]) / "receipt.json").is_file())

    def test_l1_an_unreadable_tree_is_never_called_clean(self):
        with patch.object(lc, "_members", return_value=None):
            receipt = self.run_script("raise SystemExit(0)\n", windows=lambda pids: [])
        self.assertEqual(receipt["cleanup_state"], "pending")
        self.assertEqual(lc.verdict(receipt), "cleanup_pending")
        lc._UNCONFIRMED.clear()


class JobWiringTests(unittest.TestCase):
    def make(self, look, accept_seen):
        from tests.test_long_job import Clock, nullctx
        from core.long_job import JobLedger, LongJob
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "p").mkdir()
        ledger = JobLedger.create({"goal": "Oyun", "project_path": str(root / "p"), "hours": 2, "review": True,
                                   "milestones": [{"title": "Pencere", "acceptance": "pencere açılıyor"}]},
                                  root=root / "jobs", clock=Clock())
        job = LongJob(ledger, run_milestone=lambda l, m, w, s: {"status": "completed"},
                      verify=lambda stop: {"ok": True, "summary": "ok"},
                      checkpoint=lambda: {"status": "snapshot", "ref": "cp"},
                      baseline=lambda: {"status": "snapshot", "ref": "b"}, snapshot=lambda: {},
                      changed=lambda a, b: [], commit=lambda f, m: None,
                      notify=lambda *a, **k: None, clock=Clock(), awake=nullctx,
                      accept=lambda l, m, w, c, s: accept_seen.append(c) or {"ok": True, "by": "claude"},
                      launch=lambda l, m, s: look)
        return job, ledger

    def test_a_crash_sends_the_milestone_back_with_the_output(self):
        seen = []
        job, ledger = self.make({"verdict": "crashed", "output_tail": "Traceback: NameError"}, seen)
        job.run()
        milestone = ledger.data["milestones"][0]
        self.assertFalse(seen, "a crash never reaches the reviewer as a pass")
        self.assertIn("hata verip kapandı", milestone["history"][0]["note"] + milestone.get("last_failure", ""))

    def test_a_seen_window_reaches_the_reviewer_and_the_report(self):
        from core.long_job import finish_report
        seen = []
        look = {"verdict": "window_seen", "entry": "main.py", "window_title": "Yılan", "capture_state": "captured",
                "evidence_text": "SPES ÇALIŞTIRMA DENETİMİ"}
        job, ledger = self.make(look, seen)
        job.run()
        self.assertEqual(seen[0]["launch"]["verdict"], "window_seen")
        self.assertIn("Program açıldı", finish_report(ledger))

    def test_l1_an_unconfirmed_cleanup_holds_the_milestone_without_review(self):
        seen = []
        job, ledger = self.make({"verdict": "cleanup_pending", "cleanup_state": "pending"}, seen)
        job.run()
        milestone = ledger.data["milestones"][0]
        self.assertFalse(seen, "no review over an unconfirmed cleanup")
        self.assertEqual(milestone["status"], "needs_user")
        self.assertNotIn("commit", {k for k, v in milestone.items() if v})

    def test_a_busy_desktop_is_not_a_defect(self):
        from core.long_job import finish_report
        seen = []
        job, ledger = self.make({"verdict": "skipped", "reason": "masaüstü başka bir görevde ya da ekran kilitli"}, seen)
        job.run()
        self.assertEqual(ledger.data["milestones"][0]["status"], "done")
        self.assertIn("Program çalıştırılıp görülmedi: masaüstü başka bir görevde", finish_report(ledger))


class ChatLaunchGateTests(unittest.TestCase):
    def test_only_full_permission_code_jobs_that_ask_are_looked_at(self):
        from core.long_job_chat import LongJobChatMixin

        class Ledger:
            def __init__(self, **data):
                self.data = {"project_path": tempfile.gettempdir(), **data}
                self.path = Path(tempfile.gettempdir()) / "ledger.json"
        mixin = LongJobChatMixin()
        ask = {"id": "m1", "title": "Pencere", "acceptance": "pencere açılıyor"}
        self.assertIsNone(mixin._job_launch(Ledger(kind="data", permission_level="full"), ask, threading.Event()))
        self.assertIsNone(mixin._job_launch(Ledger(kind="code", permission_level="project"), ask, threading.Event()))
        self.assertIsNone(mixin._job_launch(Ledger(kind="code", permission_level="full"),
                                            {"id": "m1", "title": "Skor", "acceptance": "testler geçiyor"},
                                            threading.Event()))
        with tempfile.TemporaryDirectory() as empty:
            look = mixin._job_launch(Ledger(kind="code", permission_level="full", project_path=empty), ask,
                                     threading.Event())
        self.assertEqual(look["verdict"], "skipped")



class ReviewPromptTests(unittest.TestCase):
    def review(self, reviewer, look):
        from tests.test_long_job_chat import FakeChat
        from core.long_job import JobLedger
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {"QUARTZ_JOBS_HOME": str(Path(directory) / "jobs")}), \
                patch("core.agent_limits.snapshot", return_value={}):
            project = Path(directory) / "p"
            project.mkdir()
            chat = FakeChat(project, replies=[("completed", "KABUL: EVET", reviewer)])
            ledger = JobLedger.create({"goal": "Oyun", "project_path": str(project), "hours": 1, "kind": "code",
                                       "conversation_id": "c1", "milestones": [{"title": "T", "acceptance": "ok"}]})
            writer = "codex" if reviewer == "claude" else "claude"
            with patch.object(chat, "_job_members", return_value=[writer, reviewer]):
                chat._job_accept(ledger, ledger.data["milestones"][0], writer, {"ok": True, "launch": look},
                                 threading.Event())
        return chat.sent[-1]

    def test_fatum_gets_the_attempts_folder_and_others_are_told_they_did_not_see_it(self):
        with tempfile.TemporaryDirectory() as evidence:
            look = {"verdict": "window_seen", "evidence_text": "SPES ÇALIŞTIRMA DENETİMİ x",
                    "screenshot": str(Path(evidence) / "window.png"), "review_dir": evidence}
            fatum = self.review("claude", look)
            fides = self.review("codex", look)
        self.assertEqual(fatum["read_root"], evidence)
        self.assertIn("window.png", fatum["text"])
        self.assertIsNone(fides["read_root"])
        self.assertIn("görsel incelendi deme", fides["text"])
        self.assertIn("SPES ÇALIŞTIRMA DENETİMİ", fides["text"])


class GateRegistryTests(unittest.TestCase):
    def test_l1_no_new_look_while_an_earlier_tree_is_unconfirmed(self):
        from core.long_job_chat import LongJobChatMixin

        class Ledger:
            data = {"project_path": tempfile.gettempdir(), "kind": "code", "permission_level": "full"}
            path = Path(tempfile.gettempdir()) / "ledger.json"
        lc._UNCONFIRMED["test"] = {"members": {os.getpid(): lc._create_time(os.getpid())},  # surely alive
                                   "capture": None, "unknown": False}
        try:
            look = LongJobChatMixin()._job_launch(Ledger(), {"id": "m1", "title": "Pencere",
                                                             "acceptance": "pencere açılıyor"}, threading.Event())
        finally:
            lc._UNCONFIRMED.clear()
        self.assertEqual(look["verdict"], "skipped")
        self.assertIn("önceki programın kapandığı henüz doğrulanmadı", look["reason"])


@unittest.skipUnless(WINDOWS, "Windows Job Object")
class PendingOwnershipTests(unittest.TestCase):
    """Fides's launch re-review 26 Nov: RR1 and RR2."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lc._UNCONFIRMED.clear)
        self.root = Path(self.tmp.name)
        self.project = self.root / "p"
        self.project.mkdir()
        (self.project / "main.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

    def look(self, **kwargs):
        return lc.observe(self.project / "main.py", self.project, self.root / "kanit", threading.Event(),
                          sys.executable, **kwargs)

    def test_rr1_a_live_capture_worker_keeps_the_gate_closed_until_it_ends(self):
        release = threading.Event()

        def capture(hwnd, result, verify):
            release.wait(30)
        with patch.object(lc, "CAPTURE_SECONDS", 0.2):
            receipt = self.look(windows=lambda pids: [(1, min(pids), "T")], settle=0.1, capture=capture)
        self.assertEqual(receipt["cleanup_state"], "pending")
        self.assertIn("ekran yakalama işlemi sürüyor", lc.unconfirmed())
        release.set()
        deadline = time.monotonic() + 5
        while lc.unconfirmed() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(lc.unconfirmed(), [], "released and read back: the gate opens")

    def test_rr1_an_unknown_tree_stays_unknown_after_its_root_is_gone(self):
        with patch.object(lc, "_members", return_value=None):
            receipt = self.look(windows=lambda pids: [], watch=0.5)
        self.assertEqual(receipt["cleanup_state"], "pending")
        time.sleep(0.3)
        self.assertIn("süreç ağacı okunamadı", lc.unconfirmed())

    def test_rr2_a_failing_cleanup_step_keeps_ownership_and_still_closes_the_job(self):
        with patch.object(lc, "_members", side_effect=RuntimeError("okuma hatası")):
            receipt = self.look(windows=lambda pids: [], watch=0.5)
        self.assertEqual((receipt["cleanup_state"], receipt["cleanup_error"]), ("pending", "RuntimeError"))
        self.assertTrue(lc.unconfirmed(), "ownership stays on record")
        time.sleep(1)
        self.assertFalse(any((p.info.get("cmdline") or [])[-1:] == [str(self.project / "main.py")]
                             for p in __import__("psutil").process_iter(["cmdline"])
                             if p.info.get("cmdline")), "the job was still closed: nothing of it runs")

    def test_rr1_a_query_during_the_look_never_prunes_it(self):
        # Fides's acceptance review: the root ends by itself while the capture still waits, and
        # another request asks the gate meanwhile.
        (self.project / "main.py").write_text("import time\ntime.sleep(0.8)\n", encoding="utf-8")
        release, during = threading.Event(), {}

        def capture(hwnd, result, verify):
            time.sleep(1.0)  # the root is gone by now
            during["guard"] = lc.unconfirmed()
            during["records"] = len(lc._UNCONFIRMED)
            release.wait(30)
        try:
            with patch.object(lc, "CAPTURE_SECONDS", 2.5):
                receipt = self.look(windows=lambda pids: [(1, min(pids), "T")], settle=0.1, capture=capture)
            self.assertEqual(during["records"], 1, "the running look stayed on record")
            self.assertIn("başka bir program gözlemi sürüyor", during["guard"])
            self.assertEqual(receipt["cleanup_state"], "pending")
            self.assertIn("ekran yakalama işlemi sürüyor", lc.unconfirmed())
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while lc.unconfirmed() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(lc.unconfirmed(), [])


class ReviewerFallbackTests(unittest.TestCase):
    """Live 26 Nov 17:13: Eos's review ended with no verdict and the milestone went "denetlenmedi"."""

    def review(self, replies, members):
        from tests.test_long_job_chat import FakeChat
        from core.long_job import JobLedger
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {"QUARTZ_JOBS_HOME": str(Path(directory) / "jobs")}), \
                patch("core.agent_limits.snapshot", return_value={}):
            project = Path(directory) / "p"
            project.mkdir()
            chat = FakeChat(project, replies=replies)
            ledger = JobLedger.create({"goal": "Oyun", "project_path": str(project), "hours": 1, "kind": "code",
                                       "conversation_id": "c1", "milestones": [{"title": "T", "acceptance": "ok"}]})
            with patch.object(chat, "_job_members", return_value=members):
                result = chat._job_accept(ledger, ledger.data["milestones"][0], members[0], {"ok": True},
                                          threading.Event())
        return result, [s["agent"] for s in chat.sent]

    def test_no_verdict_goes_to_the_next_teammate(self):
        result, asked = self.review([("completed", "İnceledim ama karar yazmadım.", "antigravity"),
                                     ("completed", "Baktım.\nKABUL: EVET", "claude")],
                                    ["codex", "antigravity", "claude"])
        self.assertEqual(asked, ["antigravity", "claude"])
        self.assertEqual((result["ok"], result["by"]), (True, "claude"))

    def test_a_no_ends_the_review_without_a_second_opinion(self):
        result, asked = self.review([("completed", "Eksik.\nKABUL: HAYIR — skor yok", "antigravity")],
                                    ["codex", "antigravity", "claude"])
        self.assertEqual(asked, ["antigravity"])
        self.assertIs(result["ok"], False)

    def test_at_most_two_reviewers_are_asked(self):
        result, asked = self.review([("completed", "karar yok", "antigravity"), ("completed", "yine yok", "claude")],
                                    ["codex", "antigravity", "claude", "claude"])
        self.assertEqual(len(asked), 2)
        self.assertIsNone(result["ok"])

    def test_a_program_without_a_window_is_not_reported_as_a_problem(self):
        from tests.test_long_job import Clock
        from core.long_job import JobLedger, finish_report
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "p").mkdir()
            ledger = JobLedger.create({"goal": "CLI", "project_path": str(Path(directory) / "p"), "hours": 1,
                                       "milestones": [{"title": "T", "acceptance": "ok"}]},
                                      root=Path(directory) / "jobs", clock=Clock())
            ledger.data["milestones"][0].update(status="done", launch={
                "verdict": "skipped", "reason": "pencere açan bir Python programı bulunamadı"})
            report = finish_report(ledger)
        self.assertIn("Pencereli bir program yok", report)
        self.assertNotIn("çalıştırılıp görülmedi", report)


if __name__ == "__main__":
    unittest.main()
