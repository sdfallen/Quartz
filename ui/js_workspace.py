"""Workspace behaviour that only exists for the new shell.

Theme and crystal preference, sliding selectors, panels, keyboard shortcuts,
the command palette and small conveniences. It clicks existing controls instead
of calling task APIs directly, so Stop, permission and writer rules stay with
the code that already owns them. Destructive actions are left out of the palette.
"""

JAVASCRIPT = r"""
  // ── Workspace shell ─────────────────────────────────────
  const uiRoot = document.documentElement;
  const UI_DEFAULTS = {theme: 'dark', crystal: 'citrine'};
  function markPrefButtons() {
    document.querySelectorAll('#prefTheme button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === uiRoot.dataset.theme)));
    document.querySelectorAll('#prefCrystal button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === uiRoot.dataset.crystal)));
  }
  function applyUiPreference(key, value, persist=true) {
    uiRoot.dataset[key] = value;
    markPrefButtons();
    if (!persist) return;
    const notice = document.getElementById('prefNotice');
    const report = text => { notice.textContent = text; notice.hidden = !text; };
    report('');
    Promise.resolve().then(() => window.pywebview.api.ui_set_preference(key, value)).then(result => {
      if (result?.status !== 'ok') throw new Error(result?.data || 'Bilinmeyen hata');
    }).catch(error => {
      report('Görünüm tercihi kaydedilemedi; yalnız bu oturumda geçerli.');
      logLine('Görünüm tercihi kaydedilemedi: ' + String(error.message || error));
    });
  }
  if (!uiRoot.dataset.theme) uiRoot.dataset.theme = UI_DEFAULTS.theme;
  if (!uiRoot.dataset.crystal) uiRoot.dataset.crystal = UI_DEFAULTS.crystal;
  markPrefButtons();
  document.querySelectorAll('#prefTheme button').forEach(b => b.addEventListener('click', () => applyUiPreference('theme', b.dataset.value)));
  document.querySelectorAll('#prefCrystal button').forEach(b => b.addEventListener('click', () => applyUiPreference('crystal', b.dataset.value)));

  function moveThumb(thumb, target) {
    if (!thumb || !target || !target.offsetWidth) return;
    thumb.style.width = target.offsetWidth + 'px';
    thumb.style.transform = `translateX(${target.offsetLeft}px)`;
  }
  const agentThumb = document.getElementById('agentSegThumb');
  const tabThumb = document.getElementById('inspectorTabThumb');
  function syncThumbs() {
    moveThumb(agentThumb, document.querySelector('.agent-seg-btn.active'));
    moveThumb(tabThumb, document.querySelector('.tab.active'));
  }
  new MutationObserver(() => {
    syncThumbs();
    const active = document.querySelector('.agent-seg-btn.active');
    if (active) document.body.dataset.agent = active.dataset.agent;
  }).observe(document.getElementById('agentSegGroup'), {attributes: true, subtree: true, childList: true, characterData: true, attributeFilter: ['class']});
  new ResizeObserver(syncThumbs).observe(document.getElementById('agentSegGroup'));
  document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => selectInspectorTab(tab)));
  function selectInspectorTab(tab) {
    document.querySelectorAll('.tab').forEach(item => {
      const on = item === tab;
      item.classList.toggle('active', on);
      item.setAttribute('aria-selected', String(on));
      document.getElementById(item.dataset.tab).hidden = !on;
    });
    syncThumbs();
    if (tab.dataset.tab === 'tabLog') logBox.scrollTop = logBox.scrollHeight;
  }
  function openInspector(tabName) {
    if (!document.body.classList.contains('show-panels')) btnPanels.click();
    if (tabName) selectInspectorTab(document.querySelector(`.tab[data-tab="${tabName}"]`));
    requestAnimationFrame(syncThumbs);
  }
  btnPanels.addEventListener('click', () => requestAnimationFrame(syncThumbs));
  document.getElementById('btnInspectorClose').addEventListener('click', () => { if (document.body.classList.contains('show-panels')) btnPanels.click(); });

  function toggleSidebar() {
    if (window.matchMedia('(max-width: 820px)').matches) document.body.classList.toggle('sidebar-open');
    else document.body.classList.toggle('sidebar-collapsed');
  }
  document.getElementById('btnSidebar').addEventListener('click', toggleSidebar);
  document.getElementById('btnWinMinimize').addEventListener('click', () => window.pywebview.api.minimize());
  let windowMaximized = false;
  const btnWinMaximize = document.getElementById('btnWinMaximize');
  function syncWindowMaximizedUi(maximized) {
    windowMaximized = !!maximized;
    document.body.classList.toggle('maximized', windowMaximized);
    if (!btnWinMaximize) return;
    btnWinMaximize.setAttribute('aria-pressed', String(windowMaximized));
    const label = windowMaximized ? 'Önceki boyuta döndür' : 'Büyüt';
    btnWinMaximize.title = label;
    btnWinMaximize.setAttribute('aria-label', label);
    const useEl = btnWinMaximize.querySelector('use');
    if (useEl) useEl.setAttribute('href', windowMaximized ? '#i-restore' : '#i-maximize');
  }
  async function syncWindowDimensions() {
    if (typeof window !== 'undefined' && window.pywebview?.api?.window_state) {
      try {
        const state = await window.pywebview.api.window_state();
        if (state && typeof state.maximized === 'boolean') {
          syncWindowMaximizedUi(state.maximized);
          return state.maximized;
        }
      } catch (_) {}
    }
    const availW = Number(typeof window !== 'undefined' && window.screen?.availWidth) || 0;
    const availH = Number(typeof window !== 'undefined' && window.screen?.availHeight) || 0;
    const curW = Number(typeof window !== 'undefined' && (window.outerWidth || window.innerWidth)) || 0;
    const curH = Number(typeof window !== 'undefined' && (window.outerHeight || window.innerHeight)) || 0;
    if (availW > 0 && availH > 0 && curW > 0 && curH > 0) {
      const fitsWorkArea = Math.abs(curW - availW) <= 2 && Math.abs(curH - availH) <= 2;
      if (fitsWorkArea !== windowMaximized) syncWindowMaximizedUi(fitsWorkArea);
    }
    return windowMaximized;
  }
  if (btnWinMaximize) {
    btnWinMaximize.addEventListener('click', async () => {
      try {
        const result = await window.pywebview.api.toggle_maximize();
        syncWindowMaximizedUi(result?.maximized);
        if (result && typeof result.compact === 'boolean') {
          compactMode = result.compact;
          document.body.classList.toggle('compact', compactMode);
          const minBtn = document.getElementById('btnMin');
          if (minBtn) minBtn.title = compactMode ? 'Tam arayüze dön' : 'Kompakt sohbete geç';
        }
      } catch (e) {
        logLine('Pencere boyutu değiştirilemedi: ' + String(e));
      }
    });
  }
  window.addEventListener('resize', () => { syncWindowDimensions(); });
  document.getElementById('btnAddProject').title = 'Windows klasör seçicisiyle proje ekle';
  document.getElementById('btnDeleteProjectChats').addEventListener('click', () =>
    requestChatDeletion(navigationConversations.filter(c=>(c.project_id||'squad-pilot')===mainProjectSelect.value), mainProjectSelect.value));

  const dayGreeting = () => {
    const hour = new Date().getHours();
    return hour < 6 ? 'İyi geceler.' : hour < 12 ? 'Günaydın.' : hour < 18 ? 'İyi günler.' : 'İyi akşamlar.';
  };
  document.getElementById('emptyGreeting').textContent = dayGreeting();
  document.querySelectorAll('.prompt-chip').forEach(chip => chip.addEventListener('click', () => {
    inputEl.value = chip.dataset.prompt;
    inputEl.focus();
    inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
  }));

  // Copy for code blocks. Added after render so message text stays text-only.
  function copyText(text) {
    const area = document.createElement('textarea');
    area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
    document.body.append(area); area.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (_) {}
    area.remove();
    return ok;
  }
  function decorateCodeBlocks() {
    chatEl.querySelectorAll('.msg-code:not([data-copy])').forEach(block => {
      block.dataset.copy = '1';
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'code-copy'; button.textContent = 'Kopyala';
      button.onclick = () => {
        button.textContent = copyText(block.querySelector('pre')?.textContent || '') ? 'Kopyalandı' : 'Kopyalanamadı';
        setTimeout(() => { button.textContent = 'Kopyala'; }, 1400);
      };
      block.append(button);
    });
  }
  new MutationObserver(decorateCodeBlocks).observe(chatEl, {childList: true, subtree: true});

  // Command palette. Commands press the same buttons a pointer would.
  const paletteLayer = document.getElementById('paletteLayer');
  const paletteInput = document.getElementById('paletteInput');
  const paletteList = document.getElementById('paletteList');
  let paletteItems = [];
  let paletteCursor = 0;
  let paletteReturnFocus = null;
  const pressIfUsable = id => { const el = document.getElementById(id); if (el && !el.disabled) el.click(); };
  const pressAgent = agent => { const el = document.querySelector(`.agent-seg-btn[data-agent="${agent}"]`); if (el && !el.disabled) el.click(); };
  function paletteCommands() {
    const commands = [
      ['Sohbet', 'Yeni sohbet', () => pressIfUsable('btnNewChat')],
      ['Sohbet', 'Mesaj kutusuna odaklan', () => inputEl.focus()],
      ['Ajan', 'Antigravity ile çalış', () => pressAgent('antigravity')],
      ['Ajan', 'Codex ile çalış', () => pressAgent('codex')],
      ['Ajan', 'Birlikte çalış', () => pressAgent('collaboration')],
      ['Ajan', 'Hesaplar ve CLI bağlantıları', () => pressIfUsable('btnCliConnections')],
      ['Araç', 'Öz teşhis başlat', () => pressIfUsable('btnSelfDiagnostics')],
      ['Araç', 'Ekran görüntüsü al', () => document.querySelector('.qa-btn[data-action="screenshot"]')?.click()],
      ['Araç', 'Sistem bilgisi', () => document.querySelector('.qa-btn[data-action="sysinfo"]')?.click()],
      ['Araç', 'Proje ekle', () => pressIfUsable('btnAddProject')],
      ['Görünüm', 'Durum panelini aç', () => openInspector('tabStatus')],
      ['Görünüm', 'Araçlar panelini aç', () => openInspector('tabTools')],
      ['Görünüm', 'Günlüğü aç', () => openInspector('tabLog')],
      ['Görünüm', 'Kenar çubuğunu aç/kapat', toggleSidebar],
      ['Görünüm', 'Kompakt pencere', () => pressIfUsable('btnMin')],
      ['Görünüm', 'Pencereyi büyüt / geri al', () => pressIfUsable('btnWinMaximize')],
      ['Görünüm', 'Koyu tema', () => applyUiPreference('theme', 'dark')],
      ['Görünüm', 'Açık tema', () => applyUiPreference('theme', 'light')],
      ['Görünüm', 'Sistem teması', () => applyUiPreference('theme', 'system')],
      ['Görünüm', 'Kristal: pembe kuvars', () => applyUiPreference('crystal', 'rose')],
      ['Görünüm', 'Kristal: sitrin', () => applyUiPreference('crystal', 'citrine')],
      ['Görünüm', 'Kristal: ametist', () => applyUiPreference('crystal', 'amethyst')],
      ['Görünüm', 'Kristal: kaya kristali', () => applyUiPreference('crystal', 'smoky')],
    ];
    if (desktopView.stop_ref) commands.unshift(['Görev', 'Masaüstü görevini durdur', () => pressIfUsable('btnDesktopTaskStop')]);
    if (thinking) commands.unshift(['Görev', 'Etkin görevi durdur', () => pressIfUsable('btnCancel')]);
    for (const conv of navigationConversations) {
      if (conv.id === currentConvId) continue;
      commands.push(['Sohbetler', conv.title || 'Yeni sohbet', async () => {
        if (thinking || deletionPending) return;
        const result = await window.pywebview.api.chat_select(conv.id);
        if (result.status === 'ok') await loadActiveConversation();
      }]);
    }
    return commands;
  }
  const paletteFold = value => String(value).toLocaleLowerCase('tr-TR');
  function renderPalette() {
    const query = paletteFold(paletteInput.value.trim());
    paletteItems = paletteCommands().filter(([group, label]) => !query || query.split(/\s+/).every(part => paletteFold(group + ' ' + label).includes(part)));
    paletteCursor = Math.min(paletteCursor, Math.max(0, paletteItems.length - 1));
    paletteList.replaceChildren();
    if (!paletteItems.length) {
      const empty = document.createElement('div'); empty.className = 'palette-empty'; empty.textContent = 'Sonuç yok';
      paletteList.append(empty);
      paletteInput.removeAttribute('aria-activedescendant');
      return;
    }
    let lastGroup = '';
    paletteItems.forEach(([group, label], index) => {
      if (group !== lastGroup) {
        const heading = document.createElement('div'); heading.className = 'palette-group'; heading.textContent = group;
        heading.setAttribute('role', 'presentation');
        paletteList.append(heading); lastGroup = group;
      }
      const row = document.createElement('div');
      row.className = 'palette-item'; row.id = `paletteItem${index}`; row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', String(index === paletteCursor));
      const text = document.createElement('span'); text.textContent = label; row.append(text);
      row.addEventListener('mousemove', () => { if (paletteCursor !== index) { paletteCursor = index; markPaletteCursor(); } });
      row.addEventListener('click', () => runPaletteItem(index));
      paletteList.append(row);
    });
    markPaletteCursor();
  }
  function markPaletteCursor() {
    paletteList.querySelectorAll('.palette-item').forEach((row, index) => {
      const on = index === paletteCursor;
      row.setAttribute('aria-selected', String(on));
      if (on) { paletteInput.setAttribute('aria-activedescendant', row.id); row.scrollIntoView({block: 'nearest'}); }
    });
  }
  function openPalette() {
    if (!paletteLayer.hidden) return;
    paletteReturnFocus = document.activeElement;
    paletteInput.value = ''; paletteCursor = 0;
    paletteLayer.hidden = false;
    renderPalette();
    paletteInput.focus();
  }
  function closePalette(restore=true) {
    if (paletteLayer.hidden) return;
    paletteLayer.hidden = true;
    if (restore && paletteReturnFocus?.isConnected) paletteReturnFocus.focus();
  }
  function runPaletteItem(index) {
    const item = paletteItems[index];
    if (!item) return;
    closePalette();
    item[2]();
  }
  paletteInput.addEventListener('input', () => { paletteCursor = 0; renderPalette(); });
  paletteInput.addEventListener('keydown', event => {
    if (event.isComposing) return;
    if (event.key === 'ArrowDown') { event.preventDefault(); paletteCursor = (paletteCursor + 1) % Math.max(1, paletteItems.length); markPaletteCursor(); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); paletteCursor = (paletteCursor - 1 + paletteItems.length) % Math.max(1, paletteItems.length); markPaletteCursor(); }
    else if (event.key === 'Enter') { event.preventDefault(); if (!event.repeat) runPaletteItem(paletteCursor); }
  });
  document.getElementById('paletteScrim').addEventListener('click', () => closePalette());
  document.getElementById('btnCommand').addEventListener('click', openPalette);

  function isElementVisibleForFocus(el) {
    if (!el || el.disabled || el.hidden) return false;
    if (typeof el.closest === 'function' && el.closest('[hidden]')) return false;
    if (typeof el.getClientRects === 'function') return el.getClientRects().length > 0;
    return true;
  }
  function modalFocusableElements(container) {
    if (!container || typeof container.querySelectorAll !== 'function') return [];
    const selector = 'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    return Array.from(container.querySelectorAll(selector)).filter(isElementVisibleForFocus);
  }
  function blockingOverlay() {
    const confirmModalEl = document.getElementById('confirmModal');
    if (confirmModalEl && !confirmModalEl.hidden && isElementVisibleForFocus(confirmModalEl)) return confirmModalEl;
    return Array.from(document.querySelectorAll('.api-setup.show, .agent-overlay.show')).find(isElementVisibleForFocus) || null;
  }
  function activeModalContainer() {
    const confirmModalEl = document.getElementById('confirmModal');
    if (confirmModalEl && !confirmModalEl.hidden && isElementVisibleForFocus(confirmModalEl)) return confirmModalEl;
    if (paletteLayer && !paletteLayer.hidden && isElementVisibleForFocus(paletteLayer)) return paletteLayer;
    const overlay = blockingOverlay();
    if (overlay) return overlay;
    return null;
  }
  function trapModalTabFocus(event) {
    if (event.key !== 'Tab') return false;
    const modal = activeModalContainer();
    if (!modal) return false;
    const focusables = modalFocusableElements(modal);
    if (!focusables.length) {
      event.preventDefault();
      return true;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement;
    const inside = typeof modal.contains === 'function' ? modal.contains(active) : focusables.includes(active);
    if (event.shiftKey) {
      if (!inside || active === first) {
        event.preventDefault();
        last.focus();
        return true;
      }
    } else {
      if (!inside || active === last) {
        event.preventDefault();
        first.focus();
        return true;
      }
    }
    return false;
  }
  document.addEventListener('keydown', event => {
    if (event.isComposing) return;
    if (event.key === 'Tab' && trapModalTabFocus(event)) return;
    if (event.key === 'Escape') {
      const confirmModalEl = document.getElementById('confirmModal');
      if (confirmModalEl && !confirmModalEl.hidden) { event.preventDefault(); resolveActiveConfirm(false); return; }
      if (!paletteLayer.hidden) { event.preventDefault(); closePalette(); return; }
      const overlay = blockingOverlay();
      if (overlay?.id === 'agentOverlay') document.getElementById('btnAgentClose').click();
      else if (overlay?.id === 'cliSetup') document.getElementById('cliLater').click();
      else document.body.classList.remove('sidebar-open');
      return;
    }
    if (!event.ctrlKey || event.altKey || event.shiftKey || event.metaKey || blockingOverlay()) return;
    const key = String(event.key).toLowerCase();
    if (key === 'k') { event.preventDefault(); if (paletteLayer.hidden) openPalette(); else closePalette(); }
    else if (key === 'b') { event.preventDefault(); toggleSidebar(); }
    else if (key === 'i') { event.preventDefault(); btnPanels.click(); }
  });

  const signatureTimer = setTimeout(() => signatureIntro.remove(), 1000);
  signatureIntro.addEventListener('animationend', event => {
    if (event.target === signatureIntro) { clearTimeout(signatureTimer); signatureIntro.remove(); }
  });
  renderAgentConnections();
  syncThumbs();
  requestAnimationFrame(syncThumbs);
  window.addEventListener('pywebviewready', async () => {
    try {
      const prefs = await window.pywebview.api.ui_preferences();
      if (prefs.status === 'ok') {
        applyUiPreference('theme', prefs.data.theme, false);
        applyUiPreference('crystal', prefs.data.crystal, false);
      }
    } catch (_) {}
  });
"""
