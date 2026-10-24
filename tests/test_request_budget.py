import unittest
from types import SimpleNamespace
from core.request_budget import compact, smalltalk
from core.llm_provider import LLMGateway

def schema(name):
    return {'type':'function','function':{'name':name,'description':name,'parameters':{}}}

class BudgetTests(unittest.TestCase):
    def test_nvidia_uses_compaction_and_disables_thinking(self):
        calls=[]
        message=SimpleNamespace(content='ok',tool_calls=[])
        response=SimpleNamespace(choices=[SimpleNamespace(message=message)],usage=None)
        client=SimpleNamespace(base_url='https://integrate.api.nvidia.com/v1',
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: calls.append(kw) or response)))
        gateway=LLMGateway(client,'nvidia/nemotron-3.5-lightning-30b-a3b')
        gateway.complete([{'role':'system','content':'x'*20000},{'role':'user','content':'naber'}],tools=[schema('desktop_inspect')])
        self.assertNotIn('tools',calls[0])
        self.assertEqual(calls[0]['extra_body']['chat_template_kwargs']['enable_thinking'],False)
        self.assertLess(len(str(calls[0]['messages'])),500)

    def test_nvidia_gpt_oss_uses_low_reasoning(self):
        calls=[]
        message=SimpleNamespace(content='ok',tool_calls=[])
        response=SimpleNamespace(choices=[SimpleNamespace(message=message)],usage=None)
        client=SimpleNamespace(base_url='https://integrate.api.nvidia.com/v1',
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: calls.append(kw) or response)))
        gateway=LLMGateway(client,'openai/gpt-oss-20b')
        gateway.complete([{'role':'user','content':'test'}])
        self.assertEqual(calls[0]['reasoning_effort'],'low')

    def test_smalltalk_is_exact_not_action_prefix(self):
        self.assertTrue(smalltalk('naber dostum'))
        self.assertFalse(smalltalk('merhaba youtube aç'))

    def test_smalltalk_has_no_tools_or_old_operation(self):
        messages, tools = compact([{'role':'system','content':'x'*20000},
            {'role':'user','content':'eski görev'}, {'role':'assistant','content':'x'*10000},
            {'role':'user','content':'naber'}], [schema('steam_install_game')])
        self.assertEqual(tools, [])
        self.assertEqual(len(messages), 2)
        self.assertLess(len(str(messages)), 400)

    def test_active_app_context_and_tool_pairs_preserved(self):
        original = [{'role':'system','content':'ACTIVE OPERATION CONTEXT\nactive_app: Steam\nDESKTOP EXECUTION PROTOCOL: verify'},
            {'role':'user','content':'orada devam et'},
            {'role':'assistant','tool_calls':[{'id':'a','function':{'name':'desktop_inspect','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':'a','content':'x'*5000}]
        result, tools = compact(original,[schema('desktop_inspect'),schema('steam_install_game')])
        self.assertIn('active_app: Steam',result[0]['content'])
        self.assertEqual(result[-1]['tool_call_id'],'a')
        self.assertLess(len(result[-1]['content']),2400)
        self.assertEqual(len(original[-1]['content']),5000)

    def test_rate_limit_wait_uses_header_and_cancels(self):
        exc = RuntimeError('429')
        exc.response = SimpleNamespace(headers={'retry-after':'3'})
        def fail(**kwargs): raise exc
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
        gateway = LLMGateway(client,'test')
        delays=[]
        def wait(delay):
            delays.append(delay)
            gateway.cancel_event.set()
        gateway.on_wait=wait
        with self.assertRaisesRegex(RuntimeError,'iptal'):
            gateway.complete([{'role':'user','content':'test'}])
        self.assertEqual(delays,[3.25])
