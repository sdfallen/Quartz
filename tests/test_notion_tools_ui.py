"""Notion local-tool status in the main chat (docs/notion-tools/PLAN.md).

Runs the shipped renderer (ui.document.NOTION_TOOLS_SCRIPT) in Node against a
small fake DOM. This is a mocked UI contract test, not a packaged Windows check.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import gui
from ui.document import DOCUMENT_HEAD, NOTION_TOOLS_SCRIPT, NOTION_TOOLS_SCRIPT_ID
from ui.theme import MODERN_CSS

FAKE_DOM = r"""
const assert = require('node:assert/strict');
const registry = new Map();
let clicks = 0;
function node(tag) {
  const n = {
    tagName: String(tag).toUpperCase(), className: '', children: [], parentNode: null, hidden: false,
    disabled: false, dataset: {}, attrs: {}, _text: '', _id: '',
    get id() { return this._id; }, set id(v) { this._id = v; registry.set(v, this); },
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k]; },
    append(...c) { for (const x of c) { x.parentNode = this; this.children.push(x); } },
    replaceChildren(...c) { this.children = []; this._text = ''; this.append(...c); },
    insertBefore(x, ref) { x.parentNode = this; const i = this.children.indexOf(ref);
      i < 0 ? this.children.push(x) : this.children.splice(i, 0, x); },
    get nextSibling() { const s = this.parentNode && this.parentNode.children; return s ? s[s.indexOf(this) + 1] || null : null; },
    click() { clicks++; },
  };
  return n;
}
const document = { getElementById: id => registry.get(id) || null, createElement: node };
const window = {};
const column = node('div');
const bar = node('div'); bar.id = 'desktopTaskBar'; column.append(bar);
const stop = node('button'); stop.id = 'btnDesktopTaskStop'; stop.hidden = true; stop.disabled = true;
function panel() { return document.getElementById('notionToolsPanel'); }
function all(n, pred, out = []) { if (pred(n)) out.push(n); n.children.forEach(c => all(c, pred, out)); return out; }
function title() { const t = all(panel(), n => n.className === 'notion-tools-title')[0]; return t ? t.textContent : null; }
function base(extra) { return Object.assign({schema_version: 1, availability: 'ready', capabilities: [], message: null, task: null}, extra || {}); }
function task(fields) { return base({task: Object.assign({task_id: 't1', session_id: 's1', revision: 1, state: 'observing',
  operator: 'notion', verification: 'none', message: ''}, fields)}); }
const ctx = {conversationId: 'c1', agent: 'notion'};
"""


def run_node(checks: str):
    code = FAKE_DOM + NOTION_TOOLS_SCRIPT + "\nconst Q = window.QuartzNotionTools;\n" + checks
    result = subprocess.run(["node", "-e", code], capture_output=True, text=True, encoding="utf-8", timeout=20)
    return result


class NotionToolsRendererTests(unittest.TestCase):
    def check(self, checks):
        result = run_node(checks)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_missing_or_unknown_payload_keeps_todays_chat(self):
        self.check(r"""
for (const p of [undefined, null, {}, {schema_version: 2, availability: 'ready'}, 'x']) {
  assert.equal(Q.update(p, ctx), 'hidden');
}
assert.equal(panel().hidden, true);
assert.equal(panel().parentNode, column); assert.equal(bar.nextSibling, panel());
""")

    def test_chat_only_other_agents_see_nothing_notion_sees_honest_state(self):
        self.check(r"""
assert.equal(Q.update(base({availability: 'unavailable'}), {conversationId: 'c1', agent: 'codex'}), 'hidden');
assert.equal(Q.update(base({availability: 'unavailable'}), {conversationId: 'c1', agent: 'antigravity'}), 'hidden');
assert.equal(panel().hidden, true);
assert.equal(Q.update(base({availability: 'unavailable'}), ctx), 'availability');
assert.equal(panel().hidden, false); assert.equal(title(), 'Yerel araçlar bağlı değil');
assert.match(panel().textContent, /bilgisayarınızda işlem yapamaz/);
assert.equal(Q.update(base({availability: 'checking'}), ctx), 'availability');
assert.equal(title(), 'Araç bağlantısı kontrol ediliyor');
Q.update(base({availability: 'nonsense'}), ctx);
assert.equal(panel().dataset.availability, 'unavailable');
""")

    def test_connection_error_is_shown_with_backend_message(self):
        self.check(r"""
Q.update(base({availability: 'blocked', message: 'Notion CLI oturumu sona erdi.'}), ctx);
assert.equal(title(), 'Araç bağlantısı engellendi');
assert.match(panel().textContent, /Notion CLI oturumu sona erdi\./);
assert.equal(panel().dataset.availability, 'blocked');
""")

    def test_awaiting_approval_points_to_existing_card_and_offers_no_controls(self):
        self.check(r"""
Q.update(task({state: 'awaiting_approval', request: {tool_name: 'read_file', scope_summary: 'Quartz · settings.py (salt okunur)'}}), ctx);
assert.equal(title(), 'İzin bekleniyor');
assert.match(panel().textContent, /İstenen kapsam: Quartz · settings\.py \(salt okunur\)\. Onay veya ret izin kartından verilir\./);
assert.equal(all(panel(), n => ['BUTTON', 'INPUT', 'A'].includes(n.tagName)).length, 0);
assert.equal(panel().dataset.state, 'awaiting_approval');
""")

    def test_approval_then_execution_and_denial_is_terminal(self):
        self.check(r"""
Q.update(task({state: 'awaiting_approval', revision: 1}), ctx);
assert.equal(Q.update(task({state: 'executing', revision: 2}), ctx), 'task');
assert.equal(title(), 'Yürütülüyor');
Q.update(task({task_id: 't2', state: 'awaiting_approval', revision: 1}), ctx);
assert.equal(Q.update(task({task_id: 't2', state: 'cancelled', revision: 2, message: 'İzin reddedildi.'}), ctx), 'task');
assert.equal(title(), 'İptal edildi');
// A denied/cancelled task must never look like it runs again.
assert.equal(Q.update(task({task_id: 't2', state: 'executing', revision: 9}), ctx), 'stale');
assert.equal(title(), 'İptal edildi');
""")

    def test_stop_uses_existing_strip_only_and_is_never_clicked_or_duplicated(self):
        self.check(r"""
Q.update(task({state: 'executing'}), ctx);
assert.match(panel().textContent, /durdurma yolu görünmüyor; yeni işlem başlatılmaz/);
stop.hidden = false; stop.disabled = false;
Q.update(task({state: 'executing', revision: 2}), ctx);
assert.match(panel().textContent, /görev şeridindeki Görevi durdur/);
assert.equal(all(panel(), n => n.tagName === 'BUTTON').length, 0);
assert.equal(clicks, 0);
Q.update(task({state: 'cancelled', revision: 3}), ctx);
assert.doesNotMatch(panel().textContent, /Görevi durdur/);
""")

    def test_duplicate_update_does_not_rerender(self):
        self.check(r"""
const p = task({state: 'executing', revision: 4});
assert.equal(Q.update(p, ctx), 'task');
const first = panel().children[0];
assert.equal(Q.update(JSON.parse(JSON.stringify(p)), ctx), 'stale');
assert.equal(panel().children[0], first);
const q = task({task_id: 'no-revision', state: 'executing'}); delete q.task.revision;
Q.reset(); Q.update(q, ctx); const again = panel().children[0];
assert.equal(Q.update(JSON.parse(JSON.stringify(q)), ctx), 'unchanged');
assert.equal(panel().children[0], again);
""")

    def test_late_events_from_old_or_older_revision_are_ignored(self):
        self.check(r"""
Q.update(task({task_id: 'old', state: 'executing', revision: 3}), ctx);
assert.equal(Q.update(task({task_id: 'old', state: 'observing', revision: 2}), ctx), 'stale');
assert.equal(Q.update(task({task_id: 'new', state: 'observing', revision: 1}), ctx), 'task');
assert.equal(Q.update(task({task_id: 'old', state: 'completed', verification: 'verified', revision: 7}), ctx), 'stale');
assert.equal(title(), 'Gözlem yapılıyor');
assert.match(panel().textContent, /"task_id": "new"/);
// Conversation switch: the old task must not leak into the new conversation.
Q.reset(); assert.equal(panel().hidden, true);
assert.equal(Q.update(task({task_id: 'new', state: 'executing', revision: 2}), ctx), 'stale');
assert.equal(Q.update(task({task_id: 'x', conversation_id: 'c9', state: 'executing'}), ctx), 'other-conversation');
assert.equal(panel().hidden, true);
""")

    def test_verified_only_from_backend_verification_field(self):
        self.check(r"""
Q.update(task({task_id: 'a', state: 'completed', message: 'Başardım, her şey doğrulandı ✓'}), ctx);
assert.equal(title(), 'Ajan tamamlandığını bildirdi · Quartz doğrulamadı');
assert.equal(panel().dataset.verification, 'unverified');
Q.update(task({task_id: 'b', state: 'completed', verification: 'observed'}), ctx);
assert.equal(title(), 'Tamamlandı · sonuç gözlendi, doğrulanmadı');
Q.update(task({task_id: 'c', state: 'completed', verification: 'VERIFIED'}), ctx);
assert.equal(panel().dataset.verification, 'unverified');
Q.update(task({task_id: 'd', state: 'completed', verification: 'verified'}), ctx);
assert.equal(title(), 'Tamamlandı ve doğrulandı'); assert.equal(panel().dataset.verification, 'verified');
Q.update(task({task_id: 'e', state: 'failed', verification: 'verified'}), ctx);
assert.equal(title(), 'Başarısız oldu'); assert.notEqual(panel().dataset.verification, 'verified');
""")

    def test_operator_and_delegation_are_explicit(self):
        self.check(r"""
Q.update(task({task_id: 'a', operator: 'notion'}), ctx);
assert.match(panel().textContent, /Yürüten: Notion(?! ·)/);
Q.update(task({task_id: 'b', operator: 'codex'}), ctx);
assert.match(panel().textContent, /Yürüten: Codex · Notion bu işi devretti/);
Q.update(task({task_id: 'c', operator: 'antigravity'}), ctx);
assert.match(panel().textContent, /Yürüten: Antigravity · Notion bu işi devretti/);
Q.update(task({task_id: 'd', operator: 'squad'}), ctx);
assert.match(panel().textContent, /Yürüten: belirtilmedi/);
""")

    def test_untrusted_text_is_never_markup(self):
        self.check(r"""
const evil = '<img src=x onerror=alert(1)><script>alert(2)</scr' + 'ipt>';
Q.update(task({task_id: '<b>id</b>', state: '<i>x</i>', operator: evil, message: evil,
  request: {scope_summary: evil}}), ctx);
assert.equal(title(), 'Durum bilinmiyor'); assert.equal(panel().dataset.state, 'unknown');
assert.ok(panel().textContent.includes('<img src=x onerror=alert(1)>'));
assert.equal(all(panel(), n => ['IMG', 'SCRIPT'].includes(n.tagName)).length, 0);
Q.update(task({task_id: 'long', message: 'a'.repeat(5000)}), ctx);
assert.ok(panel().textContent.length < 2000);
""")

    def test_renderer_source_has_no_html_parsing_or_api_access(self):
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "Function(",
                          "pywebview", ".click(", "fetch(", "XMLHttpRequest"):
            self.assertNotIn(forbidden, NOTION_TOOLS_SCRIPT, forbidden)


class DocumentAndRegressionTests(unittest.TestCase):
    def test_renderer_ships_in_head_without_breaking_application_script_contract(self):
        html = gui._HTML
        tag = '<script id="%s">' % NOTION_TOOLS_SCRIPT_ID
        self.assertEqual(html.count(tag), 1)
        self.assertIn(tag + NOTION_TOOLS_SCRIPT + "</script>\n", DOCUMENT_HEAD)
        self.assertTrue(html.startswith(DOCUMENT_HEAD))
        self.assertLess(html.index(tag), html.index("</head>"), "defined before gui.py's script uses it")
        # check_gui_javascript.py and frontend tests still see exactly gui.py's block(s).
        source = (Path(gui.__file__).resolve()).read_text(encoding="utf-8")
        block = re.compile(r"<script>(.*?)</script>", re.S)
        self.assertEqual(block.findall(source), block.findall(html))
        self.assertNotIn("<script", NOTION_TOOLS_SCRIPT.lower())

    def test_all_shipped_scripts_parse_together(self):
        scripts = re.findall(r"<script(?: id=\"[\w-]+\")?>(.*?)</script>", gui._HTML, re.S)
        self.assertEqual(len(scripts), 2)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
            handle.write("\n;\n".join(scripts))
        result = subprocess.run(["node", "--check", handle.name], capture_output=True, text=True, timeout=20)
        Path(handle.name).unlink()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_codex_and_antigravity_surfaces_are_untouched(self):
        html = gui._HTML
        for marker in ('data-agent="codex"', 'data-agent="antigravity"', 'data-agent="collaboration"',
                       'id="codexModelPill"', 'id="agyModelPill"', "function renderAgentConnections(",
                       "function syncAgentUI(agent)", 'id="btnDesktopTaskStop"', 'id="btnHudStopTask"'):
            self.assertIn(marker, html)
        for match in re.finditer(r"querySelectorAll\('\.agent-seg-btn([^']*)'\)", html):
            self.assertEqual(match.group(1), "[data-agent]")
        self.assertNotIn("notionToolsPanel", (Path(gui.__file__).resolve()).read_text(encoding="utf-8"))

    def test_motion_is_reduced_motion_and_eco_safe(self):
        block_start = MODERN_CSS.index("@media (prefers-reduced-motion: no-preference) {")
        block_end = MODERN_CSS.index("\n}\n", block_start)
        panel_animations = [m.start() for m in re.finditer(r"\.notion-tools[^{]*\{ animation:", MODERN_CSS)]
        self.assertTrue(panel_animations)
        for position in panel_animations:
            self.assertTrue(block_start < position < block_end)
            line = MODERN_CSS[MODERN_CSS.rindex("\n", 0, position):position]
            self.assertIn(":not(.low-spec)", line)
        self.assertNotRegex(MODERN_CSS, r"pointer-events\s*:\s*none")
        stop_rule = MODERN_CSS[MODERN_CSS.index("#btnDesktopTaskStop,#btnHudStopTask"):]
        self.assertIn("transition:none !important; animation:none !important;", stop_rule.split("}", 1)[0])


if __name__ == "__main__":
    unittest.main()
