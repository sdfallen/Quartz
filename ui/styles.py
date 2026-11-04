"""Design tokens and base elements: the first stylesheet in the document.

Every colour in Quartz comes from here. Components (``assets/workspace.css``)
and motion (``ui/theme.py``) read tokens only. Dark is the default; light and
the four crystal accents are selected by attributes on ``<html>``.
"""

_LIGHT_TOKENS = """
    color-scheme: light;
    --bg: #f7f5f2;
    --surface-1: #fdfcfa;
    --surface-2: #f0ede9;
    --surface-3: #e6e2dd;
    --line: rgba(40,30,20,.1);
    --line-strong: rgba(40,30,20,.2);
    --text: #1f1d1b;
    --text-2: #5c5752;
    --text-3: #6f6a64;
    --accent: #a84c38;
    --accent-soft: rgba(168,76,56,.1);
    --on-accent: #ffffff;
    --ok: #24724a;
    --warn: #85590b;
    --danger: #b5372a;
    --danger-soft: rgba(181,55,42,.09);
    --agent-codex: #2f6db0;
    --agent-agy: #7d4fb5;
    --shadow-1: 0 1px 2px rgba(50,35,25,.08);
    --shadow-2: 0 10px 30px rgba(50,35,25,.12), 0 2px 6px rgba(50,35,25,.06);
    --shadow-3: 0 24px 70px rgba(50,35,25,.2), 0 4px 14px rgba(50,35,25,.08);
    --scrim: rgba(40,32,26,.32);
"""

_LIGHT_CRYSTALS = """{selector}[data-crystal="citrine"] {{ --accent:#855d06; --accent-soft:rgba(133,93,6,.1); --on-accent:#ffffff; }}
{selector}[data-crystal="amethyst"] {{ --accent:#6d43ab; --accent-soft:rgba(109,67,171,.09); --on-accent:#ffffff; }}
{selector}[data-crystal="smoky"] {{ --accent:#57504a; --accent-soft:rgba(87,80,74,.1); --on-accent:#ffffff; }}
"""

BASE_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #141312;
  --surface-1: #1b1a18;
  --surface-2: #232220;
  --surface-3: #2d2b29;
  --line: rgba(255,244,235,.08);
  --line-strong: rgba(255,244,235,.15);
  --text: #eeebe7;
  --text-2: #aca69f;
  --text-3: #918b84;
  --accent: #e9a797;
  --accent-soft: rgba(233,167,151,.14);
  --on-accent: #2a1410;
  --ok: #86cba0;
  --warn: #e5bb6e;
  --danger: #f08a7d;
  --danger-soft: rgba(240,138,125,.13);
  --stop: #c4352a;
  --stop-hover: #d8443a;
  --on-stop: #ffffff;
  --agent-codex: #93bbe9;
  --agent-agy: #c9abec;
  --shadow-1: 0 1px 2px rgba(0,0,0,.28);
  --shadow-2: 0 10px 30px rgba(0,0,0,.34), 0 2px 6px rgba(0,0,0,.22);
  --shadow-3: 0 24px 70px rgba(0,0,0,.5), 0 4px 14px rgba(0,0,0,.28);
  --scrim: rgba(10,9,8,.62);

  --font: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
  --font-display: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
  --mono: "Cascadia Code", "Cascadia Mono", Consolas, monospace;
  --text-xs: 11.5px;
  --text-sm: 12.5px;
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
:root[data-crystal="citrine"] { --accent:#e6c06a; --accent-soft:rgba(230,192,106,.14); --on-accent:#2a2006; }
:root[data-crystal="amethyst"] { --accent:#c3a6ee; --accent-soft:rgba(195,166,238,.15); --on-accent:#1f1233; }
:root[data-crystal="smoky"] { --accent:#c9c2b8; --accent-soft:rgba(201,194,184,.14); --on-accent:#1f1c18; }
""" + ':root[data-theme="light"] {' + _LIGHT_TOKENS + "}\n" + _LIGHT_CRYSTALS.format(selector=':root[data-theme="light"]') + """
@media (prefers-color-scheme: light) {
:root[data-theme="system"] {""" + _LIGHT_TOKENS + "}\n" + _LIGHT_CRYSTALS.format(selector=':root[data-theme="system"]') + r"""}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  background: var(--bg);
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
.q-mark .f1 { fill: color-mix(in oklab, var(--accent) 62%, #fff); }
.q-mark .f2 { fill: color-mix(in oklab, var(--accent) 96%, #fff); }
.q-mark .f3 { fill: color-mix(in oklab, var(--accent) 86%, #000); }
.q-mark .f4 { fill: color-mix(in oklab, var(--accent) 58%, #000); }
.q-mark .f5 { fill: color-mix(in oklab, var(--accent) 70%, #000); }
.q-mark .f6 { fill: color-mix(in oklab, var(--accent) 92%, #000); }
.q-mark .f7 { fill: var(--accent); }
"""
