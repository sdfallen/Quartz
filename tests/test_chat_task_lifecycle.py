"""Task ownership tests use real disposable stores, never live accounts or input."""
from pathlib import Path
from copy import deepcopy
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from core.agent_chat import AgentChatService


class ChatTaskLifecycleTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.service = Mock()
        self.service.projects.selected.return_value = {"id":"fixture"}
        self.service.projects.get.return_value = {"id":"fixture", "path":folder.name}
        self.service._writer_status.return_value = {}
        self.service.pending_writer_runs.return_value = []
        self.service.get_run.return_value = {"status":"cancelled", "process_exit_confirmed":False}
        self.service.cancel.return_value = {"status":"cancelled", "process_exit_confirmed":False}
        self.chat = AgentChatService(self.service, Path(folder.name)/"chat.json")
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        self.addCleanup(self.chat._diagnostics.close)

    def wait_for(self, predicate):
        end = time.monotonic() + 3
        while not predicate():
            if time.monotonic() >= end:
                self.fail("Worker condition did not become observable")
            time.sleep(.005)

    def start_blocked_step(self, outcome="completed"):
        entered = threading.Event()
        calls = []
        def step(cid, mid, agent, prompt, project, write, confirm, full=False):
            calls.append((prompt, write, confirm, full, self.chat._active_turn["turn_id"]))
            if len(calls) == 1:
                entered.set()
                self.release.wait(3)
            if self.chat._is_turn_cancelled(mid): return
            self.chat._publish_run_update(cid, mid, "answer:"+prompt, {"status":outcome, "agent":agent})
            self.chat._finish_turn(mid, outcome)
        self.chat._run_chat_step = step
        first = self.chat.send_message("Dosyayı incele", agent="codex", write=True, confirm_write=True)
        self.assertTrue(entered.wait(2))
        return first, calls

    def test_followups_execute_once_in_order_with_frozen_authority(self):
        first, calls = self.start_blocked_step()
        cid = first["conversation_id"]
        second = self.chat.send_message("Sonucu kısa yaz", agent="codex", conversation_id=cid)
        third = self.chat.send_message("Test kanıtını da ekle", agent="codex", conversation_id=cid)
        self.assertTrue(second["queued"])
        self.assertEqual(third["queue_position"], 2)
        self.assertEqual(len(calls), 1)
        history = self.chat._format_history_context(self.chat.store.get(cid)["messages"])
        self.assertNotIn("Sonucu kısa yaz", history)
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertEqual([c[0] for c in calls], ["Dosyayı incele", "Sonucu kısa yaz", "Test kanıtını da ekle"])
        self.assertEqual(len({c[4] for c in calls}), 1)
        self.assertTrue(all(c[1:4] == (True, True, False) for c in calls))
        self.assertEqual(self.chat._active_turn["status"], "completed")
        for msg in self.chat.store.get(cid)["messages"]:
            self.assertEqual(msg["metadata"]["task_id"], calls[0][4])

    def test_failed_step_does_not_hide_error_or_execute_queued_work(self):
        first, calls = self.start_blocked_step(outcome="failed")
        queued = self.chat.send_message("Ek test", agent="codex", conversation_id=first["conversation_id"])
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.chat._active_turn["status"], "failed")
        messages = self.chat.store.get(first["conversation_id"])["messages"]
        self.assertEqual(messages[1]["content"], "answer:Dosyayı incele")
        self.assertEqual(next(m for m in messages if m["id"] == queued["assistant_message"]["id"])["status"], "cancelled")

    def test_stop_discards_queue_and_never_accepts_late_publication(self):
        first, calls = self.start_blocked_step()
        self.chat.send_message("Ek test", agent="codex", conversation_id=first["conversation_id"])
        result = self.chat.cancel_active()
        self.assertEqual(result["stop_receipt"]["status"], "pending")
        with self.assertRaises(RuntimeError): self.chat.send_message("Merhaba")
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertEqual(self.chat.poll_active()["stop_receipt"]["status"], "confirmed")
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.chat._publish_run_update(first["conversation_id"], first["assistant_message"]["id"],
                                                     "late", {"status":"completed"}))

    def test_scope_provider_and_conversation_cannot_expand_via_queue(self):
        first, _ = self.start_blocked_step()
        other = self.chat.store.create(title="Other", agent="codex")
        with self.assertRaises(RuntimeError):
            self.chat.send_message("Ek test", agent="codex", conversation_id=other["id"])
        with self.assertRaises(RuntimeError):
            self.chat.send_message("Ek test", agent="antigravity", conversation_id=first["conversation_id"])
        with self.assertRaises(PermissionError):
            self.chat.send_message("Dosyayı düzelt", agent="codex", conversation_id=first["conversation_id"],
                                   full_access=True, confirm_write=True)
        self.chat.cancel_active()
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))

    def test_cancelled_status_without_process_exit_is_not_a_stop_confirmation(self):
        cid = self.chat.store.get_active()["id"]
        self.chat._active_turn = {"turn_id":"task", "conversation_id":cid, "status":"running",
                                  "run_ids":["real-run"], "message_ids":[]}
        self.assertEqual(self.chat.cancel_active()["stop_receipt"]["status"], "pending")
        with self.assertRaises(RuntimeError): self.chat.send_message("Merhaba")
        self.service.get_run.return_value = {"status":"cancelled", "process_exit_confirmed":True}
        self.chat._refresh_stop_receipt()
        self.assertEqual(self.chat._active_turn["stop_receipt"]["status"], "confirmed")

    def test_cancel_failure_is_visible_and_keeps_admission_closed(self):
        cid = self.chat.store.get_active()["id"]
        self.chat._active_turn = {"turn_id":"task", "conversation_id":cid, "status":"running",
                                  "run_ids":["real-run"], "message_ids":[]}
        self.service.cancel.side_effect = OSError("private-provider-error")
        self.service.get_run.side_effect = OSError("private-provider-error")
        result = self.chat.cancel_active()
        self.assertEqual(result["stop_receipt"]["runs"]["real-run"]["error_type"], "OSError")
        self.assertNotIn("private-provider-error", str(result))
        self.assertEqual(self.chat.close()["status"], "pending")
        with self.assertRaises(RuntimeError): self.chat.send_message("Merhaba")

    def test_late_dispatch_after_stop_keeps_real_run_id_until_exit(self):
        entered = threading.Event()
        self.service.codex.probe.return_value = {"ready":True}
        def dispatch(*args, **kwargs):
            entered.set()
            self.release.wait(3)
            return {"run":{"id":"late-run"}}
        self.service.dispatch_codex.side_effect = dispatch
        first = self.chat.send_message("Dosyayı incele", agent="codex")
        self.assertTrue(entered.wait(2))
        self.assertEqual(self.chat.cancel_active()["stop_receipt"]["status"], "pending")
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertIn("late-run", self.chat._active_turn["run_ids"])
        self.service.cancel.assert_called_with("late-run")
        self.assertEqual(self.chat.poll_active()["stop_receipt"]["status"], "pending")
        self.service.get_run.return_value = {"status":"cancelled", "process_exit_confirmed":True}
        self.assertEqual(self.chat.poll_active()["stop_receipt"]["status"], "confirmed")
        self.assertEqual(self.chat.store.get(first["conversation_id"])["messages"][-1]["status"], "cancelled")

    def test_duplicate_stop_does_not_repeat_cancel_or_message_append(self):
        first, _ = self.start_blocked_step()
        self.chat.cancel_active()
        before = self.chat.store.get(first["conversation_id"])
        result = self.chat.cancel_active()
        self.assertFalse(result["cancelled"])
        self.assertEqual(self.chat.store.get(first["conversation_id"]), before)
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))

    def test_close_fences_new_work_even_when_diagnostics_cleanup_fails(self):
        self.chat._diagnostics.close = Mock(side_effect=OSError("offline"))
        with self.assertRaises(OSError): self.chat.close()
        with self.assertRaises(RuntimeError): self.chat.send_message("Merhaba")

    def test_old_worker_start_cannot_clear_new_worker_pending(self):
        self.chat._active_turn = {"turn_id":"new", "message_ids":["new-message"], "worker_pending":True}
        self.chat._run_chat_turn("old-cid", "old-message", "codex", "old", None, False, False)
        self.assertTrue(self.chat._active_turn["worker_pending"])

    def test_worker_start_failure_does_not_leave_a_running_ghost_task(self):
        with patch("core.agent_chat.threading.Thread.start", side_effect=RuntimeError("start failed")):
            with self.assertRaises(RuntimeError):
                self.chat.send_message("Dosyayı incele", agent="codex")
        self.assertFalse(self.chat._active_turn["worker_pending"])
        self.assertEqual(self.chat._active_turn["status"], "failed")
        self.assertEqual(self.chat.store.get_active()["messages"][-1]["status"], "failed")

    def test_restart_marks_queued_instructions_interrupted_without_replaying(self):
        from core.conversation_store import ConversationStore
        path = self.chat.store.path
        cid = self.chat.store.get_active()["id"]
        self.chat.store.append_message(cid, "user", "Do not silently replay", sender="user",
                                       metadata={"instruction_state":"queued"})
        self.chat.store.append_message(cid, "assistant", "", sender="codex",
                                       metadata={"status":"queued", "instruction_state":"queued"})
        restarted = ConversationStore(path)
        self.assertEqual(restarted.recover_interrupted()["status"], "recovered")
        messages = restarted.get(cid)["messages"]
        self.assertEqual(messages[-2]["metadata"]["instruction_state"], "interrupted")
        self.assertEqual(messages[-1]["status"], "interrupted")
        self.assertNotIn("Do not silently replay", self.chat._format_history_context(messages))
        self.service.dispatch_codex.assert_not_called()

    def test_failed_worker_cancels_unconfirmed_run_and_preserves_failure(self):
        entered = threading.Event()
        def step(cid, mid, *args):
            self.chat._set_turn_progress("Working", current_msg_id=mid, run_id="unconfirmed-run")
            self.chat._finish_turn(mid, "failed")
            entered.set()
        self.chat._run_chat_step = step
        self.chat.send_message("Dosyayı incele", agent="codex")
        self.assertTrue(entered.wait(2))
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.service.cancel.assert_called_with("unconfirmed-run")
        self.assertEqual(self.chat._active_turn["status"], "failed")
        self.assertEqual(self.chat._active_turn["stop_receipt"]["status"], "pending")

    def test_status_read_error_does_not_hide_pending_stop(self):
        first, _ = self.start_blocked_step()
        self.chat.cancel_active()
        with patch.object(self.chat.store, "get", side_effect=OSError("private-path")):
            result = self.chat.poll_active()
        self.assertEqual(result["stop_receipt"]["status"], "pending")
        self.assertNotIn("private-path", str(result))
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))

    def test_process_exit_does_not_hide_pending_writer_evidence(self):
        cid = self.chat.store.get_active()["id"]
        self.chat._active_turn = {"turn_id":"task", "conversation_id":cid, "status":"running",
                                  "run_ids":["writer-run"], "message_ids":[]}
        self.service.cancel.return_value = {"process_exit_confirmed":True}
        self.service.pending_writer_runs.return_value = ["writer-run"]
        result = self.chat.cancel_active()
        self.assertEqual(result["stop_receipt"]["status"], "pending")
        self.assertEqual(result["stop_receipt"]["writer_pending"], ["writer-run"])
        self.service.pending_writer_runs.return_value = []
        self.chat._refresh_stop_receipt()
        self.assertEqual(self.chat._active_turn["stop_receipt"]["status"], "confirmed")

    def test_followup_waits_for_existing_writer_claim_and_stop_can_interrupt_wait(self):
        first, calls = self.start_blocked_step()
        self.chat._set_turn_progress("writer", current_msg_id=first["assistant_message"]["id"], run_id="writer-run")
        self.service.pending_writer_runs.return_value = ["writer-run"]
        self.chat.send_message("Ek test", agent="codex", conversation_id=first["conversation_id"])
        self.release.set()
        self.wait_for(lambda: self.service.pending_writer_runs.called)
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.chat._active_turn["worker_pending"])
        self.chat.cancel_active()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertEqual(len(calls), 1)

    def test_store_failure_cannot_prevent_actual_provider_cancellation(self):
        first, _ = self.start_blocked_step()
        self.chat._set_turn_progress("Working", current_msg_id=first["assistant_message"]["id"], run_id="owned-run")
        self.service.cancel.return_value = {"status":"cancelled", "process_exit_confirmed":True}
        self.service.get_run.return_value = {"status":"cancelled", "process_exit_confirmed":True}
        with patch.object(self.chat.store, "update_message_content", side_effect=OSError("private-path")):
            result = self.chat.cancel_active()
        self.service.cancel.assert_called_with("owned-run")
        self.assertEqual(result["stop_receipt"]["history_error_type"], "OSError")
        self.assertNotIn("private-path", str(result))
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertEqual(self.chat.poll_active()["stop_receipt"]["status"], "failed")
        with self.assertRaises(RuntimeError): self.chat.send_message("Merhaba")
        self.assertEqual(self.chat.cancel_active()["stop_receipt"]["status"], "confirmed")

    def test_terminal_status_cannot_admit_new_work_before_failed_worker_finalizes(self):
        finalizing, finish = threading.Event(), threading.Event()
        original = self.chat._worker_finished
        def delayed_finalize(task_id):
            finalizing.set()
            finish.wait(3)
            original(task_id)
        self.chat._worker_finished = delayed_finalize
        def step(cid, mid, *args):
            self.chat._set_turn_progress("Working", current_msg_id=mid, run_id="old-live-run")
            self.chat._finish_turn(mid, "failed")
        self.chat._run_chat_step = step
        self.chat.send_message("Dosyayı incele", agent="codex")
        self.assertTrue(finalizing.wait(2))
        try:
            with self.assertRaises(RuntimeError): self.chat.send_message("Merhaba", agent="codex")
        finally:
            finish.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.service.cancel.assert_called_with("old-live-run")

    def test_partial_group_success_still_cleans_up_unconfirmed_provider(self):
        def step(cid, mid, *args):
            self.chat._set_turn_progress("Working", current_msg_id=mid, run_id="healthy-run")
            self.chat._set_turn_progress("Working", current_msg_id=mid, run_id="failed-provider-run")
            self.chat._finish_turn(mid, "completed")
        self.chat._run_chat_step = step
        self.service.get_run.side_effect = lambda rid: {"status":"completed" if rid == "healthy-run" else "running",
                                                       "process_exit_confirmed":rid == "healthy-run"}
        self.chat.send_message("Mimariyi incele", agent="collaboration")
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertEqual(self.chat._active_turn["status"], "completed")
        self.service.cancel.assert_called_once_with("failed-provider-run")
        self.assertEqual(self.chat._active_turn["stop_receipt"]["status"], "pending")

    def test_restart_excludes_dequeued_but_interrupted_instruction_from_new_prompt(self):
        from core.conversation_store import ConversationStore
        cid = self.chat.store.get_active()["id"]
        self.chat.store.append_message(cid, "user", "Never dispatched", sender="user",
                                       metadata={"instruction_state":"running"})
        self.chat.store.append_message(cid, "assistant", "", sender="codex",
                                       metadata={"status":"starting", "instruction_state":"running"})
        recovered = ConversationStore(self.chat.store.path)
        recovered.recover_interrupted()
        self.assertNotIn("Never dispatched", self.chat._format_history_context(recovered.get(cid)["messages"]))

    def test_unknown_post_start_failure_cannot_claim_empty_run_list_is_clean(self):
        from core.multi_agent_service import WriterDispatchError
        self.service.codex.probe.return_value = {"ready":True}
        self.service.dispatch_codex.side_effect = WriterDispatchError("codex", "unresolved-claim")
        self.chat.send_message("Dosyayı incele", agent="codex")
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertEqual(self.chat._active_turn["run_ids"], [])
        self.assertEqual(self.chat.close()["status"], "pending")
        self.assertEqual(self.chat._active_turn["stop_receipt"]["unresolved_dispatch"], ["unresolved-claim"])

    def test_known_run_from_post_start_failure_is_not_lost(self):
        from core.multi_agent_service import WriterDispatchError
        self.service.codex.probe.return_value = {"ready":True}
        self.service.dispatch_codex.side_effect = WriterDispatchError("codex", "claim", "spawned-run")
        self.chat.send_message("Dosyayı incele", agent="codex")
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        self.assertIn("spawned-run", self.chat._active_turn["run_ids"])
        self.service.cancel.assert_called_with("spawned-run")
        self.assertEqual(self.chat.close()["status"], "pending")

    def test_writer_readback_error_does_not_erase_completed_step_output(self):
        first, _ = self.start_blocked_step()
        self.chat._set_turn_progress("writer", current_msg_id=first["assistant_message"]["id"], run_id="writer-run")
        self.service.pending_writer_runs.side_effect = OSError("private-disk")
        self.chat.send_message("Ek test", agent="codex", conversation_id=first["conversation_id"])
        self.release.set()
        self.wait_for(lambda: not self.chat._active_turn.get("worker_pending"))
        message = self.chat.store.get(first["conversation_id"])["messages"][1]
        self.assertEqual(message["content"], "answer:Dosyayı incele")
        self.assertEqual(message["status"], "completed")
        self.assertEqual(self.chat._active_turn["status"], "failed")


class WriterClaimReadbackTests(unittest.TestCase):
    def test_durable_unreleased_claim_outlives_watcher_and_still_blocks_readback(self):
        from core.multi_agent_service import MultiAgentService
        from core.writer_journal import WriterJournal
        with tempfile.TemporaryDirectory() as folder:
            service = MultiAgentService.__new__(MultiAgentService)
            service._lock = threading.RLock()
            service._writers, service._writer_threads, service._links = {}, {}, {}
            service._writer_journal = WriterJournal(Path(folder)/"claims.json")
            claim = service._writer_journal.reserve(folder, False, "codex")
            service._writer_journal.update(claim, stage="active", run_id="writer-run")
            self.assertEqual(service.pending_writer_runs(["writer-run"]), ["writer-run"])
            service._writer_journal.error = "unreadable"
            with self.assertRaises(RuntimeError): service.pending_writer_runs(["writer-run"])

    def test_journal_failure_after_runtime_start_preserves_spawned_run_ownership(self):
        from core.multi_agent_service import MultiAgentService, WriterDispatchError
        from core.writer_journal import WriterJournal
        with tempfile.TemporaryDirectory() as folder:
            service = MultiAgentService.__new__(MultiAgentService)
            service._lock = threading.RLock()
            service._writers, service._writer_threads, service._links = {}, {}, {}
            service._writer_journal = WriterJournal(Path(folder)/"claims.json")
            service.codex = Mock()
            service.codex.start.return_value = {"id":"spawned-run"}
            original = service._writer_journal.update
            def fail_active(claim, **kwargs):
                if kwargs["stage"] == "active": raise OSError("disk blocked")
                return original(claim, **kwargs)
            project = {"id":"fixture", "path":folder}
            with patch.object(service._writer_journal, "update", side_effect=fail_active), \
                    patch("core.multi_agent_service.create_checkpoint", return_value={"status":"snapshot", "complete":True, "archive":"fixture-only"}), \
                    patch("core.multi_agent_service.snapshot_workspace_files", return_value={}):
                with self.assertRaises(WriterDispatchError) as result:
                    service._start_writer("codex", project, service.codex.start, "prompt", folder)
            self.assertEqual(result.exception.run_id, "spawned-run")
            service.codex.cancel.assert_called_once_with("spawned-run")
            self.assertEqual(service._links["spawned-run"]["provider"], "codex")
            self.assertEqual(service.pending_writer_runs(["spawned-run"]), ["spawned-run"])


class ConversationReadBoundaryTests(unittest.TestCase):
    def setUp(self):
        from core.conversation_store import ConversationStore
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = ConversationStore(Path(folder.name)/"chat.json")
        self.cid = self.store.get_active()["id"]

    def test_conversation_views_cannot_mutate_authoritative_messages_or_models(self):
        for read in (self.store.get_active, lambda: self.store.get(self.cid), lambda: self.store.select(self.cid)):
            with self.subTest(reader=read):
                before = deepcopy(self.store.get(self.cid))
                view = read()
                view["messages"].append({"content":"unsaved mutation"})
                view["models"]["codex"]["model"] = "not-the-selected-model"
                self.assertEqual(self.store.get(self.cid), before)

    def test_appended_message_and_input_metadata_are_detached(self):
        metadata = {"progress":["first"]}
        message = self.store.append_message(self.cid, "assistant", "original", sender="codex", metadata=metadata)
        metadata["progress"].append("external input mutation")
        message["content"] = "external result mutation"
        message["metadata"]["progress"].append("external nested mutation")
        stored = self.store.get(self.cid)["messages"][-1]
        self.assertEqual(stored["content"], "original")
        self.assertEqual(stored["metadata"]["progress"], ["first"])

    def test_passive_poll_evidence_does_not_enter_saved_history(self):
        service = Mock()
        service.run_evidence.return_value = {"files_changed":["test.py"]}
        chat = AgentChatService(service, self.store.path)
        self.addCleanup(chat._diagnostics.close)
        chat.store.append_message(self.cid, "assistant", "done", metadata={"run_id":"r"})
        before = deepcopy(chat.store.get(self.cid))
        view = chat.store.get(self.cid)
        chat._enrich_messages(view["messages"])
        self.assertIn("host_evidence", view["messages"][-1]["metadata"])
        self.assertEqual(chat.store.get(self.cid), before)
