"""Quartz modern theme layer.

Appended after ``assets/workspace.css`` (see ``ui/document.py``), so it is the
final word on presentation. It changes look, layout and motion only; it adds no
behaviour. Kept as a Python module for the same packaging reason as
``ui/styles.py``.

Design notes (see docs/CLAUDE_FRONTEND_MODERN_UI.md):
- Ink-blue surfaces taken from the Q mark; one bold element, the faceted
  crystal gradient, reserved for the send button, the active agent and an
  active desktop task.
- State is always text plus colour, never colour alone.
- Motion only answers something that changed. Stop controls never animate.
  ``prefers-reduced-motion`` and ``body.low-spec`` switch all motion off.
"""

MODERN_CSS = r"""
:root {
  --q-ink-950:#070c17; --q-ink-900:#0b1220; --q-ink-850:#0e1627; --q-ink-800:#111a2c;
  --q-ink-700:#17223a; --q-ink-600:#1e2b47; --q-line:#22304b; --q-line-strong:#2f4065;
  --q-text:#e7edf7; --q-text-2:#c3cee0; --q-muted:#8fa0bd; --q-faint:#62728f;
  --q-crystal:#59c9f4; --q-crystal-soft:rgba(89,201,244,.14);
  --q-facet:linear-gradient(135deg,#a8ecff 0 22%,#59c9f4 22% 48%,#3b9cf2 48% 74%,#2a6fe0 74% 100%);
  --q-codex:#7fd6ff; --q-agy:#b9a2ff; --q-notion:#d8d3c6;
  --q-ok:#4fd1a1; --q-warn:#f2c46b; --q-danger:#ff6b7d; --q-danger-strong:#e5384f;
  --q-radius-s:8px; --q-radius-m:12px; --q-radius-l:16px;
  --q-font:'Segoe UI Variable Text','Segoe UI Variable','Segoe UI',system-ui,sans-serif;
  --q-mono:'Cascadia Mono','Cascadia Code',Consolas,'Courier New',monospace;
  --q-ease:cubic-bezier(.2,.7,.2,1);
  --q-fast:140ms; --q-med:220ms;
}

html,body { font-family:var(--q-font) !important; background:var(--q-ink-900) !important; color:var(--q-text); }
.shell { background:var(--q-ink-900); }
::selection { background:rgba(89,201,244,.32); color:#fff; }
:focus-visible { outline:2px solid var(--q-crystal) !important; outline-offset:2px; }
* { scrollbar-color:var(--q-line-strong) transparent; }

/* Title bar ---------------------------------------------------------------- */
.titlebar { background:var(--q-ink-950); border-bottom:1px solid var(--q-line); height:52px; min-height:52px; }
.brand { font:600 16px var(--q-font) !important; letter-spacing:.02em; color:var(--q-text); }
.brand-icon { border-radius:7px; }
.status-pill { font:500 12px var(--q-font) !important; color:var(--q-muted); letter-spacing:0; gap:7px;
  padding:4px 10px !important; border-radius:999px !important; transition:color var(--q-med), background var(--q-med); }
.status-pill .dot { width:7px; height:7px; background:var(--q-faint) !important; transition:background var(--q-med), box-shadow var(--q-med); }
.status-pill.online { color:var(--q-text-2); background:rgba(79,209,161,.08) !important; }
.status-pill.online .dot { background:var(--q-ok) !important; box-shadow:0 0 0 3px rgba(79,209,161,.18) !important; }
.status-pill.offline .dot { background:var(--q-warn) !important; }
.titlebar .win-btn,.titlebar #btnPanels { color:var(--q-muted); font:13px var(--q-font) !important; border-radius:var(--q-radius-s); }
.titlebar #btnPanels:hover,.titlebar .win-btn:hover { background:var(--q-ink-700) !important; color:var(--q-text) !important; }
.titlebar .win-btn.close:hover { background:var(--q-danger-strong) !important; color:#fff !important; }

/* Workspace sidebar --------------------------------------------------------- */
body:not(.show-panels) .rail.left,.rail.left { background:var(--q-ink-850) !important; border-right:1px solid var(--q-line) !important;
  padding:18px 12px !important; gap:6px !important; }
.workspace-nav-title { text-transform:none !important; letter-spacing:0 !important; font:600 12px var(--q-font) !important;
  color:var(--q-muted) !important; margin:14px 8px 6px !important; }
.workspace-nav-title:first-child { margin-top:2px !important; }
.workspace-project select,.project-picker,.agent-select,.model-selector-pill select {
  font:13px var(--q-font) !important; background:var(--q-ink-700) !important; color:var(--q-text-2) !important;
  border:1px solid var(--q-line) !important; border-radius:var(--q-radius-s) !important; }
.workspace-project select:hover,.project-picker:hover,.agent-select:hover { border-color:var(--q-line-strong) !important; }
.conversation-entry { font:13.5px var(--q-font) !important; color:var(--q-text-2) !important; border-radius:var(--q-radius-s) !important;
  padding:8px 10px !important; margin:1px 0 !important; position:relative; transition:background var(--q-fast), color var(--q-fast); }
.conversation-entry:hover { background:var(--q-ink-700) !important; color:var(--q-text) !important; }
.conversation-entry.active { background:var(--q-ink-600) !important; color:#fff !important; }
.conversation-entry.active::before { content:''; position:absolute; left:0; top:8px; bottom:8px; width:3px; border-radius:3px; background:var(--q-facet); }
.conversation-delete { color:var(--q-faint) !important; opacity:0; transition:opacity var(--q-fast); }
.conversation-row:hover .conversation-delete,.conversation-delete:focus-visible,.conversation-entry.active + .conversation-delete { opacity:1; }
.conversation-delete:hover,.conversation-delete:focus-visible { color:var(--q-danger) !important; background:rgba(255,107,125,.1) !important; }
.project-chats-delete { border:1px solid var(--q-line) !important; color:var(--q-muted) !important; background:transparent !important;
  border-radius:var(--q-radius-s) !important; font:12px var(--q-font) !important; }
.project-chats-delete:hover { color:var(--q-danger) !important; border-color:rgba(255,107,125,.4) !important; }
.rail.left .card .card-label { text-transform:none !important; letter-spacing:0 !important; font:600 12px var(--q-font) !important; color:var(--q-muted) !important; }

/* Agent connections (sidebar) */
.agent-connections { display:flex; flex-direction:column; gap:2px; margin:0 0 4px; }
.agent-conn { display:grid; grid-template-columns:10px 1fr; column-gap:10px; align-items:center; padding:7px 10px;
  border-radius:var(--q-radius-s); font:13px var(--q-font); color:var(--q-text-2); }
.agent-conn[aria-current="true"] { background:var(--q-ink-700); }
.agent-conn .conn-dot { width:8px; height:8px; border-radius:50%; background:var(--q-faint); transition:background var(--q-med), box-shadow var(--q-med); }
.agent-conn[data-agent-id="codex"] .conn-name { color:var(--q-codex); }
.agent-conn[data-agent-id="antigravity"] .conn-name { color:var(--q-agy); }
.agent-conn[data-agent-id="notion"] .conn-name { color:var(--q-notion); }
.agent-conn .conn-state { grid-column:2; font-size:12px; color:var(--q-faint); line-height:1.35; }
.agent-conn[data-state="ready"] .conn-dot { background:var(--q-ok); box-shadow:0 0 0 3px rgba(79,209,161,.16); }
.agent-conn[data-state="pending"] .conn-dot { background:var(--q-warn); }
.agent-conn[data-state="missing"] .conn-dot { background:transparent; border:1.5px solid var(--q-faint); box-sizing:border-box; }
.agent-conn[data-state="ready"] .conn-state { color:var(--q-muted); }

/* Chat header ---------------------------------------------------------------- */
.chat-col { background:var(--q-ink-900) !important; }
.chat-header { padding:14px 28px 12px !important; gap:10px 12px !important; border-bottom:1px solid var(--q-line) !important; align-items:center; }
.chat-header::after { content:''; flex-basis:100%; order:3; height:0; }
.chat-title-group { order:1; flex:1 1 260px !important; min-width:0 !important; flex-wrap:wrap; row-gap:6px; }
.chat-controls-group { order:2; flex:0 0 auto; gap:6px !important; }
.agent-seg-group { order:4; }
.chat-models-bar { order:5; width:auto !important; flex:1 1 auto; padding:0 !important; justify-content:flex-start !important; border-top:0 !important; }
.chat-conv-title { font:600 17px var(--q-font) !important; color:var(--q-text) !important; max-width:100%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.squad-badge,.project-tag,#writerBadge { font:500 11.5px var(--q-font) !important; border-radius:999px !important; padding:3px 9px !important;
  border:1px solid var(--q-line) !important; background:var(--q-ink-800) !important; color:var(--q-muted) !important; white-space:nowrap; }
.squad-badge::before { content:''; display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--q-ok); margin-right:6px; vertical-align:1px; }
.squad-badge.warn { color:var(--q-warn) !important; border-color:rgba(242,196,107,.35) !important; }
.squad-badge.warn::before { background:var(--q-warn); }
#writerBadge { color:var(--q-codex) !important; font-family:var(--q-font) !important; }
#permissionSelectionHint { color:var(--q-muted) !important; font:500 12.5px var(--q-font) !important; padding:0 6px 0 0; white-space:nowrap; }

/* Agent segmented control */
.agent-seg-group { display:flex; gap:2px !important; padding:3px !important; background:var(--q-ink-800) !important;
  border:1px solid var(--q-line) !important; border-radius:var(--q-radius-m) !important; }
.agent-seg-btn,.agent-seg-btn.active,.agent-seg-btn.active[data-agent] { font:500 13px var(--q-font) !important; color:var(--q-muted) !important;
  background:transparent !important; border:0 !important; border-radius:9px !important; padding:6px 12px !important; position:relative;
  transition:background var(--q-fast), color var(--q-fast); }
.agent-seg-btn:hover:not(:disabled) { color:var(--q-text) !important; background:var(--q-ink-700) !important; }
.agent-seg-btn.active,.agent-seg-btn.active[data-agent] { color:#fff !important; background:var(--q-ink-600) !important;
  box-shadow:inset 0 0 0 1px var(--q-line-strong) !important; }
.agent-seg-btn.active::after { content:''; position:absolute; left:12px; right:12px; bottom:2px; height:2px; border-radius:2px; background:var(--q-facet); }
.agent-seg-btn[data-agent="codex"].active { color:var(--q-codex) !important; }
.agent-seg-btn[data-agent="antigravity"].active { color:var(--q-agy) !important; }
.agent-seg-btn:disabled,.agent-seg-btn[aria-disabled="true"] { opacity:.5; cursor:not-allowed; }
.agent-seg-btn.agent-seg-unavailable { color:var(--q-faint) !important; }

/* Model pills: only the agents in play are shown */
.model-selector-pill,.model-selector-pill.active-agy,.model-selector-pill.active-codex { background:var(--q-ink-800) !important;
  border:1px solid var(--q-line) !important; border-radius:var(--q-radius-m) !important; padding:2px 4px 2px 10px !important; gap:2px !important; }
.model-selector-pill:not(.active-agy):not(.active-codex):not(.active-notion) { display:none !important; }
#notionAgentPill { box-shadow:inset 3px 0 0 var(--q-notion) !important; }
#notionAgentPill .pill-agent-name { color:var(--q-notion) !important; }
.pill-agent-name { font:600 11.5px var(--q-font) !important; letter-spacing:0 !important; text-transform:none; }
#agyModelPill .pill-agent-name { color:var(--q-agy) !important; }
#agyModelPill { box-shadow:inset 3px 0 0 var(--q-agy) !important; }
#codexModelPill { box-shadow:inset 3px 0 0 var(--q-codex) !important; }
#codexModelPill .pill-agent-name { color:var(--q-codex) !important; }
.model-selector-pill select { background:transparent !important; border:0 !important; color:var(--q-text-2) !important; padding:5px 4px !important; }
.pill-sep { color:var(--q-faint); }

/* Buttons */
.chat-tool-btn,.control-btn,.qa-btn,.coordination-card button { font:500 12.5px var(--q-font) !important; border:1px solid var(--q-line) !important;
  background:var(--q-ink-800) !important; color:var(--q-text-2) !important; border-radius:var(--q-radius-s) !important; padding:6px 11px;
  transition:background var(--q-fast), border-color var(--q-fast), color var(--q-fast); }
.chat-tool-btn:hover:not(:disabled),.control-btn:hover:not(:disabled),.qa-btn:hover,.coordination-card button:hover:not(:disabled) {
  background:var(--q-ink-700) !important; border-color:var(--q-line-strong) !important; color:var(--q-text) !important; }
.chat-tool-btn:disabled,.control-btn:disabled,.coordination-card button:disabled { opacity:.45; cursor:not-allowed; }

/* Desktop task strip: the one place task state lives ---------------------------- */
.desktop-task-bar { margin:10px 28px 0 !important; padding:9px 12px 9px 16px !important; border:1px solid var(--q-line) !important;
  border-radius:var(--q-radius-m) !important; background:var(--q-ink-850) !important; position:relative; overflow:hidden;
  transition:background var(--q-med), border-color var(--q-med); }
.desktop-task-bar::before { content:''; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--q-line-strong); transition:background var(--q-med); }
.desktop-task-copy { font:12px/1.45 var(--q-font) !important; color:var(--q-muted) !important; }
.desktop-task-copy strong { font:600 13px var(--q-font) !important; color:var(--q-text-2) !important; }
.desktop-task-bar[data-state="normal"] { background:transparent !important; border-color:transparent !important; padding:4px 2px !important; }
.desktop-task-bar[data-state="normal"]::before { display:none; }
.desktop-task-bar[data-state="normal"] .desktop-task-copy { flex-direction:row; gap:8px; align-items:baseline; flex-wrap:wrap; }
.desktop-task-bar[data-state="normal"] .desktop-task-copy strong { font-weight:500 !important; color:var(--q-muted) !important; }
.desktop-task-bar[data-state="normal"] .desktop-task-copy span { color:var(--q-faint); }
.desktop-task-bar[data-state="active"],.desktop-task-bar[data-state="preparing"] { background:linear-gradient(90deg,rgba(89,201,244,.10),rgba(89,201,244,.02)) !important;
  border-color:rgba(89,201,244,.35) !important; }
.desktop-task-bar[data-state="active"]::before,.desktop-task-bar[data-state="preparing"]::before { background:var(--q-facet); }
.desktop-task-bar[data-state="active"] .desktop-task-copy strong { color:#fff !important; }
.desktop-task-bar[data-state="pending"] { background:rgba(242,196,107,.07) !important; border-color:rgba(242,196,107,.35) !important; }
.desktop-task-bar[data-state="pending"]::before { background:var(--q-warn); }
.desktop-task-bar[data-state="released"]::before { background:var(--q-ok); }

/* Notion local-tool status (rendered by ui/document.py from backend data only) */
.notion-tools { margin:8px 28px 0; padding:10px 14px 10px 16px; border:1px solid var(--q-line); border-radius:var(--q-radius-m);
  background:var(--q-ink-850); position:relative; overflow:hidden; font:12.5px/1.5 var(--q-font); color:var(--q-muted);
  transition:background var(--q-med), border-color var(--q-med); }
.notion-tools[hidden] { display:none !important; }
.notion-tools::before { content:''; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--q-notion); opacity:.55; }
.notion-tools-head { display:flex; gap:10px; align-items:flex-start; }
.notion-tools-dot { flex:none; width:8px; height:8px; margin-top:5px; border-radius:50%; background:var(--q-faint); transition:background var(--q-med); }
.notion-tools-copy { display:flex; flex-direction:column; gap:1px; min-width:0; }
.notion-tools-title { font:600 13px var(--q-font); color:var(--q-text-2); }
.notion-tools-operator { font-weight:500; color:var(--q-notion); }
.notion-tools-operator:not([data-operator="notion"]) { color:var(--q-text-2); }
.notion-tools-operator[data-operator="codex"] { color:var(--q-codex); }
.notion-tools-operator[data-operator="antigravity"] { color:var(--q-agy); }
.notion-tools-detail,.notion-tools-caps,.notion-tools-stop { color:var(--q-muted); overflow-wrap:anywhere; }
.notion-tools-stop { color:var(--q-faint); }
.notion-tools-details { margin:6px 0 0 18px; }
.notion-tools-details summary { cursor:pointer; color:var(--q-faint); font:12px var(--q-font); }
.notion-tools-details pre { margin:6px 0 0; font:12px/1.5 var(--q-mono); color:var(--q-muted); white-space:pre-wrap; overflow-wrap:anywhere; }
.notion-tools[data-availability="unavailable"]:not([data-state]) .notion-tools-dot { background:transparent; border:1.5px solid var(--q-faint); box-sizing:border-box; }
.notion-tools[data-availability="checking"]:not([data-state]) .notion-tools-dot { background:var(--q-warn); }
.notion-tools[data-availability="ready"]:not([data-state]) .notion-tools-dot { background:var(--q-ok); }
.notion-tools[data-availability="blocked"]:not([data-state]) { border-color:rgba(255,107,125,.35); }
.notion-tools[data-availability="blocked"]:not([data-state]) .notion-tools-dot { background:var(--q-danger); }
.notion-tools[data-state="observing"] .notion-tools-dot,.notion-tools[data-state="executing"] .notion-tools-dot,
.notion-tools[data-state="verifying"] .notion-tools-dot { background:var(--q-crystal); }
.notion-tools[data-state="executing"],.notion-tools[data-state="verifying"] { border-color:rgba(89,201,244,.35); }
.notion-tools[data-state="executing"]::before,.notion-tools[data-state="verifying"]::before { background:var(--q-facet); opacity:1; }
.notion-tools[data-state="awaiting_approval"] { border-color:rgba(242,196,107,.45); background:rgba(242,196,107,.06); }
.notion-tools[data-state="awaiting_approval"] .notion-tools-dot,.notion-tools[data-state="blocked"] .notion-tools-dot { background:var(--q-warn); }
.notion-tools[data-verification="verified"] .notion-tools-dot { background:var(--q-ok); }
.notion-tools[data-verification="verified"] .notion-tools-title { color:var(--q-text); }
.notion-tools[data-verification="observed"] .notion-tools-dot,.notion-tools[data-verification="unverified"] .notion-tools-dot { background:transparent; border:1.5px solid var(--q-warn); box-sizing:border-box; }
.notion-tools[data-state="failed"] { border-color:rgba(255,107,125,.4); }
.notion-tools[data-state="failed"] .notion-tools-dot { background:var(--q-danger); }
.notion-tools[data-state="cancelled"] .notion-tools-title,.notion-tools[data-state="unknown"] .notion-tools-title { color:var(--q-muted); }

/* Stop controls: immediate, never animated, always the strongest button. */
#btnDesktopTaskStop,#btnHudStopTask,#btnDesktopStop,#btnCancel { transition:none !important; animation:none !important; }
#btnDesktopTaskStop { background:var(--q-danger-strong) !important; border:1px solid var(--q-danger-strong) !important; color:#fff !important;
  font:600 13px var(--q-font) !important; padding:8px 14px !important; border-radius:var(--q-radius-s) !important; }
#btnDesktopTaskStop:hover { background:#ff4d63 !important; }
.screen-control-hud { top:8px !important; left:50% !important; transform:translateX(-50%) !important; right:auto !important;
  background:rgba(11,18,32,.96) !important; border:1px solid rgba(255,107,125,.45) !important; border-radius:999px !important;
  padding:5px 6px 5px 14px !important; gap:10px !important; box-shadow:0 8px 24px rgba(0,0,0,.45) !important; z-index:9999; }
.screen-control-hud .hud-dot { background:var(--q-danger) !important; }
.screen-control-hud .hud-title { font:600 12px var(--q-font) !important; letter-spacing:.02em !important; color:var(--q-text) !important; }
.screen-control-hud .hud-sub { font:12px var(--q-font) !important; color:var(--q-muted) !important; }
#btnHudStopTask { background:var(--q-danger-strong) !important; color:#fff !important; border:0 !important; border-radius:999px !important;
  font:600 12.5px var(--q-font) !important; padding:7px 14px !important; }

/* Conversation ---------------------------------------------------------------- */
.chat { padding:22px max(28px,calc((100% - 760px)/2)) 12px !important; gap:22px !important; }
.msg { margin-bottom:6px !important; }
.msg-meta { gap:8px !important; align-items:baseline; }
.msg-sender-tag,.msg-sender-tag.tag-user,.msg-sender-tag.tag-quartz { font:600 13px var(--q-font) !important; color:var(--q-text-2) !important; }
.msg-sender-tag.tag-codex { color:var(--q-codex) !important; }
.msg-sender-tag.tag-antigravity { color:var(--q-agy) !important; }
.msg-sender-tag.tag-notion { color:var(--q-notion) !important; }
.msg-ts,.msg-model-tag,.msg-seq-tag { font:12px var(--q-font) !important; color:var(--q-faint) !important; letter-spacing:0 !important; text-transform:none !important; }
.msg-model-tag { padding:1px 7px !important; border-radius:999px !important; background:var(--q-ink-800) !important; border:1px solid var(--q-line) !important; }
.msg .bubble { font:15px/1.65 var(--q-font) !important; color:var(--q-text) !important; max-width:72ch; }
.msg.bot .bubble > div { white-space:pre-wrap; }
.msg.bot.sender-codex,.msg.bot.sender-antigravity,.msg.bot.sender-notion { padding-left:14px; border-left:2px solid var(--q-line); }
.msg.bot.sender-codex { border-left-color:rgba(127,214,255,.45); }
.msg.bot.sender-antigravity { border-left-color:rgba(185,162,255,.45); }
.msg.user .bubble { background:var(--q-ink-700) !important; border:1px solid var(--q-line) !important; border-radius:var(--q-radius-l) var(--q-radius-l) 6px var(--q-radius-l) !important;
  padding:11px 16px !important; }
.msg.user .msg-meta { justify-content:flex-end; }
.msg.err .bubble { color:#ffd5da !important; border-left:2px solid var(--q-danger) !important; padding-left:12px !important; }
.msg.sys .bubble { font-size:13px !important; color:var(--q-muted) !important; }
.msg-code { margin:10px 0; border:1px solid var(--q-line); border-radius:var(--q-radius-s); background:var(--q-ink-950); overflow:hidden; }
.msg-code-lang { display:block; padding:5px 12px; font:12px var(--q-font); color:var(--q-faint); border-bottom:1px solid var(--q-line); background:var(--q-ink-850); }
.msg-code pre { margin:0; padding:12px 14px; overflow:auto; font:13px/1.55 var(--q-mono); color:#dbe6f6; white-space:pre; tab-size:4; }
.technical-details summary { color:var(--q-muted) !important; font:12.5px var(--q-font) !important; cursor:pointer; }
.technical-details pre { font:12.5px/1.55 var(--q-mono) !important; color:var(--q-text-2) !important; }

/* Permission / coordination cards */
.coordination-card { background:var(--q-ink-850) !important; border:1px solid var(--q-line-strong) !important; border-radius:var(--q-radius-l) !important;
  padding:16px 18px !important; gap:10px !important; align-items:center; max-width:760px; }
.coordination-card > strong { width:100%; font:600 15px var(--q-font) !important; color:var(--q-text) !important; }
.coordination-card p { font:13px/1.6 var(--q-font) !important; color:var(--q-text-2) !important; }
.coordination-card details { width:100%; order:9; }
.coordination-card details summary { font:12.5px var(--q-font); color:var(--q-muted); cursor:pointer; }
.coordination-card details pre { font:12px/1.5 var(--q-mono); color:var(--q-muted); white-space:pre-wrap; }
.coordination-card > p:last-child:empty { display:none; }
[data-natural-permission] { border-color:rgba(242,196,107,.45) !important; box-shadow:inset 3px 0 0 var(--q-warn); }
[data-natural-permission] > button:first-of-type { background:var(--q-text) !important; color:var(--q-ink-900) !important; border-color:var(--q-text) !important; font-weight:600 !important; }
[data-natural-permission] > button:first-of-type:hover:not(:disabled) { background:#fff !important; color:var(--q-ink-950) !important; }
.diagnostics-card { border-radius:var(--q-radius-l) !important; }

/* Thinking + jump */
.thinking-row { max-width:760px !important; color:var(--q-muted) !important; font:13px var(--q-font) !important; }
.thinking-row .d { background:var(--q-crystal) !important; }
.jump-bottom-btn { background:var(--q-ink-700) !important; color:var(--q-text) !important; border:1px solid var(--q-line-strong) !important;
  border-radius:999px !important; font:500 12.5px var(--q-font) !important; }

/* Composer */
.inputbar { max-width:760px !important; width:calc(100% - 56px) !important; margin:8px auto 20px !important; background:var(--q-ink-800) !important;
  border:1px solid var(--q-line-strong) !important; border-radius:var(--q-radius-l) !important; padding:7px 8px 7px 14px !important;
  transition:border-color var(--q-fast), box-shadow var(--q-fast); }
.inputbar:focus-within { border-color:rgba(89,201,244,.6) !important; box-shadow:0 0 0 4px var(--q-crystal-soft) !important; }
#msgInput { font:15px var(--q-font) !important; color:var(--q-text) !important; }
#msgInput:focus-visible { outline:none !important; }
#msgInput::placeholder { color:var(--q-faint) !important; }
#btnSend { background:var(--q-facet) !important; color:var(--q-ink-950) !important; border:0 !important; border-radius:11px !important;
  width:38px; height:38px; font-size:15px; }
#btnSend.disabled { filter:saturate(.3) brightness(.7); }
#btnMic { color:var(--q-muted) !important; }

/* Panels and dialogs */
body.show-panels .rail.right { background:var(--q-ink-850) !important; border-left:1px solid var(--q-line) !important; top:52px !important;
  box-shadow:-24px 0 48px rgba(0,0,0,.45) !important; }
.rail.right .card { background:var(--q-ink-800) !important; border:1px solid var(--q-line) !important; border-radius:var(--q-radius-m) !important; }
.rail.right .card-label { text-transform:none !important; letter-spacing:0 !important; font:600 12.5px var(--q-font) !important; color:var(--q-muted) !important; }
.log-box { font:12px/1.5 var(--q-mono) !important; color:var(--q-text-2) !important; }
.agent-overlay,.api-setup { background:rgba(4,8,16,.72) !important; }
.agent-panel,.api-panel { background:var(--q-ink-850) !important; border:1px solid var(--q-line-strong) !important; border-radius:var(--q-radius-l) !important;
  box-shadow:0 24px 64px rgba(0,0,0,.55) !important; }
/* Agent centre (diagnostics) and side panel details */
.agent-head h2 { font:600 17px var(--q-font) !important; letter-spacing:0 !important; color:var(--q-text) !important; }
.agent-head .agent-sub { font:12px var(--q-font) !important; letter-spacing:0 !important; color:var(--q-faint) !important; }
.agent-status-card,.agent-row,.agent-column { background:var(--q-ink-800) !important; border:1px solid var(--q-line) !important; border-radius:var(--q-radius-m) !important; }
.agent-status-card strong { font:600 12.5px var(--q-font) !important; letter-spacing:0 !important; color:var(--q-text-2) !important; }
.agent-status-card span { font:12px var(--q-font) !important; color:var(--q-muted) !important; }
.agent-column h3 { font:600 12.5px var(--q-font) !important; letter-spacing:0 !important; color:var(--q-muted) !important; }
.agent-prompt { background:var(--q-ink-950) !important; border:1px solid var(--q-line) !important; border-radius:var(--q-radius-m) !important;
  color:var(--q-text) !important; font:14px/1.5 var(--q-font) !important; }
.agent-panel > div[style*="border"] { border-color:var(--q-line-strong) !important; border-radius:var(--q-radius-m) !important; background:var(--q-ink-800); }
.agent-error { color:var(--q-muted) !important; font:12px var(--q-font) !important; }
.stat-fill { background:var(--q-crystal) !important; }
.stat-fill.warn { background:var(--q-warn) !important; }
.stat-fill.crit { background:var(--q-danger) !important; }
.stat-bar { background:var(--q-ink-600) !important; }
#legacyTools summary { font:500 13px var(--q-font); color:var(--q-muted); cursor:pointer; padding:6px 2px; }
.api-submit { background:var(--q-text) !important; color:var(--q-ink-900) !important; border-radius:var(--q-radius-s) !important; font:600 13px var(--q-font) !important; }

/* Motion: answers to state changes only ----------------------------------------- */
@keyframes q-msg-in { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
@keyframes q-fade-in { from { opacity:0; } to { opacity:1; } }
@keyframes q-rise-in { from { opacity:0; transform:translateY(10px) scale(.985); } to { opacity:1; transform:none; } }
@keyframes q-slide-in { from { transform:translateX(24px); opacity:0; } to { transform:none; opacity:1; } }
@keyframes q-pulse { 0%,100% { opacity:.35; transform:translateY(0); } 50% { opacity:1; transform:translateY(-2px); } }
/* Animations exist only when the user has no reduced-motion preference and the
   low-spec optimiser is off; nothing has to out-rank them to switch them off. */
@media (prefers-reduced-motion: no-preference) {
  body:not(.low-spec) .msg,body:not(.low-spec) .coordination-card,body:not(.low-spec) .diagnostics-card { animation:q-msg-in var(--q-med) var(--q-ease) both !important; }
  body:not(.low-spec) .agent-overlay.show,body:not(.low-spec) .api-setup.show { animation:q-fade-in var(--q-med) ease-out both !important; }
  body:not(.low-spec) .agent-overlay.show .agent-panel,body:not(.low-spec) .api-setup.show .api-panel { animation:q-rise-in var(--q-med) var(--q-ease) both !important; }
  body.show-panels:not(.low-spec) .rail.right { animation:q-slide-in var(--q-med) var(--q-ease) both !important; }
  body:not(.low-spec):not(.ui-idle) .thinking-row.show .d { animation:q-pulse 1.1s ease-in-out infinite !important; }
  body:not(.low-spec):not(.ui-idle) .thinking-row.show .d:nth-child(2) { animation-delay:.15s !important; }
  body:not(.low-spec):not(.ui-idle) .thinking-row.show .d:nth-child(3) { animation-delay:.3s !important; }
  body:not(.low-spec) .jump-bottom-btn.show { animation:q-fade-in var(--q-fast) ease-out both !important; }
  body:not(.low-spec) .notion-tools:not([hidden]) { animation:q-fade-in var(--q-fast) ease-out both !important; }
}

@media (prefers-reduced-motion: reduce) {
  *,*::before,*::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; }
}
body.low-spec *,body.low-spec *::before,body.low-spec *::after { animation:none !important; transition:none !important; }

/* Narrow windows */
@media (max-width:900px) {
  .chat-header { padding:12px 18px 10px !important; }
  .desktop-task-bar { margin:8px 18px 0 !important; }
  .notion-tools { margin:8px 18px 0; }
  .chat { padding:18px 18px 10px !important; }
  .inputbar { width:calc(100% - 36px) !important; }
  .msg .bubble { max-width:100%; }
}
"""
