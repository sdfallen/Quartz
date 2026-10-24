"""Reliability tests for NaturalDesktopTask lifecycle invariants.
Covers:
- F-02: Uncleared self.job in stop() prevents instance reuse (raises RuntimeError on next start).
- F-03: Scope request for read-only logs preserving active desktop broker (verified with Codex's patch).
- General lifecycle safety: idempotency of stop().
"""
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from core.natural_desktop import NaturalDesktopTask
from core.desktop_broker import DesktopBroker
from tests.test_desktop_broker import FakeBackend


class NaturalTaskLifecycleReliabilityTests(unittest.TestCase):
    """Verifies lifecycle invariants, state cleanup, and reproduces F-02 and F-03."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = FakeBackend()
        self.broker = DesktopBroker(self.backend)
        self.desktop = SimpleNamespace(broker=self.broker, windows=self.backend.windows)
        self.events = []
        self.models = {
            "codex": {"model": "gpt-5", "effort": "medium"},
            "antigravity": {"model": "gemini-3.8-flash-high", "effort": "high"},
        }
        self.project = {"path": str(self.root), "workflow": "general"}
        self.task = NaturalDesktopTask(
            self.desktop,
            lambda *a: self.events.append(a),
            factories={},
            evidence_root=self.root,
        )

    def tearDown(self):
        self.task.stop("teardown")
        self.broker.close()
        self.temp.cleanup()

    def _setup_active_approved_task(self):
        """Helper to advance task into an active, approved state with desktop input connection."""
        self.task.job = {
            "id": "test-job-1",
            "conversation_id": "conv-1",
            "project": {"path": str(self.root)},
            "scope": "test task",
            "roles": {"operator": "codex", "observer": "antigravity"},
            "expires_at": time.time() + 600,
            "status": "running",
            "events": [],
            "task_id": "squad-task-1",
            "verification": {"status": "NOT VERIFIED"},
            "cleanup": {"status": "pending", "steps": []},
        }
        self.task.evidence = self.root / "evidence"
        self.task.evidence.mkdir(parents=True, exist_ok=True)
        self.task.tokens = {"codex": "token-op", "antigravity": "token-obs"}
        self.task.agent_ids = {"codex": "c-task", "antigravity": "g-task"}
        self.task.squad = Mock()
        self.task.squad.receive.return_value = []

        # Grant window 1 to operator
        req = self.task.call("token-op", {
            "name": "desktop_request_access",
            "arguments": {"handles": [1], "log_paths": [], "reason": "Pencere incelemesi"},
        })
        self.assertEqual(req["status"], "waiting_for_inline_permission")
        appr = self.task.approve(self.task.pending["id"], confirmed=True)
        self.assertTrue(appr["active"])
        self.assertTrue(self.broker.status()["active"])
        self.assertIsNotNone(self.task.connection)

    def test_reproduce_f02_natural_task_reuse_raises_runtime_error(self):
        """F-02 PROVEN DEFECT: stop() leaves self.job populated; calling start() again raises RuntimeError.

        In core/natural_desktop.py:157:
            if self.job or self.broker.status()["active"]:
                raise RuntimeError("Önceki görevi kapatmadan yeni operatör başlatılamaz")
        Because self.job is not set to None on stop(), reusing the instance is impossible.
        """
        # Advance task to running state
        self._setup_active_approved_task()
        self.assertIsNotNone(self.task.job)

        # Stop task
        self.task.stop("completed")

        # In unpatched code, self.job is NOT None (it still holds the outcome/verification dict)
        self.assertIsNotNone(self.task.job, "Defect confirmed: self.job was not cleared on stop()")

        # Attempting start() raises RuntimeError
        with self.assertRaises(RuntimeError) as ctx:
            self.task.start("İkinci görev başlat", self.project, "cid-2", self.models)
        self.assertIn("Önceki görevi kapatmadan yeni operatör başlatılamaz", str(ctx.exception))

    @unittest.expectedFailure
    def test_contract_f02_natural_task_should_allow_start_after_stop(self):
        """CONTRACT TEST: A stopped NaturalDesktopTask instance must be reusable for a new task.

        Marked as expectedFailure until Codex clears self.job on stop() or resets finished jobs in start().
        """
        self._setup_active_approved_task()
        self.task.stop("completed")
        # In a reliable architecture, start() must succeed cleanly after stop()
        self.task.start("İkinci görev başlat", self.project, "cid-2", self.models)
        self.assertEqual(self.task.job["scope"], "İkinci görev başlat")

    def test_f03_verified_log_request_preserves_active_desktop_broker(self):
        """F-03 VERIFICATION: Requesting read-only logs preserves the active desktop connection.

        In unpatched 36a2d9e, requesting a log path revoked the active broker.
        With preserve_input logic, unchanged target windows retain their input connection while
        asking user approval for newly requested log scopes.
        """
        self._setup_active_approved_task()
        self.assertTrue(self.broker.status()["active"])
        self.assertIsNotNone(self.task.connection)

        # Create a dummy log file
        log_file = self.root / "app.log"
        log_file.write_text("sample log line\n", encoding="utf-8")

        # Observer requests read-only log access while keeping the EXISTING approved window intact
        req_res = self.task.call("token-obs", {
            "name": "desktop_request_access",
            "arguments": {"handles": [], "log_paths": ["app.log"], "reason": "Log inceleme"},
        })
        self.assertEqual(req_res["status"], "waiting_for_inline_permission")

        # Active desktop broker and connection MUST remain intact
        self.assertTrue(
            self.broker.status()["active"],
            "Broker must remain active for approved target windows when only log access is requested",
        )
        self.assertIsNotNone(
            self.task.connection,
            "Active desktop connection must not be prematurely wiped when requesting log scope",
        )

    def test_stop_idempotency(self):
        """Verifies that calling stop() repeatedly does not raise unhandled exceptions."""
        self._setup_active_approved_task()
        self.task.stop("reason-1")
        # Subsequent stop calls should be idempotent and not crash
        try:
            self.task.stop("reason-2")
            self.task.stop("reason-3")
        except Exception as exc:
            self.fail(f"Subsequent stop() calls raised unexpected exception: {exc}")


if __name__ == "__main__":
    unittest.main()
