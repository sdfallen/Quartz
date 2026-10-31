import subprocess
import unittest
import gui


class PermissionButtonTests(unittest.TestCase):
    def test_bridge_error_reenables_buttons_and_success_reloads_task(self):
        start=gui._HTML.index('    const decide=async(accept)=>{')
        end=gui._HTML.index('    approve.onclick=',start)
        script=r'''
const assert=require('node:assert/strict');
const approve={},deny={},status={},pending={id:'scope'};
let removed=0,refreshed=0,polled=0;
const panel={remove:()=>removed++};
const window={pywebview:{api:{natural_approve:async()=>{throw new Error('bridge disconnected')}}}};
async function refreshDesktopTaskState(){refreshed++;}
async function pollNaturalTask(){polled++;}
''' + gui._HTML[start:end] + r'''
(async()=>{
 await decide(true); assert.equal(approve.disabled,false); assert.equal(deny.disabled,false);
 assert.equal(removed,0); assert(status.textContent.includes('doğrulanamadı'));
 window.pywebview.api.natural_approve=async()=>({status:'ok'});
 await decide(true);assert.equal(removed,1);assert.equal(refreshed,1);assert.equal(polled,1);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
