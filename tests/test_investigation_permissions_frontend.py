"""Execute the shipped diagnostics permission card with a fake DOM/bridge."""
import subprocess
import unittest

from ui.js_diagnostics import JAVASCRIPT


SCRIPT = JAVASCRIPT[:JAVASCRIPT.index("  safeBtn.addEventListener('click'")]
HARNESS = r"""
const assert = require('node:assert/strict');
let currentConvId='conv', lowSpecHardware=false;
const calls=[],timers=[];
function setTimeout(fn,ms){timers.push({fn,ms});return timers.length;}
function clearTimeout(){}
function isUiHidden(){return false;}
function all(root,predicate){const out=[];for(const n of root.children||[]){if(predicate(n))out.push(n);out.push(...all(n,predicate));}return out;}
function element(tag){let text='';const n={tagName:tag.toUpperCase(),dataset:{},style:{},attrs:{},children:[],
 className:'',disabled:false,open:false,onclick:null,classList:{toggle(){}},
 append(...nodes){this.children.push(...nodes);},appendChild(node){this.children.push(node);return node;},
 replaceChildren(...nodes){text='';this.children=nodes;},setAttribute(k,v){this.attrs[k]=String(v);},
 querySelector(selector){if(selector.startsWith('[data-diagnostics-job='))return all(this,x=>x.dataset.diagnosticsJob===selector.split('"')[1])[0]||null;
 if(selector.startsWith('.'))return all(this,x=>x.className.split(' ').includes(selector.slice(1)))[0]||null;return null;},
 querySelectorAll(selector){if(selector==='details[data-detail-key]')return all(this,x=>x.tagName==='DETAILS'&&x.dataset.detailKey);return [];}};
 Object.defineProperty(n,'textContent',{get(){return text+this.children.map(x=>x.textContent||'').join('');},set(value){text=String(value);this.children=[];}});
 Object.defineProperty(n,'innerHTML',{set(){throw Error('Untrusted HTML parsing');}});return n;}
const chatEl=element('main');
const document={createElement:element,getElementById:()=>null,addEventListener(){}};
function job(overrides={}){return {id:'job',state:'running',phase:'analysis',progress:40,checks:[],
 chat_task:{task_id:'task',conversation_id:'conv',state:'awaiting_permission',
 pending_permission:{request_id:'request',generation:3,effect:'inspect_static',reason:'Salt okunur uygulama incelemesi'}},...overrides};}
function doneTask(){return {task_id:'task',conversation_id:'conv',state:'running',pending_permission:null};}
let reply={status:'ok',data:{diagnostics:job({chat_task:null}),chat_task:doneTask()}},
 statusReply={status:'ok',data:job()};
const window={pywebview:{api:{
 investigation_grant_scope:async(...args)=>{calls.push(['grant',...args]);return reply;},
 diagnostics_status:async id=>{calls.push(['status',id]);return statusReply;},
 diagnostics_start:()=>{throw Error('Must not start a new task');},
 diagnostics_cancel:async id=>({status:'ok',data:job({id,state:'cancelled',chat_task:null})})
}}};
function buttons(){return all(chatEl,x=>x.tagName==='BUTTON');}
function approve(){return buttons().find(x=>x.dataset.investigationApprove);}
function deny(){return buttons().find(x=>x.dataset.investigationDeny);}
"""


class InvestigationPermissionsFrontendTests(unittest.TestCase):
    def run_js(self, checks):
        result=subprocess.run(['node','-'],input=HARNESS+SCRIPT+'\n(async()=>{\n'+checks+
                              '\n})().catch(e=>{console.error(e);process.exitCode=1});',
                              capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_approve_is_bound_once_and_resumes_same_job(self):
        self.run_js(r"""
const input=job();const card=renderSelfDiagnosticsCard(input);
const details=card.querySelectorAll('details[data-detail-key]').find(x=>x.dataset.detailKey==='meta:summary');details.open=true;
const click=approve().onclick;let release;const waiting=new Promise(r=>release=r);
window.pywebview.api.investigation_grant_scope=async(...args)=>{calls.push(['grant',...args]);await waiting;return reply;};
const pending=click();assert.equal(approve().disabled,true);assert.equal(deny().disabled,true);
await click();assert.equal(calls.length,1);
renderSelfDiagnosticsCard(input);assert.equal(approve().disabled,true);
// Mutating the source object after rendering cannot change request identity.
input.chat_task.pending_permission.generation=99;input.chat_task.pending_permission.effect='mutated';
assert.deepEqual(calls[0],['grant','task','request',3,'inspect_static',true,'conv']);
release();await pending;
assert.equal(chatEl.children.length,1);assert.equal(approve(),undefined);
assert.equal(activeDiagJobId,'job');assert.ok(timers.length);
assert.equal(card.querySelectorAll('details[data-detail-key]').find(x=>x.dataset.detailKey==='meta:summary').open,true);
await click();assert.equal(calls.length,1);
""")

    def test_denial_is_raw_false_and_cannot_be_replayed(self):
        self.run_js(r"""
renderSelfDiagnosticsCard(job());const oldApprove=approve().onclick,oldDeny=deny().onclick;
await oldDeny();assert.deepEqual(calls[0],['grant','task','request',3,'inspect_static',false,'conv']);
assert.equal(typeof calls[0][5],'boolean');await oldDeny();await oldApprove();assert.equal(calls.length,1);
""")

    def test_missing_invalid_or_other_conversation_permission_has_no_buttons(self):
        self.run_js(r"""
let current=job({chat_task:null});renderSelfDiagnosticsCard(current);assert.equal(approve(),undefined);
assert.ok(buttons().some(x=>x.dataset.diagnosticsCancel==='job'));
current=job();current.chat_task.pending_permission.generation='3';renderSelfDiagnosticsCard(current);assert.equal(approve(),undefined);
current=job();current.chat_task.state='completed';renderSelfDiagnosticsCard(current);assert.equal(approve(),undefined);
current=job();current.chat_task.conversation_id='other';
assert.equal(renderSelfDiagnosticsCard(current),null);assert.equal(calls.length,0);
""")

    def test_stale_reply_disables_replay_and_offers_same_job_refresh(self):
        self.run_js(r"""
reply={status:'error',data:'<script>stale</script>'};renderSelfDiagnosticsCard(job());
const oldClick=approve().onclick;await oldClick();await oldClick();assert.equal(calls.length,1);
assert.equal(approve().disabled,true);assert.equal(deny().disabled,true);
assert.match(chatEl.textContent,/kararı doğrulanamadı/);assert.ok(!chatEl.textContent.includes('<script>stale'));
const refresh=buttons().find(x=>x.textContent==='Durumu yeniden oku');assert.ok(refresh);
await refresh.onclick();await refresh.onclick();assert.equal(calls.filter(x=>x[0]==='status').length,1);
assert.deepEqual(calls[1],['status','job']);assert.equal(approve().disabled,true);
""")

    def test_changed_conversation_blocks_click_and_late_response(self):
        self.run_js(r"""
renderSelfDiagnosticsCard(job());const old=approve().onclick;currentConvId='other';await old();assert.equal(calls.length,0);
currentConvId='conv';let release;const waiting=new Promise(r=>release=r);
window.pywebview.api.investigation_grant_scope=async(...args)=>{calls.push(args);await waiting;return reply;};
const pending=old();currentConvId='other';const marker=element('p');marker.textContent='other conversation';chatEl.replaceChildren(marker);
release();await pending;assert.equal(chatEl.textContent,'other conversation');assert.equal(timers.length,0);
""")

    def test_new_request_generation_invalidates_old_button(self):
        self.run_js(r"""
renderSelfDiagnosticsCard(job());const oldClick=approve().onclick;
const newer=job();newer.chat_task.pending_permission.generation=4;
newer.chat_task.pending_permission.request_id='request-new';renderSelfDiagnosticsCard(newer);
await oldClick();assert.equal(calls.length,0);
await approve().onclick();assert.deepEqual(calls[0],['grant','task','request-new',4,'inspect_static',true,'conv']);
""")

    def test_permission_text_is_inert_and_request_generation_is_not_evaluated(self):
        self.run_js(r"""
const input=job();input.chat_task.pending_permission.reason='<img src=x onerror=alert(1)>';
input.chat_task.pending_permission.effect='<script>danger()</script>';
renderSelfDiagnosticsCard(input);assert.ok(chatEl.textContent.includes('<img src=x onerror=alert(1)>'));
assert.equal(all(chatEl,n=>['IMG','SCRIPT'].includes(n.tagName)).length,0);
assert.equal(calls.length,0); // Rendering text never grants a permission.
input.chat_task.pending_permission.generation='process.exit()';renderSelfDiagnosticsCard(input);assert.equal(approve(),undefined);
""")

    def test_poll_fences_conversation_change_and_keeps_permission_task_polling(self):
        self.run_js(r"""
let release;const waiting=new Promise(r=>release=r);
window.pywebview.api.diagnostics_status=async()=>{await waiting;return statusReply;};
const reading=pollSelfDiagnostics('job');currentConvId='other';release();await reading;
assert.equal(chatEl.children.length,0);assert.equal(timers.length,0);
currentConvId='conv';statusReply={status:'ok',data:job({state:'completed'})};
window.pywebview.api.diagnostics_status=async()=>statusReply;
await pollSelfDiagnostics('job');assert.equal(activeDiagJobId,'job');assert.ok(approve());assert.ok(timers.length);
currentConvId='other';const before=calls.length;await timers.at(-1).fn();
assert.equal(calls.length,before);assert.equal(chatEl.children.length,1);
""")


if __name__=='__main__':unittest.main()
