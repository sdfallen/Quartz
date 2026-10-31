from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import gui
from core.agent_chat import AgentChatService
from core.multi_agent_service import MultiAgentService
from tests import test_multi_agent_service as service_tests


class WarbandSquadStatusTests(unittest.TestCase):
    def test_warband_idle_uses_task_mode_not_nonexistent_root_db(self):
        service, _, _ = service_tests.MultiAgentServiceTests().make_service()
        service.projects._projects['test']['workflow'] = 'warband'
        squad = MagicMock()
        squad.status.return_value = {'installed': True, 'initialized': False,
            'database': 'root/.squad/messages.db', 'workspace': 'root', 'version': 'squad 0.7.6', 'error': ''}
        with patch.object(service, '_squad', return_value=squad):
            result = service.status('test')
            check = service.check_squad_connection('test', force=True)
        self.assertEqual(result['error'], '')
        self.assertEqual(result['squad']['mode'], 'task-isolated')
        self.assertTrue(result['squad']['ready'])
        self.assertFalse(result['squad']['initialized'])
        self.assertEqual(result['squad']['database'], '')
        self.assertFalse(check['connected'])
        squad.initialize.assert_not_called()
        squad.agents.assert_not_called()
        squad.join.assert_not_called()
        squad.tasks.assert_not_called()
        squad.history.assert_not_called()

    def test_missing_cli_is_not_hidden_by_warband_mode(self):
        squad = MagicMock()
        squad.status.return_value = {'installed': False, 'error': 'CLI unavailable'}
        result = MultiAgentService._task_squad_status(squad)
        self.assertFalse(result['ready'])
        self.assertEqual(result['error'], 'CLI unavailable')

    def test_generic_missing_database_remains_a_real_error(self):
        service, _, _ = service_tests.MultiAgentServiceTests().make_service()
        squad = MagicMock()
        squad.status.return_value = {'installed': True, 'initialized': False}
        squad.agents.side_effect = RuntimeError('not initialized')
        with patch.object(service, '_squad', return_value=squad):
            result = service.status('test')
        self.assertIn('not initialized', result['error'])
        self.assertNotEqual(result['squad'].get('mode'), 'task-isolated')

    def test_chat_propagates_idle_mode_without_claiming_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = MagicMock()
            agents.status.return_value = {'squad': {'installed': True, 'initialized': False,
                'mode': 'task-isolated', 'ready': True, 'message': 'Task scoped', 'error': ''}}
            chat = AgentChatService(agents, Path(directory) / 'chats.json')
            chat.status()  # First poll is non-blocking and starts discovery.
            worker = chat._diagnostics.worker
            if worker: worker.join(1)
            result = chat.status()['squad']
            chat.close()
            self.assertFalse(result['connected'])
            self.assertEqual(result['mode'], 'task-isolated')
            self.assertTrue(result['ready'])

    def test_actual_badge_js_distinguishes_idle_task_connected_and_errors(self):
        start = gui._HTML.index('  function updateSquadBadge(')
        end = gui._HTML.index('  function syncConversationMessages(', start)
        handler = gui._HTML[start:end]
        code = r'''
const assert=require('node:assert/strict');
let activeTaskSquad=null,currentConvId='chat';
const classes=new Set();const badge={classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)}};
const document={getElementById:()=>badge};
'''+handler+r'''
const idle={mode:'task-isolated',ready:true,connected:false,error:''};
updateSquadBadge(idle);assert.equal(badge.textContent,'Squad: Görevle bağlanır');assert(!classes.has('warn'));
activeTaskSquad={connected:true,conversation_id:'chat',database:'actual-task/messages.db'};
updateSquadBadge(idle);assert.equal(badge.textContent,'Squad: Bağlı');assert(badge.title.includes('actual-task/messages.db'));
updateSquadBadge(idle,'other-chat');assert.equal(badge.textContent,'Squad: Görevle bağlanır');
activeTaskSquad=null;updateSquadBadge({...idle,ready:false,error:'CLI failed'});
assert(classes.has('warn'));assert.equal(badge.textContent,'Squad: Bağlantı Sorunu');assert.equal(badge.title,'CLI failed');
updateSquadBadge({connected:false,error:'DB locked'});assert(classes.has('warn'));
console.log('idle vs real connection vs real failure PASS');
'''
        result = subprocess.run(['node', '-'], input=code, capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
