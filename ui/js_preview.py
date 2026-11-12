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
  window.QuartzPreview = Object.freeze({ open: openPreview, openWindow: openPreviewWindow, decorate: decoratePreviewLinks, links: localPreviewLinks });
"""
