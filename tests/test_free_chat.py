"""Ücretsiz sohbet (core.free_chat, core.free_chat_chat) — Fides's design review 27 Nov (ŞARTLI).

No test reaches the network: the OpenAI-compatible client is a fake that records every request."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import free_chat as fc


def xor(data, unprotect=False):
    return bytes(b ^ 0x5A for b in data)


class FakeClient:
    """One fake per (channel, key); behaviour per channel from a script."""

    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, channel, key):
        outer = self

        class Models:
            def list(self):
                outer.calls.append((channel, "models", key))
                behaviour = outer.script.get(channel, {})
                if isinstance(behaviour.get("models"), Exception):
                    raise behaviour["models"]
                return [SimpleNamespace(id=i) for i in behaviour.get("models", [])]

        class Completions:
            def create(self, **kwargs):
                outer.calls.append((channel, "chat", kwargs))
                answer = outer.script.get(channel, {}).get("chat", "Merhaba!")
                if isinstance(answer, Exception):
                    raise answer
                message = SimpleNamespace(content=answer, tool_calls=[SimpleNamespace(id="x")])
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        return SimpleNamespace(models=Models(), chat=SimpleNamespace(completions=Completions()))


def api_error(kind, status, message="x"):
    import httpx
    import openai
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(status, request=request)
    return getattr(openai, kind)(message, response=response, body=None)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.script = {"gemini": {"models": ["models/gemini-3.8-flash", "models/gemini-3.8-pro",
                                             "models/gemini-3.6-flash-lite"]},
                       "openrouter": {"models": ["openai/gpt-5", "moonshotai/kimi-k2:free",
                                                 "moonshotai/kimi-k2.6:free", "moonshotai/kimi-k2.6"]},
                       "groq": {"models": ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]}}
        self.client = FakeClient(self.script)
        self.free = fc.FreeChat(fc.SecretStore(self.root, protect=xor), fc.Settings(self.root), client=self.client)


class ConnectTests(Base):
    def test_a_key_is_checked_then_stored_encrypted_and_never_returned(self):
        status = self.free.connect("gemini", "AIza-secret-123")
        self.assertNotIn("AIza-secret-123", str(status))
        self.assertNotIn("AIza-secret-123", (self.root / "keys.json").read_text(encoding="utf-8"))
        self.assertEqual(self.free.store.get("gemini"), "AIza-secret-123")
        gemini = next(c for c in status["channels"] if c["id"] == "gemini")
        self.assertEqual((gemini["connected"], gemini["send"], gemini["backup"], gemini["model"]),
                         (True, True, True, "gemini-3.8-flash"))

    def test_openrouter_only_ever_picks_a_free_model_kimi_first(self):
        self.free.connect("openrouter", "sk-or-1")
        self.assertEqual(self.free.settings.read()["channels"]["openrouter"]["model"], "moonshotai/kimi-k2.6:free")
        self.script["openrouter"]["models"] = ["openai/gpt-5", "moonshotai/kimi-k2.6"]
        with self.assertRaises(fc.FreeChatError):
            self.free.connect("openrouter", "sk-or-2")

    def test_a_wrong_key_is_not_stored_and_says_why(self):
        self.script["groq"]["models"] = api_error("AuthenticationError", 401)
        with self.assertRaises(fc.FreeChatError) as caught:
            self.free.connect("groq", "gsk-wrong")
        self.assertIn("anahtar geçersiz", str(caught.exception))
        self.assertFalse(self.free.store.has("groq"))

    def test_a_key_with_spaces_or_too_long_is_refused(self):
        for key in ("", "a b", "x" * 500):
            with self.assertRaises(fc.FreeChatError):
                self.free.store.set("gemini", key)

    def test_disconnect_removes_the_key_and_the_consents(self):
        self.free.connect("gemini", "k1")
        self.free.disconnect("gemini")
        self.assertFalse(self.free.store.has("gemini"))
        self.assertEqual(self.free.speakers(), [])

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_real_dpapi_round_trip(self):
        store = fc.SecretStore(self.root)
        store.set("groq", "gsk-real-dpapi")
        self.assertNotIn(b"gsk-real-dpapi", (self.root / "keys.json").read_bytes())
        self.assertEqual(store.get("groq"), "gsk-real-dpapi")


class ReplyTests(Base):
    def setUp(self):
        super().setUp()
        for channel in ("gemini", "openrouter", "groq"):
            self.free.connect(channel, f"key-{channel}")
        self.cancel = threading.Event()

    def chats(self):
        return [c for c in self.client.calls if c[1] == "chat"]

    def test_no_tool_is_ever_sent_and_a_returned_tool_call_is_ignored(self):
        result = self.free.reply("gemini", [{"role": "user", "content": "selam"}], self.cancel)
        self.assertEqual((result["outcome"], result["text"]), ("ok", "Merhaba!"))
        sent = self.chats()[0][2]
        self.assertFalse({"tools", "functions", "tool_choice"} & set(sent))
        self.assertEqual(sent["model"], "gemini-3.8-flash")

    def test_quota_falls_to_the_next_consented_backup_and_every_attempt_is_recorded(self):
        self.script["gemini"]["chat"] = api_error("RateLimitError", 429)
        result = self.free.reply("gemini", [{"role": "user", "content": "selam"}], self.cancel)
        self.assertEqual((result["outcome"], result["channel"]), ("ok", "openrouter"))
        self.assertEqual([a["result"] for a in result["attempts"]], ["quota", "ok"])

    def test_a_channel_without_backup_consent_is_never_tried(self):
        self.free.consent("openrouter", backup=False)
        self.free.consent("groq", backup=False)
        self.script["gemini"]["chat"] = api_error("RateLimitError", 429)
        result = self.free.reply("gemini", [{"role": "user", "content": "selam"}], self.cancel)
        self.assertEqual(result["outcome"], "exhausted")
        self.assertEqual({c[0] for c in self.chats()}, {"gemini"})

    def test_f2_a_refusal_is_never_routed_around_by_another_model(self):
        self.script["gemini"]["chat"] = api_error("BadRequestError", 400, "blocked by safety policy")
        result = self.free.reply("gemini", [{"role": "user", "content": "x"}], self.cancel)
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual({c[0] for c in self.chats()}, {"gemini"})

    def test_a_bad_key_and_an_outage_are_told_apart_from_quota(self):
        self.assertEqual(fc.classify(api_error("AuthenticationError", 401)), "key")
        self.assertEqual(fc.classify(api_error("PermissionDeniedError", 403)), "key")
        self.assertEqual(fc.classify(api_error("InternalServerError", 503)), "unreachable")
        self.assertEqual(fc.classify(api_error("RateLimitError", 429)), "quota")
        self.assertEqual(fc.classify(api_error("APIStatusError", 402)), "quota")

    def test_stop_ends_before_the_next_channel(self):
        self.cancel.set()
        result = self.free.reply("gemini", [{"role": "user", "content": "x"}], self.cancel)
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(self.chats(), [])


class PromptTests(unittest.TestCase):
    def test_f4_history_takes_only_this_free_conversations_talk(self):
        messages = [
            {"role": "user", "content": "proje raporu", "status": "completed", "metadata": {}},
            {"role": "assistant", "content": "KANIT: ...", "status": "completed", "metadata": {"long_job": "j1"}},
            {"role": "user", "content": "selam", "status": "completed", "metadata": {"free_chat": True}},
            {"role": "assistant", "content": "Merhaba", "status": "completed",
             "metadata": {"free_chat": True, "free_channel": "gemini"}},
            {"role": "assistant", "content": "", "status": "running",
             "metadata": {"free_chat": True, "free_channel": "openrouter"}},
            {"role": "assistant", "content": "not", "status": "completed",
             "metadata": {"free_chat": True}},
        ]
        history = fc.history_messages(messages, lambda c: fc.CHANNELS[c]["persona"])
        self.assertEqual([h["content"] for h in history], ["selam", "Merhaba"])

    def test_other_speakers_are_named_and_own_lines_stay_assistant(self):
        history = [{"role": "user", "content": "kedi mi köpek mi?"},
                   {"role": "assistant", "speaker": "Eos", "content": "Kedi."},
                   {"role": "assistant", "speaker": "Kimi", "content": "Köpek."}]
        messages = fc.build_messages("Kimi", ["Eos", "Kimi"], history, [("Eos", "Yine kedi.")])
        self.assertIn("Eos", messages[0]["content"])
        self.assertEqual(messages[2], {"role": "user", "content": "[Eos]: Kedi."})
        self.assertEqual(messages[3], {"role": "assistant", "content": "Köpek."})
        self.assertEqual(messages[-1]["content"], "[Eos]: Yine kedi.")

    def test_the_prompt_never_claims_tools(self):
        prompt = fc.system_prompt("Eos")
        self.assertIn("dosya, komut, internet", prompt)


class ChatServiceTests(Base):
    """The chat service with a real ConversationStore."""

    def make_chat(self):
        from core.agent_chat import AgentChatService
        from core.conversation_store import ConversationStore
        chat = AgentChatService.__new__(AgentChatService)
        chat.store = ConversationStore(self.root / "conversations.json")
        chat._lock = threading.RLock()
        chat._free_chat_service = self.free
        chat._next_sequence = lambda conv: len((conv or {}).get("messages", [])) + 1
        return chat

    def wait_done(self, chat, cid, count):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            bubbles = [m for m in chat.store.get(cid)["messages"] if m["role"] == "assistant"]
            if len(bubbles) >= count and all(m["status"] != "running" for m in bubbles):
                return bubbles
            time.sleep(0.02)
        self.fail("free round did not finish")

    def test_a_free_conversation_talks_with_every_consented_speaker_in_order(self):
        for channel in ("gemini", "openrouter"):
            self.free.connect(channel, f"k-{channel}")
        chat = self.make_chat()
        cid = chat.new_free_conversation()["id"]
        result = chat.send_message("Bir fikir tartışalım", conversation_id=cid, write=True, full_access=True)
        self.assertEqual(result["agent"], "free")
        bubbles = self.wait_done(chat, cid, 2)
        self.assertEqual([m["metadata"]["free_persona"] for m in bubbles], ["Eos", "Kimi"])
        second = [c for c in self.client.calls if c[1] == "chat"][1][2]["messages"]
        self.assertIn("[Eos]: Merhaba!", [m["content"] for m in second])

    def test_no_connection_answers_with_how_to_connect(self):
        chat = self.make_chat()
        cid = chat.new_free_conversation()["id"]
        result = chat.send_message("selam", conversation_id=cid)
        self.assertIn("Ücretsiz bağlantılar", result["assistant_message"]["content"])

    def test_server_side_no_job_project_read_skill_or_continue_from_a_free_conversation(self):
        chat = self.make_chat()
        cid = chat.new_free_conversation()["id"]
        with self.assertRaises(PermissionError):
            chat.send_message("x", conversation_id=cid, origin="long_job")
        for call in (lambda: chat.panel_read(cid, "project", "a.py"), lambda: chat.set_project(cid, None),
                     lambda: chat.continue_discussion(cid), lambda: chat.skill_override(cid, "o1"),
                     lambda: chat.prepare_resume(cid, "m1"), lambda: chat.coordination_message(cid, "user", "x")):
            with self.assertRaises(PermissionError):
                call()
        from core.long_job import JobError
        with self.assertRaises(JobError):
            chat.job_start({"conversation_id": cid, "goal": "oyun"})

    def test_is_free_answers_for_the_gui_route(self):
        chat = self.make_chat()
        cid = chat.new_free_conversation()["id"]
        self.assertEqual(chat.free_chat_action("is_free", {"conversation_id": cid}), {"free": True})
        self.assertEqual(chat.free_chat_action("is_free", {"conversation_id": "yok"}), {"free": False})


if __name__ == "__main__":
    unittest.main()
