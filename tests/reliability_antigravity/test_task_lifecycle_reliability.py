"""Reliability tests for NaturalDesktopTask lifecycle invariants and Jarvis Full-Control.
Covers:
- F-02 (FIXED): Stopped NaturalDesktopTask instance can be reused cleanly for a subsequent start(), while an active task still rejects concurrent start().
- F-03 (VERIFIED): Scope request for read-only logs preserves active desktop broker.
- Jarvis Full Authority (`requested_permission_level='full'`): Auto-approves inline desktop scope and executes `jarvis_*` tools while blocking Warband/protected paths.
"""
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.natural_desktop import NaturalDesktopTask
from core.desktop_broker import DesktopBroker
from tests.test_desktop_broker import FakeBackend


class _FakeRuntime:
    TERMINAL = {"completed", "failed", "cancelled"}
    executable = "fake-runtime.exe"

    def __init__(self):
        self.state = {"id": "run-1", "status": "running"}

    def start(self, prompt, workspace, **opts):
        return self.state

    def get(self, rid):
        return self.state

    def cancel(self, rid):
        self.state["status"] = "cancelled"


class NaturalTaskLifecycleReliabilityTests(unittest.TestCase):
    """Verifies lifecycle invariants, state cleanup, F-02 fix, F-03, and Jarvis full-control tools."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = FakeBackend()
        self.broker = DesktopBroker(self.backend)
        self.desktop = SimpleNamespace(broker=self.broker, windows=self.backend.windows)
        self.events = []
        self.models = {
            "codex": {"model": "gpt-6.1-sol", "effort": "low"},
            "antigravity": {"model": "gemini-4-argon-medium", "effort": "medium"},
        }
        self.project = {"path": str(self.root), "workflow": "general"}
        self.fake_squad = Mock()
        self.fake_squad.initialized = True
        self.fake_squad.create_task.return_value = {"id": "squad-task-2"}
        self.fake_squad.receive.return_value = []
        self.fake_squad.status.return_value = {"installed": True, "initialized": True}
        self.task = NaturalDesktopTask(
            self.desktop,
            lambda *a: self.events.append(a),
            factories={"codex": _FakeRuntime, "antigravity": _FakeRuntime},
            squad_factory=lambda _: self.fake_squad,
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
        self.task.squad = self.fake_squad

        req = self.task.call("token-op", {
            "name": "desktop_request_access",
            "arguments": {"handles": [1], "log_paths": [], "reason": "Pencere incelemesi"},
        })
        self.assertEqual(req["status"], "waiting_for_inline_permission")
        appr = self.task.approve(self.task.pending["id"], confirmed=True)
        self.assertTrue(appr["active"])
        self.assertTrue(self.broker.status()["active"])
        self.assertIsNotNone(self.task.connection)

    def test_active_task_rejects_concurrent_start(self):
        """While a task is actively running, calling start() raises RuntimeError."""
        self._setup_active_approved_task()
        with self.assertRaises(RuntimeError) as ctx:
            self.task.start("Eşzamanlı görev", self.project, "cid-2", self.models)
        self.assertIn("Önceki görevi kapatmadan yeni operatör başlatılamaz", str(ctx.exception))

    def test_contract_f02_natural_task_should_allow_start_after_stop(self):
        """F-02 VERIFIED FIX: A stopped NaturalDesktopTask instance is cleanly reusable for a new task."""
        self._setup_active_approved_task()
        self.task.stop("completed")
        with patch("core.natural_desktop.subprocess.run", return_value=SimpleNamespace(returncode=0)), \
             patch("core.natural_desktop.ensure_antigravity_tool_grants"), \
             patch("core.natural_desktop.write_operator_hooks"):
            status = self.task.start("İkinci görev başlat", self.project, "cid-2", self.models, requested_permission_level="full")
        self.assertTrue(status["active"])
        self.assertEqual(self.task.job["scope"], "İkinci görev başlat")
        self.assertEqual(self.task.job["requested_permission_level"], "full")

    def test_f03_verified_log_request_preserves_active_desktop_broker(self):
        """F-03 VERIFICATION: Requesting read-only logs preserves the active desktop connection."""
        self._setup_active_approved_task()
        self.assertTrue(self.broker.status()["active"])
        self.assertIsNotNone(self.task.connection)

        log_file = self.root / "app.log"
        log_file.write_text("sample log line\n", encoding="utf-8")

        req_res = self.task.call("token-obs", {
            "name": "desktop_request_access",
            "arguments": {"handles": [], "log_paths": ["app.log"], "reason": "Log inceleme"},
        })
        self.assertEqual(req_res["status"], "waiting_for_inline_permission")
        self.assertTrue(self.broker.status()["active"])
        self.assertIsNotNone(self.task.connection)

    def test_full_permission_auto_approves_scope_and_enables_jarvis_tools(self):
        """In Tam Yetki ('full') mode, desktop_request_access auto-approves and jarvis_* tools execute."""
        self.task.job = {
            "id": "job-full",
            "conversation_id": "conv-full",
            "project": {"path": str(self.root)},
            "scope": "Jarvis tam kontrol testi",
            "requested_permission_level": "full",
            "roles": {"operator": "codex", "observer": "antigravity"},
            "expires_at": time.time() + 600,
            "status": "running",
            "events": [],
            "task_id": "squad-full",
            "verification": {"status": "NOT VERIFIED"},
        }
        self.task.evidence = self.root / "evidence-full"
        self.task.evidence.mkdir(parents=True, exist_ok=True)
        self.task.tokens = {"codex": "token-op", "antigravity": "token-obs"}
        self.task.agent_ids = {"codex": "c-task", "antigravity": "g-task"}
        self.task.squad = self.fake_squad

        req = self.task.call("token-op", {
            "name": "desktop_request_access",
            "arguments": {"handles": [1], "log_paths": [], "reason": "Tam yetkiyle pencere kontrolü"},
        })
        self.assertEqual(req["status"], "approved")
        self.assertTrue(self.broker.status()["active"])

        # Collaborator can read system info (windows)
        win_info = self.task.call("token-obs", {
            "name": "jarvis_system_info",
            "arguments": {"action": "windows"},
        })
        self.assertEqual(win_info["status"], "ok")
        self.assertEqual(len(win_info["windows"]), 1)

        # Collaborator cannot execute operator-only jarvis_open_app
        with self.assertRaises(PermissionError):
            self.task.call("token-obs", {
                "name": "jarvis_open_app",
                "arguments": {"target": "notepad"},
            })

        # Protected Warband target is rejected even for operator
        with self.assertRaises(PermissionError):
            self.task.call("token-op", {
                "name": "jarvis_open_app",
                "arguments": {"target": "C:\\WarbandIsland\\mb_warband.exe"},
            })

    def test_stop_idempotency(self):
        """Verifies that calling stop() repeatedly does not raise unhandled exceptions."""
        self._setup_active_approved_task()
        self.task.stop("reason-1")
        self.task.stop("reason-2")
        self.task.stop("reason-3")

    def test_persistent_screen_control_survives_user_click_until_explicit_stop(self):
        """Verifies that in Tam Yetki (full) mode, user mouse clicks / foreground focus changes
        do NOT cancel screen control; control persists until explicit stop ('Görevi Durdur')."""
        self.task.job = {
            "id": "job-persist",
            "conversation_id": "conv-persist",
            "project": {"path": str(self.root)},
            "scope": "Kalıcı ekran kontrolü testi",
            "requested_permission_level": "full",
            "roles": {"operator": "codex", "observer": "antigravity"},
            "expires_at": time.time() + 600,
            "status": "running",
            "events": [],
            "task_id": "squad-persist",
            "verification": {"status": "NOT VERIFIED"},
        }
        self.task.evidence = self.root / "evidence-persist"
        self.task.evidence.mkdir(parents=True, exist_ok=True)
        self.task.tokens = {"codex": "token-op", "antigravity": "token-obs"}
        self.task.agent_ids = {"codex": "c-task", "antigravity": "g-task"}
        self.task.squad = self.fake_squad

        req = self.task.call("token-op", {
            "name": "desktop_request_access",
            "arguments": {"handles": [1], "log_paths": [], "reason": "Kalıcı ekran kontrolü"},
        })
        self.assertEqual(req["status"], "approved")
        self.assertTrue(self.broker.status()["active"])
        self.assertTrue(self.broker.status()["persistent_control"])

        # First focus target, then simulate user clicking another window (foreground = False)
        self.task.call("token-op", {"name": "desktop_focus", "arguments": {}})
        self.assertTrue(self.backend.foreground)
        self.backend.foreground = False
        # Broker status poll must NOT cancel the session
        st = self.broker.status()
        self.assertTrue(st["active"])
        self.assertEqual(self.task.job["status"], "running")

        # Next agent action automatically re-focuses handle 1 and succeeds
        obs = self.task.call("token-op", {
            "name": "desktop_observe",
            "arguments": {},
        })
        self.assertEqual(obs["target"]["handle"], 1)
        self.assertTrue(self.backend.foreground)

        # Only explicit stop ("Görevi Durdur" button) terminates control
        self.task.stop("cancelled")
        self.assertFalse(self.broker.status()["active"])


if __name__ == "__main__":
    unittest.main()
