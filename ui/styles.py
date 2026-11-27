"""Design tokens and base elements: the first stylesheet in the document.

Every colour in SpeS comes from here. Components (``assets/workspace.css``)
and motion (``ui/theme.py``) read tokens only. Dark is the default; light and
the four accents are selected by attributes on ``<html>``.
"""

# SpeS palette "Şafak" (27 Nov 2026, the new identity): the night before dawn. Deep indigo
# surfaces, moon-white text and one warm dawn accent taken from the hope-star mark. Agents keep
# their own hue: Fatum (Claude) clay, Fides (Codex) blue, Eos (Antigravity) dawn rose. The glow
# behind the ground is the mark's own gradient, very faint. Saved accent keys (rose, citrine,
# amethyst, smoky) are kept so preferences survive; citrine is now the dawn default.
_LIGHT_TOKENS = """
    color-scheme: light;
    --bg: #f7f6fb;
    --surface-1: #ffffff;
    --surface-2: #efedf7;
    --surface-3: #e3e0f0;
    --line: rgba(30,22,80,.10);
    --line-strong: rgba(30,22,80,.19);
    --text: #17152b;
    --text-2: #3e3b58;
    --text-3: #57546f;
    --accent: #b4470f;
    --accent-soft: rgba(180,71,15,.10);
    --on-accent: #ffffff;
    --ok: #1d6f43;
    --warn: #8a4f00;
    --danger: #b3261e;
    --danger-soft: rgba(179,38,30,.08);
    --agent-codex: #2b5cad;
    --agent-agy: #a33a68;
    --agent-claude: #94461b;
    --agent-spes: #4b34c9;
    --amethyst: #4b34c9;
    --amethyst-soft: rgba(75,52,201,.09);
    --aurora-1: rgba(75,52,201,.07);
    --aurora-2: rgba(255,122,89,.07);
    --shadow-1: 0 1px 2px rgba(30,22,80,.07);
    --shadow-2: 0 8px 24px rgba(30,22,80,.09), 0 2px 6px rgba(30,22,80,.05);
    --shadow-3: 0 20px 56px rgba(30,22,80,.16), 0 4px 12px rgba(30,22,80,.07);
    --scrim: rgba(20,16,44,.32);
"""

_LIGHT_CRYSTALS = """{selector}[data-crystal="rose"] {{ --accent:#a33a68; --accent-soft:rgba(163,58,104,.09); --on-accent:#ffffff; }}
{selector}[data-crystal="citrine"] {{ --accent:#b4470f; --accent-soft:rgba(180,71,15,.10); --on-accent:#ffffff; }}
{selector}[data-crystal="amethyst"] {{ --accent:#4b34c9; --accent-soft:rgba(75,52,201,.09); --on-accent:#ffffff; }}
{selector}[data-crystal="smoky"] {{ --accent:#3e3b58; --accent-soft:rgba(62,59,88,.09); --on-accent:#ffffff; }}
"""

BASE_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #0e0f1f;
  --surface-1: #15172b;
  --surface-2: #1c1f38;
  --surface-3: #272a4a;
  --line: rgba(210,204,255,.09);
  --line-strong: rgba(210,204,255,.17);
  --text: #f3f1fb;
  --text-2: #cbc8e0;
  --text-3: #a19eba;
  --accent: #ffa871;
  --accent-soft: rgba(255,168,113,.14);
  --on-accent: #2b1305;
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
  --agent-spes: #c9bfff;
  --amethyst: #b4a7f5;
  --amethyst-soft: rgba(180,167,245,.14);
  --aurora-1: rgba(91,63,217,.16);
  --aurora-2: rgba(255,122,89,.07);
  --shadow-1: 0 1px 2px rgba(0,0,0,.30);
  --shadow-2: 0 8px 24px rgba(0,0,0,.32), 0 2px 6px rgba(0,0,0,.20);
  --shadow-3: 0 20px 56px rgba(0,0,0,.45), 0 4px 12px rgba(0,0,0,.25);
  --scrim: rgba(6,6,16,.62);
  --font: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
  --font-display: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
  --mono: "Cascadia Code", "Cascadia Mono", Consolas, monospace;
  --text-xs: 12.5px;
  --text-sm: 13.5px;
  --text-md: 15px;
  --text-lg: 16px;

  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 18px;
  --r-xl: 26px;
  --side-w: 256px;
  --inspector-w: 320px;
  --measure: 760px;

  --t-fast: 110ms;
  --t-med: 200ms;
  --t-slow: 320ms;
  --ease: cubic-bezier(.2,.75,.25,1);
  --ease-exit: cubic-bezier(.4,0,1,1);
  --spring: linear(0, .009, .035 2.1%, .141 4.4%, .723 12.9%, .938 16.7%, 1.017, 1.077, 1.121, 1.149 24.3%, 1.159, 1.163, 1.161, 1.154 29.9%, 1.129 32.8%, 1.051 39.6%, 1.017 43.1%, .991, .977 51%, .974 53.8%, .975 57.1%, .997 69.8%, 1.003 76.9%, 1);

  /* Şafak brand ramp (the mark's night → dawn), the same in every theme. */
  --brand-1: #4b34c9;
  --brand-2: #7b4fe0;
  --brand-3: #c2502f;
  --on-brand: #ffffff;

  /* Older component names kept as aliases for script-set inline styles. */
  --bg-void: var(--bg);
  --txt-faint: var(--text-3);
}
:root[data-crystal="rose"] { --accent:#f2a7c0; --accent-soft:rgba(242,167,192,.13); --on-accent:#3a1222; }
:root[data-crystal="citrine"] { --accent:#ffa871; --accent-soft:rgba(255,168,113,.14); --on-accent:#2b1305; }
:root[data-crystal="amethyst"] { --accent:#b4a7f5; --accent-soft:rgba(180,167,245,.14); --on-accent:#1c1440; }
:root[data-crystal="smoky"] { --accent:#dcdaea; --accent-soft:rgba(220,218,234,.12); --on-accent:#17152b; }
""" + ':root[data-theme="light"] {' + _LIGHT_TOKENS + "}\n" + _LIGHT_CRYSTALS.format(selector=':root[data-theme="light"]') + """
@media (prefers-color-scheme: light) {
:root[data-theme="system"] {""" + _LIGHT_TOKENS + "}\n" + _LIGHT_CRYSTALS.format(selector=':root[data-theme="system"]') + r"""}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  /* Şafak: the night ground with the mark's dawn glow at two corners. */
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
/* SpeS mark (27 Nov): the hope star at dawn. The mark keeps its own colours in every theme. */
.q-mark .f-tile { fill: url(#spesDawn); }
.q-mark .f-horizon { fill: #FFB86B; }
.q-mark .f-star { fill: #FFF4E3; }
.q-mark .f-companion { fill: #FFD7A8; }
"""
