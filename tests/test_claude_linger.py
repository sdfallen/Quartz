"""A Claude turn ends once Claude has answered, even if a program it started stays open (25 Nov 2026).

Live: Fatum finished the three-stage test app and answered "Başarılı … Test penceresi hâlâ açık",
but the app it had started from its shell kept the CLI and the turn running for good.
"""
import threading
import time
import unittest
from unittest.mock import patch

from core import claude_runtime
from core.claude_runtime import ClaudeRuntime


class FakeProcess:
    def __init__(self):
        self.alive = True

    def poll(self):
        return None if self.alive else 0


def runtime_with(record):
    rt = ClaudeRuntime.__new__(ClaudeRuntime)
    rt._lock = threading.RLock()
    rt._runs = {"r1": record}
    return rt


class CloseAfterAnswerTests(unittest.TestCase):
    def test_a_lingering_process_is_closed_after_the_answer_and_the_grace(self):
        process = FakeProcess()
        record = {"status": "running", "_result_at": time.time() - 30, "result": "Başarılı."}
        closed = []
        with patch.object(claude_runtime, "stop_process_tree", lambda p, timeout: closed.append(p)):
            runtime_with(record)._close_after_answer("r1", process, grace=20, poll=0.01)
        self.assertEqual(closed, [process])
        self.assertTrue(record["_closed_after_result"])
        self.assertIn("kapatıldı", record["notes"][0])

    def test_nothing_is_closed_before_an_answer(self):
        process = FakeProcess()
        record = {"status": "running"}
        closed = []
        threading.Timer(0.1, lambda: setattr(process, "alive", False)).start()
        with patch.object(claude_runtime, "stop_process_tree", lambda p, timeout: closed.append(p)):
            runtime_with(record)._close_after_answer("r1", process, grace=0, poll=0.01)
        self.assertEqual(closed, [])
        self.assertNotIn("_closed_after_result", record)

    def test_a_finished_or_stopped_run_is_left_alone(self):
        process = FakeProcess()
        record = {"status": "cancelled", "_result_at": time.time() - 100}
        closed = []
        with patch.object(claude_runtime, "stop_process_tree", lambda p, timeout: closed.append(p)):
            runtime_with(record)._close_after_answer("r1", process, grace=0, poll=0.01)
        self.assertEqual(closed, [])

    def test_the_turn_counts_on_the_answer(self):
        source = (claude_runtime.__file__.replace("claude_runtime.py", "codex_runtime.py"))
        text = open(source, encoding="utf-8").read()
        self.assertIn('(code == 0 or record.get("_closed_after_result")) and record.get("result")', text)


if __name__ == "__main__":
    unittest.main()
