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
        # Live 14 Nov: plural and words in between were missed.
        for text in ("Hesap Makinesi Kodu Yazın ve bitirdiğinizde rapor verin", "Bitince sonuna bitirdiğinde rapor ver",
                     "bitince bana kısa bir rapor ver", "tamamladığınızda beni arayın"):
            self.assertTrue(wants_finish_report(text), text)
        for text in ("Merhaba", "Bu ne zaman biter?", "Haber programını aç", "bitince arabaya bineceğim"):
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


class VoiceRepeatTests(unittest.TestCase):
    def test_same_answer_to_a_new_question_goes_to_the_team(self):
        from core.voice_front import VoiceFront
        said = "Fides hesap makinesini yazdı ve 12 artı 3 hesabını doğruladı."
        front = VoiceFront(api_key="k", post=lambda body: {"choices": [{"message": {"content": said}}]})
        history = [{"q": "Ne oldu?", "a": said}]
        state = {"busy": False, "messages": []}
        self.assertEqual(front.answer("Hangi tarayıcıda açıldı?", state, history)["reason"], "repeat")
        self.assertEqual(front.answer("Ne oldu?", state, history)["route"], "answered")  # same question, same answer
        seen = []
        VoiceFront(api_key="k", post=lambda body: seen.append(body) or {"choices": [{"message": {"content": "Tamam."}}]}
                   ).answer("Peki?", state, history)
        self.assertEqual([m["role"] for m in seen[0]["messages"]], ["system", "user", "assistant", "user"])


class DesktopTaskReportTests(unittest.TestCase):
    """Desktop (bilgisayar kontrolü) tasks end in coordination_message, not in the chat turn."""

    def chat_with_task(self, directory, request, status, final=True):
        from tests.test_team_turn import make_chat
        chat = make_chat(directory)
        cid = chat.store.get_active()["id"]
        chat.coordination_message(cid, "user", request, {})
        chat.coordination_message(cid, "quartz", "Görev başladı.", {"natural_task": "t1", "task_status": "running"})
        chat.coordination_message(cid, "codex", "HesapMakinesi.html kaydedildi, 12 + 3 = 15 görüldü.",
                                  {"natural_task": "t1", "task_status": "running"})
        meta = {"natural_task": "t1", "task_status": status,
                "host_check": {"status": "OBSERVED UI CRITERION VERIFIED"}}
        if final:
            meta["final"] = True
        chat.coordination_message(cid, "quartz", "Ajan yürütmesi tamamlandı.", meta)
        chat.coordination_message(cid, "quartz", "Ajan yürütmesi tamamlandı.", meta)  # never twice
        time.sleep(.4)
        messages = chat.store.get(cid)["messages"]
        chat._diagnostics.close()
        return [m for m in messages if (m.get("metadata") or {}).get("report")]

    def test_desktop_task_with_the_request_rings_once(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"NVIDIA_API_KEY": ""}):
            reports = self.chat_with_task(directory, "Hesap makinesi yaz, bitirdiğinizde rapor verin", "completed")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["metadata"]["notify"], "call")
        self.assertIn("ekranda SpeS gözlemiyle görüldü", reports[0]["content"])
        self.assertIn("Fides:", reports[0]["content"])

    def test_no_report_without_request_on_stop_or_before_the_end(self):
        for request, status, final in (("Hesap makinesi yaz", "completed", True),
                                       ("Hesap makinesi yaz, bitince haber ver", "cancelled", True),
                                       ("Hesap makinesi yaz, bitince haber ver", "completed", False)):
            with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"NVIDIA_API_KEY": ""}):
                self.assertEqual(self.chat_with_task(directory, request, status, final), [], (request, status, final))


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
