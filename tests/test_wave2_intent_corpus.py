import json
from pathlib import Path
import unittest

from core.message_intent import message_intent
from core.desktop_task_ui import desktop_intent


class IntentCorpusTests(unittest.TestCase):
    def test_claude_prelabelled_corpus(self):
        path = Path(__file__).resolve().parents[1] / 'docs/task_exam/intent_corpus_20261105.json'
        rows = json.loads(path.read_text(encoding='utf-8-sig'))['items']
        self.assertEqual(len(rows), 78)
        for row in rows:
            with self.subTest(id=row['id']):
                self.assertEqual(message_intent(row['text']), row['expect_message'])
                self.assertEqual(desktop_intent(row['text']) == 'task', row['expect_desktop'])

    def test_withdrawal_is_general_but_scoped_exception_does_not_cancel(self):
        for text in ("Blender'ı açabilir misin fakat vazgeçtim", "Uygulamayı aç ancak şimdilik gerek yok",
                     "Paint'i aç ama boşver"):
            self.assertEqual(message_intent(text), 'conversation')
            self.assertIsNone(desktop_intent(text))
        text = "Chrome'u aç ama geçmişi silmene gerek yok"
        self.assertEqual(message_intent(text), 'task')
        self.assertEqual(desktop_intent(text), 'task')

    def test_unknown_apps_keyboard_spellings_and_explanations(self):
        for text in ("Blender'ı aç", "Krita'yı aç", "Inkscape'i başlat", "Pencereyi kucult"):
            # Turkish consonant buffering is included in the generic suffix rule.
            self.assertEqual(message_intent(text), 'task')
            self.assertEqual(desktop_intent(text), 'task')
        for text in ("Blender'ı açınca ne olur?", 'Calistir komutu ne demek?',
                     '"Krita\'yı aç" komutu ne demek?'):
            self.assertNotEqual(desktop_intent(text), 'task')
