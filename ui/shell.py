"""Main chat shell markup: everything from ``</head>`` up to the script block.

Presentation only. It holds element ids, Turkish labels and static structure;
no service is created here and nothing here calls the pywebview API. Behaviour
is wired by the application JavaScript in ``ui/js_*.py``.

Do not put a script element in this module: the shipped JavaScript must stay
where the syntax check can read it. Visual decisions:
docs/CLAUDE_FRONTEND_REDESIGN_20261104.md.
"""

# Same geometry as scripts/build_brand_assets.py (the hope star at dawn, 27 Nov);
# tests/test_branding.py keeps them equal. The tile's gradient is #spesDawn in the sprite.
_MARK_FACETS = '<polygon class="f f-tile" points="180.00,12.00 188.35,12.55 196.56,14.18 204.49,16.87 212.00,20.57 218.96,25.23 225.25,30.75 230.77,37.04 235.43,44.00 239.13,51.51 241.82,59.44 243.45,67.65 244.00,76.00 244.00,180.00 243.45,188.35 241.82,196.56 239.13,204.49 235.43,212.00 230.77,218.96 225.25,225.25 218.96,230.77 212.00,235.43 204.49,239.13 196.56,241.82 188.35,243.45 180.00,244.00 76.00,244.00 67.65,243.45 59.44,241.82 51.51,239.13 44.00,235.43 37.04,230.77 30.75,225.25 25.23,218.96 20.57,212.00 16.87,204.49 14.18,196.56 12.55,188.35 12.00,180.00 12.00,76.00 12.55,67.65 14.18,59.44 16.87,51.51 20.57,44.00 25.23,37.04 30.75,30.75 37.04,25.23 44.00,20.57 51.51,16.87 59.44,14.18 67.65,12.55 76.00,12.00"/><polygon class="f f-horizon" points="209.45,226.81 203.15,223.62 196.72,220.69 190.18,218.02 183.53,215.63 176.79,213.50 169.97,211.65 163.08,210.08 156.14,208.80 149.14,207.79 142.12,207.08 135.06,206.64 128.00,206.50 120.94,206.64 113.88,207.08 106.86,207.79 99.86,208.80 92.92,210.08 86.03,211.65 79.21,213.50 72.47,215.63 65.82,218.02 59.28,220.69 52.85,223.62 46.55,226.81 51.71,236.52 57.62,233.53 63.64,230.79 69.77,228.29 75.99,226.05 82.30,224.06 88.69,222.33 95.14,220.86 101.65,219.65 108.20,218.71 114.78,218.04 121.38,217.63 128.00,217.50 134.62,217.63 141.22,218.04 147.80,218.71 154.35,219.65 160.86,220.86 167.31,222.33 173.70,224.06 180.01,226.05 186.23,228.29 192.36,230.79 198.38,233.53 204.29,236.52"/><polygon class="f f-star" points="188.00,112.00 187.02,111.94 184.15,111.52 179.58,110.36 173.64,108.13 166.71,104.62 159.24,99.71 151.71,93.46 144.54,86.05 138.10,77.79 132.67,69.11 128.41,60.52 125.36,52.54 123.43,45.69 122.42,40.44 122.05,37.13 122.00,36.00 121.95,37.13 121.58,40.44 120.57,45.69 118.64,52.54 115.59,60.52 111.33,69.11 105.90,77.79 99.46,86.05 92.29,93.46 84.76,99.71 77.29,104.62 70.36,108.13 64.42,110.36 59.85,111.52 56.98,111.94 56.00,112.00 56.98,112.06 59.85,112.48 64.42,113.64 70.36,115.87 77.29,119.38 84.76,124.29 92.29,130.54 99.46,137.95 105.90,146.21 111.33,154.89 115.59,163.48 118.64,171.46 120.57,178.31 121.58,183.56 121.95,186.87 122.00,188.00 122.05,186.87 122.42,183.56 123.43,178.31 125.36,171.46 128.41,163.48 132.67,154.89 138.10,146.21 144.54,137.95 151.71,130.54 159.24,124.29 166.71,119.38 173.64,115.87 179.58,113.64 184.15,112.48 187.02,112.06"/><polygon class="f f-companion" points="205.00,62.00 204.69,61.98 203.77,61.85 202.32,61.48 200.43,60.78 198.22,59.67 195.85,58.12 193.45,56.15 191.17,53.80 189.12,51.20 187.40,48.46 186.04,45.74 185.07,43.22 184.45,41.06 184.13,39.40 184.02,38.36 184.00,38.00 183.98,38.36 183.87,39.40 183.55,41.06 182.93,43.22 181.96,45.74 180.60,48.46 178.88,51.20 176.83,53.80 174.55,56.15 172.15,58.12 169.78,59.67 167.57,60.78 165.68,61.48 164.23,61.85 163.31,61.98 163.00,62.00 163.31,62.02 164.23,62.15 165.68,62.52 167.57,63.22 169.78,64.33 172.15,65.88 174.55,67.85 176.83,70.20 178.88,72.80 180.60,75.54 181.96,78.26 182.93,80.78 183.55,82.94 183.87,84.60 183.98,85.64 184.00,86.00 184.02,85.64 184.13,84.60 184.45,82.94 185.07,80.78 186.04,78.26 187.40,75.54 189.12,72.80 191.17,70.20 193.45,67.85 195.85,65.88 198.22,64.33 200.43,63.22 202.32,62.52 203.77,62.15 204.69,62.02"/>'

_MARK = ('<svg class="q-mark" viewBox="0 0 256 256" aria-hidden="true" focusable="false">'
         + _MARK_FACETS + '</svg>')
_BRAND_MARK = ('<svg class="q-mark brand-icon" id="orbCore" data-state="idle" viewBox="0 0 256 256" '
               'role="img" aria-label="SpeS" focusable="false">' + _MARK_FACETS + '</svg>')


def _icon(name, size="md"):
    return f'<svg class="i i-{size}" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>'


_SPRITE = """<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
<linearGradient id="spesDawn" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1B1650"/><stop offset="0.52" stop-color="#4B34C9"/><stop offset="1" stop-color="#FF7A59"/></linearGradient>
<symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
<symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></symbol>
<symbol id="i-sidebar" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></symbol>
<symbol id="i-panel" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M15 4v16"/></symbol>
<symbol id="i-minus" viewBox="0 0 24 24"><path d="M5 12h14"/></symbol>
<symbol id="i-maximize" viewBox="0 0 24 24"><rect x="4.5" y="4.5" width="15" height="15" rx="2.5"/></symbol>
<symbol id="i-restore" viewBox="0 0 24 24"><rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/></symbol>
<symbol id="i-compact" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2.5"/><rect x="11" y="11" width="6" height="6" rx="1"/></symbol>
<symbol id="i-close" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></symbol>
<symbol id="i-send" viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></symbol>
<symbol id="i-clip" viewBox="0 0 24 24"><path d="M20 11.5 12.4 19a5 5 0 0 1-7.1-7.1l8-8a3.4 3.4 0 0 1 4.8 4.8l-8 8a1.7 1.7 0 0 1-2.4-2.4l7.3-7.3"/></symbol>
<symbol id="i-mic" viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></symbol>
<symbol id="i-stop" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></symbol>
<symbol id="i-pulse" viewBox="0 0 24 24"><path d="M3 12h4l3-7 4 14 3-7h4"/></symbol>
<symbol id="i-camera" viewBox="0 0 24 24"><path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13" r="3.5"/></symbol>
<symbol id="i-chip" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M10 3v3M14 3v3M10 18v3M14 18v3M3 10h3M3 14h3M18 10h3M18 14h3"/></symbol>
<symbol id="i-windows" viewBox="0 0 24 24"><rect x="3" y="7" width="14" height="13" rx="2"/><path d="M7 7V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/></symbol>
<symbol id="i-eye" viewBox="0 0 24 24"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.8"/></symbol>
<symbol id="i-agents" viewBox="0 0 24 24"><circle cx="8.5" cy="9" r="3.5"/><path d="M2.5 20a6 6 0 0 1 12 0M16 5.8a3.5 3.5 0 0 1 0 6.4M18 15a6 6 0 0 1 3.5 5"/></symbol>
<symbol id="i-phone" viewBox="0 0 24 24"><rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/></symbol>
<symbol id="i-trash" viewBox="0 0 24 24"><path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/></symbol>
<symbol id="i-spark" viewBox="0 0 24 24"><path d="M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2Z"/></symbol>
<symbol id="i-wave" viewBox="0 0 24 24"><path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/></symbol>
<symbol id="i-volume" viewBox="0 0 24 24"><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4ZM16 9a4 4 0 0 1 0 6"/></symbol>
<symbol id="i-shield" viewBox="0 0 24 24"><path d="M12 3l7.5 3v5.5c0 4.5-3 8-7.5 9.5-4.5-1.5-7.5-5-7.5-9.5V6L12 3Z"/></symbol>
<symbol id="i-globe" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5s1.2-6.1 3.6-8.5Z"/></symbol>
<symbol id="i-loop" viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 13.7-5.6L20 9M20 4v5h-5M20 12a8 8 0 0 1-13.7 5.6L4 15M4 20v-5h5"/></symbol>
</defs></svg>"""


SHELL_MARKUP = r"""
</head>
<body>
@@SPRITE@@

<div class="screen-control-hud" id="screenControlHud" role="status" hidden>
  <span class="hud-dot" aria-hidden="true"></span>
  <div class="hud-meta">
    <span class="hud-title" id="screenControlHudTitle">SpeS kontrolde</span>
    <span class="hud-sub" id="screenControlHudSub">Yalnız bu tuşla durdurulur</span>
  </div>
  <button type="button" class="hud-stop-btn" id="btnHudStopTask">@@i:stop:sm@@Görevi durdur</button>
</div>

<div class="app shell">

  <!-- SpeS layout (7 Nov 2026, built from scratch): a slim rail, a drawer for
       conversations, and a stage where Codex and Antigravity each have a column
       either side of the conversation with the SpeS crystal at its head. -->
  <nav class="app-rail pywebview-drag-region" aria-label="SpeS">
    <div class="rail-mark" id="orbWrap">@@BRAND_MARK@@</div>
    <button type="button" class="rail-btn primary" id="btnNewChat" title="Yeni sohbet başlat" aria-label="Yeni sohbet">@@i:plus@@<span class="rail-tip" aria-hidden="true">Yeni sohbet</span></button>
    <button type="button" class="rail-btn" id="btnSidebar" title="Sohbetler ve projeler (Ctrl+B)" aria-label="Sohbetler ve projeler" aria-controls="sidebar" aria-keyshortcuts="Control+B">@@i:sidebar@@<span class="rail-tip" aria-hidden="true">Sohbetler</span></button>
    <button type="button" class="rail-btn" id="btnCommand" title="Ara ve komutlar (Ctrl+K)" aria-label="Ara ve komutlar" aria-keyshortcuts="Control+K">@@i:search@@<span class="rail-tip" aria-hidden="true">Ara ve komutlar</span></button>
    <div class="rail-spacer"></div>
    <button type="button" class="rail-btn" id="btnSelfDiagnostics" title="SpeS öz teşhisini bu sohbette başlat" aria-label="Öz teşhis">@@i:pulse@@<span class="rail-tip" aria-hidden="true">Öz teşhis</span></button>
    <button type="button" class="rail-btn" id="btnPanels" title="Durum ve araç panelini aç/kapat (Ctrl+I)" aria-label="Durum ve araçlar" aria-keyshortcuts="Control+I">@@i:panel@@<span class="rail-tip" aria-hidden="true">Durum ve araçlar</span></button>
    <button type="button" class="rail-btn" id="btnPreview" title="İş panelini aç/kapat: önizleme, değişiklikler, kontroller (Ctrl+Shift+P)" aria-label="İş paneli" aria-controls="previewPane" aria-keyshortcuts="Control+Shift+P">@@i:globe@@<span class="rail-tip" aria-hidden="true">İş paneli</span></button>
    <div class="signature-mark" title="Ali Mehdi">AM</div>
  </nav>

  <div class="drawer-scrim" id="drawerScrim"></div>
  <aside class="sidebar" id="sidebar" aria-label="Sohbetler ve projeler">
    <div class="side-head">
      <div class="brand">SpeS</div>
      <button type="button" class="icon-btn" id="btnDrawerClose" title="Kapat (Esc)" aria-label="Sohbetler panelini kapat">@@i:close:sm@@</button>
    </div>
    <div class="side-section space-work-only" id="projectSection">
      <div class="workspace-nav-title">Proje</div>
      <div class="workspace-project">
        <select class="project-picker" id="mainProjectSelect" title="Aktif proje" aria-label="Aktif proje"></select>
        <button type="button" class="icon-btn" id="btnAddProject" title="Windows klasör seçicisiyle proje ekle" aria-label="Proje ekle">@@i:plus@@</button>
      </div>
      <button type="button" class="project-chats-delete" id="btnRemoveProject" title="Proje klasörü ve dosyaları silinmez">Projeyi listeden kaldır</button>
    </div>
    <div class="side-section grow">
      <div class="workspace-nav-title" id="conversationListTitle">Görevler</div>
      <div id="conversationList" class="conversation-list"></div>
      <button type="button" class="project-chats-delete" id="btnDeleteProjectChats">Bu projenin sohbetlerini temizle</button>
    </div>
    <div class="side-section">
      <div class="workspace-nav-title" id="agentConnectionsTitle">Ajanlar</div>
      <div id="agentConnections" class="agent-connections" role="list" aria-labelledby="agentConnectionsTitle"></div>
    </div>
    <div class="signature-main"><span>DESIGNED &amp; ENGINEERED BY</span><strong>ALI MEHDI</strong></div>
  </aside>

  <main class="main chat-col">
    <header class="topbar titlebar pywebview-drag-region">
      <!-- Two spaces (14 Nov 2026): Sohbet for talking, Workspace for work. -->
      <div class="space-switch" id="spaceSwitch" role="tablist" aria-label="Alan">
        <span class="space-thumb" aria-hidden="true"></span>
        <button type="button" class="space-tab" role="tab" data-space="chat" id="spaceTabChat" aria-selected="false" title="Sohbet: ekiple sohbet, iş yapılmaz">Sohbet</button>
        <button type="button" class="space-tab" role="tab" data-space="work" id="spaceTabWork" aria-selected="true" title="Workspace: görevler, dosyalar ve bilgisayar kontrolü">Workspace</button>
      </div>
      <div class="chat-title-group">
        <span class="chat-conv-title" id="chatConvTitle">Yeni Sohbet</span>
        <span class="project-tag" id="writerBadge" style="display:none"></span>
        <span class="project-tag" id="chatProjectTag" title="Çalışma alanı" style="display:none"></span>
      </div>
      <div class="titlebar-spacer"></div>
      <div class="team-limits" id="teamLimits" role="group" aria-label="Ajan limitleri">
        <span class="limit-chip" id="limitCodex" data-agent="codex" data-state="unknown" tabindex="0"><span class="limit-name">Fides</span><span class="limit-meter" aria-hidden="true"><b></b></span><span class="limit-value">—</span></span>
        <span class="limit-chip" id="limitClaude" data-agent="claude" data-state="unknown" tabindex="0"><span class="limit-name">Fatum</span><span class="limit-meter" aria-hidden="true"><b></b></span><span class="limit-value">—</span></span>
        <span class="limit-chip" id="limitAgy" data-agent="antigravity" data-state="unknown" tabindex="0"><span class="limit-name">Eos</span><span class="limit-meter" aria-hidden="true"><b></b></span><span class="limit-value">—</span></span>
      </div>
      <div class="status-pill offline" id="statusPill"><span class="dot" aria-hidden="true"></span><span id="statusText">Bağlanıyor</span></div>
      <span class="squad-badge" id="squadBadge" title="Squad mesajlaşma altyapısı">Squad: Kontrol ediliyor</span>
      <span class="perm-hint" id="permissionSelectionHint" aria-live="polite">Tam Yetki</span>
      <div class="win-controls">
        <button type="button" class="win-btn" id="btnWinMinimize" title="Küçült" aria-label="Küçült">@@i:minus:sm@@</button>
        <button type="button" class="win-btn" id="btnWinMaximize" title="Büyüt" aria-label="Büyüt" aria-pressed="false">@@i:maximize:sm@@</button>
        <button type="button" class="win-btn" id="btnMin" title="Kompakt sohbete geç" aria-label="Kompakt sohbet">@@i:compact:sm@@</button>
        <button type="button" class="win-btn close" id="btnClose" title="Kapat" aria-label="Kapat">@@i:close:sm@@</button>
      </div>
    </header>

    <details id="writerRecoveryPanel" class="notice-panel" hidden>
      <summary>Kesilen yazıcı görevi — inceleme gerekli</summary><div id="writerRecoveryBody"></div>
    </details>

    <div class="desktop-task-bar" id="desktopTaskBar" data-state="normal">
      <div class="desktop-task-copy" aria-live="polite">
        <strong id="desktopTaskLabel">Normal sohbet</strong>
        <span id="desktopTaskDetail">Dosya erişimi ayrı; masaüstü kontrolü görev onayı gerektirir.</span>
      </div>
      <button type="button" class="control-btn" id="btnDesktopTaskStop" hidden>Görevi durdur</button>
    </div>

    <div class="stage-shell">
      <div class="stage crew" id="crew" data-focus="antigravity" data-flow="" data-control="false">
        <aside class="lane-col lane-codex" id="laneColCodex" data-state="idle" aria-label="Codex">
          <button type="button" class="lane-card" id="laneCodex" data-agent="codex" data-state="idle" aria-pressed="false" aria-describedby="laneCodexState">
            <span class="lane-gem" aria-hidden="true"></span>
            <span class="lane-copy">
              <span class="lane-name">Fides <span class="lane-agent">Codex</span></span>
              <span class="lane-state" id="laneCodexState">Hazır</span>
            </span>
          </button>
          <button type="button" class="team-toggle" data-team-agent="codex" aria-pressed="true" title="Birlikte modunda Fides ekipte; tıklayınca pasif olur">Ekipte</button>
          <div class="model-selector-pill" id="codexModelPill" title="Codex modeli ve düşünme seviyesi">
              <span class="pill-agent-name">Codex</span>
              <select id="codexModelSelect" aria-label="Codex modeli">
                <option value="gpt-6.1-sol">GPT-6.1-Sol</option>
                <option value="gpt-6-astra">GPT-6-Astra</option>
                <option value="gpt-6-sol">GPT-6-Sol</option>
                <option value="gpt-6-luna">GPT-6-Luna</option>
                <option value="gpt-5.6-sol">GPT-5.6-Sol</option>
                <option value="gpt-5.6-terra">GPT-5.6-Terra</option>
                <option value="gpt-5.6-luna">GPT-5.6-Luna</option>
              </select>
              <select id="codexEffortSelect" aria-label="Codex düşünme seviyesi" title="Codex düşünme seviyesi (model_reasoning_effort)">
                <option value="low" selected>low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
                <option value="xhigh">xhigh</option>
                <option value="max">max</option>
                <option value="ultra">ultra</option>
              </select>
            </div>
          <dl class="lane-status" id="laneCodexStatus" aria-label="Görev durumu" aria-live="polite" hidden></dl>
          <div class="lane-title">Son adımlar</div>
          <ol class="lane-trail" id="laneCodexTrail"></ol>
          <p class="lane-empty">Çalışırken attığı adımlar burada akar.</p>
        </aside>

        <aside class="lane-col lane-claude" id="laneColClaude" data-state="idle" aria-label="Claude">
          <button type="button" class="lane-card" id="laneClaude" data-agent="claude" data-state="idle" aria-pressed="false" aria-describedby="laneClaudeState">
            <span class="lane-gem" aria-hidden="true"></span>
            <span class="lane-copy">
              <span class="lane-name">Fatum <span class="lane-agent">Claude</span></span>
              <span class="lane-state" id="laneClaudeState">Hazır</span>
            </span>
          </button>
          <button type="button" class="team-toggle" data-team-agent="claude" aria-pressed="true" title="Birlikte modunda Fatum ekipte; tıklayınca pasif olur">Ekipte</button>
          <div class="model-selector-pill" id="claudeModelPill" title="Claude modeli ve düşünme seviyesi">
              <span class="pill-agent-name">Claude</span>
              <select id="claudeModelSelect" aria-label="Claude modeli">
                <option value="sonnet" selected>Claude Sonnet (hızlı ve güçlü)</option>
                <option value="opus">Claude Opus (en güçlü)</option>
                <option value="haiku">Claude Haiku (en hızlı)</option>
              </select>
              <select id="claudeEffortSelect" aria-label="Claude düşünme seviyesi" title="Claude düşünme seviyesi (--effort)">
                <option value="low">low</option>
                <option value="medium" selected>medium</option>
                <option value="high">high</option>
                <option value="xhigh">xhigh</option>
                <option value="max">max</option>
              </select>
            </div>
          <dl class="lane-status" id="laneClaudeStatus" aria-label="Görev durumu" aria-live="polite" hidden></dl>
          <div class="lane-title">Son adımlar</div>
          <ol class="lane-trail" id="laneClaudeTrail"></ol>
          <p class="lane-empty">Çalışırken attığı adımlar burada akar.</p>
        </aside>

        <section class="stream" aria-label="Sohbet akışı">
          <div class="stream-head">
            <span class="core-beam beam-codex" aria-hidden="true"><b class="beam-flow"></b></span>
            <button type="button" class="crew-core" id="crewCore" data-agent="collaboration" aria-pressed="false" aria-describedby="crewCoreLabel" title="Birlikte: Codex ve Antigravity aynı görevde">
              <span class="core-crystal" aria-hidden="true"><span class="core-halo"></span>@@MARK@@</span>
              <span class="core-label" id="crewCoreLabel">Birlikte</span>
            </button>
            <span class="core-beam beam-agy" aria-hidden="true"><b class="beam-flow"></b></span>
          </div>

          <div class="chat-stage">
      <div class="lane-rails" aria-hidden="true">
        <i class="rail rail-codex"><b class="rail-flow"></b></i>
        <i class="rail rail-agy"><b class="rail-flow"></b></i>
      </div>
      <div class="chat" id="chat" role="log" aria-label="Sohbet"></div>
      <section class="empty-state face" id="emptyState" aria-label="Başlangıç">
        <div class="face-mark" aria-hidden="true">@@MARK@@</div>
        <h1 id="emptyGreeting">Merhaba.</h1>
        <p class="face-lede space-chat-only">Aklındakini yaz. Sohbet edelim, fikir verelim, birlikte çözelim.</p>
        <p class="face-lede space-work-only">Ne yapılmasını istediğini kendi cümlelerinle söyle. SpeS planlar, yapar ve kontrol eder.</p>
        <div class="prompt-chips face-cards space-chat-only">
          <button type="button" class="prompt-chip face-card" data-prompt="Selam! Bugün nasılsın, biraz sohbet edelim mi?"><span class="face-card-icon" aria-hidden="true">@@i:wave@@</span><span class="face-card-text"><b>Sohbet et</b><small>Merhaba de, laflayalım</small></span></button>
          <button type="button" class="prompt-chip face-card" data-prompt="Bana bugün için küçük, uygulanabilir bir fikir ver."><span class="face-card-icon" aria-hidden="true">@@i:spark@@</span><span class="face-card-text"><b>Fikir iste</b><small>Gün için küçük bir öneri</small></span></button>
          <button type="button" class="prompt-chip face-card" data-prompt="Bunu bana basitçe açıklar mısın: "><span class="face-card-icon" aria-hidden="true">@@i:globe@@</span><span class="face-card-text"><b>Bir şeyi açıkla</b><small>Zor bir konuyu sade anlat</small></span></button>
        </div>
        <div class="face-free space-chat-only">
          <button type="button" class="face-free-btn" id="btnFreeChatStart"><span class="face-free-title">Ücretsiz sohbet</span><span class="face-free-hint">Aboneliğin yoksa: kendi ücretsiz hesaplarınla konuş</span></button>
          <button type="button" class="face-link" id="btnFreeChatManage">Bağlantıları yönet</button>
        </div>
        <div class="prompt-chips face-cards space-work-only">
          <button type="button" class="prompt-chip face-card" data-prompt="Bana basit bir hesap makinesi programı yap."><span class="face-card-icon" aria-hidden="true">@@i:chip@@</span><span class="face-card-text"><b>Bir program yap</b><small>Baştan sona, kendisi dener</small></span></button>
          <button type="button" class="prompt-chip face-card" data-prompt="Bu projenin yapısını incele ve kısaca özetle."><span class="face-card-icon" aria-hidden="true">@@i:search@@</span><span class="face-card-text"><b>Projeyi özetle</b><small>Ne var, ne eksik</small></span></button>
          <button type="button" class="prompt-chip face-card" data-prompt="İndirilenler klasöründeki faturaları bir Excel tablosunda topla."><span class="face-card-icon" aria-hidden="true">@@i:clip@@</span><span class="face-card-text"><b>Dosyalarla çalış</b><small>Rapor, tablo, düzen</small></span></button>
          <button type="button" class="prompt-chip face-card" data-prompt="Açık uygulamada şunu yap: "><span class="face-card-icon" aria-hidden="true">@@i:windows@@</span><span class="face-card-text"><b>Bilgisayarda iş yap</b><small>Pencereleri SpeS kullanır</small></span></button>
        </div>
      </section>
      <button type="button" class="jump-bottom-btn" id="btnJumpBottom" title="En son mesaja git">Yeni mesajlar ↓</button>
    </div>

          <div class="dock">
            <section class="repair-plan" id="repairPlan" aria-labelledby="repairPlanTitle" hidden>
              <div class="repair-plan-head">
                <h2 id="repairPlanTitle">Onarım planı</h2>
                <button type="button" class="env-health-btn" id="rpClose" aria-label="Onarım planını kapat">Kapat</button>
              </div>
              <p class="rp-intro">Testler başarısız olursa aynı ajan en çok seçtiğiniz sayıda yeniden dener. Hangi testlerin sayılacağını siz belirlersiniz; ajan değiştiremez.</p>
              <div class="rp-grid">
                <label for="rpProvider">Ajan</label>
                <select id="rpProvider" disabled aria-describedby="rpProviderHelp"><option value="codex">Codex</option><option value="antigravity">Antigravity</option></select>
                <span class="rp-help" id="rpProviderHelp">Sohbette seçili ajan. Birlikte modunda önce tek ajan seçin.</span>
                <label for="rpTests">Test dosyaları</label>
                <textarea id="rpTests" rows="2" spellcheck="false" aria-describedby="rpTestsHelp" placeholder="tests/test_invoice.py"></textarea>
                <span class="rp-help" id="rpTestsHelp">Satır başına bir dosya, proje klasörüne göre.</span>
                <label for="rpSupport">Destek dosyaları</label>
                <textarea id="rpSupport" rows="2" spellcheck="false" aria-describedby="rpSupportHelp" placeholder="tests/fixtures/expected.json"></textarea>
                <span class="rp-help" id="rpSupportHelp">İsteğe bağlı: testlerin okuduğu beklenen değerler ve örnek veriler. Çalıştırılmaz, yalnız korunur.</span>
                <label for="rpExpected">En az test sayısı</label>
                <input id="rpExpected" type="number" min="1" max="100000" inputmode="numeric" required>
                <label for="rpPython">Python</label>
                <input id="rpPython" type="text" list="rpPythonList" spellcheck="false" aria-describedby="rpPythonHelp" placeholder="Önizleme bulur">
                <datalist id="rpPythonList"></datalist>
                <span class="rp-help" id="rpPythonHelp">Boş bırakırsanız önizleme bulduğu yolu önerir.</span>
                <label for="rpSitePackages">Bağımlılık klasörü</label>
                <input id="rpSitePackages" type="text" spellcheck="false" aria-describedby="rpSitePackagesHelp" placeholder="İsteğe bağlı: …\Lib\site-packages">
                <span class="rp-help" id="rpSitePackagesHelp">Testler üçüncü parti paket istiyorsa, proje dışındaki site-packages klasörü. İçeriği korunmaz; yalnız güvendiğiniz klasörü girin.</span>
                <label for="rpMax">En çok onarım</label>
                <select id="rpMax"><option value="1">1</option><option value="2" selected>2</option><option value="3">3</option></select>
              </div>
              <p class="rp-error" id="rpError" role="alert" hidden></p>
              <div class="rp-preview" id="rpPreviewOut" aria-live="polite" hidden></div>
              <div class="rp-actions">
                <button type="button" class="env-health-btn" id="rpPreviewBtn">Önizle</button>
                <button type="button" class="env-health-btn rp-primary" id="rpRegister" disabled>Onayla ve kaydet</button>
              </div>
            </section>
            <div class="repair-chip" id="repairChip" data-status="ready" hidden>
              <span class="msg-badge" id="repairChipBadge" data-tone="ok"><i class="msg-badge-icon" aria-hidden="true"></i><span id="repairChipText" role="status">Onarım planı hazır</span></span>
              <button type="button" class="env-health-btn" id="repairChipClear">Kaldır</button>
            </div>
            <section class="env-health" id="envHealth" data-status="ok" aria-label="Ortam sağlık kontrolü" hidden>
              <div class="env-health-head">
                <span class="msg-badge" id="envHealthBadge" data-tone="warn"><i class="msg-badge-icon" aria-hidden="true"></i><span id="envHealthTitle" role="status">Ortamda uyarı var</span></span>
                <button type="button" class="env-health-btn" id="envHealthToggle" aria-expanded="false" aria-controls="envHealthList">Ayrıntılar</button>
                <button type="button" class="env-health-btn" id="envHealthRecheck">Yeniden kontrol et</button>
              </div>
              <ul class="env-health-list" id="envHealthList" hidden></ul>
            </section>
            <div class="thinking-row" id="thinkingRow">
        <div class="thinking-dots" aria-hidden="true"><div class="d"></div><div class="d"></div><div class="d"></div></div>
        <span id="thinkingText">işleniyor...</span>
        <button type="button" class="control-btn" id="btnCancel" title="Etkin görevi ve ajan süreçlerini durdur" style="display:none">Görevi durdur</button>
      </div>
            <div class="inputbar composer" id="composer">
              <div class="attach-chips" id="attachChips" aria-label="Eklenen dosyalar" hidden></div>
              <div class="skill-hint" id="skillHint" role="listbox" aria-label="Raftaki skill'ler" hidden></div>
              <textarea id="msgInput" rows="1" aria-label="Ekibe yazın veya görev verin" aria-keyshortcuts="Control+L" title="Sohbete odaklan: Ctrl+L · Gönder: Enter · Yeni satır: Shift+Enter" placeholder="Ekibe yazın veya görev verin…" autofocus></textarea>
              <div class="composer-row">
                <div class="agent-seg-group" id="agentSegGroup" role="group" aria-label="Ajan seçici">
            <span class="seg-thumb" id="agentSegThumb" aria-hidden="true"></span>
            <button type="button" class="agent-seg-btn active" data-agent="antigravity">Antigravity</button>
            <button type="button" class="agent-seg-btn" data-agent="codex">Codex</button>
            <button type="button" class="agent-seg-btn" data-agent="claude">Claude</button>
            <button type="button" class="agent-seg-btn" data-agent="collaboration">Birlikte</button>
          </div>
                <div class="composer-spacer"></div>
                <button type="button" class="chat-tool-btn" id="btnRepairPlan" aria-expanded="false" aria-controls="repairPlan" title="Testler başarısız olursa ajanın yeniden denemesi için plan kur">Onarım planı</button>
                <button type="button" class="chat-tool-btn" id="btnContinueCollab" style="display:none" title="Birlikte modunda ajanlar arası tartışmayı 1 tur daha sürdür">@@i:loop:sm@@ 1 tur daha</button>
          <button type="button" class="icon-btn attach" id="btnAttach" title="Dosya, fotoğraf veya zip ekle (sürükleyip bırakabilir ya da yapıştırabilirsiniz)" aria-label="Dosya ekle">@@i:clip@@</button>
          <button type="button" class="icon-btn mic" id="btnMic" title="Konuş (bas-konuş)" aria-label="Sesle yaz">@@i:mic@@</button>
          <button type="button" class="send-btn send" id="btnSend" title="Gönder (Enter)" aria-label="Gönder">@@i:send@@</button>
              </div>
            </div>
          </div>
        </section>

        <aside class="lane-col lane-antigravity" id="laneColAgy" data-state="idle" aria-label="Antigravity">
          <button type="button" class="lane-card" id="laneAgy" data-agent="antigravity" data-state="idle" aria-pressed="false" aria-describedby="laneAgyState">
            <span class="lane-gem" aria-hidden="true"></span>
            <span class="lane-copy">
              <span class="lane-name">Eos <span class="lane-agent">Antigravity</span></span>
              <span class="lane-state" id="laneAgyState">Hazır</span>
            </span>
          </button>
          <button type="button" class="team-toggle" data-team-agent="antigravity" aria-pressed="true" title="Birlikte modunda Eos ekipte; tıklayınca pasif olur">Ekipte</button>
          <div class="model-selector-pill active-agy" id="agyModelPill" title="Antigravity modeli ve düşünme seviyesi">
              <span class="pill-agent-name">Antigravity</span>
              <select id="agyModelSelect" aria-label="Antigravity modeli">
                <option value="gemini-4-argon-medium">Gemini 4 Argon (Medium)</option>
                <option value="gemini-4-argon-high">Gemini 4 Argon (High)</option>
                <option value="gemini-4-argon-low">Gemini 4 Argon (Low)</option>
                <option value="gemini-3.8-flash-high">Gemini 3.8 Flash (High)</option>
                <option value="gemini-3.8-flash-medium">Gemini 3.8 Flash (Medium)</option>
                <option value="gemini-3.8-flash-low">Gemini 3.8 Flash (Low)</option>
                <option value="claude-opus-5-5-medium">Claude Opus 5.5 (Medium)</option>
                <option value="claude-sonnet-5-5-medium">Claude Sonnet 5.5 (Medium)</option>
                <option value="gpt-oss-120b-medium">GPT-OSS 120B (Medium)</option>
              </select>
              <select id="agyEffortSelect" aria-label="Antigravity düşünme seviyesi" title="Antigravity düşünme seviyesi (--effort)">
                <option value="low">low</option>
                <option value="medium" selected>medium</option>
                <option value="high">high</option>
                <option value="xhigh">xhigh</option>
                <option value="max">max</option>
              </select>
            </div>
          <dl class="lane-status" id="laneAgyStatus" aria-label="Görev durumu" aria-live="polite" hidden></dl>
          <div class="lane-title">Son adımlar</div>
          <ol class="lane-trail" id="laneAgyTrail"></ol>
          <p class="lane-empty">Çalışırken attığı adımlar burada akar.</p>
        </aside>
      </div>
    </div>

    <div class="legacy-controls" hidden>
      <select id="mainPermissionLevel" title="Tam yetki (tek yetki sistemi)" aria-label="İşlem Yetkisi"><option value="full" selected>Tam Yetki</option></select>
      <input type="checkbox" id="mainWriteToggle" checked aria-label="Yazma yetkisi">
      <select id="mainAgentSelect" aria-label="Aktif ajan">
        <option value="antigravity">Antigravity</option>
        <option value="codex">Codex</option>
        <option value="claude">Claude</option>
        <option value="collaboration">Birlikte (Squad)</option>
      </select>
    </div>
  </main>

  <aside class="inspector" id="inspector" aria-label="Durum ve araçlar">
    <div class="inspector-head">
      <div class="tabs" role="tablist" aria-label="Panel bölümleri">
        <span class="tab-thumb" id="inspectorTabThumb" aria-hidden="true"></span>
        <button type="button" class="tab active" role="tab" aria-selected="true" aria-controls="tabStatus" data-tab="tabStatus">Durum</button>
        <button type="button" class="tab" role="tab" aria-selected="false" aria-controls="tabTools" data-tab="tabTools">Araçlar</button>
        <button type="button" class="tab" role="tab" aria-selected="false" aria-controls="tabLog" data-tab="tabLog">Günlük</button>
      </div>
      <button type="button" class="icon-btn" id="btnInspectorClose" title="Paneli kapat" aria-label="Paneli kapat">@@i:close:sm@@</button>
    </div>

    <div class="tab-panel" id="tabStatus" role="tabpanel">
      <section class="card">
        <div class="card-label">Sistem</div>
        <div class="stat-row"><div class="stat-top"><span>CPU</span><span class="val" id="cpuVal">--%</span></div><div class="stat-bar"><div class="stat-fill" id="cpuFill"></div></div></div>
        <div class="stat-row"><div class="stat-top"><span>Bellek</span><span class="val" id="memVal">--%</span></div><div class="stat-bar"><div class="stat-fill" id="memFill"></div></div></div>
        <div class="stat-row"><div class="stat-top"><span>Disk</span><span class="val" id="diskVal">--%</span></div><div class="stat-bar"><div class="stat-fill" id="diskFill"></div></div></div>
      </section>
      <section class="card">
        <div class="card-label">Yerel asistan operasyonu</div>
        <div class="log-box" id="operationStatus">Operasyon yok</div>
        <div class="card-actions">
          <button type="button" class="control-btn" id="btnLearnOperation" style="display:none">Öğren</button>
          <button type="button" class="control-btn" id="btnFinishOperation" style="display:none">Bitir</button>
        </div>
      </section>
      <section class="card">
        <div class="card-label">Yerel asistan görevleri</div>
        <div class="log-box" id="taskList">Yerel asistan görevi yok</div>
      </section>
      <section class="card">
        <div class="card-label">Yerel asistan modeli (API)</div>
        <div class="log-box" id="providerStatus">Kontrol ediliyor...</div>
        <div class="card-actions">
          <button type="button" class="control-btn" id="btnProviderProbe">Bağlantıyı test et</button>
          <button type="button" class="control-btn" id="btnCliConnections">Hesaplar ve CLI</button>
        </div>
      </section>
      <section class="card">
        <div class="card-label">Oturum</div>
        <div class="sess-row"><span>Mesaj</span><span class="val" id="sessMsgs">0</span></div>
        <div class="sess-row"><span>Süre</span><span class="val" id="sessUptime">00:00:00</span></div>
        <div class="sess-row"><span>Bağlantı</span><span class="val" id="sessStatus">—</span></div>
        <div class="sess-row"><span>Saat</span><span class="val" id="clock">--:--:--</span></div>
      </section>
    </div>

    <div class="tab-panel" id="tabTools" role="tabpanel" hidden>
      <section class="card">
        <div class="card-label">Görünüm</div>
        <div class="pref-row">
          <span>Tema</span>
          <div class="choice" role="group" aria-label="Tema" id="prefTheme">
            <button type="button" data-value="dark">Koyu</button>
            <button type="button" data-value="light">Açık</button>
            <button type="button" data-value="system">Sistem</button>
          </div>
        </div>
        <div class="pref-row">
          <span>Vurgu</span>
          <div class="swatches" role="group" aria-label="Vurgu rengi" id="prefCrystal">
            <button type="button" data-value="rose" title="Şafak pembesi" aria-label="Şafak pembesi"></button>
            <button type="button" data-value="citrine" title="Umut yeşili" aria-label="Umut yeşili"></button>
            <button type="button" data-value="amethyst" title="Lavanta" aria-label="Lavanta"></button>
            <button type="button" data-value="smoky" title="Kül" aria-label="Kül"></button>
          </div>
        </div>
        <div class="pref-notice" id="prefNotice" role="status" hidden></div>
        <div class="pref-row stacked">
          <label for="responseDetail">Yanıt ayrıntısı</label>
          <select class="agent-select" id="responseDetail">
            <option value="short" selected>Kısa (varsayılan)</option>
            <option value="normal">Normal</option>
            <option value="technical">Teknik</option>
          </select>
        </div>
      </section>
      <section class="card">
        <div class="card-label">Hızlı işlemler</div>
        <button type="button" class="qa-btn" data-action="screenshot">@@i:camera@@ Ekran görüntüsü</button>
        <button type="button" class="qa-btn" data-action="sysinfo">@@i:chip@@ Sistem bilgisi</button>
        <button type="button" class="qa-btn" data-action="desktop" style="display:none">Masaüstünü listele</button>
        <button type="button" class="qa-btn" data-action="plugins" style="display:none">Eklentiler</button>
        <button type="button" class="qa-btn" data-action="update_all" style="display:none">Hepsini güncelle</button>
        <button type="button" class="qa-btn" id="btnMobile">@@i:phone@@ Mobil erişim</button>
      </section>
      <section class="card">
        <div class="card-label">Ses</div>
        <button type="button" class="qa-btn voice-toggle" id="btnWake" title="Uyandırma kelimesi: &quot;Hey SpeS&quot;">@@i:wave@@ <span id="wakeLabel">Uyandırma kelimesi: kapalı</span></button>
        <button type="button" class="qa-btn voice-toggle active" id="btnTts" title="Sesli yanıt aç/kapat">@@i:volume@@ <span id="ttsLabel">Sesli yanıt: açık</span></button>
      </section>
      <section class="card">
        <div class="card-label">Güvenlik</div>
        <button type="button" class="qa-btn" id="btnSafe">@@i:shield@@ <span id="safeLabel">Güvenli mod: kapalı</span></button>
        <div class="log-box plugin-permissions" id="pluginPermissions"></div>
      </section>
      <section class="card" id="memoryCard">
        <div class="card-label">Hafıza</div>
        <p class="work-note">Ajanlar yalnız senin "bunu hatırla" dediğin bilgileri sohbetler arasında hatırlar. Şifre, kart ve anahtar kaydedilmez.</p>
        <ul class="memory-list" id="memoryList" aria-label="Hatırlanan bilgiler"></ul>
        <p class="work-empty" id="memoryEmpty">Henüz hatırlanan bir şey yok.</p>
        <button type="button" class="qa-btn danger" id="btnMemoryClear" hidden>@@i:trash@@ Hafızayı temizle</button>
      </section>
      <section class="card danger-zone">
        <div class="card-label">Sohbet</div>
        <button type="button" class="qa-btn danger" id="btnClear">@@i:trash@@ Sohbeti temizle</button>
      </section>
    </div>

    <div class="tab-panel log-panel" id="tabLog" role="tabpanel" hidden>
      <div class="log-box" id="logBox" role="log" aria-label="Uygulama günlüğü"></div>
    </div>
  </aside>

  <!-- App preview: shows a web app running on this computer (loopback only). -->
  <aside class="preview-pane" id="previewPane" data-work-tab="preview" aria-label="İş paneli">
    <div class="work-tabs" role="tablist" aria-label="İş paneli">
      <button type="button" class="work-tab" role="tab" id="workTabPreview" data-tab="preview" aria-selected="true" aria-controls="previewBar">Önizleme</button>
      <button type="button" class="work-tab" role="tab" id="workTabFiles" data-tab="files" aria-selected="false" aria-controls="workFiles">Dosyalar <span class="work-count" id="workFilesCount"></span></button>
      <button type="button" class="work-tab" role="tab" id="workTabChanges" data-tab="changes" aria-selected="false" aria-controls="workChanges">Değişiklikler <span class="work-count" id="workChangesCount"></span></button>
      <button type="button" class="work-tab" role="tab" id="workTabChecks" data-tab="checks" aria-selected="false" aria-controls="workChecks">Kontroller <span class="work-count" id="workChecksCount"></span></button>
    </div>
    <section class="work-files" id="workFiles" role="tabpanel" aria-labelledby="workTabFiles">
      <div class="work-files-list" id="workFilesList" aria-label="Sonuç dosyaları ve ekler"></div>
      <div class="work-viewer" id="workViewer" aria-live="polite">
        <p class="work-empty-view">Ekibin yazdığı bir dosyayı ya da gönderdiğin bir eki seç.</p>
      </div>
    </section>
    <section class="work-list" id="workChanges" role="tabpanel" aria-labelledby="workTabChanges">
      <p class="work-note">SpeS'in dosya sisteminde kendisinin gördüğü değişiklikler. Ajanın "değiştirdim" demesi buraya girmez.</p>
      <ol class="work-items" id="workChangesList"></ol>
      <p class="work-empty">Bu sohbette henüz doğrulanmış dosya değişikliği yok.</p>
    </section>
    <section class="work-list" id="workChecks" role="tabpanel" aria-labelledby="workTabChecks">
      <p class="work-note">Her yazıcı turunun SpeS tarafından görülen kontrol sonucu. Kullanıcı kabulü ayrıdır.</p>
      <ol class="work-items" id="workChecksList"></ol>
      <p class="work-empty">Bu sohbette henüz kontrol kanıtı yok.</p>
    </section>
    <form class="preview-bar" id="previewBar" autocomplete="off">
      <button type="button" class="icon-btn" id="btnPreviewReload" title="Yenile" aria-label="Önizlemeyi yenile">@@i:loop:sm@@</button>
      <input class="preview-address" id="previewAddress" type="text" inputmode="url" spellcheck="false" placeholder="http://127.0.0.1:8000" aria-label="Önizleme adresi">
      <button type="submit" class="control-btn" id="btnPreviewGo">Aç</button>
      <span class="device-switch" role="group" aria-label="Önizleme genişliği">
        <button type="button" class="device-btn" data-device="desktop" aria-pressed="true" title="Masaüstü genişliği">Masaüstü</button>
        <button type="button" class="device-btn" data-device="tablet" aria-pressed="false" title="Tablet genişliği (768 px)">Tablet</button>
        <button type="button" class="device-btn" data-device="phone" aria-pressed="false" title="Telefon genişliği (390 px)">Telefon</button>
      </span>
      <button type="button" class="icon-btn" id="btnPreviewWindow" title="Ayrı pencerede aç" aria-label="Ayrı pencerede aç">@@i:windows:sm@@</button>
      <button type="button" class="icon-btn" id="btnPreviewClose" title="Önizlemeyi kapat" aria-label="Önizlemeyi kapat">@@i:close:sm@@</button>
    </form>
    <div class="preview-note" id="previewNote" role="status">Bu bilgisayarda çalışan bir uygulamanın adresini yazın (ör. 127.0.0.1:8000). Ajan yanıtındaki yerel adreslerin yanında da “Önizle” düğmesi çıkar.</div>
    <iframe class="preview-frame" id="previewFrame" title="Uygulama önizlemesi" sandbox="allow-scripts allow-forms allow-same-origin allow-downloads allow-modals" referrerpolicy="no-referrer" hidden></iframe>
  </aside>
</div>

<div class="palette-layer" id="paletteLayer" hidden>
  <div class="palette-scrim" id="paletteScrim"></div>
  <div class="palette" role="dialog" aria-modal="true" aria-label="Komut paleti">
    <div class="palette-input">
      @@i:search@@
      <input id="paletteInput" type="text" role="combobox" aria-expanded="true" aria-controls="paletteList" aria-autocomplete="list" autocomplete="off" spellcheck="false" placeholder="Komut veya sohbet ara…">
      <kbd>Esc</kbd>
    </div>
    <div class="palette-list" id="paletteList" role="listbox" aria-label="Sonuçlar"></div>
  </div>
</div>

<div class="confirm-layer" id="confirmModal" hidden>
  <div class="confirm-scrim" id="confirmScrim"></div>
  <div class="confirm-panel" role="alertdialog" aria-modal="true" aria-labelledby="confirmTitle" aria-describedby="confirmMessage">
    <h2 id="confirmTitle">Onay gerekiyor</h2>
    <p class="confirm-message" id="confirmMessage"></p>
    <div class="confirm-actions">
      <button type="button" class="control-btn" id="confirmCancel">Vazgeç</button>
      <button type="button" class="api-submit" id="confirmAccept">Onayla</button>
    </div>
  </div>
</div>

<div class="free-sheet-scrim" id="freeSheet" hidden>
  <section class="free-sheet" role="dialog" aria-modal="true" aria-labelledby="freeSheetTitle">
    <header class="free-sheet-head">
      <div>
        <h2 id="freeSheetTitle">Ücretsiz bağlantılar</h2>
        <p>Abonelik gerekmez. Bu şirketlerin ücretsiz anahtarlarından birini al, buraya yapıştır. Anahtarın yalnız bu bilgisayarda, Windows kullanıcı şifrelemesiyle saklanır.</p>
      </div>
      <button type="button" class="free-sheet-close" id="freeSheetClose" aria-label="Kapat">@@i:close@@</button>
    </header>
    <div class="free-channels" id="freeChannels" aria-live="polite"></div>
    <p class="free-sheet-note">Ücretsiz modda yalnız sohbet edilir: dosya, komut, internet ve bilgisayar kontrolü kapalıdır. Gönderme izni verdiğin her kanal bir sohbet ekibi gibi sırayla konuşur ve birbirinin yanıtını görür. Ücretsiz kotalar küçüktür; birinin kotası dolarsa yalnız yedek izni de verdiğin kanal onun yerine geçer. Bir model bir soruyu yanıtlamayı reddederse o tur biter; SpeS soruyu başka bir modele sormaz. Claude'un ücretsiz hesabı başka uygulamalara bağlanamaz.</p>
    <footer class="free-sheet-foot">
      <button type="button" class="free-start" id="freeSheetStart">Ücretsiz sohbeti başlat</button>
    </footer>
  </section>
</div>
<div class="signature-intro" id="signatureIntro" aria-hidden="true">
  @@MARK@@
  <div class="intro-brand">SpeS</div>
  <div class="intro-credit">CREATED BY <strong>ALI MEHDI</strong></div>
</div>

<div class="api-setup" id="cliSetup" role="dialog" aria-modal="true" aria-labelledby="cliWelcome">
  <div class="api-panel wide">
    <div class="panel-mark">@@MARK@@</div>
    <h2 id="cliWelcome">SpeS'e Hoş Geldiniz</h2>
    <p>Başka bir şey kurmana gerek yok: SpeS kendi araçlarını kendisi kurar. Sana kalan tek şey hesabınla giriş yapmak.</p>
    <p class="auto-setup-line" id="autoSetupLine" role="status" aria-live="polite" hidden></p>
    <div class="panel-actions" id="autoSetupActions" hidden>
      <button type="button" class="api-submit" id="cliPrepare">Araçları hazırla</button>
      <button type="button" class="control-btn" id="cliAutoStop" hidden>Kurulumu durdur</button>
    </div>
    <label for="cliProvider">Bağlantı</label>
    <select id="cliProvider"><option value="codex">Codex / OpenAI</option><option value="gemini">Gemini / Google</option><option value="claude">Claude / Anthropic</option></select>
    <div id="cliProviderState" class="log-box" aria-live="polite">Bağlantılar kontrol ediliyor…</div>
    <button type="button" class="api-submit" id="cliAccount">Hesabımla bağlan</button>
    <p class="help">Google hesabı bağımsız Antigravity CLI ile bağlanır; Desktop gerekmez. API anahtarı Gemini CLI ve ayrı API kotasını kullanır.</p>
    <label for="cliKey">Veya API anahtarı</label>
    <input id="cliKey" type="password" autocomplete="off" spellcheck="false" placeholder="Anahtarınız yalnız bu bilgisayarda saklanır">
    <div class="panel-actions">
      <button type="button" class="control-btn" id="cliValidate">Doğrula ve bağlan</button>
      <button type="button" class="control-btn" id="cliInstall">Hesap için CLI kur (Desktop gerekmez)</button>
      <button type="button" class="control-btn" id="cliCheck">Bağlantıyı kontrol et</button>
    </div>
    <div id="cliMessage" class="api-error" role="status" aria-live="polite"></div>
    <div class="panel-actions end">
      <button type="button" class="control-btn" id="cliFree">Aboneliğim yok: ücretsiz sohbet</button>
      <button type="button" class="control-btn" id="cliLater">Şimdi değil</button>
      <button type="button" class="api-submit" id="cliContinue" disabled>Sohbete geç</button>
    </div>
    <p class="privacy-note">Anahtar .env dosyasında; yalnız bağlantı bilgisi SpeS belleğinde tutulur. Sohbete ve günlüklere anahtar yazılmaz. Kurulum SpeS'e özel klasördedir; sistem PATH ayarı değişmez.</p>
  </div>
</div>

<div class="api-setup" id="apiSetup" role="dialog" aria-modal="true" aria-labelledby="apiSetupTitle">
  <div class="api-panel">
    <h2 id="apiSetupTitle">SpeS bağlantısı</h2>
    <p>Asistanı kullanmaya başlamak için API anahtarını bir kez doğrula. Sonraki açılışlarda bu ekran tekrar gösterilmez.</p>
    <label for="apiProvider">Sağlayıcı</label>
    <select id="apiProvider">
      <option value="nvidia">NVIDIA — GPT-OSS 20B</option>
      <option value="groq">Groq — GPT OSS 120B</option>
      <option value="github">GitHub Models</option>
    </select>
    <label for="apiKey">API anahtarı</label>
    <input id="apiKey" type="password" autocomplete="off" spellcheck="false" placeholder="Anahtarını buraya yapıştır">
    <button type="button" class="api-submit" id="apiSubmit">DOĞRULA VE BAŞLAT</button>
    <div class="api-error" id="apiError"></div>
    <p class="privacy-note">Anahtar yalnızca bu bilgisayardaki .env dosyasında saklanır; sohbet geçmişine ve loglara yazılmaz.</p>
  </div>
</div>

<div class="agent-overlay" id="agentOverlay" role="dialog" aria-modal="true" aria-labelledby="agentOverlayTitle">
  <div class="agent-panel">
    <div class="agent-head">
      <div class="agent-head-copy">
        <h2 id="agentOverlayTitle">Ajan merkezi</h2>
        <div class="agent-sub">Squad koordinasyonu · yerel abonelik CLI çalışma zamanı</div>
      </div>
      <select class="agent-select" id="agentProject" aria-label="Proje"></select>
      <button type="button" class="control-btn" id="btnAgentRefresh">Yenile</button>
      <button type="button" class="icon-btn" id="btnAgentClose" title="Kapat" aria-label="Ajan merkezini kapat">@@i:close:sm@@</button>
    </div>
    <div class="agent-status-grid">
      <div class="agent-status-card"><strong>Squad</strong><span id="agentSquadStatus">Kontrol ediliyor...</span></div>
      <div class="agent-status-card"><strong>Codex</strong><span id="agentCodexStatus">Kontrol ediliyor...</span></div>
      <div class="agent-status-card"><strong>Gemini / Antigravity</strong><span id="agentGeminiStatus">Doğrulanmadı</span></div>
    </div>
    <div class="agent-compose">
      <textarea class="agent-prompt" id="agentPrompt" aria-label="Görev açıklaması" placeholder="Gerçek ajanlara görev ver..."></textarea>
      <div class="agent-compose-side">
        <select class="agent-select" id="agentProvider" aria-label="Ajan">
          <option value="codex">Codex</option>
          <option value="antigravity">Antigravity</option>
          <option value="collaboration">Codex + Antigravity</option>
        </select>
        <select class="agent-select" id="agentWrite" aria-label="Görev Yetkisi" hidden>
          <option value="full" selected>Tam Yetki</option>
          <!-- <option value="read-only" selected> -->
        </select>
        <button type="button" class="api-submit" id="btnAgentDispatch">Ajana ata</button>
        <div class="agent-error" id="agentModelSelection">Üstteki sohbet model seçimleri kullanılır.</div>
        <div class="agent-error" id="agentError"></div>
      </div>
    </div>
    <div class="operator-card">
      <strong>Bilgisayar operatörü · ayrı oturum izni</strong>
      <p>Yalnız seçili pencere. Aynı anda tek ajan. Kimlik doğrulama, güvenlik, silme/ödeme ve kayıt üzerine yazma kapsam dışıdır. Deneysel: Windows UIA ve yerel WebView fare/tuş testi geçti; her uygulama için ayrıca doğrulama gerekir. Warband girişi Universal Modder koruma adaptörü tamamlanana kadar kapalıdır.</p>
      <div class="operator-row">
        <select class="agent-select" id="desktopWindow" aria-label="Kontrol edilecek pencere"></select>
        <button type="button" class="control-btn" id="btnDesktopWindows">Pencereleri getir</button>
        <button type="button" class="control-btn" id="btnDesktopStart">Seçili ajanla kontrol et</button>
        <button type="button" class="control-btn" id="btnDesktopStop">Kontrolü durdur</button>
      </div>
      <pre id="desktopOperatorStatus">KAPALI · Görev açıklamasını yukarıya yazın. Model seçimleri sohbet seçicilerinden alınır.</pre>
    </div>
    <div class="agent-columns">
      <div class="agent-column"><h3>Gerçek çalışma zamanları</h3><div class="agent-scroll" id="agentRuns"></div></div>
      <div class="agent-column"><h3>Squad görevleri / ajanlar</h3><div class="agent-scroll" id="agentTasks"></div></div>
      <div class="agent-column"><h3>Mesaj geçmişi</h3><div class="agent-scroll" id="agentHistory"></div></div>
    </div>
  </div>
</div>

"""

SHELL_MARKUP = SHELL_MARKUP.replace("@@SPRITE@@", _SPRITE).replace("@@BRAND_MARK@@", _BRAND_MARK).replace("@@MARK@@", _MARK)
for _name, _size in (("stop", "sm"), ("plus", "md"), ("search", "md"), ("sidebar", "md"), ("pulse", "md"),
                     ("panel", "md"), ("minus", "sm"), ("maximize", "sm"), ("compact", "sm"), ("close", "sm"), ("loop", "sm"),
                     ("mic", "md"), ("send", "md"), ("camera", "md"), ("chip", "md"), ("windows", "md"),
                     ("spark", "md"), ("eye", "md"), ("agents", "md"), ("phone", "md"), ("wave", "md"),
                     ("volume", "md"), ("shield", "md"), ("trash", "md"), ("globe", "md"), ("windows", "sm"),
                     ("clip", "md")):
    SHELL_MARKUP = SHELL_MARKUP.replace(f"@@i:{_name}:{_size}@@", _icon(_name, _size)).replace(f"@@i:{_name}@@", _icon(_name))
