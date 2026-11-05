import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.task_oracle import TaskOracle, GoalEvaluation
from core.task_outcome import execution_outcome
from tests import test_multi_agent_service as fixtures


class TaskOracleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.oracle = TaskOracle()

    def test_no_oracle_or_model_dictionary_is_not_verified(self):
        self.assertIsNone(self.oracle.evaluate('task', 'run'))
        for proof in ({'verdict':'VERIFIED'}, GoalEvaluation('t','r','VERIFIED',())):
            self.assertEqual(execution_outcome('completed', goal_evaluation=proof)['goal_verdict'], 'NOT VERIFIED')

    def test_actual_file_not_a_claim_drives_result_and_stale_receipt_is_not_reused(self):
        self.oracle.register('t', 'r', self.root, [{'path':'answer.txt', 'text':'42'}])
        self.assertEqual(self.oracle.evaluate('t','r').verdict, 'FAILED')
        (self.root/'answer.txt').write_text('42')
        proof = self.oracle.evaluate('t','r')
        outcome = execution_outcome('completed', goal_evaluation=proof)
        self.assertEqual(outcome['goal_verdict'], 'VERIFIED'); self.assertFalse(outcome['goal_accepted'])
        (self.root/'answer.txt').write_text('wrong')
        self.assertEqual(self.oracle.evaluate('t','r').verdict, 'FAILED')

    def test_valid_noop_and_expected_negative_do_not_require_a_file_change(self):
        (self.root/'already.txt').write_text('correct')
        self.oracle.register('t','r',self.root,[{'path':'already.txt','text':'correct'}, {'path':'forbidden.txt','absent':True}])
        self.assertEqual(self.oracle.evaluate('t','r').verdict,'VERIFIED')

    def test_scope_escape_rebind_and_wrong_task_are_rejected(self):
        for relative in ('../outside.txt', str(self.root/'absolute.txt')):
            with self.assertRaises(ValueError): self.oracle.register('t','r',self.root,[{'path':relative,'text':'x'}])
        self.oracle.register('t','r',self.root,[{'path':'x','absent':True}])
        with self.assertRaises(ValueError): self.oracle.register('t','r',self.root,[{'path':'y','absent':True}])
        with self.assertRaises(PermissionError): self.oracle.evaluate('other','r')
        self.assertIsNone(self.oracle.evaluate('t','other-run'))

    def test_hash_and_empty_check_rejection(self):
        with self.assertRaises(ValueError): self.oracle.register('t','r',self.root,[])
        (self.root/'a').write_bytes(b'hello')
        self.oracle.register('t','r',self.root,[{'path':'a','sha256':hashlib.sha256(b'hello').hexdigest()}])
        self.assertEqual(self.oracle.evaluate('t','r').verdict,'VERIFIED')

    def test_failure_or_partial_cannot_be_upgraded_by_a_goal(self):
        self.oracle.register('t','r',self.root,[{'path':'a','absent':True}])
        proof=self.oracle.evaluate('t','r')
        for status in ('failed','cancelled','partial','running'):
            self.assertNotEqual(execution_outcome(status, goal_evaluation=proof)['goal_verdict'],'VERIFIED')
        self.assertEqual(execution_outcome('completed',source_validation={'status':'FAILED'},goal_evaluation=proof)['goal_verdict'],'FAILED')

    def test_service_consumers_use_host_binding_and_recheck_actual_files(self):
        service, runtime, _ = fixtures.MultiAgentServiceTests().make_service()
        service._links['r'] = {'task_id':'t','project_id':'test','provider':'codex'}
        runtime.get.return_value={'id':'r','status':'running','result':'VERIFIED'}
        with patch.object(service.projects,'resolve',return_value=self.root):
            service.register_goal_oracle('r',[{'path':'a','text':'done'}])
        runtime.get.return_value={'id':'r','status':'completed','result':'VERIFIED'}
        self.assertEqual(service.get_run('r')['outcome']['goal_verdict'],'FAILED')
        (self.root/'a').write_text('done')
        self.assertEqual(service.get_run('r')['outcome']['goal_verdict'],'VERIFIED')
        with self.assertRaises(PermissionError): service.register_goal_oracle('r',[{'path':'a','text':'wrong'}])
