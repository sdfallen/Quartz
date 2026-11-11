import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from core.repair_review import review_writer_changes


class RepairReviewDynamicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.archive = Path(self.temp.name) / 'before.zip'
        self.path = self.root / 'invoice.py'

    def run_review(self, before, after, **overrides):
        self.path.write_text(after, encoding='utf-8')
        data = before.encode('utf-8')
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('files/invoice.py', data)
            z.writestr('checkpoint-manifest.json', json.dumps({
                'workspace': str(self.root),
                'files': {'invoice.py': {'exists': True, 'sha256': hashlib.sha256(data).hexdigest()}}
            }))
        run = {'checkpoint': {'complete': True, 'archive': str(self.archive)}, 'files_changed': [str(self.path)]}
        run.update(overrides)
        return review_writer_changes(self.root, run)

    def test_getattr_sys_with_string_concatenation(self):
        code = "fn = getattr(sys, '_get' + 'frame')\nsecret_1 = 'supersecret_987'\n"
        result = self.run_review('total = 1\n', code)
        self.assertEqual(result['status'], 'suspicious')
        self.assertTrue(result['independent_review_required'])
        signals = [s['signal'] for s in result['signals']]
        self.assertIn('getattr', signals)
        self.assertNotIn('supersecret_987', json.dumps(result))

    def test_getattr_os_and_builtins(self):
        cases = (
            "getattr(os, '_ex' + 'it')(0)\n",
            "getattr(builtins, 'ev' + 'al')('1+1')\n",
            "getattr(__builtins__, 'exec')('pass')\n",
            "builtins.getattr(sys, 'modules')\n",
            "__builtins__.getattr(os, 'system')('cmd')\n",
        )
        for snippet in cases:
            with self.subTest(snippet=snippet):
                result = self.run_review('x = 10\n', snippet)
                self.assertEqual(result['status'], 'suspicious')
                signals = [s['signal'] for s in result['signals']]
                self.assertIn('getattr', signals)

    def test_import_and_importlib_signals(self):
        cases = (
            ("__import__('os')", '__import__'),
            ("mod = __import__('sys')", '__import__'),
            ("import importlib", 'importlib'),
            ("from importlib import import_module", 'importlib'),
            ("importlib.import_module('inspect')", 'importlib'),
        )
        for snippet, expected_signal in cases:
            with self.subTest(snippet=snippet):
                result = self.run_review('total = 0\n', snippet + '\n')
                self.assertEqual(result['status'], 'suspicious')
                signals = [s['signal'] for s in result['signals']]
                self.assertIn(expected_signal, signals)

    def test_benign_getattr_is_clear(self):
        benign_cases = (
            "val = getattr(self, 'amount', 0)\n",
            "name = getattr(item, 'title')\n",
            "status = getattr(response, 'status_code')\n",
            "x = getattr(custom_module, 'helper')\n",
        )
        for snippet in benign_cases:
            with self.subTest(snippet=snippet):
                result = self.run_review('total = 1\n', snippet)
                self.assertEqual(result['status'], 'clear')
                self.assertEqual(result['signals'], [])
                self.assertTrue(result['independent_review_required'])

    def test_unchanged_dynamic_access_is_not_flagged(self):
        before = "import importlib\nfn = getattr(sys, '_get' + 'frame')\ntotal = 1\n"
        after = "import importlib\nfn = getattr(sys, '_get' + 'frame')\ntotal = 2\n"
        result = self.run_review(before, after)
        self.assertEqual(result['status'], 'clear')
        self.assertEqual(result['signals'], [])

    def test_multiline_getattr_detected(self):
        after = "val = getattr(\n    sys,\n    '_get' + 'frame'\n)\n"
        result = self.run_review('total = 1\n', after)
        self.assertEqual(result['status'], 'suspicious')
        signals = [s['signal'] for s in result['signals']]
        self.assertIn('getattr', signals)


if __name__ == '__main__':
    unittest.main()
