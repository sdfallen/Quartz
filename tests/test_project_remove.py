"""Removing a project from the list (user request 8 Nov: "projeleri silme seçeneği yok").

Only SpeS's registration and the project's chats go; the chats keep a local
recovery copy and the project folder is never touched.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gui
import main
from core.agent_chat import AgentChatService
from core.project_registry import ProjectRegistry


class ProjectRemoveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.folder = root / 'proj'
        self.folder.mkdir()
        (self.folder / 'source.txt').write_text('keep', encoding='utf-8')
        (root / 'pilot').mkdir()
        self.registry_path = root / 'projects.json'
        defaults = ({'id': 'squad-pilot', 'name': 'Squad Pilot', 'path': str(root / 'pilot')},
                    {'id': 'legacy', 'name': 'Legacy', 'path': str(root / 'legacy')})
        self.defaults = defaults
        self.registry = ProjectRegistry(defaults, storage_path=self.registry_path)
        self.project = self.registry.add(str(self.folder), 'Proj')
        self.service = AgentChatService(MagicMock(), root / 'chats.json')
        self.service.agent_service.projects = self.registry
        self.store = self.service.store

    def tearDown(self):
        self.temp.cleanup()

    def test_remove_deletes_its_chats_with_backup_and_keeps_files_and_other_projects(self):
        a = self.store.create('A', project_id=self.project['id'])
        b = self.store.create('B', project_id=self.project['id'])
        self.store.append_message(a['id'], 'user', 'Original')
        other = self.store.create('Other', project_id='squad-pilot')
        self.store.select(b['id'])
        result = self.service.remove_project(self.project['id'], [a['id'], b['id']], confirmed=True)
        self.assertEqual(result['deleted_count'], 2)
        self.assertFalse(result['files_deleted'])
        self.assertEqual((self.folder / 'source.txt').read_text(encoding='utf-8'), 'keep')
        self.assertNotIn(self.project['id'], [p['id'] for p in self.registry.list()])
        self.assertEqual(self.store.get(other['id']), other)
        # The new active conversation belongs to a project that still exists.
        self.assertEqual(self.store.get_active()['project_id'], result['selected_project'])
        self.assertIn(result['selected_project'], [p['id'] for p in self.registry.list()])
        backup = json.loads(Path(result['backup']).read_text(encoding='utf-8'))
        self.assertEqual(backup['conversations'][a['id']]['messages'][0]['content'], 'Original')

    def test_removal_survives_restart_even_for_a_built_in_project(self):
        self.store.create('L', project_id='legacy')
        chats = [c['id'] for c in self.store.list() if c.get('project_id') == 'legacy']
        result = self.service.remove_project('legacy', chats, confirmed=True)
        # The replacement chat went to the selected project, which is then removed too.
        self.assertEqual(result['selected_project'], self.project['id'])
        chats = [c['id'] for c in self.store.list() if c.get('project_id') == self.project['id']]
        self.service.remove_project(self.project['id'], chats, confirmed=True)
        reloaded = ProjectRegistry(self.defaults, storage_path=self.registry_path)
        self.assertEqual([p['id'] for p in reloaded.list()], ['squad-pilot'])
        # Adding the folder again is the way back.
        self.assertEqual(reloaded.add(str(self.folder))['path'], str(self.folder.resolve()))

    def test_refuses_without_confirmation_stale_list_default_or_running_turn(self):
        a = self.store.create('A', project_id=self.project['id'])
        before = self.registry_path.read_bytes()
        with self.assertRaises(PermissionError):
            self.service.remove_project(self.project['id'], [a['id']], confirmed=False)
        with self.assertRaises(ValueError):  # the confirmed list no longer matches
            self.service.remove_project(self.project['id'], [], confirmed=True)
        with self.assertRaises(ValueError):
            self.service.remove_project('squad-pilot', [], confirmed=True)
        self.service._active_turn = {'status': 'running'}
        with self.assertRaises(RuntimeError):
            self.service.remove_project(self.project['id'], [a['id']], confirmed=True)
        self.assertEqual(self.registry_path.read_bytes(), before)
        self.assertEqual(self.store.get(a['id'])['title'], 'A')

    def test_ipc_and_gui_paths(self):
        server = main.IPCServer(MagicMock())
        server._agent_chat = self.service
        result = server._dispatch_action({'action': 'project_remove', 'data': {
            'project_id': self.project['id'], 'conversation_ids': [], 'confirmed': True}})
        self.assertEqual(result['data']['removed_project']['id'], self.project['id'])
        api = gui.Api()
        api._natural = SimpleNamespace(status=lambda: {'active': True})
        with patch.object(gui, 'ipc_send') as send:
            self.assertEqual(api.project_remove('p', [], True)['status'], 'error')
            send.assert_not_called()

    def test_registry_write_failure_restores_chats_and_memory(self):
        chat = self.store.create('Keep', project_id=self.project['id'])
        before = self.registry_path.read_bytes()
        with patch.object(self.registry, '_save', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.service.remove_project(self.project['id'], [chat['id']], confirmed=True)
        self.assertEqual(self.store.get(chat['id'])['title'], 'Keep')
        self.assertEqual(self.registry.get(self.project['id'])['id'], self.project['id'])
        self.assertEqual(self.registry_path.read_bytes(), before)
        from core.conversation_store import ConversationStore
        self.assertEqual(ConversationStore(self.store.path).get(chat['id'])['title'], 'Keep')

    def test_ui_offers_removal_with_confirmation_and_hides_it_for_the_default(self):
        self.assertIn('id="btnRemoveProject"', gui._HTML)
        self.assertIn("window.pywebview.api.project_remove(projectId, chats.map(c => c.id), true)", gui._HTML)
        self.assertIn("mainProjectSelect.value === 'squad-pilot'", gui._HTML)
        self.assertIn('Proje klasörü ve dosyaları silinmez', gui._HTML)


if __name__ == '__main__':
    unittest.main()
