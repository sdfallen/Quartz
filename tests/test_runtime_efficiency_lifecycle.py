"""Tests for runtime efficiency, resource lifecycle, and process termination."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.async_snapshot import AsyncSnapshot
from core.low_spec_optimizer import (
    measure_process_tree_resources,
    trim_working_set,
)
from core.process_tree import stop_process_tree


class RuntimeEfficiencyLifecycleTests(unittest.TestCase):
    def test_async_snapshot_memoization_isolates_caller_mutations(self):
        loader = MagicMock(return_value={"status": "ok", "nested": {"counter": 1}})
        snapshot = AsyncSnapshot(loader, ttl=10)
        try:
            # First read starts the asynchronous refresh worker
            _, state0 = snapshot.read("proj_1")
            self.assertTrue(state0["refreshing"])
            if snapshot.worker:
                snapshot.worker.join(1.0)

            # Second read has completed the refresh and holds value
            val1, state1 = snapshot.read("proj_1")
            self.assertEqual(val1, {"status": "ok", "nested": {"counter": 1}})
            self.assertFalse(state1["refreshing"])

            # Caller mutates the returned dictionary
            val1["status"] = "tampered"
            val1["nested"]["counter"] = 999

            # Subsequent read must remain intact and unmutated
            val2, state2 = snapshot.read("proj_1")
            self.assertEqual(val2, {"status": "ok", "nested": {"counter": 1}})
            self.assertEqual(loader.call_count, 1)
        finally:
            snapshot.close()

    def test_async_snapshot_worker_watchdog_recovers_from_hung_loader(self):
        clock_time = [100.0]
        hung_event = threading.Event()

        def hanging_loader(key):
            hung_event.wait(5.0)
            return {"key": key}

        snapshot = AsyncSnapshot(hanging_loader, ttl=5, clock=lambda: clock_time[0])
        try:
            val1, state1 = snapshot.read("hang_test", seed={"initial": True})
            self.assertTrue(state1["refreshing"])
            first_worker = snapshot.worker
            self.assertIsNotNone(first_worker)

            # Advance clock past the watchdog threshold (max(2*ttl, 30s) -> 30s)
            clock_time[0] += 35.0
            val2, state2 = snapshot.read("hang_test", seed={"initial": True})
            # Watchdog recorded the timeout error
            self.assertEqual(state2["error"], "Status probe timed out")
            # A new attempt was started instead of remaining permanently stuck
            self.assertNotEqual(snapshot.worker, first_worker)
        finally:
            hung_event.set()
            snapshot.close(timeout=0.5)

    def test_async_snapshot_clean_close_with_timeout(self):
        release = threading.Event()
        snapshot = AsyncSnapshot(lambda k: (release.wait(2.0), {"k": k})[1], ttl=10)
        try:
            snapshot.read("k1")
            self.assertIsNotNone(snapshot.worker)
            release.set()
            snapshot.close(timeout=1.0)
            self.assertTrue(snapshot.closed)
        finally:
            release.set()

    def test_stop_process_tree_handles_int_pid_and_none(self):
        # Must not raise on None or invalid pid
        stop_process_tree(None)
        stop_process_tree("not_a_pid")
        # On a non-existent PID, must return immediately without error
        stop_process_tree(9999999)

    def test_stop_process_tree_terminates_deep_process_hierarchy(self):
        grandchild_code = "import time; time.sleep(120)"
        child_code = (
            "import subprocess, sys, time\n"
            f"p = subprocess.Popen([sys.executable, '-c', {grandchild_code!r}], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))\n"
            "print(p.pid, flush=True)\n"
            "time.sleep(120)\n"
        )
        parent_code = (
            "import subprocess, sys, time\n"
            f"p = subprocess.Popen([sys.executable, '-c', {child_code!r}], stdout=subprocess.PIPE, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))\n"
            "gc_pid = p.stdout.readline().strip()\n"
            "print(f'{p.pid},{gc_pid}', flush=True)\n"
            "time.sleep(120)\n"
        )

        parent = subprocess.Popen(
            [sys.executable, "-c", parent_code],
            stdout=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            line = parent.stdout.readline().strip()
            parts = [int(x) for x in line.split(",") if x.isdigit()]
            self.assertEqual(len(parts), 2)
            child_pid, grandchild_pid = parts[0], parts[1]

            t0 = time.perf_counter()
            stop_process_tree(parent, timeout=4.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # Stop latency must be responsive (< 2000ms even on slower machines)
            self.assertLess(elapsed_ms, 2000.0)

            import psutil
            self.assertFalse(psutil.pid_exists(child_pid))
            self.assertFalse(psutil.pid_exists(grandchild_pid))
            self.assertIsNotNone(parent.poll())
        finally:
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=2)
            parent.stdout.close()

    def test_measure_process_tree_reports_thread_counts(self):
        metrics = measure_process_tree_resources(cpu_interval=0.0)
        self.assertIn("total_threads", metrics)
        self.assertGreaterEqual(metrics["total_threads"], 1)
        self.assertIn("quartz_threads", metrics["breakdown"])
        self.assertIn("webview2_threads", metrics["breakdown"])
        self.assertIn("cli_threads", metrics["breakdown"])

    def test_trim_working_set_has_valid_win32_types(self):
        res = trim_working_set(force=True)
        self.assertTrue(res["trimmed"])
        if sys.platform == "win32":
            # On 64-bit Windows, proper ctypes typing allows SetProcessWorkingSetSize to succeed
            self.assertTrue(res["os_working_set_trimmed"])


if __name__ == "__main__":
    unittest.main()
