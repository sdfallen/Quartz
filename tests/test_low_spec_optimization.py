"""Tests for low-spec laptop optimization, lazy startup, and memory management."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from core.low_spec_optimizer import (
    LOW_SPEC_WEBVIEW_FLAGS,
    LazyClientProxy,
    cleanup_stale_cli_artifacts,
    configure_webview_environment,
    detect_hardware_profile,
    measure_process_tree_resources,
    trim_working_set,
)


class LowSpecOptimizationTests(unittest.TestCase):
    def test_detect_hardware_profile_respects_env_override(self):
        with patch.dict(os.environ, {"QUARTZ_LOW_SPEC": "1"}):
            prof_low = detect_hardware_profile(force_refresh=True)
            self.assertTrue(prof_low["low_spec_mode"])
            self.assertEqual(prof_low["max_uia_elements"], 150)
            self.assertEqual(prof_low["max_uia_depth"], 4)
            self.assertGreaterEqual(prof_low["idle_poll_ms"], 2000)

        with patch.dict(os.environ, {"QUARTZ_LOW_SPEC": "0"}):
            prof_high = detect_hardware_profile(force_refresh=True)
            self.assertFalse(prof_high["low_spec_mode"])
            self.assertEqual(prof_high["max_uia_elements"], 250)
            self.assertEqual(prof_high["max_uia_depth"], 5)

    def test_configure_webview_environment_injects_memory_flags_idempotently(self):
        with patch.dict(os.environ, {"WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": "--custom-flag=1"}, clear=False):
            first = configure_webview_environment()
            second = configure_webview_environment()
            self.assertEqual(first, second)
            self.assertIn("--custom-flag=1", first)
            for flag in LOW_SPEC_WEBVIEW_FLAGS:
                self.assertIn(flag, first)

    def test_lazy_client_proxy_defers_instantiation(self):
        created = []

        class FakeSDKClient:
            def __init__(self):
                created.append(True)
                self.models = MagicMock()

        proxy = LazyClientProxy(FakeSDKClient)
        self.assertFalse(proxy.is_initialized)
        self.assertEqual(len(created), 0)

        _ = proxy.models
        self.assertTrue(proxy.is_initialized)
        self.assertEqual(len(created), 1)

    def test_trim_working_set_throttles_unless_forced(self):
        res1 = trim_working_set(force=True)
        self.assertTrue(res1["trimmed"])
        res2 = trim_working_set(force=False, min_interval_sec=60.0)
        self.assertFalse(res2["trimmed"])
        self.assertEqual(res2["reason"], "throttled")
        res3 = trim_working_set(force=True)
        self.assertTrue(res3["trimmed"])

    def test_ipc_server_fast_startup_does_not_instantiate_assistant_on_health_or_polls(self):
        import main
        from core.local_ipc import request_token

        server = main.IPCServer(None)
        self.assertIsNone(server._assistant_instance)

        token = request_token()
        for action in ("ping", "health", "ui_events", "tasks", "tool_permissions"):
            reply = server._dispatch({"action": action, "auth": token})
            self.assertEqual(reply["status"], "ok", f"Failed on {action}: {reply}")
            self.assertIsNone(
                server._assistant_instance,
                f"Action '{action}' should not eagerly instantiate GitHubAssistant",
            )

    def test_controlled_cli_housekeeping_preserves_recent_logs_and_active_locks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            log_dir = base / "log"
            presence_dir = base / "presence"
            log_dir.mkdir(parents=True)
            presence_dir.mkdir(parents=True)

            old_mtime = time.time() - (72 * 3600)
            for idx in range(6):
                p = log_dir / f"cli-old-{idx}.log"
                p.write_text("old diagnostic log" * 10, encoding="utf-8")
                os.utime(p, (old_mtime + idx, old_mtime + idx))
            recent_log = log_dir / "cli-recent.log"
            recent_log.write_text("fresh diagnostic log", encoding="utf-8")

            lock_file = presence_dir / "session-old.lock"
            lock_file.write_text("", encoding="utf-8")
            os.utime(lock_file, (old_mtime, old_mtime))

            for idx in range(4):
                b = base / f"settings.before-quartz-desktop-{idx}.json"
                b.write_text("{}", encoding="utf-8")
                os.utime(b, (old_mtime + idx, old_mtime + idx))

            # 1) When an agy process is active, lock files must NEVER be deleted
            fake_proc = MagicMock()
            fake_proc.info = {"name": "agy.exe"}
            with patch("psutil.process_iter", return_value=[fake_proc]):
                res_active = cleanup_stale_cli_artifacts(
                    base,
                    max_age_hours=48.0,
                    keep_recent_logs=3,
                    keep_recent_backups=2,
                    force=True,
                )
            self.assertTrue(res_active["active_session_guard"])
            self.assertEqual(res_active["locks_removed"], 0)
            self.assertTrue(lock_file.exists())
            # Kept 3 most recent logs (including recent_log) and removed 4 old logs
            self.assertEqual(res_active["logs_removed"], 4)
            self.assertTrue(recent_log.exists())
            self.assertEqual(len(list(log_dir.glob("*.log"))), 3)
            self.assertEqual(res_active["backups_removed"], 2)

            # 2) When no agy process is running, stale lock older than 48h is cleaned
            with patch("psutil.process_iter", return_value=[]):
                res_idle = cleanup_stale_cli_artifacts(
                    base,
                    max_age_hours=48.0,
                    keep_recent_logs=3,
                    keep_recent_backups=2,
                    force=True,
                )
            self.assertFalse(res_idle["active_session_guard"])
            self.assertEqual(res_idle["locks_removed"], 1)
            self.assertFalse(lock_file.exists())

    def test_uia_inspection_uses_adaptive_profile_and_fresh_scans(self):
        from core.desktop_control import DesktopController

        controller = DesktopController()
        fake_win = MagicMock()
        fake_win.is_visible.return_value = True
        fake_win.window_text.return_value = "Not Defteri"
        fake_win.process_id.return_value = 4242
        fake_win.descendants.return_value = []

        with patch.dict(os.environ, {"QUARTZ_LOW_SPEC": "1"}):
            detect_hardware_profile(force_refresh=True)
            controller._get_descendants(fake_win)
            fake_win.descendants.assert_called_with(depth=4)

        with patch.dict(os.environ, {"QUARTZ_LOW_SPEC": "0"}):
            detect_hardware_profile(force_refresh=True)
            controller._get_descendants(fake_win)
            fake_win.descendants.assert_called_with(depth=5)

    def test_measure_process_tree_resources_reports_structured_totals(self):
        metrics = measure_process_tree_resources(cpu_interval=0.05)
        self.assertGreaterEqual(metrics["process_count"], 1)
        self.assertGreater(metrics["total_rss_mb"], 0.0)
        self.assertIn("breakdown", metrics)
        self.assertIn("quartz_rss_mb", metrics["breakdown"])
        self.assertIn("webview2_rss_mb", metrics["breakdown"])


if __name__ == "__main__":
    unittest.main()
