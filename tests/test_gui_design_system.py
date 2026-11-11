"""New shell: readable colours, kept preferences, safe palette, working shortcuts."""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gui
from core import ui_preferences, ui_window
from ui.js_workspace import JAVASCRIPT as WORKSPACE
from ui.shell import SHELL_MARKUP
from ui.theme import MODERN_CSS
from ui.styles import BASE_CSS, _LIGHT_CRYSTALS, _LIGHT_TOKENS

ROOT = Path(__file__).resolve().parents[1]


def _luminance(colour):
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + .05) / (low + .05)


def _tokens(css):
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b", css))


DARK = _tokens(BASE_CSS[:BASE_CSS.index('[data-crystal="rose"]')])
LIGHT = {**DARK, **_tokens(_LIGHT_TOKENS)}


class ContrastTests(unittest.TestCase):
    def assert_readable(self, tokens, label):
        for surface in ("bg", "surface-1", "surface-2"):
            for text in ("text", "text-2", "text-3"):
                self.assertGreaterEqual(_contrast(tokens[text], tokens[surface]), 4.5, f"{label} {text} on {surface}")
        self.assertGreaterEqual(_contrast(tokens["text"], tokens["surface-3"]), 4.5, label)
        self.assertGreaterEqual(_contrast(tokens["on-accent"], tokens["accent"]), 4.5, f"{label} on-accent")
        self.assertGreaterEqual(_contrast(tokens["accent"], tokens["surface-1"]), 3, f"{label} accent")
        for state in ("ok", "warn", "danger"):
            self.assertGreaterEqual(_contrast(tokens[state], tokens["surface-1"]), 4.5, f"{label} {state}")

    def test_dark_and_light_text_pairs_meet_aa(self):
        self.assert_readable(DARK, "dark")
        self.assert_readable(LIGHT, "light")

    def test_every_crystal_keeps_accent_text_readable(self):
        dark_rules = re.findall(r':root\[data-crystal="(\w+)"\] \{ --accent:(#\w+);.*?--on-accent:(#\w+);', BASE_CSS)
        light_rules = re.findall(r'\[data-crystal="(\w+)"\] \{\{ --accent:(#\w+);.*?--on-accent:(#\w+);', _LIGHT_CRYSTALS)
        self.assertEqual({r[0] for r in dark_rules}, {"rose", "citrine", "amethyst", "smoky"})
        self.assertEqual({r[0] for r in light_rules}, {"rose", "citrine", "amethyst", "smoky"})
        for rules, surface in ((dark_rules, DARK["surface-1"]), (light_rules, LIGHT["surface-1"])):
            for name, accent, on_accent in rules:
                self.assertGreaterEqual(_contrast(on_accent, accent), 4.5, name)
                self.assertGreaterEqual(_contrast(accent, surface), 3, name)

    def test_stop_button_is_readable_in_both_themes(self):
        self.assertGreaterEqual(_contrast(DARK["on-stop"], DARK["stop"]), 4.5)
        self.assertGreaterEqual(_contrast(DARK["on-stop"], DARK["stop-hover"]), 3)

    def test_components_use_tokens_not_raw_colours(self):
        css = (ROOT / "assets" / "workspace.css").read_text(encoding="utf-8")
        swatches = [line for line in css.splitlines() if ".swatches [data-value" in line]
        self.assertEqual(len(swatches), 4)
        rest = "\n".join(line for line in css.splitlines() if ".swatches [data-value" not in line)
        self.assertNotRegex(rest.replace("#000 14px", ""), r"#[0-9a-fA-F]{6}\b")


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "nested" / "ui.json"

    def test_defaults_when_missing_or_damaged(self):
        self.assertEqual(ui_preferences.load_ui_preferences(self.path), ui_preferences.DEFAULTS)
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(ui_preferences.load_ui_preferences(self.path), ui_preferences.DEFAULTS)
        self.path.write_text(json.dumps({"theme": "<script>", "crystal": "rose"}), encoding="utf-8")
        self.assertEqual(ui_preferences.load_ui_preferences(self.path)["theme"], "dark")

    def test_saved_value_round_trips_and_reaches_first_paint(self):
        ui_preferences.save_ui_preference("theme", "light", self.path)
        ui_preferences.save_ui_preference("crystal", "amethyst", self.path)
        self.assertEqual(ui_preferences.load_ui_preferences(self.path), {"theme": "light", "crystal": "amethyst"})
        html = ui_preferences.apply_to_document(gui._HTML, self.path)
        self.assertIn('<html lang="tr" data-theme="light" data-crystal="amethyst">', html)
        self.assertEqual(ui_preferences.window_background(self.path), "#f7f3fd")

    def test_simultaneous_saves_keep_both_values(self):
        import threading
        for _ in range(20):
            start = threading.Barrier(2)
            def save(key, value):
                start.wait()
                ui_preferences.save_ui_preference(key, value, self.path)
            threads = [threading.Thread(target=save, args=args) for args in (("theme", "light"), ("crystal", "amethyst"))]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(ui_preferences.load_ui_preferences(self.path), {"theme": "light", "crystal": "amethyst"})
            self.path.unlink()

    def test_unknown_keys_and_values_are_refused(self):
        for key, value in (("theme", "neon"), ("crystal", "ruby"), ("permission_level", "full")):
            with self.assertRaises(ValueError):
                ui_preferences.save_ui_preference(key, value, self.path)
        self.assertFalse(self.path.exists())

    def test_api_reports_refusal_instead_of_raising(self):
        result = gui.Api.ui_set_preference(None, "theme", "neon")
        self.assertEqual(result["status"], "error")


class WindowPlacementTests(unittest.TestCase):
    def actual_rect(self, geometry):
        width, height, x, y = geometry
        return x, y, x + width - ui_window.FRAME_LOSS[0], y + height - ui_window.FRAME_LOSS[1]

    def test_small_laptop_screen_keeps_the_whole_window_visible(self):
        left, top, right, bottom = self.actual_rect(ui_window.fit_window((0, 0, 1366, 728)))
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(right, 1366)
        self.assertLessEqual(bottom, 728)

    def test_tiny_and_offset_work_areas_stay_inside(self):
        for area in ((0, 0, 1024, 600), (0, 40, 800, 600), (100, 0, 1380, 720)):
            left, top, right, bottom = self.actual_rect(ui_window.fit_window(area))
            self.assertGreaterEqual(left, area[0])
            self.assertGreaterEqual(top, area[1])
            self.assertLessEqual(right, area[2])
            self.assertLessEqual(bottom, area[3])

    def test_large_screen_keeps_the_designed_size_and_centres(self):
        self.assertEqual(ui_window.fit_window((0, 0, 1920, 1040)), (1160, 740, 388, 169))

    def test_unknown_work_area_falls_back_to_default_size(self):
        with patch.object(ui_window, "work_area", return_value=None):
            self.assertEqual(ui_window.initial_geometry(), {"width": 1160, "height": 740})
        with patch.object(ui_window, "work_area", side_effect=OSError):
            self.assertEqual(ui_window.initial_geometry(), {"width": 1160, "height": 740})


class ShellTests(unittest.TestCase):
    def test_no_emoji_or_symbol_glyphs_used_as_icons(self):
        self.assertNotRegex(SHELL_MARKUP, r"[\U0001F300-\U0001FAFF◈◉◌◎⬡▣➤⏹☰]")
        self.assertNotRegex(WORKSPACE, r"[\U0001F300-\U0001FAFF◈◉◌◎⬡▣➤⏹☰]")

    def test_icon_only_buttons_have_accessible_names(self):
        for match in re.finditer(r'<button([^>]*)>\s*<svg[^>]*><use[^>]*/></svg>\s*</button>', SHELL_MARKUP):
            self.assertIn("aria-label=", match.group(1), match.group(0)[:120])

    def test_every_icon_reference_has_a_symbol(self):
        used = set(re.findall(r'href="#i-([\w-]+)"', SHELL_MARKUP))
        defined = set(re.findall(r'<symbol id="i-([\w-]+)"', SHELL_MARKUP))
        self.assertTrue(used)
        self.assertEqual(used - defined, set())
        self.assertNotIn("@@", SHELL_MARKUP)

    def test_composer_is_multiline_and_grows_with_content(self):
        self.assertRegex(SHELL_MARKUP, r'<textarea id="msgInput"')
        css = (ROOT / "assets" / "workspace.css").read_text(encoding="utf-8")
        self.assertIn("field-sizing: content", css)

    def test_stop_stays_reachable_when_a_control_session_is_active(self):
        css = (ROOT / "assets" / "workspace.css").read_text(encoding="utf-8")
        self.assertIn('id="btnHudStopTask"', SHELL_MARKUP)
        self.assertIn(".desktop-task-bar[data-state=\"normal\"]:has(#btnDesktopTaskStop[hidden])", css)
        # The strip only hides when there is nothing to stop.
        self.assertNotRegex(css, r'\.desktop-task-bar\[data-state="normal"\]\s*\{')

    def test_stop_buttons_sit_above_panels_and_overlays(self):
        css = (ROOT / "assets" / "workspace.css").read_text(encoding="utf-8")
        self.assertIn("#btnDesktopTaskStop, #btnCancel { position: relative; z-index: 950; }", css)
        layers = [int(v) for v in re.findall(r"z-index:\s*(\d+)", css)]
        self.assertEqual(max(layers), 950)
        # Containment or animation on an ancestor would trap Stop under the panels.
        self.assertNotRegex(re.search(r"\.main \{[^}]*\}", css).group(0), r"container-type|contain:|transform|z-index")
        self.assertNotRegex(MODERN_CSS, r"\.thinking-row\.show \{")

    def test_status_cards_name_the_local_assistant(self):
        for label in ("Yerel asistan operasyonu", "Yerel asistan görevleri", "Yerel asistan modeli (API)"):
            self.assertIn(label, SHELL_MARKUP)

    def test_failed_preference_save_is_reported_not_swallowed(self):
        self.assertNotIn(".catch(() => {});", WORKSPACE[:WORKSPACE.index("function moveThumb")])
        self.assertIn('id="prefNotice"', SHELL_MARKUP)
        start = WORKSPACE.index("  function applyUiPreference")
        end = WORKSPACE.index("  if (!uiRoot.dataset.theme)")
        script = r'''
const assert=require('node:assert/strict');
const notice={textContent:'',hidden:true};const logs=[];
const uiRoot={dataset:{}};const markPrefButtons=()=>{};const logLine=t=>logs.push(t);
const document={getElementById:()=>notice};let reply;
const window={pywebview:{api:{ui_set_preference:()=>reply()}}};
''' + WORKSPACE[start:end] + r'''
(async()=>{
 reply=()=>Promise.resolve({status:'error',data:'disk dolu'});
 applyUiPreference('theme','light');await new Promise(r=>setTimeout(r,5));
 assert.equal(uiRoot.dataset.theme,'light');assert.equal(notice.hidden,false);assert.match(logs[0],/disk dolu/);
 reply=()=>Promise.reject(new Error('köprü yok'));
 applyUiPreference('theme','dark');await new Promise(r=>setTimeout(r,5));
 assert.equal(notice.hidden,false);assert.match(logs[1],/köprü yok/);
 reply=()=>Promise.resolve({status:'ok',data:{}});
 applyUiPreference('theme','dark');await new Promise(r=>setTimeout(r,5));
 assert.equal(notice.hidden,true);
})().catch(e=>{console.error(e);process.exit(1)});
'''
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_palette_cannot_run_destructive_actions(self):
        commands = WORKSPACE[WORKSPACE.index("function paletteCommands()"):WORKSPACE.index("const paletteFold")]
        for forbidden in ("btnClear", "chat_delete", "requestChatDeletion", "btnClose", "natural_approve", "agent_center_dispatch", "chat_send"):
            self.assertNotIn(forbidden, commands)


class WorkspaceBehaviourTests(unittest.TestCase):
    def test_enter_sends_and_shift_enter_keeps_a_new_line(self):
        start = gui._HTML.index("  inputEl.addEventListener('keydown', (e) => {")
        end = gui._HTML.index("  document.querySelectorAll('.qa-btn", start)
        script = r'''
const assert=require('node:assert/strict');
let handler,sent=0;
const inputEl={value:'',addEventListener:(_,fn)=>handler=fn};
const inpHistory=['eski'];let histCursor=-1;
function sendAgentMessage(){sent++;}
''' + gui._HTML[start:end] + r'''
const key=extra=>({key:'Enter',prevented:false,preventDefault(){this.prevented=true},...extra});
const shift=key({shiftKey:true});handler(shift);assert.equal(sent,0);assert.equal(shift.prevented,false);
const plain=key({});handler(plain);assert.equal(sent,1);assert.equal(plain.prevented,true);
inputEl.value='a\nb';handler({key:'ArrowUp'});assert.equal(inputEl.value,'a\nb');
inputEl.value='';handler({key:'ArrowUp'});assert.equal(inputEl.value,'eski');
'''
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
