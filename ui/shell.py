"""Main chat shell markup: everything from ``</head>`` up to the script block.

Presentation only. It holds element ids, Turkish labels and static structure;
no service is created here and nothing here calls the pywebview API. Behaviour
is wired by the application JavaScript in ``ui/js_*.py``.

Do not put a script element in this module: the shipped JavaScript must stay
where the syntax check can read it. Visual decisions:
docs/CLAUDE_FRONTEND_REDESIGN_20261104.md.
"""

# Same geometry as scripts/build_brand_assets.py; tests/test_branding.py keeps them equal.
_MARK_FACETS = '<polygon class="f f1" points="122.00,14.00 212.07,66.00 165.30,93.00 122.00,68.00"/><polygon class="f f2" points="212.07,66.00 212.07,170.00 165.30,143.00 165.30,93.00"/><polygon class="f f3" points="212.07,170.00 122.00,222.00 122.00,168.00 165.30,143.00"/><polygon class="f f4" points="122.00,222.00 31.93,170.00 78.70,143.00 122.00,168.00"/><polygon class="f f5" points="31.93,170.00 31.93,66.00 78.70,93.00 78.70,143.00"/><polygon class="f f6" points="31.93,66.00 122.00,14.00 122.00,68.00 78.70,93.00"/><polygon class="f f7" points="122.00,122.00 152.00,106.00 236.00,222.00 200.00,240.00"/>'

_MARK = ('<svg class="q-mark" viewBox="0 0 256 256" aria-hidden="true" focusable="false">'
         + _MARK_FACETS + '</svg>')
_BRAND_MARK = ('<svg class="q-mark brand-icon" id="orbCore" data-state="idle" viewBox="0 0 256 256" '
               'role="img" aria-label="Quartz" focusable="false">' + _MARK_FACETS + '</svg>')


def _icon(name, size="md"):
    return f'<svg class="i i-{size}" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>'


_SPRITE = """<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
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
<symbol id="i-loop" viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 13.7-5.6L20 9M20 4v5h-5M20 12a8 8 0 0 1-13.7 5.6L4 15M4 20v-5h5"/></symbol>
</defs></svg>"""


SHELL_MARKUP = r"""
</head>
<body>
@@SPRITE@@

<div class="screen-control-hud" id="screenControlHud" role="status" hidden>
  <span class="hud-dot" aria-hidden="true"></span>
  <div class="hud-meta">
    <span class="hud-title" id="screenControlHudTitle">Quartz kontrolde</span>
    <span class="hud-sub" id="screenControlHudSub">Yalnız bu tuşla durdurulur</span>
  </div>
  <button type="button" class="hud-stop-btn" id="btnHudStopTask">@@i:stop:sm@@Görevi durdur</button>
</div>

<div class="app shell">

  <!-- Quartz layout (7 Nov 2026, built from scratch): a slim rail, a drawer for
       conversations, and a stage where Codex and Antigravity each have a column
       either side of the conversation with the Quartz crystal at its head. -->
  <nav class="app-rail pywebview-drag-region" aria-label="Quartz">
    <div class="rail-mark" id="orbWrap">@@BRAND_MARK@@</div>
    <button type="button" class="rail-btn primary" id="btnNewChat" title="Yeni sohbet başlat" aria-label="Yeni sohbet">@@i:plus@@<span class="rail-tip" aria-hidden="true">Yeni sohbet</span></button>
    <button type="button" class="rail-btn" id="btnSidebar" title="Sohbetler ve projeler (Ctrl+B)" aria-label="Sohbetler ve projeler" aria-controls="sidebar" aria-keyshortcuts="Control+B">@@i:sidebar@@<span class="rail-tip" aria-hidden="true">Sohbetler</span></button>
    <button type="button" class="rail-btn" id="btnCommand" title="Ara ve komutlar (Ctrl+K)" aria-label="Ara ve komutlar" aria-keyshortcuts="Control+K">@@i:search@@<span class="rail-tip" aria-hidden="true">Ara ve komutlar</span></button>
    <div class="rail-spacer"></div>
    <button type="button" class="rail-btn" id="btnSelfDiagnostics" title="Quartz öz teşhisini bu sohbette başlat" aria-label="Öz teşhis">@@i:pulse@@<span class="rail-tip" aria-hidden="true">Öz teşhis</span></button>
    <button type="button" class="rail-btn" id="btnPanels" title="Durum ve araç panelini aç/kapat (Ctrl+I)" aria-label="Durum ve araçlar" aria-keyshortcuts="Control+I">@@i:panel@@<span class="rail-tip" aria-hidden="true">Durum ve araçlar</span></button>
    <div class="signature-mark" title="Ali Mehdi">AM</div>
  </nav>

  <div class="drawer-scrim" id="drawerScrim"></div>
  <aside class="sidebar" id="sidebar" aria-label="Sohbetler ve projeler">
    <div class="side-head">
      <div class="brand">QUARTZ</div>
      <button type="button" class="icon-btn" id="btnDrawerClose" title="Kapat (Esc)" aria-label="Sohbetler panelini kapat">@@i:close:sm@@</button>
    </div>
    <div class="side-section">
      <div class="workspace-nav-title">Proje</div>
      <div class="workspace-project">
        <select class="project-picker" id="mainProjectSelect" title="Aktif proje" aria-label="Aktif proje"></select>
        <button type="button" class="icon-btn" id="btnAddProject" title="Windows klasör seçicisiyle proje ekle" aria-label="Proje ekle">@@i:plus@@</button>
      </div>
      <button type="button" class="project-chats-delete" id="btnRemoveProject" title="Proje klasörü ve dosyaları silinmez">Projeyi listeden kaldır</button>
    </div>
    <div class="side-section grow">
      <div class="workspace-nav-title">Sohbetler</div>
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
      <div class="chat-title-group">
        <span class="chat-conv-title" id="chatConvTitle">Yeni Sohbet</span>
        <span class="project-tag" id="writerBadge" style="display:none"></span>
        <span class="project-tag" id="chatProjectTag" title="Çalışma alanı" style="display:none"></span>
      </div>
      <div class="titlebar-spacer"></div>
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
              <span class="lane-name">Codex</span>
              <span class="lane-state" id="laneCodexState">Hazır</span>
            </span>
          </button>
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
      <section class="empty-state" id="emptyState" aria-label="Başlangıç">
        @@MARK@@
        <h1 id="emptyGreeting">Merhaba.</h1>
        <p>Antigravity ve Codex burada. Bir görev yazın ya da buradan başlayın.</p>
        <div class="prompt-chips">
          <button type="button" class="prompt-chip" data-prompt="Bu projenin yapısını incele ve kısaca özetle.">Projeyi özetle</button>
          <button type="button" class="prompt-chip" data-prompt="Testleri çalıştır, başarısız olanların nedenini açıkla.">Testleri çalıştır</button>
          <button type="button" class="prompt-chip" data-prompt="Son değişiklikleri gözden geçir ve riskleri listele.">Değişiklikleri incele</button>
          <button type="button" class="prompt-chip" data-prompt="Açık uygulamada şunu yap: ">Bilgisayarda görev ver</button>
        </div>
      </section>
      <button type="button" class="jump-bottom-btn" id="btnJumpBottom" title="En son mesaja git">Yeni mesajlar ↓</button>
    </div>

          <div class="dock">
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
            <div class="inputbar composer">
              <textarea id="msgInput" rows="1" aria-label="Ekibe yazın veya görev verin" aria-keyshortcuts="Control+L" title="Sohbete odaklan: Ctrl+L · Gönder: Enter · Yeni satır: Shift+Enter" placeholder="Ekibe yazın veya görev verin…" autofocus></textarea>
              <div class="composer-row">
                <div class="agent-seg-group" id="agentSegGroup" role="group" aria-label="Ajan seçici">
            <span class="seg-thumb" id="agentSegThumb" aria-hidden="true"></span>
            <button type="button" class="agent-seg-btn active" data-agent="antigravity">Antigravity</button>
            <button type="button" class="agent-seg-btn" data-agent="codex">Codex</button>
            <button type="button" class="agent-seg-btn" data-agent="collaboration">Birlikte</button>
          </div>
                <div class="composer-spacer"></div>
                <button type="button" class="chat-tool-btn" id="btnContinueCollab" style="display:none" title="Birlikte modunda ajanlar arası tartışmayı 1 tur daha sürdür">@@i:loop:sm@@ 1 tur daha</button>
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
              <span class="lane-name">Antigravity</span>
              <span class="lane-state" id="laneAgyState">Hazır</span>
            </span>
          </button>
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
          <span>Kristal</span>
          <div class="swatches" role="group" aria-label="Vurgu rengi" id="prefCrystal">
            <button type="button" data-value="rose" title="Pembe kuvars" aria-label="Pembe kuvars"></button>
            <button type="button" data-value="citrine" title="Sitrin" aria-label="Sitrin"></button>
            <button type="button" data-value="amethyst" title="Ametist" aria-label="Ametist"></button>
            <button type="button" data-value="smoky" title="Kaya kristali" aria-label="Kaya kristali"></button>
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
        <button type="button" class="qa-btn voice-toggle" id="btnWake" title="Uyandırma kelimesi: &quot;Hey Quartz&quot;">@@i:wave@@ <span id="wakeLabel">Uyandırma kelimesi: kapalı</span></button>
        <button type="button" class="qa-btn voice-toggle active" id="btnTts" title="Sesli yanıt aç/kapat">@@i:volume@@ <span id="ttsLabel">Sesli yanıt: açık</span></button>
      </section>
      <section class="card">
        <div class="card-label">Güvenlik</div>
        <button type="button" class="qa-btn" id="btnSafe">@@i:shield@@ <span id="safeLabel">Güvenli mod: kapalı</span></button>
        <div class="log-box plugin-permissions" id="pluginPermissions"></div>
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

<div class="signature-intro" id="signatureIntro" aria-hidden="true">
  @@MARK@@
  <div class="intro-brand">QUARTZ</div>
  <div class="intro-credit">CREATED BY <strong>ALI MEHDI</strong></div>
</div>

<div class="api-setup" id="cliSetup" role="dialog" aria-modal="true" aria-labelledby="cliWelcome">
  <div class="api-panel wide">
    <div class="panel-mark">@@MARK@@</div>
    <h2 id="cliWelcome">Quartz'a Hoş Geldiniz</h2>
    <p>Tek bir hesapla başlayabilirsiniz. Codex veya Antigravity masaüstü uygulaması gerekmez. Hafif CLI araçlarını Quartz sizin için kurar.</p>
    <label for="cliProvider">Bağlantı</label>
    <select id="cliProvider"><option value="codex">Codex / OpenAI</option><option value="gemini">Gemini / Google</option></select>
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
      <button type="button" class="control-btn" id="cliLater">Şimdi değil</button>
      <button type="button" class="api-submit" id="cliContinue" disabled>Sohbete geç</button>
    </div>
    <p class="privacy-note">Anahtar .env dosyasında; yalnız bağlantı bilgisi Quartz belleğinde tutulur. Sohbete ve günlüklere anahtar yazılmaz. Kurulum Quartz'a özel klasördedir; sistem PATH ayarı değişmez.</p>
  </div>
</div>

<div class="api-setup" id="apiSetup" role="dialog" aria-modal="true" aria-labelledby="apiSetupTitle">
  <div class="api-panel">
    <h2 id="apiSetupTitle">Quartz bağlantısı</h2>
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
                     ("volume", "md"), ("shield", "md"), ("trash", "md")):
    SHELL_MARKUP = SHELL_MARKUP.replace(f"@@i:{_name}:{_size}@@", _icon(_name, _size)).replace(f"@@i:{_name}@@", _icon(_name))
