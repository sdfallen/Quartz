import tempfile
import unittest
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from core.workspace_checkpoint import create_checkpoint, snapshot_workspace_files, changed_workspace_files


class WorkspaceFileEvidenceTests(unittest.TestCase):
    def test_detects_created_modified_and_deleted_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            modified = root / "modified.txt"
            deleted = root / "deleted.txt"
            modified.write_text("before", encoding="utf-8")
            deleted.write_text("before", encoding="utf-8")
            before = snapshot_workspace_files(root)
            modified.write_text("after-content", encoding="utf-8")
            deleted.unlink()
            created = root / "created.txt"
            created.write_text("new", encoding="utf-8")
            after = snapshot_workspace_files(root)
            changed, warning = changed_workspace_files(root, before, after)
            self.assertEqual(set(changed),
                             {str(modified.resolve()), str(deleted.resolve()), str(created.resolve())})
            self.assertEqual(warning, "")

    def test_file_limit_reports_incomplete_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "first.txt").touch()
            (root / "second.txt").touch()
            snapshot = snapshot_workspace_files(root, max_files=1)
            self.assertIsNone(snapshot["files"])
            self.assertIn("sınırı", snapshot["warning"])


class DurableCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'project';self.root.mkdir()
        self.backups=Path(self.tmp.name)/'backups'

    def tearDown(self):
        self.tmp.cleanup()

    def git(self,*args):
        return subprocess.run(['git','-C',str(self.root),*args],capture_output=True,text=True,check=True)

    def test_non_git_archive_is_complete_and_readable(self):
        (self.root/'new.py').write_text('before',encoding='utf-8')
        checkpoint=create_checkpoint(self.root,backup_root=self.backups)
        self.assertEqual(checkpoint['status'],'snapshot',checkpoint)
        self.assertTrue(checkpoint['complete'])
        (self.root/'new.py').write_text('changed',encoding='utf-8')
        with zipfile.ZipFile(checkpoint['archive']) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read('files/new.py'),b'before')
            manifest=json.loads(archive.read('checkpoint-manifest.json'))
            self.assertEqual(manifest['files']['new.py']['sha256'],hashlib.sha256(b'before').hexdigest())
            (self.root/'new.py').write_bytes(archive.read('files/new.py'))
        self.assertEqual((self.root/'new.py').read_bytes(),b'before')

    def test_git_archive_preserves_dirty_untracked_and_deleted_files_without_reset(self):
        self.git('init')
        (self.root/'.gitignore').write_text('.env\n',encoding='utf-8')
        (self.root/'tracked.py').write_text('committed',encoding='utf-8')
        deleted=self.root/'deleted.py';deleted.write_text('deleted',encoding='utf-8')
        self.git('add','.')
        self.git('-c','user.name=Quartz Test','-c','user.email=test@example.invalid','commit','-m','test fixture')
        (self.root/'tracked.py').write_text('dirty',encoding='utf-8')
        (self.root/'untracked.py').write_text('not committed',encoding='utf-8')
        (self.root/'.env').write_text('SYNTHETIC_TEST_ONLY=1',encoding='utf-8')
        deleted.unlink()
        status_before=self.git('status','--porcelain').stdout
        checkpoint=create_checkpoint(self.root,backup_root=self.backups)
        self.assertEqual(checkpoint['status'],'git',checkpoint)
        self.assertTrue(checkpoint['complete'])
        self.assertEqual(self.git('status','--porcelain').stdout,status_before)
        self.git('show-ref','--verify',checkpoint['ref'])
        with zipfile.ZipFile(checkpoint['archive']) as archive:
            self.assertEqual(archive.read('files/tracked.py'),b'dirty')
            self.assertEqual(archive.read('files/untracked.py'),b'not committed')
            self.assertNotIn('files/.env',archive.namelist())
            manifest=json.loads(archive.read('checkpoint-manifest.json'))
            self.assertFalse(manifest['files']['deleted.py']['exists'])

    def test_non_git_does_not_copy_credentials_or_runtime_data(self):
        for name in ('.env','.env.local','assistant.log','mobile_access.json','quartz_conversations.json'):
            (self.root/name).write_text('SYNTHETIC_TEST_ONLY',encoding='utf-8')
        (self.root/'main.py').write_text('pass',encoding='utf-8')
        checkpoint=create_checkpoint(self.root,backup_root=self.backups)
        with zipfile.ZipFile(checkpoint['archive']) as archive:
            self.assertEqual(set(archive.namelist()),{'files/main.py','checkpoint-manifest.json'})

    def test_limits_and_inside_project_destination_fail_closed(self):
        (self.root/'file').write_bytes(b'1234')
        for kwargs in ({'max_bytes':1},{'max_files':0},{'backup_root':self.root/'nested'}):
            with self.subTest(kwargs=kwargs):
                options={'backup_root':self.backups,**kwargs}
                result=create_checkpoint(self.root,**options)
                self.assertEqual(result['status'],'error')
                self.assertFalse(result.get('complete',False))
                self.assertNotIn('archive',result)

    def test_missing_project_fails_closed(self):
        result=create_checkpoint(self.root/'absent',backup_root=self.backups)
        self.assertEqual(result['status'],'error')
        self.assertNotIn('archive',result)


if __name__ == "__main__":
    unittest.main()
