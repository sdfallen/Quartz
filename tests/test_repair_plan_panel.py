"""Repair plan panel (docs/INTEGRATION_REQUEST_REPAIR_PLAN_UI_20261110.md).

Runs the shipped panel code in Node with a minimal DOM. The host previews, registers and decides;
the panel only collects user values, requires a matching preview and never renders host text as HTML.
"""
import unittest
import subprocess
from unittest.mock import patch

import gui
from ui.js_repair_plan import JAVASCRIPT as PANEL

HARNESS = r'''
const assert=require('node:assert/strict');
const node=(id,extra={})=>Object.assign({id,hidden:true,dataset:{},attrs:{},textContent:'',value:'',disabled:false,
  children:[],listeners:{},title:'',className:'',
  setAttribute(k,v){this.attrs[k]=String(v)},append(...c){this.children.push(...c)},
  replaceChildren(...c){this.children=c},addEventListener(t,f){this.listeners[t]=f},focus(){}},extra);
const ids=['repairPlan','btnRepairPlan','repairChip','repairChipText','repairChipClear','repairChipBadge','rpProvider',
  'rpTests','rpSupport','rpExpected','rpPython','rpSitePackages','rpPythonList','rpMax','rpError','rpPreviewOut','rpPreviewBtn',
  'rpRegister','rpClose'];
const els={};for(const id of ids)els[id]=node(id);
els.rpProvider.value='codex';els.rpMax.value='2';els.rpRegister.disabled=true;
const document={getElementById:id=>els[id]||null,createElement:t=>node(t,{tag:t})};
const logs=[];const logLine=m=>logs.push(m);
let currentConvId='c1';const mainAgentSelect={value:'codex'};
const calls=[];let previewReply,registerReply,clearReply={status:'ok',data:{}};
const window={pywebview:{api:{
  repair_plan_preview:async v=>{calls.push(['preview',v]);return previewReply;},
  repair_plan_register:async (id,c)=>{calls.push(['register',id,c]);return registerReply;},
  repair_plan_clear:async id=>{calls.push(['clear',id]);return clearReply;}}}};
const text=n=>(n.textContent||'')+(n.children||[]).map(text).join('');
const okPreview={status:'ok',data:{preview_id:'pv1',conversation_id:'c1',provider:'codex',model:{model:'gpt-6.1',effort:'medium'},expected_tests:8,
  python_executable:'C:\\Python313\\python.exe',python_candidates:['C:\\Python313\\python.exe'],warnings:[],
  files:[{path:'tests/test_invoice.py',role:'test',sha256:'a'.repeat(64)},{path:'fixtures/expected.json',role:'support',sha256:'b'.repeat(64)}]}};
function fill(){els.rpTests.value='tests/test_invoice.py\n';els.rpSupport.value=' fixtures/expected.json ';els.rpExpected.value='8';}
'''


def run(checks):
    return subprocess.run(["node", "-"], input=HARNESS + PANEL + "\n(async()=>{" + checks +
                          "})().catch(e=>{console.error(e);process.exitCode=1;});",
                          capture_output=True, text=True, encoding="utf-8", timeout=30)


class RepairPlanPanelTests(unittest.TestCase):
    def assertJs(self, checks):
        result = run(checks)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_validation_blocks_preview_without_tests_or_count(self):
        self.assertJs(r'''
await els.rpPreviewBtn.listeners.click();
assert.equal(calls.length,0);assert.match(els.rpError.textContent,/test dosyası/);assert.equal(els.rpError.hidden,false);
els.rpTests.value='tests/test_invoice.py';await els.rpPreviewBtn.listeners.click();
assert.equal(calls.length,0);assert.match(els.rpError.textContent,/test sayısı/);
els.rpExpected.value='8';mainAgentSelect.value='collaboration';await els.rpPreviewBtn.listeners.click();
assert.equal(calls.length,0);assert.match(els.rpError.textContent,/tek ajanla/);
mainAgentSelect.value='antigravity';els.btnRepairPlan.listeners.click();assert.equal(els.rpProvider.value,'antigravity');
currentConvId=null;await els.rpPreviewBtn.listeners.click();
assert.equal(calls.length,0);assert.match(els.rpError.textContent,/sohbet/);
''')

    def test_preview_sends_user_values_and_enables_register_only_after_success(self):
        self.assertJs(r'''
fill();previewReply=okPreview;
await els.rpPreviewBtn.listeners.click();
assert.deepEqual(calls[0],['preview',{conversation_id:'c1',provider:'codex',test_files:['tests/test_invoice.py'],
  support_files:['fixtures/expected.json'],expected_tests:8,python_executable:null,max_repairs:2,python_site_packages:null}]);
assert.equal(els.rpRegister.disabled,false);assert.equal(els.rpPreviewOut.hidden,false);
const out=text(els.rpPreviewOut);
assert.match(out,/1 test dosyası, 1 destek dosyası/);assert.match(out,/\(gpt-6\.1 · medium\)/);assert.match(out,/aaaaaaaaaaaa/);assert.doesNotMatch(out,/a{13}/);
assert.match(out,/hiçbir kod çalıştırmadı/);assert.equal(els.rpPython.value,'C:\\Python313\\python.exe');
assert.equal(els.rpPreviewBtn.disabled,false);assert.equal(els.rpPreviewBtn.textContent,'Önizle');
''')

    def test_host_error_is_shown_and_register_stays_disabled(self):
        self.assertJs(r'''
fill();previewReply={status:'error',data:'Korumalı projede onarım planı kurulamaz.'};
await els.rpPreviewBtn.listeners.click();
assert.equal(els.rpRegister.disabled,true);assert.equal(els.rpError.textContent,'Korumalı projede onarım planı kurulamaz.');
''')

    def test_editing_after_preview_invalidates_it(self):
        self.assertJs(r'''
fill();previewReply=okPreview;await els.rpPreviewBtn.listeners.click();
assert.equal(els.rpRegister.disabled,false);
els.rpExpected.value='3';els.rpExpected.listeners.input();
assert.equal(els.rpRegister.disabled,true);assert.equal(els.rpPreviewOut.hidden,true);
await els.rpRegister.listeners.click();
assert.equal(calls.filter(c=>c[0]==='register').length,0);
''')

    def test_register_sends_preview_id_with_confirm_and_shows_chip(self):
        self.assertJs(r'''
fill();previewReply=okPreview;await els.rpPreviewBtn.listeners.click();
els.repairPlan.hidden=false;
registerReply={status:'ok',data:{status:'ready',provider:'codex',files_count:2,support_count:1,expected_tests:8,max_repairs:2}};
await els.rpRegister.listeners.click();
assert.deepEqual(calls.at(-1),['register','pv1',true]);
assert.equal(els.repairChip.hidden,false);assert.equal(els.repairPlan.hidden,true);
assert.equal(els.repairChipText.textContent,'Onarım planı hazır — en az 8 test · 2 dosya · en çok 2 onarım · ajan Codex');
assert.equal(els.repairChipBadge.dataset.tone,'ok');assert.equal(els.rpRegister.disabled,true);
''')

    def test_register_failure_requires_a_new_preview(self):
        self.assertJs(r'''
fill();previewReply=okPreview;await els.rpPreviewBtn.listeners.click();
registerReply={status:'error',data:'Test dosyaları önizlemeden sonra değişti.'};
await els.rpRegister.listeners.click();
assert.match(els.rpError.textContent,/değişti/);assert.equal(els.rpRegister.disabled,true);assert.equal(els.repairChip.hidden,true);
''')

    def test_chip_follows_host_state_and_clear(self):
        self.assertJs(r'''
renderRepairPlanChip({status:'running',provider:'antigravity',files_count:1,support_count:0,expected_tests:8,max_repairs:1},'c1');
assert.equal(els.repairChipText.textContent,'Onarım döngüsü çalışıyor');assert.equal(els.repairChipClear.hidden,true);
assert.equal(els.repairChipBadge.dataset.tone,'wait');
renderRepairPlanChip({status:'ready',provider:'antigravity',files_count:3,support_count:2,expected_tests:8,max_repairs:1},'c1');
assert.equal(els.repairChipClear.hidden,false);assert.match(els.repairChipText.textContent,/ajan Antigravity/);
assert.match(els.repairChipText.textContent,/ 3 dosya /);  // files_count is already the total
clearReply={status:'ok',data:null};
await els.repairChipClear.listeners.click();
assert.deepEqual(calls.at(-1),['clear','c1']);assert.equal(els.repairChip.hidden,true);
renderRepairPlanChip(null,'c1');assert.equal(els.repairChip.hidden,true);
''')

    def test_host_text_is_never_html(self):
        self.assertJs(r'''
fill();previewReply={status:'ok',data:{...okPreview.data,warnings:['<img src=x onerror=alert(1)>'],
  files:[{path:'<b>x</b>.py',role:'test',sha256:'c'.repeat(64)}]}};
await els.rpPreviewBtn.listeners.click();
assert.match(text(els.rpPreviewOut),/<img src=x onerror=alert\(1\)>/);assert.match(text(els.rpPreviewOut),/<b>x<\/b>\.py/);
''')
        self.assertNotIn("innerHTML", PANEL)

    # Codex review 10 Nov (P2-1): a late answer must not paint or clear another conversation.
    def test_late_register_answer_does_not_paint_another_conversation(self):
        self.assertJs(r'''
fill();previewReply=okPreview;await els.rpPreviewBtn.listeners.click();
let release;registerReply=new Promise(r=>{release=r;});
const pending=els.rpRegister.listeners.click();
currentConvId='c2';renderRepairPlanChip(null,'c2');
release({status:'ok',data:{status:'ready',provider:'codex',files_count:2,support_count:1,expected_tests:8,max_repairs:2}});
await pending;
assert.equal(els.repairChip.hidden,true);assert.match(els.rpError.textContent,/yeniden önizleyin/);  // poll retired it, reply ignored
release=null;currentConvId='c1';fill();await els.rpPreviewBtn.listeners.click();
registerReply=new Promise(r=>{release=r;});const p2=els.rpRegister.listeners.click();
currentConvId='c2';release({status:'error',data:'eski hata'});await p2;
assert.equal(els.rpError.textContent,'');
''')

    # Gemini review 10 Nov (P2-1): the context is checked BEFORE the register IPC, not only after.
    def test_register_refuses_a_preview_from_another_conversation_or_agent(self):
        self.assertJs(r'''
fill();previewReply=okPreview;await els.rpPreviewBtn.listeners.click();
currentConvId='c2';await els.rpRegister.listeners.click();
assert.equal(calls.filter(c=>c[0]==='register').length,0);assert.equal(els.rpRegister.disabled,true);
assert.match(els.rpError.textContent,/Sohbet veya ajan değişti/);
currentConvId='c1';await els.rpPreviewBtn.listeners.click();assert.equal(els.rpRegister.disabled,false);
mainAgentSelect.value='antigravity';await els.rpRegister.listeners.click();
assert.equal(calls.filter(c=>c[0]==='register').length,0);
mainAgentSelect.value='codex';await els.rpPreviewBtn.listeners.click();
mainAgentSelect.value='collaboration';renderRepairPlanChip(null,'c1');  // a poll after the switch
assert.equal(els.rpRegister.disabled,true);assert.equal(els.rpPreviewOut.hidden,true);
''')

    def test_open_panel_follows_the_agent_on_each_poll(self):
        self.assertJs(r'''
els.btnRepairPlan.listeners.click();assert.equal(els.rpProvider.value,'codex');
mainAgentSelect.value='antigravity';renderRepairPlanChip(null,'c1');assert.equal(els.rpProvider.value,'antigravity');
''')

    # Live gate 3 (11 Nov): the chip said "hazır" for the whole turn.
    def test_chip_shows_running_during_a_turn_and_host_status_wins_after(self):
        self.assertJs(r'''
const ready={status:'ready',provider:'antigravity',files_count:2,support_count:1,expected_tests:8,max_repairs:2};
markRepairPlanRunning(true);assert.equal(els.repairChip.hidden,true);  // no plan: nothing to show
renderRepairPlanChip(ready,'c1');markRepairPlanRunning(true);
assert.equal(els.repairChipText.textContent,'Onarım döngüsü çalışıyor');assert.equal(els.repairChipClear.hidden,true);
assert.equal(els.repairChipBadge.dataset.tone,'wait');
renderRepairPlanChip(ready,'c1');assert.match(els.repairChipText.textContent,/hazır/);  // same host data repaints
renderRepairPlanChip(null,'c1');assert.equal(els.repairChip.hidden,true);
renderRepairPlanChip(ready,'c1');currentConvId='c2';markRepairPlanRunning(true);
assert.match(els.repairChipText.textContent,/hazır/);  // another conversation's turn
''')
        self.assertIn("if (typeof markRepairPlanRunning === 'function') markRepairPlanRunning(!!v);", gui._HTML)

    def test_panel_is_opaque_and_scrolls_with_sticky_actions(self):
        from pathlib import Path
        css = (Path(__file__).resolve().parents[1] / "assets" / "workspace.css").read_text(encoding="utf-8")
        block = css[css.index(".repair-plan {"):css.index(".repair-plan-head")]
        self.assertIn("overflow-y: auto", block)
        self.assertIn("max-height:", block)
        self.assertNotIn("transparent)", block.split("--rp-bg:")[1].split(";")[0])
        actions = css[css.index(".rp-actions {"):]
        self.assertIn("position: sticky", actions.split("}")[0])

    def test_late_preview_and_clear_answers_stay_in_their_conversation(self):
        self.assertJs(r'''
fill();let release;previewReply=new Promise(r=>{release=r;});
const pending=els.rpPreviewBtn.listeners.click();currentConvId='c2';release(okPreview);await pending;
assert.equal(els.rpRegister.disabled,true);assert.equal(els.rpPreviewOut.hidden,true);
currentConvId='c1';
renderRepairPlanChip({status:'ready',provider:'codex',files_count:1,support_count:0,expected_tests:8,max_repairs:2},'c1');
currentConvId='c2';await els.repairChipClear.listeners.click();
assert.equal(calls.filter(c=>c[0]==='clear').length,0);  // chip is c1's, the user is on c2
currentConvId='c1';clearReply=new Promise(r=>{release=r;});const p=els.repairChipClear.listeners.click();
renderRepairPlanChip({status:'ready',provider:'codex',files_count:1,support_count:0,expected_tests:9,max_repairs:2},'c3');
release({status:'ok',data:null});await p;
assert.deepEqual(calls.at(-1),['clear','c1']);assert.equal(els.repairChip.hidden,false);  // c3's chip survives
''')

    # Codex review 10 Nov (P2-2): counts are whole numbers or refused, never rounded.
    def test_count_must_be_a_plain_whole_number(self):
        self.assertJs(r'''
fill();previewReply=okPreview;
for(const bad of ['1e2','1.9','-3','8x','0','100001',' ']){
  els.rpExpected.value=bad;await els.rpPreviewBtn.listeners.click();
  assert.match(els.rpError.textContent,/tam sayı/,bad);
}
els.rpExpected.value='8';els.rpMax.value='2.5';await els.rpPreviewBtn.listeners.click();
assert.match(els.rpError.textContent,/1, 2 veya 3/);
assert.equal(calls.length,0);
els.rpMax.value='3';els.rpExpected.value=' 12 ';await els.rpPreviewBtn.listeners.click();
assert.equal(calls[0][1].expected_tests,12);assert.equal(calls[0][1].max_repairs,3);
''')

    # Gate 4 (11 Nov): isolated host tests can use a user-approved dependency folder.
    def test_dependency_folder_is_sent_shown_and_invalidates_the_preview(self):
        self.assertJs(r'''
fill();els.rpSitePackages.value='  C:\\venv\\Lib\\site-packages  ';
previewReply={status:'ok',data:{...okPreview.data,python_site_packages:'C:\\venv\\Lib\\site-packages'}};
await els.rpPreviewBtn.listeners.click();
assert.equal(calls[0][1].python_site_packages,'C:\\venv\\Lib\\site-packages');
assert.match(text(els.rpPreviewOut),/Bağımlılık klasörü: C:\\venv\\Lib\\site-packages/);
assert.equal(els.rpRegister.disabled,false);
els.rpSitePackages.value='D:\\other';els.rpSitePackages.listeners.input();
assert.equal(els.rpRegister.disabled,true);
els.rpSitePackages.value='   ';await els.rpPreviewBtn.listeners.click();
assert.equal(calls.at(-1)[1].python_site_packages,null);
''')
        self.assertIn('id="rpSitePackages"', gui._HTML)
        self.assertIn('for="rpSitePackages"', gui._HTML)

    def test_shell_wiring(self):
        for snippet in ('id="repairPlan"', 'aria-controls="repairPlan"', 'id="repairChip"', 'for="rpTests"'):
            self.assertIn(snippet, gui._HTML)
        self.assertIn("if ('repair_plan' in st.data) renderRepairPlanChip(st.data.repair_plan, st.data.active_conversation?.id);",
                      gui._HTML)
        self.assertIn("if ('repair_plan' in data) renderRepairPlanChip(data.repair_plan, data.active_conversation?.id);",
                      gui._HTML)

    def test_bridge_sends_only_valid_whitelisted_fields(self):
        api = gui.Api()
        good = {"conversation_id": "c1", "provider": "antigravity", "test_files": [" a.py ", ""],
                "support_files": ["  ", "fx.json"], "expected_tests": 8, "python_executable": "  ",
                "max_repairs": 3, "python_site_packages": " C:\\venv\\Lib\\site-packages ", "extra": "drop me"}
        with patch.object(gui, "ipc_send", return_value={"status": "ok", "data": {}}) as send:
            api.repair_plan_preview(good)
            api.repair_plan_preview({k: v for k, v in good.items() if k != "support_files"})
            api.repair_plan_register("pv1", "yes")
            api.repair_plan_register("pv1", True)
            api.repair_plan_clear("c1")
        self.assertEqual(send.call_args_list[0].args, ("repair_plan_preview", {
            "conversation_id": "c1", "provider": "antigravity", "test_files": ["a.py"], "support_files": ["fx.json"],
            "expected_tests": 8, "python_executable": None, "max_repairs": 3,
            "python_site_packages": "C:\\venv\\Lib\\site-packages"}))
        self.assertEqual(send.call_args_list[1].args[1]["support_files"], [])  # omitted optional list
        self.assertEqual(send.call_args_list[2].args, ("repair_plan_register", {"preview_id": "pv1", "confirm": False}))
        self.assertEqual(send.call_args_list[3].args, ("repair_plan_register", {"preview_id": "pv1", "confirm": True}))
        self.assertEqual(send.call_args_list[4].args, ("repair_plan_clear", {"conversation_id": "c1"}))
        with patch.object(gui, "ipc_send", side_effect=RuntimeError("down")):
            self.assertEqual(api.repair_plan_preview(good)["status"], "error")

    # Codex review 10 Nov (P2-3): malformed input is refused before IPC, not turned into another plan.
    def test_bridge_fails_closed_without_ipc(self):
        api = gui.Api()
        good = {"conversation_id": "c1", "provider": "codex", "test_files": ["a.py"], "support_files": [],
                "expected_tests": 8, "python_executable": None, "max_repairs": 2}
        bad = [None, "x", {**good, "provider": "evil"}, {**good, "conversation_id": ""},
               {**good, "test_files": []}, {**good, "test_files": ["a.py", 3]}, {**good, "test_files": "a.py"},
               {**good, "support_files": "x"}, {**good, "support_files": [f"s{i}.json" for i in range(65)]},
               {**good, "support_files": ["ok.json", None]}, {**good, "expected_tests": "8"},
               {**good, "expected_tests": True}, {**good, "expected_tests": 0}, {**good, "expected_tests": 1.5},
               {**good, "max_repairs": 9}, {**good, "python_executable": 5},
               {**good, "python_site_packages": 5}, {**good, "python_site_packages": ["C:/x"]}]
        with patch.object(gui, "ipc_send") as send:
            for values in bad:
                result = api.repair_plan_preview(values)
                self.assertEqual(result["status"], "error", values)
                self.assertIsInstance(result["data"], str)
            self.assertEqual(api.repair_plan_register("", True)["status"], "error")
            self.assertEqual(api.repair_plan_register(None, True)["status"], "error")
            self.assertEqual(api.repair_plan_clear(None)["status"], "error")
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
