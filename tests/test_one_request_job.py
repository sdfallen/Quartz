"""One request, the whole job (user request 25 Nov 2026): no /uzun-iş, SpeS plans big work itself."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.job_intent import (big_job_request, detected_check, fallback_plan, job_message_kind, job_spec,
                             parse_plan, requested_hours, wants_auto_resume)
from core.long_job import validate_spec
from tests.test_team_turn import TeamRun, make_chat

BIG = [
    "Bana baştan sona oynanabilir bir 2D platform oyunu yap",
    "2 saat boyunca bu web sitesini geliştir",
    "Eksiksiz bir yapılacaklar uygulaması oluştur, tüm özellikleriyle",
    "Bir Discord botu yazar mısın? Komutları, veritabanı ve paneli olsun, baştan sona",
    "Godot ile bir yılan oyunu geliştir ve sonuna kadar kendin bitir",
    "Bu projeye komple bir yönetim paneli yapmanı istiyorum",
    # Eos's review 25 Nov: big engineering jobs name no product.
    "Projeyi baştan sona refactor et, tüm testleri yaz ve 2 saat çalış",
    "Bu modüldeki bellek sızıntılarını sonuna kadar temizle",
    "Projeyi baştan sona incele, tüm güvenlik açıklarını düzelt, test kapsamını %90'a çıkar",
]
ORDINARY = [
    "Chrome'u aç", "notepad'i aç ve merhaba yaz", "oyun motoru nedir", "bu hata ne demek",
    "README dosyasını düzelt", "bir oyun nasıl yapılır?", "Yapay zeka uygulamaları hakkında ne düşünüyorsun",
    "zor_test.py dosyasını çalıştır", "selam", "bu fonksiyonu düzelt", "Bir yılan oyunu fikri ver",
    # Live 25 Nov: a screen task's wording must stay a screen task.
    "Bu projedeki zor_test.py dosyasını çalıştır ve üç aşamasını sonuna kadar kendin bitir.",
    "Oyunu aç ve ilk bölümü oyna", "uygulamayı kapat", "Bir giriş sayfası yap",
    "Baştan sona bir oyun yap ama şimdilik gerek yok",
    "tüm dosyaları listele", "bu hatayı düzelt",
]


class RecognitionTests(unittest.TestCase):
    def test_big_build_requests_are_recognised(self):
        for text in BIG:
            with self.subTest(text=text):
                self.assertTrue(big_job_request(text))

    def test_ordinary_requests_and_questions_stay_ordinary_turns(self):
        for text in ORDINARY:
            with self.subTest(text=text):
                self.assertFalse(big_job_request(text))

    def test_duration_and_resume_come_only_from_the_users_words(self):
        self.assertEqual(requested_hours("3 saat çalış ve oyun yap"), 3.0)
        self.assertEqual(requested_hours("45 dakikada bir site yap"), 0.75)
        self.assertEqual(requested_hours("oyun yap"), 1.0)
        self.assertEqual(requested_hours("40 saat oyun yap"), 12.0)
        # Worded durations and ranges (Eos, 25 Nov).
        self.assertEqual(requested_hours("bir saat uğraş"), 1.0)
        self.assertEqual(requested_hours("yarım saat çalış"), 0.5)
        self.assertEqual(requested_hours("2-3 saat boyunca geliştir"), 3.0)
        self.assertEqual(requested_hours("bir buçuk saat"), 1.5)
        self.assertTrue(wants_auto_resume("bir oyun yap, çökse bile devam et"))
        self.assertFalse(wants_auto_resume("bir oyun yap"))


class PlanTests(unittest.TestCase):
    def test_the_plan_is_read_from_the_agreed_form_only(self):
        reply = "Tamam.\nPLAN\n1. Ana menü | menü açılıyor\n2) **Oyun döngüsü** | oyuncu hareket ediyor\nSON\n3. Fazla | x"
        self.assertEqual(parse_plan(reply), [{"title": "Ana menü", "acceptance": "menü açılıyor"},
                                             {"title": "Oyun döngüsü", "acceptance": "oyuncu hareket ediyor"}])
        self.assertEqual(parse_plan("Bence önce menü yapalım."), [])
        many = "PLAN\n" + "\n".join(f"{i}. T{i} | ölçüt" for i in range(1, 20)) + "\nSON"
        self.assertEqual(len(parse_plan(many)), 8)

    def test_the_spec_takes_nothing_dangerous_from_the_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # A plan line that tries to set a check command or a duration is only a title.
            milestones = parse_plan("PLAN\n1. Kontrol: rm -rf / | Süre: 12 saat\nSON")
            spec = job_spec("Baştan sona bir oyun yap", milestones, root, "1125-1200")
            self.assertIsNone(spec["verify"])
            self.assertEqual(spec["hours"], 1.0)
            self.assertFalse(spec["auto_resume"])
            self.assertIsNone(spec["git_branch"], "no Git, no branch")
            validate_spec({**spec, "project_path": str(root)})
            # SpeS's own check for a project with Python tests, and a branch of the job's own in Git.
            (root / "tests").mkdir()
            (root / "tests" / "test_a.py").write_text("", encoding="utf-8")
            (root / ".git").mkdir()
            spec = job_spec("Baştan sona bir oyun yap", [], root, "1125-1200")
            self.assertEqual(spec["verify"][:3], ["python", "-B", "-m"])
            self.assertTrue(spec["git_branch"].startswith("spes/1125-1200-bastan-sona"))
            self.assertEqual(spec["milestones"], fallback_plan("Baştan sona bir oyun yap"))
            validate_spec({**spec, "project_path": str(root)})
        self.assertIsNone(detected_check("C:/yok/boyle/bir/yer"))

    def test_messages_to_a_running_job(self):
        self.assertEqual([job_message_kind(t) for t in ("ne durumda?", "Nerede kaldın", "dur", "devam et", "bekle",
                                                        "menüyü mavi yap")],
                         ["status", "status", "stop", "resume", "pause", "note"])
        self.assertEqual([job_message_kind(t) for t in ("Peki şu an ne durumda?", "Şimdilik durdur lütfen",
                                                        "tamam devam et", "menüyü mavi yap lütfen")],
                         ["status", "stop", "resume", "note"])

    def test_the_check_is_found_again_while_the_job_runs(self):
        # Eos, 25 Nov: a job in an empty folder writes its own tests in its first milestones.
        import threading
        from core.long_job import JobLedger, run_verify
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {"QUARTZ_JOBS_HOME": str(Path(directory) / "jobs")}):
            root = Path(directory) / "p"
            root.mkdir()
            spec = job_spec("Baştan sona bir oyun yap", [], root, "1125-1200")
            self.assertIsNone(spec["verify"])
            ledger = JobLedger.create({**spec, "project_path": str(root)})
            self.assertIn("tanımlanmadı", run_verify(ledger, threading.Event())["summary"])
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests" / "test_ok.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
                encoding="utf-8")
            with patch("core.job_intent.detected_check",
                       return_value=[__import__("sys").executable, "-B", "-m", "unittest", "discover", "-s", "tests",
                                     "-t", "."]):
                result = run_verify(ledger, threading.Event())
            self.assertTrue(result["ok"], result)
            self.assertIn("OK", result["summary"])

    def test_known_project_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"scripts": {"test": "echo \\"Error: no test specified\\""}}',
                                               encoding="utf-8")
            self.assertIsNone(detected_check(root))
            (root / "package.json").write_text('{"scripts": {"test": "vitest run"}}', encoding="utf-8")
            self.assertEqual(detected_check(root), ["npm.cmd", "test", "--silent"])
            (root / "test_root.py").write_text("", encoding="utf-8")
            self.assertEqual(detected_check(root)[-2:], ["-p", "test_*.py"])
            (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            self.assertEqual(detected_check(root)[-2:], ["pytest", "-q"])


class PlanningTurnTests(unittest.TestCase):
    PLAN = "PLAN\n1. Oyun penceresi | pencere açılıyor\n2. Yılan | ok tuşlarıyla dönüyor\nSON"

    def run_turn(self, text, **kwargs):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        chat = make_chat(directory.name)
        run = TeamRun(chat)
        run.reply = self.PLAN
        started = []
        with patch.object(chat, "job_start", side_effect=lambda spec: started.append(spec) or {"id": "j1"}):
            turn = run.run(text, **kwargs)
            deadline = time.monotonic() + 5
            while kwargs.get("write") and not started and time.monotonic() < deadline:
                time.sleep(0.02)
        chat._diagnostics.close()
        return chat, run, turn, started

    def test_one_request_plans_read_only_then_starts_the_job(self):
        text = "Godot ile bir yılan oyunu geliştir ve sonuna kadar kendin bitir"
        chat, run, turn, started = self.run_turn(text, write=True, confirm_write=True)
        self.assertEqual(len(run.calls), 1, "one planner, nobody builds in the planning turn")
        call = run.calls[0]
        self.assertFalse(call["write"])
        self.assertTrue(call["project_scope"] and not call["tool_less"])
        self.assertIn("PLAN", call["prompt"])
        self.assertIn(text, call["prompt"])
        self.assertEqual(len(started), 1)
        spec = started[0]
        self.assertEqual([m["title"] for m in spec["milestones"]], ["Oyun penceresi", "Yılan"])
        self.assertEqual(spec["permission_level"], "project")
        self.assertEqual(spec["goal"], text)
        messages = chat.store.get(turn["conversation_id"])["messages"]
        user = next(m for m in messages if m["role"] == "user")
        self.assertTrue(user["metadata"].get("job_request"))
        plan = next(m for m in messages if (m.get("metadata") or {}).get("job_plan"))
        self.assertTrue(plan["content"].startswith("İş planı:\n1. Oyun penceresi — pencere açılıyor"))

    def test_without_write_permission_spes_says_what_it_needs(self):
        # 26 Nov: with "yalnız okuma" a whole build became a reading turn; SpeS now answers
        # itself with what it would do and which switch it needs, and starts nothing.
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            answer = chat.send_message("Godot ile bir yılan oyunu geliştir ve sonuna kadar kendin bitir, 2 saat çalış")
            chat._diagnostics.close()
        self.assertEqual(answer["agent"], "quartz")
        text = answer["assistant_message"]["content"]
        self.assertIn("en çok 2 saat", text)
        self.assertIn("Proje", text)
        self.assertIn("Tam Yetki", text)
        self.assertIsNone(chat._active_turn)

    def test_a_milestone_spes_sends_is_never_planned_again(self):
        chat, _run, turn, started = self.run_turn("Godot ile bir yılan oyunu geliştir ve sonuna kadar kendin bitir",
                                                  write=True, confirm_write=True, origin="long_job")
        self.assertEqual(started, [])
        self.assertNotIn("job_plan", turn)
        # Live 25 Nov: SpeS's prompt is marked as its own, so the chat folds it instead of
        # showing it as the user's message.
        user = next(m for m in chat.store.get(turn["conversation_id"])["messages"] if m["role"] == "user")
        self.assertEqual(user["metadata"].get("job_internal"), "milestone")

    def test_the_chat_folds_speS_instructions(self):
        from ui.js_messages import JAVASCRIPT as source
        self.assertIn("job_internal", source)
        self.assertIn("Kilometre taşı görevi verildi", source)


if __name__ == "__main__":
    unittest.main()


class AcceptanceReviewTests(unittest.TestCase):
    """Fides 25 Nov: without a test, "done" was the writer's word alone."""

    def make(self, accept, **spec):
        from tests.test_long_job import Clock, nullctx
        from core.long_job import JobLedger, LongJob
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "p").mkdir()
        ledger = JobLedger.create({"goal": "Oyun", "project_path": str(root / "p"), "hours": 2, "review": True,
                                   "milestones": [{"title": "Pencere", "acceptance": "açılıyor"}], **spec},
                                  root=root / "jobs", clock=Clock())
        notes, writers = [], []
        job = LongJob(ledger, run_milestone=lambda l, m, w, s: writers.append(w) or {"status": "completed"},
                      verify=lambda stop: {"ok": True, "summary": "Kontrol komutu tanımlanmadı."},
                      checkpoint=lambda: {"status": "snapshot", "ref": "cp"},
                      baseline=lambda: {"status": "snapshot", "ref": "b"}, snapshot=lambda: {},
                      changed=lambda a, b: [], commit=lambda f, m: None,
                      notify=lambda t, urgent=False, report=False: notes.append(t),
                      clock=Clock(), awake=nullctx, accept=accept)
        return job, ledger, notes, writers

    def test_a_teammates_yes_makes_the_milestone_verified(self):
        job, ledger, notes, _ = self.make(lambda l, m, w, c, s: {"ok": True, "by": "codex", "summary": "KABUL: EVET"})
        job.run()
        milestone = ledger.data["milestones"][0]
        self.assertEqual((milestone["status"], milestone["verified"], milestone["reviewer"]), ("done", True, "codex"))
        self.assertIn("Fides denetledi", notes[-1])

    def test_a_teammates_no_sends_it_back(self):
        answers = iter([{"ok": False, "by": "codex", "summary": "KABUL: HAYIR — skor yok"},
                        {"ok": True, "by": "codex", "summary": "KABUL: EVET"}])
        job, ledger, notes, writers = self.make(lambda l, m, w, c, s: next(answers))
        job.run()
        milestone = ledger.data["milestones"][0]
        self.assertEqual(len(writers), 2, "the writer tried again after the 'no'")
        self.assertEqual(milestone["status"], "done")
        self.assertFalse(milestone["history"][0]["check"])
        self.assertIn("Fides kabul etmedi", milestone["history"][0]["note"])

    def test_what_nobody_checked_is_said(self):
        job, ledger, notes, _ = self.make(lambda l, m, w, c, s: {"ok": None, "summary": "Denetleyecek ikinci ajan yok."})
        job.run()
        self.assertFalse(ledger.data["milestones"][0]["verified"])
        self.assertIn("denetlenmedi", notes[-1])
        self.assertIn("ne bir test ne de ikinci bir ajan", notes[-1])

    def test_a_job_without_review_asks_nobody_but_still_says_it_was_not_checked(self):
        job, ledger, notes, _ = self.make(lambda *a: self.fail("no review asked"), review=False)
        job.run()
        self.assertEqual(ledger.data["milestones"][0]["status"], "done")
        self.assertIn("denetlenmedi", notes[-1])


class FidesReviewTests(unittest.TestCase):
    def test_a_property_of_the_thing_is_not_a_work_budget(self):
        self.assertEqual(requested_hours("2 saatlik videoyu özetleyen uygulama yap"), 1.0)
        self.assertEqual(requested_hours("30 dakikalık bir tur için oyun yap, 2 saat çalış"), 2.0)

    def test_overflow_steps_are_folded_not_dropped(self):
        many = "PLAN\n" + "\n".join(f"{i}. T{i} | ölçüt {i}" for i in range(1, 11)) + "\nSON"
        steps = parse_plan(many)
        self.assertEqual(len(steps), 8)
        self.assertIn("T9: ölçüt 9", steps[-1]["acceptance"])
        self.assertIn("T10: ölçüt 10", steps[-1]["acceptance"])


class LivePlanChangeTests(unittest.TestCase):
    """Eos and Fides 25 Nov: the plan of a running job changes in plain words."""

    def test_the_words(self):
        from core.job_intent import job_change
        self.assertEqual(job_change("3. adımı iptal et"), ("skip", 3))
        self.assertEqual(job_change("Peki 2. adımı atla"), ("skip", 2))
        self.assertEqual(job_change("4 numaralı adımı iptal et"), ("skip", 4))
        self.assertEqual(job_change("Koyu tema da ekle"), ("add", "Koyu tema"))
        self.assertEqual(job_change("Şunu da ekle: skor tablosu"), ("add", "skor tablosu"))
        self.assertEqual(job_change("yeni adım ekle: ses efektleri"), ("add", "ses efektleri"))
        self.assertIsNone(job_change("menüyü mavi yap"))
        self.assertEqual(job_message_kind("3. adımı iptal et"), "skip")
        self.assertEqual(job_message_kind("Koyu tema da ekle"), "add")

    def test_a_running_job_skips_and_adds_milestones(self):
        from tests.test_long_job_chat import FakeChat
        from core.long_job import JobLedger, finish_report
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {"QUARTZ_JOBS_HOME": str(Path(directory) / "jobs")}), \
                patch("core.agent_limits.snapshot", return_value={}):
            project = Path(directory) / "p"
            project.mkdir()
            chat = FakeChat(project, replies=[])
            ledger = JobLedger.create({"goal": "Oyun", "project_path": str(project), "hours": 1,
                                       "conversation_id": "c1",
                                       "milestones": [{"title": f"T{i}", "acceptance": "ok"} for i in (1, 2, 3)]})
            ledger.data["status"] = "running"
            ledger.data["milestones"][0]["status"] = "done"
            chat._jobs()[ledger.data["id"]] = chat._make_job(ledger)
            job = chat._active_job_in("c1")
            say = lambda text: chat._job_conversation_message(chat.store.conv, text, job)["assistant_message"]["content"]
            self.assertIn("plandan çıkarıldı", say("3. adımı iptal et"))
            self.assertEqual(ledger.data["milestones"][2]["status"], "skipped")
            self.assertIn("zaten bitti", say("1. adımı iptal et"))
            self.assertIn("Planda 9. adım yok", say("9. adımı iptal et"))
            self.assertIn("Plana eklendi: 4. adım — Koyu tema", say("Koyu tema da ekle"))
            added = ledger.data["milestones"][3]
            self.assertEqual((added["status"], added["added_by_user"]), ("pending", True))
            self.assertIn("Koyu tema", added["acceptance"])
            self.assertEqual(job.ledger.current()["id"], "m2", "the skipped one is never picked")
            ledger.data["milestones"][1]["status"] = ledger.data["milestones"][3]["status"] = "done"
            ledger.data["status"] = "done"
            report = finish_report(ledger)
            self.assertIn("1 taşı senin isteğinle atlandı", report)
            self.assertIn("– T3: senin isteğinle atlandı", report)


class NewProjectTests(unittest.TestCase):
    """Eos 25 Nov: "yeni bir klasörde sıfırdan ... kur" had no project to work in."""

    def test_the_words(self):
        from core.job_intent import wants_new_project
        self.assertTrue(wants_new_project("Yeni bir klasörde sıfırdan stok takip uygulaması yap"))
        self.assertTrue(wants_new_project("Ayrı bir projede baştan sona oyun yap"))
        self.assertFalse(wants_new_project("Bu projede baştan sona oyun yap"))

    def test_the_folder_is_new_named_and_a_git_repository(self):
        import subprocess
        from core.job_intent import new_project_folder
        from core.job_planner import create_project_folder
        with tempfile.TemporaryDirectory() as directory:
            first = new_project_folder("Yeni bir klasörde stok takip uygulaması yap", "1125-2300", base=directory)
            self.assertEqual(first.name, "stok-takip-uygulamasi-1125-2300")
            create_project_folder(first)
            second = new_project_folder("Yeni bir klasörde stok takip uygulaması yap", "1125-2300", base=directory)
            self.assertEqual(second.name, "stok-takip-uygulamasi-1125-2300-2", "never an existing folder")
            head = subprocess.run(["git", "-C", str(first), "log", "--oneline"], capture_output=True, text=True)
            self.assertIn("SpeS: yeni proje", head.stdout)
            name = subprocess.run(["git", "-C", str(first), "config", "user.name"], capture_output=True, text=True)
            self.assertEqual(name.stdout.strip(), "SpeS", "identity of this repository only")

    def test_the_conversation_gets_the_new_project_before_planning(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {"SPES_PROJECTS_HOME": str(Path(directory) / "projeler")}):
            chat = make_chat(directory)
            projects = {}
            chat.agent_service.projects.add.side_effect = lambda path, name=None: projects.setdefault(
                "p", {"id": "p-new", "path": path})
            run = TeamRun(chat)
            run.reply = PlanningTurnTests.PLAN
            started = []
            with patch.object(chat, "job_start", side_effect=lambda spec: started.append(spec) or {"id": "j"}):
                turn = run.run("Yeni bir klasörde baştan sona stok takip uygulaması yap",
                               write=True, confirm_write=True)
                deadline = time.monotonic() + 5
                while not started and time.monotonic() < deadline:
                    time.sleep(0.02)
            chat._diagnostics.close()
            conv = chat.store.get(turn["conversation_id"])
            self.assertEqual(conv["project_id"], "p-new")
            self.assertTrue(Path(projects["p"]["path"]).is_dir())
            plan = next(m for m in conv["messages"] if (m.get("metadata") or {}).get("job_plan"))
            self.assertIn("Yeni proje klasörü açıldı:", plan["content"])


class SelectedWriterTests(unittest.TestCase):
    """Live 26 Nov: with "Yalnız Codex" selected, Fatum wrote the job's milestones."""

    def test_the_selected_agent_writes_in_its_own_turns_and_another_reviews(self):
        from tests.test_long_job_chat import FakeChat
        from core.long_job import JobLedger
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {"QUARTZ_JOBS_HOME": str(Path(directory) / "jobs")}), \
                patch("core.agent_limits.snapshot", return_value={}), patch("core.long_job.keep_awake"):
            project = Path(directory) / "p"
            project.mkdir()
            chat = FakeChat(project, replies=[("completed", "Yapıldı.", "codex"),
                                              ("completed", "İnceledim.\nKABUL: EVET", "claude")])
            chat.store.conv["agent"] = "codex"
            self.assertEqual(chat._job_members("c1")[0], "codex")
            ledger = JobLedger.create({"goal": "Oyun", "project_path": str(project), "hours": 1, "review": True,
                                       "conversation_id": "c1",
                                       "milestones": [{"title": "T1", "acceptance": "ok"}]})
            job = chat._make_job(ledger)
            chat._jobs()[ledger.data["id"]] = job
            job.start()
            for _ in range(300):
                if ledger.data["status"] in {"done", "needs_user", "failed"}:
                    break
                time.sleep(0.02)
            job.thread.join(5)
        self.assertEqual(ledger.data["status"], "done")
        self.assertEqual(chat.sent[0]["agent"], "codex", "a single-agent turn, not Birlikte")
        self.assertEqual(chat.sent[1]["agent"], "claude", "a teammate reviews")
        self.assertEqual(ledger.data["milestones"][0]["reviewer"], "claude")
        self.assertNotIn("Fatum limitte", chat.sent[0]["text"])
