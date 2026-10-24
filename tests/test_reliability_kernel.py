import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.agent_chat import AgentChatService
from core.async_snapshot import AsyncSnapshot
from core.natural_desktop import NaturalDesktopTask
from core.task_outcome import execution_outcome


class SnapshotTests(unittest.TestCase):
    def idle(self, cache):
        worker = cache.worker
        if worker: worker.join(1)
        self.assertIsNone(cache.worker)

    def test_many_polls_do_not_wait_or_duplicate_slow_loader(self):
        entered, release = threading.Event(), threading.Event()
        def load(key):
            entered.set(); release.wait(2); return {'project': key}
        cache = AsyncSnapshot(load)
        try:
            started = time.monotonic()
            for _ in range(100):
                value, state = cache.read('a', {'seed': True})
                self.assertEqual(value, {'seed': True})
            self.assertLess(time.monotonic() - started, .5)
            self.assertTrue(entered.wait(1)); self.assertTrue(state['refreshing'])
        finally:
            release.set(); self.idle(cache); cache.close()

    def test_old_project_result_cannot_replace_new_project(self):
        release = threading.Event()
        cache = AsyncSnapshot(lambda key: (release.wait(2), {'project': key})[1])
        cache.read('old'); worker = cache.worker
        cache.read('new', {'project': 'new-seed'})
        release.set(); worker.join(1)
        value, _ = cache.read('new', {'project': 'new-seed'})
        self.assertNotEqual(value.get('project'), 'old')
        worker = cache.worker
        if worker: worker.join(1)
        cache.close()

    def test_failed_refresh_retains_last_good_result_and_reports_error(self):
        clock = [1.0]
        loader = Mock(return_value={'ok': True})
        cache = AsyncSnapshot(loader, clock=lambda: clock[0])
        cache.read('a'); self.idle(cache)
        clock[0] = 20; loader.side_effect = RuntimeError('probe failed')
        cache.read('a'); self.idle(cache)
        value, state = cache.read('a')
        self.assertTrue(value['ok']); self.assertTrue(state['stale'])
        self.assertEqual(state['error'], 'probe failed'); self.assertEqual(loader.call_count, 2)
        cache.close()

    def test_chat_history_and_saved_models_available_while_probe_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            release = threading.Event()
            agents = Mock()
            agents.status.side_effect = lambda _: (release.wait(2), {})[1]
            agents.local_status.return_value = {'projects':[{'id':'project','path':directory}]}
            chat = AgentChatService(agents, Path(directory)/'chat.json')
            try:
                cid = chat.store.get_active()['id']
                chat.store.update_agent_model(cid, 'codex', model='chosen-model', effort='high')
                started = time.monotonic()
                result = chat.status()
                self.assertLess(time.monotonic() - started, .5)
                self.assertEqual(result['active_conversation']['id'], cid)
                self.assertEqual(result['models']['codex']['default_model'], 'chosen-model')
                self.assertTrue(result['diagnostics']['refreshing'])
                self.assertEqual(result['projects'][0]['id'], 'project')
                agents.list_models.assert_not_called()
            finally:
                release.set(); self.idle(chat._diagnostics); chat.close()


class TurnOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.agents = Mock()
        self.chat = AgentChatService(self.agents, Path(self.temp.name)/'chat.json')

    def test_new_turn_is_rejected_while_cancellation_is_releasing_resources(self):
        self.chat._active_turn = {'status': 'cancelling'}
        with self.assertRaises(RuntimeError): self.chat.send_message('Merhaba')

    def test_old_cancel_callback_cannot_cancel_new_generation(self):
        conv = self.chat.store.get_active()
        old = {'turn_id': 'old', 'conversation_id': conv['id'], 'message_ids': [],
               'status': 'running', 'run_ids': ['old-run']}
        new = {'turn_id': 'new', 'status': 'running', 'run_ids': []}
        self.chat._active_turn = old
        def cancel(_):
            self.chat._active_turn = new
        self.agents.cancel.side_effect = cancel
        self.chat.cancel_active()
        self.assertEqual(new['status'], 'running')

    def test_unowned_progress_cannot_register_a_late_run_in_new_turn(self):
        self.chat._active_turn = {'status': 'running', 'message_id': 'new',
                                  'message_ids': ['new'], 'run_ids': []}
        self.chat._set_turn_progress('late', current_msg_id='old', run_id='late-run')
        self.assertEqual(self.chat._active_turn['message_id'], 'new')
        self.assertEqual(self.chat._active_turn['run_ids'], [])

    def test_old_stream_result_cannot_overwrite_cancelled_message_or_session(self):
        cid = self.chat.store.get_active()['id']
        message = self.chat.store.append_message(cid, 'assistant', 'cancelled', sender='codex', metadata={'status':'cancelled'})
        self.chat._active_turn = {'status':'cancelled', 'message_ids':[message['id']]}
        self.assertFalse(self.chat._publish_run_update(cid, message['id'], 'late success', {'status':'completed'},
                                                     provider='codex', session='late-thread'))
        conv = self.chat.store.get(cid)
        self.assertEqual(conv['messages'][-1]['content'], 'cancelled')
        self.assertIsNone(conv['sessions']['codex'])

    def test_stale_terminal_callback_does_not_finish_new_turn(self):
        self.chat._active_turn = {'status':'running', 'message_ids':['new'], 'run_id':'new-run'}
        self.assertFalse(self.chat._finish_turn('old', 'completed'))
        self.assertEqual(self.chat._active_turn['run_id'], 'new-run')
        self.assertTrue(self.chat._finish_turn('new', 'failed'))
        self.assertFalse(self.chat._finish_turn('new', 'completed'))


class IndependentPermissionTests(unittest.TestCase):
    def test_log_only_consent_does_not_revoke_or_extend_existing_input(self):
        from tests.test_natural_desktop import NaturalTaskTests
        fixture = NaturalTaskTests('test_metadata_and_model_request_never_grant_input')
        fixture.setUp(); self.addCleanup(fixture.tearDown)
        fixture.approve()
        connection = dict(fixture.task.connection)
        session_id = fixture.broker.status()['id']
        (fixture.root/'extra.log').write_text('real fixture bytes', encoding='utf-8')
        result = fixture.call('task_read_log', {'path':'extra.log'}, 'review')
        self.assertEqual(result['status'], 'waiting_for_inline_permission')
        self.assertTrue(fixture.broker.status()['active'])
        self.assertEqual(fixture.task.connection, connection)
        fixture.task.approve(fixture.task.pending['id'], confirmed=True)
        self.assertEqual(fixture.broker.status()['id'], session_id)
        self.assertEqual(fixture.task.connection, connection)
        self.assertIn('real fixture bytes', fixture.call('task_read_log', {'path':'extra.log'}, 'review')['untrusted_log']['text'])


class CleanupTests(unittest.TestCase):
    def test_every_release_attempted_and_persisted_even_after_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = Mock(); broker.status.return_value = {'active': False}; broker.audit = []
            task = NaturalDesktopTask(SimpleNamespace(broker=broker), Mock(side_effect=RuntimeError('emit down')),
                                      factories={}, evidence_root=directory)
            task.evidence = Path(directory)
            task.job = {'id':'t', 'conversation_id':'c', 'status':'running', 'events':[],
                        'roles':{'operator':'codex'}, 'task_id':'s', 'verification':{'status':'NOT VERIFIED'}}
            task.agent_ids = {'codex':'op'}; task.squad = Mock()
            first, second = Mock(), Mock()
            for runtime in (first, second): runtime.get.return_value = {'status':'cancelled'}
            first.cancel.side_effect = RuntimeError('cancel failed')
            task.runs = {'codex':(first,'a'), 'antigravity':(second,'b')}
            task.tokens = {'codex':'old-token'}
            task.server = Mock()
            result = task.stop()
            second.cancel.assert_called_once_with('b')
            self.assertEqual(task.tokens, {}); self.assertFalse(result['active'])
            self.assertEqual(result['job']['status'], 'cancelled')
            self.assertEqual(result['job']['cleanup']['status'], 'failed')
            evidence = json.loads((Path(directory)/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(evidence['cleanup']['status'], 'failed')
            task.stop(); second.cancel.assert_called_once()

    def test_completed_process_does_not_mean_goal_verified(self):
        result = execution_outcome('completed', {'status':'OBSERVED UI CRITERION VERIFIED', 'scope':'exact UI text'})
        self.assertFalse(result['goal_accepted'])
        self.assertEqual(result['execution_status'], 'completed')
        self.assertEqual(result['evidence_scope'], 'exact UI text')
