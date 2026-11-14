"""Research answers become cards in Sohbet and Workspace (14 Nov 2026)."""
import json
import tempfile
import unittest

from tests.test_team_turn import TeamRun, make_chat

CARD_REPLY = ("Üç uygun iş buldum.\n```spes-kartlar\n"
              + json.dumps([{"title": "React ile kafe sitesi", "description": "Tek sayfa, 1 hafta.",
                             "url": "https://ornek.com/is/1", "source": "Bionluk"}], ensure_ascii=False)
              + "\n```")
ASK = "İnternette React bilen freelancer arayan işleri araştırın ve en uygunlarını liste halinde getirin"


class CardsChatTests(unittest.TestCase):
    def test_research_is_a_web_answer_by_the_lead_with_cards(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            cid = chat.new_conversation(agent="collaboration", space="work")["id"]
            run = TeamRun(chat)
            run.reply = CARD_REPLY
            run.run(ASK, write=True, confirm_write=True, full_access=True)
            messages = chat.store.get(cid)["messages"]
            chat._diagnostics.close()
        self.assertEqual([c["agent"] for c in run.calls], ["claude"])  # one researched answer
        call = run.calls[0]
        self.assertTrue(call["tool_less"] and not call["write"] and call["web"])
        self.assertIn("ARAŞTIRMA", call["prompt"])  # the card rule itself comes with the communication prompt
        user = next(m for m in messages if m["role"] == "user")
        self.assertTrue(user["metadata"].get("research"))
        self.assertNotIn("space_hint", user["metadata"])

    def test_published_reply_keeps_cards_out_of_the_text(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            cid = chat.new_conversation(agent="claude", space="chat")["id"]
            msg = chat.store.append_message(cid, "assistant", "", sender="claude", metadata={"status": "running"})
            chat._active_turn = {"conversation_id": cid, "status": "running", "message_ids": [msg["id"]],
                                 "turn_id": "t", "project_id": None}
            self.assertTrue(chat._publish_run_update(cid, msg["id"], CARD_REPLY,
                                                     {"status": "completed", "agent": "claude"}))
            stored = next(m for m in chat.store.get(cid)["messages"] if m["id"] == msg["id"])
            # A half-streamed block is hidden, never shown as JSON.
            chat._publish_run_update(cid, msg["id"], 'Bakıyorum\n```spes-kartlar\n[{"title": "ya',
                                     {"status": "running", "agent": "claude"})
            streaming = next(m for m in chat.store.get(cid)["messages"] if m["id"] == msg["id"])
            chat._diagnostics.close()
        self.assertEqual(stored["content"], "Üç uygun iş buldum.")
        self.assertEqual(stored["metadata"]["cards"][0]["source"], "Bionluk")
        self.assertEqual(streaming["content"], "Bakıyorum")

    def test_a_request_about_local_files_stays_work(self):
        from core.result_cards import is_research
        self.assertFalse(is_research("Projedeki testleri bul ve listele"))
        self.assertTrue(is_research(ASK))


if __name__ == "__main__":
    unittest.main()
