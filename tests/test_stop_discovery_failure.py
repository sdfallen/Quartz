"""Owned-process Stop fault paths; no real user processes or provider calls."""
import subprocess
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

import psutil

from core.process_tree import owned_cleanup_pending, stop_process_tree, wait_for_owned_cleanup
from core.codex_runtime import CodexRuntime
from core.antigravity_runtime import AntigravityRuntime
from core.tool_workbench.execution import ToolExecutor


class OwnedStub:
    pid = 24680  # Never looked up: psutil.Process is patched for stub cases.

    def __init__(self, *, stubborn=False, terminate_error=False, kill_error=False):
        self.code = None
        self.terminates = self.kills = 0
        self.stubborn, self.terminate_error, self.kill_error = stubborn, terminate_error, kill_error

    def poll(self):return self.code
    def terminate(self):
        self.terminates += 1
        if self.terminate_error:raise OSError('fixture terminate denied')
        if not self.stubborn:self.code = -15
    def kill(self):
        self.kills += 1
        if self.kill_error:raise OSError('fixture kill denied')
        self.code = -9
    def wait(self, timeout=None):
        if self.code is None:raise subprocess.TimeoutExpired('owned fixture', timeout)
        return self.code


class StopDiscoveryFailureTests(unittest.TestCase):
    def denied_children(self, process):
        parent = MagicMock()
        parent.children.side_effect = psutil.AccessDenied(process.pid)
        return parent

    def test_children_access_denied_still_terminates_owned_root(self):
        proc = OwnedStub();parent = self.denied_children(proc)
        with patch('psutil.Process', return_value=parent), patch('psutil.wait_procs', return_value=([], [])):
            self.assertFalse(stop_process_tree(proc, .01))
        self.assertEqual(proc.terminates, 1)
        self.assertIsNotNone(proc.poll())
        self.assertTrue(getattr(proc, '_quartz_tree_discovery_incomplete', False))
        self.assertFalse(stop_process_tree(proc, .01))  # Root exit cannot erase uncertainty.

    def test_missing_psutil_identity_still_terminates_owned_root(self):
        proc = OwnedStub()
        with patch('psutil.Process', side_effect=psutil.NoSuchProcess(proc.pid)):
            self.assertFalse(stop_process_tree(proc, .01))
        self.assertEqual(proc.terminates, 1)
        self.assertIsNotNone(proc.poll())

    def test_owned_root_timeout_escalates_to_kill(self):
        proc = OwnedStub(stubborn=True)
        with patch('psutil.Process', side_effect=psutil.AccessDenied(proc.pid)):
            self.assertFalse(stop_process_tree(proc, .01))
        self.assertEqual((proc.terminates, proc.kills), (1, 1))
        self.assertIsNotNone(proc.poll())

    def test_owned_root_errors_are_not_success_or_unhandled(self):
        proc = OwnedStub(terminate_error=True, kill_error=True)
        with patch('psutil.Process', side_effect=psutil.AccessDenied(proc.pid)):
            self.assertFalse(stop_process_tree(proc, .01))
        self.assertEqual(proc.terminates, 1)
        self.assertIsNone(proc.poll())

    def test_missing_psutil_does_not_skip_root_stop_with_known_children(self):
        proc = OwnedStub();child = MagicMock();proc._quartz_pending_children = [child]
        with patch.dict(sys.modules, {'psutil': None}):
            self.assertFalse(stop_process_tree(proc, .01))
        self.assertEqual(proc.terminates, 1)
        self.assertEqual(proc._quartz_pending_children, [child])

    def test_verification_failure_retains_observed_identities_for_retry(self):
        proc = OwnedStub();parent = MagicMock();child = MagicMock()
        parent.children.return_value = [child]
        with patch('psutil.Process', return_value=parent) as discover, \
             patch('psutil.wait_procs', side_effect=psutil.AccessDenied(proc.pid)):
            self.assertFalse(stop_process_tree(proc, .01))
        self.assertEqual(proc.terminates, 1)
        self.assertIn(child, proc._quartz_pending_children)
        with patch('psutil.Process', side_effect=AssertionError('Do not rediscover an exited root')), \
             patch('psutil.wait_procs', return_value=([], [])):
            self.assertTrue(stop_process_tree(proc, .01))
        self.assertEqual(proc._quartz_pending_children, [])
        self.assertEqual(discover.call_count, 1)

    def test_watcher_does_not_confirm_exited_root_with_unknown_tree(self):
        proc = OwnedStub();proc.code = 0;proc._quartz_tree_discovery_incomplete = True
        with self.assertRaisesRegex(RuntimeError, 'tree_discovery_incomplete'):
            wait_for_owned_cleanup(proc, lambda: None)

    def test_tool_fallback_retains_unknown_tree_unless_job_proves_empty(self):
        proc = OwnedStub();proc.code = 0;proc._quartz_tree_discovery_incomplete = True
        executor = ToolExecutor.__new__(ToolExecutor)
        record = {'process':proc, 'job':None, 'children':{}, 'observation_failed':False}
        self.assertFalse(executor._tree_empty(record))
        job = MagicMock();job.empty.return_value = True;record['job'] = job
        self.assertTrue(executor._tree_empty(record))

    def test_root_exit_cannot_race_a_still_running_tree_verification(self):
        proc = OwnedStub();parent = MagicMock();parent.children.return_value = []
        parent.terminate.side_effect = lambda: setattr(proc, 'code', 0)
        verifying, release, observer_started, observed = (threading.Event() for _ in range(4))
        results = []
        def waiting(*args, **kwargs):
            verifying.set()
            if not release.wait(3):raise OSError('fixture gate timeout')
            return [], []
        def observe():
            observer_started.set()
            results.append(owned_cleanup_pending(proc, include_root=False))
            observed.set()
        with patch('psutil.Process', return_value=parent), patch('psutil.wait_procs', side_effect=waiting):
            stopper = threading.Thread(target=lambda: stop_process_tree(proc, .01), daemon=True)
            reader = threading.Thread(target=observe, daemon=True)
            stopper.start()
            try:
                self.assertTrue(verifying.wait(2))
                reader.start();self.assertTrue(observer_started.wait(2))
                self.assertFalse(observed.wait(.05))
            finally:
                release.set();stopper.join(2)
                if reader.ident is not None:reader.join(2)
        self.assertFalse(stopper.is_alive())
        self.assertFalse(reader.is_alive())
        self.assertEqual(results, [False])

    def test_runtime_retains_claim_and_shutdown_rejects_unknown_tree(self):
        for cls in (CodexRuntime, AntigravityRuntime):
            with self.subTest(provider=cls.__name__):
                proc = OwnedStub();proc.code = 0;proc._quartz_tree_discovery_incomplete = True
                rt = cls.__new__(cls);rt._lock = threading.RLock()
                rt._runs = {'r': {'status':'running', 'timeout_seconds':.01, 'cancel_requested':True,
                    'errors':[], 'events':[], 'result':'fixture response', 'remote_status':'completed', 'denied_actions':[]}}
                rt._processes, rt._writers = {'r':proc}, {'project':'r'}
                rt._wait('r', proc, 'project', MagicMock(), MagicMock())
                self.assertIn('r', rt._processes)
                self.assertEqual(rt._writers.get('project'), 'r')
                self.assertFalse(rt._runs['r']['process_exit_confirmed'])
                self.assertTrue(rt._runs['r']['cleanup_pending'])
                self.assertEqual(rt._runs['r'].get('cleanup_error'), 'tree_discovery_incomplete')
                with self.assertRaises(RuntimeError):rt.shutdown()

    def test_actual_owned_root_stops_even_when_discovery_fault_is_injected(self):
        process = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(30)'],
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            with patch('psutil.Process', side_effect=psutil.AccessDenied(process.pid)):
                result = stop_process_tree(process, .1)
            self.assertFalse(result)  # Descendant coverage remains unknown.
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)


if __name__ == '__main__':unittest.main()
