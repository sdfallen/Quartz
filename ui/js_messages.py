"""SpeS messages JavaScript fragment; composed in the shared application scope."""

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

  const TEAM_PERSONA = {claude: 'FATUM', codex: 'FIDES', antigravity: 'EOS'};
  const TEAM_STEP = {1: 'Plan', 2: 'Eleştiri', 3: 'Karar', 4: 'Hazırlık', 5: 'Kontrol', 6: 'Kapanış'};
  function teamStepLabel(m) {
    const meta = (m && m.metadata) || {};
    // SpeS's own record of a "bunu hatırla" request, shown on the user's message.
    if (meta.memory && typeof meta.memory === 'object') {
      if (meta.memory.saved) return 'Hafızaya alındı';
      return meta.memory.reason === 'secret' ? 'Kaydedilmedi: gizli bilgi' : '';
    }
    if (!meta.team || !TEAM_STEP[meta.team_step]) return '';
    return meta.team_step === 4 && (m.sender || meta.sender) === 'claude' ? 'İnşa' : TEAM_STEP[meta.team_step];
  }
  function formatMessageLabel(m) {
    if (!m) return 'SPES';
    if (m.metadata && m.metadata.team && TEAM_PERSONA[(m.sender || m.metadata.sender || '').toLowerCase()]) {
      const agent = (m.sender || m.metadata.sender).toLowerCase();
      return `${TEAM_PERSONA[agent]} · ${agent === 'antigravity' ? 'ANTIGRAVITY' : agent.toUpperCase()}`;
    }
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
    // Execution, evidence and goal are separate host fields; model text never earns a badge.
    let status = msg?.status || meta.status;
    // A desktop task posts progress lines while it runs. Their chat status only says the
    // line was delivered; the task's own state decides the badge (live exam 9 Nov:
    // "Görev hazırlanıyor" showed "Yürütme bitti, hedef henüz doğrulanmadı").
    const taskStatus = meta.natural_task ? String(meta.task_status || '') : '';
    const inProgress = ['starting', 'running', 'waiting_for_inline_permission'].includes(taskStatus);
    if (taskStatus && !inProgress && status === 'completed') {
      status = taskStatus === 'expired' ? 'failed'
        : /^(blocked|permission)/.test(taskStatus) ? 'blocked'
        : ['failed', 'cancelled', 'partial'].includes(taskStatus) ? taskStatus : status;
    }
    const outcome = meta.outcome || {};
    const PARTIAL = 'Kısmi — istenen ajanlardan biri tamamlayamadı';
    let state = ({failed:'Başarısız', cancelled:'Durduruldu', interrupted:'Önceki oturum kesildi; otomatik sürdürülmedi',
      blocked:'Engellendi; nedeni ayrıntılarda', awaiting_approval:'Onay bekleniyor — görev duraklatıldı',
      partial:PARTIAL})[status] || '';
    // Badge: a short scannable outcome (tone + word) beside the full sentence.
    // ok = host-checked, warn = finished without independent evidence.
    let [tone, label] = ({failed:['fail','Başarısız'], cancelled:['stop','Durduruldu'], interrupted:['stop','Kesildi'],
      blocked:['fail','Engellendi'], awaiting_approval:['wait','Onay bekliyor'], partial:['warn','Kısmi']})[status] || ['', ''];
    if (status === 'interrupted' && meta.interrupted_while === 'awaiting_approval') {
      state = 'Önceki oturum onay beklerken kesildi; eski izin geçersiz. Devam için görevi yeniden yaz.';
    }
    const missing = Object.entries(outcome.participants || {}).filter(([, s]) => s !== 'completed')
      .map(([agent]) => agent === 'codex' ? 'Codex' : agent === 'antigravity' ? 'Gemini' : agent === 'claude' ? 'Claude' : String(agent));
    if (status === 'completed') {
      const checks = outcome.goal_evidence?.checks;
      if (outcome.goal_verdict === 'VERIFIED' && outcome.goal_evidence?.level === 'HOST POSTCONDITION' && Array.isArray(checks) && checks.length) {
        state = `Önceden bildirilen ${checks.length} hedef koşulu dosyadan doğrulandı; kullanıcı kabulü ayrı.`;
        [tone, label] = ['ok', 'Doğrulandı'];
      } else if (outcome.goal_verdict === 'PARTIAL') {
        state = PARTIAL;
        [tone, label] = ['warn', 'Kısmi'];
      } else if (['project','full'].includes(meta.permission_level)) {
        const check = meta.host_evidence?.source_validation;
        // Test commands the agent ran, with exit status observed from the CLI events (14 Nov:
        // 18/18 Node tests passed and the badge still said "Kanıt yok"). core.test_evidence.
        const tests = meta.host_evidence?.agent_tests;
        state = check?.status === 'FAILED' ? 'Ajan bitti; kaynak sözdizimi kontrolü başarısız.'
          : tests?.status === 'FAILED' ? 'Ajanın çalıştırdığı test komutu başarısız bitti.'
          : tests?.status === 'PASSED' ? 'Ajanın çalıştırdığı testler geçti (komut çıktısı gözlendi); SpeS testleri kendisi çalıştırmadı.'
          : check?.status === 'VERIFIED' ? 'Python sözdizimi doğrulandı; çalışma/test başarısı doğrulanmış değil.'
          : 'Ajan yanıtı tamamlandı; bağımsız çalışma/test kanıtı yok.';
        [tone, label] = check?.status === 'FAILED' ? ['fail', 'Kontrol başarısız']
          : tests?.status === 'FAILED' ? ['fail', 'Test başarısız']
          : tests?.status === 'PASSED' ? ['ok', 'Testler geçti']
          : check?.status === 'VERIFIED' ? ['warn', 'Kısmen doğrulandı'] : ['warn', 'Kanıt yok'];
        if (meta.host_evidence?.historical) state = 'Önceki oturumun kaynak kanıtı: ' + state;
      } else if (meta.natural_task && meta.host_check?.status === 'OBSERVED UI CRITERION VERIFIED'
                 && Array.isArray(meta.host_check.expected_text) && meta.host_check.expected_text.length) {
        state = 'İstenen metin SpeS gözlemiyle ekranda görüldü; kullanıcı kabulü ayrı.';
        [tone, label] = ['ok', 'Ekranda görüldü'];
      } else if (meta.review_scope || meta.natural_task) {
        state = 'Yürütme bitti, hedef henüz doğrulanmadı.';
        [tone, label] = ['warn', 'Doğrulanmadı'];
      }
    }
    if (state === PARTIAL && missing.length) state += ': ' + missing.join(', ');
    const evidence = {};
    for (const key of ['error','run_id','squad_task_id','checkpoint','files_changed','performance','permission_level','review_scope','host_evidence','host_check','outcome']) {
      if (meta[key] != null && meta[key] !== '') evidence[key] = meta[key];
    }
    if (Object.keys(evidence).length) details += (details ? '\n\n' : '') + JSON.stringify(evidence, null, 2);
    if (inProgress) state = '';
    if (!state) [tone, label] = ['', ''];
    return {summary, details, state, tone, label, open:detailLevel === 'technical'};
  }

  // Typing reveal for agent text that arrives while SpeS is open. History
  // (first load, conversation switch) appears at once; a growing streamed
  // message continues from what is already visible. Off under reduced motion
  // (low-spec keeps it: one rAF loop over text nodes); the full text is always in the DOM model it is rebuilt from.
  const revealedLength = new Map();
  let liveRevealArmed = false;
  let revealSuppressed = false;
  function revealMotionAllowed() {
    if (typeof window === 'undefined' || !document.body) return false;
    return !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }
  function revealMessage(bubble, body, msgId) {
    if (!msgId || typeof document.createTreeWalker !== 'function') return;
    const nodes = [];
    const walker = document.createTreeWalker(body, 4);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) nodes.push([n, n.nodeValue]);
    const total = nodes.reduce((sum, item) => sum + item[1].length, 0);
    const previous = revealedLength.get(msgId);
    if (!liveRevealArmed || revealSuppressed || !revealMotionAllowed()) { revealedLength.set(msgId, total); return; }
    let shown = previous === undefined ? 0 : Math.min(previous, total);
    revealedLength.set(msgId, shown);
    if (shown >= total) return;
    const token = {};
    bubble.__reveal = token;
    const caret = document.createElement('span');
    caret.className = 'reveal-caret';
    caret.setAttribute('aria-hidden', 'true');
    const rate = Math.max(90, (total - shown) / 1.4);  // chars/s; long answers finish in about 1.4 s
    // Blocks not reached yet stay out of the layout, so no empty bullet or box shows early.
    const blocks = Array.from(body.querySelectorAll ? body.querySelectorAll('li, .msg-p, .msg-heading, .msg-code') : []);
    const paint = () => {
      let budget = shown, anchor = null;
      for (const [node, value] of nodes) {
        if (budget >= value.length) { if (node.nodeValue !== value) node.nodeValue = value; budget -= value.length; anchor = node; }
        else if (budget > 0) { node.nodeValue = value.slice(0, budget); budget = 0; anchor = node; }
        else if (node.nodeValue !== '') node.nodeValue = '';
      }
      for (const block of blocks) block.classList.toggle('reveal-pending', !block.textContent);
      const target = anchor || nodes[0][0];
      if (target.parentNode) target.parentNode.insertBefore(caret, target.nextSibling);
    };
    const finish = () => { caret.remove(); for (const block of blocks) block.classList.remove('reveal-pending'); };
    // A timer, not requestAnimationFrame: WebView2 stops frames while SpeS is
    // covered (e.g. by the app an agent is driving) and the text must not wait for
    // that. Progress follows elapsed time; a hidden window gets the whole text.
    let last = performance.now();
    const next = () => setTimeout(() => step(performance.now()), 16);
    const step = (now) => {
      if (bubble.__reveal !== token || !body.isConnected) { finish(); return; }
      const hidden = typeof document.hidden === 'boolean' && document.hidden;
      shown = hidden ? total : Math.min(total, shown + Math.max(1, Math.round(rate * (now - last) / 1000)));
      last = now;
      revealedLength.set(msgId, shown);
      paint();
      if (userPinnedToBottom) scrollToBottom(true);
      if (shown < total) next();
      else { finish(); bubble.__reveal = null; }
    };
    paint();
    next();
  }

  // What each agent is doing right now, under its own working bubble. The
  // line comes from chat_poll agent_progress (memory only, never evidence).
  function renderAgentLive(progress) {
    const keep = new Set();
    for (const [agent, entry] of Object.entries(progress || {})) {
      if (!['codex', 'antigravity', 'claude'].includes(agent) || !entry || entry.status !== 'running') continue;
      if (!entry.activity || !/^[\w-]{1,80}$/.test(String(entry.message_id || ''))) continue;
      const bubble = chatEl.querySelector(`.msg[data-msg-id="${entry.message_id}"] .bubble`);
      if (!bubble || !bubble.parentNode) continue;
      let live = bubble.parentNode.querySelector(':scope > .agent-live');
      if (!live) {
        live = document.createElement('div');
        live.className = 'agent-live';
        const now = document.createElement('div'); now.className = 'agent-live-now';
        const gem = document.createElement('i'); gem.className = 'agent-live-gem'; gem.setAttribute('aria-hidden', 'true');
        const trail = document.createElement('div'); trail.className = 'agent-live-trail';
        now.append(gem); live.append(now, trail);
        bubble.after(live);
      }
      live.dataset.agent = agent;
      keep.add(live);
      const now = live.querySelector('.agent-live-now');
      const current = now.querySelector('span');
      if (!current || current.textContent !== entry.activity) {
        const text = document.createElement('span'); text.textContent = String(entry.activity).slice(0, 160);
        if (current) current.replaceWith(text); else now.append(text);
      }
      const history = (Array.isArray(entry.activity_trail) ? entry.activity_trail : [])
        .filter(t => t !== entry.activity).slice(-3).map(t => String(t).slice(0, 160));
      const trail = live.querySelector('.agent-live-trail');
      if (trail.dataset.key !== JSON.stringify(history)) {
        trail.dataset.key = JSON.stringify(history);
        trail.replaceChildren(...history.map(t => { const s = document.createElement('span'); s.textContent = t; return s; }));
      }
    }
    chatEl.querySelectorAll('.agent-live').forEach(el => { if (!keep.has(el)) el.remove(); });
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
      const state = document.createElement('div'); state.className = 'msg-state';
      if (view.label) {
        // Icon + word + sentence: the outcome never depends on color alone.
        state.dataset.tone = view.tone;
        const badge = document.createElement('span'); badge.className = 'msg-badge';
        const icon = document.createElement('i'); icon.className = 'msg-badge-icon'; icon.setAttribute('aria-hidden', 'true');
        const word = document.createElement('span'); word.textContent = view.label;
        badge.append(icon, word); state.append(badge);
        if (view.state !== view.label) {
          const note = document.createElement('span'); note.className = 'msg-state-note'; note.textContent = view.state;
          state.append(note);
        }
      } else {
        state.textContent = view.state;
      }
      bubble.append(state);
    }
    const body = document.createElement('div');
    const isUserMessage = msg?.role === 'user' || String(msg?.sender || '').toLowerCase() === 'user';
    if (isUserMessage) {
      body.textContent = view.summary;
    } else {
      appendMessageText(body, view.summary);
    }
    bubble.append(body);
    if (!isUserMessage && view.summary !== '...' && typeof revealMessage === 'function') revealMessage(bubble, body, msg?.id);
    if (!isUserMessage && view.summary !== '...' && window.QuartzPreview) window.QuartzPreview.decorate(bubble, view.summary + '\n' + (view.details || ''));
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
  const INLINE_RE = /(?<!`)`([^`\n]+)`(?!`)|(?<=^|[\s([{"'«“‘])(?:\[([^\[\]\n]+)\]\((https?:\/\/[^()\s\n]+)\)|\*\*(?=[^\s*\n])([^*\n]+)(?<=[^\s*\n])\*\*|__(?=[^\s_\n])([^_\n]+)(?<=[^\s_\n])__|\*(?!\*)(?=[^\s*.\n])([^*\n]+)(?<=[^\s*\n])\*(?!\*)|_(?!_)(?=[^\s_.\n])([^_\n]+)(?<=[^\s_\n])_(?!_))(?=$|[\s)\]}"'»”’,!?:;]|\.(?=$|[\s)\]}"'»”’]))/u;
  function hasMarkdownSyntax(value) {
    const src = String(value ?? '');
    if (/^(?:[ \t]*#{1,6}[ \t]+\S|[ \t]*(?:[-*•]|\d+[.)])[ \t]+\S)/m.test(src)) return true;
    return INLINE_RE.test(src);
  }

  function appendInlineFormatted(parent, text) {
    const src = String(text ?? '');
    const tokenRe = new RegExp(INLINE_RE.source, 'gu');
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
    let listStack = [];
    let paragraphLines = [];
    const createListEl = (type, startNum) => {
      const el = document.createElement(type);
      el.className = 'msg-list';
      if (type === 'ol' && startNum > 1) {
        el.start = startNum;
        if (typeof el.setAttribute === 'function') el.setAttribute('start', String(startNum));
      }
      return el;
    };
    const flushParagraph = () => {
      if (!paragraphLines.length) return;
      const p = document.createElement('p');
      p.className = 'msg-p';
      appendInlineFormatted(p, paragraphLines.join('\n'));
      target.append(p);
      paragraphLines = [];
    };
    const flushList = () => {
      listStack = [];
    };
    for (const rawLine of lines) {
      const trimmed = rawLine.trim();
      if (!trimmed) {
        flushParagraph();
        continue;
      }
      const headingMatch = /^[ \t]*(#{1,6})[ \t]+(.+?)[ \t]*$/.exec(rawLine);
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
      const listMatch = /^([ \t]*)(?:([-*•])|(\d+)[.)])[ \t]+(.+?)[ \t]*$/.exec(rawLine);
      if (listMatch) {
        flushParagraph();
        const indent = listMatch[1].replace(/\t/g, '  ').length;
        const itemType = listMatch[2] ? 'ul' : 'ol';
        const startNum = listMatch[3] ? parseInt(listMatch[3], 10) : 1;
        const itemText = listMatch[4];
        while (listStack.length > 1 && indent < listStack[listStack.length - 1].indent) {
          listStack.pop();
        }
        let top = listStack[listStack.length - 1];
        if (!top) {
          const rootList = createListEl(itemType, startNum);
          target.append(rootList);
          top = {el: rootList, type: itemType, indent};
          listStack.push(top);
        } else if (indent > top.indent) {
          const childList = createListEl(itemType, startNum);
          const parentItems = top.el.children;
          const lastLi = parentItems && parentItems.length ? parentItems[parentItems.length - 1] : null;
          (lastLi || top.el).append(childList);
          top = {el: childList, type: itemType, indent};
          listStack.push(top);
        } else if (top.type !== itemType) {
          listStack.pop();
          const replacement = createListEl(itemType, startNum);
          const parent = listStack[listStack.length - 1];
          if (parent) {
            const parentItems = parent.el.children;
            const lastLi = parentItems && parentItems.length ? parentItems[parentItems.length - 1] : null;
            (lastLi || parent.el).append(replacement);
          } else {
            target.append(replacement);
          }
          top = {el: replacement, type: itemType, indent};
          listStack.push(top);
        }
        const li = document.createElement('li');
        if (itemType === 'ol') {
          li.value = startNum;
          if (typeof li.setAttribute === 'function') li.setAttribute('value', String(startNum));
        }
        appendInlineFormatted(li, itemText);
        top.el.append(li);
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
      const stepText = teamStepLabel(msgObj);
      if (stepText) {
        const stepTag = document.createElement('span');
        stepTag.className = 'msg-step-tag';
        stepTag.textContent = stepText;
        meta.append(stepTag);
        wrap.dataset.teamStep = String(msgObj.metadata.team_step);
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
      const effectiveMsg = msgObj || (kind === 'user' || cleanSender === 'user' ? {role: 'user', sender: 'user'} : null);
      renderMessageBody(bubble, text, effectiveMsg);
      // A work request typed in Sohbet: one click opens it as a Workspace task (not sent yet).
      if (msgObj && msgObj.metadata && msgObj.metadata.space_hint === 'work' && typeof window.spesOpenInWorkspace === 'function') {
        const hint = document.createElement('div');
        hint.className = 'space-hint';
        const move = document.createElement('button');
        move.type = 'button';
        move.className = 'space-hint-btn';
        move.textContent = "Workspace'te görev olarak aç";
        move.title = 'Yeni bir Workspace görevi açar ve bu mesajı yazma kutusuna koyar; göndermeden önce bakabilirsin.';
        move.onclick = () => window.spesOpenInWorkspace(text);
        hint.append(move);
        inner.append(hint);
      }
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
    const activeMsgIds = new Set();
    for (const m of messages) {
      if (m && m.id) activeMsgIds.add(m.id);
    }
    for (const key of Array.from(revealedLength.keys())) {
      if (!activeMsgIds.has(key)) revealedLength.delete(key);
    }
    revealSuppressed = replaceAll;  // history appears at once; later arrivals are written out
    if (typeof setCrewResults === 'function') setCrewResults(messages, replaceAll);
    if (typeof setWorkEvidence === 'function') setWorkEvidence(messages, replaceAll);
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
          // Team metadata can arrive after the bubble was first drawn.
          const stepText = teamStepLabel(m);
          let stepEl = wrap.querySelector('.msg-step-tag');
          if (stepText && !stepEl) {
            stepEl = document.createElement('span');
            stepEl.className = 'msg-step-tag';
            tagEl.after(stepEl);
          }
          if (stepEl && stepEl.textContent !== stepText) stepEl.textContent = stepText;
          if (stepText) wrap.dataset.teamStep = String(m.metadata.team_step);
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

    revealSuppressed = false;
    liveRevealArmed = true;
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
    // The status poll pauses during a turn; show a ready repair plan as running meanwhile.
    if (typeof markRepairPlanRunning === 'function') markRepairPlanRunning(!!v);
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
      title.textContent = task.title;
      const meta = document.createElement('div');
      const label = ({completed:'tamamlandı', failed:'başarısız', cancelled:'iptal edildi', running:'çalışıyor',
        pending:'bekliyor', queued:'sırada'})[task.status] || 'durum bilinmiyor';
      meta.textContent = `${done}/${task.steps.length} adım · ${label}`;
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
    if (resp.status === 'ok') appendMsg('bot', 'SPES', resp.data);
    else appendMsg('err', 'HATA', resp.data || 'Bilinmeyen hata');
  }

  async function sendDirect(text) {
    setThinking(true);
    const resp = await window.pywebview.api.send_chat(text);
    setThinking(false);
    renderResponse(resp);
  }

"""
