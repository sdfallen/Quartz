import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock

from core.agent_chat import AgentChatService
from core.conversation_store import ConversationStore
from core.response_style import communication_instruction, wants_full_report, DETAIL_MARKER


class ResponseStyleTests(unittest.TestCase):
    def test_default_setting_persists_without_changing_messages_or_models(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"conversations.json"
            store = ConversationStore(path)
            cid = store.get_active()["id"]
            store.append_message(cid, "assistant", "tam kanıt", metadata={"status":"failed", "error":"trace"})
            before = store.get(cid)
            self.assertEqual(store.preferences()["response_detail"], "short")
            store.set_response_detail("technical")
            loaded = ConversationStore(path)
            self.assertEqual(loaded.preferences()["response_detail"], "technical")
            self.assertEqual(loaded.get(cid), before)
            with self.assertRaises(ValueError): store.set_response_detail("unbounded")

    def test_single_and_group_bubbles_share_generation_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = AgentChatService(MagicMock(), Path(directory)/"conversations.json")
            cid = chat.store.get_active()["id"]
            for level in ("short", "normal", "technical"):
                chat.set_response_detail(level)
                for kind in ("Codex bağımsız yanıt", "Antigravity bağımsız yanıt", "Grup tur2 Squad verisi"):
                    prompt = chat._communication_prompt(cid, kind)
                    self.assertIn("sade, doğal ve doğrudan Türkçe", prompt)
                    self.assertIn(kind, prompt)
                    self.assertIn("Başarısız", prompt)
                    self.assertIn("Squad üzerinden gerekli tam teknik veriyi paylaş", prompt)

    def test_explicit_report_overrides_short_preference(self):
        for request in ("Kapsamlı bir rapor ver", "Ayrıntılı analiz istiyorum", "Give a detailed report"):
            self.assertTrue(wants_full_report(request))
            self.assertIn("istenen tam raporu ana yanıtta ver", communication_instruction("short", request))
        self.assertFalse(wants_full_report("Masaüstü kontrolü çalışıyor mu?"))

    def test_technical_error_retains_complete_trace(self):
        trace = "quota 429\nprovider-path\n" + "evidence " * 500
        text = AgentChatService._format_error("codex", RuntimeError(trace))
        self.assertTrue(text.startswith("Başarısız."))
        self.assertEqual(text.split(DETAIL_MARKER+"\n")[1], trace)

    def test_real_js_presentation_preserves_evidence_and_failure(self):
        # Execute the production pure presentation function, not a rewritten copy.
        import gui
        source = gui._HTML.split("  function agentMessageView(", 1)[1].split("  function renderMessageBody(", 1)[0]
        javascript = "function agentMessageView(" + source + r'''
const assert = require('assert');
let full = 'Başarısız. Bağlantı kurulamadı.\n\n---TEKNIK_AYRINTILAR---\n' + 'tam hata izi '.repeat(500);
let v = agentMessageView(full, {status:'failed', metadata:{error:'trace',checkpoint:'backup.zip'}}, 'short');
assert(v.summary.includes('Bağlantı kurulamadı')); assert.equal(v.state, 'Başarısız');
assert(v.details.includes('tam hata izi '.repeat(500))); assert(v.details.includes('backup.zip')); assert(!v.open);
assert(agentMessageView(full, {}, 'technical').open);
assert.equal(agentMessageView(full, {role:'user'}, 'short').summary, full);
assert.equal(agentMessageView('Henüz doğrulanmadı.', {status:'completed'}, 'short').state, '');
console.log('presentation PASS');
'''
        result = subprocess.run(["node", "-e", javascript], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
