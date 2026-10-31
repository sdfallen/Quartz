"""Tests for resource boundaries, adaptive polling profiles, and controlled cleanup."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from core.low_spec_optimizer import (
    cleanup_stale_cli_artifacts,
    detect_hardware_profile,
    get_adaptive_poll_intervals,
)


class RuntimeEfficiencyBoundariesTests(unittest.TestCase):
    def test_adaptive_polling_profiles_differentiate_states(self):
        with patch.dict(os.environ, {"QUARTZ_LOW_SPEC": "1"}):
            prof_low = detect_hardware_profile(force_refresh=True)
            self.assertIn("profiles", prof_low)
            self.assertIn("idle", prof_low["profiles"])
            self.assertIn("chat", prof_low["profiles"])
            self.assertIn("active_desktop", prof_low["profiles"])

            idle_p = get_adaptive_poll_intervals("idle", low_spec=True)
            chat_p = get_adaptive_poll_intervals("chat", low_spec=True)
            active_p = get_adaptive_poll_intervals("active_desktop", low_spec=True)

            # Active desktop polling must be more responsive than idle
            self.assertLess(active_p["poll_ms"], idle_p["poll_ms"])
            self.assertLess(active_p["tasks_poll_ms"], idle_p["tasks_poll_ms"])
            self.assertLess(chat_p["poll_ms"], idle_p["poll_ms"])
            self.assertGreaterEqual(idle_p["poll_ms"], 2400)

        with patch.dict(os.environ, {"QUARTZ_LOW_SPEC": "0"}):
            idle_high = get_adaptive_poll_intervals("idle", low_spec=False)
            active_high = get_adaptive_poll_intervals("active_desktop", low_spec=False)
            self.assertLess(active_high["poll_ms"], idle_high["poll_ms"])
            self.assertEqual(active_high["poll_ms"], 800)

    def test_log_cleanup_respects_size_boundary_and_preserves_recent_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            log_dir = base / "log"
            log_dir.mkdir(parents=True)

            now = time.time()
            # Create 10 files of 1 MB each (all within 24 hours, so young enough by age)
            created_files = []
            for i in range(10):
                p = log_dir / f"session-{i:02d}.log"
                # Write 1 MB to each
                p.write_bytes(b"A" * (1024 * 1024))
                file_time = now - (i * 100)
                os.utime(p, (file_time, file_time))
                created_files.append(p)

            # Set max_total_size_mb to 3.0 MB, but keep_recent_logs=4
            # Total size is 10 MB, cap is 3 MB.
            # Even though all files are younger than 48h, size cap triggers pruning on eligible files,
            # but MUST NEVER prune the 4 most recent files!
            res = cleanup_stale_cli_artifacts(
                base,
                max_age_hours=48.0,
                keep_recent_logs=4,
                max_total_size_mb=3.0,
                force=True,
            )

            self.assertTrue(res["cleaned"])
            self.assertIn("boundaries", res)
            self.assertEqual(res["boundaries"]["max_total_size_mb"], 3.0)
            self.assertEqual(res["boundaries"]["keep_recent_logs"], 4)

            remaining_logs = list(log_dir.glob("*.log"))
            # Exactly 4 most recent files must be preserved
            self.assertGreaterEqual(len(remaining_logs), 4)
            # Oldest files beyond recent 4 were pruned to satisfy size limit
            self.assertLess(len(remaining_logs), 10)
            for i in range(4):
                self.assertTrue((log_dir / f"session-{i:02d}.log").exists())

    def test_log_cleanup_path_containment_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "managed"
            outside = Path(tmp) / "outside"
            log_dir = base / "log"
            log_dir.mkdir(parents=True)
            outside.mkdir(parents=True)

            outside_file = outside / "critical.log"
            outside_file.write_text("do not touch", encoding="utf-8")
            old_time = time.time() - (100 * 3600)
            os.utime(outside_file, (old_time, old_time))

            # In managed log dir
            managed_file = log_dir / "old.log"
            managed_file.write_text("can clean", encoding="utf-8")
            os.utime(managed_file, (old_time, old_time))

            res = cleanup_stale_cli_artifacts(
                base,
                max_age_hours=48.0,
                keep_recent_logs=0,
                force=True,
            )

            self.assertTrue(res["cleaned"])
            # Outside file must remain untouched
            self.assertTrue(outside_file.exists())
            # Managed file was cleaned
            self.assertFalse(managed_file.exists())

    def test_log_cleanup_never_touches_conversations_or_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            conv_dir = base / "conversations"
            conv_dir.mkdir(parents=True)
            conv_file = conv_dir / "chat.db"
            conv_file.write_text("important user messages", encoding="utf-8")

            config_file = base / "settings.json"
            config_file.write_text("{\"theme\": \"dark\"}", encoding="utf-8")

            old_time = time.time() - (200 * 3600)
            os.utime(conv_file, (old_time, old_time))
            os.utime(config_file, (old_time, old_time))

            res = cleanup_stale_cli_artifacts(
                base,
                max_age_hours=24.0,
                keep_recent_logs=0,
                force=True,
            )
            self.assertTrue(res["cleaned"])
            self.assertTrue(conv_file.exists())
            self.assertTrue(config_file.exists())


if __name__ == "__main__":
    unittest.main()
