"""Review regressions: controlled fake processes, never user processes."""
import itertools
import io
import subprocess
import sys
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

from core.codex_runtime import CodexRuntime
from core.antigravity_runtime import AntigravityRuntime
from core.process_tree import stop_process_tree
from scripts.check_gui_javascript import application_script


class ReviewTests(unittest.TestCase):
    def test_terminal_output_cannot_replace_session_identity(self):
        for cls, raw, field in (
                (CodexRuntime, '{"type":"thread.started","thread_id":"late"}\n', 'thread_id'),
                (AntigravityRuntime, '{"event":"init","conversation_id":"late"}\n', 'conversation_id')):
            with self.subTest(provider=cls.__name__):
                rt = cls.__new__(cls)
                rt._lock = threading.RLock()
                rt._runs = {'r': {'status': 'completed', 'events': [], field: 'original'}}
                rt._read_stdout('r', types.SimpleNamespace(stdout=io.StringIO(raw)))
                self.assertEqual(rt._runs['r'][field], 'original')
                self.assertEqual(rt._runs['r']['events'], [])

    def test_shutdown_does_not_claim_unstoppable_process_is_cleaned(self):
        for cls, module in ((CodexRuntime, 'core.codex_runtime'),
                            (AntigravityRuntime, 'core.antigravity_runtime')):
            with self.subTest(provider=cls.__name__):
                rt = cls.__new__(cls)
                rt._lock = threading.RLock()
                proc = MagicMock(); proc.poll.return_value = None
                rt._processes = {'r': proc}
                rt._runs = {'r': {'status': 'running', 'errors': [], 'events': []}}
                rt.cancel = MagicMock()
                with self.assertRaises(RuntimeError): rt.shutdown()
                rt.cancel.assert_called_once_with('r')

    def test_javascript_guard_rejects_empty_malformed_and_duplicate_blocks(self):
        for source in ('', '<script>short</script>', '<script >' + 'x' * 1001 + '</script>',
                       '<script>' + 'x' * 1001 + '</script><script>' + 'x' * 1001 + '</script>'):
            with self.subTest(source_size=len(source)), self.assertRaises(ValueError):
                application_script(source)
        self.assertEqual(application_script('<script>' + 'x' * 1001 + '</script>'), 'x' * 1001)

    def test_codex_deadline_is_opt_in_and_invalid_values_are_rejected(self):
        self.assertIsNone(CodexRuntime._parse_timeout_seconds(None))
        self.assertEqual(CodexRuntime._parse_timeout_seconds('2m'), 120)
        for value in (float('inf'), float('nan'), True, -2, 'invalid'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CodexRuntime._parse_timeout_seconds(value)

    def test_parent_exit_does_not_confirm_a_surviving_child(self):
        child, parent, proc = MagicMock(), MagicMock(), MagicMock()
        parent.children.return_value = [child]
        proc.poll.side_effect = itertools.chain([None, None], itertools.repeat(0))
        fake = types.SimpleNamespace(Process=lambda pid: parent,
            wait_procs=MagicMock(side_effect=[([parent], [child]), ([], [child])]),
            NoSuchProcess=type('Gone', (Exception,), {}),
            AccessDenied=type('Denied', (Exception,), {}), Error=type('Error', (Exception,), {}))
        with patch.dict(sys.modules, {'psutil': fake}):
            self.assertFalse(stop_process_tree(proc, timeout=.01))

    def test_observed_child_can_be_reaped_after_parent_exited(self):
        child, parent, proc = MagicMock(), MagicMock(), MagicMock()
        parent.children.return_value = [child]
        proc.poll.side_effect = itertools.chain([None, None], itertools.repeat(0))
        factory = MagicMock(return_value=parent)
        fake = types.SimpleNamespace(Process=factory,
            wait_procs=MagicMock(side_effect=[([parent], [child]), ([], [child]), ([child], [])]),
            NoSuchProcess=type('Gone', (Exception,), {}),
            AccessDenied=type('Denied', (Exception,), {}), Error=type('Error', (Exception,), {}))
        with patch.dict(sys.modules, {'psutil': fake}):
            self.assertFalse(stop_process_tree(proc, timeout=.01))
            self.assertEqual(proc._quartz_pending_children, [child])
            self.assertTrue(stop_process_tree(proc, timeout=.01))
            self.assertEqual(proc._quartz_pending_children, [])
            self.assertEqual(factory.call_count, 1)  # Never reconstruct an orphan by PID.

    def test_unconfirmed_exit_keeps_process_and_writer_owned(self):
        for cls, module in ((CodexRuntime, 'core.codex_runtime'),
                            (AntigravityRuntime, 'core.antigravity_runtime')):
            with self.subTest(provider=cls.__name__):
                exited, entered, done = threading.Event(), threading.Event(), threading.Event()
                proc = MagicMock()
                def wait(timeout=None):
                    entered.set()
                    if exited.wait(.01): return 0
                    raise subprocess.TimeoutExpired('owned-fixture', timeout)
                proc.wait.side_effect = wait
                proc.poll.side_effect = lambda: 0 if exited.is_set() else None
                rt = cls.__new__(cls)
                rt._lock = threading.RLock()
                rt._runs = {'r': {'status': 'running', 'timeout_seconds': .01,
                    'cancel_requested': False, 'errors': [], 'result': '', 'remote_status': '',
                    'denied_actions': []}}
                rt._processes, rt._writers = {'r': proc}, {'project': 'r'}
                def watcher():
                    try: rt._wait('r', proc, 'project', MagicMock(), MagicMock())
                    finally: done.set()
                with patch(module + '.stop_process_tree', return_value=False):
                    thread = threading.Thread(target=watcher, daemon=True)
                    thread.start()
                    try:
                        self.assertTrue(entered.wait(1))
                        done.wait(.1)
                        self.assertIn('r', rt._processes)
                        self.assertEqual(rt._writers.get('project'), 'r')
                        self.assertNotIn(rt._runs['r']['status'], rt.TERMINAL)
                    finally:
                        exited.set()
                        thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(rt._runs['r']['status'], 'failed')
                self.assertNotIn('r', rt._processes)
                self.assertNotIn('project', rt._writers)
