"""Wave 2 UI contracts: outcome badges and the paused approval card.

The UI only reads host fields (outcome, pause, pending). Model text never earns a
badge, a paused card cannot approve before runtime cleanup, and an expired card
can only be reissued, never approved.
"""
import subprocess
import unittest
from unittest.mock import MagicMock

import gui


def _node(code):
    return subprocess.run(["node", "-e", code], capture_output=True, text=True, encoding="utf-8", timeout=20)


def _between(start, end):
    first = gui._HTML.index(start)
    return gui._HTML[first:gui._HTML.index(end, first)]


MESSAGE_VIEW = "function agentMessageView(" + gui._HTML.split("  function agentMessageView(", 1)[1].split("  function renderMessageBody(", 1)[0]


class OutcomeBadgeTests(unittest.TestCase):
    def view(self, cases):
        code = MESSAGE_VIEW + r'''
const assert=require('node:assert/strict');
const view=(status,meta,text='Bitti')=>agentMessageView(text,{status,metadata:meta},'short').state;
''' + cases
        result = _node(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_group_names_the_agent_that_did_not_finish(self):
        self.view(r'''
assert.equal(view('partial',{outcome:{participants:{codex:'completed',antigravity:'failed'}}}),
  'Kısmi — istenen ajanlardan biri tamamlayamadı: Gemini');
assert.equal(view('partial',{}),'Kısmi — istenen ajanlardan biri tamamlayamadı');
assert.match(view('completed',{outcome:{goal_verdict:'PARTIAL',participants:{codex:'failed',antigravity:'completed'}}}),/Kısmi.*Codex/);
''')

    def test_only_a_host_postcondition_with_checks_reports_a_verified_goal(self):
        self.view(r'''
const host={goal_verdict:'VERIFIED',goal_evidence:{level:'HOST POSTCONDITION',checks:[{path:'not.txt'},{path:'b.txt'}]}};
assert.match(view('completed',{outcome:host}),/2 hedef koşulu dosyadan doğrulandı; kullanıcı kabulü ayrı/);
for (const fake of [{goal_verdict:'VERIFIED'},{goal_verdict:'VERIFIED',goal_evidence:{level:'MODEL',checks:[1]}},
                    {goal_verdict:'VERIFIED',goal_evidence:{level:'HOST POSTCONDITION',checks:[]}}]) {
  assert.doesNotMatch(view('completed',{outcome:fake,review_scope:'x'}),/doğrulandı/);
}
// The model writing VERIFIED in its answer is text, not evidence.
assert.equal(view('completed',{},'VERIFIED: hedef doğrulandı, her şey tamam'),'');
''')

    def test_execution_only_is_labelled_for_tasks_but_plain_chat_stays_clean(self):
        self.view(r'''
assert.equal(view('completed',{outcome:{completion_kind:'execution_only'}}),'');
assert.equal(view('completed',{review_scope:'supplied-text-only'}),'Yürütme bitti, hedef henüz doğrulanmadı.');
assert.equal(view('completed',{natural_task:'job'}),'Yürütme bitti, hedef henüz doğrulanmadı.');
assert.match(view('completed',{permission_level:'project'}),/kanıtı yok/);
''')

    def test_restart_while_awaiting_approval_says_the_old_permission_is_void(self):
        self.view(r'''
assert.equal(view('interrupted',{interrupted_while:'awaiting_approval'}),
  'Önceki oturum onay beklerken kesildi; eski izin geçersiz. Devam için görevi yeniden yaz.');
assert.equal(view('interrupted',{}),'Önceki oturum kesildi; otomatik sürdürülmedi');
''')

    def test_quartz_text_check_has_its_own_scoped_label(self):
        self.view(r'''
const ok={status:'OBSERVED UI CRITERION VERIFIED',expected_text:['deneme']};
assert.equal(view('completed',{natural_task:'job',host_check:ok}),'İstenen metin Quartz gözlemiyle ekranda görüldü; kullanıcı kabulü ayrı.');
for (const fake of [{status:'VERIFIED',expected_text:['x']},{status:'OBSERVED UI CRITERION VERIFIED',expected_text:[]},{status:'OBSERVED UI CRITERION VERIFIED'}]) {
  assert.equal(view('completed',{natural_task:'job',host_check:fake}),'Yürütme bitti, hedef henüz doğrulanmadı.');
}
assert.equal(view('cancelled',{natural_task:'job',host_check:ok}),'Durduruldu');
assert.equal(view('completed',{host_check:ok}),'');  // Not a desktop task message.
''')

    def test_blocked_and_paused_have_their_own_meaning(self):
        self.view(r'''
assert.equal(view('blocked',{}),'Engellendi; nedeni ayrıntılarda');
assert.equal(view('awaiting_approval',{}),'Onay bekleniyor — görev duraklatıldı');
assert.doesNotMatch(view('blocked',{}),/doğrulan/);
''')

    def test_local_task_card_has_no_check_mark_or_english_state(self):
        source = _between("  function renderTasks(tasks=[]) {", "\n  }\n") + "\n  }\n"
        code = r'''
const assert=require('node:assert/strict');
function el(){return {children:[],textContent:'',className:'',append(...c){this.children.push(...c)},appendChild(c){this.children.push(c)},set innerHTML(v){this.children=[]}};}
const document={createElement:el};const taskList=el();
''' + source + r'''
renderTasks([{id:'t',title:'Rapor',status:'completed',steps:[{status:'completed'}]}]);
const row=taskList.children[0];
assert.equal(row.children[0].textContent,'Rapor');
assert.equal(row.children[1].textContent,'1/1 adım · tamamlandı');
renderTasks([{id:'t',title:'X',status:'weird',steps:[]}]);
assert.equal(taskList.children[0].children[1].textContent,'0/0 adım · durum bilinmiyor');
'''
        result = _node(code)
        self.assertEqual(result.returncode, 0, result.stderr)


POLL = _between("  async function pollNaturalTask() {", "  async function pollCoordination()")

CARD_HARNESS = r'''
const assert=require('node:assert/strict');
const cards=[];const calls=[];let permission='read-only';let natural;let activeTaskSquad=null;
function el(tag){return {tag,dataset:{},children:[],textContent:'',disabled:false,hidden:false,className:'',
  setAttribute(k,v){this['attr_'+k]=v},append(...c){this.children.push(...c)},
  remove(){const i=cards.indexOf(this);if(i>=0)cards.splice(i,1)}};}
const document={createElement:el,getElementById:()=>({value:permission}),
  querySelectorAll:()=>cards.slice(),
  querySelector:(sel)=>{const m=/data-natural-permission="([^"]+)"/.exec(sel);return cards.find(c=>c.dataset.naturalPermission===m[1])||null;}};
const chatEl={append:(p)=>cards.push(p)};const currentConvId='chat';
function scrollToBottom(){} function updateSquadBadge(){} function logLine(){}
async function refreshDesktopTaskState(){}
const window={pywebview:{api:{
  natural_status:async()=>({status:'ok',data:natural}),
  natural_approve:async(...a)=>{calls.push(['approve',...a]);return {status:'ok'};},
  natural_deny:async(...a)=>{calls.push(['deny',...a]);return {status:'ok'};},
  natural_refresh_permission:async(...a)=>{calls.push(['refresh',...a]);return {status:'ok'};}}}};
const button=(card,text)=>card.children.find(c=>c.tag==='button'&&c.textContent===text);
const texts=(card)=>card.children.map(c=>c.textContent).join(' | ');
const state=(pending,pause,status='awaiting_approval')=>({active:true,job:{status,conversation_id:'chat',pause},
  pending:{id:'r1',conversation_id:'chat',kind:'scope',operator:'codex',reason:'Not Defteri',targets:[{title:'Not'}],logs:[],...pending}});
''' + POLL


class PausedApprovalCardTests(unittest.TestCase):
    def run_card(self, cases):
        result = _node(CARD_HARNESS + "\n(async()=>{\n" + cases + "\n})().catch(e=>{console.error(e);process.exitCode=1});")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_paused_card_explains_the_pause_and_waits_for_cleanup(self):
        self.run_card(r'''
natural=state({},{reason:'scope',cleanup_confirmed:false});
await pollNaturalTask();
assert.equal(cards.length,1);
const card=cards[0];
assert.match(texts(card),/Görev duraklatıldı/);
assert.equal(button(card,'Bu görev için izin ver').disabled,true);
assert.match(texts(card),/temizlik doğrulanınca/);
// Cleanup confirmed: the card is replaced and approval becomes available.
natural=state({},{reason:'scope',cleanup_confirmed:true});
await pollNaturalTask();
assert.equal(cards.length,1);assert.notEqual(cards[0],card);
assert.equal(button(cards[0],'Bu görev için izin ver').disabled,false);
assert.deepEqual(calls,[]);
''')

    def test_full_permission_never_auto_approves_a_blocked_card(self):
        self.run_card(r'''
permission='full';
natural=state({},{reason:'scope',cleanup_confirmed:false});
await pollNaturalTask();
natural=state({expired:true},{reason:'permission_expired',cleanup_confirmed:true});
await pollNaturalTask();
assert.deepEqual(calls,[]);
natural=state({id:'r2'},{reason:'scope',cleanup_confirmed:true});
await pollNaturalTask();
assert.deepEqual(calls,[['approve','r2',true]]);
''')

    def test_expired_card_can_only_be_reissued_never_approved(self):
        self.run_card(r'''
natural=state({expired:true},{reason:'permission_expired',cleanup_confirmed:true});
await pollNaturalTask();
const card=cards[0];
assert.match(texts(card),/İzin süresi doldu/);
const approve=button(card,'Bu görev için izin ver');
assert.equal(approve.disabled,true);assert.equal(approve.hidden,true);
const refresh=button(card,'Yeniden onay hazırla');
natural=state({id:'r2',expired:false},{reason:'scope',cleanup_confirmed:true});
await refresh.onclick();
assert.deepEqual(calls,[['refresh','r1','chat',true]]);
assert.equal(cards.length,1);assert.equal(cards[0].dataset.naturalPermission,'r2');
''')

    def test_failed_reissue_is_reported_and_can_be_retried(self):
        self.run_card(r'''
natural=state({expired:true},{reason:'permission_expired',cleanup_confirmed:true});
await pollNaturalTask();
const card=cards[0];const refresh=button(card,'Yeniden onay hazırla');
window.pywebview.api.natural_refresh_permission=async()=>({status:'error',data:'Window changed'});
await refresh.onclick();
assert.match(texts(card),/Yeni onay hazırlanamadı: Window changed/);
assert.equal(refresh.disabled,false);assert.equal(cards.length,1);
''')

    def test_failed_approval_keeps_a_blocked_approve_button_disabled(self):
        self.run_card(r'''
natural=state({},{reason:'scope',cleanup_confirmed:false});
await pollNaturalTask();
const card=cards[0];const approve=button(card,'Bu görev için izin ver');
window.pywebview.api.natural_approve=async()=>({status:'error',data:'cleanup pending'});
await approve.onclick();
assert.equal(approve.disabled,true);
''')


class RefreshBridgeTests(unittest.TestCase):
    def test_reissue_requires_explicit_true_and_an_active_task(self):
        api = gui.Api.__new__(gui.Api)
        api._services = MagicMock()
        api._services.peek.return_value = None
        self.assertEqual(api.natural_refresh_permission("r1", "chat", True)["status"], "error")
        natural = MagicMock()
        api._services.peek.return_value = natural
        api.natural_refresh_permission("r1", "chat", "true")
        natural.refresh_permission.assert_called_with("r1", "chat", confirmed=False)
        api.natural_refresh_permission("r1", "chat", True)
        natural.refresh_permission.assert_called_with("r1", "chat", confirmed=True)

    def test_reissue_is_not_offered_to_model_tools(self):
        from core import desktop_mcp
        names = {tool["name"] for tool in desktop_mcp.TOOLS}
        self.assertFalse(any("refresh" in name or "permission" in name for name in names))


if __name__ == "__main__":
    unittest.main()
