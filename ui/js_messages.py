"""Quartz messages JavaScript fragment; composed in the shared application scope."""

JAVASCRIPT = r"""  let ttsEnabled = true;

  let thinking   = false;
  let msgCount   = 0;
  let startTime  = Date.now();
  let inpHistory = [];
  let histCursor = -1;
  let safeMode = false;
  let advisorEnabled = false;
  let requestStarted = 0;
  let requestTimer = null;

  function setOrb(state) {
    orbCore.dataset.state = ['listening', 'thinking', 'error'].includes(state) ? state : 'idle';
  }

  function tick() {
    const d = new Date();
    clockEl.textContent = d.toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    const up = Math.floor((Date.now() - startTime) / 1000);
    const h = String(Math.floor(up/3600)).padStart(2,'0');
    const m = String(Math.floor((up%3600)/60)).padStart(2,'0');
    const s = String(up%60).padStart(2,'0');
    document.getElementById('sessUptime').textContent = `${h}:${m}:${s}`;
  }
  setInterval(tick, 1000); tick();

  function logLine(msg) {
    const ts = new Date().toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    const line = document.createElement('div');
    const stamp = document.createElement('span'); stamp.textContent = `[${ts}] `;
    line.append(stamp, document.createTextNode(String(msg)));
    logBox.appendChild(line);
    logBox.scrollTop = logBox.scrollHeight;
    while (logBox.children.length > 80) logBox.removeChild(logBox.firstChild);
  }

  // ── Scroll Position State Controller ───────────────────
  const btnJumpBottom = document.getElementById('btnJumpBottom');
  const SCROLL_BOTTOM_THRESHOLD = 38;
  let userPinnedToBottom = true;
  let unreadWhileScrolledUp = 0;
  let programmaticScroll = false;

  function isNearBottom() {
    if (!chatEl) return true;
    const distance = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight;
    return distance <= SCROLL_BOTTOM_THRESHOLD;
  }

  function updateJumpBottomBtn() {
    if (!btnJumpBottom) return;
    if (!userPinnedToBottom && unreadWhileScrolledUp > 0) {
      btnJumpBottom.textContent = unreadWhileScrolledUp > 1
        ? `Yeni mesajlar (${unreadWhileScrolledUp}) ↓`
        : 'Yeni mesajlar ↓';
      btnJumpBottom.classList.add('show');
    } else {
      btnJumpBottom.classList.remove('show');
    }
  }

  function scrollToBottom(force = false) {
    if (!chatEl) return;
    if (!force && !userPinnedToBottom) return;
    programmaticScroll = true;
    chatEl.scrollTop = chatEl.scrollHeight;
    userPinnedToBottom = true;
    unreadWhileScrolledUp = 0;
    updateJumpBottomBtn();
    requestAnimationFrame(() => { programmaticScroll = false; });
  }

  chatEl.addEventListener('wheel', (e) => {
    if (e.deltaY < 0) {
      userPinnedToBottom = false;
    } else if (e.deltaY > 0 && isNearBottom()) {
      userPinnedToBottom = true;
      unreadWhileScrolledUp = 0;
      updateJumpBottomBtn();
    }
  }, { passive: true });

  chatEl.addEventListener('scroll', () => {
    if (programmaticScroll) return;
    if (isNearBottom()) {
      userPinnedToBottom = true;
      unreadWhileScrolledUp = 0;
      updateJumpBottomBtn();
    } else {
      userPinnedToBottom = false;
    }
  }, { passive: true });

  if (btnJumpBottom) {
    btnJumpBottom.addEventListener('click', () => {
      scrollToBottom(true);
    });
  }

  function formatMessageLabel(m) {
    if (!m) return 'QUARTZ';
    const sender = (m.sender || (m.role === 'user' ? 'user' : 'quartz')).toLowerCase();
    const recipient = (m.recipient || (m.metadata && m.metadata.recipient) || '').toLowerCase();
    if (sender === 'user' || m.role === 'user') {
      if (recipient && recipient !== 'all' && recipient !== 'user') {
        return `SEN → ${recipient.toUpperCase()}`;
      }
      return 'SEN';
    }
    const senderUp = sender.toUpperCase();
    if (recipient === 'codex' || recipient === 'antigravity') {
      return `${senderUp} → ${recipient.toUpperCase()}`;
    }
    if (recipient === 'all') {
      return `${senderUp} · GRUP`;
    }
    return senderUp;
  }

  function formatModelTagText(m) {
    if (!m || m.role === 'user') return '';
    const meta = m.metadata || {};
    const model = meta.model || m.model || '';
    const effort = meta.effort || m.effort || '';
    if (!model) return '';
    return effort ? `${model} · ${effort}` : model;
  }

  function agentMessageView(text, msg, detailLevel) {
    text = String(text || '');
    if (msg?.role === 'user') return {summary:text, details:'', state:''};
    const meta = msg?.metadata || {};
    const marker = /\r?\n\s*---TEKNIK_AYRINTILAR---\r?\n/;
    const match = marker.exec(text);
    const summary = match ? text.slice(0, match.index).trimEnd() : text;
    let details = match ? text.slice(match.index + match[0].length) : '';
    let state = ({failed:'Başarısız', cancelled:'Durduruldu', interrupted:'Önceki oturum kesildi; otomatik sürdürülmedi', blocked:'Henüz doğrulanmadı',
      awaiting_approval:'Kullanıcı onayı bekleniyor'})[msg?.status || meta.status] || '';
    if ((msg?.status || meta.status) === 'completed' && ['project','full'].includes(meta.permission_level)) {
      const check = meta.host_evidence?.source_validation;
      state = check?.status === 'FAILED' ? 'Ajan bitti; kaynak sözdizimi kontrolü başarısız.'
        : check?.status === 'VERIFIED' ? 'Python sözdizimi doğrulandı; çalışma/test başarısı doğrulanmış değil.'
        : 'Ajan yanıtı tamamlandı; bağımsız çalışma/test kanıtı yok.';
      if (meta.host_evidence?.historical) state = 'Önceki oturumun kaynak kanıtı: ' + state;
    }
    const evidence = {};
    for (const key of ['error','run_id','squad_task_id','checkpoint','files_changed','performance','permission_level','review_scope','host_evidence']) {
      if (meta[key] != null && meta[key] !== '') evidence[key] = meta[key];
    }
    if (Object.keys(evidence).length) details += (details ? '\n\n' : '') + JSON.stringify(evidence, null, 2);
    return {summary, details, state, open:detailLevel === 'technical'};
  }

  function renderMessageBody(bubble, text, msg) {
    const level = document.getElementById('responseDetail')?.value || 'short';
    const view = agentMessageView(text, msg, level);
    const key = JSON.stringify([text, view.details, view.state, level]);
    if (bubble.dataset.renderKey === key) return false;
    bubble.dataset.renderKey = key;
    bubble.classList?.toggle('pending', view.summary === '...');
    bubble.replaceChildren();
    if (view.state) {
      const state = document.createElement('div'); state.className = 'msg-state'; state.textContent = view.state;
      bubble.append(state);
    }
    const body = document.createElement('div'); appendMessageText(body, view.summary); bubble.append(body);
    if (msg?.status === 'interrupted' && msg.id) {
      const resume = document.createElement('button'); resume.className = 'control-btn';
      resume.textContent = 'Yeni görev taslağı hazırla';
      resume.onclick = async () => {
        const result = await window.pywebview.api.chat_prepare_resume(currentConvId, msg.id);
        if (result.status !== 'ok') { logLine(String(result.data || 'Taslak hazırlanamadı')); return; }
        const fresh = await window.pywebview.api.chat_new('Devam taslağı',result.data.agent,result.data.project_id || '');
        if (fresh.status !== 'ok') { logLine(String(fresh.data || 'Yeni taslak sohbeti açılamadı')); return; }
        await loadActiveConversation(); // New conversation has no provider sessions.
        document.getElementById('mainPermissionLevel').value = 'read-only';
        updatePermissionSelectionHint();
        window.__writeConfirmed = false;
        inputEl.value = result.data.draft; inputEl.focus();
        logLine(result.data.warning); // Deliberately no sendAgentMessage call.
      };
      bubble.append(resume);
    }
    if (view.details) {
      const details = document.createElement('details'); details.className = 'technical-details'; details.open = view.open;
      const title = document.createElement('summary'); title.textContent = 'Teknik ayrıntılar';
      const full = document.createElement('pre'); full.textContent = view.details;
      full.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font:inherit';
      details.append(title, full); bubble.append(details);
    }
    return true;
  }

  // Fenced ``` blocks become monospace code panels. Text only: no HTML is parsed.
  function appendMessageText(container, text) {
  function hasMarkdownSyntax(value) {
    const src = String(value ?? '');
    if (/^(?:\s*#{1,6}\s+\S|\s*(?:[-*•]|\d+[.)])\s+\S)/m.test(src)) return true;
    return /(?<!`)`[^`\n]+`(?!`)|\[[^\]\n]+\]\([^)\n]+\)|\*\*[^*\n]+?\*\*|__[^_\n]+?__|(?<!\*)\*[^*\s\n][^*\n]*?\*(?!\*)|(?<![\w_])_[^_\s\n][^_\n]*?_(?![\w_])/.test(src);
  }

  function appendInlineFormatted(parent, text) {
    const src = String(text ?? '');
    const tokenRe = /(?<!`)`([^`\n]+)`(?!`)|\[([^\]\n]+)\]\(([^)\n]+)\)|\*\*([^*\n]+?)\*\*|__([^_\n]+?)__|(?<!\*)\*([^*\s\n](?:[^*\n]*?[^*\s\n])?)\*(?!\*)|(?<![\w_])_([^_\s\n](?:[^_\n]*?[^_\s\n])?)_(?![\w_])/g;
    let lastIndex = 0;
    let match = null;
    while ((match = tokenRe.exec(src)) !== null) {
      if (match.index > lastIndex) {
        const plain = document.createElement('span');
        plain.textContent = src.slice(lastIndex, match.index);
        parent.append(plain);
      }
      if (match[1] !== undefined) {
        const code = document.createElement('code');
        code.className = 'msg-inline-code';
        code.textContent = match[1];
        parent.append(code);
      } else if (match[2] !== undefined) {
        const link = document.createElement('span');
        link.className = 'msg-link';
        link.textContent = match[2];
        link.title = match[3].trim();
        parent.append(link);
      } else if (match[4] !== undefined || match[5] !== undefined) {
        const strong = document.createElement('strong');
        appendInlineFormatted(strong, match[4] ?? match[5]);
        parent.append(strong);
      } else if (match[6] !== undefined || match[7] !== undefined) {
        const em = document.createElement('em');
        appendInlineFormatted(em, match[6] ?? match[7]);
        parent.append(em);
      }
      lastIndex = tokenRe.lastIndex;
    }
    if (lastIndex === 0) {
      parent.textContent = src;
      return;
    }
    if (lastIndex < src.length) {
      const tail = document.createElement('span');
      tail.textContent = src.slice(lastIndex);
      parent.append(tail);
    }
  }

  function appendProseBlocks(target, prose) {
    const lines = String(prose ?? '').split(/\r?\n/);
    let listEl = null;
    let listType = '';
    let paragraphLines = [];
    const flushParagraph = () => {
      if (!paragraphLines.length) return;
      const p = document.createElement('p');
      p.className = 'msg-p';
      appendInlineFormatted(p, paragraphLines.join('\n'));
      target.append(p);
      paragraphLines = [];
    };
    const flushList = () => {
      if (!listEl) return;
      target.append(listEl);
      listEl = null;
      listType = '';
    };
    for (const rawLine of lines) {
      const trimmed = rawLine.trim();
      if (!trimmed) {
        flushParagraph();
        flushList();
        continue;
      }
      const headingMatch = /^(#{1,6})\s+(.+?)\s*$/.exec(trimmed);
      if (headingMatch) {
        flushParagraph();
        flushList();
        const level = Math.min(4, headingMatch[1].length);
        const heading = document.createElement('h' + level);
        heading.className = 'msg-heading msg-h' + level;
        appendInlineFormatted(heading, headingMatch[2]);
        target.append(heading);
        continue;
      }
      const ulMatch = /^[-*•]\s+(.+?)\s*$/.exec(trimmed);
      if (ulMatch) {
        flushParagraph();
        if (listType !== 'ul') {
          flushList();
          listEl = document.createElement('ul');
          listEl.className = 'msg-list';
          listType = 'ul';
        }
        const li = document.createElement('li');
        appendInlineFormatted(li, ulMatch[1]);
        listEl.append(li);
        continue;
      }
      const olMatch = /^\d+[.)]\s+(.+?)\s*$/.exec(trimmed);
      if (olMatch) {
        flushParagraph();
        if (listType !== 'ol') {
          flushList();
          listEl = document.createElement('ol');
          listEl.className = 'msg-list';
          listType = 'ol';
        }
        const li = document.createElement('li');
        appendInlineFormatted(li, olMatch[1]);
        listEl.append(li);
        continue;
      }
      flushList();
      paragraphLines.push(rawLine);
    }
    flushParagraph();
    flushList();
  }
    const value = String(text ?? '');
    if (!value.includes('```')) {
      if (!hasMarkdownSyntax(value)) { container.textContent = value; return; }
      appendProseBlocks(container, value);
      return;
    }
    const parts = value.split('```');
    parts.forEach((part, index) => {
      const isCode = index % 2 === 1 && index < parts.length - 1;
      if (!isCode) {
        const prose = (index % 2 === 1 ? '```' + part : part).replace(/^\n+|\n+$/g, '');
        if (prose) {
          const segment = document.createElement('div');
          if (!hasMarkdownSyntax(prose)) {
            segment.textContent = prose;
          } else {
            segment.className = 'msg-prose';
            appendProseBlocks(segment, prose);
          }
          container.append(segment);
        }
        return;
      }
      const newline = part.indexOf('\n');
      const lang = newline > 0 ? part.slice(0, newline).trim() : '';
      const block = document.createElement('div'); block.className = 'msg-code';
      if (/^[\w+#.-]{1,20}$/.test(lang)) {
        const label = document.createElement('span'); label.className = 'msg-code-lang'; label.textContent = lang; block.append(label);
      }
      const pre = document.createElement('pre');
      pre.textContent = (newline >= 0 ? part.slice(newline + 1) : part).replace(/\n$/, '');
      block.append(pre); container.append(block);
    });
  }

  function appendMsg(kind, label, text, msgId='', sender='bot', msgObj=null, skipScroll=false, forceScroll=false) {
    if (!programmaticScroll && !isNearBottom()) {
      userPinnedToBottom = false;
    }
    const prevScrollTop = chatEl.scrollTop;
    const wrap = document.createElement('div');
    const cleanSender = (sender || 'bot').toLowerCase();
    wrap.className = `msg ${kind} sender-${cleanSender}`;
    if (msgId) wrap.dataset.msgId = msgId;
    let ts = new Date().toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    if (msgObj && msgObj.timestamp) {
      try {
        const rawTs = msgObj.timestamp < 1e12 ? msgObj.timestamp * 1000 : msgObj.timestamp;
        ts = new Date(rawTs).toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
      } catch (_) {}
    }
    const seqNum = msgObj && (msgObj.sequence || (msgObj.metadata && msgObj.metadata.sequence));
    const modelTagText = formatModelTagText(msgObj);
    if (kind === 'sys') {
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.textContent = text;
      wrap.append(bubble);
    } else {
      const inner = document.createElement('div');
      const meta = document.createElement('div');
      meta.className = 'msg-meta';
      if (label) {
        const senderTag = document.createElement('span');
        senderTag.className = `msg-sender-tag tag-${cleanSender}`;
        senderTag.textContent = label;
        meta.append(senderTag);
      }
      if (seqNum) {
        const seqTag = document.createElement('span');
        seqTag.className = 'msg-seq-tag';
        seqTag.textContent = `#${seqNum}`;
        meta.append(seqTag);
      }
      if (modelTagText) {
        const modelTag = document.createElement('span');
        modelTag.className = 'msg-model-tag';
        modelTag.textContent = modelTagText;
        meta.append(modelTag);
      }
      const tsTag = document.createElement('span');
      tsTag.className = 'msg-ts';
      tsTag.textContent = ts;
      meta.append(tsTag);
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      inner.append(meta, bubble);
      wrap.append(inner);
      renderMessageBody(bubble, text, msgObj);
    }
    chatEl.appendChild(wrap);
    if (!skipScroll) {
      if (forceScroll || userPinnedToBottom) {
        scrollToBottom(true);
      } else {
        chatEl.scrollTop = prevScrollTop;
        unreadWhileScrolledUp++;
        updateJumpBottomBtn();
      }
    }
    return wrap;
  }

  let activeTaskSquad = null;
  function updateSquadBadge(squad, conversationId = currentConvId) {
    const badge = document.getElementById('squadBadge');
    if (!badge || !squad) return;
    if (activeTaskSquad?.conversation_id === conversationId) squad = activeTaskSquad;
    if (squad.checking && !activeTaskSquad) {
      badge.classList.remove('warn');
      badge.textContent = 'Squad: Kontrol ediliyor';
      badge.title = 'Sohbet kullanılabilir; bağlantı arka planda doğrulanıyor.';
    } else if (squad.connected) {
      badge.classList.remove('warn');
      badge.textContent = 'Squad: Bağlı';
      badge.title = `Squad veritabanı aktif (${squad.version || 'v0.7.6'}) · ${squad.database || squad.db_path || ''}`;
    } else if (squad.mode === 'task-isolated' && squad.ready && !squad.error) {
      badge.classList.remove('warn');
      badge.textContent = 'Squad: Görevle bağlanır';
      badge.title = squad.message || 'Görev başladığında ayrı Squad veritabanı oluşturulur; mod klasörüne yazılmaz.';
    } else {
      badge.classList.add('warn');
      badge.textContent = 'Squad: Bağlantı Sorunu';
      badge.title = squad.error || squad.message || 'Squad veritabanına erişilemiyor';
    }
  }

  function syncConversationMessages(messages, replaceAll=false) {
    if (!Array.isArray(messages)) return;
    if (replaceAll) {
      chatEl.innerHTML = '';
      userPinnedToBottom = true;
      unreadWhileScrolledUp = 0;
      updateJumpBottomBtn();
    } else {
      if (!programmaticScroll && !isNearBottom()) {
        userPinnedToBottom = false;
      }
      chatEl.querySelectorAll('[data-welcome="1"]').forEach(el => el.remove());
    }
    const savedScrollTop = chatEl.scrollTop;
    let hadNewOrUpdatedContent = false;

    for (const m of messages) {
      if (!m || !m.id) continue;
      const cleanSender = (m.sender || (m.role === 'user' ? 'user' : 'bot')).toLowerCase();
      const statusVal = m.status || (m.metadata && m.metadata.status) || '';
      const kind = m.role === 'user' ? 'user' : (statusVal === 'failed' ? 'err' : 'bot');
      const label = formatMessageLabel(m);
      const displayContent = m.content || (statusVal === 'running' || statusVal === 'starting' ? '...' : '');
      let wrap = chatEl.querySelector(`.msg[data-msg-id="${m.id}"]`);
      if (!wrap) {
        wrap = appendMsg(kind, label, displayContent, m.id, cleanSender, m, true, false);
        hadNewOrUpdatedContent = true;
      } else {
        const desiredClass = `msg ${kind} sender-${cleanSender}`;
        if (wrap.className !== desiredClass) wrap.className = desiredClass;
        const tagEl = wrap.querySelector('.msg-sender-tag');
        if (tagEl) {
          const desiredTagClass = `msg-sender-tag tag-${cleanSender}`;
          if (tagEl.className !== desiredTagClass) tagEl.className = desiredTagClass;
          if (tagEl.textContent !== label) tagEl.textContent = label;
        }
        const seqNum = m.sequence || (m.metadata && m.metadata.sequence);
        let seqEl = wrap.querySelector('.msg-seq-tag');
        if (seqNum) {
          if (!seqEl) {
            seqEl = document.createElement('span');
            seqEl.className = 'msg-seq-tag';
            const metaEl = wrap.querySelector('.msg-meta');
            const tsEl = wrap.querySelector('.msg-ts');
            if (metaEl && tsEl) metaEl.insertBefore(seqEl, tsEl);
          }
          const seqText = `#${seqNum}`;
          if (seqEl.textContent !== seqText) seqEl.textContent = seqText;
        }
        const modelTagText = formatModelTagText(m);
        let modelEl = wrap.querySelector('.msg-model-tag');
        if (modelTagText) {
          if (!modelEl) {
            modelEl = document.createElement('span');
            modelEl.className = 'msg-model-tag';
            const metaEl = wrap.querySelector('.msg-meta');
            const tsEl = wrap.querySelector('.msg-ts');
            if (metaEl && tsEl) metaEl.insertBefore(modelEl, tsEl);
          }
          if (modelEl.textContent !== modelTagText) modelEl.textContent = modelTagText;
        }
        const bubbleEl = wrap.querySelector('.bubble');
        if (bubbleEl && renderMessageBody(bubbleEl, displayContent, m)) {
          hadNewOrUpdatedContent = true;
        }
      }
    }

    if (replaceAll || userPinnedToBottom) {
      scrollToBottom(true);
    } else {
      chatEl.scrollTop = savedScrollTop;
      if (hadNewOrUpdatedContent) {
        unreadWhileScrolledUp++;
        updateJumpBottomBtn();
      }
    }
  }

  function setThinking(v) {
    thinking = v;
    document.body.classList.toggle('thinking-active', !!v);
    thinkingRow.classList.toggle('show', v);
    // Sending while a managed turn runs submits a same-task instruction.
    sendBtn.classList.remove('disabled');
    const btnCont = document.getElementById('btnContinueCollab');
    if (btnCont) btnCont.disabled = v;
    setOrb(v ? 'thinking' : 'idle');
    cancelBtn.style.display = v ? 'inline-block' : 'none';
    if (v) {
      requestStarted = Date.now();
      clearInterval(requestTimer);
      requestTimer = setInterval(() => {
        const sec = Math.floor((Date.now() - requestStarted) / 1000);
        thinkingText.textContent = `görev yürütülüyor... ${sec}s`;
      }, 1000);
    } else {
      clearInterval(requestTimer);
      thinkingText.textContent = 'işleniyor...';
    }
  }

  function appendActionCard(event) {
    const prevScrollTop = chatEl.scrollTop;
    const card = document.createElement('div'); card.className = 'action-card';
    const tools = event.tools || [event.tool];
    const title = document.createElement('div');
    title.textContent = `Onay gerekli [${event.risk}]: ${tools.filter(Boolean).join(', ')}`;
    const actions = document.createElement('div'); actions.className = 'actions';
    const approve = document.createElement('button'); approve.textContent = 'Onayla';
    const reject = document.createElement('button'); reject.textContent = 'İptal'; reject.className = 'danger';
    approve.onclick = async () => { card.remove(); await sendDirect(`onayla ${event.code}`); };
    reject.onclick = async () => { card.remove(); await sendDirect('iptal'); };
    actions.append(approve, reject); card.append(title, actions);
    chatEl.appendChild(card);
    if (userPinnedToBottom) scrollToBottom(true);
    else chatEl.scrollTop = prevScrollTop;
  }

  function renderUiEvents(events=[]) {
    for (const event of events) {
      if (event.type === 'confirmation') appendActionCard(event);
      else if (event.type === 'tool_running') logLine(`Araç: ${event.tool} çalışıyor`);
      else if (event.type === 'tool_completed') logLine(`✓ ${event.tool}: tamamlandı`);
      else if (event.type === 'tool_failed') logLine(`✗ ${event.tool}: ${event.error}`);
      else if (event.type === 'blocked') appendMsg('sys', '', `Güvenli Mod engelledi: ${(event.tools || [event.tool]).join(', ')}`);
      else if (event.type === 'cancelled') appendMsg('sys', '', 'İstek iptal edildi.');
      else if (event.type === 'rate_limit') appendMsg('sys', '', `API kotası doldu; ${Math.ceil(event.seconds)} saniye bekleniyor. İptal edebilirsin.`);
      else if (event.type === 'screen_advice') appendMsg('sys', '', `Ekran Rehberi: ${event.text}`);
      else if (event.type === 'task_created' || event.type === 'task_updated') renderTasks([event.task]);
    }
  }

  function renderTasks(tasks=[]) {
    if (!tasks.length) { taskList.textContent = 'Yerel asistan görevi yok'; return; }
    taskList.innerHTML = '';
    for (const task of tasks.slice(0, 5)) {
      const row = document.createElement('div'); row.className = 'task-row';
      const done = task.steps.filter(s => s.status === 'completed').length;
      const title = document.createElement('div');
      title.textContent = `${task.status === 'completed' ? '✓ ' : ''}${task.title}`;
      const meta = document.createElement('div');
      meta.textContent = `${done}/${task.steps.length} adım · ${task.status}`;
      meta.className = 'task-meta';
      row.append(title, meta);
      if (!['completed','failed','cancelled'].includes(task.status)) {
        const stop = document.createElement('button'); stop.className = 'control-btn';
        stop.textContent = 'İptal';
        stop.onclick = async () => { await window.pywebview.api.cancel_task(task.id); pollTasks(); };
        row.appendChild(stop);
      }
      taskList.appendChild(row);
    }
  }

  function renderResponse(resp) {
    renderUiEvents(resp.ui_events || []);
    if (resp.status === 'ok') appendMsg('bot', 'QUARTZ', resp.data);
    else appendMsg('err', 'HATA', resp.data || 'Bilinmeyen hata');
  }

  async function sendDirect(text) {
    setThinking(true);
    const resp = await window.pywebview.api.send_chat(text);
    setThinking(false);
    renderResponse(resp);
  }

"""
