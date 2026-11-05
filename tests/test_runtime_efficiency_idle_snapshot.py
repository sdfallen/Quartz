"""Unit tests for AsyncSnapshot post-completion TTL window and idle subprocess accounting."""

from __future__ import annotations

import unittest
from core.async_snapshot import AsyncSnapshot


class AsyncSnapshotIdleTests(unittest.TestCase):
    def _wait_worker(self, snapshot: AsyncSnapshot) -> None:
        worker = snapshot.worker
        if worker is not None:
            worker.join(timeout=1.0)
        self.assertIsNone(snapshot.worker)

    def test_slow_probe_anchors_ttl_to_completion_time_not_start_time(self):
        clock = [0.0]
        calls = []

        def slow_loader(key: str) -> dict:
            calls.append((key, clock[0]))
            # Simulate a 10-second initial CLI probe (codex + agy + squad)
            clock[0] += 10.0
            return {"project": key, "ok": True}

        cache = AsyncSnapshot(slow_loader, ttl=15, clock=lambda: clock[0])
        try:
            cache.read("proj-1")
            self._wait_worker(cache)
            self.assertEqual(len(calls), 1)
            self.assertEqual(clock[0], 10.0)

            # At t=16.0s (only 6s after the 10s probe completed), a new refresh MUST NOT start
            clock[0] = 16.0
            val, state = cache.read("proj-1")
            self._wait_worker(cache)
            self.assertEqual(len(calls), 1)
            self.assertFalse(state["stale"])
            self.assertEqual(val["project"], "proj-1")

            # At t=25.0s (15s after completion at t=10.0s), the next refresh is due
            clock[0] = 25.0
            cache.read("proj-1")
            self._wait_worker(cache)
            self.assertEqual(len(calls), 2)
        finally:
            cache.close()


if __name__ == "__main__":
    unittest.main()
