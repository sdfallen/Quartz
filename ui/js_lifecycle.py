"""Quartz lifecycle JavaScript fragment; composed in the shared application scope."""

JAVASCRIPT = r"""  let lastUserActivityAt = Date.now();
  let lowSpecHardware = false;
  let idleDesktopTick = 0;
  function markUserActivity() { lastUserActivityAt = Date.now(); }
  function isUiHidden() { return !!(document.hidden || document.visibilityState === 'hidden'); }
  function hasActiveDesktopTask() { return !!desktopView.stop_ref; }
  function isUiIdle() {
    return !thinking && !chatPollInterval && !hasActiveDesktopTask() && (typeof hasActiveDiagnosticsJob === 'function' ? !hasActiveDiagnosticsJob() : true) && (Date.now() - lastUserActivityAt > 20000);
  }
  ['mousedown', 'keydown', 'focus'].forEach(ev => window.addEventListener(ev, markUserActivity, { passive: true }));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      markUserActivity();
      pollUiEvents();
    }
  });

  async function pollPing() {
    let nextDelay = 600;
    try {
      nextDelay = isUiHidden() ? 10000 : (isUiIdle() || lowSpecHardware ? 7500 : 5000);
      const r = await window.pywebview.api.ping();
      statusPill.classList.toggle('online', r.online);
      statusPill.classList.toggle('offline', !r.online);
      statusText.textContent = r.online ? 'Çevrimiçi' : 'Çevrimdışı';
      document.getElementById('sessStatus').textContent = r.online ? 'Çevrimiçi' : 'Çevrimdışı';
      if (!r.online) {
        nextDelay = 600;
      } else {
        if (!conversationLoaded) {
          await loadActiveConversation();
        }
        if (r.health && r.health.components) {
          const c = r.health.components;
          renderProvider(c.provider_manager);
          safeMode = !!c.safe_mode;
          safeBtn.classList.toggle('active', safeMode);
          document.getElementById('safeLabel').textContent = `Güvenli mod: ${safeMode ? 'açık' : 'kapalı'}`;
          advisorEnabled = !!(c.screen_advisor && c.screen_advisor.enabled);
          advisorBtn.classList.toggle('active', advisorEnabled);
          document.getElementById('advisorLabel').textContent = `Ekran rehberi: ${advisorEnabled ? 'açık' : 'kapalı'}`;
          const operation = c.operation && c.operation.active;
          if (operation) {
            const actionCount = (operation.actions || []).length;
            operationStatus.textContent = `${operation.root_goal}\n${actionCount} eylem · ${operation.app_context || 'uygulama belirsiz'}`;
            learnOperationBtn.style.display = 'inline-block';
            finishOperationBtn.style.display = 'inline-block';
          } else {
            operationStatus.textContent = 'Operasyon yok';
            learnOperationBtn.style.display = 'none';
            finishOperationBtn.style.display = 'none';
          }
          statusPill.title = `LLM: ${c.llm.status} (${c.llm.provider}) | MCP: ${c.mcp.status} | Vision: ${c.vision.status}`;
        }
      }
    } catch (e) {
      nextDelay = 600;
      statusPill.classList.remove('online');
      statusPill.classList.add('offline');
      statusText.textContent = 'Çevrimdışı';
    } finally {
      setTimeout(pollPing, nextDelay);
    }
  }

  function fillClass(pct) {
    if (pct > 80) return 'crit';
    if (pct > 60) return 'warn';
    return '';
  }
  let statsPollBusy = false;
  async function pollStats() {
    if (!statsPollBusy && !isUiHidden()) {
      statsPollBusy = true;
      try {
        const s = await window.pywebview.api.get_stats();
        if (typeof s.low_spec === 'boolean') {
          lowSpecHardware = s.low_spec;
          document.body.classList.toggle('low-spec', lowSpecHardware);
        }
        for (const [key, id] of [['cpu','cpu'], ['mem','mem'], ['disk','disk']]) {
          const val = s[key] || 0;
          document.getElementById(id + 'Val').textContent = val.toFixed(1) + '%';
          const fill = document.getElementById(id + 'Fill');
          fill.style.width = Math.min(100, val) + '%';
          fill.className = 'stat-fill ' + fillClass(val);
        }
      } catch (e) { /* ignore */ }
      finally { statsPollBusy = false; }
    }
    const statsDelay = isUiHidden() ? 10000 : (isUiIdle() || lowSpecHardware ? 6000 : 3000);
    setTimeout(pollStats, statsDelay);
  }

  let tasksPollBusy = false;
  async function pollTasks() {
    if (!tasksPollBusy && !isUiHidden()) {
      tasksPollBusy = true;
      try {
        const response = await window.pywebview.api.tasks();
        if (response.status === 'ok') renderTasks(response.data || []);
      } catch (e) { /* ignore */ }
      finally { tasksPollBusy = false; }
    }
    const tasksDelay = isUiHidden() ? 12000 : (isUiIdle() || lowSpecHardware ? 9000 : 6000);
    setTimeout(pollTasks, tasksDelay);
  }

  let uiEventsPollBusy = false;
  async function pollUiEvents() {
    document.body.classList.toggle('ui-idle', isUiIdle());
    if (!uiEventsPollBusy) {
      uiEventsPollBusy = true;
      try {
        idleDesktopTick = (idleDesktopTick + 1) % 2;
        if (hasActiveDesktopTask() || !isUiIdle() || idleDesktopTick === 0) {
          await refreshDesktopTaskState();
        }
        const response = await window.pywebview.api.ui_events();
        if (response.status === 'ok') renderUiEvents(response.data || []);
        if (!chatPollInterval && (!isUiIdle() || !conversationLoaded || idleDesktopTick === 0)) {
          const st = await window.pywebview.api.chat_status();
          if (st.status === 'ok' && st.data) {
            updateAntigravitySafety(st.data.agents?.antigravity);
            if (st.data.squad) updateSquadBadge(st.data.squad, st.data.active_conversation?.id);
            const conv = st.data.active_conversation;
            if (conv) {
              const switched = currentConvId !== conv.id;
              currentConvId = conv.id;
              renderConversationNavigation(st.data.conversations || []);
              chatConvTitle.textContent = conv.title || 'Yeni Sohbet';
              if (conv.agent) syncAgentUI(conv.agent);
              syncModelCatalogAndSelection(st.data.models, conv.models);
              if (switched) {
                const permSelect = document.getElementById('mainPermissionLevel');
                if (permSelect) {
                  permSelect.value = conv.permission_level || st.data.preferences?.permission_level || 'full';
                  updatePermissionSelectionHint();
                  window.__writeConfirmed = true;
                }
              }
              if (Array.isArray(conv.messages) && conv.messages.length > 0) {
                syncConversationMessages(conv.messages, switched);
              } else if (switched) {
                await loadActiveConversation();
              }
            }
            if (st.data.active_turn && (st.data.active_turn.status === 'running' ||
                (typeof chatCleanupUnconfirmed === 'function' && chatCleanupUnconfirmed(st.data.active_turn.stop_receipt)))) {
              if (!thinking) setThinking(true);
              await pollAgentTurn();
            } else if (thinking && !(typeof chatSubmissionBusy !== 'undefined' && chatSubmissionBusy) &&
                       !(typeof chatCleanupUnconfirmed === 'function' && chatCleanupUnconfirmed())) {
              setThinking(false);
            }
          }
        }
        if (hasActiveDesktopTask() || !isUiIdle() || idleDesktopTick === 0) {
          await pollNaturalTask();
        }
      } catch (_) { /* backend may still be starting */ }
      finally { uiEventsPollBusy = false; }
    }
    const uiDelay = (isUiHidden() && !thinking && !hasActiveDesktopTask())
      ? 4500
      : (isUiIdle() ? (lowSpecHardware ? 3200 : 2200) : (lowSpecHardware ? 1800 : 1200));
    setTimeout(pollUiEvents, uiDelay);
  }

  window.addEventListener('pywebviewready', async () => {
    const welcome = appendMsg('bot', 'QUARTZ', 'Merhaba! Ben Quartz. Doğrudan Antigravity ve Codex ajanlarıyla çalışıyorum.\nÜstteki seçiciden Antigravity, Codex veya Birlikte modunu seçip mesaj gönderebilirsin.', '', 'quartz');
    welcome.dataset.welcome = '1';
    logLine('Quartz UI başlatıldı');
    await loadActiveConversation();
    pollPing();
    pollStats();
    pollTasks();
    pollUiEvents();
    checkApiSetup();
    updatePermissionSelectionHint();
    window.__writeConfirmed = true;
    inputEl.focus();
    try {
      const perms = await window.pywebview.api.tool_permissions();
      const box = document.getElementById('pluginPermissions');
      box.innerHTML = '';
      for (const group of (perms.data || []).filter(x => x.source.startsWith('plugin:'))) {
        const btn = document.createElement('button'); btn.className = 'control-btn';
        btn.textContent = `${group.enabled ? '✓' : '○'} ${group.source.replace('plugin:','')}`;
        btn.onclick = async () => {
          await window.pywebview.api.set_tool_source(group.source, !group.enabled);
          group.enabled = !group.enabled;
          btn.textContent = `${group.enabled ? '✓' : '○'} ${group.source.replace('plugin:','')}`;
        };
        box.appendChild(btn);
      }
      // Voice is a legacy advanced feature: do not initialize microphone/TTS
      // merely by opening the development workspace.
      document.getElementById('btnPanels').addEventListener('click', async () => {
      if (window.__voiceChecked) return; window.__voiceChecked = true;
      const v = await window.pywebview.api.voice_status();
      if (!v.mic) {
        micBtn.classList.add('disabled');
        micBtn.title = 'Mikrofon bulunamadı';
        wakeBtn.classList.add('disabled');
        logLine('Mikrofon bulunamadı — sesli komut devre dışı');
      }
      if (!v.tts) {
        ttsEnabled = false;
        ttsBtn.classList.remove('active');
        document.getElementById('ttsLabel').textContent = 'Sesli yanıt: kapalı';
        logLine('TTS motoru bulunamadı');
      }
      });
    } catch (e) { /* ignore */ }
  });
"""
