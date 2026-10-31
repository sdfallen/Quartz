"""Quartz base theme stylesheet.

Extracted verbatim from the former inline ``<style>`` block of ``gui.py``.
Kept as a Python module (not a ``.css`` data file) so PyInstaller bundles it
through normal import analysis of ``gui`` without any ``Quartz.spec`` change.

``assets/workspace.css`` is still appended after this sheet at document build
time, so later rules there keep overriding these exactly as before.
"""

BASE_CSS = r"""  :root {
    --bg-void:   #030608;
    --glass:     rgba(14, 26, 38, 0.55);
    --glass-brd: rgba(52, 234, 255, 0.14);
    --cyan:      #34eaff;
    --violet:    #7c6cff;
    --amber:     #ffb454;
    --red:       #ff5c72;
    --mint:      #34ffc0;
    --txt:       #eaf6ff;
    --txt-dim:   #6d8ea3;
    --txt-faint: #3d5b6c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    height: 100%; width: 100%;
    background: radial-gradient(ellipse at 50% -10%, #0b1620 0%, #030608 55%, #010203 100%);
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
    color: var(--txt);
    overflow: hidden;
    user-select: none;
  }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-thumb { background: rgba(52,234,255,0.15); border-radius: 3px; }

  .shell {
    display: flex; flex-direction: column;
    height: 100vh; width: 100vw;
    border: 1px solid rgba(52,234,255,0.18);
  }

  /* ── Title bar (drag region) ─────────────────────────── */
  .titlebar {
    display: flex; align-items: center; gap: 12px;
    height: 46px; flex-shrink: 0;
    padding: 0 10px 0 16px;
    background: rgba(8, 16, 24, 0.7);
    border-bottom: 1px solid rgba(52,234,255,0.1);
  }
  .orb-wrap { position: relative; width: 26px; height: 26px; flex-shrink: 0; }
  .orb-ring {
    position: absolute; inset: -5px; border-radius: 50%;
    background: conic-gradient(from 0deg, transparent 0%, var(--cyan) 10%, transparent 26%, transparent 100%);
    animation: spin 3.2s linear infinite;
  }
  .orb-core {
    position: absolute; inset: 0; border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #8ff6ff 0%, #17b7d6 45%, #063a47 100%);
    box-shadow: 0 0 14px 2px rgba(52,234,255,0.55), 0 0 28px 8px rgba(52,234,255,0.16);
    animation: breathe 2.6s ease-in-out infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes breathe {
    0%, 100% { transform: scale(1); filter: brightness(1); }
    50%      { transform: scale(1.08); filter: brightness(1.18); }
  }
  body.ui-idle .orb-ring, body.ui-idle .orb-core,
  body.low-spec:not(.thinking-active) .orb-ring, body.low-spec:not(.thinking-active) .orb-core {
    animation-play-state: paused;
  }
  .brand {
    font-family: 'Rajdhani', sans-serif; font-weight: 700;
    font-size: 15px; letter-spacing: 0.14em; color: var(--txt);
  }
  .status-pill {
    display: flex; align-items: center; gap: 6px;
    font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: 11px; letter-spacing: 0.06em; color: var(--txt-dim);
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 20px; padding: 3px 12px;
    margin-left: 6px;
  }
  .status-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--amber); }
  .status-pill.online .dot { background: var(--mint); box-shadow: 0 0 6px var(--mint); }
  .status-pill.offline .dot { background: var(--red); box-shadow: 0 0 6px var(--red); }

  .titlebar-spacer { flex: 1; }
  .clock {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; color: var(--txt-dim); letter-spacing: 0.03em;
    margin-right: 8px; text-align: right; line-height: 1.3;
  }
  .win-btn {
    -webkit-app-region: no-drag;
    width: 30px; height: 30px; border-radius: 8px;
    border: none; background: transparent; color: var(--txt-dim);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; font-size: 13px; transition: all .15s ease;
  }
  .win-btn:hover { background: rgba(255,255,255,0.06); color: var(--txt); }
  .win-btn.close:hover { background: var(--red); color: #1a0407; }

  /* ── Body layout ──────────────────────────────────────── */
  .body { flex: 1; display: flex; min-height: 0; padding: 10px; gap: 10px; }

  .rail { width: 158px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
  .rail.right { width: 172px; }

  .card {
    background: var(--glass);
    border: 1px solid var(--glass-brd);
    border-radius: 12px;
    backdrop-filter: blur(14px);
    padding: 10px;
  }
  .card-label {
    font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: 10.5px; letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--txt-faint); margin-bottom: 8px;
  }

  .qa-btn {
    -webkit-app-region: no-drag;
    width: 100%; text-align: left;
    font-family: 'Rajdhani', sans-serif; font-weight: 600; font-size: 12.5px;
    letter-spacing: 0.02em; color: var(--txt-dim);
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px; padding: 8px 10px; margin-bottom: 6px;
    cursor: pointer; transition: all .15s ease;
    display: flex; align-items: center; gap: 8px;
  }
  .qa-btn:last-child { margin-bottom: 0; }
  .qa-btn:hover { color: var(--cyan); border-color: rgba(52,234,255,0.3); background: rgba(52,234,255,0.05); }
  .qa-btn .ic { font-size: 13px; opacity: 0.85; }
  .qa-btn.quartz-mode { color:#bdb5ff; border-color:rgba(124,108,255,.2); background:rgba(124,108,255,.06); }
  .qa-btn.quartz-mode:hover { color:#e2ddff; border-color:rgba(124,108,255,.55); background:rgba(124,108,255,.14); box-shadow:0 0 16px rgba(124,108,255,.10); }

  .stat-row { margin-bottom: 9px; }
  .stat-row:last-child { margin-bottom: 0; }
  .stat-top {
    display: flex; justify-content: space-between; align-items: baseline;
    font-family: 'JetBrains Mono', monospace; font-size: 10.5px;
    color: var(--txt-dim); margin-bottom: 4px;
  }
  .stat-top .val { color: var(--cyan); font-weight: 500; }
  .stat-bar { height: 4px; border-radius: 2px; background: rgba(255,255,255,0.06); overflow: hidden; }
  .stat-fill { height: 100%; border-radius: 2px; background: var(--cyan); width: 0%; transition: width .4s ease; }
  .stat-fill.warn { background: var(--amber); }
  .stat-fill.crit { background: var(--red); }

  .sess-row {
    display: flex; justify-content: space-between;
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--txt-dim); padding: 3px 0;
  }
  .sess-row .val { color: var(--cyan); }

  .log-box {
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
    color: var(--txt-faint); line-height: 1.7;
    max-height: 130px; overflow-y: auto;
  }
  .log-box div span { color: #3d5b6c; }

  /* ── Chat column ──────────────────────────────────────── */
  .chat-col { flex: 1; display: flex; flex-direction: column; min-width: 0; position: relative; }
  .chat {
    flex: 1; overflow-y: auto; overflow-anchor: none;
    display: flex; flex-direction: column; gap: 10px;
    padding: 6px 4px 14px;
  }
  .msg { display: flex; max-width: 82%; }
  .msg.user { align-self: flex-end; }
  .msg.bot  { align-self: flex-start; }
  .msg.sys  { align-self: center; max-width: 90%; }
  .bubble {
    padding: 10px 14px; border-radius: 13px;
    font-size: 13.5px; line-height: 1.55;
    backdrop-filter: blur(12px);
    white-space: pre-wrap;
  }
  .msg.bot .bubble {
    background: rgba(20,38,50,0.55);
    border: 1px solid rgba(52,234,255,0.12);
    border-left: 2px solid var(--cyan);
    color: #d7f2fb; border-top-left-radius: 4px;
  }
  .msg.user .bubble {
    background: rgba(52,234,255,0.1);
    border: 1px solid rgba(52,234,255,0.22);
    color: var(--txt); border-top-right-radius: 4px;
  }
  .msg.sys .bubble {
    background: transparent; border: none;
    color: var(--txt-faint); font-size: 11px; font-style: italic;
    text-align: center; padding: 2px 8px;
  }
  .msg.err .bubble {
    background: rgba(255,92,114,0.08);
    border: 1px solid rgba(255,92,114,0.3);
    color: #ffc2ca;
  }
  .msg-meta {
    font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--txt-faint); margin-bottom: 3px; padding: 0 2px;
  }

  .thinking-row {
    display: flex; align-items: center; gap: 6px;
    font-family: 'Rajdhani', sans-serif; font-size: 11px;
    color: var(--amber); padding: 0 6px 6px; height: 16px;
    opacity: 0; transition: opacity .2s ease;
  }
  .thinking-row.show { opacity: 1; }
  .thinking-row .d { width: 4px; height: 4px; border-radius: 50%; background: var(--amber); animation: pulse 1s infinite ease-in-out; }
  .thinking-row .d:nth-child(2) { animation-delay: .15s; }
  .thinking-row .d:nth-child(3) { animation-delay: .3s; }
  @keyframes pulse { 0%,100% { opacity: .3; } 50% { opacity: 1; } }

  .inputbar {
    display: flex; align-items: center; gap: 8px;
    background: rgba(15,28,38,0.65);
    border: 1px solid rgba(52,234,255,0.15);
    border-radius: 22px; padding: 5px 6px 5px 16px;
    backdrop-filter: blur(16px);
    transition: border-color .2s ease, box-shadow .2s ease;
  }
  .inputbar:focus-within { border-color: rgba(52,234,255,0.55); box-shadow: 0 0 0 3px rgba(52,234,255,0.08); }
  .inputbar input {
    flex: 1; background: none; border: none; outline: none;
    color: var(--txt); font-family: 'Inter', sans-serif; font-size: 13.5px;
  }
  .inputbar input::placeholder { color: #43606e; }
  .icon-btn {
    -webkit-app-region: no-drag;
    width: 32px; height: 32px; border-radius: 50%; border: none;
    display: flex; align-items: center; justify-content: center;
    color: var(--txt-dim); background: rgba(255,255,255,0.04);
    cursor: pointer; transition: all .15s ease; flex-shrink: 0;
  }
  .icon-btn:hover { color: var(--cyan); background: rgba(52,234,255,0.1); }
  .icon-btn.send { color: #04222a; background: var(--cyan); }
  .icon-btn.send:hover { background: #6ff2ff; }
  .icon-btn.disabled { opacity: 0.4; pointer-events: none; }
  .icon-btn.mic.listening {
    color: #04222a; background: var(--violet);
    animation: mic-pulse 1s infinite ease-in-out;
  }
  @keyframes mic-pulse {
    0%,100% { box-shadow: 0 0 0 0 rgba(124,108,255,0.5); }
    50%     { box-shadow: 0 0 0 8px rgba(124,108,255,0); }
  }

  .voice-toggle {
    -webkit-app-region: no-drag;
    display: flex; align-items: center; gap: 4px;
    font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: 10.5px; letter-spacing: 0.05em; color: var(--txt-dim);
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px; padding: 4px 10px;
    cursor: pointer; transition: all .15s ease; margin-right: 4px;
  }
  .voice-toggle:hover { border-color: rgba(52,234,255,0.25); }
  .voice-toggle.active {
    color: #1c1030; background: var(--violet); border-color: var(--violet);
  }
  .action-card {
    align-self: stretch; margin: 2px 16px; padding: 12px;
    border-radius: 12px; border: 1px solid rgba(255,180,84,.45);
    background: rgba(70,45,12,.35); color: var(--txt); font-size: 12px;
  }
  .action-card .actions { display:flex; gap:8px; margin-top:10px; }
  .action-card button, .control-btn {
    border: 1px solid rgba(52,234,255,.3); border-radius: 8px;
    background: rgba(52,234,255,.08); color: var(--cyan);
    padding: 6px 10px; cursor:pointer;
  }
  .action-card button.danger { color:#ffc2ca; border-color:rgba(255,92,114,.4); }
  .control-btn.active { background: var(--mint); color:#04221a; }
  .mobile-access-card { border-color:rgba(52,234,255,.22)!important; background:linear-gradient(135deg,rgba(11,34,46,.88),rgba(10,20,30,.75))!important; }
  .mobile-access-card .mobile-label { font-family:'Rajdhani',sans-serif; color:var(--txt-faint); font-size:10px; letter-spacing:.13em; margin:10px 0 4px; }
  .mobile-access-card .mobile-label:first-child { margin-top:0; }
  .mobile-access-card .mobile-value { color:var(--txt-dim); font-family:'JetBrains Mono',monospace; font-size:11px; overflow-wrap:anywhere; }
  .mobile-access-card .mobile-token { color:var(--cyan); padding:8px 9px; border:1px solid rgba(52,234,255,.18); border-radius:8px; background:rgba(3,10,15,.45); }
  .mobile-card-action { display:inline-flex; align-items:center; gap:6px; margin-top:11px; border:1px solid rgba(52,234,255,.3); border-radius:8px; background:rgba(52,234,255,.08); color:var(--cyan); padding:7px 10px; font-family:'Rajdhani',sans-serif; font-size:11px; font-weight:700; letter-spacing:.06em; cursor:pointer; transition:all .15s ease; }
  .mobile-card-action:hover { background:rgba(52,234,255,.16); border-color:rgba(52,234,255,.55); }
  .mobile-card-action:disabled { opacity:.7; cursor:default; }

  .agent-overlay {
    position:fixed; inset:46px 0 0; z-index:80; display:none;
    align-items:center; justify-content:center; padding:18px;
    background:rgba(1,4,7,.9); backdrop-filter:blur(18px);
  }
  .agent-overlay.show { display:flex; }
  .agent-panel {
    width:min(900px,96vw); height:min(620px,88vh); min-height:480px;
    display:flex; flex-direction:column; gap:11px; padding:16px;
    border:1px solid rgba(52,234,255,.24); border-radius:16px;
    background:linear-gradient(145deg,rgba(9,22,31,.98),rgba(3,9,14,.98));
    box-shadow:0 26px 90px rgba(0,0,0,.6),0 0 36px rgba(52,234,255,.05);
  }
  .agent-head { display:flex; align-items:center; gap:10px; }
  .agent-head h2 { font:700 18px 'Rajdhani',sans-serif; letter-spacing:.12em; }
  .agent-head .agent-sub { color:var(--txt-faint); font-size:10px; flex:1; }
  .agent-select, .agent-input, .agent-prompt {
    border:1px solid rgba(52,234,255,.16); border-radius:9px;
    background:#061017; color:var(--txt); outline:none; padding:8px 10px;
    font:11px 'Inter',sans-serif; user-select:text;
  }
  .agent-select:focus, .agent-input:focus, .agent-prompt:focus { border-color:rgba(52,234,255,.55); }
  .agent-status-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
  .agent-status-card { padding:9px; border:1px solid rgba(255,255,255,.06); border-radius:10px; background:rgba(255,255,255,.025); }
  .agent-status-card strong { display:block; font:600 11px 'Rajdhani',sans-serif; color:var(--cyan); letter-spacing:.08em; }
  .agent-status-card span { display:block; margin-top:4px; color:var(--txt-dim); font:10px 'JetBrains Mono',monospace; white-space:pre-wrap; }
  .agent-compose { display:grid; grid-template-columns:1fr 150px; gap:8px; }
  .agent-prompt { resize:none; min-height:68px; }
  .agent-compose-side { display:flex; flex-direction:column; gap:7px; }
  .agent-check { color:var(--amber); font-size:10px; display:flex; gap:6px; align-items:flex-start; }
  .agent-check input { accent-color:var(--amber); }
  .agent-columns { flex:1; min-height:0; display:grid; grid-template-columns:1.15fr 1fr 1fr; gap:8px; }
  .agent-column { min-height:0; display:flex; flex-direction:column; padding:9px; border:1px solid rgba(52,234,255,.09); border-radius:10px; background:rgba(1,7,11,.42); }
  .agent-column h3 { font:600 10px 'Rajdhani',sans-serif; letter-spacing:.11em; color:var(--txt-faint); margin-bottom:7px; }
  .agent-scroll { overflow:auto; min-height:0; color:var(--txt-dim); font:10px/1.55 'JetBrains Mono',monospace; }
  .agent-row { padding:7px 0; border-bottom:1px solid rgba(255,255,255,.045); overflow-wrap:anywhere; }
  .agent-row strong { color:var(--txt); font-weight:500; }
  .agent-row .ok { color:var(--mint); } .agent-row .bad { color:var(--red); } .agent-row .wait { color:var(--amber); }
  .agent-error { min-height:15px; color:#ffc2ca; font-size:10px; }
  body.compact .agent-overlay { display:none!important; }

  /* ── Chat Top Bar & Agent Selector ──────────────────── */
  .rail { display: none; }
  body.show-panels .rail { display: flex; }
  body:not(.show-panels):not(.compact) .chat-col {
    max-width: 920px; margin: 0 auto; width: 100%;
  }
  .chat-header {
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 10px;
    padding: 10px 14px; margin-bottom: 8px;
    background: rgba(8, 20, 30, 0.78); border: 1px solid rgba(52, 234, 255, 0.18);
    border-radius: 14px; backdrop-filter: blur(12px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
  }
  .chat-title-group { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .chat-conv-title {
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 14px;
    color: var(--txt); letter-spacing: 0.05em; max-width: 200px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .agent-seg-group {
    display: inline-flex; align-items: center; gap: 4px;
    background: rgba(3, 10, 16, 0.9);
    border: 1px solid rgba(52, 234, 255, 0.22);
    border-radius: 11px; padding: 3px;
  }
  .agent-seg-btn {
    -webkit-app-region: no-drag;
    border: none; background: transparent; color: var(--txt-dim);
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 12px;
    letter-spacing: 0.06em; padding: 5px 12px; border-radius: 8px;
    cursor: pointer; transition: all .15s ease;
  }
  .agent-seg-btn:hover { color: var(--txt); background: rgba(255, 255, 255, 0.05); }
  .agent-seg-btn.active[data-agent="antigravity"] {
    background: rgba(52, 234, 255, 0.18); color: var(--cyan);
    box-shadow: 0 0 12px rgba(52, 234, 255, 0.2);
  }
  .agent-seg-btn.active[data-agent="codex"] {
    background: rgba(124, 108, 255, 0.22); color: #d5cdff;
    box-shadow: 0 0 12px rgba(124, 108, 255, 0.22);
  }
  .agent-seg-btn.active[data-agent="collaboration"] {
    background: rgba(255, 180, 84, 0.2); color: var(--amber);
    box-shadow: 0 0 12px rgba(255, 180, 84, 0.2);
  }
  .chat-controls-group { display: flex; align-items: center; gap: 8px; }
  .agent-badge-select {
    display: flex; align-items: center; gap: 5px;
    background: rgba(4, 12, 18, 0.85); border: 1px solid rgba(52, 234, 255, 0.22);
    border-radius: 18px; padding: 2px 8px; font-family: 'Rajdhani', sans-serif;
    font-weight: 600; font-size: 11px; color: var(--cyan);
  }
  .agent-badge-select select {
    background: transparent; border: none; color: var(--cyan);
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 11.5px;
    letter-spacing: 0.05em; outline: none; cursor: pointer;
  }
  .agent-badge-select select option { background: #06111a; color: var(--txt); }
  .chat-tool-btn {
    background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px; color: var(--txt-dim); font-size: 11px;
    padding: 5px 10px; cursor: pointer; font-family: 'Inter', sans-serif;
    transition: all .15s ease;
  }
  .chat-tool-btn:hover { background: rgba(52, 234, 255, 0.12); color: var(--cyan); border-color: rgba(52, 234, 255, 0.3); }
  .project-tag {
    font-size: 10px; color: var(--cyan); font-family: 'JetBrains Mono', monospace;
    background: rgba(52, 234, 255, 0.08); padding: 2px 7px; border-radius: 5px; border: 1px solid rgba(52, 234, 255, 0.2);
  }
  .project-picker {
    max-width: 145px; background: rgba(52,234,255,.08); color: var(--cyan);
    border: 1px solid rgba(52,234,255,.24); border-radius: 5px;
    font: 10px 'JetBrains Mono', monospace; padding: 3px 5px;
  }
  .project-picker option { background: #07141b; color: #d5faff; }
  .squad-badge {
    font-size: 10px; font-family: 'JetBrains Mono', monospace;
    padding: 2px 7px; border-radius: 5px;
    background: rgba(61, 220, 151, 0.12); color: #3ddc97;
    border: 1px solid rgba(61, 220, 151, 0.3);
  }
  .squad-badge.warn {
    background: rgba(255, 92, 114, 0.14); color: #ff8c9c;
    border-color: rgba(255, 92, 114, 0.36);
  }
  .msg-progress-box {
    margin-top: 6px; padding: 6px 8px; border-radius: 6px;
    background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(52, 234, 255, 0.08);
    font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--txt-dim);
  }
  .msg-sender-tag {
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 10px;
    letter-spacing: 0.08em; text-transform: uppercase; margin-right: 6px;
  }
  .msg-seq-tag {
    display: inline-block; font-family: 'JetBrains Mono', monospace;
    font-size: 9px; color: var(--txt-faint); margin-right: 6px;
  }
  .msg-model-tag {
    display: inline-block; font-family: 'JetBrains Mono', monospace;
    font-size: 9px; color: var(--txt-dim); background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 4px;
    padding: 0 5px; margin-right: 6px;
  }
  .chat-models-bar {
    width: 100%; display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 8px; padding-top: 7px;
    border-top: 1px solid rgba(52, 234, 255, 0.1);
  }
  .model-selector-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 9px; border-radius: 9px;
    background: rgba(3, 10, 16, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.09);
    font-family: 'Rajdhani', sans-serif; font-size: 11px; color: var(--txt-dim);
    transition: all .15s ease;
  }
  .model-selector-pill.active-agy {
    border-color: rgba(52, 234, 255, 0.36);
    background: rgba(52, 234, 255, 0.06);
  }
  .model-selector-pill.active-codex {
    border-color: rgba(124, 108, 255, 0.42);
    background: rgba(124, 108, 255, 0.08);
  }
  .model-selector-pill .pill-agent-name {
    font-weight: 700; letter-spacing: 0.06em; font-size: 10.5px;
  }
  .model-selector-pill.active-agy .pill-agent-name { color: var(--cyan); }
  .model-selector-pill.active-codex .pill-agent-name { color: #d5cdff; }
  .model-selector-pill select {
    -webkit-app-region: no-drag;
    background: rgba(8, 20, 30, 0.9); color: var(--txt);
    border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px;
    padding: 2px 6px; font-family: 'JetBrains Mono', monospace; font-size: 10.5px;
    outline: none; cursor: pointer;
  }
  .model-selector-pill select:hover,
  .model-selector-pill select:focus {
    border-color: rgba(52, 234, 255, 0.45);
  }
  .model-selector-pill select option { background: #06111a; color: var(--txt); }
  .model-selector-pill .pill-sep { color: var(--txt-faint); font-size: 10px; }
  .jump-bottom-btn {
    -webkit-app-region: no-drag;
    position: absolute; right: 18px; bottom: 72px; z-index: 30;
    display: none; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 18px;
    background: rgba(8, 24, 36, 0.95);
    border: 1px solid rgba(52, 234, 255, 0.5);
    color: var(--cyan); font-family: 'Rajdhani', sans-serif;
    font-weight: 700; font-size: 12px; letter-spacing: 0.06em;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.6), 0 0 14px rgba(52, 234, 255, 0.24);
    cursor: pointer; transition: all .15s ease;
  }
  .jump-bottom-btn.show { display: inline-flex; }
  .jump-bottom-btn:hover { background: rgba(52, 234, 255, 0.2); color: #fff; }
  .tag-antigravity { background: rgba(52, 234, 255, 0.16); color: var(--cyan); border: 1px solid rgba(52, 234, 255, 0.34); }
  .tag-codex { background: rgba(124, 108, 255, 0.18); color: #d5cdff; border: 1px solid rgba(124, 108, 255, 0.38); }
  .tag-collaboration { background: rgba(255, 180, 84, 0.15); color: var(--amber); border: 1px solid rgba(255, 180, 84, 0.3); }
  .tag-user { background: rgba(255, 255, 255, 0.1); color: var(--txt); }
  .msg.bot.sender-antigravity .bubble {
    border-left: 3px solid rgba(52, 234, 255, 0.65);
  }
  .msg.bot.sender-codex .bubble {
    border-left: 3px solid rgba(124, 108, 255, 0.75);
    background: rgba(16, 14, 34, 0.78);
  }

  /* Compact companion: same visual language, chat-only footprint. */
  body.compact .shell {
    border-color: rgba(52,234,255,.32);
    box-shadow: inset 0 0 34px rgba(52,234,255,.025);
  }
  body.compact .titlebar { height: 48px; padding-left: 14px; }
  body.compact .titlebar .status-pill,
  body.compact .titlebar .voice-toggle,
  body.compact .titlebar .clock { display: none; }
  body.compact .body { padding: 9px; }
  body.compact .rail { display: none !important; }
  body.compact .chat { gap: 8px; padding: 4px 2px 10px; }
  body.compact .msg { max-width: 92%; }
  body.compact .bubble { font-size: 12.5px; padding: 8px 11px; }
  body.compact .msg-meta { font-size: 9px; }
  body.compact .inputbar { padding-left: 13px; }
  body.compact .inputbar input { font-size: 12.5px; }
  body.compact #btnMic { display: none; }
  body.compact #btnMin {
    color: var(--cyan); background: rgba(52,234,255,.08);
  }
  .signature-main {
    position: fixed; right: 14px; bottom: 7px; z-index: 5;
    font-family: 'Rajdhani', sans-serif; font-size: 11px;
    font-weight: 500; letter-spacing: .1em; color: rgba(157,190,208,.68);
    padding: 3px 7px; border-radius: 7px;
    background: rgba(3,8,12,.42);
    width: 172px; text-align: center; line-height: 1.25;
    pointer-events: none;
  }
  .signature-main span, .signature-main strong { display: block; }
  .signature-main strong {
    color: rgba(52,234,255,.82); font-weight: 700; margin-top: 2px;
  }
  .signature-mark {
    display: none; align-items: center; justify-content: center;
    width: 25px; height: 25px; border-radius: 8px;
    border: 1px solid rgba(52,234,255,.22);
    color: rgba(52,234,255,.78); background: rgba(52,234,255,.045);
    font-family: 'Rajdhani', sans-serif; font-weight: 700;
    font-size: 10px; letter-spacing: .08em; margin-right: 2px;
  }
  body.compact .signature-main,
  body:not(.show-panels) .signature-main { display: none; }
  body.compact .signature-mark,
  body:not(.show-panels) .signature-mark { display: flex; }
  .signature-intro {
    position: fixed; inset: 0; z-index: 100;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: radial-gradient(circle at center, rgba(11,28,38,.98), rgba(1,2,3,.995) 68%);
    pointer-events: none; animation: signature-reveal 1.8s ease forwards;
  }
  .signature-intro .intro-brand {
    font-family: 'Rajdhani', sans-serif; font-weight: 700;
    font-size: 26px; letter-spacing: .28em; color: var(--txt);
    text-shadow: 0 0 22px rgba(52,234,255,.32);
  }
  .signature-intro .intro-credit {
    margin-top: 12px; font-family: 'Rajdhani', sans-serif;
    font-size: 11px; letter-spacing: .18em; color: var(--txt-dim);
  }
  .signature-intro .intro-credit strong { color: var(--cyan); font-weight: 600; }
  @keyframes signature-reveal {
    0% { opacity: 0; }
    14%, 70% { opacity: 1; }
    100% { opacity: 0; visibility: hidden; }
  }
  .api-setup {
    position: fixed; inset: 0; z-index: 90; display: none;
    align-items: center; justify-content: center; padding: 22px;
    background: radial-gradient(circle at 50% 28%, rgba(11,31,42,.97), rgba(1,3,5,.99) 72%);
  }
  .api-setup.show { display: flex; }
  .api-panel {
    width: min(430px, 100%); padding: 28px; border-radius: 18px;
    background: rgba(10,22,30,.88); border: 1px solid rgba(52,234,255,.22);
    box-shadow: 0 24px 80px rgba(0,0,0,.55), 0 0 40px rgba(52,234,255,.06);
  }
  .api-panel h2 { font-family:'Rajdhani',sans-serif; letter-spacing:.12em; font-size:21px; }
  .api-panel p { color:var(--txt-dim); font-size:12.5px; line-height:1.55; margin:9px 0 18px; }
  .api-panel label { display:block; color:var(--txt-dim); font-size:10px; letter-spacing:.1em; margin:12px 0 6px; }
  .api-panel select, .api-panel input {
    width:100%; border:1px solid rgba(52,234,255,.16); border-radius:10px;
    background:#071017; color:var(--txt); padding:11px 12px; outline:none;
  }
  .api-panel input:focus, .api-panel select:focus { border-color:rgba(52,234,255,.55); }
  .api-submit {
    width:100%; margin-top:16px; padding:11px; border:0; border-radius:10px;
    background:var(--cyan); color:#03171d; font-weight:700; cursor:pointer;
  }
  .api-submit:disabled { opacity:.5; cursor:wait; }
  .api-error { min-height:18px; margin-top:10px; color:#ffc2ca; font-size:11px; }
  .privacy-note { color:var(--txt-faint)!important; font-size:10.5px!important; margin-bottom:0!important; }
  @keyframes quartz-control-pulse {
    0%, 100% { box-shadow: inset 0 0 28px rgba(52,234,255,.16), 0 0 18px rgba(52,234,255,.22); border-color: rgba(52,234,255,.68); }
    50% { box-shadow: inset 0 0 46px rgba(52,234,255,.28), 0 0 28px rgba(52,234,255,.38); border-color: rgba(52,234,255,.95); }
  }
  body.screen-control-active .shell {
    animation: quartz-control-pulse 2.2s infinite ease-in-out;
  }
  .screen-control-hud {
    -webkit-app-region: no-drag;
    position: fixed; top: 12px; left: 14px; z-index: 9999;
    display: inline-flex; align-items: center; gap: 12px;
    padding: 7px 12px 7px 14px; border-radius: 12px;
    background: rgba(5, 13, 21, 0.94);
    border: 1.5px solid rgba(52, 234, 255, 0.78);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.65), 0 0 20px rgba(52, 234, 255, 0.25);
    backdrop-filter: blur(10px);
  }
  .screen-control-hud[hidden] { display: none !important; }
  .screen-control-hud .hud-dot {
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--cyan); box-shadow: 0 0 10px var(--cyan);
  }
  .screen-control-hud .hud-meta { display: flex; flex-direction: column; line-height: 1.15; }
  .screen-control-hud .hud-title {
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 11.5px;
    letter-spacing: 0.08em; color: var(--cyan);
  }
  .screen-control-hud .hud-sub { font-size: 10px; color: var(--txt-dim); }
  .screen-control-hud .hud-stop-btn {
    padding: 6px 12px; border-radius: 8px; border: 1px solid rgba(255, 110, 128, 0.65);
    background: linear-gradient(180deg, #e12d4b, #b81d38); color: #fff;
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 11.5px;
    letter-spacing: 0.06em; cursor: pointer; transition: all .15s ease;
  }
  .screen-control-hud .hud-stop-btn:hover {
    background: linear-gradient(180deg, #ff3b5c, #d42240);
    box-shadow: 0 0 14px rgba(255, 59, 92, 0.55);
  }
"""
