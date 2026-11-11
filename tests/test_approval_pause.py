import json
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from tests import test_natural_desktop as fixture


class ApprovalPauseTests(unittest.TestCase):
    def setUp(self): fixture.NaturalTaskTests.setUp(self)
    def tearDown(self): fixture.NaturalTaskTests.tearDown(self)
    call = fixture.NaturalTaskTests.call
    request = fixture.NaturalTaskTests.request
    approve = fixture.NaturalTaskTests.approve

    def test_manual_card_revokes_old_token_and_every_input_route(self):
        self.approve(); old = self.task.connection['token']
        (self.root/'scope.log').write_text('fixture')
        self.call('task_read_log', {'path':'scope.log'})
        self.assertEqual(self.task.job['status'], 'awaiting_approval')
        self.assertIsNone(self.task.connection)
        self.assertFalse(self.broker.status()['active'])
        for name in ('desktop_focus','desktop_observe','desktop_act','desktop_launch','jarvis_input','jarvis_open_app'):
            with self.subTest(name=name), self.assertRaises(PermissionError): self.call(name)
        with self.assertRaises(PermissionError): self.broker.call(old, {'name':'desktop_focus'})
        self.assertEqual(self.backend.actions, [])

    def test_expiry_after_two_hours_is_pause_not_completion_or_failure(self):
        self.task.job['expires_at'] = None
        self.request(); expires = self.task.pending['expires_at']
        with patch('core.natural_desktop.time.time', return_value=expires+7200), \
             patch.object(self.broker, 'renew', wraps=self.broker.renew) as renew, \
             patch.object(self.task, '_launch_provider') as launch:
            watcher = threading.Thread(target=self.task._watch, daemon=True)
            self.task.thread = watcher; watcher.start(); time.sleep(.45)
            self.assertEqual(self.task.job['status'], 'awaiting_approval')
            self.assertNotIn('finished_at', self.task.job)
            self.assertTrue(self.task.pending['expired'])
            self.assertEqual(self.call('task_context')['task_id'], 'test')
            launch.assert_not_called(); renew.assert_not_called()
        self.task.squad.complete_task.assert_not_called()

    def test_expired_card_requires_fresh_ui_request_identity_and_new_observation(self):
        self.request(); old = self.task.pending['id']
        self.task.pending['expires_at'] = 0
        with self.assertRaises(PermissionError): self.task.approve(old, confirmed=True)
        self.task.refresh_permission(old, 'chat', confirmed=True)
        fresh = self.task.pending['id']
        self.assertNotEqual(fresh, old)
        with self.assertRaises(PermissionError): self.task.approve(old, confirmed=True)
        self.task.approve(fresh, confirmed=True)
        self.assertTrue(self.broker.status()['active'])
        with self.assertRaises(PermissionError): self.call('desktop_act', {'snapshot_id':'old'})
        self.assertIsNone(self.task.latest)

    def test_changed_window_wrong_chat_or_generation_cannot_resume(self):
        self.request(); old = self.task.pending['id']
        with self.assertRaises(PermissionError): self.task.refresh_permission(old, 'other', confirmed=True)
        self.backend.target['started'] = 'different'
        with self.assertRaises(PermissionError): self.task.refresh_permission(old, 'chat', confirmed=True)
        self.assertFalse(self.broker.status()['active'])
        self.task.pending['generation'] += 1
        with self.assertRaises(PermissionError): self.task.approve(old, confirmed=True)
        self.assertFalse(self.task.stopped.is_set())

    def test_pause_cancels_both_provider_namespaces_and_requires_actual_exit(self):
        states = [{'status':'running','pid':101,'process_exit_confirmed':False},
                  {'status':'running','pid':102,'process_exit_confirmed':False}]
        runtimes = []
        for state in states:
            def cancel(_, state=state): state['status'] = 'cancelled'
            rt = SimpleNamespace(TERMINAL={'completed','cancelled'}, get=lambda _, state=state:state, cancel=Mock(side_effect=cancel))
            runtimes.append(rt)
        self.task.runs = {'codex':(runtimes[0],'same-id'), 'antigravity':(runtimes[1],'same-id')}
        self.request(); self.task._drain_pause(self.task.job)
        for runtime in runtimes: runtime.cancel.assert_called_once()
        with self.assertRaises(PermissionError): self.task.approve(self.task.pending['id'], confirmed=True)
        self.assertFalse(self.broker.status()['active'])
        for state in states: state['process_exit_confirmed'] = True
        self.task._drain_pause(self.task.job)
        with patch.object(self.task, '_launch_provider') as launch:
            self.task.approve(self.task.pending['id'], confirmed=True)
            self.assertEqual(launch.call_count, 2)

    def test_cleanup_exception_keeps_same_pending_request_and_no_input(self):
        runtime = SimpleNamespace(TERMINAL={'completed'}, get=lambda _: {'status':'running'}, cancel=Mock(side_effect=RuntimeError('cleanup')))
        self.task.runs={'codex':(runtime,'r')}
        self.request(); old=self.task.pending['id']; self.task._drain_pause(self.task.job)
        with self.assertRaises(PermissionError): self.task.approve(old,confirmed=True)
        self.assertEqual(self.task.pending['id'],old)
        self.assertEqual(self.task.job['status'],'awaiting_approval')
        self.task.runs={}

    def test_stop_and_late_approval_cannot_resurrect_the_task(self):
        self.request(); old=self.task.pending['id']; self.task.stop()
        with self.assertRaises(PermissionError): self.task.approve(old,confirmed=True)
        with self.assertRaises(PermissionError): self.task.refresh_permission(old,'chat',confirmed=True)
        self.assertEqual(self.task.tokens,{})
        self.assertFalse(self.broker.status()['active'])
        self.assertEqual(self.task.paused_contexts(), [])

    def test_task_state_file_records_the_final_state_after_a_pause(self):
        # Live 6 Nov (task b873df4c): task-state.json still said "running" after Stop.
        self.request(); self.task.approve(self.task.pending['id'],confirmed=True)
        self.assertEqual(json.loads((self.task.evidence/'task-state.json').read_text())['state'],'running')
        self.task.stop()
        state=json.loads((self.task.evidence/'task-state.json').read_text())
        self.assertEqual(state['state'],'cancelled')
        self.assertIsNone(state['request_id'])
        self.assertEqual(self.task.paused_contexts(), [])

    def test_task_that_never_paused_leaves_no_task_state_file(self):
        self.task.stop()
        self.assertFalse((self.task.evidence/'task-state.json').exists())

    def test_checkpoint_is_context_only_and_full_automatic_scope_is_not_paused(self):
        self.request()
        state=json.loads((self.task.evidence/'task-state.json').read_text())
        self.assertNotIn('targets',state); self.assertNotIn('token',state)
        contexts=self.task.paused_contexts()
        self.assertEqual(contexts[0]['task_id'],'test')
        self.assertFalse(self.broker.status()['active'])
        self.task.approve(self.task.pending['id'],confirmed=True)
        self.task.job['requested_permission_level']='full'
        (self.root/'scope.log').write_text('fixture')
        self.call('task_read_log',{'path':'scope.log'})
        self.assertFalse(self.task._paused()); self.assertTrue(self.broker.status()['active'])

    def test_controller_invocation_is_serialized_before_the_pause_boundary(self):
        entered=threading.Event(); release=threading.Event(); calls=[]
        def effect(): entered.set(); release.wait(2); calls.append('before pause')
        worker=threading.Thread(target=lambda:self.task._effect(self.task.job,effect)); worker.start()
        self.assertTrue(entered.wait(1))
        requested=threading.Thread(target=self.request); requested.start()
        release.set(); worker.join(2); requested.join(2)
        self.assertFalse(worker.is_alive()); self.assertFalse(requested.is_alive())
        with self.assertRaises(PermissionError): self.task._effect(self.task.job,lambda:calls.append('after pause'))
        self.assertEqual(calls,['before pause'])
