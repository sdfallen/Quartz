"""Time Capsule ("Zaman Kapsülü", 28 Nov 2026): plain-Turkish milestone rewind with backup refs."""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.job_intent import job_change, job_message_kind
from core.long_job import JobError, JobLedger, LongJob, git_commit, prepare_branch
from tests.test_long_job_chat import FakeChat


def nullctx():
    from contextlib import nullcontext
    return nullcontext()


class IntentTests(unittest.TestCase):
    def test_plain_turkish_rewind_phrases_and_notes_are_recognised(self):
        self.assertEqual(job_change("2. adıma geri dön"), ("rewind", {"target": 2, "note": ""}))
        self.assertEqual(job_change("1. adıma dön ve arayüzü koyu tema yap"),
                         ("rewind", {"target": 1, "note": "arayüzü koyu tema yap"}))
        self.assertEqual(job_change("Peki 2. kilometre taşına geri sar, butonları büyüt"),
                         ("rewind", {"target": 2, "note": "butonları büyüt"}))
        self.assertEqual(job_change("son adımı geri al"), ("rewind", {"target": "previous", "note": ""}))
        self.assertEqual(job_change("bir önceki adıma dön ve renkleri değiştir"),
                         ("rewind", {"target": "previous", "note": "renkleri değiştir"}))
        self.assertEqual(job_message_kind("2. adıma geri dön"), "rewind")

    def test_negated_question_and_descriptive_phrases_never_trigger_rewind(self):
        for text in (
            "2. adıma geri dönme",
            "son adımı geri alma",
            "2. adıma geri dönsek ne olur?",
            "2. adıma dönmek istemiyorum",
            "2. adıma geri dön, dur",
            "2. adıma döndüğünde, hata veriyor",
            "bir önceki adıma dönünce, form sıfırlanıyor",
            "2. adıma dönüştür ve kaydet",
            "1. aşamaya dönük testler, kontroller",
            "son adımı geri aldığında, ekran bozuluyor",
        ):
            with self.subTest(text=text):
                self.assertIsNone(job_change(text))
                self.assertNotEqual(job_message_kind(text), "rewind")


class GitTimeCapsuleTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.project), *args], capture_output=True, text=True, check=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "app"
        self.project.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "Test")
        (self.project / "README.md").write_text("başlangıç\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        # User's own untracked file that must never be touched by a rewind!
        (self.project / "kullanici_notu.txt").write_text("özel taslak\n", encoding="utf-8")

    def make_three_step_job(self):
        ledger = JobLedger.create({
            "goal": "Üç adımlı uygulama",
            "project_path": str(self.project),
            "conversation_id": "c1",
            "hours": 1,
            "git_branch": "spes/test-kapsul",
            "milestones": [
                {"title": "İskelet", "acceptance": "app.py var"},
                {"title": "Arayüz", "acceptance": "ui.py var"},
                {"title": "Tema", "acceptance": "tema uygulandı"},
            ],
        }, root=self.root / "jobs")

        def writer_run(l, m, w, s):
            if m["id"] == "m1":
                (self.project / "app.py").write_text("v = 1\n", encoding="utf-8")
            elif m["id"] == "m2":
                (self.project / "app.py").write_text("v = 2\n", encoding="utf-8")
                (self.project / "ui.py").write_text("theme = 'light'\n", encoding="utf-8")
            elif m["id"] == "m3":
                note_texts = " ".join(d["text"] for d in l.data["decisions"])
                theme = "dark" if "koyu tema" in note_texts else "neon"
                (self.project / "ui.py").write_text(f"theme = '{theme}'\n", encoding="utf-8")
                (self.project / "extra_m3.py").write_text("extra = True\n", encoding="utf-8")
            return {"status": "completed"}

        job = LongJob(
            ledger,
            run_milestone=writer_run,
            verify=lambda stop: {"ok": True, "summary": "ok"},
            checkpoint=lambda: {"status": "git-head", "ref": "x"},
            baseline=lambda: {"status": "snapshot", "ref": "b"},
            awake=nullctx,
        )
        return job, ledger

    def test_rewind_to_step_preserves_user_files_creates_backup_ref_and_reruns_with_new_note(self):
        job, ledger = self.make_three_step_job()
        job.run()
        self.assertEqual(ledger.data["status"], "done")
        self.assertTrue((self.project / "extra_m3.py").is_file())
        self.assertEqual((self.project / "ui.py").read_text(encoding="utf-8"), "theme = 'neon'\n")
        m3_sha = ledger.data["milestones"][2]["commit"]

        # Rewind back to step 2 with a new instruction!
        info = job.rewind_milestone(2, note="koyu tema kullan")
        self.assertEqual(info["to_step"], 2)
        self.assertFalse((self.project / "extra_m3.py").exists(), "m3's added file is cleanly removed")
        self.assertEqual((self.project / "ui.py").read_text(encoding="utf-8"), "theme = 'light'\n")
        self.assertEqual((self.project / "kullanici_notu.txt").read_text(encoding="utf-8"), "özel taslak\n")
        # Backup ref preserves the rewound m3 commit in Git!
        saved_sha = self.git("rev-parse", info["backup_ref"]).stdout.strip()
        self.assertEqual(saved_sha, m3_sha)
        self.assertEqual(ledger.data["milestones"][2]["status"], "pending")

        # Running again executes only m3, now applying the new note!
        # Also create a NEW untracked user file AFTER job completion before rewinding: it must NOT be
        # swept into m3's commit or deleted on a subsequent rewind!
        late_note = self.project / "sonradan_eklenen_not.txt"
        late_note.write_text("kullanıcının sonradan yazdığı özel dosya\n", encoding="utf-8")
        # Refresh initial_dirty via rewind already happened before late_note; test rewinding AFTER late_note exists:
        job.run()
        self.assertEqual(ledger.data["status"], "done")
        self.assertEqual((self.project / "ui.py").read_text(encoding="utf-8"), "theme = 'dark'\n")

        late_note2 = self.project / "ikinci_ozel_dosya.txt"
        late_note2.write_text("bu dosya asla silinmemeli\n", encoding="utf-8")
        job.rewind_milestone(2, note="koyu tema kullan")
        job.run()
        # Neither m3's commit nor a second rewind may touch ikinci_ozel_dosya.txt!
        committed_files = self.git("show", "--name-only", "--pretty=format:", "HEAD").stdout.splitlines()
        self.assertNotIn("ikinci_ozel_dosya.txt", committed_files)
        job.rewind_milestone(2)
        self.assertTrue(late_note2.is_file(), "User file added before rewind must never be deleted!")
        self.assertEqual(late_note2.read_text(encoding="utf-8"), "bu dosya asla silinmemeli\n")

        # Post-job manual commits made outside the job are protected against accidental rewind!
        job.run()
        (self.project / "manual.py").write_text("user_work = 1\n", encoding="utf-8")
        self.git("add", "manual.py")
        self.git("commit", "-qm", "manual user commit")
        with self.assertRaises(JobError) as manual_ctx:
            job.rewind_milestone(2)
        self.assertIn("yeni Git kayıtları", str(manual_ctx.exception))

    def test_undo_first_step_returns_to_base_git_head_and_dirty_conflict_is_refused(self):
        job, ledger = self.make_three_step_job()
        job.run()
        # Uncommitted manual edit to a milestone-touched file blocks rewind rather than losing user edits!
        (self.project / "ui.py").write_text("elle degistirildi\n", encoding="utf-8")
        with self.assertRaises(JobError) as ctx:
            job.rewind_milestone(1)
        self.assertIn("kaydedilmemiş değişiklik", str(ctx.exception))
        # Restore clean working tree and rewind to step 1, then undo step 1 ("previous") to base_git_head!
        self.git("checkout", "--", "ui.py")
        job.rewind_milestone(1)
        self.assertFalse((self.project / "ui.py").exists())
        self.assertTrue((self.project / "app.py").is_file())
        info0 = job.rewind_milestone("previous")
        self.assertEqual(info0["to_step"], 0)
        self.assertFalse((self.project / "app.py").exists())
        self.assertEqual((self.project / "kullanici_notu.txt").read_text(encoding="utf-8"), "özel taslak\n")

    def test_conversation_rewind_after_completion_and_project_mismatch_guard(self):
        with patch.dict(os.environ, {"QUARTZ_JOBS_HOME": str(self.root / "jobs")}), \
                patch("core.long_job.baseline_checkpoint", return_value={"status": "snapshot", "ref": "b"}), \
                patch("core.agent_limits.snapshot", return_value={}):
            job, ledger = self.make_three_step_job()
            job.run()
            chat = FakeChat(self.project, replies=[("completed", "Koyu tema yapıldı.", "claude")])
            # Different project on conversation refuses rewind (Fides F2).
            other = self.root / "other"
            other.mkdir()
            wrong_chat = FakeChat(other, replies=[])
            res_wrong = wrong_chat._rewind_conversation_job(wrong_chat.store.conv, "2. adıma geri dön")
            self.assertIn("farklı", res_wrong["assistant_message"]["content"])

            # Matching project rewinds and restarts step 3 automatically!
            res_ok = chat._rewind_conversation_job(chat.store.conv, "2. adıma geri dön ve koyu tema yap")
            self.assertIn("Zaman kapsülü", res_ok["assistant_message"]["content"])
            for _ in range(200):
                st = chat._jobs()[ledger.data["id"]].ledger.data["status"]
                if st == "done":
                    t = chat._jobs()[ledger.data["id"]].thread
                    if t is not None:
                        t.join(5)
                    break
                time.sleep(0.02)
            self.assertEqual(chat._jobs()[ledger.data["id"]].ledger.data["status"], "done")
            self.assertEqual(len(chat.sent), 1)
            self.assertIn("koyu tema yap", chat.sent[0]["text"])


if __name__ == "__main__":
    unittest.main()
