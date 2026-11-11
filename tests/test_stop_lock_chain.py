"""Stop must not queue behind an in-flight desktop input (live exam 9 Nov, exam-desk-09).

The broker holds its lock for a whole action. A status poll or the watchdog that read
the broker while holding the task lock made Stop wait for the action to end: 1.72 s
from the HUD click to authority revocation, measured on the installed package.
"""
import threading
import time
import unittest

from tests import test_natural_desktop


class StopLockChainTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_natural_desktop.NaturalTaskTests()
        self.fixture.setUp()
        self.task, self.broker = self.fixture.task, self.fixture.broker

    def tearDown(self):
        self.fixture.tearDown()

    def hold_broker(self, seconds):
        """Simulate an action in flight: the broker lock is held for its duration."""
        held, release = threading.Event(), threading.Event()

        def worker():
            with self.broker._lock:
                held.set()
                release.wait(seconds)
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        held.wait(2)
        return release, thread

    def test_stop_revokes_at_once_while_a_status_poll_waits_on_the_broker(self):
        release, holder = self.hold_broker(3)
        poll = threading.Thread(target=self.task.status, daemon=True)
        poll.start()
        time.sleep(0.2)  # the poll is now waiting on the broker
        pressed = time.time()
        stopper = threading.Thread(target=lambda: self.task.stop("cancelled"), daemon=True)
        stopper.start()
        deadline = time.time() + 2
        while not self.task.job.get("finished_at") and time.time() < deadline:
            time.sleep(0.01)
        try:
            self.assertTrue(self.task.stopped.is_set())
            self.assertEqual(self.task.job["status"], "cancelled")
            self.assertLess(self.task.job["finished_at"] - pressed, 0.5)
            self.assertEqual(self.task.tokens, {})
        finally:
            release.set()
            holder.join(2)
            stopper.join(5)
            poll.join(5)

    def test_task_context_reads_the_broker_outside_the_task_lock(self):
        self.fixture.approve()
        release, holder = self.hold_broker(3)
        context = threading.Thread(target=lambda: self.fixture.call("task_context"), daemon=True)
        context.start()
        time.sleep(0.2)
        try:
            # The task lock is free while task_context waits on the broker.
            self.assertTrue(self.task.lock.acquire(timeout=0.5))
            self.task.lock.release()
        finally:
            release.set()
            holder.join(2)
            context.join(5)

    def test_status_still_reports_the_operator_session_and_runs(self):
        status = self.task.status()
        self.assertIn("session", status["operator"])
        self.assertEqual(status["runs"], {})
        self.assertTrue(status["active"])


if __name__ == "__main__":
    unittest.main()
