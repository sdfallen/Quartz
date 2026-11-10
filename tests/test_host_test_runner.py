import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from core.host_test_runner import HostUnittestAdapter
from core.agent_chat import AgentChatService


PASS = 'import unittest\nclass TestValue(unittest.TestCase):\n def test_value(self): self.assertEqual(2,2)\n'


class HostRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'test_value.py').write_text(PASS, encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def adapter(self, **kwargs):
        return HostUnittestAdapter(self.root, ['test_value.py'], expected_tests=1, **kwargs)

    def test_manifest_is_sorted_tuple_and_stable_before_execution(self):
        (self.root/'test_alpha.py').write_text(PASS, encoding='utf-8')
        runner = HostUnittestAdapter(self.root, ['test_value.py','test_alpha.py'], expected_tests=2)
        self.assertIsInstance(runner.baseline_manifest, tuple)
        self.assertEqual([p for p,_ in runner.baseline_manifest], ['test_alpha.py','test_value.py'])
        runner.validate_baseline()
        (self.root/'test_value.py').write_text(PASS.replace('2,2','True,True'), encoding='utf-8')
        with self.assertRaises(RuntimeError): runner.validate_baseline()

    def test_invalid_and_duplicate_test_paths_are_rejected(self):
        for files in (['../test.py'], ['test_value.py','test_value.py'], ['test-unsafe.py'], ['C:/test.py']):
            with self.subTest(files=files), self.assertRaises(ValueError):
                HostUnittestAdapter(self.root, files, expected_tests=1)

    def test_changed_tests_are_rejected_before_any_process(self):
        runner = self.adapter()
        (self.root/'test_value.py').write_text(PASS.replace('2,2','True,True'), encoding='utf-8')
        with patch('core.host_test_runner.subprocess.Popen') as launch:
            with self.assertRaises(RuntimeError): runner(threading.Event())
        launch.assert_not_called()

    def test_chat_captures_before_dispatch_and_rejects_changed_tests(self):
        service = MagicMock()
        service.projects.get.return_value = {'path': str(self.root)}
        chat = AgentChatService(service, self.root/'chat.json')
        conv = chat.store.create('fixture', agent='codex', project_id='p')
        try:
            runner = chat.register_host_unittest_plan(conv['id'], project_id='p', provider='codex',
                                                       test_files=['test_value.py'], expected_tests=1)
            self.assertEqual(runner.baseline_manifest[0][0], 'test_value.py')
            service.dispatch_codex.assert_not_called()
            (self.root/'test_value.py').write_text(PASS+'# changed\n', encoding='utf-8')
            with self.assertRaises(RuntimeError):
                chat.send_message('Dosyayı düzelt', 'codex', conv['id'], write=True, confirm_write=True)
            service.dispatch_codex.assert_not_called()
        finally:
            chat._diagnostics.close()
            chat._environment_health.close()

    def test_unconfirmed_host_cleanup_blocks_admission_and_stop_confirmation(self):
        service = MagicMock()
        chat = AgentChatService(service, self.root/'chat.json')
        try:
            chat._host_test_adapters['old'] = SimpleNamespace(cleanup_pending=True)
            chat._active_turn = {'status': 'cancelled', 'run_ids': [], 'stop_receipt': {}, 'worker_pending': False}
            chat._refresh_stop_receipt()
            self.assertEqual(chat._active_turn['stop_receipt']['status'], 'pending')
            with self.assertRaises(RuntimeError): chat.send_message('Dosyayı düzelt', write=True, confirm_write=True)
            service.dispatch_codex.assert_not_called()
        finally:
            chat._diagnostics.close()
            chat._environment_health.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object runner')
    def test_real_unittest_pass_and_fail_receipts(self):
        result = self.adapter()(threading.Event())
        self.assertEqual((result.exit_code,result.tests_run), (0,1))
        self.assertIsInstance(result.test_manifest, tuple)
        (self.root/'test_value.py').write_text(PASS.replace('2,2','2,3'), encoding='utf-8')
        runner = self.adapter()
        result = runner(threading.Event())
        self.assertEqual((result.exit_code,result.tests_run), (1,1))
        self.assertFalse(runner.cleanup_pending)

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object runner')
    def test_stdout_claim_cannot_replace_real_failure(self):
        (self.root/'test_value.py').write_text("print('Ran 99 tests in 0s\\nOK')\n"+PASS.replace('2,2','2,3'), encoding='utf-8')
        result = self.adapter()(threading.Event())
        self.assertEqual((result.exit_code,result.tests_run), (1,1))

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object runner')
    def test_normal_exit_cleans_up_lingering_child(self):
        import psutil
        code = "import subprocess,sys\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\nPath('child.pid').write_text(str(p.pid))\n"
        (self.root/'test_value.py').write_text(code+PASS, encoding='utf-8')
        runner = self.adapter()
        result = runner(threading.Event())
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(runner.cleanup_pending)
        self.assertFalse(psutil.pid_exists(int((self.root/'child.pid').read_text())))

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object runner')
    def test_skip_and_timeout_are_not_passes(self):
        (self.root/'test_value.py').write_text(PASS.replace(' def test_value', ' @unittest.skip("fixture")\n def test_value'), encoding='utf-8')
        with self.assertRaises(RuntimeError): self.adapter()(threading.Event())
        (self.root/'test_value.py').write_text('import time\ntime.sleep(20)\n'+PASS, encoding='utf-8')
        runner = self.adapter(timeout=.2)
        with self.assertRaisesRegex(RuntimeError,'timeout'): runner(threading.Event())
        self.assertFalse(runner.cleanup_pending)

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object runner')
    def test_stop_terminates_owned_test_and_spawned_child(self):
        import psutil
        code = "import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\nPath('child.pid').write_text(str(p.pid))\ntime.sleep(30)\n"
        (self.root/'test_value.py').write_text(code+PASS, encoding='utf-8')
        runner, stop, errors = self.adapter(), threading.Event(), []
        def work():
            try: runner(stop)
            except RuntimeError as exc: errors.append(str(exc))
        thread = threading.Thread(target=work)
        thread.start()
        child = None
        try:
            deadline = time.monotonic()+5
            while not (self.root/'child.pid').exists() and time.monotonic()<deadline: time.sleep(.03)
            self.assertTrue((self.root/'child.pid').exists())
            child = psutil.Process(int((self.root/'child.pid').read_text()))
        finally:
            stop.set()
            thread.join(8)
        self.assertFalse(thread.is_alive())
        self.assertTrue(errors)
        self.assertFalse(runner.cleanup_pending)
        self.assertTrue(child is not None and not child.is_running())

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object runner')
    def test_invoice_fixture_real_baseline_has_eight_failing_tests(self):
        fixture = Path(__file__).resolve().parents[1]/'docs/task_exam/fixtures/invoice'
        for p in fixture.iterdir():
            if p.is_file(): shutil.copy2(p,self.root/p.name)
        runner = HostUnittestAdapter(self.root,['test_invoice.py'],expected_tests=8)
        result = runner(threading.Event())
        self.assertEqual((result.exit_code,result.tests_run),(1,8))
