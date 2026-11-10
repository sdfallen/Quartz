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
  'rpTests','rpSupport','rpExpected','rpPython','rpPythonList','rpMax','rpError','rpPreviewOut','rpPreviewBtn',
  'rpRegister','rpClose'];
const els={};for(const id of ids)els[id]=node(id);
els.rpProvider.value='codex';els.rpMax.value='2';els.rpRegister.disabled=true;
const document={getElementById:id=>els[id]||null,createElement:t=>node(t,{tag:t})};
const logs=[];const logLine=m=>logs.push(m);
let currentConvId='c1';
const calls=[];let previewReply,registerReply,clearReply={status:'ok',data:{}};
const window={pywebview:{api:{
  repair_plan_preview:async v=>{calls.push(['preview',v]);return previewReply;},
  repair_plan_register:async (id,c)=>{calls.push(['register',id,c]);return registerReply;},
  repair_plan_clear:async id=>{calls.push(['clear',id]);return clearReply;}}}};
const text=n=>(n.textContent||'')+(n.children||[]).map(text).join('');
const okPreview={status:'ok',data:{preview_id:'pv1',provider:'codex',model:'gpt-6.1',expected_tests:8,
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
currentConvId=null;els.rpExpected.value='8';await els.rpPreviewBtn.listeners.click();
assert.equal(calls.length,0);assert.match(els.rpError.textContent,/sohbet/);
''')

    def test_preview_sends_user_values_and_enables_register_only_after_success(self):
        self.assertJs(r'''
fill();previewReply=okPreview;
await els.rpPreviewBtn.listeners.click();
assert.deepEqual(calls[0],['preview',{conversation_id:'c1',provider:'codex',test_files:['tests/test_invoice.py'],
  support_files:['fixtures/expected.json'],expected_tests:8,python_executable:null,max_repairs:2}]);
assert.equal(els.rpRegister.disabled,false);assert.equal(els.rpPreviewOut.hidden,false);
const out=text(els.rpPreviewOut);
assert.match(out,/1 test dosyası, 1 destek dosyası/);assert.match(out,/aaaaaaaaaaaa/);assert.doesNotMatch(out,/a{13}/);
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
registerReply={status:'ok',data:{status:'ready',provider:'codex',files_count:1,support_count:1,expected_tests:8,max_repairs:2}};
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
renderRepairPlan({status:'running',provider:'antigravity',files_count:1,support_count:0,expected_tests:8,max_repairs:1});
assert.equal(els.repairChipText.textContent,'Onarım döngüsü çalışıyor');assert.equal(els.repairChipClear.hidden,true);
assert.equal(els.repairChipBadge.dataset.tone,'wait');
renderRepairPlan({status:'ready',provider:'antigravity',files_count:1,support_count:0,expected_tests:8,max_repairs:1});
assert.equal(els.repairChipClear.hidden,false);assert.match(els.repairChipText.textContent,/ajan Antigravity/);
await els.repairChipClear.listeners.click();
assert.deepEqual(calls.at(-1),['clear','c1']);assert.equal(els.repairChip.hidden,true);
renderRepairPlan(null);assert.equal(els.repairChip.hidden,true);
''')

    def test_host_text_is_never_html(self):
        self.assertJs(r'''
fill();previewReply={status:'ok',data:{...okPreview.data,warnings:['<img src=x onerror=alert(1)>'],
  files:[{path:'<b>x</b>.py',role:'test',sha256:'c'.repeat(64)}]}};
await els.rpPreviewBtn.listeners.click();
assert.match(text(els.rpPreviewOut),/<img src=x onerror=alert\(1\)>/);assert.match(text(els.rpPreviewOut),/<b>x<\/b>\.py/);
''')
        self.assertNotIn("innerHTML", PANEL)

    def test_shell_wiring_and_bridge_whitelist(self):
        for snippet in ('id="repairPlan"', 'aria-controls="repairPlan"', 'id="repairChip"', 'for="rpTests"'):
            self.assertIn(snippet, gui._HTML)
        self.assertIn("if ('repair_plan' in st.data) renderRepairPlan(st.data.repair_plan);", gui._HTML)
        self.assertIn("if ('repair_plan' in data) renderRepairPlan(data.repair_plan);", gui._HTML)
        api = gui.Api()
        with patch.object(gui, "ipc_send", return_value={"status": "ok", "data": {}}) as send:
            api.repair_plan_preview({"conversation_id": "c1", "provider": "evil", "test_files": ["a.py", 3, " "],
                                     "support_files": "x", "expected_tests": "8", "python_executable": "  ",
                                     "max_repairs": 9, "extra": "drop me"})
            api.repair_plan_register("pv1", "yes")
            api.repair_plan_register("pv1", True)
            api.repair_plan_clear("c1")
        self.assertEqual(send.call_args_list[0].args, ("repair_plan_preview", {
            "conversation_id": "c1", "provider": "codex", "test_files": ["a.py"], "support_files": [],
            "expected_tests": 0, "python_executable": None, "max_repairs": 2}))
        self.assertEqual(send.call_args_list[1].args, ("repair_plan_register", {"preview_id": "pv1", "confirm": False}))
        self.assertEqual(send.call_args_list[2].args, ("repair_plan_register", {"preview_id": "pv1", "confirm": True}))
        self.assertEqual(send.call_args_list[3].args, ("repair_plan_clear", {"conversation_id": "c1"}))
        with patch.object(gui, "ipc_send", side_effect=RuntimeError("down")):
            self.assertEqual(api.repair_plan_preview({})["status"], "error")


if __name__ == "__main__":
    unittest.main()
