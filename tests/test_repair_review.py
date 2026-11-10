import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from core.repair_review import review_writer_changes


class RepairReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'project'
        self.root.mkdir()
        self.archive = Path(self.temp.name)/'before.zip'
        self.path = self.root/'invoice.py'

    def run_review(self, before, after, **overrides):
        self.path.write_text(after, encoding='utf-8')
        data = before.encode('utf-8')
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('files/invoice.py',data)
            z.writestr('checkpoint-manifest.json',json.dumps({'workspace':str(self.root),
                'files':{'invoice.py':{'exists':True,'sha256':hashlib.sha256(data).hexdigest()}}}))
        run = {'checkpoint':{'complete':True,'archive':str(self.archive)}, 'files_changed':[str(self.path)]}
        run.update(overrides)
        return review_writer_changes(self.root,run)

    def test_changed_lines_emit_labels_without_source(self):
        for text in ('__main__','gc.get_objects','sys._getframe','inspect','os._exit','unittest.mock','quartz-host-unittest'):
            with self.subTest(text=text):
                result=self.run_review('total=1\n','secret_value=12345\n'+text+'\n')
                self.assertEqual(result['status'],'suspicious')
                self.assertTrue(result['independent_review_required'])
                self.assertNotIn('12345',json.dumps(result))

    def test_unchanged_marker_is_not_flagged(self):
        result=self.run_review('import inspect\ntotal=1\n','import inspect\ntotal=2\n')
        self.assertEqual(result['status'],'clear')
        self.assertTrue(result['independent_review_required'])

    def test_missing_or_incomplete_evidence_stays_unknown(self):
        self.assertEqual(review_writer_changes(self.root,{})['status'],'unknown')
        self.assertEqual(self.run_review('','',evidence_warning='truncated')['status'],'unknown')

    def test_escape_is_not_read(self):
        result=self.run_review('','',files_changed=[str(self.root/'../outside.py')])
        self.assertEqual(result['status'],'unknown')

    def test_checkpoint_hash_mismatch_is_unknown(self):
        self.run_review('before','after')
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('files/invoice.py','tampered')
            z.writestr('checkpoint-manifest.json',json.dumps({'workspace':str(self.root),
                'files':{'invoice.py':{'exists':True,'sha256':'0'*64}}}))
        result=review_writer_changes(self.root,{'checkpoint':{'complete':True,'archive':str(self.archive)},'files_changed':[str(self.path)]})
        self.assertEqual(result['status'],'unknown')
