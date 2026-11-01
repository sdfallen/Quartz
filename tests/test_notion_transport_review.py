"""Adversarial review regressions, no Notion account or desktop access."""
from dataclasses import replace
import unittest
from core.notion_tool_transport import (NotionToolTransport, NotionToolRequest,
    NotionToolResult, NotionTransportError, ReplayError, SessionMismatchError)
from core.notion_local_tools import NotionLocalTools
from tests.test_notion_tool_transport import _make_valid_payload


class TransportReviewTests(unittest.TestCase):
    def test_cancellation_during_result_normalization_is_fenced_at_commit(self):
        p = _make_valid_payload()
        t = NotionToolTransport(lambda r: {'status': 'completed', 'output': 'late'})
        original = t._bound_payload
        def bound(output):
            t.cancel_session(p['session_id'])
            return original(output)
        t._bound_payload = bound
        result = t.dispatch(p)
        self.assertEqual(result.status, 'cancelled')
        self.assertIsNone(result.output)
        self.assertTrue(result.uncertain)

    def test_receipt_limit_never_reenables_old_execution(self):
        calls = []
        t = NotionToolTransport(lambda r: calls.append(r.request_id), max_history=1)
        p = _make_valid_payload()
        t.dispatch(p)
        with self.assertRaises(ReplayError): t.dispatch({**p, "request_id": "another"})
        t.dispatch(p)
        self.assertEqual(calls, [p["request_id"]])

    def test_same_id_different_args_or_scope_is_rejected(self):
        p = _make_valid_payload()
        t = NotionToolTransport(lambda r: {"output": "ok"})
        t.dispatch(p)
        for changed in ({"arguments": {"other": True}}, {"tool_name": "different"},
                        {"scope_ref": "foreign"}, {"project_id": "other"}):
            with self.subTest(changed=changed), self.assertRaises(SessionMismatchError):
                t.dispatch({**p, **changed})

    def test_router_exception_including_transport_error_is_cached_and_redacted(self):
        p = _make_valid_payload()
        for exc in (RuntimeError, NotionTransportError):
            calls = []
            def router(r):
                calls.append(r.request_id)
                raise exc("SYNTHETIC_PRIVATE_VALUE")
            t = NotionToolTransport(router)
            first = t.dispatch(p)
            self.assertTrue(first.uncertain)
            self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", str(first))
            self.assertEqual(t.dispatch(p), first)
            self.assertEqual(len(calls), 1)

    def test_deadline_after_dispatch_is_not_verified(self):
        now = [1]
        def late(r):
            now[0] = 3
            return {"status": "completed", "verification": "verified", "output": "late"}
        t = NotionToolTransport(late, clock=lambda: now[0])
        r = t.dispatch(_make_valid_payload(deadline=2))
        self.assertEqual(r.status, "timeout")
        self.assertTrue(r.uncertain)
        self.assertEqual(r.verification, "none")

    def test_invalid_numbers_unknown_fields_and_objects_do_not_dispatch(self):
        calls = []
        t = NotionToolTransport(lambda r: calls.append(r))
        for changed in ({"deadline": float('nan')}, {"deadline": float('inf')},
                        {"deadline": True}, {"schema_version": True}, {"extra": "field"},
                        {"scope_ref": ""}, {"arguments": {"value": object()}}):
            self.assertEqual(t.dispatch(_make_valid_payload(**changed)).status, "rejected")
        forged = NotionToolRequest.from_dict(_make_valid_payload())
        self.assertEqual(t.dispatch(replace(forged, deadline=float('nan'))).status, "rejected")
        self.assertEqual(calls, [])

    def test_mutating_receipt_or_router_result_cannot_change_cached_data(self):
        value = {"nested": [1]}
        t = NotionToolTransport(lambda r: {"output": value})
        p = _make_valid_payload()
        first = t.dispatch(p)
        first.output['nested'].append(2)
        value['nested'].append(3)
        self.assertEqual(t.dispatch(p).output, {"nested": [1]})
        t.get_result(p['request_id']).output['nested'].append(4)
        self.assertEqual(t.dispatch(p).output, {"nested": [1]})

    def test_transport_and_authoritative_local_gate_together(self):
        p = _make_valid_payload(tool_name='read')
        calls = []
        gate = NotionLocalTools(task_id=p['task_id'], session_id=p['session_id'],
            project_id=p['project_id'], scope_ref=p['scope_ref'], enabled=True,
            authorize=lambda name, args: args == p['arguments'],
            expires_at=p['deadline'], tools={'read': lambda args, stop: calls.append(args) or {'text': 'actual local fixture'}})
        def router(req):
            result = gate.call(req.to_dict())
            return {'status': result['status'], 'output': result.get('result'),
                    'verification': result['verification'], 'uncertain': result.get('uncertain', False)}
        t = NotionToolTransport(router)
        self.assertEqual(t.dispatch(p).output, {'text': 'actual local fixture'})
        self.assertEqual(len(calls), 1)
        gate.stop()
        stopped = t.dispatch({**p, 'request_id': 'stopped'})
        self.assertEqual(stopped.status, 'blocked')
        self.assertEqual(len(calls), 1)
