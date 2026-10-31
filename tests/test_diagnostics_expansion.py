import hashlib
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

from core.package_repair import PackageRepair
from core.artifact_diagnostics import ArtifactDiagnosticsService
from core.diagnostics_intent import diagnostics_intent


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base, self.ref = self.root/'app', self.root/'reference'
        for folder in (self.base, self.ref):
            folder.mkdir()
            (folder/'Quartz.exe').write_bytes(b'identical-test-build')
            for name in PackageRepair.ALLOWED:
                file = folder/name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'good' if folder == self.ref else b'broken')
        files = {p.relative_to(self.ref).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.ref.rglob('*') if p.is_file()}
        (self.ref/'release-manifest.json').write_text(json.dumps({'files': files}))
        (self.base/'.env').write_text('private fixture')
        self.service = PackageRepair(self.base, self.root/'backups')

    def test_repair_verifies_backup_and_never_changes_private_files(self):
        plan = self.service.prepare(self.ref)
        self.assertEqual(self.service.apply(plan['id'])['state'], 'verified')
        for name in PackageRepair.ALLOWED:
            self.assertEqual((self.base/name).read_bytes(), b'good')
        self.assertEqual((self.base/'.env').read_text(), 'private fixture')
        self.assertEqual((self.root/'backups'/plan['id']/'0').read_bytes(), b'broken')
        with self.assertRaises(ValueError): self.service.apply(plan['id'])

    def test_partial_failure_rolls_back(self):
        plan = self.service.prepare(self.ref)
        replace = self.service._replace
        calls = []
        def fail_second(path, data):
            calls.append(path)
            if len(calls) == 2: raise OSError('fixture write failure')
            replace(path, data)
        with patch.object(self.service, '_replace', side_effect=fail_second):
            self.assertEqual(self.service.apply(plan['id'])['state'], 'rolled_back')
        for name in PackageRepair.ALLOWED:
            self.assertEqual((self.base/name).read_bytes(), b'broken')

    def test_changed_target_rejected_before_write(self):
        plan = self.service.prepare(self.ref)
        (self.base/PackageRepair.ALLOWED[0]).write_bytes(b'external edit')
        with self.assertRaises(ValueError): self.service.apply(plan['id'])
        self.assertFalse((self.root/'backups').exists())

    def test_wrong_build_and_modified_reference_rejected(self):
        (self.ref/'Quartz.exe').write_bytes(b'other build')
        with self.assertRaises(ValueError): self.service.prepare(self.ref)
        (self.ref/'Quartz.exe').write_bytes(b'identical-test-build')
        (self.ref/PackageRepair.ALLOWED[0]).write_bytes(b'modified reference')
        with self.assertRaises(ValueError): self.service.prepare(self.ref)

    def test_missing_resource_is_repaired(self):
        (self.base/PackageRepair.ALLOWED[0]).unlink()
        plan = self.service.prepare(self.ref)
        self.assertEqual(self.service.apply(plan['id'])['state'], 'verified')

    def test_expired_plan_and_wrong_token_do_not_write(self):
        plan = self.service.prepare(self.ref)
        self.service.plan['expires'] = 0
        with self.assertRaises(ValueError): self.service.apply(plan['id'])
        self.service.prepare(self.ref)
        with self.assertRaises(ValueError): self.service.apply('wrong')
        self.assertEqual((self.base/PackageRepair.ALLOWED[0]).read_bytes(), b'broken')


class ArtifactTests(unittest.TestCase):
    def test_selected_exe_read_only_and_unknown_is_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root/'test.exe'
            data = bytearray(128)
            data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 64)
            data[64:68] = b'PE\0\0'; struct.pack_into('<HH', data, 68, 0x8664, 3)
            target.write_bytes(data)
            rea = Mock(); rea.inspect.return_value = {'status': 'UNKNOWN', 'message': 'Unsupported format', 'used': True}
            service = ArtifactDiagnosticsService(target, reports=root/'reports', rea=rea)
            self.addCleanup(service.shutdown)
            job = service.start()
            service.threads[job['id']].join(5)
            result = service.status()
            self.assertEqual(result['state'], 'completed')
            self.assertEqual(result['verdict'], 'PARTIAL')
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(result['checks'][1]['evidence']['sections'], 3)

    def test_changed_identity_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'test.exe'; target.write_bytes(b'one')
            service = ArtifactDiagnosticsService(target, reports=Path(folder)/'reports')
            target.write_bytes(b'different')
            job = service.start(False); service.threads[job['id']].join(5)
            self.assertEqual(service.status()['state'], 'failed')

    def test_protected_project_and_wrong_extension_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'WarbandIsland'/'game.exe'
            target.parent.mkdir(); target.write_bytes(b'not executed')
            with self.assertRaises(ValueError): ArtifactDiagnosticsService(target)
            target = Path(folder)/'secret.txt'; target.write_bytes(b'not read')
            with self.assertRaises(ValueError): ArtifactDiagnosticsService(target)


class RoutingTests(unittest.TestCase):
    def test_commands_and_discussion_are_separate(self):
        for value, expected in [("Quartz'ı kontrol et", 'self'), ('Quartz’ı onar', 'repair'),
                                ('Başka bir uygulamayı incele', 'artifact')]:
            self.assertEqual(diagnostics_intent(value), expected)
        for value in ['"Quartz onar" ne demek?', 'Araç kullanma, Quartz onar',
                      'Quartz onarabilir mi?', 'Quartz ayarlarını değiştir', 'Quartz onar?']:
            self.assertIsNone(diagnostics_intent(value))

    def test_main_chat_alias_uses_diagnostics_not_agents(self):
        import gui
        api = gui.Api()
        with patch.object(api, 'diagnostics_start', return_value={'status':'ok','data':{'id':'x'}}) as start:
            result = api.coordination_route("Quartz'ı kontrol et", 'c', 'p', {})
        self.assertTrue(result['data']['diagnostics_started'])
        start.assert_called_once()

    def test_picker_cancel_does_not_start_inspection_or_repair(self):
        import gui
        api = gui.Api()
        window = Mock(); window.create_file_dialog.return_value = None
        with patch.object(gui.webview, 'windows', [window]):
            self.assertIsNone(api.diagnostics_select_application()['data'])
            self.assertIsNone(api.diagnostics_prepare_repair()['data'])
        self.assertIsNone(api._artifact_diagnostics)
        self.assertIsNone(api._repair)


if __name__ == '__main__':
    unittest.main()
