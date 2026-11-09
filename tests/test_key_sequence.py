"""One desktop_act key action may carry a short key sequence (live exam 9 Nov, exam-desk-03).

Eight single-key actions, each with its own observation and model turn, took 4 minutes
for "1234 x 56" on Calculator. A sequence is one action, keeps the SAFE_KEYS profile and
stops at the first Stop or foreground change without sending the remaining keys.
"""
import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from core.desktop_broker import DesktopBroker
from core.desktop_native import MAX_KEY_SEQUENCE, NativeDesktopBackend


class KeySequenceTests(unittest.TestCase):
    def press(self, args, *, foreground=None, cancelled=None):
        backend = NativeDesktopBackend()
        keyboard = MagicMock()

        @contextmanager
        def scope():
            yield MagicMock()
        if cancelled is not None:
            backend.input_cancelled = cancelled
        with patch.object(backend.controller, "_desktop", scope), \
             patch.object(backend.controller, "_window", return_value=MagicMock()), \
             patch.object(backend.controller, "focused_control", return_value=None), \
             patch.object(backend, "is_foreground", side_effect=foreground or (lambda _t: True)), \
             patch.object(backend, "_safe_controls"), \
             patch.object(backend, "_before_input"), \
             patch.dict("sys.modules", {"pyautogui": keyboard}):
            error = None
            try:
                backend.act({"handle": 1}, {}, args)
            except Exception as exc:  # noqa: BLE001 - the test inspects it
                error = exc
        return [c.args[0] for c in keyboard.press.call_args_list], error

    def test_a_sequence_is_sent_in_order_as_one_action(self):
        pressed, error = self.press({"action": "key", "key": "1 2 3 4 * 5 6 Enter"})
        self.assertIsNone(error)
        self.assertEqual(pressed, ["1", "2", "3", "4", "multiply", "5", "6", "enter"])

    def test_a_single_key_still_works(self):
        self.assertEqual(self.press({"action": "key", "key": "Tab"}), (["tab"], None))

    def test_unsafe_or_too_long_sequences_send_nothing(self):
        for key in ("1 ctrl+a", "f13", "1 2 win+r", " ", "", " ".join(["1"] * (MAX_KEY_SEQUENCE + 1))):
            with self.subTest(key=key):
                pressed, error = self.press({"action": "key", "key": key})
                self.assertEqual(pressed, [])
                self.assertIsInstance(error, PermissionError)

    def test_hold_takes_one_key_only(self):
        pressed, error = self.press({"action": "hold", "key": "1 2", "seconds": 0.1})
        self.assertEqual(pressed, [])
        self.assertIsInstance(error, PermissionError)

    def test_stop_mid_sequence_sends_no_further_key(self):
        state = {"calls": 0}

        def cancelled():
            state["calls"] += 1
            return state["calls"] > 2  # Stop arrives after the second key
        pressed, error = self.press({"action": "key", "key": "1 2 3 4"}, cancelled=cancelled)
        self.assertEqual(pressed, ["1", "2"])
        self.assertRegex(str(error), "Stopped after 2 of 4 keys")

    def test_focus_change_mid_sequence_sends_no_further_key(self):
        answers = iter([True, True, False])
        pressed, error = self.press({"action": "key", "key": "1 2 3 4"},
                                    foreground=lambda _t: next(answers, False))
        self.assertEqual(pressed, ["1", "2"])
        self.assertRegex(str(error), "Foreground changed after 2 of 4 keys")


class BrokerCancelTests(unittest.TestCase):
    def test_stop_raises_the_cancel_flag_without_waiting_for_the_broker_lock(self):
        broker = DesktopBroker(MagicMock())
        held, release = threading.Event(), threading.Event()

        def in_flight_action():
            with broker._lock:
                held.set()
                release.wait(3)
        worker = threading.Thread(target=in_flight_action, daemon=True)
        worker.start()
        held.wait(2)
        stopper = threading.Thread(target=broker.stop, daemon=True)
        stopper.start()
        try:
            deadline = time.time() + 0.5
            while not broker._input_cancel.is_set() and time.time() < deadline:
                time.sleep(0.01)
            self.assertTrue(broker._input_cancel.is_set())
        finally:
            release.set()
            worker.join(3)
            stopper.join(3)

    def test_a_new_grant_clears_the_cancel_flag(self):
        broker = DesktopBroker(MagicMock())
        broker.stop()
        self.assertTrue(broker._input_cancel.is_set())
        try:
            broker.grant(1, "codex", confirmed=True)
        except Exception:
            pass  # the mock backend may refuse later checks; the flag is cleared first
        self.assertFalse(broker._input_cancel.is_set())


if __name__ == "__main__":
    unittest.main()
