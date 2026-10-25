import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

import gui
from core.source_verification import verify_changed_python
from core.task_outcome import stop_summary


class PassiveEvidenceTests(unittest.TestCase):
    def test_parsing_never_executes_project_code(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'sample.py'
            path.write_text('raise RuntimeError("must never execute")\n', encoding='utf-8')
            result = verify_changed_python(folder, [str(path)])
            self.assertEqual(result['status'], 'VERIFIED')
            self.assertEqual(result['level'], 'SOURCE/STATIC')
            self.assertFalse(result['tests_executed']); self.assertFalse(result['goal_accepted'])

    def test_invalid_syntax_is_failed_without_copying_source_into_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'bad.py'; path.write_text('private_value = (\n', encoding='utf-8')
            result = verify_changed_python(folder, [str(path)])
            self.assertEqual(result['status'], 'FAILED')
            self.assertNotIn('private_value', json.dumps(result))
            self.assertEqual(result['files'][0]['line'], 1)

    def test_incomplete_removed_large_or_outside_files_never_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'good.py').write_text('x = 1\n')
            for paths, options in ((['removed.py'], {}), (['good.py'], {'warning':'inventory incomplete'}),
                                    ([str(root.parent/'outside.py')], {}), (['good.py'], {'max_bytes':2})):
                with self.subTest(paths=paths):
                    self.assertEqual(verify_changed_python(folder, paths, **options)['status'], 'NOT TESTED')

    def test_writer_host_receipt_detects_invalid_python_and_releases_lock(self):
        from tests.test_multi_agent_service import MultiAgentServiceTests
        from core.workspace_checkpoint import snapshot_workspace_files
        service, runtime, _ = MultiAgentServiceTests().make_service()
        runtime.get.return_value = {'id':'run', 'status':'completed', 'files_changed':[]}
        with tempfile.TemporaryDirectory() as folder:
            before = snapshot_workspace_files(folder)
            (Path(folder)/'bad.py').write_text('broken = (\n')
            service._writers['key'] = {'owner':'run'}
            service._watch_writer('key', 'run', runtime, folder, before)
            result = service.get_run('run')
            self.assertEqual(result['source_validation']['status'], 'FAILED')
            self.assertNotIn('key', service._writers)

    def test_human_summary_keeps_internal_reason_out_of_primary_text(self):
        text = stop_summary('blocked: foreground changed (user takeover)')
        self.assertIn('odağı', text); self.assertNotIn('foreground', text)
        self.assertIn('anlamına gelmez', stop_summary('completed'))


class ActualJavaScriptTests(unittest.TestCase):
    def node(self, source):
        result = subprocess.run(['node', '-e', source], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_in_flight_chat_poll_is_single_flight_even_on_failure(self):
        source = gui._HTML.split('  let chatPollBusy = false;', 1)[1].split('  let savedResponseDetail', 1)[0]
        self.node('let chatPollBusy = false;\n' + source + r'''
const assert=require('assert');let calls=0,finish;
global.window={pywebview:{api:{chat_poll:()=>{calls++;return new Promise(r=>finish=r)}}}};
(async()=>{
 const first=pollAgentTurn();await pollAgentTurn();assert.equal(calls,1);
 finish({status:'error'});await first;assert.equal(chatPollBusy,false);
 const next=pollAgentTurn();assert.equal(calls,2);finish({status:'error'});await next;
})().catch(e=>{console.error(e);process.exitCode=1});
''')

    def test_model_completion_and_host_source_check_are_not_live_acceptance(self):
        source = gui._HTML.split('  function agentMessageView(', 1)[1].split('  function renderMessageBody(', 1)[0]
        self.node('function agentMessageView(' + source + r'''
const assert=require('assert');
const message={status:'completed',metadata:{permission_level:'project'}};
assert(agentMessageView('Tests passed',message,'short').state.includes('kanıtı yok'));
message.metadata.host_evidence={source_validation:{status:'VERIFIED'}};
assert(agentMessageView('Done',message,'short').state.includes('test başarısı doğrulanmış değil'));
message.metadata.host_evidence.historical=true;
assert(agentMessageView('Done',message,'short').state.includes('Önceki oturumun kaynak kanıtı'));
message.metadata.host_evidence.source_validation.status='FAILED';
assert(agentMessageView('Done',message,'short').state.includes('başarısız'));
message.status='interrupted';
assert(agentMessageView('Partial',message,'short').state.includes('otomatik sürdürülmedi'));
''')

    def test_per_agent_labels_keep_both_results_visible(self):
        source=gui._HTML.split('  function agentProgressText(',1)[1].split('  async function loadActiveConversation()',1)[0]
        self.node('function agentProgressText('+source+r'''
const assert=require('assert');
const text=agentProgressText({codex:{status:'completed'},antigravity:{status:'running',step:'checking'},evil:{status:'completed'}});
assert(text.includes('Codex: tamamlandı'));assert(text.includes('Antigravity: çalışıyor'));
assert(!text.includes('evil'));assert.equal(agentProgressText({}),'');
''')

    def test_resume_button_creates_fresh_readonly_draft_without_sending(self):
        source=gui._HTML.split('  function renderMessageBody(',1)[1].split('  function appendMsg(',1)[0]
        self.node('function renderMessageBody('+source+r'''
const assert=require('assert');let clicked,created=0,loaded=0;
const level={value:'short'},permission={value:'full'};
global.document={getElementById:id=>id==='responseDetail'?level:permission,createElement:tag=>{
 const element={style:{},append:()=>{}};if(tag==='button')clicked=element;return element;}};
global.currentConvId='old';global.inputEl={value:'',focus:()=>{}};global.logLine=()=>{};
global.agentMessageView=()=>({summary:'partial',state:'interrupted',details:''});
global.loadActiveConversation=async()=>{loaded++};
global.window={__writeConfirmed:true,pywebview:{api:{
 chat_prepare_resume:async()=>({status:'ok',data:{draft:'Review only',agent:'codex',project_id:'p',warning:'Review first'}}),
 chat_new:async(title,agent,project)=>{created++;assert.equal(agent,'codex');assert.equal(project,'p');return {status:'ok'}},
 chat_send:()=>{throw new Error('must not dispatch')}
}}};
renderMessageBody({dataset:{},replaceChildren:()=>{},append:()=>{}},'partial',{id:'m',status:'interrupted'});
(async()=>{await clicked.onclick();assert.equal(created,1);assert.equal(loaded,1);
assert.equal(permission.value,'read-only');assert.equal(window.__writeConfirmed,false);assert.equal(inputEl.value,'Review only');
})().catch(e=>{console.error(e);process.exitCode=1});
''')
