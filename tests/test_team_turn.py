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
                               "write": kwargs.get("write", False), "step": (kwargs.get("base_meta") or {}).get("team_step")})
            self.active["now"] += 1
            self.active["max"] = max(self.active["max"], self.active["now"])
        time.sleep(0.05)
        with self.lock:
            self.active["now"] -= 1
        return self.reply

    def codex(self, cid, mid, prompt, project_id, write, confirm_write, **kwargs):
        kwargs["write"] = write
        return self._record(kwargs.get("agent", "codex"), kwargs)

    def agy(self, cid, mid, prompt, project_id, write, confirm_write, **kwargs):
        kwargs["write"] = write
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
                         {"codex": "Atlas", "antigravity": "Vision", "claude": "Usta"})
        self.assertEqual(len(set(CHARACTERS.values())), 3)
        self.assertIn("Adın Usta", character_instruction("claude"))

    def test_clamp_keeps_at_most_the_given_sentences(self):
        self.assertEqual(clamp_sentences("Bir. İki! Üç? Dört.", 3), "Bir. İki! Üç?")
        self.assertEqual(clamp_sentences("Tek cümle", 3), "Tek cümle")
        self.assertEqual(clamp_sentences("  ", 3), "")
        long = "Bu cümle " + "çok " * 120 + "uzun; ama tek cümle."
        short = clamp_sentences(long, 2)
        self.assertLessEqual(len(short), 2 * 160 + 1)
        self.assertTrue(short.endswith("…"))


class TeamTurnTests(unittest.TestCase):
    def test_conversation_turn_is_plan_parallel_critique_and_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            run = TeamRun(chat)
            turn = run.run("Bu mimari hakkında ne düşünüyorsunuz?")
            chat._diagnostics.close()
            messages = chat.store.get(turn["conversation_id"])["messages"]
        steps = [(c["agent"], c["step"]) for c in run.calls]
        self.assertEqual(steps[0], ("claude", 1))
        self.assertEqual(sorted(steps[1:3]), [("antigravity", 2), ("codex", 2)])
        self.assertEqual(steps[3], ("claude", 3))
        self.assertEqual(len(steps), 4)
        self.assertTrue(all(c["tool_less"] and not c["write"] for c in run.calls))
        self.assertGreaterEqual(run.active["max"], 2, "critiques must run in parallel")
        team = [m for m in messages if (m.get("metadata") or {}).get("team")]
        self.assertEqual([m["metadata"]["persona"] for m in team], ["Usta", "Atlas", "Vision", "Usta"])
        plan = team[0]["content"]
        self.assertLessEqual(plan.count("."), 3, "planning messages are clamped to three sentences")
        self.assertIn(turn["status"], {"completed", "running"})

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
