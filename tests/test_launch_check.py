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

    def run_script(self, text, stop=None, **kwargs):
        entry = self.project / "main.py"
        entry.write_text(text, encoding="utf-8")
        return lc.observe(entry, self.project, self.root / "kanit" / "m1-deneme1", stop or threading.Event(),
                          sys.executable, **kwargs)

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
        def capture(hwnd, out, result):
            out.write_bytes(b"png")
            result.update(state="captured")
        receipt = self.run_script("import time\ntime.sleep(30)\n",
                                  windows=lambda pids: [(1234, min(pids), "Yılan Oyunu")],
                                  settle=0.2, capture=capture)
        self.assertEqual(lc.verdict(receipt), "window_seen")
        self.assertEqual((receipt["window_title"], receipt["capture_state"]), ("Yılan Oyunu", "captured"))
        self.assertTrue(Path(receipt["screenshot"]).is_file())
        self.assertEqual(receipt["termination_reason"], "closed_by_spes")
        self.assertEqual(receipt["cleanup_state"], "confirmed")
        self.assertIn("etkileşim denenmedi", lc.evidence_text(receipt))

    def test_a_hung_capture_does_not_hold_the_look(self):
        def capture(hwnd, out, result):
            time.sleep(5)
        began = time.monotonic()
        with patch.object(lc, "CAPTURE_SECONDS", 0.3):
            receipt = self.run_script("import time\ntime.sleep(30)\n",
                                      windows=lambda pids: [(1, min(pids), "T")], settle=0.1,
                                      capture=lambda h, o, r: capture(h, o, r))
        self.assertLess(time.monotonic() - began, 10, "well under the 5 s hang plus the 30 s program")
        self.assertEqual(receipt["capture_state"], "timeout")
        self.assertEqual(receipt["cleanup_state"], "confirmed")

    def test_stop_cancels_the_look_and_closes_the_program(self):
        stop = threading.Event()
        threading.Timer(0.5, stop.set).start()
        receipt = self.run_script("import time\ntime.sleep(30)\n", stop=stop, windows=lambda pids: [])
        self.assertEqual(lc.verdict(receipt), "cancelled")
        self.assertEqual(receipt["cleanup_state"], "confirmed")

    def test_a_program_that_cannot_be_owned_never_runs(self):
        marker = self.root / "calisti.txt"
        with patch("core.process_tree.bind_kill_on_close_job", return_value=False):
            receipt = self.run_script(f"open(r'{marker}', 'w').write('x')\n", windows=lambda pids: [])
        self.assertEqual(lc.verdict(receipt), "blocked")
        self.assertEqual(receipt["termination_reason"], "job_object_unavailable")
        time.sleep(0.5)
        self.assertFalse(marker.exists(), "the suspended program was never resumed")

    def test_two_attempts_keep_their_own_evidence(self):
        first = self.run_script("raise SystemExit(2)\n", windows=lambda pids: [])
        entry = self.project / "main.py"
        second = lc.observe(entry, self.project, self.root / "kanit" / "m1-deneme2", threading.Event(),
                            sys.executable, windows=lambda pids: [])
        self.assertNotEqual(first["evidence_dir"], second["evidence_dir"])
        self.assertTrue((Path(first["evidence_dir"]) / "receipt.json").is_file())


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


if __name__ == "__main__":
    unittest.main()


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
                    "screenshot": str(Path(evidence) / "window.png"), "evidence_dir": evidence}
            fatum = self.review("claude", look)
            fides = self.review("codex", look)
        self.assertEqual(fatum["read_root"], evidence)
        self.assertIn("window.png", fatum["text"])
        self.assertIsNone(fides["read_root"])
        self.assertIn("görsel incelendi deme", fides["text"])
        self.assertIn("SPES ÇALIŞTIRMA DENETİMİ", fides["text"])
