"""Design tokens and base elements: the first stylesheet in the document.

Every colour in SpeS comes from here. Components (``assets/workspace.css``)
and motion (``ui/theme.py``) read tokens only. Dark is the default; light and
the four accents are selected by attributes on ``<html>``.
"""

# SpeS palette (13 Nov 2026): a calm, study-desk ground instead of a cockpit.
# Warm ink surfaces, soft paper-white text and one quiet accent: sage "hope"
# green by default. Agents keep their own hue: Fatum (Claude) clay, Fides
# (Codex) blue, Eos (Antigravity) dawn rose. Glows are nearly flat.
# The stored accent keys (rose/citrine/amethyst/smoky) are kept so saved
# preferences survive; their colours and Turkish labels changed.
_LIGHT_TOKENS = """
    color-scheme: light;
    --bg: #f5f6f3;
    --surface-1: #ffffff;
    --surface-2: #eceeea;
    --surface-3: #dfe3de;
    --line: rgba(24,40,32,.10);
    --line-strong: rgba(24,40,32,.19);
    --text: #161b18;
    --text-2: #3c4741;
    --text-3: #55615a;
    --accent: #1f6b4b;
    --accent-soft: rgba(31,107,75,.10);
    --on-accent: #ffffff;
    --ok: #1d6f43;
    --warn: #8a4f00;
    --danger: #b3261e;
    --danger-soft: rgba(179,38,30,.08);
    --agent-codex: #2b5cad;
    --agent-agy: #a33a68;
    --agent-claude: #94461b;
    --agent-spes: #161b18;
    --amethyst: #5a4ab5;
    --amethyst-soft: rgba(90,74,181,.10);
    --aurora-1: rgba(31,107,75,.035);
    --aurora-2: rgba(163,58,104,.025);
    --shadow-1: 0 1px 2px rgba(20,30,25,.07);
    --shadow-2: 0 8px 24px rgba(20,30,25,.09), 0 2px 6px rgba(20,30,25,.05);
    --shadow-3: 0 20px 56px rgba(20,30,25,.16), 0 4px 12px rgba(20,30,25,.07);
    --scrim: rgba(18,24,21,.30);
"""

_LIGHT_CRYSTALS = """{selector}[data-crystal="rose"] {{ --accent:#a33a68; --accent-soft:rgba(163,58,104,.09); --on-accent:#ffffff; }}
{selector}[data-crystal="citrine"] {{ --accent:#1f6b4b; --accent-soft:rgba(31,107,75,.10); --on-accent:#ffffff; }}
{selector}[data-crystal="amethyst"] {{ --accent:#5a4ab5; --accent-soft:rgba(90,74,181,.09); --on-accent:#ffffff; }}
{selector}[data-crystal="smoky"] {{ --accent:#3f4943; --accent-soft:rgba(63,73,67,.09); --on-accent:#ffffff; }}
"""

BASE_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #121416;
  --surface-1: #181b1d;
  --surface-2: #1f2326;
  --surface-3: #2a2f32;
  --line: rgba(226,236,230,.08);
  --line-strong: rgba(226,236,230,.15);
  --text: #eef1ed;
  --text-2: #c4cbc6;
  --text-3: #98a29c;
  --accent: #8fcfb0;
  --accent-soft: rgba(143,207,176,.13);
  --on-accent: #0f2a1e;
  --ok: #86d39f;
  --warn: #f0b866;
  --danger: #f28b82;
  --danger-soft: rgba(242,139,130,.12);
  --stop: #b93a30;
  --stop-hover: #cc4a3f;
  --on-stop: #ffffff;
  --agent-codex: #8ab4f8;
  --agent-agy: #f2a7c0;
  --agent-claude: #e8a06e;
  --agent-spes: #eef1ed;
  --amethyst: #b4a7f5;
  --amethyst-soft: rgba(180,167,245,.14);
  --aurora-1: rgba(143,207,176,.045);
  --aurora-2: rgba(242,167,192,.03);
  --shadow-1: 0 1px 2px rgba(0,0,0,.30);
  --shadow-2: 0 8px 24px rgba(0,0,0,.32), 0 2px 6px rgba(0,0,0,.20);
  --shadow-3: 0 20px 56px rgba(0,0,0,.45), 0 4px 12px rgba(0,0,0,.25);
  --scrim: rgba(8,10,9,.60);
  --font: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
  --font-display: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
  --mono: "Cascadia Code", "Cascadia Mono", Consolas, monospace;
  --text-xs: 12px;
  --text-sm: 13px;
  --text-md: 14px;
  --text-lg: 15px;

  --r-sm: 6px;
  --r-md: 9px;
  --r-lg: 14px;
  --r-xl: 20px;
  --side-w: 256px;
  --inspector-w: 320px;
  --measure: 760px;

  --t-fast: 110ms;
  --t-med: 200ms;
  --t-slow: 320ms;
  --ease: cubic-bezier(.2,.75,.25,1);
  --ease-exit: cubic-bezier(.4,0,1,1);
  --spring: linear(0, .009, .035 2.1%, .141 4.4%, .723 12.9%, .938 16.7%, 1.017, 1.077, 1.121, 1.149 24.3%, 1.159, 1.163, 1.161, 1.154 29.9%, 1.129 32.8%, 1.051 39.6%, 1.017 43.1%, .991, .977 51%, .974 53.8%, .975 57.1%, .997 69.8%, 1.003 76.9%, 1);

  /* Older component names kept as aliases for script-set inline styles. */
  --bg-void: var(--bg);
  --txt-faint: var(--text-3);
}
:root[data-crystal="rose"] { --accent:#f2a7c0; --accent-soft:rgba(242,167,192,.13); --on-accent:#3a1222; }
:root[data-crystal="citrine"] { --accent:#8fcfb0; --accent-soft:rgba(143,207,176,.13); --on-accent:#0f2a1e; }
:root[data-crystal="amethyst"] { --accent:#b4a7f5; --accent-soft:rgba(180,167,245,.14); --on-accent:#1c1440; }
:root[data-crystal="smoky"] { --accent:#dde3df; --accent-soft:rgba(221,227,223,.12); --on-accent:#1a201c; }
""" + ':root[data-theme="light"] {' + _LIGHT_TOKENS + "}\n" + _LIGHT_CRYSTALS.format(selector=':root[data-theme="light"]') + """
@media (prefers-color-scheme: light) {
:root[data-theme="system"] {""" + _LIGHT_TOKENS + "}\n" + _LIGHT_CRYSTALS.format(selector=':root[data-theme="system"]') + r"""}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  /* Calm and still: an almost flat ground with the faintest dawn light. */
  background:
    radial-gradient(1100px 620px at 88% -12%, var(--aurora-1), transparent 62%),
    radial-gradient(900px 520px at -8% 112%, var(--aurora-2), transparent 60%),
    var(--bg);
  color: var(--text);
  font: 400 var(--text-md)/1.55 var(--font);
  -webkit-font-smoothing: antialiased;
  user-select: none;
}
button, select, input, textarea { font: inherit; color: inherit; }
button { background: none; border: 0; cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .45; }
input, textarea { user-select: text; }
[hidden] { display: none !important; }
:focus { outline: none; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: var(--r-sm); }
kbd { font: 500 10.5px var(--font); color: var(--text-3); border: 1px solid var(--line-strong); border-radius: 5px; padding: 1px 5px; white-space: nowrap; }
::selection { background: var(--accent-soft); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--surface-3); border-radius: 8px; border: 3px solid transparent; background-clip: content-box; }
::-webkit-scrollbar-thumb:hover { background: var(--text-3); border: 3px solid transparent; background-clip: content-box; }
::-webkit-scrollbar-track { background: transparent; }
.i { fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; flex: none; }
.i-sm { width: 14px; height: 14px; }
.i-md { width: 17px; height: 17px; }
/* SpeS mark: f1 the rising sun, f2-f6 its rays (gold to rose), f7 the horizon in the accent. */
.q-mark .f1 { fill: color-mix(in oklab, var(--warn) 55%, var(--agent-claude)); }
.q-mark .f2 { fill: color-mix(in oklab, var(--warn) 80%, #fff); }
.q-mark .f3 { fill: var(--warn); }
.q-mark .f4 { fill: color-mix(in oklab, var(--warn) 45%, var(--agent-claude)); }
.q-mark .f5 { fill: var(--agent-claude); }
.q-mark .f6 { fill: color-mix(in oklab, var(--agent-claude) 45%, var(--agent-agy)); }
.q-mark .f7 { fill: var(--accent); }
"""
