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

    def test_without_write_permission_it_is_an_ordinary_turn(self):
        _chat, _run, turn, started = self.run_turn("Godot ile bir yılan oyunu geliştir ve sonuna kadar kendin bitir")
        self.assertEqual(started, [])
        self.assertNotIn("job_plan", turn)

    def test_a_milestone_spes_sends_is_never_planned_again(self):
        _chat, _run, turn, started = self.run_turn("Godot ile bir yılan oyunu geliştir ve sonuna kadar kendin bitir",
                                                   write=True, confirm_write=True, origin="long_job")
        self.assertEqual(started, [])
        self.assertNotIn("job_plan", turn)


if __name__ == "__main__":
    unittest.main()
