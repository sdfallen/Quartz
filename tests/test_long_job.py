import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from core.long_job import (JobError, JobLedger, LongJob, MAX_ATTEMPTS, MAX_CRASHES, git_commit, milestone_prompt,
                           prepare_branch, resumable)


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def nullctx():
    from contextlib import nullcontext
    return nullcontext()


class LongJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "game"
        self.project.mkdir()
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def spec(self, **extra):
        return {"goal": "Animasyonlar", "project_path": str(self.project), "hours": 2,
                "milestones": [{"title": "Yürüme", "acceptance": "8 yön"},
                               {"title": "Koşma", "acceptance": "8 yön"}], **extra}

    def job(self, run, *, limits=None, verify=None, ledger=None, notes=None, **spec):
        ledger = ledger or JobLedger.create(self.spec(**spec), root=self.root / "jobs", clock=self.clock)
        notes = notes if notes is not None else []
        job = LongJob(ledger, run_milestone=run, verify=verify or (lambda stop: {"ok": True, "summary": "ok"}),
                      checkpoint=lambda: {"status": "snapshot", "ref": "cp"},
                      snapshot=lambda: {"files": {}}, changed=lambda a, b: [], commit=lambda f, m: None,
                      limits=limits or (lambda: {}), notify=lambda t, urgent=False: notes.append(t),
                      clock=self.clock, awake=nullctx)
        return job, ledger, notes

    def test_spec_needs_goal_milestones_and_bounded_hours(self):
        with self.assertRaises(JobError):
            JobLedger.create(self.spec(goal=""), root=self.root)
        with self.assertRaises(JobError):
            JobLedger.create(self.spec(milestones=[{"title": "x"}]), root=self.root)
        with self.assertRaises(JobError):
            JobLedger.create(self.spec(hours=30), root=self.root)
        with self.assertRaises(JobError):
            JobLedger.create(self.spec(git_branch="../main"), root=self.root)

    def test_all_milestones_run_in_order_and_the_ledger_is_durable(self):
        seen = []
        job, ledger, notes = self.job(lambda l, m, w, s: seen.append((m["id"], w)) or {"status": "completed"})
        job.run()
        self.assertEqual(seen, [("m1", "claude"), ("m2", "claude")])
        again = JobLedger.load(ledger.path)
        self.assertEqual(again.data["status"], "done")
        self.assertEqual([m["status"] for m in again.data["milestones"]], ["done", "done"])
        self.assertIn("bütün kilometre taşları tamam", notes[-1])

    def test_failed_check_retries_then_asks_the_user_and_moves_on(self):
        runs = []

        def run(l, m, w, s):
            runs.append(m["id"])
            return {"status": "completed"}

        verify = lambda stop: {"ok": runs[-1] == "m2", "summary": "test kırık"}
        job, ledger, notes = self.job(run, verify=verify)
        job.run()
        self.assertEqual(runs, ["m1"] * MAX_ATTEMPTS + ["m2"])
        self.assertEqual(ledger.data["milestones"][0]["status"], "needs_user")
        self.assertEqual(ledger.data["status"], "needs_user")
        prompt = milestone_prompt(ledger, ledger.data["milestones"][0], "claude")
        self.assertIn("test kırık", prompt)

    def test_limit_moves_the_writer_role_and_records_the_decision(self):
        calls = []

        def run(l, m, w, s):
            calls.append(w)
            return {"limit": "claude"} if w == "claude" else {"status": "completed"}

        job, ledger, notes = self.job(run)
        job.run()
        self.assertEqual(calls, ["claude", "codex", "codex"])
        self.assertEqual(ledger.data["milestones"][0]["attempts"], 1)  # the limit was not an attempt
        self.assertTrue(any("Fatum → Fides" in d["text"] for d in ledger.data["decisions"]))

    def test_writer_returns_to_fatum_after_its_limit_resets(self):
        calls = []
        limits = {"claude": {"state": "full", "resets_at": self.clock.now + 60}}

        def run(l, m, w, s):
            calls.append(w)
            self.clock.now += 120  # the first milestone outlives Fatum's limit
            return {"status": "completed"}

        job, ledger, _ = self.job(run, limits=lambda: limits if self.clock.now < limits["claude"]["resets_at"] else {})
        job.run()
        self.assertEqual(calls, ["codex", "claude"])

    def test_all_three_limited_waits_until_the_earliest_reset(self):
        resets = {"claude": 500, "codex": 200, "antigravity": 900}
        snapshot = {a: {"state": "full", "resets_at": self.clock.now + s} for a, s in resets.items()}
        job, ledger, notes = self.job(lambda l, m, w, s: {"status": "completed"},
                                      limits=lambda: snapshot if self.clock.now < 1_000_000 + 200 else {})
        waited = []
        job._wait = lambda seconds: (waited.append(seconds), setattr(self.clock, "now", self.clock.now + seconds))
        job.run()
        self.assertEqual(waited[0], 200)
        self.assertTrue(any("limit nedeniyle bekliyor" in n for n in notes))
        self.assertEqual(ledger.data["status"], "done")

    def test_stop_is_final_and_never_resumes(self):
        job, ledger, _ = self.job(lambda l, m, w, s: (job.stop(), {"status": "completed"})[1], auto_resume=True)
        job.run()
        self.assertEqual(ledger.data["status"], "stopped")
        self.assertTrue(ledger.data["stopped"])
        self.assertEqual(resumable(JobLedger.load(ledger.path), self.clock.now), "")
        with self.assertRaises(JobError):
            job.resume()

    def test_deadline_ends_the_job(self):
        def run(l, m, w, s):
            self.clock.now += 3 * 3600
            return {"status": "completed"}
        job, ledger, _ = self.job(run)
        job.run()
        self.assertEqual(ledger.data["status"], "expired")
        self.assertEqual(ledger.data["milestones"][1]["status"], "pending")

    def test_crash_recovery_follows_the_users_rules(self):
        ledger = JobLedger.create(self.spec(auto_resume=True), root=self.root / "jobs", clock=self.clock)
        ledger.data["status"] = "running"
        ledger.data["milestones"][0].update(status="running", attempts=1)
        ledger.save()
        self.assertEqual(resumable(ledger, self.clock.now), "resume")
        self.assertEqual(resumable(ledger, ledger.data["deadline"] + 1), "")  # expired: no resume
        ledger.data["auto_resume"] = False
        self.assertEqual(resumable(ledger, self.clock.now), "pause")
        ledger.data["auto_resume"] = True
        job, _, _ = self.job(lambda *a: {"status": "completed"}, ledger=ledger)
        for n in range(1, MAX_CRASHES):
            ledger.data["milestones"][0]["status"] = "running"
            self.assertEqual(job.recover_after_crash(), "resume")
        ledger.data["milestones"][0]["status"] = "running"
        self.assertEqual(job.recover_after_crash(), "pause")
        self.assertEqual(ledger.data["status"], "paused")
        self.assertIn("yarıda kaldı", milestone_prompt(ledger, ledger.data["milestones"][0], "claude"))

    def test_pause_then_resume_continues(self):
        job, ledger, _ = self.job(lambda l, m, w, s: {"status": "completed"})
        job.pause()
        thread = threading.Thread(target=job.run)
        thread.start()
        for _ in range(100):
            if ledger.data["status"] == "paused":
                break
            threading.Event().wait(0.02)
        self.assertEqual(ledger.data["status"], "paused")
        job.resume()
        thread.join(5)
        self.assertEqual(ledger.data["status"], "done")


class GitTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.project), *args], capture_output=True, text=True, check=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "game"
        self.project.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "Test")
        (self.project / ".gitignore").write_text(".godot/\n")
        (self.project / "a.gd").write_text("a\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        (self.project / "user_draft.txt").write_text("kullanıcının kaydedilmemiş dosyası\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_commits_only_milestone_files_on_the_job_branch(self):
        ledger = JobLedger.create({"goal": "g", "project_path": str(self.project), "hours": 1,
                                   "git_branch": "spes/deneme", "milestones": [{"title": "t", "acceptance": "a"}]},
                                  root=Path(self.tmp.name) / "jobs")
        prepare_branch(ledger)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "spes/deneme")
        (self.project / "walk.gd").write_text("walk\n")
        (self.project / ".godot").mkdir()
        (self.project / ".godot" / "cache.bin").write_text("x")
        sha = git_commit(ledger, [str(self.project / "walk.gd"), str(self.project / ".godot" / "cache.bin")], "m1")
        self.assertTrue(sha)
        files = self.git("show", "--name-only", "--format=", "HEAD").stdout.split()
        self.assertEqual(files, ["walk.gd"])
        status = self.git("status", "--porcelain").stdout
        self.assertIn("?? user_draft.txt", status)  # the user's file is untouched and uncommitted


if __name__ == "__main__":
    unittest.main()
