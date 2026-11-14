"""App preview JavaScript fragment; composed in the shared application scope.

The pane frames a web app running on this computer. Python decides which
addresses are allowed (``core/preview_url.py``); this script only asks, shows
and refuses the SpeS page's own origin. Reply text is never parsed as HTML.
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
    // The previewed page must never share the SpeS page's origin.
    if (location.origin && location.origin !== 'null' && new URL(result.data).origin === location.origin) {
      throw new Error('SpeS arayüzünün kendi adresi önizlenemez');
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
  const WORK_AGENT = {codex: 'Fides', claude: 'Fatum', antigravity: 'Eos', gemini: 'Eos'};
  function setWorkTab(tab) {
    previewPane.dataset.workTab = tab;
    previewPane.querySelectorAll('.work-tab').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === tab ? 'true' : 'false'));
  }
  function workCheckLabel(ev, meta) {
    const status = ev?.source_validation?.status;
    const tests = ev?.agent_tests?.status;  // core.test_evidence.evidence_label is the Python twin
    if (meta?.outcome?.goal_verdict === 'VERIFIED') return ['ok', 'Hedef doğrulandı'];
    if (status === 'FAILED') return ['fail', 'Kontrol başarısız'];
    if (tests === 'FAILED') return ['fail', 'Test başarısız'];
    if (tests === 'PASSED') return ['ok', 'Testler geçti (ajan çalıştırdı)'];
    if (tests === 'RAN') return ['warn', 'Test çalıştı; sonucu ayırt edilemedi'];
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
  let workEvidenceSeeded = false;
  function setWorkEvidence(messages, replaceAll) {
    if (replaceAll) { workEvidence.clear(); workEvidenceSeeded = false; }
    const before = new Set(workEvidence.keys());
    for (const m of messages || []) {
      const meta = (m && m.metadata) || {};
      const ev = meta.host_evidence;
      if (!m || !m.id || !ev || typeof ev !== 'object') continue;
      const files = Array.isArray(ev.files_changed) ? ev.files_changed.map(String) : [];
      const hasCheck = !!(ev.source_validation || meta.outcome?.goal_verdict);
      workEvidence.set(m.id, {files, seq: m.sequence || meta.sequence, agent: WORK_AGENT[String(m.sender || '').toLowerCase()] || 'SpeS',
                              check: hasCheck ? workCheckLabel(ev, meta) : null});
    }
    renderWorkEvidence();
    // A build that finished while SpeS is open shows its result in the panel by itself.
    const fresh = [...workEvidence.entries()].some(([id, item]) => !before.has(id) && item.files.length);
    if (workEvidenceSeeded && fresh && typeof showWorkResult === 'function') showWorkResult();
    else if (typeof refreshPanelFiles === 'function' && !workEvidenceSeeded) refreshPanelFiles();
    workEvidenceSeeded = true;
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

  // ── Work panel as a general side view (14 Nov): live page, files, attachments ──
  const workFilesList = document.getElementById('workFilesList');
  const workViewer = document.getElementById('workViewer');
  let panelFiles = {project: [], attachments: []};
  function viewerMessage(text) {
    const p = document.createElement('p'); p.className = 'work-empty-view'; p.textContent = text;
    workViewer.replaceChildren(p);
  }
  function showFileView(data, label) {
    const head = document.createElement('div'); head.className = 'viewer-head';
    head.textContent = label + (data.truncated ? ' (ilk 400 KB)' : '');
    if (data.kind === 'image') {
      const img = document.createElement('img'); img.className = 'viewer-image'; img.alt = data.name;
      img.src = `data:${data.mime};base64,${data.data}`;
      workViewer.replaceChildren(head, img);
    } else if (data.kind === 'text' && data.language === 'md') {
      const body = document.createElement('div'); body.className = 'viewer-markdown';
      appendMessageText(body, data.text);
      workViewer.replaceChildren(head, body);
    } else if (data.kind === 'text') {
      const pre = document.createElement('pre'); pre.className = 'viewer-code'; pre.dataset.language = data.language || '';
      const lines = String(data.text).split('\n');
      pre.textContent = lines.map((line, i) => String(i + 1).padStart(4, ' ') + '  ' + line).join('\n');
      workViewer.replaceChildren(head, pre);
    } else {
      viewerMessage(`${data.name}: bu dosya türü panelde gösterilemiyor (${Math.round((data.size || 0) / 1024)} KB).`);
    }
  }
  async function openPanelFile(scope, path, batch, label) {
    showPreviewPane(true); setWorkTab('files');
    if (scope === 'project' && /\.html?$/i.test(path)) {   // pages are shown live
      const result = await window.pywebview.api.panel_result(currentConvId || '');
      if (result.status === 'ok' && result.data.open && result.data.open.kind === 'web') {
        const base = result.data.open.url.slice(0, result.data.open.url.length - encodeURI(result.data.open.file).length);
        setWorkTab('preview'); openPreview(base + encodeURI(path)); return;
      }
    }
    if (String(path).endsWith('/')) { viewerMessage(`${label}: zip içeriği ajanlara açıldı; tek tek dosya seçimi henüz yok.`); return; }
    const result = await window.pywebview.api.panel_read(currentConvId || '', scope, path, batch || '');
    if (result.status !== 'ok') { viewerMessage(String(result.data || 'Dosya açılamadı')); return; }
    showFileView(result.data, label);
  }
  function renderPanelFiles() {
    if (!workFilesList) return;
    const rows = [];
    const group = (title) => { const h = document.createElement('div'); h.className = 'work-files-title'; h.textContent = title; return h; };
    if (panelFiles.project.length) rows.push(group(`Ekibin yazdıkları${panelFiles.project_name ? ' · ' + panelFiles.project_name : ''}`));
    for (const path of panelFiles.project) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'work-file'; b.textContent = path;
      b.onclick = () => openPanelFile('project', path, '', path); rows.push(b);
    }
    if (panelFiles.attachments.length) rows.push(group('Gönderdiğin ekler'));
    for (const item of panelFiles.attachments) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'work-file'; b.dataset.kind = item.kind || 'file';
      b.textContent = item.name || item.path;
      b.onclick = () => openPanelFile('attachment', item.path, item.batch, item.name || item.path); rows.push(b);
    }
    if (!rows.length) { const p = document.createElement('p'); p.className = 'work-empty-view'; p.textContent = 'Bu sohbette henüz sonuç dosyası ya da ek yok.'; rows.push(p); }
    workFilesList.replaceChildren(...rows);
    const count = document.getElementById('workFilesCount');
    if (count) count.textContent = (panelFiles.project.length + panelFiles.attachments.length) || '';
  }
  let panelConvId = null;
  async function refreshPanelFiles() {
    if (panelConvId !== currentConvId) {
      // Another conversation: its files only; the old viewer content goes (live 14 Nov).
      panelConvId = currentConvId;
      viewerMessage('Ekibin yazdığı bir dosyayı ya da gönderdiğin bir eki seç.');
    }
    try {
      const result = await window.pywebview.api.panel_result(currentConvId || '');
      if (result.status === 'ok') { panelFiles = result.data; renderPanelFiles(); return result.data; }
    } catch (_) {}
    return null;
  }
  // After a build: open the result by itself (a page live, otherwise the best file).
  async function showWorkResult() {
    const data = await refreshPanelFiles();
    if (!data || !data.open) return false;
    showPreviewPane(true);
    if (data.open.kind === 'web') { setWorkTab('preview'); openPreview(data.open.url); }
    else openPanelFile(data.open.scope, data.open.path, '', data.open.path);
    return true;
  }
  window.spesShowResult = showWorkResult;
  window.spesOpenAttachment = (batch, item) => openPanelFile('attachment', item.path, batch, item.name || item.path);
  previewPane?.querySelectorAll('.device-btn').forEach(button => button.addEventListener('click', () => {
    previewPane.dataset.device = button.dataset.device;
    previewPane.querySelectorAll('.device-btn').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
  }));
  window.QuartzPreview = Object.freeze({ open: openPreview, openWindow: openPreviewWindow, decorate: decoratePreviewLinks, links: localPreviewLinks });
"""
