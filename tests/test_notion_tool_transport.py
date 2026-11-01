"""Tests for Notion Custom Agent local tool transport adapter."""
from __future__ import annotations

import time
import unittest
import uuid
from unittest.mock import MagicMock

from core.notion_tool_transport import (
    DEFAULT_MAX_PAYLOAD_BYTES,
    NotionToolRequest,
    NotionToolResult,
    NotionToolTransport,
    ReplayError,
    SCHEMA_VERSION,
    SessionMismatchError,
    ValidationError,
    format_continuation_message,
)


def _make_valid_payload(**overrides):
    base = {
        "schema_version": SCHEMA_VERSION,
        "task_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "request_id": f"req-{uuid.uuid4().hex[:8]}",
        "tool_name": "read_file",
        "arguments": {"path": "example.txt"},
        "project_id": "proj-alpha",
        "scope_ref": "workspace",
        "deadline": time.monotonic() + 30.0,
    }
    base.update(overrides)
    return base


class NotionToolTransportTests(unittest.TestCase):
    def test_valid_request_dispatch_executes_injected_router(self):
        payload = _make_valid_payload()
        called_requests = []

        def fake_router(req: NotionToolRequest) -> dict:
            called_requests.append(req)
            return {"output": {"content": "file contents"}, "status": "completed", "verification": "verified"}

        transport = NotionToolTransport(fake_router)
        res = transport.dispatch(payload)

        self.assertEqual(res.status, "completed")
        self.assertEqual(res.request_id, payload["request_id"])
        self.assertEqual(res.session_id, payload["session_id"])
        self.assertEqual(res.output, {"content": "file contents"})
        self.assertEqual(res.verification, "verified")
        self.assertGreaterEqual(res.duration_ms, 0.0)
        self.assertEqual(len(called_requests), 1)

    def test_malformed_event_validation_rejections(self):
        transport = NotionToolTransport(lambda r: {"status": "completed"})

        # 1. Non-dict payload
        res1 = transport.dispatch("not a dict")
        self.assertEqual(res1.status, "rejected")
        self.assertIn("Validation failed", res1.error)

        # 2. Unsupported schema_version
        res2 = transport.dispatch(_make_valid_payload(schema_version=99))
        self.assertEqual(res2.status, "rejected")
        self.assertIn("schema_version", res2.error)

        # 3. Invalid UUIDs
        res3 = transport.dispatch(_make_valid_payload(session_id="not-a-uuid"))
        self.assertEqual(res3.status, "rejected")
        self.assertIn("session_id", res3.error)

        # 4. Empty tool_name
        res4 = transport.dispatch(_make_valid_payload(tool_name="  "))
        self.assertEqual(res4.status, "rejected")
        self.assertIn("tool_name", res4.error)

        # 5. Non-dict arguments
        res5 = transport.dispatch(_make_valid_payload(arguments="not a dict"))
        self.assertEqual(res5.status, "rejected")
        self.assertIn("arguments", res5.error)

        # 6. Invalid deadline
        res6 = transport.dispatch(_make_valid_payload(deadline=-1.0))
        self.assertEqual(res6.status, "rejected")
        self.assertIn("deadline", res6.error)

    def test_session_mismatch_fails_closed_on_replayed_request_id(self):
        payload1 = _make_valid_payload(request_id="shared-req-id")
        transport = NotionToolTransport(lambda r: {"output": "ok", "status": "completed"})

        # Initial dispatch completes cleanly
        res1 = transport.dispatch(payload1)
        self.assertEqual(res1.status, "completed")

        # Replay with a DIFFERENT session_id must raise SessionMismatchError
        payload2 = dict(payload1)
        payload2["session_id"] = str(uuid.uuid4())

        with self.assertRaises(SessionMismatchError):
            transport.dispatch(payload2)

        # Replay with a DIFFERENT task_id must also raise SessionMismatchError
        payload3 = dict(payload1)
        payload3["task_id"] = str(uuid.uuid4())

        with self.assertRaises(SessionMismatchError):
            transport.dispatch(payload3)

    def test_idempotent_replay_of_completed_request(self):
        payload = _make_valid_payload()
        invocations = 0

        def counting_router(req: NotionToolRequest) -> dict:
            nonlocal invocations
            invocations += 1
            return {"output": f"run_{invocations}", "status": "completed"}

        transport = NotionToolTransport(counting_router)
        res1 = transport.dispatch(payload)
        self.assertEqual(res1.output, "run_1")
        self.assertEqual(invocations, 1)

        # Replaying identical valid request returns cached result without re-executing
        res2 = transport.dispatch(payload)
        self.assertEqual(res2.output, "run_1")
        self.assertEqual(res2.request_id, res1.request_id)
        self.assertEqual(invocations, 1)  # Router was NOT re-invoked!

    def test_in_flight_concurrent_replay_raises_replay_error(self):
        payload = _make_valid_payload()
        started = False

        def slow_router(req: NotionToolRequest) -> dict:
            nonlocal started
            started = True
            # Attempt to dispatch the same request recursively while in-progress
            transport.dispatch(payload)
            return {"status": "completed"}

        transport = NotionToolTransport(slow_router)
        with self.assertRaises(ReplayError):
            transport.dispatch(payload)

    def test_deadline_expired_before_execution_yields_timeout(self):
        mock_router = MagicMock()
        transport = NotionToolTransport(mock_router)

        # Deadline in the past
        past_deadline = time.monotonic() - 5.0
        payload = _make_valid_payload(deadline=past_deadline)

        res = transport.dispatch(payload)
        self.assertEqual(res.status, "timeout")
        self.assertIn("deadline expired", res.error.lower())
        mock_router.assert_not_called()

    def test_cancellation_by_request_id(self):
        mock_router = MagicMock()
        transport = NotionToolTransport(mock_router)
        payload = _make_valid_payload()

        transport.cancel_request(payload["request_id"])
        res = transport.dispatch(payload)

        self.assertEqual(res.status, "cancelled")
        mock_router.assert_not_called()

    def test_cancellation_by_session_id(self):
        mock_router = MagicMock()
        transport = NotionToolTransport(mock_router)
        session_id = str(uuid.uuid4())
        payload = _make_valid_payload(session_id=session_id)

        transport.cancel_session(session_id)
        res = transport.dispatch(payload)

        self.assertEqual(res.status, "cancelled")
        mock_router.assert_not_called()

    def test_unregistered_router_returns_clean_rejection(self):
        transport = NotionToolTransport(local_router=None)
        payload = _make_valid_payload()

        res = transport.dispatch(payload)
        self.assertEqual(res.status, "rejected")
        self.assertIn("No local router registered", res.error)

    def test_router_exception_handled_safely(self):
        def crashing_router(req: NotionToolRequest):
            raise RuntimeError("Underlying broker connection dropped.")

        transport = NotionToolTransport(crashing_router)
        payload = _make_valid_payload()

        res = transport.dispatch(payload)
        self.assertEqual(res.status, "failed")
        self.assertIn("Underlying broker connection dropped", res.error)

    def test_payload_size_limit_enforced_on_large_output(self):
        # Set max payload to 1 KB for test
        transport = NotionToolTransport(
            lambda r: {"output": {"data": "X" * 2048}, "status": "completed"},
            max_payload_bytes=1024,
        )
        payload = _make_valid_payload()
        res = transport.dispatch(payload)

        self.assertEqual(res.status, "failed")
        self.assertIn("PayloadLimitError", res.error)
        self.assertIsNone(res.output)

    def test_format_continuation_message_structure(self):
        result = NotionToolResult(
            schema_version=SCHEMA_VERSION,
            task_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            request_id="req-test-99",
            status="completed",
            output={"observed_window": "Not Defteri", "found": True},
            error="",
            duration_ms=45.2,
            verification="observed",
        )

        msg = format_continuation_message(result)
        self.assertEqual(msg["session_id"], result.session_id)
        self.assertIn("[Quartz Local Tool Result]", msg["message"])
        self.assertIn("tool_request_id: req-test-99", msg["message"])
        self.assertIn("verification: observed", msg["message"])
        self.assertIn("Not Defteri", msg["message"])
        self.assertEqual(msg["metadata"]["request_id"], "req-test-99")

    def test_post_execution_cancellation_fences_result(self):
        payload = _make_valid_payload()
        transport = None

        def router_that_cancels(req: NotionToolRequest):
            transport.cancel_request(req.request_id)
            return {"status": "completed", "output": "sensitive output"}

        transport = NotionToolTransport(router_that_cancels)
        res = transport.dispatch(payload)

        # Result must be fenced and marked cancelled
        self.assertEqual(res.status, "cancelled")
        self.assertIsNone(res.output)
        self.assertIn("cancelled while awaiting execution", res.error)

    def test_binary_screenshot_payload_masked_in_continuation_message(self):
        result = NotionToolResult(
            schema_version=SCHEMA_VERSION,
            task_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            request_id="req-screenshot-1",
            status="completed",
            output=b"\x89PNG\r\n\x1a\n" + (b"\x00" * 1024),
            error="",
            duration_ms=12.5,
            verification="observed",
        )

        msg = format_continuation_message(result)
        # Continuation message must NOT expose raw unprintable binary bytes
        self.assertIn("<binary data: 1032 bytes>", msg["message"])
        self.assertNotIn("\x89PNG", msg["message"])


if __name__ == "__main__":
    unittest.main()
