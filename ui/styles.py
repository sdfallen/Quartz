"""Design tokens and base elements: the first stylesheet in the document.

Every colour in Quartz comes from here. Components (``assets/workspace.css``)
and motion (``ui/theme.py``) read tokens only. Dark is the default; light and
the four crystal accents are selected by attributes on ``<html>``.
"""

# Quartz palette (7 Nov 2026): the three faces of quartz instead of black and
# white. Amethyst is the ground, clear rock crystal the text, citrine the light.
# Codex speaks in citrine, Gemini in amethyst, Quartz itself in crystal white.
_LIGHT_TOKENS = """
    color-scheme: light;
    --bg: #f7f3fd;
    --surface-1: #fdfbff;
    --surface-2: #efe8fb;
    --surface-3: #e3d9f6;
    --line: rgba(60,30,110,.11);
    --line-strong: rgba(60,30,110,.21);
    --text: #1c1330;
    --text-2: #4a3c66;
    --text-3: #5f5279;
    --accent: #855a00;
    --accent-soft: rgba(133,90,0,.11);
    --on-accent: #ffffff;
    --ok: #1d7446;
    --warn: #8a4f00;
    --danger: #b0263d;
    --danger-soft: rgba(176,38,61,.09);
    --agent-codex: #855a00;
    --agent-agy: #6a3fc9;
    --agent-quartz: #1c1330;
    --amethyst: #6a3fc9;
    --amethyst-soft: rgba(106,63,201,.12);
    --aurora-1: rgba(106,63,201,.11);
    --aurora-2: rgba(204,150,20,.10);
    --shadow-1: 0 1px 2px rgba(50,20,90,.08);
    --shadow-2: 0 10px 30px rgba(50,20,90,.12), 0 2px 6px rgba(50,20,90,.06);
    --shadow-3: 0 24px 70px rgba(50,20,90,.2), 0 4px 14px rgba(50,20,90,.08);
    --scrim: rgba(30,16,52,.32);
"""

_LIGHT_CRYSTALS = """{selector}[data-crystal="rose"] {{ --accent:#a8325f; --accent-soft:rgba(168,50,95,.1); --on-accent:#ffffff; }}
{selector}[data-crystal="citrine"] {{ --accent:#855a00; --accent-soft:rgba(133,90,0,.11); --on-accent:#ffffff; }}
{selector}[data-crystal="amethyst"] {{ --accent:#6a3fc9; --accent-soft:rgba(106,63,201,.1); --on-accent:#ffffff; }}
{selector}[data-crystal="smoky"] {{ --accent:#4f4763; --accent-soft:rgba(79,71,99,.1); --on-accent:#ffffff; }}
"""

BASE_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #130e1f;
  --surface-1: #1a1428;
  --surface-2: #231b36;
  --surface-3: #2f2546;
  --line: rgba(222,204,255,.09);
  --line-strong: rgba(222,204,255,.17);
  --text: #f7f3ff;
  --text-2: #cfc4e6;
  --text-3: #ab9dca;
  --accent: #f5c85a;
  --accent-soft: rgba(245,200,90,.14);
  --on-accent: #2a1d00;
  --ok: #8fdcaa;
  --warn: #ffb870;
  --danger: #ff8fa1;
  --danger-soft: rgba(255,143,161,.13);
  --stop: #c4352a;
  --stop-hover: #d8443a;
  --on-stop: #ffffff;
  --agent-codex: #f5c85a;
  --agent-agy: #c6a6ff;
  --agent-quartz: #f7f3ff;
  --amethyst: #9d6cff;
  --amethyst-soft: rgba(157,108,255,.18);
  --aurora-1: rgba(157,108,255,.24);
  --aurora-2: rgba(245,200,90,.09);
  --shadow-1: 0 1px 2px rgba(6,0,16,.36);
  --shadow-2: 0 10px 30px rgba(6,0,16,.42), 0 2px 6px rgba(6,0,16,.26);
  --shadow-3: 0 24px 70px rgba(6,0,16,.58), 0 4px 14px rgba(6,0,16,.32);
  --scrim: rgba(10,5,22,.64);

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
:root[data-crystal="rose"] { --accent:#f4a9c6; --accent-soft:rgba(244,169,198,.14); --on-accent:#2c0f1c; }
:root[data-crystal="citrine"] { --accent:#f5c85a; --accent-soft:rgba(245,200,90,.14); --on-accent:#2a1d00; }
:root[data-crystal="amethyst"] { --accent:#c6a6ff; --accent-soft:rgba(198,166,255,.16); --on-accent:#1f1036; }
:root[data-crystal="smoky"] { --accent:#ebe5f5; --accent-soft:rgba(235,229,245,.13); --on-accent:#1f1a2a; }
""" + ':root[data-theme="light"] {' + _LIGHT_TOKENS + "}\n" + _LIGHT_CRYSTALS.format(selector=':root[data-theme="light"]') + """
@media (prefers-color-scheme: light) {
:root[data-theme="system"] {""" + _LIGHT_TOKENS + "}\n" + _LIGHT_CRYSTALS.format(selector=':root[data-theme="system"]') + r"""}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  /* Still light, no motion: an amethyst glow above, a citrine one below. */
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
.q-mark .f1 { fill: color-mix(in oklab, var(--accent) 62%, #fff); }
.q-mark .f2 { fill: color-mix(in oklab, var(--accent) 96%, #fff); }
.q-mark .f3 { fill: color-mix(in oklab, var(--accent) 86%, #000); }
.q-mark .f4 { fill: color-mix(in oklab, var(--accent) 58%, #000); }
.q-mark .f5 { fill: color-mix(in oklab, var(--accent) 70%, #000); }
.q-mark .f6 { fill: color-mix(in oklab, var(--accent) 92%, #000); }
.q-mark .f7 { fill: var(--accent); }
"""
