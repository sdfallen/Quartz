"""App preview JavaScript fragment; composed in the shared application scope.

The pane frames a web app running on this computer. Python decides which
addresses are allowed (``core/preview_url.py``); this script only asks, shows
and refuses the Quartz page's own origin. Reply text is never parsed as HTML.
"""

JAVASCRIPT = r"""
  // ── App preview (loopback web apps) ─────────────────────
  const previewPane = document.getElementById('previewPane');
  const previewFrame = document.getElementById('previewFrame');
  const previewAddress = document.getElementById('previewAddress');
  const previewNote = document.getElementById('previewNote');
  const btnPreview = document.getElementById('btnPreview');
  const PREVIEW_LINK_RE = /\bhttps?:\/\/(?:localhost|127\.0\.0\.1|\[::1\]|[a-z0-9-]+\.localhost)(?::\d{1,5})?(?:\/[^\s<>"'`)\]\\]*)?/gi;
  // A backslash ends the address: technical details carry escaped "\r\n" text
  // (live 13 Nov: "localhost:18431/login\r\nalembic.ini..." became one link).
  const PREVIEW_HINT = 'Sayfa boş kalırsa uygulama çerçeve içinde gösterilmeyi engelliyor olabilir; ayrı pencerede açın.';
  let previewUrl = '';

  function setPreviewNote(text, tone) {
    previewNote.textContent = text || '';
    if (tone) previewNote.dataset.tone = tone; else delete previewNote.dataset.tone;
  }

  function showPreviewPane(shown) {
    document.body.classList.toggle('show-preview', shown);
    btnPreview?.classList.toggle('active', shown);
    btnPreview?.setAttribute('aria-expanded', shown ? 'true' : 'false');
  }

  async function checkPreviewUrl(raw) {
    const result = await window.pywebview.api.preview_check_url(String(raw ?? ''));
    if (result.status !== 'ok') throw new Error(String(result.data || 'Adres açılamadı'));
    // The previewed page must never share the Quartz page's origin.
    if (location.origin && location.origin !== 'null' && new URL(result.data).origin === location.origin) {
      throw new Error('Quartz arayüzünün kendi adresi önizlenemez');
    }
    return result.data;
  }

  async function openPreview(raw) {
    showPreviewPane(true);
    try {
      const url = await checkPreviewUrl(raw);
      previewUrl = url;
      previewAddress.value = url;
      setPreviewNote('Uygulama yoklanıyor…');
      const probe = await window.pywebview.api.preview_frame_policy(url);
      const policy = probe.status === 'ok' ? probe.data : 'allowed';
      if (policy === 'unreachable') {
        previewFrame.removeAttribute('src'); previewFrame.hidden = true;
        setPreviewNote('Bu adreste yanıt veren bir uygulama yok. Sunucunun çalıştığından ve portun doğru olduğundan emin olun.', 'error');
        return;
      }
      if (policy === 'blocked') {
        previewFrame.removeAttribute('src'); previewFrame.hidden = true;
        setPreviewNote('Bu uygulama güvenlik ayarı gereği başka bir sayfanın içinde gösterilmiyor; ayrı önizleme penceresinde açıldı.');
        await openPreviewWindow(url);
        return;
      }
      previewFrame.hidden = false;
      previewFrame.src = url;
      setPreviewNote(PREVIEW_HINT);
    } catch (err) {
      setPreviewNote(err.message, 'error');
    }
  }

  async function openPreviewWindow(raw) {
    const target = raw || previewAddress.value || previewUrl;
    if (!target) { setPreviewNote('Önce bir adres yazın.', 'error'); return; }
    const result = await window.pywebview.api.preview_open_window(String(target));
    if (result.status !== 'ok') setPreviewNote(String(result.data || 'Pencere açılamadı'), 'error');
  }

  function closePreview() {
    showPreviewPane(false);
    previewFrame.removeAttribute('src');
    previewFrame.hidden = true;
  }

  btnPreview?.addEventListener('click', () => {
    if (document.body.classList.contains('show-preview')) { showPreviewPane(false); return; }
    showPreviewPane(true);
    if (!previewUrl) previewAddress.focus();
  });
  document.getElementById('previewBar').addEventListener('submit', (event) => { event.preventDefault(); openPreview(previewAddress.value); });
  document.getElementById('btnPreviewReload').addEventListener('click', () => { if (previewUrl) openPreview(previewUrl); });
  document.getElementById('btnPreviewWindow').addEventListener('click', () => openPreviewWindow());
  document.getElementById('btnPreviewClose').addEventListener('click', closePreview);
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && !event.altKey && String(event.key).toLowerCase() === 'p') {
      event.preventDefault(); btnPreview?.click();
    }
  });

  function localPreviewLinks(text) {
    const found = [];
    for (const match of String(text ?? '').matchAll(PREVIEW_LINK_RE)) {
      const url = match[0].replace(/[.,;:!?]+$/, '');
      if (!found.includes(url)) found.push(url);
      if (found.length >= 3) break;
    }
    return found;
  }

  // Adds "Önizle" buttons under an agent reply for each loopback address in it.
  function decoratePreviewLinks(bubble, text) {
    bubble.querySelector(':scope > .preview-links')?.remove();
    const links = localPreviewLinks(text);
    if (!links.length) return;
    const row = document.createElement('div'); row.className = 'preview-links';
    for (const url of links) {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'control-btn preview-link-btn';
      button.textContent = 'Önizle · ' + url.replace(/^https?:\/\//i, '');
      button.title = url;
      button.addEventListener('click', () => openPreview(url));
      row.append(button);
    }
    bubble.append(row);
  }
  // Work panel tabs: preview, host-observed file changes and host checks for this conversation.
  // Only host evidence (metadata.host_evidence) is listed; agent text never adds a row.
  const workEvidence = new Map();
  const WORK_AGENT = {codex: 'Pusula', claude: 'Usta', antigravity: 'Gözcü', gemini: 'Gözcü'};
  function setWorkTab(tab) {
    previewPane.dataset.workTab = tab;
    previewPane.querySelectorAll('.work-tab').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === tab ? 'true' : 'false'));
  }
  function workCheckLabel(ev, meta) {
    const status = ev?.source_validation?.status;
    if (meta?.outcome?.goal_verdict === 'VERIFIED') return ['ok', 'Hedef doğrulandı'];
    if (status === 'FAILED') return ['fail', 'Kontrol başarısız'];
    if (status === 'VERIFIED') return ['warn', 'Sözdizimi doğrulandı; test kanıtı yok'];
    return ['warn', 'Bağımsız kanıt yok'];
  }
  function renderWorkEvidence() {
    const changes = new Map();
    const checks = [];
    for (const item of workEvidence.values()) {
      for (const file of item.files) changes.set(file, item);
      if (item.check) checks.push(item);
    }
    const fill = (id, rows, build) => {
      const list = document.getElementById(id);
      if (!list) return;
      list.replaceChildren(...rows.map(build));
      list.closest('.work-list')?.classList.toggle('has-items', rows.length > 0);
    };
    fill('workChangesList', [...changes.entries()], ([file, item]) => {
      const li = document.createElement('li');
      const code = document.createElement('code'); code.textContent = file;
      const who = document.createElement('span'); who.className = 'work-who'; who.textContent = `${item.agent} · #${item.seq || '?'}`;
      li.append(code, who); return li;
    });
    fill('workChecksList', checks, (item) => {
      const li = document.createElement('li'); li.dataset.tone = item.check[0];
      const label = document.createElement('span'); label.className = 'work-check'; label.textContent = item.check[1];
      const who = document.createElement('span'); who.className = 'work-who'; who.textContent = `${item.agent} · #${item.seq || '?'} · ${item.files.length} dosya`;
      li.append(label, who); return li;
    });
    const setCount = (id, n) => { const el = document.getElementById(id); if (el) el.textContent = n ? String(n) : ''; };
    setCount('workChangesCount', changes.size);
    setCount('workChecksCount', checks.length);
  }
  function setWorkEvidence(messages, replaceAll) {
    if (replaceAll) workEvidence.clear();
    for (const m of messages || []) {
      const meta = (m && m.metadata) || {};
      const ev = meta.host_evidence;
      if (!m || !m.id || !ev || typeof ev !== 'object') continue;
      const files = Array.isArray(ev.files_changed) ? ev.files_changed.map(String) : [];
      const hasCheck = !!(ev.source_validation || meta.outcome?.goal_verdict);
      workEvidence.set(m.id, {files, seq: m.sequence || meta.sequence, agent: WORK_AGENT[String(m.sender || '').toLowerCase()] || 'Quartz',
                              check: hasCheck ? workCheckLabel(ev, meta) : null});
    }
    renderWorkEvidence();
  }
  previewPane?.querySelectorAll('.work-tab').forEach(b => b.addEventListener('click', () => setWorkTab(b.dataset.tab)));

  // Agent limits: a small read-only indicator (core.agent_limits); refreshed every minute.
  const LIMIT_CHIPS = {codex: 'limitCodex', claude: 'limitClaude', antigravity: 'limitAgy'};
  function renderAgentLimits(data) {
    for (const [agent, id] of Object.entries(LIMIT_CHIPS)) {
      const chip = document.getElementById(id);
      if (!chip) continue;
      const entry = (data || {})[agent] || {};
      const values = [entry.five_hour, entry.week].filter(v => typeof v === 'number');
      const worst = values.length ? Math.max(...values) : null;
      chip.dataset.state = entry.state || 'unknown';
      chip.querySelector('.limit-value').textContent = worst === null ? '—' : `%${Math.round(worst)}`;
      chip.querySelector('.limit-meter b').style.width = worst === null ? '0' : `${Math.min(100, worst)}%`;
      const name = chip.querySelector('.limit-name').textContent;
      const reset = entry.resets_at ? new Date(entry.resets_at * 1000).toLocaleTimeString('tr-TR', {hour: '2-digit', minute: '2-digit'}) : '';
      chip.title = worst === null
        ? `${name}: ${entry.source === 'unavailable' ? 'bu CLI limit bilgisi vermiyor' : 'henüz ölçülmedi'}`
        : `${name}: 5 saatlik %${Math.round(entry.five_hour ?? 0)} · haftalık %${Math.round(entry.week ?? 0)}${reset ? ` · sıfırlanma ${reset}` : ''}`;
      chip.setAttribute('aria-label', chip.title);
    }
  }
  async function refreshAgentLimits() {
    try {
      const result = await window.pywebview.api.agent_limits();
      if (result && result.status === 'ok') renderAgentLimits(result.data);
    } catch (_) {}
  }
  if (typeof window !== 'undefined' && window.addEventListener) {
    window.addEventListener('pywebviewready', () => { refreshAgentLimits(); setInterval(refreshAgentLimits, 60000); });
  }
  window.QuartzPreview = Object.freeze({ open: openPreview, openWindow: openPreviewWindow, decorate: decoratePreviewLinks, links: localPreviewLinks });
"""
