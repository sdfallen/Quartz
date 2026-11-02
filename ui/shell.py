"""Main chat shell markup: everything from ``</head>`` up to the script block.

Presentation only. It holds element ids, Turkish labels and static structure;
no service is created here and nothing here calls the pywebview API. Behaviour
is wired by the application JavaScript that still lives in ``gui.py``
(``scripts/check_gui_javascript.py`` reads that script from gui.py's source),
and ``gui._HTML_BODY`` is ``SHELL_MARKUP`` followed by that script, byte for
byte the same document as before the split. See docs/CLAUDE_PYRAMID_FRONTEND.md.

Do not put a script element in this module: the shipped JavaScript must stay
where the syntax check can read it.
"""

SHELL_MARKUP = r"""
</head>
<body>

<div class="screen-control-hud" id="screenControlHud" hidden>
  <span class="hud-dot"></span>
  <div class="hud-meta">
    <span class="hud-title" id="screenControlHudTitle">QUARTZ KONTROLDE</span>
    <span class="hud-sub" id="screenControlHudSub">Yalnız bu tuşla durdurulur</span>
  </div>
  <button type="button" class="hud-stop-btn" id="btnHudStopTask">⏹ GÖREVİ DURDUR</button>
</div>

<div class="shell">

  <div class="titlebar pywebview-drag-region">
    <div class="orb-wrap" id="orbWrap">
      <div class="orb-ring"></div>
      <div class="orb-core" id="orbCore"></div>
    </div>
    <div class="brand">QUARTZ</div>
    <div class="status-pill offline" id="statusPill">
      <div class="dot"></div><span id="statusText">CONNECTING</span>
    </div>
    <div class="titlebar-spacer"></div>
    <div class="signature-mark" title="Ali Mehdi">AM</div>
    <button class="voice-toggle" id="btnPanels" title="Yan panelleri ve sistem araçlarını göster/gizle">☰ Araçlar</button>
    <button class="voice-toggle" id="btnWake" title="Uyandırma kelimesi: &quot;Hey Quartz&quot;">◎ Wake</button>
    <button class="voice-toggle active" id="btnTts" title="Sesli yanıt aç/kapat">🔊 TTS</button>
    <div class="clock" id="clock">--:--:--</div>
    <button class="win-btn" id="btnMin" title="Küçült">─</button>
    <button class="win-btn close" id="btnClose" title="Kapat">✕</button>
  </div>

  <div class="body">

    <div class="rail left">
      <div class="card">
        <div class="card-label">Hızlı İşlemler</div>
        <button class="qa-btn" data-action="screenshot"><span class="ic">⬡</span> Ekran Görüntüsü</button>
        <button class="qa-btn" data-action="sysinfo"><span class="ic">⬡</span> Sistem Bilgisi</button>
        <button class="qa-btn" data-action="windows"><span class="ic">▣</span> Açık Pencereler</button>
        <button class="qa-btn" data-action="desktop" style="display:none"><span class="ic">⬡</span> Masaüstünü Listele</button>
        <button class="qa-btn" data-action="plugins" style="display:none"><span class="ic">⬡</span> Eklentiler</button>
        <button class="qa-btn" data-action="update_all" style="display:none"><span class="ic">⬡</span> Hepsini Güncelle</button>
        <button class="qa-btn quartz-mode" data-action="quartz_mode"><span class="ic">◉</span> Quartz Mode</button>
        <button class="qa-btn" id="btnAdvisor"><span class="ic">◌</span> Ekran Rehberi: KAPALI</button>
        <button class="qa-btn" id="btnAgentCenter"><span class="ic">◇</span> Ajan Merkezi</button>
        <button class="qa-btn" id="btnMobile"><span class="ic">◇</span> Mobil Erişim</button>
        <button class="qa-btn" id="btnClear"><span class="ic">⬡</span> Sohbeti Temizle</button>
      </div>
      <div class="card">
        <div class="card-label">Güvenlik</div>
        <button class="control-btn" id="btnSafe">Güvenli Mod: KAPALI</button>
        <div class="log-box" id="pluginPermissions" style="margin-top:8px"></div>
      </div>
    </div>

    <div class="chat-col">
      <div class="chat-header">
        <div class="chat-title-group">
          <span class="chat-conv-title" id="chatConvTitle">Yeni Sohbet</span>
          <select class="project-picker" id="mainProjectSelect" title="Aktif Proje" aria-label="Aktif Proje"></select>
          <button class="chat-tool-btn" id="btnAddProject" title="Windows klasör seçicisiyle proje ekle">＋ Proje</button>
          <span class="project-tag" id="writerBadge" style="display:none"></span>
          <details id="writerRecoveryPanel" hidden style="max-width:720px;font-size:12px">
            <summary>Kesilen yazıcı görevi — inceleme gerekli</summary><div id="writerRecoveryBody"></div>
          </details>
          <span class="project-tag" id="chatProjectTag" title="Çalışma Alanı" style="display:none">SquadPilot</span>
          <span class="squad-badge" id="squadBadge" title="Squad Mesajlaşma Altyapısı">Squad: Bağlı</span>
        </div>
        <div class="agent-seg-group" id="agentSegGroup" role="tablist" aria-label="Ajan Seçici">
          <button type="button" class="agent-seg-btn active" data-agent="antigravity">◈ Antigravity</button>
          <button type="button" class="agent-seg-btn" data-agent="codex">◈ Codex</button>
          <button type="button" class="agent-seg-btn" data-agent="collaboration">◈ Birlikte</button>
        </div>
        <div class="chat-controls-group">
          <select class="project-picker" id="mainPermissionLevel" title="Tam Yetki (Tek Yetki Sistemi)" aria-label="İşlem Yetkisi" style="display:none">
            <option value="full" selected>Tam Yetki</option>
          </select>
          <input type="checkbox" id="mainWriteToggle" style="display:none" checked>
          <span id="permissionSelectionHint" aria-live="polite" style="font-size:11px;max-width:280px;color:#34eaff;font-weight:600">◉ Tam Yetki Aktif</span>
          <div class="agent-badge-select" title="Aktif Ajan" style="display:none">
            <span style="font-size:10px">◈</span>
            <select id="mainAgentSelect">
              <option value="antigravity">Antigravity</option>
              <option value="codex">Codex</option>
              <option value="collaboration">Birlikte (Squad)</option>
            </select>
          </div>
          <button class="chat-tool-btn" id="btnContinueCollab" style="display:none" title="Birlikte modunda ajanlar arası tartışmayı 1 tur daha sürdür">⇄ +1 Tur</button>
          <button type="button" class="chat-tool-btn" id="btnSelfDiagnostics" title="Quartz öz teşhisini bu sohbette başlat">◈ Öz Teşhis</button>
          <button class="chat-tool-btn" id="btnNewChat" title="Yeni Sohbet Başlat">＋ Yeni</button>
        </div>
        <div class="chat-models-bar" id="chatModelsBar">
          <div class="model-selector-pill active-agy" id="agyModelPill" title="Antigravity Model ve Düşünme Seviyesi Seçimi">
            <span class="pill-agent-name">ANTIGRAVITY</span>
            <select id="agyModelSelect" aria-label="Antigravity Modeli">
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
            <span class="pill-sep">·</span>
            <select id="agyEffortSelect" aria-label="Antigravity Düşünme Seviyesi" title="Antigravity Düşünme Seviyesi (--effort)">
              <option value="low">low</option>
              <option value="medium" selected>medium</option>
              <option value="high">high</option>
              <option value="xhigh">xhigh</option>
              <option value="max">max</option>
            </select>
          </div>
          <div class="model-selector-pill" id="codexModelPill" title="Codex Model ve Düşünme Seviyesi Seçimi">
            <span class="pill-agent-name">CODEX</span>
            <select id="codexModelSelect" aria-label="Codex Modeli">
              <option value="gpt-6.1-sol">GPT-6.1-Sol</option>
              <option value="gpt-6-astra">GPT-6-Astra</option>
              <option value="gpt-6-sol">GPT-6-Sol</option>
              <option value="gpt-6-luna">GPT-6-Luna</option>
              <option value="gpt-5.6-sol">GPT-5.6-Sol</option>
              <option value="gpt-5.6-terra">GPT-5.6-Terra</option>
              <option value="gpt-5.6-luna">GPT-5.6-Luna</option>
            </select>
            <span class="pill-sep">·</span>
            <select id="codexEffortSelect" aria-label="Codex Düşünme Seviyesi" title="Codex Düşünme Seviyesi (model_reasoning_effort)">
              <option value="low" selected>low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="xhigh">xhigh</option>
              <option value="max">max</option>
              <option value="ultra">ultra</option>
            </select>
          </div>
        </div>
      </div>
      <div class="desktop-task-bar" id="desktopTaskBar" data-state="normal">
        <div class="desktop-task-copy" aria-live="polite">
          <strong id="desktopTaskLabel">Normal sohbet</strong>
          <span id="desktopTaskDetail">Dosya erişimi ayrı; masaüstü kontrolü görev onayı gerektirir.</span>
        </div>
        <button type="button" class="control-btn" id="btnDesktopTaskStop" hidden>Görevi durdur</button>
      </div>
      <div class="chat" id="chat"></div>
      <button type="button" class="jump-bottom-btn" id="btnJumpBottom" title="En son mesaja git">Yeni mesajlar ↓</button>
      <div class="thinking-row" id="thinkingRow">
        <div class="d"></div><div class="d"></div><div class="d"></div>
        <span id="thinkingText">işleniyor...</span>
        <button class="control-btn" id="btnCancel" title="Etkin görevi ve ajan süreçlerini durdur" style="display:none">Görevi durdur</button>
      </div>
      <div class="inputbar">
        <input type="text" id="msgInput" aria-label="Ekibe yazın veya görev verin" aria-keyshortcuts="Control+L" title="Sohbete odaklan: Ctrl+L · Gönder: Enter" placeholder="Antigravity veya Codex'e mesaj yaz..." autofocus>
        <button class="icon-btn mic" id="btnMic" title="Konuş (push-to-talk)">🎤</button>
        <button class="icon-btn send" id="btnSend">➤</button>
      </div>
    </div>

    <div class="rail right">
      <div class="card">
        <div class="card-label">Yanıt Ayrıntısı</div>
        <select class="agent-select" id="responseDetail" aria-label="Yanıt Ayrıntısı" style="width:100%">
          <option value="short" selected>Kısa (varsayılan)</option>
          <option value="normal">Normal</option>
          <option value="technical">Teknik</option>
        </select>
        <div style="font-size:11px;opacity:.7;margin-top:5px">Codex, Antigravity ve Birlikte için geçerlidir.</div>
      </div>
      <div class="card">
        <div class="card-label">Sistem</div>
        <div class="stat-row">
          <div class="stat-top"><span>CPU</span><span class="val" id="cpuVal">--%</span></div>
          <div class="stat-bar"><div class="stat-fill" id="cpuFill"></div></div>
        </div>
        <div class="stat-row">
          <div class="stat-top"><span>RAM</span><span class="val" id="memVal">--%</span></div>
          <div class="stat-bar"><div class="stat-fill" id="memFill"></div></div>
        </div>
        <div class="stat-row">
          <div class="stat-top"><span>DISK</span><span class="val" id="diskVal">--%</span></div>
          <div class="stat-bar"><div class="stat-fill" id="diskFill"></div></div>
        </div>
      </div>
      <div class="card">
        <div class="card-label">Sağlayıcı Yöneticisi</div>
        <div class="log-box" id="providerStatus">Kontrol ediliyor...</div>
        <button class="control-btn" id="btnProviderProbe" style="margin-top:7px;width:100%">Bağlantıyı Test Et</button>
        <button class="control-btn" id="btnCliConnections" style="margin-top:7px;width:100%">Hesaplar ve CLI kurulumu</button>
      </div>
      <div class="card">
        <div class="card-label">Oturum</div>
        <div class="sess-row"><span>Mesaj</span><span class="val" id="sessMsgs">0</span></div>
        <div class="sess-row"><span>Süre</span><span class="val" id="sessUptime">00:00:00</span></div>
        <div class="sess-row"><span>Durum</span><span class="val" id="sessStatus">—</span></div>
      </div>
      <div class="card">
        <div class="card-label">Aktif Operasyon</div>
        <div class="log-box" id="operationStatus">Aktif görev yok</div>
        <div style="display:flex;gap:6px;margin-top:7px">
          <button class="control-btn" id="btnLearnOperation" style="display:none">Öğren</button>
          <button class="control-btn" id="btnFinishOperation" style="display:none">Bitir</button>
        </div>
      </div>
      <div class="card">
        <div class="card-label">Görevler</div>
        <div class="log-box" id="taskList">Henüz görev yok</div>
      </div>
      <div class="card" style="flex:1; min-height:0; display:flex; flex-direction:column;">
        <div class="card-label">Log</div>
        <div class="log-box" id="logBox"></div>
      </div>
    </div>

  </div>
  <div class="signature-main">
    <span>DESIGNED &amp; ENGINEERED BY</span><strong>ALI MEHDI</strong>
  </div>
</div>

<div class="signature-intro" id="signatureIntro" aria-hidden="true">
  <div class="intro-brand">QUARTZ</div>
  <div class="intro-credit">CREATED BY <strong>ALI MEHDI</strong></div>
</div>

<div class="api-setup" id="cliSetup" role="dialog" aria-modal="true" aria-labelledby="cliWelcome">
  <div class="api-panel" style="max-width:570px;max-height:90vh;overflow:auto">
    <h2 id="cliWelcome">Quartz'a Hoş Geldiniz</h2>
    <p>Tek bir hesapla başlayabilirsiniz. Codex veya Antigravity masaüstü uygulaması gerekmez. Hafif CLI araçlarını Quartz sizin için kurar.</p>
    <label for="cliProvider">BAĞLANTI</label>
    <select id="cliProvider"><option value="codex">Codex / OpenAI</option><option value="gemini">Gemini / Google</option></select>
    <div id="cliProviderState" class="log-box" aria-live="polite">Bağlantılar kontrol ediliyor…</div>
    <button class="api-submit" id="cliAccount">Hesabımla bağlan</button>
    <p>Google hesabı bağımsız Antigravity CLI ile bağlanır; Desktop gerekmez. API anahtarı Gemini CLI ve ayrı API kotasını kullanır.</p>
    <label for="cliKey">VEYA API ANAHTARI</label>
    <input id="cliKey" type="password" autocomplete="off" spellcheck="false" placeholder="Anahtarınız yalnız bu bilgisayarda saklanır">
    <button class="api-submit" id="cliValidate">Doğrula ve bağlan</button>
    <button class="control-btn" id="cliInstall">Hesap için CLI kur (Desktop gerekmez)</button>
    <button class="control-btn" id="cliCheck">Bağlantıyı kontrol et</button>
    <div id="cliMessage" class="api-error" role="status" aria-live="polite"></div>
    <button class="api-submit" id="cliContinue" disabled>Sohbete geç</button>
    <button class="control-btn" id="cliLater">Şimdi değil</button>
    <p class="privacy-note">Anahtar .env dosyasında; yalnız bağlantı bilgisi Quartz belleğinde tutulur. Sohbete ve günlüklere anahtar yazılmaz. Kurulum Quartz'a özel klasördedir; sistem PATH ayarı değişmez.</p>
  </div>
</div>

<div class="api-setup" id="apiSetup">
  <div class="api-panel">
    <h2>QUARTZ BAĞLANTISI</h2>
    <p>Asistanı kullanmaya başlamak için API anahtarını bir kez doğrula. Sonraki açılışlarda bu ekran tekrar gösterilmez.</p>
    <label for="apiProvider">SAĞLAYICI</label>
    <select id="apiProvider">
      <option value="nvidia">NVIDIA — GPT-OSS 20B</option>
      <option value="groq">Groq — GPT OSS 120B</option>
      <option value="github">GitHub Models</option>
    </select>
    <label for="apiKey">API ANAHTARI</label>
    <input id="apiKey" type="password" autocomplete="off" spellcheck="false" placeholder="Anahtarını buraya yapıştır">
    <button class="api-submit" id="apiSubmit">DOĞRULA VE BAŞLAT</button>
    <div class="api-error" id="apiError"></div>
    <p class="privacy-note">Anahtar yalnızca bu bilgisayardaki .env dosyasında saklanır; sohbet geçmişine ve loglara yazılmaz.</p>
  </div>
</div>

<div class="agent-overlay" id="agentOverlay">
  <div class="agent-panel">
    <div class="agent-head">
      <h2>AJAN MERKEZİ</h2>
      <div class="agent-sub">SQUAD KOORDİNASYONU · YEREL ABONELİK CLI ÇALIŞMA ZAMANI</div>
      <select class="agent-select" id="agentProject"></select>
      <button class="control-btn" id="btnAgentRefresh">Yenile</button>
      <button class="win-btn close" id="btnAgentClose">✕</button>
    </div>
    <div class="agent-status-grid">
      <div class="agent-status-card"><strong>SQUAD</strong><span id="agentSquadStatus">Kontrol ediliyor...</span></div>
      <div class="agent-status-card"><strong>CODEX</strong><span id="agentCodexStatus">Kontrol ediliyor...</span></div>
      <div class="agent-status-card"><strong>GEMINI / ANTIGRAVITY</strong><span id="agentGeminiStatus">Doğrulanmadı</span></div>
    </div>
    <div class="agent-compose">
      <textarea class="agent-prompt" id="agentPrompt" placeholder="Gerçek ajanlara görev ver..."></textarea>
      <div class="agent-compose-side">
        <select class="agent-select" id="agentProvider">
          <option value="codex">Codex</option>
          <option value="antigravity">Antigravity</option>
          <option value="collaboration">Codex + Antigravity</option>
        </select>
        <select class="agent-select" id="agentWrite" aria-label="Görev Yetkisi" style="display:none">
          <option value="full" selected>Tam Yetki</option>
          <!-- <option value="read-only" selected> -->
        </select>
        <button class="control-btn" id="btnAgentDispatch">AJANA ATA</button>
        <div class="agent-error" id="agentModelSelection">Üstteki sohbet model seçimleri kullanılır.</div>
        <div class="agent-error" id="agentError"></div>
      </div>
    </div>
    <div style="padding:12px;border:1px solid #3a6670;margin:8px 0">
      <strong>BİLGİSAYAR OPERATÖRÜ · AYRI OTURUM İZNİ</strong>
      <p style="font-size:12px">Yalnız seçili pencere. Aynı anda tek ajan. Başka pencereye geçmek girdiyi keser.
      Kimlik doğrulama, güvenlik, silme/ödeme ve kayıt üzerine yazma kapsam dışıdır.
      Deneysel: Windows UIA ve yerel WebView fare/tuş testi geçti; her uygulama için ayrıca doğrulama gerekir.
      Warband girişi Universal Modder koruma adaptörü tamamlanana kadar kapalıdır.</p>
      <select class="agent-select" id="desktopWindow" aria-label="Kontrol edilecek pencere"></select>
      <button class="control-btn" id="btnDesktopWindows">Pencereleri Getir</button>
      <button class="control-btn" id="btnDesktopStart">Seçili Ajanla Kontrol Et</button>
      <button class="control-btn" id="btnDesktopStop" style="color:#ff8888">KONTROLÜ DURDUR</button>
      <pre id="desktopOperatorStatus" style="white-space:pre-wrap;max-height:180px;overflow:auto">KAPALI · Görev açıklamasını yukarıya yazın. Model seçimleri sohbet seçicilerinden alınır.</pre>
    </div>
    <div class="agent-columns">
      <div class="agent-column"><h3>GERÇEK ÇALIŞMA ZAMANLARI</h3><div class="agent-scroll" id="agentRuns"></div></div>
      <div class="agent-column"><h3>SQUAD GÖREVLERİ / AJANLAR</h3><div class="agent-scroll" id="agentTasks"></div></div>
      <div class="agent-column"><h3>MESAJ GEÇMİŞİ</h3><div class="agent-scroll" id="agentHistory"></div></div>
    </div>
  </div>
</div>

"""
