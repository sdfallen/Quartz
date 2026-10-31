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
    def test_notion_is_listed_but_not_selectable(self):
        button = re.search(r'<button[^>]*id="agentSegNotion"[^>]*>', gui._HTML).group(0)
        self.assertIn(" disabled", button)
        self.assertIn('aria-disabled="true"', button)
        self.assertNotIn("data-agent=", button)
        self.assertNotIn('data-agent="notion"', gui._HTML)
        self.assertNotIn("value=\"notion\"", gui._HTML)

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
assert.deepEqual(view().map(r=>r[1]),['unknown','unknown','missing']);
renderAgentConnections({codex:{installed:true,ready:true},gemini:{installed:true,login_pending:true}},'collaboration');
assert.deepEqual(view(),[['codex','ready','Bağlı','true'],['antigravity','pending','Giriş bekleniyor','true'],
  ['notion','missing','Bu sürümde bağlantı yok','false']]);
renderAgentConnections(undefined,'codex');
assert.deepEqual(view().map(r=>r[3]),['true','false','false']);
renderAgentConnections({gemini:{installed:false}});
assert.deepEqual(view().map(r=>r[2]),['Bağlı değil','CLI kurulmamış','Bu sürümde bağlantı yok']);
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
        source = _js(gui._HTML, "  function appendMessageText(container, text)", "  function appendMsg(")
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("insertAdjacentHTML", source)


if __name__ == "__main__":
    unittest.main()
