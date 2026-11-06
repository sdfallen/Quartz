"""Agents must hold their own view and keep disagreement visible (user request, 7 Nov 2026)."""
import tempfile
from pathlib import Path
import time
import unittest
from unittest.mock import MagicMock, patch

from core.agent_character import CHARACTERS, character_instruction
from core.agent_chat import AgentChatService
from core.response_style import communication_instruction


class AgentCharacterTests(unittest.TestCase):
    def test_each_agent_has_a_distinct_character_and_the_same_norms(self):
        codex, gemini = character_instruction("codex"), character_instruction("antigravity")
        self.assertIn("uygulayıcı mühendis", codex)
        self.assertIn("eleştirel mimar", gemini)
        self.assertNotEqual(CHARACTERS["codex"], CHARACTERS["antigravity"])
        for text in (codex, gemini):
            self.assertIn("gerekçesiz 'katılıyorum' yazma", text)
            self.assertIn("Yapay itiraz üretme", text)
            self.assertIn("Son karar kullanıcınındır", text)
            self.assertIn("izinleri, Durdur'u", text)
        with self.assertRaises(ValueError):
            character_instruction("notion")

    def test_every_chat_asks_for_an_own_view_without_empty_praise(self):
        text = communication_instruction("short")
        self.assertIn("yalnızca söylendiği için katılma", text)
        self.assertIn("Boş övgü kullanma", text)

    def test_group_rounds_carry_the_characters_and_keep_disagreement_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MagicMock(); service.check_squad_connection.return_value = {'connected': True}
            service.squad_create_group_task.return_value = {'id': 'squad'}
            service.squad_receive_messages.return_value = []
            chat = AgentChatService(service, Path(directory) / 'conversations.json')
            prompts = {'codex': [], 'antigravity': []}
            def codex(cid, mid, prompt, *a, **k): prompts['codex'].append(prompt); return 'Codex görüşü'
            def gemini(cid, mid, prompt, *a, **k): prompts['antigravity'].append(prompt); return 'Gemini görüşü'
            with patch.object(chat, '_execute_codex_bubble', side_effect=codex), \
                 patch.object(chat, '_execute_antigravity_bubble', side_effect=gemini):
                chat.send_message('İkiniz bu yaklaşımı değerlendirin', agent='collaboration')
                deadline = time.monotonic() + 3
                while chat._active_turn.get('status') == 'running' and time.monotonic() < deadline: time.sleep(.02)
            chat._diagnostics.close()
        self.assertEqual(len(prompts['codex']), 2)
        self.assertEqual(len(prompts['antigravity']), 2)
        for prompt in prompts['codex']: self.assertIn('uygulayıcı mühendis', prompt)
        for prompt in prompts['antigravity']: self.assertIn('eleştirel mimar', prompt)
        self.assertIn('En zayıf gördüğün noktayı', prompts['codex'][1])
        self.assertIn('Açık kalan anlaşmazlık:', prompts['antigravity'][1])
        self.assertNotIn('ORTAK KARAR', prompts['antigravity'][1])


if __name__ == '__main__':
    unittest.main()
