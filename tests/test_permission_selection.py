from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import gui
from core.agent_chat import AgentChatService
from core.message_intent import message_intent


class PermissionRoutingTests(unittest.TestCase):
    def test_reported_turkish_followups_are_actionable(self):
        for text in ('Yetkilerinizi kontrol edin bakalım çocuklar',
                     'Pekala onay isteme yetkiniz var başlayın ben onay vereceğim',
                     'Kontrol ediniz', 'Test edin', 'Başlayın', 'Başla'):
            with self.subTest(text=text): self.assertEqual(message_intent(text),'task')
        for text in ('Başlamak mantıklı mı?', '"başlayın" ne anlama geliyor?', 'Kontrol etmekten bahsediyorum'):
            with self.subTest(text=text): self.assertEqual(message_intent(text),'conversation')

    def test_permission_query_reports_selection_without_starting_any_agent(self):
        api=gui.Api()
        with patch('gui.ipc_send',return_value={'status':'ok'}) as ipc, patch.object(api,'natural_start') as start:
            result=api.coordination_route('Yetkilerinizi kontrol edin bakalım çocuklar','c','p',{},'full')
        self.assertIn('Tam Yetki',result['data']['permission_status'])
        self.assertIn('çalışan görevin yetkisini değiştirmez',result['data']['permission_status'])
        start.assert_not_called(); self.assertIsNone(api._desktop_agents)
        self.assertEqual(ipc.call_count,2)

    def test_warband_followup_forwards_preference_without_any_um_action(self):
        api=gui.Api()
        state={'status':'ok','data':{'projects':[{'id':'p','workflow':'warband'}]}}
        with patch('gui.ipc_send',return_value=state), patch.object(api,'natural_start',return_value={'status':'ok'}) as start:
            api.coordination_route('Pekala başlayın ben onay vereceğim','c','p',{},'project')
        self.assertEqual(start.call_args.args[-1],'project')

    def test_plain_source_task_uses_file_runtime_not_desktop_handoff(self):
        api=gui.Api()
        with patch('gui.ipc_send',return_value={'status':'ok','data':{'projects':[{'id':'p'}]}}), patch.object(api,'natural_start') as start:
            result=api.coordination_route('Kodu düzelt','c','p',{},'full')
        self.assertFalse(result['data']['handled']); self.assertEqual(result['data']['intent'],'task')
        start.assert_not_called()

    def test_plain_chat_keeps_tools_off_even_when_full_preference_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            chat=AgentChatService(Mock(),Path(folder)/'chat.json')
            with patch('core.agent_chat.threading.Thread') as worker:
                result=chat.send_message('Merhaba',agent='codex',write=True,full_access=True,
                    confirm_write=True,requested_permission_level='full')
            self.assertEqual(worker.call_args.kwargs['args'][-3:],(False,False,False))
            self.assertEqual(chat._active_turn['requested_permission_level'],'full')
            self.assertEqual(chat._active_turn['permission_level'],'read-only')
            self.assertEqual(result['assistant_message']['metadata']['requested_permission_level'],'full')
            chat._active_turn=None; chat.close()

    def test_natural_start_preserves_conversation_context_and_mode_without_grant(self):
        api=gui.Api()
        state={'status':'ok','data':{'active_turn':None,'active_conversation':{'id':'c',
               'messages':[{'sender':'user','content':'Review the existing bug'},{'sender':'codex','content':'Old context'}]},
               'projects':[{'id':'p','path':'.'}]}}
        with patch('gui.ipc_send',side_effect=lambda action,*_:state if action=='chat_status' else {'status':'ok'}), \
             patch.object(api,'_desktop_service'), patch('core.natural_desktop.NaturalDesktopTask') as task:
            api.natural_start('Başlayın','c','p',{},'full')
        kwargs=task.return_value.start.call_args.kwargs
        self.assertEqual(kwargs['requested_permission_level'],'full')
        self.assertIn('Review the existing bug',kwargs['conversation_context'])

    def test_mcp_mode_preference_never_elevates_cli_filesystem(self):
        from tests.test_natural_desktop import NaturalTaskTests
        fixture=NaturalTaskTests('test_metadata_and_model_request_never_grant_input')
        fixture.setUp(); self.addCleanup(fixture.tearDown)
        task=fixture.task; runtime=Mock(); runtime.start.return_value={'id':'fixture-run'}
        runtime.get.return_value={'status':'completed'}
        task.factories={'codex':lambda:runtime}; task.server=Mock(server_port=1234)
        task.job.update(models={'codex':{'model':'fake','effort':'low'}},requested_permission_level='full',conversation_context='Previous requested goal')
        task.job['roles']['assignments']={'codex':'inspect','antigravity':'review'}
        task._launch_provider('codex')
        self.assertEqual(runtime.start.call_args.kwargs['sandbox'],'read-only')
        self.assertIn('Previous requested goal',runtime.start.call_args.args[0])
        self.assertIn('scoped MCP tools',runtime.start.call_args.args[0])
        self.assertFalse(fixture.broker.status()['active'])


class PermissionJavaScriptTests(unittest.TestCase):
    def node(self, source):
        result=subprocess.run(['node','-e',source],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_selection_feedback_is_synchronous_and_does_not_grant_or_dispatch(self):
        source=gui._HTML.split('  function updatePermissionSelectionHint()',1)[1].split('  let coordinationRouting',1)[0]
        # Use the actual binding code, including the native change handler.
        self.node(r'''
const assert=require('assert');let changed;
const select={value:'read-only',addEventListener:(kind,fn)=>{assert.equal(kind,'change');changed=fn}};
const hint={textContent:''};global.window={__writeConfirmed:true};
global.document={getElementById:id=>id==='mainPermissionLevel'?select:hint};
'''+'function updatePermissionSelectionHint()'+source+r'''
select.value='full';window.__writeConfirmed=true;changed();
assert(hint.textContent.includes('Tam Yetki'));assert.equal(window.__writeConfirmed,false);
select.value='project';changed();assert(hint.textContent.includes('Proje Yetkisi'));
''')

    def test_send_uses_selection_at_submit_not_a_later_dropdown_value(self):
        # Complete function extraction is bounded by the actual following binding.
        import re
        matched=re.search(r'async function sendAgentMessage\(\)[\s\S]*?\n  }\n',gui._HTML)
        self.assertIsNotNone(matched)
        self.node(r'''
const assert=require('assert');const selected={value:'full'};let sent,confirmCalls=0,expectedLevel='full',routeIntent='task';
global.coordinationRouting=false;global.inputEl={value:'Kodu düzelt'};
global.currentConvId='c';global.mainProjectSelect={value:'p'};
global.codexModelSelect=global.agyModelSelect={value:'model'};
global.codexEffortSelect=global.agyEffortSelect={value:'low'};
global.mainAgentSelect={value:'codex'};global.thinking=false;global.inpHistory=[];global.histCursor=0;global.msgCount=0;
global.document={getElementById:id=>id==='mainPermissionLevel'?selected:{textContent:''}};
global.chatEl={querySelectorAll:()=>[]};global.appendMsg=()=>({dataset:{},querySelector:()=>({textContent:''})});
global.setThinking=()=>{};global.logLine=()=>{};global.setOrb=()=>{};global.setTimeout=()=>{};
global.window={__writeConfirmed:false,confirm:()=>{confirmCalls++;return true},pywebview:{api:{
 coordination_route:async(...args)=>{assert.equal(args[4],expectedLevel);selected.value='read-only';return {status:'ok',data:{handled:false,intent:routeIntent}}},
 chat_send:async(...args)=>{sent=args;return {status:'error',data:'fixture stop after dispatch capture'}}}}};
'''+matched.group(0)+r'''
(async()=>{await sendAgentMessage();assert.equal(sent[5],'full');assert.equal(sent[6],'full');assert.equal(sent[3],true);assert.equal(confirmCalls,1);
expectedLevel='project';selected.value='project';inputEl.value='Kodu düzelt';window.__writeConfirmed=false;
await sendAgentMessage();assert.equal(sent[5],'project');assert.equal(sent[6],'project');assert.equal(sent[3],true);assert.equal(confirmCalls,2);
expectedLevel='full';selected.value='full';routeIntent='conversation';inputEl.value='Merhaba';window.__writeConfirmed=false;
await sendAgentMessage();assert.equal(sent[5],'read-only');assert.equal(sent[6],'full');assert.equal(sent[3],false);assert.equal(confirmCalls,2);
})()
.catch(e=>{console.error(e);process.exitCode=1});
''')


if __name__=='__main__':unittest.main()
