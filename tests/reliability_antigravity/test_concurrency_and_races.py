"""Reliability tests for concurrency, socket resilience, and race conditions.
Covers:
- F-04: Ephemeral HTTP server socket disconnect resilience during header flush.
- F-05: Parallel collaboration turn progress race overwriting scalar message_id and progress_step.
"""
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

from core.natural_desktop import NaturalDesktopTask
from core.agent_chat import AgentChatService


class ConcurrencyAndRacesReliabilityTests(unittest.TestCase):
    """Tests verifying socket crash resilience and multi-agent progress race conditions."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_ephemeral_server_resilient_to_client_disconnect(self):
        """F-04 VERIFICATION: Verifies that client disconnect during header flush does not escape unhandled.

        When a CLI subprocess or remote client abruptly closes the TCP socket during response generation,
        writing to the socket raises BrokenPipeError or ConnectionResetError (WinError 10054).
        The HTTP server handler must guard all header writing and body transmission within a try/except block.
        """
        task = NaturalDesktopTask(Mock(), Mock(), factories={}, evidence_root=self.root)
        task._serve()
        HandlerCls = task.server.RequestHandlerClass

        class BrokenSocketWriter(io.BytesIO):
            def write(self, b):
                raise ConnectionResetError("[WinError 10054] Client disconnected during transmission")

        handler = HandlerCls.__new__(HandlerCls)
        handler.connection = Mock()
        handler.path = "/tool"
        handler.headers = {"Content-Length": "2", "Authorization": "Bearer test"}
        handler.rfile = io.BytesIO(b"{}")
        handler.wfile = BrokenSocketWriter()
        handler._headers_buffer = []
        handler.requestline = "POST /tool HTTP/1.1"
        handler.request_version = "HTTP/1.1"
        handler.command = "POST"

        try:
            # Must safely absorb ConnectionResetError without raising to ThreadingHTTPServer
            handler.do_POST()
        except ConnectionResetError as exc:
            self.fail(f"F-04 Defect: ConnectionResetError escaped do_POST unhandled: {exc}")
        finally:
            task.server.shutdown()
            task.server.server_close()

    def test_reproduce_f05_collaboration_turn_progress_race(self):
        """F-05 RISK REPRODUCTION: Parallel agent execution causes progress_step and message_id to clobber each other.

        In core/agent_chat.py:597 (_set_turn_progress):
            self._active_turn["progress_step"] = step_text
            if current_msg_id:
                self._active_turn["message_id"] = current_msg_id

        Because _active_turn stores a single scalar message_id and progress_step,
        two threads running concurrently (Codex and Antigravity) overwrite each other.
        poll_active() only reports whichever agent wrote last, starving the other bubble.
        """
        agent_svc = Mock()
        agent_svc.projects.selected.return_value = {"id": "p1", "path": str(self.root)}
        agent_svc.projects.get.return_value = {"id": "p1", "path": str(self.root)}
        store_path = self.root / "conv.json"
        chat = AgentChatService(agent_svc, store_path)
        conv = chat.new_conversation(title="Test Turn", agent="collaboration")
        cid = conv["id"]

        owner_id = "turn-owner-msg-1"
        chat._active_turn = {
            "conversation_id": cid,
            "status": "running",
            "owner_msg_id": owner_id,
            "message_ids": [owner_id],
            "message_id": owner_id,
            "run_id": None,
            "progress_step": "Başlatılıyor...",
            "run_ids": [],
        }

        # Step 1: Agent 1 (Codex) reports progress
        chat._set_turn_progress("Codex yanıtlıyor...", current_msg_id="msg-codex-1", owner_msg_id=owner_id)
        self.assertEqual(chat._active_turn["message_id"], "msg-codex-1")
        self.assertEqual(chat._active_turn["progress_step"], "Codex yanıtlıyor...")

        # Step 2: Agent 2 (Antigravity) concurrently reports progress
        chat._set_turn_progress("Antigravity yanıtlıyor...", current_msg_id="msg-agy-1", owner_msg_id=owner_id)

        # DEFECT / RACE CONFIRMED:
        # Codex's message_id and progress step were completely overwritten in the active turn state.
        self.assertEqual(
            chat._active_turn["message_id"],
            "msg-agy-1",
            "Race confirmed: Antigravity's message_id overwrote Codex's message_id",
        )
        self.assertEqual(
            chat._active_turn["progress_step"],
            "Antigravity yanıtlıyor...",
            "Race confirmed: Antigravity's progress_step overwrote Codex's progress_step",
        )

        # poll_active() only returns Antigravity's scalar state; Codex's progress is invisible to the UI poller
        active = chat.poll_active()
        self.assertEqual(active["message_id"], "msg-agy-1")
        self.assertNotIn("msg-codex-1", active["message_id"])

    def test_contract_f05_collaboration_turn_should_track_per_agent_progress(self):
        """CONTRACT TEST: A multi-agent turn must track concurrent agent progress in structured state.

        Codex follow-up: promoted from expectedFailure after per-agent progress was added.
        """
        agent_svc = Mock()
        store_path = self.root / "conv.json"
        chat = AgentChatService(agent_svc, store_path)

        owner_id = "turn-owner-msg-1"
        chat._active_turn = {
            "conversation_id": "conv-1",
            "status": "running",
            "owner_msg_id": owner_id,
            "message_ids": [owner_id],
            "agent_progress": {},
        }

        # Expected contract: agent-keyed progress preserves both updates
        chat._set_turn_progress("Codex çalışıyor...", current_msg_id="msg-c", agent="codex", owner_msg_id=owner_id)
        chat._set_turn_progress("Antigravity inceliyor...", current_msg_id="msg-a", agent="antigravity", owner_msg_id=owner_id)

        self.assertIn("codex", chat._active_turn.get("agent_progress", {}))
        self.assertIn("antigravity", chat._active_turn.get("agent_progress", {}))


if __name__ == "__main__":
    unittest.main()
