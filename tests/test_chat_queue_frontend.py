"""Execute shipped chat fragments with a fake bridge, not live providers or GUI."""
import subprocess
import unittest

from ui.js_chat import JAVASCRIPT as CHAT
from ui.js_messages import JAVASCRIPT as MESSAGES
from ui.js_lifecycle import JAVASCRIPT as LIFECYCLE


def segment(source, start, end):
    return source[source.index(start):source.index(end, source.index(start))]


HARNESS = r"""
const assert = require('node:assert/strict');
const events = {}, elements = new Map(), calls = [], rendered = [], timers = new Map();
let nextTimer=1, thinking=false, currentConvId='c', activeBotBubble={textContent:'original'},
    chatPollInterval=null, requestTimer=null, requestStarted=0, msgCount=0, histCursor=0,
    userPinnedToBottom=true, savedResponseDetail='short', conversationLoaded=true,
    desktopView={stop_ref:null}, idleDesktopTick=0, uiEventsPollBusy=false;
const inpHistory=[];
function el(id) {if(!elements.has(id)) elements.set(id,{value:'full',textContent:'',disabled:false,
 style:{},dataset:{},classList:{toggle(){},remove(){},add(){}},
 addEventListener(type,fn){events[id+':'+type]=fn;}});return elements.get(id);}
const inputEl=el('input'),thinkingText=el('thinking'),cancelBtn=el('cancel'),sendBtn=el('send'),
 writerBadge=el('writer'),thinkingRow=el('row'),mainAgentSelect=el('agent'),
 mainProjectSelect=el('project'),codexModelSelect=el('model'),codexEffortSelect=el('effort'),
 agyModelSelect=el('agy'),agyEffortSelect=el('agyEffort'),chatConvTitle=el('title');
inputEl.value='ek talimat';mainAgentSelect.value='codex';mainProjectSelect.value='quartz';
const document={getElementById:el,body:el('body'),querySelectorAll:()=>[]};
const chatEl={scrollTop:0,querySelectorAll:()=>[]};
let route={status:'ok',data:{handled:false,intent:'task'}},
    response={status:'ok',data:{queued:true,task_id:'t',queue_position:1,
      conversation_id:'c',user_message:{id:'u'},assistant_message:{id:'a',sender:'codex'}}},
    pollData={active:true,queued_instructions:1}, cancelResponse={status:'ok',data:{stop_receipt:{status:'pending'}}};
const window={__writeConfirmed:true,confirm:()=>true,pywebview:{api:{
 coordination_route:async(...args)=>{calls.push(['route',...args]);return route;},
 chat_send:async(...args)=>{calls.push(['send',...args]);return response;},
 chat_poll:async()=>({status:'ok',data:pollData}),
 chat_cancel:async()=>{calls.push(['cancel']);return cancelResponse;},
 cancel_request:async()=>{calls.push(['legacyCancel']);return {status:'ok'};}
}}};
function setInterval(fn,ms){const id=nextTimer++;timers.set(id,{fn,ms});return id;}
function clearInterval(id){timers.delete(id);}
function setTimeout(){}
function setOrb(){}
function logLine(){}
function appendMsg(kind,label,text,id,sender){const bubble={textContent:text};const item={kind,label,text,
 dataset:{msgId:id},querySelector:()=>bubble};rendered.push(item);return item;}
function formatMessageLabel(m){return m.sender.toUpperCase();}
function syncConversationMessages(){}
function renderMessageBody(){}
function scrollToBottom(){}
function agentProgressText(){return 'working';}
async function refreshDesktopTaskState(){calls.push(['desktop']);}
async function pollNaturalTask(){calls.push(['natural']);}
async function loadActiveConversation(){}
"""

THINKING = segment(MESSAGES, '  function setThinking(v)', '  function appendActionCard(')
POLL = segment(CHAT, '  let chatStopReceipt =', "  let savedResponseDetail =")
SEND = segment(CHAT, '  let coordinationRouting =', '  async function sendMessage()')
STOP = segment(CHAT, "  cancelBtn.addEventListener('click'", '  function updatePermissionSelectionHint()')


class ChatQueueFrontendTests(unittest.TestCase):
    def check(self, checks, extra=''):
        result = subprocess.run(['node', '-e', HARNESS + THINKING + POLL + SEND + STOP + extra +
                                 '\n(async()=>{\n' + checks +
                                 '\n})().catch(e=>{console.error(e);process.exitCode=1});'],
                                capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_running_turn_queues_once_without_replacing_worker_view(self):
        self.check(r"""
setThinking(true);const oldBubble=activeBotBubble,oldTimer=requestTimer;
let release;const wait=new Promise(r=>release=r);
window.pywebview.api.chat_send=async(...args)=>{calls.push(['send',...args]);await wait;return response;};
const first=sendAgentMessage();await new Promise(setImmediate);
assert.equal(inputEl.value,'ek talimat');
await sendAgentMessage();assert.equal(calls.filter(c=>c[0]==='send').length,1);
release();await first;
assert.equal(thinking,true);assert.equal(activeBotBubble,oldBubble);assert.equal(requestTimer,oldTimer);
assert.equal(cancelBtn.style.display,'inline-block');assert.equal(inputEl.value,'');
assert.equal(rendered.filter(x=>x.kind==='user').length,1);
assert.equal(rendered.at(-1).dataset.msgId,'a');assert.match(rendered.at(-1).text,/sırada/);
assert.deepEqual(calls.slice(0,2).map(x=>x[0]),['route','send']);
assert.equal(calls[1][3],'c');assert.equal(calls[1][6],'full');
""")

    def test_a_reply_polled_before_send_returns_is_reused_not_duplicated(self):
        # Live exam 7 Nov: Codex answered within ms; polling drew the reply first,
        # then the send path added the user bubble below it and an empty "..." twin.
        self.check(r"""
response={status:'ok',data:{conversation_id:'c',user_message:{id:'u1'},assistant_message:{id:'a1',sender:'codex'}}};
const early={kind:'bot',dataset:{msgId:'a1'},querySelector:()=>({textContent:'hazır yanıt'})};
const order=[early];
chatEl.querySelector=sel=>order.find(x=>sel.includes(`"${x.dataset.msgId}"`))||null;
chatEl.insertBefore=(node,ref)=>{order.splice(order.indexOf(node),1);order.splice(order.indexOf(ref),0,node);};
const realAppend=appendMsg;appendMsg=(...a)=>{const item=realAppend(...a);item.parentNode=chatEl;order.push(item);return item;};
await sendAgentMessage();
assert.equal(rendered.filter(x=>x.kind==='bot').length,0);  // no second, empty bubble for a1
assert.deepEqual(order.map(x=>x.dataset.msgId),['u1','a1']);  // the question sits above its answer
""")

    def test_rejected_followup_preserves_input_and_current_task(self):
        self.check(r"""
setThinking(true);const oldBubble=activeBotBubble,oldTimer=requestTimer;
response={status:'error',data:'Aktif görevin yetkisi genişletilemez.'};
await sendAgentMessage();
assert.equal(inputEl.value,'ek talimat');assert.equal(thinking,true);
assert.equal(activeBotBubble,oldBubble);assert.equal(requestTimer,oldTimer);
assert.equal(rendered.filter(x=>x.kind==='user').length,0);
assert.match(rendered.at(-1).text,/kabul edilmedi/);
assert.equal(chatSubmissionBusy,false);
""")

    def test_desktop_router_has_priority_and_does_not_dispatch_chat(self):
        self.check(r"""
route={status:'ok',data:{handled:true,natural_started:true}};
await sendAgentMessage();
assert.equal(calls.filter(c=>c[0]==='send').length,0);
assert.equal(calls[0][0],'route');assert.equal(calls[0].at(-1),'codex');
assert.deepEqual(calls.slice(1).map(x=>x[0]),['desktop','natural']);
""")

    def test_pending_failed_and_missing_receipts_do_not_claim_idle(self):
        self.check(r"""
pollData={active:false,status:'cancelled',stop_receipt:{status:'pending',worker_pending:true}};
await pollAgentTurn();assert.equal(thinking,true);assert.ok(chatPollInterval);
assert.match(thinkingText.textContent,/kapanışı doğrulanıyor/);
const interval=chatPollInterval;
pollData={active:false,status:'cancelled'};
await pollAgentTurn();assert.equal(chatPollInterval,interval);assert.equal(thinking,true);
pollData.stop_receipt={status:'failed',history_error_type:'OSError',worker_pending:false};
await pollAgentTurn();assert.match(thinkingText.textContent,/kaydı tamamlanamadı/);
assert.equal(cancelBtn.disabled,false);
await sendAgentMessage();assert.equal(calls.filter(c=>c[0]==='send').length,0);
assert.equal(inputEl.value,'ek talimat');
pollData.stop_receipt={status:'confirmed'};
await pollAgentTurn();assert.equal(thinking,false);assert.equal(chatPollInterval,null);
""")

    def test_stop_retries_both_owners_even_if_one_throws(self):
        self.check(r"""
setThinking(true);
window.pywebview.api.chat_cancel=()=>{calls.push(['cancel']);throw Error('bridge');};
pollData={active:false,status:'cancelled'};
await events['cancel:click']();
assert.deepEqual(calls.map(x=>x[0]),['cancel','legacyCancel']);
assert.equal(thinking,true);assert.ok(chatPollInterval);assert.equal(cancelBtn.disabled,false);
window.pywebview.api.chat_cancel=async()=>cancelResponse;
await events['cancel:click']();assert.equal(chatStopReceipt.status,'pending');
cancelResponse={status:'ok',data:{stop_receipt:{status:'confirmed'}}};
pollData={active:false,status:'cancelled',stop_receipt:{status:'confirmed'}};
await events['cancel:click']();
assert.equal(thinking,false);assert.equal(chatPollInterval,null);
""")

    def test_submitting_does_not_erase_newer_edits(self):
        self.check(r"""
let release;const wait=new Promise(r=>release=r);
window.pywebview.api.chat_send=async()=>{await wait;return response;};
setThinking(true);const sent=sendAgentMessage();await new Promise(setImmediate);
inputEl.value='bir sonraki düzenleme';release();await sent;
assert.equal(inputEl.value,'bir sonraki düzenleme');
""")

    def test_stop_fences_late_route_and_send_responses(self):
        self.check(r"""
let release;const waiting=new Promise(r=>release=r);
window.pywebview.api.coordination_route=async()=>{await waiting;return route;};
const pendingRoute=sendAgentMessage();await new Promise(setImmediate);
pollData={active:false,status:'cancelled',stop_receipt:{status:'pending'}};
await events['cancel:click']();release();await pendingRoute;
assert.equal(calls.filter(c=>c[0]==='send').length,0);
assert.equal(thinking,true);assert.equal(chatStopReceipt.status,'pending');
assert.equal(inputEl.value,'ek talimat');
// A request already dispatched before Stop must not reset its receipt on return.
chatStopReceipt=null;window.pywebview.api.coordination_route=async()=>route;
let finish;const sending=new Promise(r=>finish=r);
window.pywebview.api.chat_send=async()=>{await sending;return {status:'ok',data:{queued:false}};};
const pendingSend=sendAgentMessage();await new Promise(setImmediate);
await events['cancel:click']();finish();await pendingSend;
assert.equal(chatStopReceipt.status,'pending');assert.equal(thinking,true);
assert.equal(rendered.filter(x=>x.kind==='user').length,0);
""")

    def test_reload_rehydrates_pending_cleanup_from_status(self):
        event_loop=segment(LIFECYCLE, '  let uiEventsPollBusy =', "  window.addEventListener('pywebviewready'")
        # The loop declares this flag itself.
        event_loop=event_loop.replace('  let uiEventsPollBusy = false;', '')
        self.check(r"""
window.pywebview.api.ui_events=async()=>({status:'ok',data:[]});
window.pywebview.api.chat_status=async()=>({status:'ok',data:{active_turn:{status:'cancelled',stop_receipt:{status:'pending'}}}});
pollData={active:false,status:'cancelled',stop_receipt:{status:'pending'}};
await pollUiEvents();
assert.equal(thinking,true);assert.ok(chatPollInterval);assert.equal(chatStopReceipt.status,'pending');
""", extra=r"""
function isUiIdle(){return false;}function isUiHidden(){return false;}
function hasActiveDesktopTask(){return false;}function renderUiEvents(){}
function updateAntigravitySafety(){}let lowSpecHardware=false;
"""+event_loop)


if __name__ == '__main__':
    unittest.main()
