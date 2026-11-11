"""Quartz advanced JavaScript fragment; composed in the shared application scope."""

JAVASCRIPT = r"""  function addAgentRow(container, title, details, status='') {
    const row = document.createElement('div'); row.className = 'agent-row';
    const head = document.createElement('strong'); head.textContent = title;
    if (status) head.className = status;
    const body = document.createElement('div'); body.textContent = details || '';
    row.append(head, body); container.appendChild(row);
    return row;
  }

  function renderAgentCenter(data) {
    if (!data) return;
    const squad = data.squad || {}, codex = data.codex || {}, antigravity = data.antigravity || {};
    updateAntigravitySafety(antigravity);
    document.getElementById('agentSquadStatus').textContent =
      `${squad.initialized ? 'HAZIR' : 'BAŞLATILMADI'} · ${squad.version || 'sürüm yok'}\n${squad.workspace || ''}`;
    document.getElementById('agentCodexStatus').textContent =
      `${codex.ready ? 'HAZIR' : (codex.authenticated ? 'YÜKLÜ' : 'GİRİŞ GEREKİYOR')} · ${codex.version || ''}\nOturum: ${codex.authentication || 'bilinmiyor'}`;
    document.getElementById('agentGeminiStatus').textContent =
      `${antigravity.ready ? 'HAZIR · ⚠ SINIRLI YALITIM' : (antigravity.installed ? 'GİRİŞ GEREKİYOR' : 'YÜKLÜ DEĞİL')} · ${antigravity.version || ''}\n${antigravity.bridge === 'squad-cli' ? 'Squad CLI köprüsü' : ''}${antigravity.safety_warning ? `\n${antigravity.safety_warning}` : ''}${antigravity.error ? `\n${antigravity.error}` : ''}`;
    const selected = agentProject.value;
    const writer = data.single_writer || {};
    agentProject.innerHTML = '';
    for (const project of (data.projects || [])) {
      const option = document.createElement('option'); option.value = project.id;
      option.textContent = `${project.name} · ${project.squad_initialized ? 'Squad hazır' : 'Squad yok'}`;
      option.selected = project.selected || project.id === selected;
      agentProject.appendChild(option);
    }

    const runs = document.getElementById('agentRuns'); runs.innerHTML = '';
    for (const run of (data.runs || [])) {
      const stateClass = run.status === 'completed' ? 'ok' : (['failed','cancelled'].includes(run.status) ? 'bad' : 'wait');
      const recentErrors = (run.errors || []).slice(-3).join('\n');
      const coordination = run.coordination_status && run.coordination_status !== 'not_linked'
        ? `\nSquad raporu: ${run.coordination_status}` : '';
      const coordinationError = run.coordination_error ? `\nSquad hatası: ${run.coordination_error}` : '';
      const commandEvidence = (run.commands || []).slice(-5).map(command =>
        `\nKomut: ${command.command || '—'} · çıkış: ${command.exit_code ?? 'bilinmiyor'}${command.output ? `\n${command.output.slice(0, 500)}` : ''}`).join('');
      const changedFiles = (run.files_changed || []).length
        ? `\nDeğişen dosyalar:\n${run.files_changed.join('\n')}` : '';
      const checkpoint = run.checkpoint?.ref ? `\nGit checkpoint: ${run.checkpoint.ref}`
        : (run.checkpoint?.warning ? `\nCheckpoint uyarısı: ${run.checkpoint.warning}` : '');
      const evidenceWarning = run.evidence_warning ? `\nDeğişiklik kaydı: ${run.evidence_warning}` : '';
      const row = addAgentRow(runs, `${(run.provider || 'codex').toUpperCase()} · ${run.status.toUpperCase()} · PID ${run.pid || '—'}`,
        `İstenen model: ${run.model || 'eski kayıt / belirtilmemiş'} · ${run.effort || 'belirtilmemiş'}\n${run.sandbox} · ${run.squad_task_id || 'Squad görevi yok'} · çıkış: ${run.exit_code ?? 'bekleniyor'}${coordination}${run.result ? `\n${run.result}` : ''}${commandEvidence}${changedFiles}${checkpoint}${evidenceWarning}${recentErrors ? `\nHata kaydı:\n${recentErrors}` : ''}${coordinationError}`, stateClass);
      if (!['completed','failed','cancelled'].includes(run.status)) {
        const stop = document.createElement('button'); stop.className = 'control-btn'; stop.textContent = 'Durdur';
        stop.onclick = async () => { await window.pywebview.api.agent_center_cancel(run.id); refreshAgentCenter(); };
        row.appendChild(stop);
      }
    }
    for (const collaboration of (data.collaborations || [])) {
      const stateClass = collaboration.status === 'completed' ? 'ok' : (collaboration.status === 'failed' ? 'bad' : 'wait');
      const selectedModels = Object.entries(collaboration.models || {}).map(([agent, cfg]) =>
        `${agent}: ${cfg.model} (${cfg.effort})`).join(' · ');
      addAgentRow(runs, `İŞ BİRLİĞİ · ${collaboration.status.toUpperCase()}`,
        `${selectedModels}\n${collaboration.run_ids.length} çalışma · ${collaboration.messages.length} Squad mesajı${collaboration.result ? `\n${collaboration.result}` : ''}${collaboration.error ? `\nHata: ${collaboration.error}` : ''}`, stateClass);
    }
    if (!runs.children.length) addAgentRow(runs, 'Çalışan ajan yok', 'Yeni görev verdiğinde gerçek PID burada görünür.');

    const tasks = document.getElementById('agentTasks'); tasks.innerHTML = '';
    for (const agent of (data.agents || [])) addAgentRow(tasks, `AJAN · ${agent.id}`, `${agent.role} · ${agent.effective_client_type} · ${agent.status}`);
    for (const task of (data.tasks || [])) {
      const taskResult = task.result ? `\nSonuç: ${String(task.result).slice(0, 600)}` : '';
      addAgentRow(tasks, `${task.status || 'task'} · ${task.title || task.id}`, `${task.assigned_to || 'atanmadı'} · ${task.id}${taskResult}`);
    }
    if (!tasks.children.length) addAgentRow(tasks, 'Kayıt yok', data.error || 'Squad verisi bulunamadı.');

    const history = document.getElementById('agentHistory'); history.innerHTML = '';
    for (const msg of [...(data.history || [])].reverse()) addAgentRow(history, `${msg.from} → ${msg.to}`, `${msg.timestamp}\n${msg.content}`);
    if (!history.children.length) addAgentRow(history, 'Mesaj yok', 'Squad geçmişi boş.');
    agentError.textContent = data.error || (writer.locked ? `Aktif yazıcı: ${writer.agent || writer.owner || 'ajan'}` : '');
  }

  async function refreshAgentCenter() {
    if (!agentOverlay.classList.contains('show')) return;
    try {
      const response = await window.pywebview.api.agent_center_status(agentProject.value || '');
      if (response.status !== 'ok') throw new Error(response.data || 'Ajan durumu alınamadı');
      renderAgentCenter(response.data);
    } catch (error) { agentError.textContent = String(error.message || error); }
  }

  async function pollAgentCenter(token) {
    if (token !== agentPollToken || !agentOverlay.classList.contains('show')) return;
    await refreshAgentCenter();
    setTimeout(() => pollAgentCenter(token), 2500);
  }

  document.getElementById('btnAgentClose').addEventListener('click', () => {
    closeModalOverlay(agentOverlay); agentPollToken++;
  });
  document.getElementById('btnAgentRefresh').addEventListener('click', refreshAgentCenter);
  agentProject.addEventListener('change', refreshAgentCenter);
  agentProvider.addEventListener('change', () => {
    const collaborative = agentProvider.value === 'collaboration';
    agentWrite.disabled = collaborative;
    if (collaborative) agentWrite.value = 'read-only';
  });
  document.getElementById('btnAgentDispatch').addEventListener('click', async () => {
    const prompt = agentPrompt.value.trim();
    if (!prompt) { agentError.textContent = 'Görev açıklaması boş olamaz.'; return; }
    const models = {
      codex: {model: codexModelSelect.value, effort: codexEffortSelect.value},
      antigravity: {model: agyModelSelect.value, effort: agyEffortSelect.value},
    };
    document.getElementById('agentModelSelection').textContent = Object.entries(models)
      .map(([agent, cfg]) => `${agent}: ${cfg.model} (${cfg.effort})`).join(' · ');
    const write = agentWrite.value === 'project';
    const provider = agentProvider.value || 'codex';
    if (write && provider === 'antigravity') {
      agentError.textContent = 'Antigravity için Proje Yetkisiyle yazma Windows güvenlik sınırı doğrulanana kadar kapalı. Codex seç.';
      return;
    }
    if (provider === 'collaboration' && write) {
      agentError.textContent = 'İki ajanlı iş birliği bu sürümde salt-okunur çalışır.'; return;
    }
    if ((provider === 'antigravity' || provider === 'collaboration') && !(await confirmAntigravitySafety())) return;
    let confirmed = false;
    if (write) {
      confirmed = await requestUiConfirm(
        `Bu görev seçili proje dosyalarını değiştirebilir. Tek yazıcı kilidiyle ${provider} ajanına yazma yetkisi verilsin mi?`,
        {title: 'Yazma yetkisi onayı', confirmLabel: 'Yetki ver'}
      );
      if (!confirmed) return;
    }
    const button = document.getElementById('btnAgentDispatch');
    button.disabled = true; agentError.textContent = 'Görev Squad kuyruğuna ekleniyor...';
    try {
      const response = await window.pywebview.api.agent_center_dispatch(
        prompt, prompt.slice(0, 70), agentProject.value || '', write, confirmed, provider,
        models, currentConvId || '');
      if (response.status !== 'ok') throw new Error(response.data || 'Görev başlatılamadı');
      agentPrompt.value = ''; agentError.textContent = `${provider === 'collaboration' ? 'İki ajanlı iş birliği' : provider} başlatıldı.`;
      refreshAgentCenter();
    } catch (error) { agentError.textContent = String(error.message || error); }
    finally { button.disabled = false; }
  });

  let desktopPolling = false;
  const desktopStatus = document.getElementById('desktopOperatorStatus');
  document.getElementById('btnDesktopWindows').addEventListener('click', async () => {
    const response = await window.pywebview.api.desktop_operator_windows();
    if (response.status !== 'ok') { desktopStatus.textContent = response.data; return; }
    const select = document.getElementById('desktopWindow'); select.innerHTML = '';
    for (const target of response.data || []) {
      const option = document.createElement('option'); option.value = target.handle;
      option.textContent = `${target.title} · PID ${target.pid}`; select.appendChild(option);
    }
    desktopStatus.textContent = 'Pencereyi seçin; görev için ayrıca onay istenecek.';
  });
  async function pollDesktopOperator() {
    try {
      const response = await window.pywebview.api.desktop_operator_status();
      const data = response.data || {}; const run = data.run || {};
      desktopStatus.textContent = `${data.session?.active ? 'KONTROL AÇIK' : 'KONTROL KAPALI'} · ${run.status || 'bekliyor'}\n` +
        `${run.model || ''}\n${run.result || ''}\n${(run.errors || []).join('\n')}`;
      if (data.session?.active || ['running','starting','cancelling'].includes(run.status)) {
        setTimeout(pollDesktopOperator, 1000); return;
      }
    } catch (error) { desktopStatus.textContent = String(error); }
    desktopPolling = false;
  }
  document.getElementById('btnDesktopStart').addEventListener('click', async () => {
    const provider = agentProvider.value;
    if (!['codex','antigravity'].includes(provider)) { desktopStatus.textContent = 'Tek operatör seçin: Codex veya Antigravity.'; return; }
    const handle = document.getElementById('desktopWindow').value;
    const prompt = agentPrompt.value.trim();
    if (!handle || !prompt) { desktopStatus.textContent = 'Önce pencere seçin ve görev açıklaması yazın.'; return; }
    const cfg = provider === 'codex' ? {model:codexModelSelect.value,effort:codexEffortSelect.value} : {model:agyModelSelect.value,effort:agyEffortSelect.value};
    if (provider === 'antigravity' && !(await requestUiConfirm(
      'Antigravity Windows istemcisi katı dosya/terminal sandbox garantisi vermiyor. Bu köprü pencere girdisini sınırlar; genel CLI dosya erişimini işletim sistemi düzeyinde yalıtmaz. Bu sınırlamayla yalnız bu masaüstü görevi başlatılsın mı?',
      {title: 'Masaüstü güvenlik uyarısı', confirmLabel: 'Başlat'}
    ))) return;
    if (!(await requestUiConfirm(
      'Bu görev için seçili pencereye ekran okuma ve sınırlı klavye/fare izni verilsin mi? Görüntüler seçili model sağlayıcısına gönderilir. Dosya yazma yetkisi verilmez.',
      {title: 'Masaüstü kontrol izni', confirmLabel: 'İzin ver'}
    ))) return;
    const response = await window.pywebview.api.desktop_operator_start(provider, handle, prompt, cfg.model, cfg.effort, true);
    if (response.status !== 'ok') { desktopStatus.textContent = response.data; return; }
    if (!desktopPolling) { desktopPolling = true; pollDesktopOperator(); }
  });
  document.getElementById('btnDesktopStop').addEventListener('click', async () => {
    if (typeof resolveActiveConfirm === 'function' && activeConfirmResolver) resolveActiveConfirm(false);
    await window.pywebview.api.desktop_operator_stop();
    if (!desktopPolling) { desktopPolling = true; pollDesktopOperator(); }
  });

  function renderProvider(p) {
    if (!p) return;
    const labels = {ready:'HAZIR',checking:'KONTROL',unchecked:'BEKLİYOR',
      degraded:'YAVAŞ/SINIRLI',error:'HATA',missing_key:'ANAHTAR YOK'};
    const latency = p.latency_ms == null ? '—' : `${p.latency_ms} ms`;
    providerStatus.textContent = `${p.provider || '—'} · ${labels[p.status] || p.status}\n${p.model || '—'}\nGecikme: ${latency} · Hata: ${p.failures || 0}` +
      (p.last_error ? `\n${p.last_error}` : '');
  }
  learnOperationBtn.addEventListener('click', () => sendDirect('bu işi öğren'));
  finishOperationBtn.addEventListener('click', () => sendDirect('görevi bitir'));
  // Keyboard access remains available when pointer geometry cannot be captured.
  document.addEventListener('keydown', (e) => {
    if (!e.ctrlKey || e.altKey || e.shiftKey || e.metaKey || e.isComposing || String(e.key).toLowerCase() !== 'l') return;
    if (Array.from(document.querySelectorAll('[aria-modal="true"], dialog[open]')).some(el => el.getClientRects().length > 0)) return;
    if (inputEl.disabled || !inputEl.getClientRects().length) return;
    e.preventDefault();
    inputEl.focus();
  });
  inputEl.addEventListener('keydown', (e) => {
    if (e.isComposing || e.repeat) return;
    if (e.key === 'Enter') { if (e.shiftKey) return; e.preventDefault(); sendAgentMessage(); }
    else if (e.key === 'ArrowUp') {
      if (!inpHistory.length || inputEl.value.includes('\n')) return;
      histCursor = Math.min(histCursor + 1, inpHistory.length - 1);
      inputEl.value = inpHistory[inpHistory.length - 1 - histCursor];
    } else if (e.key === 'ArrowDown') {
      if (inputEl.value.includes('\n')) return;
      if (histCursor <= 0) { histCursor = -1; inputEl.value = ''; return; }
      histCursor--;
      inputEl.value = inpHistory[inpHistory.length - 1 - histCursor];
    }
  });

  document.querySelectorAll('.qa-btn[data-action]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const action = btn.dataset.action;
      appendMsg('sys', '', 'Çalıştırılıyor: ' + btn.textContent.trim());
      setThinking(true);
      const resp = await window.pywebview.api.quick_action(action);
      setThinking(false);
      renderResponse(resp);
    });
  });

  document.getElementById('btnClear').addEventListener('click', async () => {
    chatEl.innerHTML = '';
    msgCount = 0;
    document.getElementById('sessMsgs').textContent = 0;
    await window.pywebview.api.clear_history();
    logLine('Sohbet temizlendi');
  });

  document.getElementById('btnMobile').addEventListener('click', async () => {
    const response = await window.pywebview.api.mobile_access();
    if (response.status !== 'ok') { appendMsg('err', 'HATA', response.data); return; }
    const data = response.data;
    appendMsg('bot', 'MOBİL ERİŞİM', '');
    const bubble = chatEl.lastElementChild.querySelector('.bubble');
    bubble.classList.add('mobile-access-card');
    const addDetail = (label, value, token=false) => {
      const heading = document.createElement('div'); heading.className = 'mobile-label'; heading.textContent = label;
      const content = document.createElement('div'); content.className = `mobile-value${token ? ' mobile-token' : ''}`; content.textContent = value;
      bubble.append(heading, content);
    };
    addDetail('YEREL ADRES', data.local_url);
    addDetail('CİHAZ ANAHTARI', data.token, true);
    addDetail('TAILSCALE YAYINI', data.tailscale_command);
    const copyButton = document.createElement('button');
    copyButton.type = 'button'; copyButton.className = 'mobile-card-action';
    copyButton.textContent = 'ANAHTARI KOPYALA';
    copyButton.onclick = async () => {
      copyButton.disabled = true;
      const result = await window.pywebview.api.copy_mobile_token();
      copyButton.textContent = result.status === 'ok' ? 'KOPYALANDI' : 'KOPYALANAMADI';
      if (result.status !== 'ok') logLine(result.data);
      setTimeout(() => { copyButton.disabled = false; copyButton.textContent = 'ANAHTARI KOPYALA'; }, 1800);
    };
    bubble.appendChild(copyButton);
  });

  let compactMode = false;
  document.getElementById('btnMin').addEventListener('click', async () => {
    compactMode = !compactMode;
    const button = document.getElementById('btnMin');
    try {
      const result = await window.pywebview.api.set_compact(compactMode);
      compactMode = !!result.compact;
      document.body.classList.toggle('compact', compactMode);
      if (compactMode && typeof syncWindowMaximizedUi === 'function') syncWindowMaximizedUi(false);
      button.title = compactMode ? 'Tam arayüze dön' : 'Kompakt sohbete geç';
      inputEl.focus();
    } catch (e) {
      compactMode = !compactMode;
      logLine('Kompakt mod açılamadı: ' + String(e));
    }
  });
  document.getElementById('btnClose').addEventListener('click', () => window.pywebview.api.close());

  // ── Voice: push-to-talk ─────────────────────────────────
  micBtn.addEventListener('click', async () => {
    if (thinking || micBtn.classList.contains('listening')) return;
    micBtn.classList.add('listening');
    setOrb('listening');
    logLine('Dinleniyor (push-to-talk)...');
    try {
      const resp = await window.pywebview.api.push_to_talk();
      micBtn.classList.remove('listening');
      if (resp.transcript) appendMsg('user', 'SEN (sesli)', resp.transcript);
      if (resp.status === 'ok') {
        renderResponse(resp);
        setOrb('idle');
      } else {
        appendMsg('err', 'HATA', resp.data || 'Bilinmeyen hata');
        setOrb('error');
        setTimeout(() => setOrb('idle'), 2000);
      }
    } catch (e) {
      micBtn.classList.remove('listening');
      setOrb('idle');
      appendMsg('err', 'HATA', String(e));
    }
  });

  // ── Voice: wake-word toggle ──────────────────────────────
  wakeBtn.addEventListener('click', async () => {
    const enabling = !wakeBtn.classList.contains('active');
    const r = await window.pywebview.api.toggle_wake_word(enabling);
    if (!r.available) {
      logLine('Mikrofon yok — wake-word açılamadı');
      return;
    }
    wakeBtn.classList.toggle('active', r.enabled);
    document.getElementById('wakeLabel').textContent = `Uyandırma kelimesi: ${r.enabled ? 'açık' : 'kapalı'}`;
    logLine(r.enabled ? '"Hey Quartz" dinleniyor...' : 'Wake-word kapatıldı');
  });

  // ── Voice: TTS toggle ────────────────────────────────────
  ttsBtn.addEventListener('click', async () => {
    ttsEnabled = !ttsEnabled;
    await window.pywebview.api.set_tts_enabled(ttsEnabled);
    ttsBtn.classList.toggle('active', ttsEnabled);
    document.getElementById('ttsLabel').textContent = `Sesli yanıt: ${ttsEnabled ? 'açık' : 'kapalı'}`;
  });

  // ── Voice: callbacks pushed from the Python wake-word thread ──
  window.onWakeDetected = function() {
    setOrb('listening');
    logLine('"Quartz" duyuldu, dinleniyor...');
  };
  window.onWakeTimeout = function() {
    setOrb('idle');
    logLine('Komut algılanamadı.');
  };
  window.onVoiceResult = function(resp) {
    setOrb('idle');
    if (resp.transcript) appendMsg('user', 'SEN (sesli)', resp.transcript);
    renderResponse(resp);
  };

"""
