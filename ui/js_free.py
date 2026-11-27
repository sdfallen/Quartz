"""Ücretsiz sohbet in the page (27 Nov 2026): the Ücretsiz bağlantılar sheet and the free door.

A key is read from its field once, sent to the backend (which checks it with one model-list
request and stores it with Windows DPAPI) and the field is cleared at once; the page never shows,
keeps or logs a key. Status only says whether a key exists.
"""

JAVASCRIPT = r"""
  // ── Ücretsiz sohbet (27 Nov) ───────────────────────────────────────────────────
  const freeSheet = document.getElementById('freeSheet');
  const freeChannelsEl = document.getElementById('freeChannels');
  let freeStatus = null;
  let freeSheetOpener = null;
  const FREE_CONSENTS = [['send', 'Sohbetlerimi bu kanala gönder (bu sohbetteki her mesaj)'],
                         ['backup', 'Başka bir kanalın kotası dolarsa bunu yedek olarak da kullan']];

  async function freeCall(action, data) {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.free_chat)
      return {status: 'error', message: 'SpeS henüz hazır değil.'};
    try { return await window.pywebview.api.free_chat(action, data || {}); }
    catch (e) { return {status: 'error', message: String(e)}; }
  }

  function freeEl(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function renderFreeChannels(status) {
    freeStatus = status;
    if (!freeChannelsEl) return;
    freeChannelsEl.replaceChildren();
    for (const ch of (status && status.channels) || []) {
      const card = freeEl('section', 'free-channel');
      card.dataset.connected = ch.connected ? 'true' : 'false';
      const head = freeEl('div', 'free-channel-head');
      head.append(freeEl('b', '', ch.label), freeEl('span', 'free-persona', `Sohbette adı: ${ch.persona}`),
                  freeEl('span', 'free-state', ch.connected ? 'Bağlı' : 'Bağlı değil'));
      card.append(head);
      const error = freeEl('p', 'free-error');
      error.id = `freeErr-${ch.id}`;
      error.setAttribute('role', 'alert');
      if (!ch.connected && ch.kind === 'account') {
        // 27 Nov: the ChatGPT account has no key. Codex is installed and signed in only by the
        // user's own clicks (the existing setup and sign-in); SpeS then checks the sign-in method.
        const row = freeEl('div', 'free-key-row');
        const stateText = !ch.installed ? 'Bu kanal için Codex gerekiyor (birkaç yüz MB indirir).'
          : (ch.checked && !ch.signed_in ? 'Codex\'te ChatGPT ile giriş görünmüyor.' : 'Codex kurulu. ChatGPT ile giriş yaptıysan kontrol et.');
        row.append(freeEl('span', 'free-persona', stateText));
        const before = freeEl('div', 'free-consents');
        const pre = {};
        for (const [field, text] of FREE_CONSENTS) {
          const label = freeEl('label');
          const box = freeEl('input');
          box.type = 'checkbox'; box.checked = false;
          pre[field] = box;
          label.append(box, document.createTextNode(text));
          before.append(label);
        }
        const begin = async (operation, button, busy) => {
          const old = button.textContent; button.disabled = true; button.textContent = busy; error.textContent = '';
          try {
            const r = await window.pywebview.api.onboarding_begin(operation, 'codex', '');
            if (r && r.status && r.status !== 'ok') error.textContent = r.message || r.data || 'Başlatılamadı.';
            else error.textContent = operation === 'install' ? 'Codex kuruluyor; bitince "Kontrol et ve bağla"ya bas.'
              : 'Açılan pencerede ChatGPT hesabınla giriş yap, sonra "Kontrol et ve bağla"ya bas.';
          } catch (e) { error.textContent = String(e); }
          button.disabled = false; button.textContent = old;
        };
        if (!ch.installed) {
          const install = freeEl('button', 'free-btn', 'Codex\'i kur');
          install.type = 'button';
          install.addEventListener('click', () => begin('install', install, 'Kuruluyor…'));
          row.append(install);
        } else {
          const login = freeEl('button', 'free-btn ghost', 'ChatGPT ile giriş');
          login.type = 'button';
          login.addEventListener('click', () => begin('account', login, 'Açılıyor…'));
          row.append(login);
        }
        const connect = freeEl('button', 'free-btn', 'Kontrol et ve bağla');
        connect.type = 'button';
        connect.addEventListener('click', async () => {
          connect.disabled = true; connect.textContent = 'Kontrol ediliyor…'; error.textContent = '';
          const result = await freeCall('connect', {channel: ch.id, key: '', send: pre.send.checked, backup: pre.backup.checked});
          connect.disabled = false; connect.textContent = 'Kontrol et ve bağla';
          if (result.status !== 'ok') { error.textContent = result.message || result.data || 'Bağlanamadı.'; return; }
          renderFreeChannels(result.data);
        });
        const get = freeEl('button', 'free-link', 'Ücretsiz planda Codex nedir?');
        get.type = 'button';
        get.addEventListener('click', () => window.pywebview?.api?.open_external?.(ch.key_page));
        row.append(connect, get);
        card.append(row, before);
      } else if (!ch.connected) {
        const row = freeEl('div', 'free-key-row');
        const label = freeEl('label', '', 'Ücretsiz anahtarını buraya yapıştır');
        const input = freeEl('input', 'free-key');
        input.type = 'password'; input.autocomplete = 'off'; input.spellcheck = false;
        input.id = `freeKey-${ch.id}`; label.htmlFor = input.id;
        input.setAttribute('aria-describedby', error.id);
        // Fides FS3: both consents are chosen before connecting; none is on by default.
        const before = freeEl('div', 'free-consents');
        const pre = {};
        for (const [field, text] of FREE_CONSENTS) {
          const label = freeEl('label');
          const box = freeEl('input');
          box.type = 'checkbox'; box.checked = false;
          pre[field] = box;
          label.append(box, document.createTextNode(text));
          before.append(label);
        }
        const connect = freeEl('button', 'free-btn', 'Bağla');
        connect.type = 'button';
        connect.addEventListener('click', async () => {
          const key = input.value.trim();
          input.value = '';
          if (!key) { error.textContent = 'Önce anahtarı yapıştır.'; input.focus(); return; }
          connect.disabled = true; connect.textContent = 'Kontrol ediliyor…'; error.textContent = '';
          const result = await freeCall('connect', {channel: ch.id, key, send: pre.send.checked, backup: pre.backup.checked});
          connect.disabled = false; connect.textContent = 'Bağla';
          if (result.status !== 'ok') { error.textContent = result.message || result.data || 'Bağlanamadı.'; input.focus(); return; }
          renderFreeChannels(result.data);
          const next = document.getElementById(`freeKey-${ch.id}`) || freeChannelsEl.querySelector('.free-channel[data-connected="true"] .free-btn');
          if (next) next.focus();
        });
        const get = freeEl('button', 'free-link', 'Anahtar nereden alınır?');
        get.type = 'button';
        get.addEventListener('click', () => window.pywebview?.api?.open_external?.(ch.key_page));
        row.append(label, input, connect, get);
        card.append(row, before);
      } else {
        const consents = freeEl('div', 'free-consents');
        for (const [field, text] of FREE_CONSENTS) {
          const label = freeEl('label');
          const box = freeEl('input');
          box.type = 'checkbox'; box.checked = !!ch[field];
          box.addEventListener('change', async () => {
            const result = await freeCall('consent', {channel: ch.id, [field]: box.checked});
            if (result.status === 'ok') renderFreeChannels(result.data);
            else { box.checked = !box.checked; error.textContent = result.message || 'Kaydedilemedi.'; }
          });
          label.append(box, document.createTextNode(text));
          consents.append(label);
        }
        const remove = freeEl('button', 'free-btn ghost', 'Bağlantıyı kaldır');
        remove.type = 'button';
        remove.addEventListener('click', async () => {
          const result = await freeCall('disconnect', {channel: ch.id});
          if (result.status === 'ok') renderFreeChannels(result.data);
        });
        const model = freeEl('span', 'free-persona', ch.kind === 'account' ? 'Model: Codex\'in varsayılanı'
          : (ch.model ? `Model: ${ch.model}` : ''));
        consents.append(remove, model);
        card.append(consents);
      }
      card.append(freeEl('p', 'free-privacy', ch.privacy), error);
      freeChannelsEl.append(card);
    }
    const start = document.getElementById('freeSheetStart');
    if (start) start.disabled = !((status && status.channels) || []).some(c => c.connected && c.send);
  }

  async function openFreeSheet() {
    if (!freeSheet) return;
    freeSheetOpener = document.activeElement;
    freeSheet.hidden = false;
    const result = await freeCall('status');
    if (result.status === 'ok') renderFreeChannels(result.data);
    const first = freeSheet.querySelector('.free-key, .free-btn, #freeSheetClose');
    if (first) first.focus();
  }

  function closeFreeSheet() {
    if (!freeSheet) return;
    freeSheet.hidden = true;
    if (freeSheetOpener && typeof freeSheetOpener.focus === 'function') freeSheetOpener.focus();
  }

  async function startFreeChat() {
    const status = await freeCall('status');
    if (status.status !== 'ok' || !(status.data.channels || []).some(c => c.connected && c.send)) {
      await openFreeSheet();
      return;
    }
    const created = await freeCall('new');
    if (created.status !== 'ok') { appendMsg('err', 'SPES', created.message || 'Ücretsiz sohbet açılamadı.'); return; }
    closeFreeSheet();
    if (typeof loadActiveConversation === 'function') await loadActiveConversation();
    if (typeof inputEl !== 'undefined' && inputEl) inputEl.focus();
  }

  // A free conversation: the page sends agent "free" and hides agent and permission choices.
  window.applyFreeChat = function applyFreeChat(conv) {
    const free = !!(conv && conv.free);
    document.body.classList.toggle('free-chat', free);
    if (free && typeof mainAgentSelect !== 'undefined' && mainAgentSelect) {
      if (![...mainAgentSelect.options].some(o => o.value === 'free')) {
        const option = document.createElement('option');
        option.value = 'free'; option.textContent = 'Ücretsiz';
        mainAgentSelect.append(option);
      }
      mainAgentSelect.value = 'free';
    } else if (!free && typeof mainAgentSelect !== 'undefined' && mainAgentSelect) {
      [...mainAgentSelect.options].filter(o => o.value === 'free').forEach(o => o.remove());
    }
  };

  document.getElementById('btnFreeChatStart')?.addEventListener('click', startFreeChat);
  document.getElementById('btnFreeChatManage')?.addEventListener('click', openFreeSheet);
  document.getElementById('freeSheetClose')?.addEventListener('click', closeFreeSheet);
  document.getElementById('freeSheetStart')?.addEventListener('click', startFreeChat);
  freeSheet?.addEventListener('click', e => { if (e.target === freeSheet) closeFreeSheet(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && freeSheet && !freeSheet.hidden) closeFreeSheet(); });
"""
