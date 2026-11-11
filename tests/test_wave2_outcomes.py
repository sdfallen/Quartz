import unittest
from types import SimpleNamespace
from core.task_outcome import execution_outcome, group_execution_status
from core.multi_agent_service import MultiAgentService
from core.agent_chat import AgentChatService


class OutcomeContractTests(unittest.TestCase):
    def test_process_and_syntax_completion_never_verify_goal(self):
        for verification in (None,{'status':'VERIFIED'},{'status':'LIVE OBSERVED'}):
            outcome=execution_outcome('completed',verification)
            self.assertEqual(outcome['goal_verdict'],'NOT VERIFIED')
            self.assertFalse(outcome['goal_accepted'])

    def test_validation_failure_overrides_model_completion(self):
        result=MultiAgentService._with_file_evidence({'status':'completed'},
                    {'source_validation':{'status':'FAILED'}})
        self.assertEqual(result['outcome']['goal_verdict'],'FAILED')

    def test_partial_group_cannot_be_completed_or_verified(self):
        for states in ({'codex':'completed','antigravity':'failed'},
                       {'codex':'timed_out','antigravity':'completed'}):
            self.assertEqual(group_execution_status(states),'partial')
            self.assertEqual(execution_outcome('partial',participants=states)['goal_verdict'],'PARTIAL')
        self.assertEqual(group_execution_status({'c':'failed','a':'failed'}),'failed')
        self.assertEqual(group_execution_status({'c':'completed','a':'completed'}),'completed')

    def test_message_projection_contains_honest_goal_verdict(self):
        owner=AgentChatService.__new__(AgentChatService)
        owner.agent_service=SimpleNamespace(run_evidence=lambda _: {'source_validation':{'status':'FAILED'}})
        rows=[{'status':'completed','metadata':{'run_id':'owned'}}]
        owner._enrich_messages(rows)
        self.assertEqual(rows[0]['metadata']['outcome']['goal_verdict'],'FAILED')
