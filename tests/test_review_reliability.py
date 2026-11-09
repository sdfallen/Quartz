import tempfile
import unittest
from scripts.exam_oracle import Context, evaluate
from tests.test_natural_desktop import NaturalTaskTests
from core.natural_desktop import requested_literals


class OracleReliabilityTests(unittest.TestCase):
    def test_cancelled_message_does_not_override_missing_or_negative_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            for value in (None, False):
                c = Context(root, marks={'stop_receipt_confirmed': value},
                            messages=[{'role': 'assistant', 'metadata': {'status': 'cancelled'}}])
                self.assertFalse(evaluate({'check': 'stop_receipt_confirmed'}, c)['passed'])

    def test_structured_command_result_prevents_no_tools_pass(self):
        with tempfile.TemporaryDirectory() as root:
            c = Context(root, messages=[{'metadata': {'command_results': [{'exit_code': 0}]}}])
            self.assertFalse(evaluate({'check': 'no_tool_calls_recorded'}, c)['passed'])

    def test_text_subgoal_does_not_direct_operator_to_abandon_remaining_steps(self):
        fixture = NaturalTaskTests()
        fixture.setUp()
        try:
            fixture.task.job['requested_text'] = requested_literals("'deneme' yaz, sonra pencereyi küçült")
            fixture.approve()
            fixture.notepad('')
            before = fixture.call('desktop_focus')
            fixture.notepad('deneme')
            result = fixture.call('desktop_act', {'snapshot_id': before['snapshot_id'],
                                                  'action': 'text', 'text': 'deneme'})
            instruction = result['host_verification']['next']
            self.assertNotIn('Do not call more tools', instruction)
            self.assertIn('Continue any remaining user requirements', instruction)
        finally:
            fixture.tearDown()
