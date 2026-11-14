"""Birlikte (team) mode: plan, critique and decision in the chat; only the lead writes."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.agent_character import CHARACTERS, PERSONAS, character_instruction
from core.agent_chat import AgentChatService
from core.team_turn import clamp_sentences


def make_chat(directory, *, claude_ready=True):
    service = MagicMock()
    service.check_squad_connection.return_value = {"connected": False}
    service.claude.probe.return_value = {"ready": claude_ready}
    return AgentChatService(service, Path(directory) / "conversations.json")


class TeamRun:
    def __init__(self, chat, reply_words=6):
        self.calls, self.lock, self.active = [], threading.Lock(), {"max": 0, "now": 0}
        self.reply = " ".join(["Kısa bir cümle."] * reply_words)
        self.chat = chat

    def _record(self, agent, kwargs):
        with self.lock:
            self.calls.append({"agent": agent, "tool_less": kwargs.get("tool_less", False), "project_scope": kwargs.get("project_scope", False),
                               "write": kwargs.get("write", False), "step": (kwargs.get("base_meta") or {}).get("team_step"),
                               "prompt": kwargs.get("prompt", ""), "web": kwargs.get("web", False)})
            self.active["now"] += 1
            self.active["max"] = max(self.active["max"], self.active["now"])
        time.sleep(0.05)
        with self.lock:
            self.active["now"] -= 1
        return self.reply

    def codex(self, cid, mid, prompt, project_id, write, confirm_write, **kwargs):
        kwargs["write"] = write; kwargs["prompt"] = prompt
        return self._record(kwargs.get("agent", "codex"), kwargs)

    def agy(self, cid, mid, prompt, project_id, write, confirm_write, **kwargs):
        kwargs["write"] = write; kwargs["prompt"] = prompt
        return self._record("antigravity", kwargs)

    def run(self, text, **send_kwargs):
        with patch.object(self.chat, "_execute_codex_bubble", side_effect=self.codex), \
             patch.object(self.chat, "_execute_antigravity_bubble", side_effect=self.agy):
            self.chat.send_message(text, agent="collaboration", **send_kwargs)
            deadline = time.monotonic() + 5
            while self.chat._active_turn.get("status") == "running" and time.monotonic() < deadline:
                time.sleep(0.02)
        return self.chat._active_turn


class PersonaTests(unittest.TestCase):
    def test_three_agents_have_their_own_persona(self):
        self.assertEqual({a: p["name"] for a, p in PERSONAS.items()},
                         {"codex": "Fides", "antigravity": "Eos", "claude": "Fatum"})
        self.assertEqual(len(set(CHARACTERS.values())), 3)
        self.assertIn("Adın Fatum", character_instruction("claude"))

    def test_clamp_keeps_at_most_the_given_sentences(self):
        self.assertEqual(clamp_sentences("Bir. İki! Üç? Dört.", 3), "Bir. İki! Üç?")
        self.assertEqual(clamp_sentences("Tek cümle", 3), "Tek cümle")
        self.assertEqual(clamp_sentences("  ", 3), "")
        long = "Bu cümle " + "çok " * 120 + "uzun; ama tek cümle."
        short = clamp_sentences(long, 2)
        self.assertLessEqual(len(short), 2 * 160 + 1)
        self.assertTrue(short.endswith("…"))
        # Several sentences over budget: keep whole sentences, never cut one in half.
        many = "Kısa giriş cümlesi. " + "Bu ikinci cümle " + "epey " * 100 + "uzun. Üçüncü."
        kept = clamp_sentences(many, 3)
        self.assertEqual(kept, "Kısa giriş cümlesi.")
        self.assertFalse(kept.endswith("…"))


class TeamTurnTests(unittest.TestCase):
    def test_small_talk_to_the_team_is_short_and_has_no_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            run = TeamRun(chat)
            turn = run.run("Bu mimari hakkında ne düşünüyorsunuz?")
            chat._diagnostics.close()
            messages = chat.store.get(turn["conversation_id"])["messages"]
        steps = [(c["agent"], c["step"]) for c in run.calls]
        self.assertEqual(steps[0], ("claude", 0))
        self.assertEqual(sorted(steps[1:]), [("antigravity", 0), ("codex", 0)])
        self.assertTrue(all(c["tool_less"] and not c["write"] for c in run.calls))
        self.assertGreaterEqual(run.active["max"], 2, "teammates answer in parallel")
        team = [m for m in messages if (m.get("metadata") or {}).get("team")]
        self.assertEqual([m["metadata"]["persona"] for m in team], ["Fatum", "Fides", "Eos"])
        for message in team:
            self.assertLessEqual(len(message["content"]), 2 * 110 + 1, "chat replies stay text-message short")
        # Older conversations count as Workspace: short and formal (space split, 14 Nov).
        self.assertTrue(all("KISA YANIT" in c["prompt"] for c in run.calls))
        self.assertIn(turn["status"], {"completed", "running"})

    def test_the_team_remembers_earlier_turns(self):
        for second, kwargs in (("Adım neydi?", {}),
                               ("Bir giriş sayfası yap", {"write": True, "confirm_write": True, "full_access": True})):
            with self.subTest(second=second), tempfile.TemporaryDirectory() as directory:
                chat = make_chat(directory)
                run = TeamRun(chat)
                run.run("Benim adım Ali, bunu hatırla")
                first_calls = len(run.calls)
                run.run(second, **kwargs)
                chat._diagnostics.close()
                later = run.calls[first_calls:]
                self.assertTrue(later)
                for call in later:
                    self.assertIn("Kullanıcı: Benim adım Ali, bunu hatırla", call["prompt"])
                    self.assertIn("Fatum: Kısa bir cümle.", call["prompt"])
                    self.assertEqual(call["prompt"].count(second), 1, "the new message is not repeated in the history")

    def test_history_uses_persona_names_and_drops_errors_and_details(self):
        from core.team_turn import team_history
        messages = [
            {"id": "1", "role": "user", "sender": "user", "content": "Selam"},
            {"id": "2", "role": "assistant", "sender": "codex", "content": "Merhaba\n---TEKNIK_AYRINTILAR---\nrun 77"},
            {"id": "3", "role": "assistant", "sender": "antigravity", "content": "Traceback", "metadata": {"status": "failed"}},
            {"id": "4", "role": "assistant", "sender": "claude", "content": "x" * 900},
            {"id": "5", "role": "user", "sender": "user", "content": "şimdiki"},
        ]
        text = team_history(messages, exclude_ids={"5"})
        self.assertEqual(text.splitlines()[:2], ["Kullanıcı: Selam", "Fides: Merhaba"])
        self.assertNotIn("Traceback", text)
        self.assertNotIn("run 77", text)
        self.assertNotIn("şimdiki", text)
        self.assertLess(len(text.splitlines()[2]), 380)

    def test_every_agent_may_search_in_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            run = TeamRun(chat)
            run.run("Bugün İstanbul'da hava nasıl beyler?")
            chat._diagnostics.close()
        self.assertEqual([(c["agent"], c["web"]) for c in run.calls],
                         [("claude", True), ("codex", True), ("antigravity", True)])
        for call in run.calls:
            self.assertIn("yalnız arama", call["prompt"])  # results are data, not instructions

    def test_eos_guard_allows_only_a_plain_search(self):
        from core.desktop_mcp import web_search_tool_allowed as ok
        self.assertTrue(ok({"toolCall": {"name": "search_web", "args": {"query": "dolar kuru"}}}))
        self.assertTrue(ok({"tool_name": "search_web", "tool_input": '{"query": "dolar kuru"}'}))
        for denied in ({"toolCall": {"name": "read_url_content", "args": {"Url": "https://x.y"}}},
                       {"toolCall": {"name": "open_browser_url", "args": {"Url": "https://x.y"}}},
                       {"toolCall": {"name": "read_browser_page", "args": {}}},
                       {"toolCall": {"name": "run_command", "args": {"CommandLine": "dir"}}},
                       {"toolCall": {"name": "read_file", "args": {"Path": "C:/a"}}},
                       {"toolCall": {"name": "search_web", "args": {"query": "x", "url": "https://x.y"}}},
                       {"toolCall": {"name": "search_web", "args": {"query": ""}}},
                       {"toolCall": {"name": "search_web", "args": {"query": "q" * 500}}},
                       "not a dict", {}):
            self.assertFalse(ok(denied), denied)

    def test_web_policy_table(self):
        from core.web_policy import codex_web_mode, web_allowed
        self.assertTrue(web_allowed("claude", conversation_only=True))
        self.assertTrue(web_allowed("codex", conversation_only=True))
        self.assertTrue(web_allowed("antigravity", conversation_only=True))
        self.assertFalse(web_allowed("antigravity", conversation_only=True, write=True))
        for blocked in (dict(project_read=True), dict(write=True), dict(full_access=True), dict(desktop=True)):
            self.assertFalse(web_allowed("claude", conversation_only=True, **blocked), blocked)
        self.assertFalse(web_allowed("codex", conversation_only=False))
        self.assertEqual(codex_web_mode(False), "disabled")
        self.assertEqual(codex_web_mode(True), "cached")

    def test_who_answers_small_talk(self):
        from core.team_turn import addressed_agents
        self.assertEqual(addressed_agents("Merhaba"), ["claude"])
        self.assertEqual(addressed_agents("selam beyler"), ["claude", "codex", "antigravity"])
        self.assertEqual(addressed_agents("Eos sen ne dersin?"), ["antigravity"])
        self.assertEqual(addressed_agents("Fides ve Eos, nasılsınız?"), ["claude", "codex", "antigravity"])
        self.assertEqual(addressed_agents("Fides bugün nasıl?"), ["codex"])

    def test_task_turn_only_the_lead_writes_and_checks_run_in_parallel(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            run = TeamRun(chat)
            run.run("Bir giriş sayfası yap ve testlerini çalıştır", write=True, confirm_write=True, full_access=True)
            chat._diagnostics.close()
        writers = [c for c in run.calls if c["write"]]
        self.assertEqual([(c["agent"], c["step"]) for c in writers], [("claude", 4)])
        steps = [(c["agent"], c["step"]) for c in run.calls]
        for expected in [("claude", 1), ("codex", 2), ("antigravity", 2), ("claude", 3), ("codex", 4),
                         ("antigravity", 4), ("codex", 5), ("antigravity", 5), ("claude", 6)]:
            self.assertIn(expected, steps)
        checks = [c for c in run.calls if c["step"] == 5]
        self.assertTrue(all(c["project_scope"] and not c["write"] for c in checks), "checks are project-read runs")

    def test_team_readiness_is_checked_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            self.assertTrue(chat._team_ready())
            chat.agent_service.claude.probe.assert_called_with(force=True)
            chat._diagnostics.close()

    def test_without_a_ready_claude_the_classic_pair_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory, claude_ready=False)
            run = TeamRun(chat)
            run.run("İkiniz bu yaklaşımı değerlendirin")
            chat._diagnostics.close()
        self.assertNotIn("claude", {c["agent"] for c in run.calls})


class IntentRegressionTests(unittest.TestCase):
    def test_point_of_view_is_not_an_open_command(self):
        from core.message_intent import message_intent
        self.assertEqual(message_intent("Senin karakterin ne olurdu: işe bakış açın ve rolün nedir?"), "conversation")
        self.assertEqual(message_intent("Not defterini aç"), "task")
        self.assertEqual(message_intent("uygulamayı açın"), "task")


if __name__ == "__main__":
    unittest.main()
