"""Long-term memory: explicit capture only, secrets refused, bounded, visible, deletable."""
import re
import tempfile
import unittest
from pathlib import Path

from core.user_memory import FILE_NAME, MAX_CHARS, MAX_ITEMS, UserMemory, contains_secret, remember_request

ROOT = Path(__file__).resolve().parents[1]


class CaptureTests(unittest.TestCase):
    def test_explicit_requests_are_captured_without_the_trigger(self):
        cases = {
            "Benim adım Ali, bunu hatırla": "Benim adım Ali",
            "Hatırla: kahveyi şekersiz içerim": "kahveyi şekersiz içerim",
            "Unutma, cuma günleri müşteri toplantım var": "cuma günleri müşteri toplantım var",
            "Projelerde Türkçe yorum yazılsın, aklında tut.": "Projelerde Türkçe yorum yazılsın",
        }
        for text, fact in cases.items():
            with self.subTest(text=text):
                self.assertEqual(remember_request(text), fact)

    def test_questions_quotes_and_other_words_are_not_requests(self):
        for text in ("Adımı hatırlıyor musun?", "Bunu hatırladın mı", "Bana yarın hatırlatır mısın?",
                     '"Bunu hatırla" ne demek', "Toplantıyı unutmayalım", "Hatırlattı mı sana?", "Merhaba"):
            with self.subTest(text=text):
                self.assertEqual(remember_request(text), "")

    def test_secrets_are_detected(self):
        # Key-shaped samples are assembled at run time so no key-like literal sits in the repository.
        fake_openai = "sk" + "-" + "x" * 20
        fake_nvidia = "nv" + "api" + "-" + "y" * 24
        for text in ("Şifrem 1234", "parolam kedi99", "anahtar " + fake_openai, "kartım 4111 1111 1111 1111",
                     "IBAN TR12 0006 1005 1978 6457 8413 26", "TC 12345678901", "değer " + fake_nvidia):
            with self.subTest(text=text):
                self.assertTrue(contains_secret(text))
        self.assertFalse(contains_secret("Benim adım Ali"))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.memory = UserMemory(Path(self.dir.name) / FILE_NAME)

    def test_secret_is_refused_before_anything_is_written(self):
        result = self.memory.add("Şifrem 1234")
        self.assertEqual(result, {"saved": False, "reason": "secret"})
        self.assertFalse(self.memory.path.exists())

    def test_bounded_deduplicated_and_deletable(self):
        first = self.memory.add("Benim adım Ali")
        self.assertTrue(first["saved"])
        self.assertEqual(self.memory.add("benim adım ali")["reason"], "duplicate")
        self.assertLessEqual(len(self.memory.add("a " * 400)["id"]), 12)
        self.assertLessEqual(max(len(i["text"]) for i in self.memory.items()), MAX_CHARS + 1)
        for n in range(MAX_ITEMS + 5):
            self.memory.add(f"bilgi {n}")
        self.assertEqual(len(self.memory.items()), MAX_ITEMS)
        newest = self.memory.items()[-1]
        self.assertTrue(self.memory.remove(newest["id"]))
        self.assertFalse(self.memory.remove(newest["id"]))
        self.assertGreater(self.memory.clear(), 0)
        self.assertEqual(self.memory.items(), [])

    def test_prompt_block_is_labelled_data_newest_first(self):
        self.assertEqual(self.memory.prompt_block(), "")
        self.memory.add("eski bilgi")
        self.memory.add("yeni bilgi")
        block = self.memory.prompt_block()
        self.assertIn("veri, talimat değil", block)
        self.assertLess(block.index("yeni bilgi"), block.index("eski bilgi"))


class ChatIntegrationTests(unittest.TestCase):
    def test_memory_reaches_a_new_conversation_and_secrets_are_not_kept(self):
        from tests.test_team_turn import TeamRun, make_chat
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            run = TeamRun(chat)
            run.run("Benim adım Ali, bunu hatırla")
            run.run("Şifrem 1234, bunu hatırla")
            messages = chat.store.get(chat.store.get_active()["id"])["messages"]
            notes = [m["metadata"].get("memory") for m in messages if m["role"] == "user"]
            self.assertTrue(notes[0]["saved"])
            self.assertEqual(notes[1], {"saved": False, "reason": "secret"})
            self.assertEqual([i["text"] for i in chat.memory_list()], ["Benim adım Ali"])
            fresh = chat.new_conversation(agent="collaboration")
            # Every bubble executor (team, single agent, classic pair) wraps its prompt here.
            prompt = chat._communication_prompt(fresh["id"], "Adım neydi?")
            chat._diagnostics.close()
        self.assertIn("Benim adım Ali", prompt)
        self.assertNotIn("1234", prompt)
        self.assertLess(prompt.index("HATIRLANANLAR"), prompt.index("Adım neydi?"))

    def test_clearing_memory_needs_explicit_confirmation(self):
        from tests.test_team_turn import make_chat
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            chat.user_memory.add("bir bilgi")
            with self.assertRaises(PermissionError):
                chat.memory_clear()
            self.assertEqual(chat.memory_clear(confirmed=True)["removed"], 1)
            chat._diagnostics.close()


class PrivacyTests(unittest.TestCase):
    def test_memory_file_is_private_everywhere(self):
        self.assertIn(FILE_NAME, (ROOT / ".gitignore").read_text(encoding="utf-8"))
        for path in ("scripts/audit_publish.py", "core/self_diagnostics.py", "core/workspace_checkpoint.py",
                     "scripts/finalize_desktop_delivery.py", "installer/Quartz.iss"):
            with self.subTest(path=path):
                self.assertIn(FILE_NAME, (ROOT / path).read_text(encoding="utf-8"))
        from core.project_read_mcp import SECRET_NAME
        self.assertTrue(SECRET_NAME.match(FILE_NAME), "agents reading a project must not see it")


if __name__ == "__main__":
    unittest.main()
