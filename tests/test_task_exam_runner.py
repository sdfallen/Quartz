import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from scripts.task_exam_runner import command_for, private_output, verdict, run_task, ROOT


class TaskExamTests(unittest.TestCase):
    def test_output_in_repo_or_existing_directory_is_rejected(self):
        with self.assertRaises(ValueError): private_output(ROOT/'labs/new-evidence')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): private_output(directory)

    def test_unreviewed_script_cannot_execute(self):
        with self.assertRaises(ValueError): command_for({'kind':'script','script':'unknown.py'}, {}, ())

    def test_account_gate_precedes_execution_adapter(self):
        catalog={'live':{'requires':['account'],'adapter':None}}
        with self.assertRaisesRegex(PermissionError,'permission'):
            command_for({'kind':'script','script':'live'},catalog,())
        with self.assertRaisesRegex(PermissionError,'adapter'):
            command_for({'kind':'script','script':'live'},catalog,('account',))

    def test_command_and_path_injection_rejected(self):
        for name in ('scripts.text_chat_acceptance','tests.test_x;echo x','../../x'):
            with self.assertRaises(ValueError): command_for({'kind':'regression','modules':[name]}, {}, ())

    def test_zero_exit_is_not_task_verification(self):
        self.assertEqual(verdict('unknown','model says completed',0)[0],'NOT VERIFIED')
        self.assertEqual(verdict('unittest','',0)[0],'NOT VERIFIED')
        self.assertEqual(verdict('unittest','Ran 4 tests in 1s\n\nOK',1)[0],'FAILED')

    def test_test_counts_and_skips_are_measured(self):
        self.assertEqual(verdict('unittest','',0,'Ran 14 tests in 2s\n\nOK (skipped=2)'),
                         ('VERIFIED',{'tests':14,'skipped':2}))

    def test_benchmark_false_or_missing_cleanup_is_not_success(self):
        for raw in ('{}','bad json',json.dumps({'stop_cancellation':{'stop_verified':False}})):
            self.assertNotEqual(verdict('process-benchmark',raw,0)[0],'VERIFIED')

    def test_gated_task_never_spawns(self):
        with tempfile.TemporaryDirectory() as directory:
            result=run_task({'id':'gated','kind':'script','script':'live'},Path(directory)/'evidence',
                            {'live':{'requires':['desktop'],'adapter':None}},execute=True)
            self.assertEqual(result['status'],'BLOCKED')
            self.assertEqual(result['runner_processes'],0)
            self.assertIsNone(result['step_count'])
            self.assertFalse((Path(directory)/'evidence').exists())

    def test_dry_run_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'evidence'
            row=run_task({'id':'dry','kind':'regression','modules':['tests.test_desktop_broker']},path,{})
            self.assertEqual(row['status'],'NOT TESTED')
            self.assertFalse(path.exists())

    def test_interrupt_cleans_owned_process_and_marks_stop(self):
        process=Mock(); process.wait.side_effect=KeyboardInterrupt()
        owner=Mock(); owner.launch.return_value=process; owner.cleanup.return_value=False; owner.interrupted=False
        with tempfile.TemporaryDirectory() as directory, \
             patch('scripts.task_exam_runner.command_for',return_value=(['fixture'],'unittest')), \
             patch('scripts.task_exam_runner.ExamProcess',return_value=owner):
            row=run_task({'id':'cancel'},Path(directory)/'evidence',{},execute=True)
            owner.cleanup.assert_called_once_with(force=True)
            self.assertEqual(row['status'],'BLOCKED')
            self.assertTrue(row['interrupted'])
            self.assertFalse(row['cleanup_confirmed'])

    def test_empty_all_skipped_and_stdout_spoof_are_not_verified(self):
        for text in ('Ran 0 tests in 0.000s\n\nOK','Ran 2 tests in 1s\n\nOK (skipped=2)'):
            self.assertEqual(verdict('unittest','',0,text)[0],'NOT VERIFIED')
        self.assertEqual(verdict('unittest','Ran 3 tests in 1s\n\nOK',0)[0],'NOT VERIFIED')

    def test_unknown_fields_and_changed_script_are_rejected(self):
        with self.assertRaises(ValueError):
            command_for({'id':'x','kind':'regression','modules':['tests.test_task_exam_runner'],'command':'anything'},{},())
        with self.assertRaisesRegex(PermissionError,'changed'):
            command_for({'kind':'script','script':'x'},
                        {'x':{'requires':[],'adapter':'process-benchmark','path':'scripts/task_exam_runner.py','sha256':'stale'}},())


if __name__=='__main__':unittest.main()
