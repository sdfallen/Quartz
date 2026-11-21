"""Birlikte: the user makes any agent passive or active (user request 21 Nov 2026).

"Limitleri dolduğu zaman ya da işe uygun olmadıkları vakit" an agent sits the team turn out.
The first active agent leads and is the only writer; the other active agents criticise and check.
"""
import tempfile
import unittest
from pathlib import Path

from core.long_job import JobLedger, LongJob
from tests.test_long_job import Clock, nullctx
from tests.test_team_turn import TeamRun, make_chat

WRITE = {"write": True, "confirm_write": True, "full_access": True}


class TeamStoreTests(unittest.TestCase):
    def test_all_agents_are_active_until_the_user_says_otherwise(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            cid = chat.store.get_active()["id"]
            self.assertEqual(chat.store.get_team(cid), ["claude", "codex", "antigravity"])
            result = chat.set_team_member(cid, "codex", False)
            self.assertEqual(result["team"], ["claude", "antigravity"])
            self.assertEqual(result["active_conversation"]["team_passive"], ["codex"])
            again = make_chat(directory)  # persisted with the conversation
            self.assertEqual(again.store.get_team(cid), ["claude", "antigravity"])
            self.assertEqual(again.set_team_member(cid, "codex", True)["team"], ["claude", "codex", "antigravity"])
            chat._diagnostics.close()
            again._diagnostics.close()

    def test_one_agent_must_stay_active(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            cid = chat.store.get_active()["id"]
            chat.set_team_member(cid, "claude", False)
            chat.set_team_member(cid, "codex", False)
            with self.assertRaises(ValueError):
                chat.set_team_member(cid, "antigravity", False)
            with self.assertRaises(ValueError):
                chat.set_team_member(cid, "notion", False)
            self.assertEqual(chat.store.get_team(cid), ["antigravity"])
            chat._diagnostics.close()


class TeamTurnWithPassiveAgentsTests(unittest.TestCase):
    def run_turn(self, passive, text, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            cid = chat.store.get_active()["id"]
            for agent in passive:
                chat.set_team_member(cid, agent, False)
            run = TeamRun(chat)
            turn = run.run(text, **kwargs)
            chat._diagnostics.close()
            messages = chat.store.get(cid)["messages"]
        return run.calls, turn, messages

    def test_a_passive_fatum_hands_the_lead_and_the_writing_to_fides(self):
        calls, turn, messages = self.run_turn(["claude"], "Bir giriş sayfası yap", **WRITE)
        agents = {c["agent"] for c in calls}
        self.assertNotIn("claude", agents)
        writers = [c["agent"] for c in calls if c["write"]]
        self.assertEqual(writers, ["codex"], "the first active agent is the only writer")
        self.assertEqual({c["agent"] for c in calls if c["step"] in (2, 5)}, {"antigravity"})
        lead_bubbles = [m for m in messages if (m.get("metadata") or {}).get("team_step") == 1]
        self.assertEqual([m["metadata"]["sender"] for m in lead_bubbles], ["codex"])
        self.assertEqual(turn["status"], "completed")

    def test_a_passive_eos_neither_criticises_nor_checks(self):
        calls, turn, _ = self.run_turn(["antigravity"], "Bir giriş sayfası yap", **WRITE)
        self.assertNotIn("antigravity", {c["agent"] for c in calls})
        self.assertEqual([c["agent"] for c in calls if c["write"]], ["claude"])
        self.assertEqual({c["agent"] for c in calls if c["step"] in (2, 5)}, {"codex"})
        self.assertEqual(turn["status"], "completed")

    def test_a_team_of_one_builds_alone_and_completes(self):
        calls, turn, _ = self.run_turn(["codex", "antigravity"], "Bir giriş sayfası yap", **WRITE)
        self.assertEqual({c["agent"] for c in calls}, {"claude"})
        self.assertFalse([c for c in calls if c["step"] in (2, 5)])
        self.assertEqual(turn["status"], "completed")

    def test_the_team_header_names_only_active_members(self):
        calls, _, _ = self.run_turn(["antigravity"], "Bir giriş sayfası yap", **WRITE)
        header = calls[0]["prompt"].split("\n", 1)[0]
        self.assertIn("Fides", header)
        self.assertNotIn("Eos", header)

    def test_a_passive_agent_stays_quiet_in_group_chat(self):
        calls, _, _ = self.run_turn(["codex"], "Bu mimari hakkında ne düşünüyorsunuz?")
        self.assertEqual(sorted(c["agent"] for c in calls), ["antigravity", "claude"])

    def test_naming_only_a_passive_agent_falls_back_to_the_lead(self):
        calls, _, _ = self.run_turn(["codex"], "Fides sen ne dersin?")
        self.assertEqual([c["agent"] for c in calls], ["claude"])


class LongJobSkipsPassiveWritersTests(unittest.TestCase):
    def test_pick_writer_never_chooses_a_passive_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "game").mkdir()
            clock = Clock()
            ledger = JobLedger.create({"goal": "x", "project_path": str(root / "game"), "hours": 1,
                                       "milestones": [{"title": "a", "acceptance": "b"}]},
                                      root=root / "jobs", clock=clock)
            members = ["codex", "antigravity"]
            job = LongJob(ledger, run_milestone=lambda *a: {}, checkpoint=lambda: {}, baseline=lambda: {},
                          snapshot=lambda: {}, changed=lambda a, b: [], commit=lambda f, m: None,
                          limits=lambda: {}, clock=clock, awake=nullctx, writers=lambda: members)
            self.assertEqual(job.pick_writer(), ("codex", None))
            members[:] = ["antigravity"]
            self.assertEqual(job.pick_writer(), ("antigravity", None))


if __name__ == "__main__":
    unittest.main()
