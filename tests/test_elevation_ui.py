import subprocess
import unittest
import gui


class ElevationUiTests(unittest.TestCase):
    def test_full_permission_cannot_auto_approve_uac(self):
        start=gui._HTML.index('  async function pollNaturalTask()')
        end=gui._HTML.index('  async function pollCoordination()',start)
        script=r'''
const assert=require('node:assert/strict');
let activeTaskSquad=null, currentConvId='chat', approvals=0, panel;
const pending={id:'uac1',kind:'elevation',phase:'awaiting_user',conversation_id:'chat',
 operator:'codex',reason:'Requires elevation',targets:[],logs:[],launch:{exe:'C:/Test/app.exe'}};
function element(){return {dataset:{},children:[],append(...v){this.children.push(...v)},setAttribute(){}};}
const document={querySelectorAll:()=>[],querySelector:()=>null,
 getElementById:()=>({value:'full'}),createElement:element};
const chatEl={append:p=>panel=p};
function scrollToBottom(){};function updateSquadBadge(){};
const window={pywebview:{api:{natural_status:async()=>({status:'ok',data:{pending}}),
 natural_approve:async()=>{approvals++;throw new Error('unexpected automatic UAC')}}}};
''' + gui._HTML[start:end] + r'''
(async()=>{
 await pollNaturalTask();assert.equal(approvals,0);
 const button=panel.children.find(e=>e.textContent==='Windows UAC isteğini aç');assert(button);
 assert.equal(button.disabled,false);
 pending.phase='prompting';await pollNaturalTask();
 const waiting=panel.children.find(e=>e.textContent==='Windows UAC isteğini aç');assert.equal(waiting.disabled,true);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
