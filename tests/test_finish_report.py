"""Finish report: "bitince haber ver" -> short report at the end, flagged for a phone call."""
import tempfile
import time
import unittest
from unittest.mock import patch

from core.finish_report import collect_facts, plain_report, wants_finish_report, write_report
from core.voice_front import build_context

MESSAGES = [
    {"id": "u1", "role": "user", "content": "Giriş sayfasını yap, bitince haber ver"},
    {"id": "a1", "role": "assistant", "sender": "claude", "content": "Giriş sayfası yazıldı.\n---TEKNIK_AYRINTILAR---\nC:\\x\\app.py",
     "metadata": {"sender": "claude", "host_evidence": {"files_changed": ["app.py", "login.html"],
                                                          "source_validation": {"status": "VERIFIED"}}}},
    {"id": "a2", "role": "assistant", "sender": "codex", "content": "Test kırıldı.",
     "metadata": {"sender": "codex", "status": "failed", "error": "x"}},
]


class Front:
    def __init__(self, key="k", reply=None, error=None):
        self.api_key, self.model, self.reply, self.error, self.bodies = key, "m", reply, error, []

    def _post(self, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        return {"choices": [{"message": {"content": self.reply}}]}


class FinishReportTests(unittest.TestCase):
    def test_notify_phrases(self):
        for text in ("Giriş sayfasını yap, bitince haber ver", "Testleri çalıştır tamamlanınca beni ara",
                     "iş bitince bildir", "Bitirdiğinde bana rapor ver"):
            self.assertTrue(wants_finish_report(text), text)
        for text in ("Merhaba", "Bu ne zaman biter?", "Haber programını aç"):
            self.assertFalse(wants_finish_report(text), text)

    def test_facts_come_from_host_evidence_and_stored_messages(self):
        facts = collect_facts(MESSAGES, "u1", "partial")
        self.assertEqual(facts["status"], "kısmen tamamlandı")
        self.assertEqual(facts["files"], 2)
        self.assertEqual(facts["failed"], ["Fides"])
        self.assertIn("sözdizimi doğrulandı, test kanıtı yok (Fatum)", facts["checks"])
        self.assertNotIn("app.py", " ".join(facts["last"]))  # technical details stay out
        plain = plain_report(facts)
        self.assertIn("Görev kısmen tamamlandı.", plain)
        self.assertIn("2 dosya değişti.", plain)

    def test_bolt_phrases_it_or_the_plain_summary_is_used(self):
        facts = collect_facts(MESSAGES, "u1", "completed")
        front = Front(reply="Giriş sayfası yapıldı, iki dosya değişti.")
        self.assertEqual(write_report(facts, front), "Giriş sayfası yapıldı, iki dosya değişti.")
        self.assertIn("Değişen dosya sayısı: 2", front.bodies[0]["messages"][1]["content"])
        for broken in (Front(error=TimeoutError()), Front(reply=""), Front(reply="x" * 1200), Front(key="")):
            self.assertEqual(write_report(facts, broken), plain_report(facts))

    def test_report_is_the_voice_context_for_questions(self):
        state = {"busy": False, "messages": [
            {"role": "assistant", "persona": "Fatum", "text": "Tamam."},
            {"role": "assistant", "persona": "SpeS", "report": True, "text": "Görev raporu: " + "uzun " * 60}]}
        text = build_context(state)
        self.assertIn("SpeS GÖREV RAPORU", text)
        self.assertGreater(len(text.split("SpeS GÖREV RAPORU: ")[1]), 240)


class ChatIntegrationTests(unittest.TestCase):
    def run_and_wait(self, chat, run, text, **kw):
        run.run(text, **kw)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            messages = chat.store.get(chat.store.get_active()["id"])["messages"]
            if any((m.get("metadata") or {}).get("report") for m in messages):
                return messages
            time.sleep(.05)
        return chat.store.get(chat.store.get_active()["id"])["messages"]

    def test_notify_turn_ends_with_a_report_flagged_for_a_call(self):
        from tests.test_team_turn import TeamRun, make_chat
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"NVIDIA_API_KEY": ""}):
            chat = make_chat(directory)
            messages = self.run_and_wait(chat, TeamRun(chat), "Bir giriş sayfası yap, bitince haber ver",
                                         write=True, confirm_write=True, full_access=True)
            chat._diagnostics.close()
        reports = [m for m in messages if (m.get("metadata") or {}).get("report")]
        self.assertEqual(len(reports), 1)
        self.assertTrue(reports[0]["content"].startswith("Görev raporu: "))
        self.assertEqual(reports[0]["metadata"]["notify"], "call")
        self.assertEqual(reports[0]["sender"], "quartz")

    def test_no_report_without_the_request(self):
        from tests.test_team_turn import TeamRun, make_chat
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"NVIDIA_API_KEY": ""}):
            chat = make_chat(directory)
            run = TeamRun(chat)
            run.run("Bir giriş sayfası yap", write=True, confirm_write=True, full_access=True)
            time.sleep(.3)
            messages = chat.store.get(chat.store.get_active()["id"])["messages"]
            chat._diagnostics.close()
        self.assertFalse(any((m.get("metadata") or {}).get("report") for m in messages))


if __name__ == "__main__":
    unittest.main()
