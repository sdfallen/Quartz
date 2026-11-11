from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.atomic_json import atomic_write_json, load_json
from core.notion_cli import NotionError
from core.notion_runtime import NotionRuntime
from core.agent_chat import AgentChatService
from core.multi_agent_service import MultiAgentService

WORKSPACE = "10000000-0000-0000-0000-000000000001"
AGENT = "20000000-0000-0000-0000-000000000001"
SESSION = "30000000-0000-0000-0000-000000000001"
OTHER = "40000000-0000-0000-0000-000000000001"


def session(status="completed", **values):
    return {"object": "session", "id": SESSION, "agent_id": AGENT, "status": status, **values}


def event(seq=2, text="Notion yanıtı", **values):
    return {"id": str(seq), "sequence": seq, "type": "agent.message",
            "content": [{"type": "text", "text": text}], **values}


def wait(runtime, rid):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        run = runtime.get(rid)
        if run["status"] in runtime.TERMINAL:
            return run
        time.sleep(0.005)
    raise AssertionError("worker did not terminate")


class NotionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = MagicMock()
        self.client.agents.return_value = [{"id": AGENT, "name": "Test ajanı"}]
        self.runtime = NotionRuntime(home=self.tmp.name, transport_factory=lambda w: self.client, poll_interval=0.005)
        self.runtime.configure(WORKSPACE, AGENT)
        self.client.request.side_effect = self.reply

    def reply(self, path, body=None):
        if path.endswith("/events/query"):
            return {"results": [event(), event()], "has_more": False}
        return session()

    def test_real_session_protocol_filters_user_events_and_duplicates(self):
        run = wait(self.runtime, self.runtime.start("Merhaba")["id"])
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["result"], "Notion yanıtı")
        self.assertEqual(run["session_id"], SESSION)
        self.assertFalse(run["local_tools"])
        self.assertTrue(self.runtime._owned(SESSION, self.runtime.configuration()))
        self.assertEqual(self.client.request.call_args_list[0].args, ("v1/sessions", {"message": "Merhaba", "agent_id": AGENT}))
        self.assertNotIn("Merhaba", (Path(self.tmp.name) / "sessions" / (SESSION + ".json")).read_text())

    def test_continue_only_owned_session_and_do_not_replay_old_answer(self):
        self.runtime._remember(SESSION, self.runtime.configuration())
        events_calls = []
        def reply(path, body=None):
            if path.endswith("/events/query"):
                events_calls.append(path)
                return {"results": [event(2, "old")] if len(events_calls) == 1 else
                        [event(2, "old"), event(4, "new"), event(3, "user", type="user.message")], "has_more": False}
            return session()
        self.client.request.side_effect = reply
        run = wait(self.runtime, self.runtime.start("followup", session_id=SESSION)["id"])
        self.assertEqual(run["result"], "new")
        self.assertIn({"session_id": SESSION, "message": "followup"}, [c.args[1] for c in self.client.request.call_args_list if len(c.args) > 1])

    def test_session_scope_and_foreign_agent_mismatch_are_rejected(self):
        with self.assertRaises(PermissionError):
            self.runtime.start("test", session_id=OTHER)
        self.runtime._remember(SESSION, self.runtime.configuration())
        self.client.request.side_effect = lambda *a: session(agent_id=OTHER)
        run = wait(self.runtime, self.runtime.start("test", session_id=SESSION)["id"])
        self.assertEqual(run["status"], "failed")
        self.assertFalse(any(c.args[0] == "v1/sessions" for c in self.client.request.call_args_list))

    def test_create_timeout_is_not_retried_or_auto_fallback(self):
        self.client.request.side_effect = NotionError("timeout", uncertain=True)
        run = wait(self.runtime, self.runtime.start("test")["id"])
        self.assertEqual(run["status"], "failed")
        self.assertTrue(run["remote_uncertain"])
        self.assertEqual(self.client.request.call_count, 1)

    def test_requires_action_is_blocked_never_autoapproved(self):
        def reply(path, body=None):
            return self.reply(path, body) if path.endswith("/events/query") else session("requires_action")
        self.client.request.side_effect = reply
        run = wait(self.runtime, self.runtime.start("test")["id"])
        self.assertEqual(run["status"], "blocked")
        self.assertTrue(run["required_actions"])
        self.client.request.side_effect = lambda *a: session("canceled")
        self.runtime.cancel(run["id"])
        self.assertEqual(wait(self.runtime, run["id"])["status"], "cancelled")
        self.assertFalse(any("approve" in str(c) for c in self.client.request.call_args_list))

    def test_polled_foreign_session_is_not_accepted(self):
        def reply(path, body=None):
            if path == "v1/sessions":
                return session("queued")
            if path.endswith("/events/query"):
                return {"results": [], "has_more": False}
            return session(id=OTHER)
        self.client.request.side_effect = reply
        run = wait(self.runtime, self.runtime.start("test")["id"])
        self.assertEqual(run["status"], "failed")
        self.assertTrue(run["remote_uncertain"])

    def test_completed_with_no_new_text_is_not_success(self):
        self.client.request.side_effect = lambda path, body=None: {"results": [], "has_more": False} if path.endswith("/events/query") else session()
        run = wait(self.runtime, self.runtime.start("test")["id"])
        self.assertEqual(run["status"], "failed")
        self.assertFalse(run["remote_uncertain"])

    def test_stop_during_submit_cancels_returned_remote_handle_once(self):
        entered, release = threading.Event(), threading.Event()
        def reply(path, body=None):
            if path == "v1/sessions":
                entered.set()
                release.wait(2)
                return session("queued")
            if path.endswith("/cancel"):
                return session("canceled")
            return self.reply(path, body)
        self.client.request.side_effect = reply
        rid = self.runtime.start("test")["id"]
        self.assertTrue(entered.wait(1))
        self.assertEqual(self.runtime.cancel(rid)["status"], "cancelling")
        release.set()
        run = wait(self.runtime, rid)
        self.assertEqual(run["status"], "cancelled")
        self.runtime.cancel(rid)
        self.assertEqual(sum(c.args[0].endswith("/cancel") for c in self.client.request.call_args_list), 1)

    def test_timeout_requests_remote_stop_without_claiming_unconfirmed_success(self):
        runtime = NotionRuntime(home=self.tmp.name, transport_factory=lambda w: self.client, timeout=0)
        self.client.request.side_effect = lambda *a: session("in_progress")
        run = wait(runtime, runtime.start("test")["id"])
        self.assertEqual(run["status"], "failed")
        self.assertTrue(run["remote_uncertain"])
        self.assertTrue(any(c.args[0].endswith("/cancel") for c in self.client.request.call_args_list))

    def test_busy_configuration_and_second_task_are_rejected(self):
        entered, release = threading.Event(), threading.Event()
        def reply(path, body=None):
            if path == "v1/sessions":
                entered.set()
                release.wait(2)
            return self.reply(path, body)
        self.client.request.side_effect = reply
        rid = self.runtime.start("one")["id"]
        self.assertTrue(entered.wait(1))
        with self.assertRaises(RuntimeError):
            self.runtime.start("two")
        with self.assertRaises(RuntimeError):
            self.runtime.configure(WORKSPACE, AGENT)
        release.set()
        self.assertEqual(wait(self.runtime, rid)["status"], "completed")

    def test_transport_factory_failure_always_ends_run(self):
        runtime = NotionRuntime(home=self.tmp.name, transport_factory=lambda w: (_ for _ in ()).throw(RuntimeError("sensitive")))
        run = wait(runtime, runtime.start("test")["id"])
        self.assertEqual(run["status"], "failed")
        self.assertNotIn("sensitive", run["error"])

    def test_profile_only_saves_explicit_accessible_selection(self):
        self.assertEqual(set(load_json(Path(self.tmp.name) / "connection.json", {})), {"workspace_id", "agent_id", "agent_name"})
        with self.assertRaises(ValueError):
            self.runtime.configure(WORKSPACE, OTHER)
        self.assertEqual(self.runtime.configuration()["agent_id"], AGENT)


class NotionChatTests(unittest.TestCase):
    def test_chat_prefix_routes_remote_response_and_preserves_existing_models(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MagicMock()
            service.notion.configuration.return_value = {"workspace_id": WORKSPACE, "agent_id": AGENT}
            run = {"id": "notion-test", "status": "completed", "result": "Bulut yanıtı", "session_id": SESSION}
            service.dispatch_notion.return_value = {"run": run}
            service.notion.get.return_value = run
            service.notion.TERMINAL = NotionRuntime.TERMINAL
            chat = AgentChatService(service, Path(directory) / "chat.json")
            before = chat.store.get_active()["models"]
            result = chat.send_message("@notion Merhaba", agent="codex")
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and chat._active_turn["status"] == "running":
                time.sleep(0.005)
            self.assertEqual(chat._active_turn["status"], "completed")
            service.dispatch_notion.assert_called_once_with("Merhaba", session_id=None)
            service.dispatch_codex.assert_not_called()
            service.dispatch_antigravity.assert_not_called()
            conv = chat.store.get(result["conversation_id"])
            self.assertEqual(conv["models"], before)
            self.assertEqual(conv["agent"], "antigravity")
            self.assertEqual(conv["messages"][-1]["sender"], "notion")
            self.assertEqual(conv["messages"][-1]["content"], "Bulut yanıtı")
            self.assertEqual(conv["sessions"][f"notion:{WORKSPACE}:{AGENT}"], SESSION)

    def test_service_dispatch_and_cancel_use_notion_not_codex(self):
        service = MultiAgentService.__new__(MultiAgentService)
        service._lock = threading.RLock()
        service._links, service._file_changes = {}, {}
        service._notion = MagicMock()
        service._notion.start.return_value = {"id": "n-run"}
        service.codex = MagicMock()
        service.dispatch("notion", "test", project_id="local-project", write=True)
        service._notion.start.assert_called_once_with("test", session_id=None)
        service.cancel("n-run")
        service._notion.cancel.assert_called_once_with("n-run")
        service.codex.cancel.assert_not_called()
        service.get_run("n-run")
        service._notion.get.assert_called_once_with("n-run")


if __name__ == "__main__":
    unittest.main()
