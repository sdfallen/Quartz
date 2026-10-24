import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gui
import main
from core.agent_chat import AgentChatService
from core.conversation_store import ConversationStore


class ConversationDeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'chats.json'
        self.service = AgentChatService(MagicMock(), self.path)
        self.store = self.service.store
        self.original = self.store.get_active()['id']

    def tearDown(self):
        self.temp.cleanup()

    def test_single_delete_is_backed_up_and_persists_without_other_data_loss(self):
        other = self.store.create('Keep', project_id='other')
        target = self.store.create('Delete', project_id='aster-warband')
        self.store.append_message(target['id'], 'user', 'Original text')
        self.store.set_response_detail('technical')
        result = self.service.delete_conversation(target['id'], confirmed=True)
        self.assertEqual(result['deleted_count'], 1)
        self.assertEqual(result['active_conversation']['project_id'], 'aster-warband')
        self.assertEqual(result['active_conversation']['messages'], [])
        backup = json.loads(Path(result['backup']).read_text(encoding='utf-8'))
        self.assertEqual(backup['conversations'][target['id']]['messages'][0]['content'], 'Original text')
        self.assertEqual(self.store.get(other['id']), other)
        loaded = ConversationStore(self.path)
        self.assertNotIn(target['id'], [c['id'] for c in loaded.list()])
        self.assertEqual(loaded.preferences()['response_detail'], 'technical')

    def test_inactive_delete_keeps_active_and_models(self):
        target = self.store.create('Old', project_id='p')
        active = self.store.create('Active', project_id='p')
        self.store.update_agent_model(active['id'], 'codex', 'chosen', 'high')
        self.service.delete_conversation(target['id'], confirmed=True)
        self.assertEqual(self.store.get_active()['id'], active['id'])
        self.assertEqual(self.store.get_active()['models']['codex']['model'], 'chosen')

    def test_delete_all_in_active_project_preserves_other_projects_and_files(self):
        root = Path(self.temp.name) / 'project'
        root.mkdir(); (root / 'source.txt').write_text('keep')
        a = self.store.create('A', project_id='p')
        b = self.store.create('B', project_id='p')
        other = self.store.create('Other', project_id='q')
        self.store.select(b['id'])
        result = self.service.delete_project_conversations('p', [a['id'], b['id']], confirmed=True)
        self.assertEqual(result['deleted_count'], 2)
        self.assertEqual(result['active_conversation']['project_id'], 'p')
        self.assertEqual(result['active_conversation']['title'], 'Yeni Sohbet')
        self.assertEqual(self.store.get(other['id']), other)
        self.assertEqual((root / 'source.txt').read_text(), 'keep')

    def test_legacy_default_project_and_stale_project_confirmation(self):
        a = self.store.create('Explicit', project_id='squad-pilot')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.service.delete_project_conversations('squad-pilot', [a['id']], confirmed=True)
        self.assertEqual(self.path.read_bytes(), before)
        result = self.service.delete_project_conversations('squad-pilot', [a['id'], self.original], confirmed=True)
        self.assertEqual(result['deleted_count'], 2)

    def test_confirmation_and_active_turn_reject_before_write(self):
        before = self.path.read_bytes()
        for value in (False, None, 'true', 1):
            with self.assertRaises(PermissionError):
                self.service.delete_conversation(self.original, confirmed=value)
        self.service._active_turn = {'status': 'running'}
        with self.assertRaises(RuntimeError):
            self.service.delete_conversation(self.original, confirmed=True)
        self.service._active_turn = {'status': 'cancelling'}
        with self.assertRaises(RuntimeError):
            self.service.delete_conversation(self.original, confirmed=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / 'quartz_deleted_chats').exists())

    def test_deleted_terminal_turn_cannot_be_polled_as_stale_chat(self):
        self.service._active_turn = {'status': 'completed', 'conversation_id': self.original}
        self.service.delete_conversation(self.original, confirmed=True)
        self.assertEqual(self.service.poll_active(), {'active': False})

    def test_backup_or_commit_failure_preserves_store_and_disk(self):
        import core.conversation_store as module
        real = module.atomic_write_json
        before = self.path.read_bytes()
        for stage in ('backup', 'commit'):
            def fail(path, value):
                if (Path(path) == self.path) == (stage == 'commit'):
                    raise OSError('test failure')
                return real(path, value)
            with patch.object(module, 'atomic_write_json', side_effect=fail):
                with self.assertRaises(OSError):
                    self.service.delete_conversation(self.original, confirmed=True)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(self.store.get_active()['id'], self.original)

    def test_ipc_requires_confirmation_for_single_and_project_delete(self):
        server = main.IPCServer(MagicMock())
        server._agent_chat = self.service
        with self.assertRaises(PermissionError):
            server._dispatch_action({'action': 'chat_delete', 'data': {'conversation_id': self.original}})
        result = server._dispatch_action({'action': 'chat_delete_project', 'data': {
            'project_id': 'squad-pilot', 'conversation_ids': [self.original], 'confirmed': True}})
        self.assertEqual(result['data']['deleted_count'], 1)

    def test_gui_refuses_delete_during_natural_or_coordination_task(self):
        api = gui.Api()
        for attr in ('_natural', '_coordination'):
            setattr(api, attr, SimpleNamespace(status=lambda: {'active': True}))
            with patch.object(gui, 'ipc_send') as send:
                self.assertEqual(api.chat_delete('id', True)['status'], 'error')
                self.assertEqual(api.chat_delete_project('p', ['id'], True)['status'], 'error')
                send.assert_not_called()
            setattr(api, attr, None)
        api._desktop_agents = SimpleNamespace(status=lambda: {'session': {'active': True}})
        with patch.object(gui, 'ipc_send') as send:
            self.assertEqual(api.chat_delete('id', True)['status'], 'error')
            send.assert_not_called()

    def test_ui_has_separate_accessible_delete_buttons_and_explicit_confirmation(self):
        self.assertIn("remove.setAttribute('aria-label'", gui._HTML)
        self.assertIn("window.confirm(message", gui._HTML)
        self.assertIn("btnDeleteProjectChats", gui._HTML)
        self.assertIn("c.project_id||'squad-pilot'", gui._HTML)

    def test_actual_javascript_confirmation_cancel_bulk_and_error_paths(self):
        # Execute the actual handler, not a separate implementation. No browser,
        # user history, model call or native UI deletion is involved.
        start = gui._HTML.index('  async function requestChatDeletion(')
        end = gui._HTML.index('  function renderConversationNavigation(', start)
        handler = gui._HTML[start:end]
        harness = r'''
const assert=require('node:assert/strict');
let thinking=false,deletionPending=false,chatPollInterval=null,activeBotBubble=null;
let reloads=0,calls=[],errors=[],accepted=false,response={status:'ok',data:{deleted_count:1}};
const mainProjectSelect={selectedOptions:[{textContent:'Project P'}]};
const window={confirm:()=>accepted,pywebview:{api:{
chat_delete:async(...a)=>{calls.push(['single',...a]);return response;},
chat_delete_project:async(...a)=>{calls.push(['project',...a]);return response;}}}};
const loadActiveConversation=async()=>reloads++;
const logLine=()=>{};const appendMsg=(...a)=>errors.push(a);
'''
        checks = r'''
(async()=>{
const a={id:'a',title:'A'},b={id:'b',title:'B'};
await requestChatDeletion([a]);assert.equal(calls.length,0);assert.equal(reloads,0);
accepted=true;await requestChatDeletion([a]);assert.deepEqual(calls.pop(),['single','a',true]);
assert.equal(reloads,1);assert.equal(deletionPending,false);
await requestChatDeletion([a,b],'p');assert.deepEqual(calls.pop(),['project','p',['a','b'],true]);
assert.equal(reloads,2);
response={status:'error',data:'busy'};await requestChatDeletion([a]);
assert.equal(errors.length,1);assert.equal(reloads,2);assert.equal(deletionPending,false);
thinking=true;await requestChatDeletion([a]);assert.equal(calls.length,1);
console.log('actual delete handler: cancel/single/project/error/busy PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-'], input=harness + handler + checks,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
