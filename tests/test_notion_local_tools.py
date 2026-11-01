import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.notion_local_tools import NotionLocalTools
from core.desktop_broker import DesktopBroker
from tests.test_desktop_broker import FakeBackend


class LocalToolTests(unittest.TestCase):
    def setUp(self):
        self.now = 10
        self.handler = Mock(return_value={"text": "observed"})
        self.authorize = Mock(return_value=True)
        self.cancel = Mock()
        self.gate = self.make_gate()

    def make_gate(self, **extra):
        options = dict(task_id="task-1", session_id="session-1", project_id="project-1",
                       scope_ref="local-scope-1", tools={"project_read": self.handler},
                       authorize=self.authorize, expires_at=100, clock=lambda: self.now,
                       enabled=True, cancel=self.cancel)
        return NotionLocalTools(**{**options, **extra})

    def request(self, **extra):
        return {"schema_version": 1, "task_id": "task-1", "session_id": "session-1",
                "project_id": "project-1", "scope_ref": "local-scope-1", "request_id": "r1",
                "tool_name": "project_read", "arguments": {"path": "test.txt"},
                "deadline": 50, **extra}

    def test_default_closed_and_no_raw_text_execution(self):
        self.assertEqual(self.make_gate(enabled=False).call(self.request())["status"], "blocked")
        for value in ("```json\n{}\n```", [], None):
            with self.assertRaises(ValueError): self.gate.call(value)
        self.handler.assert_not_called()

    def test_scope_and_schema_are_not_model_grants(self):
        for key in ("task_id", "session_id", "project_id", "scope_ref", "tool_name"):
            with self.subTest(key=key), self.assertRaises(PermissionError):
                self.gate.call(self.request(**{key: "foreign"}))
        for fields in ({"token": "model-token"}, {"schema_version": True},
                       {"arguments": "open anything"}, {"deadline": float("inf")}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.gate.call(self.request(**fields))
        self.handler.assert_not_called()

    def test_replay_returns_receipt_not_a_second_execution(self):
        first = self.gate.call(self.request())
        first["result"]["text"] = "changed by caller"
        second = self.gate.call(self.request())
        self.assertEqual(second["result"], {"text": "observed"})
        self.assertEqual(second["verification"], "none")
        self.handler.assert_called_once()
        self.authorize.assert_called_once()
        with self.assertRaises(PermissionError):
            self.gate.call(self.request(arguments={"path": "different.txt"}))

    def test_revoked_scope_and_pending_permission_do_not_execute(self):
        for approved in (False, None, "approved", {"pending": True}):
            self.authorize.return_value = approved
            self.assertEqual(self.make_gate().call(self.request())["status"], "blocked")
        self.handler.assert_not_called()

    def test_deadline_never_extends_local_expiry(self):
        self.now = 101
        self.assertEqual(self.gate.call(self.request(deadline=9999))["status"], "blocked")
        self.handler.assert_not_called()

    def test_expired_request_and_expiry_during_authorization(self):
        self.assertEqual(self.gate.call(self.request(deadline=9))["status"], "blocked")
        def late(*_):
            self.now = 100
            return True
        self.authorize.side_effect = late
        self.assertEqual(self.gate.call(self.request())["status"], "blocked")
        self.handler.assert_not_called()

    def test_exceptions_are_redacted_and_ambiguous_execution_is_not_retried(self):
        self.handler.side_effect = RuntimeError("secret bearer and user path")
        first = self.gate.call(self.request())
        self.assertTrue(first["uncertain"])
        self.assertNotIn("bearer", str(first))
        self.assertEqual(self.gate.call(self.request()), first)
        self.handler.assert_called_once()

    def test_authorization_exception_does_not_report_a_side_effect(self):
        self.authorize.side_effect = RuntimeError("secret")
        self.assertFalse(self.gate.call(self.request())["uncertain"])
        self.handler.assert_not_called()

    def test_stop_in_authorization_blocks_handler(self):
        def stop(*_):
            self.gate.stop()
            return True
        self.authorize.side_effect = stop
        self.assertEqual(self.gate.call(self.request())["status"], "cancelled")
        self.handler.assert_not_called()

    def test_stop_is_idempotent_and_late_result_is_not_success(self):
        entered, release = threading.Event(), threading.Event()
        def delayed(args, stopped):
            entered.set()
            release.wait(2)
            self.assertTrue(stopped.is_set())
            return {"text": "late data must not be published"}
        self.handler.side_effect = delayed
        outcomes = []
        worker = threading.Thread(target=lambda: outcomes.append(self.gate.call(self.request())))
        worker.start()
        self.assertTrue(entered.wait(2))
        try:
            self.assertEqual(self.gate.call(self.request())["status"], "executing")
            self.assertEqual(self.gate.call(self.request(request_id="r2"))["status"], "blocked")
            self.gate.stop()
            self.gate.stop()
            self.cancel.assert_called_once()
            self.assertEqual(self.gate.call(self.request(request_id="r3"))["status"], "blocked")
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes[0]["status"], "cancelled")
        self.assertNotIn("result", outcomes[0])

    def test_expiry_after_handler_does_not_claim_completion(self):
        def late(*_):
            self.now = 60
            return {"text": "possibly applied"}
        self.handler.side_effect = late
        reply = self.gate.call(self.request())
        self.assertEqual(reply["status"], "failed")
        self.assertTrue(reply["uncertain"])

    def test_receipts_are_not_evicted_to_allow_reexecution(self):
        gate = self.make_gate(max_receipts=1)
        gate.call(self.request())
        self.assertEqual(gate.call(self.request(request_id="r2"))["status"], "blocked")
        gate.call(self.request())
        self.handler.assert_called_once()

    def test_missing_revoke_is_not_verified(self):
        self.assertFalse(self.make_gate(cancel=None).stop()["owner_revocation_verified"])
        self.assertFalse(self.make_gate(cancel=Mock()).stop()["owner_revocation_verified"])
        self.assertTrue(self.make_gate(cancel=lambda: True).stop()["owner_revocation_verified"])
        bad = self.make_gate(cancel=Mock(side_effect=RuntimeError("private details")))
        self.assertFalse(bad.stop()["owner_revocation_verified"])

    def test_real_disposable_file_read_does_not_expand_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.txt"
            path.write_text("fixture result", encoding="utf-8")
            def allowed(name, args):
                return args == {"path": "test.txt"}
            def read(args, stopped):
                if stopped.is_set(): raise PermissionError()
                return {"text": path.read_text(encoding="utf-8")}
            gate = self.make_gate(tools={"project_read": read}, authorize=allowed)
            self.assertEqual(gate.call(self.request())["result"]["text"], "fixture result")
            rejected = gate.call(self.request(request_id="r2", arguments={"path": "../other"}))
            self.assertEqual(rejected["status"], "blocked")


class BrokerIntegrationTests(unittest.TestCase):
    """Real broker and gate, fake desktop backend: NOT a Windows GUI acceptance."""

    def setUp(self):
        self.backend = FakeBackend()
        self.broker = DesktopBroker(self.backend)
        self.addCleanup(self.broker.close)
        self.connection = self.broker.grant(1, "notion", confirmed=True)
        def revoke():
            self.broker.stop("notion task stopped")
            return not self.broker.status()["active"]
        def call(name):
            def handler(args, stopped):
                if stopped.is_set(): raise PermissionError("stopped")
                return self.broker.call(self.connection["token"], {"name": name, "arguments": args})
            return handler
        self.gate = NotionLocalTools(task_id="t", session_id="s", project_id="p", scope_ref="local",
            tools={name: call(name) for name in ("desktop_focus", "desktop_observe", "desktop_act")},
            authorize=lambda name, args: self.broker.status()["active"],
            expires_at=100, clock=lambda: 10, enabled=True, cancel=revoke)

    def call(self, rid, tool, **args):
        return self.gate.call(dict(schema_version=1, task_id="t", session_id="s", project_id="p",
            scope_ref="local", request_id=rid, tool_name=tool, arguments=args, deadline=50))

    def test_existing_one_operator_confirmation_and_revoke_remain(self):
        self.assertEqual(self.broker.status()["provider"], "notion")
        with self.assertRaises(RuntimeError): self.broker.grant(1, "codex", confirmed=True)
        self.assertTrue(self.gate.stop()["owner_revocation_verified"])
        with self.assertRaises(PermissionError): self.broker.grant(1, "notion", confirmed=False)
        result = self.call("stopped", "desktop_act", action="key", key="tab", snapshot_id="old")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.backend.actions, [])

    def test_fresh_snapshot_and_duplicate_action_use_existing_broker(self):
        first = self.call("focus", "desktop_focus")
        args = dict(snapshot_id=first["result"]["snapshot_id"], action="key", key="tab")
        acted = self.call("act", "desktop_act", **args)
        self.assertEqual(acted["status"], "completed")
        self.assertFalse(acted["result"]["goal_verified"])
        self.assertEqual(self.call("act", "desktop_act", **args), acted)
        self.assertEqual(len(self.backend.actions), 1)
        rejected = self.call("stale", "desktop_act", **args)
        self.assertEqual(rejected["status"], "failed")
        self.assertEqual(len(self.backend.actions), 1)

    def test_changed_process_identity_revokes_instead_of_rebinding(self):
        self.call("focus", "desktop_focus")
        self.backend.target["pid"] += 1
        result = self.call("changed", "desktop_observe")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(self.broker.status()["active"])
        self.assertEqual(self.backend.actions, [])


if __name__ == "__main__":
    unittest.main()
