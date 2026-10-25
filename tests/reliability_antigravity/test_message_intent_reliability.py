"""Reliability tests for intent classification and routing.
Covers:
- F-01: Polite Turkish requests with vowel harmony ('mısınız', 'mısın', 'musunuz', 'eder misiniz', 'çalıştırır mısınız'),
  missing common task verbs ('çöz', 'kapat'), and English commands downgraded to conversation.
- F-06: Orphan continuation ('devam et') when no task or coordination is active.
"""
import unittest
from core.message_intent import message_intent, tools_disallowed


class MessageIntentReliabilityTests(unittest.TestCase):
    """Tests verifying intent boundaries and reproducing F-01 and F-06."""

    def test_explicit_turkish_imperatives_are_tasks(self):
        """Baseline sanity check: explicit singular/imperative commands must be 'task'."""
        self.assertEqual(message_intent("Not defterini aç"), "task")
        self.assertEqual(message_intent("Test uygulamasını inceleyin ve düzeltin"), "task")
        self.assertEqual(message_intent("Logları kontrol et"), "task")
        self.assertEqual(message_intent("Hataları bul ve test yap"), "task")

    def test_polite_front_vowel_edebilir_misin_is_task(self):
        """Front-vowel polite form 'edebilir misin' and serendipitous prefix match 'misiniz' are tasks."""
        self.assertEqual(message_intent("Pencereyi kontrol edebilir misin?"), "task")
        self.assertEqual(message_intent("Pencereyi kontrol edebilir misiniz?"), "task")

    def test_regression_f01_vowel_harmony_polite_is_task(self):
        """Codex follow-up: original defect reproduced in f456185; now a regression.

        Original reviewer report and baseline remain in Git/checkpoints.
        """
        back_vowel_polite_commands = [
            "Pencereye bakar mısınız?",
            "Testleri çalıştırır mısınız?",
            "Pencereleri kontrol eder misiniz?",
            "Hata loglarını inceler misiniz?",
            "Bu sorunu çözebilir misiniz?",
            "Uygulamayı kapatır mısınız?",
        ]
        for cmd in back_vowel_polite_commands:
            actual = message_intent(cmd)
            self.assertEqual(
                actual,
                "task",
                f"F-01 regression: polite request '{cmd}' should be a task",
            )

    def test_regression_f01_english_commands_are_tasks(self):
        """Codex follow-up: preserve reviewer cases as positive regression coverage."""
        english_commands = [
            "Open Notepad and check logs",
            "Fix the bug in settings screen",
            "Inspect the active window",
            "Run unit tests and report results",
        ]
        for cmd in english_commands:
            actual = message_intent(cmd)
            self.assertEqual(
                actual,
                "task",
                f"F-01 regression: English request '{cmd}' should be a task",
            )

    def test_contract_f01_vowel_harmony_and_aorist_polite_should_be_task(self):
        """CONTRACT TEST: Back-vowel and aorist polite requests must be recognized as 'task'.

        Codex follow-up: fixed and promoted from expectedFailure.
        """
        self.assertEqual(message_intent("Pencereye bakar mısınız?"), "task")
        self.assertEqual(message_intent("Testleri çalıştırır mısınız?"), "task")
        self.assertEqual(message_intent("Hata loglarını inceler misiniz?"), "task")
        self.assertEqual(message_intent("Bu sorunu çözebilir misiniz?"), "task")

    def test_contract_f01_basic_english_commands_should_be_task(self):
        """CONTRACT TEST: Common English task verbs must be recognized as 'task'.

        Codex follow-up: fixed and promoted from expectedFailure.
        """
        self.assertEqual(message_intent("Open Notepad and check the logs"), "task")
        self.assertEqual(message_intent("Inspect and fix the bug in settings"), "task")
        self.assertEqual(message_intent("Run the tests and fix any failures"), "task")

    def test_reproduce_f06_orphan_continuation_routing(self):
        """F-06 RISK: When no task is active, 'devam et' yields 'continuation' which gui.py downgrades to conversation.

        In gui.py:183:
            return {"status":"ok","data":{"handled":False,"intent":"conversation" if message_kind != "task" else "task"}}
        Since message_kind is 'continuation', intent becomes 'conversation'.
        The bare string 'devam et' is sent to the LLM with no active task context.
        """
        intent = message_intent("devam et")
        self.assertEqual(intent, "continuation")

        # Simulate gui.py:183 fallback when no active desktop task or coordination exists
        has_active_natural_task = False
        has_active_coordination = False

        if not has_active_natural_task and not has_active_coordination:
            fallback_intent = "conversation" if intent != "task" else "task"
            self.assertEqual(fallback_intent, "conversation")

    def test_tools_disallowed_overrides_task_intent(self):
        """Verifies that explicit tool prohibition always forces 'conversation'."""
        self.assertEqual(message_intent("Sadece sohbet edelim, hiçbir araç kullanma"), "conversation")
        self.assertEqual(message_intent("İşlem yapmadan sadece fikir ver"), "conversation")


if __name__ == "__main__":
    unittest.main()
