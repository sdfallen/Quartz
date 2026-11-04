"""Modern UI layer: motion safety, Stop controls, honest agent surface, code blocks."""
import re
import subprocess
import unittest

import gui
from ui.theme import MODERN_CSS


def _js(source: str, start: str, end: str) -> str:
    return source[source.index(start):source.index(end)]


def _node(code: str):
    return subprocess.run(["node", "-e", code], capture_output=True, text=True, encoding="utf-8", timeout=15)


def _rules(css: str):
    """Flat (selector, body) pairs; good enough for this hand-written sheet."""
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)]


class MotionContractTests(unittest.TestCase):
    def test_keyframes_only_touch_opacity_and_transform(self):
        frames = re.findall(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", MODERN_CSS)
        self.assertTrue(frames)
        for name, body in frames:
            props = {p.split(":")[0].strip() for step in re.findall(r"\{([^{}]*)\}", body) for p in step.split(";") if ":" in p}
            self.assertLessEqual(props, {"opacity", "transform"}, name)

    def test_reduced_motion_and_low_spec_switch_everything_off(self):
        reduced = MODERN_CSS[MODERN_CSS.index("@media (prefers-reduced-motion: reduce)"):]
        self.assertRegex(reduced, r"\*,\*::before,\*::after \{ animation:none !important; transition:none !important;")
        self.assertIn("body.low-spec *,body.low-spec *::before,body.low-spec *::after { animation:none !important; transition:none !important; }",
                      MODERN_CSS)

    def test_animations_are_declared_only_for_motion_ok_and_not_low_spec(self):
        # A universal `* { animation:none }` cannot out-rank class selectors, so
        # every animation must be scoped instead of relying on being overridden.
        block_start = MODERN_CSS.index("@media (prefers-reduced-motion: no-preference) {")
        block_end = MODERN_CSS.index("\n}\n", block_start)
        uses = [m.start() for m in re.finditer(r"animation:q-", MODERN_CSS)]
        self.assertTrue(uses)
        for position in uses:
            self.assertTrue(block_start < position < block_end, MODERN_CSS[position - 80:position])
        for selector, body in _rules(MODERN_CSS[block_start:block_end].split("{", 1)[1]):
            if "animation:q-" in body:
                for part in selector.split(","):
                    self.assertIn(":not(.low-spec)", part, part)

    def test_stop_controls_never_animate_or_transition(self):
        stop_ids = ("#btnDesktopTaskStop", "#btnHudStopTask", "#btnDesktopStop", "#btnCancel")
        rule = next(body for sel, body in _rules(MODERN_CSS) if all(i in sel for i in stop_ids))
        self.assertIn("transition:none !important", rule)
        self.assertIn("animation:none !important", rule)
        for sel, body in _rules(MODERN_CSS):
            if any(i in sel for i in stop_ids):
                self.assertNotRegex(body, r"pointer-events\s*:\s*none", sel)

    def test_motion_never_disables_pointer_input(self):
        self.assertNotRegex(MODERN_CSS, r"pointer-events\s*:\s*none")

    def test_theme_is_offline(self):
        self.assertNotRegex(MODERN_CSS, r"@import|url\(|https?://|@font-face")

    def test_theme_is_the_last_stylesheet(self):
        head = gui._HTML[:gui._HTML.index("</head>")]
        self.assertTrue(head.endswith('<style id="quartz-modern-theme">' + MODERN_CSS + "</style>"))


class AgentSurfaceTests(unittest.TestCase):
    def test_notion_agent_controls_are_removed(self):
        for marker in ('agentSegNotion', 'value="notion"', 'notionAgentPill'):
            self.assertNotIn(marker, gui._HTML)

    def test_agent_handlers_only_bind_real_agents(self):
        for match in re.finditer(r"querySelectorAll\('\.agent-seg-btn([^']*)'\)", gui._HTML):
            self.assertEqual(match.group(1), "[data-agent]")

    def test_connection_list_reports_backend_state_and_active_agent(self):
        source = _js(gui._HTML, "  let agentConnectionView =", "  async function refreshCliStatus(")
        harness = r'''
const assert=require('node:assert/strict');
function node(){return {dataset:{},attrs:{},children:[],textContent:'',className:'',
 setAttribute(k,v){this.attrs[k]=v},append(...c){this.children.push(...c)},replaceChildren(){this.children=[]}};}
const box=node();
const document={getElementById:id=>id==='agentConnections'?box:null,createElement:node};
'''
        checks = r'''
const view=()=>box.children.map(r=>[r.dataset.agentId,r.dataset.state,r.children[2].textContent,r.attrs['aria-current']]);
renderAgentConnections();
assert.deepEqual(view().map(r=>r[1]),['unknown','unknown']);
renderAgentConnections({codex:{installed:true,ready:true},gemini:{installed:true,login_pending:true}},'collaboration');
assert.deepEqual(view(),[['codex','ready','Bağlı','true'],['antigravity','pending','Giriş bekleniyor','true']]);
renderAgentConnections(undefined,'codex');
assert.deepEqual(view().map(r=>r[3]),['true','false']);
renderAgentConnections({gemini:{installed:false}});
assert.deepEqual(view().map(r=>r[2]),['Bağlı değil','CLI kurulmamış']);
renderAgentConnections({notion:{installed:true,configured:true,checking:true}},'notion');
assert.equal(view().length,2);
renderAgentConnections({notion:{installed:true,configured:true,ready:true}},'notion');
assert.equal(view().length,2);
'''
        result = _node(harness + source + checks)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sync_agent_ui_updates_connection_highlight(self):
        source = re.search(r"  function syncAgentUI\(agent\) \{[\s\S]*?\n  \}\n", gui._HTML).group(0)
        self.assertIn("renderAgentConnections(undefined, agent);", source)


class MessageTextTests(unittest.TestCase):
    def run_js(self, checks):
        source = _js(gui._HTML, "  function appendMessageText(container, text)", "  function appendMsg(")
        harness = r'''
const assert=require('node:assert/strict');
function node(tag){return {tag,className:'',textContent:'',children:[],append(...c){this.children.push(...c)}};}
const document={createElement:node};
'''
        result = _node(harness + source + checks)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plain_text_is_unchanged(self):
        self.run_js(r'''
const box=node('div');appendMessageText(box,'Merhaba\n<b>kalın değil</b>');
assert.equal(box.textContent,'Merhaba\n<b>kalın değil</b>');assert.equal(box.children.length,0);
''')

    def test_fenced_code_becomes_code_panel_without_html(self):
        self.run_js(r'''
const box=node('div');
appendMessageText(box,'Önce\n```python\nprint("<x>")\n```\nSonra');
assert.deepEqual(box.children.map(c=>c.tag),['div','div','div']);
assert.equal(box.children[0].textContent,'Önce');
const code=box.children[1];assert.equal(code.className,'msg-code');
assert.equal(code.children[0].textContent,'python');
assert.equal(code.children[1].tag,'pre');assert.equal(code.children[1].textContent,'print("<x>")');
assert.equal(box.children[2].textContent,'Sonra');
''')

    def test_unterminated_fence_stays_text_and_bad_language_label_is_dropped(self):
        self.run_js(r'''
const box=node('div');appendMessageText(box,'a\n```bash\nls');
assert.equal(box.children.length,2);assert.equal(box.children[1].textContent,'```bash\nls');
const other=node('div');appendMessageText(other,'```<img src=x onerror=1>\nx\n```');
assert.equal(other.children[0].children.length,1);assert.equal(other.children[0].children[0].tag,'pre');
''')

    def test_message_text_never_uses_html_parsing(self):
        source = _js(gui._HTML, "  function appendMessageText(container, text)", "  let activeTaskSquad =")
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("insertAdjacentHTML", source)
        self.assertNotIn("window.open", source)

    def test_markdown_headings_lists_bold_italic_inline_code_and_link_text(self):
        self.run_js(r'''
const box=node('div');
appendMessageText(box,[
  '# Ana Başlık',
  '### Alt *Başlık*',
  'Normal **kalın**, *italik*, __ikinci kalın__, _ikinci italik_, `satır içi <kod>` ve [Belgeler](https://example.org/docs) metni.',
  '- Madde **bir**',
  '- Madde `iki`',
  '1. Sıralı bir',
  '2. Sıralı [bağlantı](https://example.org/item)'
].join('\n'));
assert.deepEqual(box.children.map(c=>c.tag),['h1','h3','p','ul','ol']);
assert.equal(box.children[0].className,'msg-heading msg-h1');
assert.equal(box.children[0].textContent,'Ana Başlık');
assert.equal(box.children[1].className,'msg-heading msg-h3');
assert.equal(box.children[1].children[1].tag,'em');
assert.equal(box.children[1].children[1].textContent,'Başlık');
const p=box.children[2];
assert.equal(p.className,'msg-p');
const tags=p.children.map(c=>c.tag);
assert(tags.includes('strong'));
assert(tags.includes('em'));
assert(tags.includes('code'));
const codeNode=p.children.find(c=>c.tag==='code');
assert.equal(codeNode.className,'msg-inline-code');
assert.equal(codeNode.textContent,'satır içi <kod>');
const linkNode=p.children.find(c=>c.className==='msg-link');
assert.equal(linkNode.tag,'span');
assert.equal(linkNode.textContent,'Belgeler');
assert.equal(linkNode.title,'https://example.org/docs');
assert.equal(linkNode.href,undefined);
const ul=box.children[3];
assert.equal(ul.className,'msg-list');
assert.equal(ul.children.length,2);
assert.equal(ul.children[0].tag,'li');
assert.equal(ul.children[0].children[1].tag,'strong');
assert.equal(ul.children[0].children[1].textContent,'bir');
const ol=box.children[4];
assert.equal(ol.className,'msg-list');
assert.equal(ol.children.length,2);
assert.equal(ol.children[1].children[1].className,'msg-link');
assert.equal(ol.children[1].children[1].textContent,'bağlantı');
''')


class ModalAndWindowControlTests(unittest.TestCase):
    def test_confirm_modal_requires_explicit_accept_and_restores_focus(self):
        source = _js(gui._HTML, "  let activeConfirmResolver =", "  function chatCleanupUnconfirmed(")
        code = r'''
const assert=require('node:assert/strict');
function makeEl(id){
  return {
    id, hidden:id==='confirmModal', textContent:'', onclick:null, isConnected:true,
    classes:new Set(),
    classList:{toggle(c,on){if(on)this.classes.add(c);else this.classes.delete(c);}},
    focus(){document.activeElement=this;}
  };
}
const trigger=makeEl('btnDeleteProjectChats');
const confirmModal=makeEl('confirmModal');
const confirmTitle=makeEl('confirmTitle');
const confirmMessage=makeEl('confirmMessage');
const confirmCancel=makeEl('confirmCancel');
const confirmAccept=makeEl('confirmAccept');
const confirmScrim=makeEl('confirmScrim');
confirmCancel.classList.classes=confirmCancel.classes;
confirmAccept.classList.classes=confirmAccept.classes;
const map={confirmModal,confirmTitle,confirmMessage,confirmCancel,confirmAccept,confirmScrim};
const document={activeElement:trigger,getElementById:id=>map[id]||null};
const window={};
''' + source + r'''
(async()=>{
  // Danger confirm focuses Cancel first; clicking Cancel resolves false and restores focus.
  const p1=requestUiConfirm('Silinsin mi?',{title:'Silme onayı',confirmLabel:'Sil',danger:true});
  assert.equal(confirmModal.hidden,false);
  assert.equal(confirmTitle.textContent,'Silme onayı');
  assert.equal(confirmMessage.textContent,'Silinsin mi?');
  assert.equal(document.activeElement,confirmCancel);
  assert.equal(confirmAccept.classes.has('danger'),true);
  confirmCancel.onclick();
  assert.equal(await p1,false);
  assert.equal(confirmModal.hidden,true);
  assert.equal(document.activeElement,trigger);

  // Clicking Accept resolves true and restores focus.
  const p2=requestUiConfirm('Yetki verilsin mi?',{title:'Yetki onayı',confirmLabel:'Yetki ver'});
  assert.equal(confirmModal.hidden,false);
  assert.equal(document.activeElement,confirmAccept);
  assert.equal(confirmAccept.classes.has('danger'),false);
  confirmAccept.onclick();
  assert.equal(await p2,true);
  assert.equal(confirmModal.hidden,true);
  assert.equal(document.activeElement,trigger);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = _node(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_modal_tab_focus_trap_and_overlay_focus_return(self):
        setup_slice = _js(gui._HTML, "  const modalReturnFocus = new Map();", "  function updateAntigravitySafety(")
        trap_slice = _js(gui._HTML, "  function isElementVisibleForFocus(el)", "  document.addEventListener('keydown', event => {")
        code = r'''
const assert=require('node:assert/strict');
function makeControl(id){
  return {
    id, disabled:false, hidden:false, isConnected:true,
    getClientRects:()=>[1], closest:()=>null,
    focus(){document.activeElement=this;}
  };
}
const opener=makeControl('btnAgentCenter');
const b1=makeControl('firstBtn');
const b2=makeControl('midInput');
const b3=makeControl('lastBtn');
const overlay={
  id:'agentOverlay', hidden:false,
  classes:new Set(),
  classList:{
    contains(c){return overlay.classes.has(c);},
    add(c){overlay.classes.add(c);},
    remove(c){overlay.classes.delete(c);}
  },
  getClientRects:()=>overlay.classes.has('show')?[1]:[],
  contains:el=>[b1,b2,b3].includes(el),
  querySelector:()=>b1,
  querySelectorAll:()=>[b1,b2,b3]
};
const confirmModal={id:'confirmModal',hidden:true,getClientRects:()=>[]};
const paletteLayer={id:'paletteLayer',hidden:true,getClientRects:()=>[]};
const document={
  activeElement:opener,
  getElementById:id=>({agentOverlay:overlay,agentPrompt:b2,confirmModal,paletteLayer})[id]||null,
  querySelectorAll:()=>overlay.classes.has('show')?[overlay]:[]
};
''' + setup_slice + trap_slice + r'''
openModalOverlay(overlay,'agentPrompt');
assert.equal(overlay.classes.has('show'),true);
assert.equal(document.activeElement,b2);

// Tab from last element wraps to first element.
document.activeElement=b3;
let prevented=false;
assert.equal(trapModalTabFocus({key:'Tab',shiftKey:false,preventDefault(){prevented=true;}}),true);
assert.equal(prevented,true);
assert.equal(document.activeElement,b1);

// Shift+Tab from first element wraps to last element.
prevented=false;
assert.equal(trapModalTabFocus({key:'Tab',shiftKey:true,preventDefault(){prevented=true;}}),true);
assert.equal(prevented,true);
assert.equal(document.activeElement,b3);

// Closing overlay restores focus to opener.
closeModalOverlay(overlay);
assert.equal(overlay.classes.has('show'),false);
assert.equal(document.activeElement,opener);
'''
        result = _node(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_window_maximize_button_updates_aria_and_icon(self):
        source = _js(gui._HTML, "  let windowMaximized = false;", "  if (btnWinMaximize) {")
        code = r'''
const assert=require('node:assert/strict');
const useEl={href:'#i-maximize',setAttribute(k,v){this[k]=v;}};
const maxBtn={
  attrs:{}, title:'',
  setAttribute(k,v){this.attrs[k]=v;},
  querySelector:()=>useEl
};
const bodyClasses=new Set();
const document={
  getElementById:id=>id==='btnWinMaximize'?maxBtn:null,
  body:{classList:{toggle(c,on){if(on)bodyClasses.add(c);else bodyClasses.delete(c);}}}
};
''' + source + r'''
syncWindowMaximizedUi(true);
assert.equal(maxBtn.attrs['aria-pressed'],'true');
assert.equal(maxBtn.attrs['aria-label'],'Önceki boyuta döndür');
assert.equal(useEl.href,'#i-restore');
assert.equal(bodyClasses.has('maximized'),true);

syncWindowMaximizedUi(false);
assert.equal(maxBtn.attrs['aria-pressed'],'false');
assert.equal(maxBtn.attrs['aria-label'],'Büyüt');
assert.equal(useEl.href,'#i-maximize');
assert.equal(bodyClasses.has('maximized'),false);
'''
        result = _node(code)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
