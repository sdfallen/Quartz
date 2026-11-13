"""Motion layer: the last stylesheet in the document.

Rules this file keeps (tests/test_gui_modern_theme.py enforces them):
keyframes move only opacity and transform; every animation is declared inside
the no-preference block and scoped to ``:not(.low-spec)``, except the few
one-element, compositor-only motions in LOW_SPEC_MOTION (the typing reveal and
the live agent line); nothing disables
pointer input; controls that stop real work never animate. Motion shows cause
and effect (a message arrived, a panel opened, the agent is working), so idle
screens stay still. While an agent works, light walks round the crystal in the
brand mark.
"""

# A message being written and an agent at work: the only motion while waiting.
# Selectors that keep their motion on low-spec hardware (user, 7 Nov: no motion
# at all on an 8 GB / 4-core PC, which counts as low-spec): each moves one small
# element with opacity/transform only, and the reveal is cut short by Stop/history.
LOW_SPEC_MOTION = ("body.low-spec .chat > .msg:last-child", "body:not(.ui-idle) .reveal-caret",
                   "body .agent-live-now > span", "body:not(.ui-idle) .agent-live-gem",
                   # Crew band (7 Nov): light flowing down a working agent's rail, along
                   # the crystal's beam, and the crystal's halo. Declared paused; the
                   # stylesheet runs them only while that agent is working.
                   "body:not(.ui-idle) .rail-flow", "body:not(.ui-idle) .beam-flow",
                   "body:not(.ui-idle) .core-halo")

MODERN_CSS = r"""
/* Stop must respond the instant it is pressed. */
#btnDesktopTaskStop,#btnHudStopTask,#btnDesktopStop,#btnCancel { transition:none !important; animation:none !important; transform:none !important; }

@keyframes q-rise { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
@keyframes q-fade { from { opacity:0; } to { opacity:1; } }
@keyframes q-sheet { from { opacity:0; transform:translateY(10px) scale(.975); } to { opacity:1; transform:none; } }
@keyframes q-palette { from { opacity:0; transform:translateY(-8px) scale(.98); } to { opacity:1; transform:none; } }
@keyframes q-panel-in { from { opacity:0; transform:translateX(14px); } to { opacity:1; transform:none; } }
@keyframes q-facet { from { opacity:0; transform:scale(.72); } to { opacity:1; transform:none; } }
@keyframes q-facet-work { 0%,100% { opacity:1; } 45% { opacity:.34; } }
@keyframes q-dot { 0%,100% { opacity:.3; transform:none; } 40% { opacity:1; transform:translateY(-2px); } }
@keyframes q-intro-out { to { opacity:0; transform:scale(1.015); } }
@keyframes q-hud-pulse { 0%,100% { opacity:1; } 50% { opacity:.4; } }
@keyframes q-caret { 0%,45% { opacity:1; } 55%,100% { opacity:.2; } }
@keyframes q-live-in { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
@keyframes q-gem { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:.55; transform:scale(.78); } }
@keyframes q-flow { from { transform:translateY(-100%); } to { transform:translateY(340%); } }
@keyframes q-beam { from { transform:translateX(-100%); } to { transform:translateX(230%); } }
@keyframes q-halo { 0%,100% { opacity:.55; transform:scale(.9); } 50% { opacity:1; transform:scale(1.1); } }

@media (prefers-reduced-motion: no-preference) {
  body:not(.low-spec) .chat > .msg:nth-last-child(-n+8),
  body:not(.low-spec) .chat > .coordination-card,
  body:not(.low-spec) .chat > .action-card { animation:q-rise var(--t-slow) var(--ease) both; }
  body:not(.low-spec) .empty-state > * { animation:q-rise 420ms var(--ease) both; }
  body:not(.low-spec) .empty-state > :nth-child(2) { animation-delay:40ms; }
  body:not(.low-spec) .empty-state > :nth-child(3) { animation-delay:80ms; }
  body:not(.low-spec) .empty-state > :nth-child(4) { animation-delay:120ms; }
  body:not(.low-spec) .api-setup.show,
  body:not(.low-spec) .agent-overlay.show,
  body:not(.low-spec) .confirm-layer:not([hidden]) .confirm-scrim,
  body:not(.low-spec) .palette-scrim { animation:q-fade var(--t-med) var(--ease) both; }
  body:not(.low-spec) .api-setup.show .api-panel,
  body:not(.low-spec) .confirm-layer:not([hidden]) .confirm-panel,
  body:not(.low-spec) .agent-overlay.show .agent-panel { animation:q-sheet var(--t-slow) var(--spring) both; }
  body:not(.low-spec) .palette { animation:q-palette var(--t-med) var(--ease) both; }
  body.show-panels:not(.low-spec) .inspector { animation:q-panel-in var(--t-slow) var(--ease) both; }
  body:not(.low-spec) .tab-panel:not([hidden]) { animation:q-fade var(--t-med) var(--ease) both; }
  body:not(.low-spec) .notion-tools:not([hidden]) { animation:q-rise var(--t-slow) var(--ease) both; }

  body:not(.low-spec) .signature-intro { animation:q-intro-out 220ms var(--ease-exit) 620ms both; }
  body:not(.low-spec) .signature-intro .f { transform-box:fill-box; transform-origin:center; animation:q-facet 420ms var(--spring) both; }
  body:not(.low-spec) .signature-intro .f2 { animation-delay:40ms; }
  body:not(.low-spec) .signature-intro .f3 { animation-delay:80ms; }
  body:not(.low-spec) .signature-intro .f4 { animation-delay:120ms; }
  body:not(.low-spec) .signature-intro .f5 { animation-delay:160ms; }
  body:not(.low-spec) .signature-intro .f6 { animation-delay:200ms; }
  body:not(.low-spec) .signature-intro .f7 { animation-delay:280ms; }
  body:not(.low-spec) .signature-intro .intro-brand,
  body:not(.low-spec) .signature-intro .intro-credit { animation:q-rise 360ms var(--ease) 180ms both; }

  body.thinking-active:not(.low-spec):not(.ui-idle) #orbCore .f { animation:q-facet-work 1500ms ease-in-out infinite; }
  body.thinking-active:not(.low-spec):not(.ui-idle) #orbCore .f2 { animation-delay:120ms; }
  body.thinking-active:not(.low-spec):not(.ui-idle) #orbCore .f3 { animation-delay:240ms; }
  body.thinking-active:not(.low-spec):not(.ui-idle) #orbCore .f4 { animation-delay:360ms; }
  body.thinking-active:not(.low-spec):not(.ui-idle) #orbCore .f5 { animation-delay:480ms; }
  body.thinking-active:not(.low-spec):not(.ui-idle) #orbCore .f6 { animation-delay:600ms; }
  body.thinking-active:not(.low-spec):not(.ui-idle) #orbCore .f7 { animation-delay:720ms; }
  body:not(.low-spec):not(.ui-idle) .thinking-row.show .d { animation:q-dot 1100ms ease-in-out infinite; }
  body:not(.low-spec):not(.ui-idle) .thinking-row.show .d:nth-child(2) { animation-delay:140ms; }
  body:not(.low-spec):not(.ui-idle) .thinking-row.show .d:nth-child(3) { animation-delay:280ms; }
  body:not(.low-spec):not(.ui-idle) .bubble.pending > div:first-child::before { animation:q-dot 1100ms ease-in-out infinite; }
  body:not(.low-spec):not(.ui-idle) .bubble.pending > div:first-child::after { animation:q-dot 1100ms ease-in-out 200ms infinite; }
  body:not(.low-spec) .hud-dot { animation:q-hud-pulse 1600ms ease-in-out infinite; }
  body.low-spec .chat > .msg:last-child { animation:q-rise var(--t-slow) var(--ease) both; }
  body:not(.ui-idle) .reveal-caret { animation:q-caret 900ms steps(1,end) infinite; }
  body .agent-live-now > span { animation:q-live-in var(--t-med) var(--ease) both; }
  body:not(.ui-idle) .agent-live-gem { animation:q-gem 1400ms ease-in-out infinite; }
  body:not(.ui-idle) .rail-flow { animation:q-flow 2600ms linear infinite paused; }
  body:not(.ui-idle) .beam-flow { animation:q-beam 1300ms linear infinite paused; }
  body:not(.ui-idle) .core-halo { animation:q-halo 2400ms ease-in-out infinite paused; }
}
/* Orb state still reads without motion. */
#orbCore[data-state="error"] .f { fill:var(--danger); }
#orbCore[data-state="listening"] .f { fill:var(--ok); }

@media (prefers-reduced-motion: reduce) {
  *,*::before,*::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; }
  .signature-intro { display:none !important; }
}
body.low-spec *:not(.msg):not(.reveal-caret):not(.agent-live-gem):not(.agent-live-now > span):not(.rail-flow):not(.beam-flow):not(.core-halo),body.low-spec *::before,body.low-spec *::after { animation:none !important; transition:none !important; }
"""
