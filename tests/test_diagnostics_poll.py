import subprocess
import unittest
import gui


class DiagnosticsPollingTests(unittest.TestCase):
    def test_failed_status_retries_and_never_discards_unverified_job(self):
        start = gui._HTML.index('  async function pollSelfDiagnostics(')
        end = gui._HTML.index('  async function startSelfDiagnostics(', start)
        script = r'''
const assert=require('node:assert/strict');
let activeDiagJobId='job', diagPollBusy=false, diagPollTimer=null;
const diagPollFailures=new Map();
let scheduled=0, rendered=0, reply={status:'error'};
const window={pywebview:{api:{diagnostics_status:async()=>reply}}};
const chatEl={querySelector:()=>null};
const setTimeout=()=>++scheduled, clearTimeout=()=>{};
function renderSelfDiagnosticsCard(){rendered++;}
''' + gui._HTML[start:end] + r'''
(async()=>{
 await pollSelfDiagnostics(); assert.equal(scheduled,1); assert.equal(activeDiagJobId,'job');
 await pollSelfDiagnostics(); await pollSelfDiagnostics(); await pollSelfDiagnostics();
 assert.equal(scheduled,3); assert.equal(activeDiagJobId,'job'); assert.equal(rendered,0);
 reply={status:'ok',data:{id:'wrong',state:'completed'}};
 await pollSelfDiagnostics(); assert.equal(activeDiagJobId,'job'); assert.equal(rendered,0);
 reply={status:'ok',data:{id:'job',state:'completed'}};
 await pollSelfDiagnostics(); assert.equal(activeDiagJobId,null); assert.equal(rendered,1);
 assert.equal(diagPollFailures.size,0); assert.equal(diagPollBusy,false);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
