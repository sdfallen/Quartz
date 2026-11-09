import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.chat_environment_health import ChatEnvironmentHealth
from core.agent_chat import AgentChatService


class ChatHealthTests(unittest.TestCase):
    def test_poll_is_nonblocking_and_project_switch_fences_old_result(self):
        entered, release = threading.Event(), threading.Event()
        def slow(key):
            entered.set()
            release.wait(2)
            return {'status': 'ok', 'project': key[0], 'checks': []}
        health = ChatEnvironmentHealth()
        health.snapshot.loader = slow
        try:
            health.read('project-one', 'codex', {})
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            result = health.read('project-two', 'codex', {})
            self.assertLess(time.monotonic() - started, .2)
            self.assertEqual(result['status'], 'warn')
            self.assertNotIn('project', result)
        finally:
            health.close()
            release.set()

    def test_force_changes_generation_and_volatile_diagnostics_do_not(self):
        health = ChatEnvironmentHealth()
        health.snapshot.read = MagicMock(return_value=({'checks': []}, {}))
        health.read('p', 'codex', {'codex': {'ready': True, 'timestamp': 1}})
        first = health.snapshot.read.call_args.args[0]
        health.read('p', 'codex', {'codex': {'ready': True, 'timestamp': 2}})
        self.assertEqual(first, health.snapshot.read.call_args.args[0])
        health.read('p', 'codex', {'codex': {'ready': True}}, True)
        self.assertNotEqual(first, health.snapshot.read.call_args.args[0])
        health.close()

    def test_loader_passes_existing_diagnostics_and_minimal_environment(self):
        raw = {'codex': {}, 'antigravity': {}, 'squad': {}}
        with patch('core.environment_health.check', return_value={'status': 'ok'}) as check, \
             patch('core.cli_installer.cli_environment', return_value={'PATH': 'fixture-bin', 'TOKEN': 'private'}):
            ChatEnvironmentHealth._load(('p', 'codex', json.dumps(raw), 0))
        kwargs = check.call_args.kwargs
        self.assertEqual(kwargs['agents'], raw)
        self.assertEqual(kwargs['squad'], raw['squad'])
        self.assertEqual(kwargs['env'], {'PATH': 'fixture-bin'})

    def test_status_and_ipc_contract(self):
        import main
        with tempfile.TemporaryDirectory() as root:
            service = MagicMock()
            service.projects.get.return_value = {'path': root}
            chat = AgentChatService(service, Path(root) / 'chats.json')
            chat._diagnostics.read = MagicMock(return_value=({'codex': {'ready': True}, 'squad': {}}, {}))
            chat._environment_health.read = MagicMock(return_value={'status': 'warn', 'checks': []})
            try:
                self.assertEqual(chat.status()['environment_health']['status'], 'warn')
                self.assertEqual(chat._environment_health.read.call_args.args[2]['codex'], {'ready': True})
                server = main.IPCServer(MagicMock())
                server._agent_chat = chat
                self.assertEqual(server._dispatch_action({'action': 'environment_health', 'data': {'force': True}})['data']['status'], 'warn')
                self.assertIs(chat._environment_health.read.call_args.args[3], True)
                server._dispatch_action({'action': 'environment_health', 'data': {'force': 'yes'}})
                self.assertIs(chat._environment_health.read.call_args.args[3], False)
            finally:
                chat._diagnostics.close()
                chat._environment_health.close()
