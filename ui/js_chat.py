"""Quartz chat JavaScript fragment; composed in the shared application scope."""

JAVASCRIPT = r"""  // ── Agent Chat & Model Selection Integration ────────────
  let conversationLoaded = false;
  const btnPanels = document.getElementById('btnPanels');
  const agyModelPill = document.getElementById('agyModelPill');
  const codexModelPill = document.getElementById('codexModelPill');
  const agyModelSelect = document.getElementById('agyModelSelect');
  const agyEffortSelect = document.getElementById('agyEffortSelect');
  const codexModelSelect = document.getElementById('codexModelSelect');
  const codexEffortSelect = document.getElementById('codexEffortSelect');
  const btnContinueCollab = document.getElementById('btnContinueCollab');

  if (btnPanels) {
    btnPanels.addEventListener('click', () => {
      const shown = document.body.classList.toggle('show-panels');
      btnPanels.classList.toggle('active', shown);
    });
  }

  function populateSelectOptions(selectEl, items, valueKey='id', labelKey='label') {
    if (!selectEl || !Array.isArray(items) || !items.length) return;
    if (document.activeElement === selectEl) return;
    const prevValue = selectEl.value;
    const sig = items.map(it => typeof it === 'string' ? it : `${it[valueKey]}:${it[labelKey]}`).join('|');
    if (selectEl.dataset.optionsSig === sig) return;
    selectEl.dataset.optionsSig = sig;
    selectEl.innerHTML = '';
    for (const item of items) {
      const opt = document.createElement('option');
      if (typeof item === 'string') {
        opt.value = item;
        opt.textContent = item;
      } else {
        opt.value = item[valueKey];
        opt.textContent = item[labelKey] || item[valueKey];
        if (item.description) opt.title = item.description;
      }
      selectEl.appendChild(opt);
    }
    if (prevValue && Array.from(selectEl.options).some(o => o.value === prevValue)) {
      selectEl.value = prevValue;
    }
  }

  function syncModelCatalogAndSelection(modelsCatalog, convModels) {
    if (modelsCatalog) {
      if (modelsCatalog.antigravity) {
        populateSelectOptions(agyModelSelect, modelsCatalog.antigravity.models || []);
        populateSelectOptions(agyEffortSelect, modelsCatalog.antigravity.efforts || []);
      }
      if (modelsCatalog.codex) {
        populateSelectOptions(codexModelSelect, modelsCatalog.codex.models || []);
        populateSelectOptions(codexEffortSelect, modelsCatalog.codex.efforts || []);
      }
    }
    if (convModels) {
      if (convModels.antigravity) {
        if (agyModelSelect && document.activeElement !== agyModelSelect && convModels.antigravity.model) {
          if (!Array.from(agyModelSelect.options).some(o => o.value === convModels.antigravity.model)) {
            const extra = document.createElement('option');
            extra.value = convModels.antigravity.model;
            extra.textContent = convModels.antigravity.model;
            agyModelSelect.appendChild(extra);
          }
          agyModelSelect.value = convModels.antigravity.model;
        }
        if (agyEffortSelect && document.activeElement !== agyEffortSelect && convModels.antigravity.effort) {
          agyEffortSelect.value = convModels.antigravity.effort;
        }
      }
      if (convModels.codex) {
        if (codexModelSelect && document.activeElement !== codexModelSelect && convModels.codex.model) {
          if (!Array.from(codexModelSelect.options).some(o => o.value === convModels.codex.model)) {
            const extra = document.createElement('option');
            extra.value = convModels.codex.model;
            extra.textContent = convModels.codex.model;
            codexModelSelect.appendChild(extra);
          }
          codexModelSelect.value = convModels.codex.model;
        }
        if (codexEffortSelect && document.activeElement !== codexEffortSelect && convModels.codex.effort) {
          codexEffortSelect.value = convModels.codex.effort;
        }
      }
    }
  }

  async function saveAgentModelSelection(agent, changedFromModelSelect=false) {
    if (!currentConvId) return;
    let modelVal = '';
    let effortVal = '';
    if (agent === 'antigravity') {
      modelVal = agyModelSelect ? agyModelSelect.value : '';
      if (changedFromModelSelect && agyEffortSelect && modelVal) {
        for (const eff of ['low', 'medium', 'high', 'xhigh', 'max']) {
          if (modelVal.endsWith('-' + eff)) {
            agyEffortSelect.value = eff;
            break;
          }
        }
      }
      effortVal = agyEffortSelect ? agyEffortSelect.value : '';
    } else if (agent === 'codex') {
      modelVal = codexModelSelect ? codexModelSelect.value : '';
      effortVal = codexEffortSelect ? codexEffortSelect.value : '';
    }
    try {
      await window.pywebview.api.chat_set_model(currentConvId, agent, modelVal, effortVal);
      logLine(`${agent.toUpperCase()} modeli güncellendi: ${modelVal} (${effortVal})`);
    } catch (e) {
      logLine(`Model kaydetme hatası: ${e}`);
    }
  }

  if (agyModelSelect) agyModelSelect.addEventListener('change', () => saveAgentModelSelection('antigravity', true));
  if (agyEffortSelect) agyEffortSelect.addEventListener('change', () => saveAgentModelSelection('antigravity', false));
  if (codexModelSelect) codexModelSelect.addEventListener('change', () => saveAgentModelSelection('codex', true));
  if (codexEffortSelect) codexEffortSelect.addEventListener('change', () => saveAgentModelSelection('codex', false));

  function syncAgentUI(agent) {
    if (!agent) return;
    // Old Notion conversations stay readable; the next turn uses a supported agent.
    if (!['codex', 'antigravity', 'collaboration'].includes(agent)) agent = 'codex';
    if (mainAgentSelect) mainAgentSelect.value = agent;
    document.querySelectorAll('.agent-seg-btn[data-agent]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.agent === agent);
    });
    const isCollab = agent === 'collaboration';
    if (agyModelPill) {
      agyModelPill.classList.toggle('active-agy', agent === 'antigravity' || isCollab);
    }
    if (codexModelPill) {
      codexModelPill.classList.toggle('active-codex', agent === 'codex' || isCollab);
    }
    if (btnContinueCollab) {
      btnContinueCollab.style.display = isCollab ? 'inline-block' : 'none';
    }
    renderAgentConnections(undefined, agent);
  }

  document.querySelectorAll('.agent-seg-btn[data-agent]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const agent = btn.dataset.agent;
      syncAgentUI(agent);
      if (currentConvId) {
        await window.pywebview.api.chat_set_agent(currentConvId, agent);
      }
      logLine('Aktif ajan değiştirildi: ' + agent.toUpperCase());
    });
  });

  if (btnContinueCollab) {
    btnContinueCollab.addEventListener('click', async () => {
      if (thinking || !currentConvId) return;
      try {
        setThinking(true);
        thinkingText.textContent = 'Ajanlar tartışmayı 1 tur daha sürdürüyor...';
        const resp = await window.pywebview.api.chat_continue(currentConvId);
        if (resp.status !== 'ok') {
          setThinking(false);
          appendMsg('err', 'HATA', resp.data || 'Tartışma sürdürülemedi');
          return;
        }
        await pollAgentTurn();
        if (chatPollInterval) clearInterval(chatPollInterval);
        chatPollInterval = setInterval(pollAgentTurn, 120);
      } catch (e) {
        setThinking(false);
        logLine('Tartışma sürdürme hatası: ' + String(e));
      }
    });
  }

  let writerRecoveryKey = '';
  function renderWriterRecovery(data) {
    data = data || {};
    const key = JSON.stringify(data); if (key === writerRecoveryKey) return;
    writerRecoveryKey = key;
    const panel = document.getElementById('writerRecoveryPanel');
    const body = document.getElementById('writerRecoveryBody');
    panel.hidden = !data.blocked; body.replaceChildren();
    if (data.error) { const text=document.createElement('p'); text.textContent='Yazıcı kaydı okunamıyor: '+data.error; body.append(text); }
    for (const claim of data.claims || []) {
      const row=document.createElement('div'); const label=document.createElement('p');
      label.textContent=`${claim.provider || 'Ajan'} · ${claim.project} · ${claim.stage}`;
      const inspect=document.createElement('button'); inspect.className='control-btn'; inspect.textContent='Süreç durumunu incele';
      const details=document.createElement('pre'); details.style.whiteSpace='pre-wrap';
      const confirmation=document.createElement('label'); const check=document.createElement('input'); check.type='checkbox';
      confirmation.append(check,document.createTextNode('Harici süreçleri ve dosya durumunu kontrol ettim.'));
      const ack=document.createElement('button'); ack.className='control-btn'; ack.textContent='İncelemeyi onayla; engeli kaldır'; ack.disabled=true;
      let inspected=false; check.onchange=()=>{ ack.disabled=!inspected || !check.checked; };
      inspect.onclick=async()=>{
        const result=await window.pywebview.api.writer_recovery_inspect(claim.id);
        details.textContent=JSON.stringify(result.data,null,2); inspected=result.status==='ok';
        ack.disabled=!inspected || !check.checked;
      };
      ack.onclick=async()=>{
        if (!inspected || !check.checked || !window.confirm('Eski görev yeniden çalıştırılmayacak; izin verilmeyecek. Harici etkinliği kontrol ettiyseniz yalnız engel kaydını kaldırın.')) return;
        const result=await window.pywebview.api.writer_recovery_acknowledge(claim.id,true,true);
        if (result.status!=='ok') { details.textContent=String(result.data); return; }
        await loadActiveConversation();
      };
      row.append(label,inspect,details,confirmation,ack); body.append(row);
    }
  }

  function agentProgressText(progress) {
    const names={codex:'Codex',antigravity:'Antigravity'};
    const states={running:'çalışıyor',completed:'tamamlandı',failed:'başarısız',cancelling:'durduruluyor',cancelled:'durduruldu'};
    return Object.entries(progress || {}).filter(([key])=>key in names)
      .map(([key,value])=>`${names[key]}: ${states[value.status] || 'hazırlanıyor'}${value.status==='running' && value.step ? ' — '+value.step : ''}`).join(' | ');
  }

  async function loadActiveConversation() {
    try {
      const resp = await window.pywebview.api.chat_status();
      if (resp.status !== 'ok') return false;
      const data = resp.data;
      renderWriterRecovery(data.writer_recovery);
      document.getElementById('responseDetail').value = data.preferences?.response_detail || 'short';
      savedResponseDetail = document.getElementById('responseDetail').value;
      updateAntigravitySafety(data.agents?.antigravity);
      if (data.squad) updateSquadBadge(data.squad, data.active_conversation?.id);
      const conv = data.active_conversation;
      const projects = Array.isArray(data.projects) ? data.projects : [];
      mainProjectSelect.replaceChildren();
      for (const project of projects) {
        const option = document.createElement('option');
        option.value = project.id;
        option.textContent = project.name;
        option.title = project.path;
        mainProjectSelect.append(option);
      }
      if (!conv) return false;
      conversationLoaded = true;
      currentConvId = conv.id;
      renderConversationNavigation(data.conversations || []);
      chatConvTitle.textContent = conv.title || 'Yeni Sohbet';
      if (conv.agent) syncAgentUI(conv.agent);
      syncModelCatalogAndSelection(data.models, conv.models);
      const activeProjectId = conv.project_id || 'squad-pilot';
      mainProjectSelect.value = activeProjectId;
      if (chatProjectTag) chatProjectTag.textContent = projects.find(p => p.id === activeProjectId)?.name || activeProjectId;
      const permSelect = document.getElementById('mainPermissionLevel');
      if (permSelect) {
        permSelect.value = conv.permission_level || data.preferences?.permission_level || 'full';
        updatePermissionSelectionHint();
        window.__writeConfirmed = true;
      }
      const writer = data.single_writer || {};
      writerBadge.style.display = writer.locked ? 'inline-block' : 'none';
      writerBadge.textContent = writer.locked ? `Yazıcı: ${writer.agent || 'ajan'}` : '';

      // Sohbet mesajlarını render et
      chatEl.innerHTML = '';
      userPinnedToBottom = true;
      unreadWhileScrolledUp = 0;
      updateJumpBottomBtn();
      if (!conv.messages || !conv.messages.length) {
        const welcome = appendMsg('bot', 'QUARTZ', 'Merhaba! Ben Quartz. Doğrudan Antigravity ve Codex ajanlarıyla çalışıyorum.\nÜstteki seçiciden Antigravity, Codex veya Birlikte modunu seçip mesaj gönderebilirsin.', '', 'quartz');
        welcome.dataset.welcome = '1';
      } else {
        syncConversationMessages(conv.messages, true);
      }
      return true;
    } catch (e) {
      logLine('Sohbet yüklenemedi: ' + String(e));
      return false;
    }
  }

  let chatPollBusy = false;
  async function pollAgentTurn() {
    if (chatPollBusy) return;
    chatPollBusy = true;
    try {
      const poll = await window.pywebview.api.chat_poll();
      if (poll.status !== 'ok') return;
      const data = poll.data;
      if (!data) return;
      const writer = data.single_writer || {};
      writerBadge.style.display = writer.locked ? 'inline-block' : 'none';
      writerBadge.textContent = writer.locked ? `Yazıcı: ${writer.agent || 'ajan'}` : '';

      if (Array.isArray(data.messages) && data.messages.length > 0) {
        syncConversationMessages(data.messages, false);
      } else if (activeBotBubble && data.content) {
        const prevScrollTop = chatEl.scrollTop;
        renderMessageBody(activeBotBubble, data.content, {metadata:data.metadata});
        if (userPinnedToBottom) scrollToBottom(true);
        else chatEl.scrollTop = prevScrollTop;
      }

      if (data.metadata) {
        if (Object.keys(data.agent_progress || {}).length) {
          thinkingText.textContent = agentProgressText(data.agent_progress);
        } else if (data.metadata.progress_step) {
          thinkingText.textContent = data.metadata.progress_step;
        } else if (Array.isArray(data.metadata.progress) && data.metadata.progress.length > 0) {
          thinkingText.textContent = data.metadata.progress[data.metadata.progress.length - 1];
        }
      }

      // İşlem aktif değilse (tamamlandı / iptal / hata) en son metin işlendikten sonra polling'i kapat
      if (!data.active) {
        if (chatPollInterval) {
          clearInterval(chatPollInterval);
          chatPollInterval = null;
        }
        setThinking(false);
        activeBotBubble = null;
      }
    } catch (_) {}
    finally { chatPollBusy = false; }
  }

  let savedResponseDetail = 'short';
  document.getElementById('responseDetail').addEventListener('change', async (event) => {
    const selected = event.target.value;
    try {
      const result = await window.pywebview.api.chat_response_detail(selected);
      if (result.status !== 'ok') throw new Error(result.data || 'Ayar kaydedilemedi');
      savedResponseDetail = selected;
      document.querySelectorAll('.technical-details').forEach(item => { item.open = selected === 'technical'; });
    } catch (error) {
      event.target.value = savedResponseDetail;
      logLine('Yanıt ayrıntısı kaydedilemedi: ' + String(error));
    }
  });

  btnNewChat.addEventListener('click', async () => {
    try {
      if (chatPollInterval) {
        clearInterval(chatPollInterval);
        chatPollInterval = null;
      }
      setThinking(false);
      activeBotBubble = null;
      const agent = mainAgentSelect.value || 'antigravity';
      const resp = await window.pywebview.api.chat_new('Yeni Sohbet', agent, mainProjectSelect.value);
      if (resp.status === 'ok') {
        await loadActiveConversation();
        logLine('Yeni sohbet başlatıldı.');
      }
    } catch (e) { logLine('Hata: ' + String(e)); }
  });

  mainProjectSelect.addEventListener('change', async () => {
    const response = await window.pywebview.api.project_select(mainProjectSelect.value);
    if (response.status !== 'ok') {
      logLine('Proje değiştirilemedi: ' + response.data);
    }
    await loadActiveConversation();
  });

  btnAddProject.addEventListener('click', async () => {
    btnAddProject.disabled = true;
    try {
      const response = await window.pywebview.api.project_pick_add();
      if (response.status === 'ok') await loadActiveConversation();
      else if (response.status !== 'cancelled') logLine('Proje eklenemedi: ' + response.data);
    } catch (error) { logLine('Proje eklenemedi: ' + String(error)); }
    finally { btnAddProject.disabled = false; }
  });

  mainAgentSelect.addEventListener('change', async () => {
    const agent = mainAgentSelect.value;
    syncAgentUI(agent);
    if (!currentConvId) return;
    await window.pywebview.api.chat_set_agent(currentConvId, agent);
    logLine('Aktif ajan değiştirildi: ' + agent.toUpperCase());
  });

  cancelBtn.addEventListener('click', async () => {
    cancelBtn.disabled = true;
    thinkingText.textContent = 'iptal ediliyor...';
    try {
      await window.pywebview.api.chat_cancel();
      await window.pywebview.api.cancel_request();
    } catch (_) {}
    setTimeout(() => { cancelBtn.disabled = false; setThinking(false); }, 1000);
  });

  function updatePermissionSelectionHint() {
    const select=document.getElementById('mainPermissionLevel');
    const hint=document.getElementById('permissionSelectionHint');
    const labels={'read-only':'Tam Yetki',project:'Proje Yetkisi',full:'◉ Tam Yetki Aktif'};
    const level=select?.value || 'full';
    if(hint){hint.textContent=`${labels[level] || labels['full']}`;
      hint.title='Tek Yetki Sistemi (Tam Yetki) kalıcı olarak aktiftir.';}
    window.__writeConfirmed=false;
  }
  const permissionSelect=document.getElementById('mainPermissionLevel');
  if(permissionSelect){permissionSelect.addEventListener('change',updatePermissionSelectionHint);updatePermissionSelectionHint();}

  let coordinationRouting = false;
  window.__writeConfirmed = true;
  async function sendAgentMessage() {
    const text = inputEl.value.trim();
    if (!text || coordinationRouting) return;
    // Freeze the selected mode for THIS submitted message, not a later poll
    // or a dropdown edit while routing is awaiting the backend.
    const selectedPermissionLevel=document.getElementById('mainPermissionLevel')?.value || 'read-only';
    coordinationRouting = true;
    const wasThinking = typeof thinking !== 'undefined' ? thinking : false;
    if (!wasThinking && typeof setThinking === 'function') {
      setThinking(true);
      if (typeof thinkingText !== 'undefined' && thinkingText) thinkingText.textContent = 'Görev hazırlanıyor...';
    }
    const submittedAgent = mainAgentSelect?.value || 'antigravity';
    let coordinated;
    try { coordinated = await window.pywebview.api.coordination_route(text, currentConvId, mainProjectSelect.value,
      {codex:{model:codexModelSelect.value,effort:codexEffortSelect.value},antigravity:{model:agyModelSelect.value,effort:agyEffortSelect.value}},selectedPermissionLevel, submittedAgent); }
    catch(e) { appendMsg('err','QUARTZ',String(e)); return; }
    finally {
      coordinationRouting = false;
      if (!wasThinking && typeof setThinking === 'function') setThinking(false);
    }
    if (coordinated.status !== 'ok') { appendMsg('err','QUARTZ',coordinated.data); return; }
    if (coordinated.data?.handled) {
      inputEl.value = '';
      if (coordinated.data.diagnostics_repair) {
        appendMsg('user', 'SEN', coordinated.data.user_text, '', 'user', null, false, true);
        renderRepairPlan(coordinated.data.repair_plan);
        return;
      }
      if (coordinated.data.diagnostics_knowledge) {
        appendMsg('user', 'SEN', coordinated.data.user_text, '', 'user', null, false, true);
        if (typeof renderLearnedApplicationsCard === 'function') {
          renderLearnedApplicationsCard(coordinated.data.learned_items || []);
        }
        return;
      }
      if (coordinated.data.diagnostics_started || coordinated.data.diagnostics_cancelled || coordinated.data.diagnostics_status) {
        if (coordinated.data.user_text && typeof appendMsg === 'function') appendMsg('user', 'SEN', coordinated.data.user_text, '', 'user', null, false, true);
        const diagJob = coordinated.data.diagnostics || coordinated.data.diagnostics_status;
        if (!diagJob) appendMsg('bot', 'QUARTZ', 'Dosya seçimi iptal edildi; inceleme başlatılmadı.');
        if (typeof renderSelfDiagnosticsCard === 'function' && diagJob) renderSelfDiagnosticsCard(diagJob);
        if (typeof scheduleSelfDiagnosticsPoll === 'function' && diagJob?.state === 'running' && diagJob?.id) scheduleSelfDiagnosticsPoll(diagJob.id);
        return;
      }
      if(coordinated.data.permission_status || coordinated.data.desktop_help || coordinated.data.continuation_status) await loadActiveConversation();
      else if(!coordinated.data.natural_started) appendMsg('bot','QUARTZ',coordinated.data.stopped ? 'Görev durduruldu.' : 'Talimat iletildi; yetki kapsamı değişmedi.');
      await refreshDesktopTaskState();
      await pollNaturalTask();
      return;
    }
    if (thinking) return;

    const writeSelect = document.getElementById('mainPermissionLevel');
    const conversationOnly = coordinated.data?.intent === 'conversation';
    const permissionLevel = conversationOnly ? 'read-only' : selectedPermissionLevel;
    const isWrite = permissionLevel === 'full' || permissionLevel === 'project';
    const confirmWrite = isWrite;
    const agent = submittedAgent;
    if (isWrite && !window.__writeConfirmed) {
      const ok = window.confirm(permissionLevel === 'full'
        ? 'Bu görev için TAM sistem erişimi verilsin mi? Ajan proje dışındaki dosyalara da erişebilir. Yazma öncesi proje checkpoint’i alınır; bu tüm bilgisayarın yedeği değildir.'
        : 'Bu görev için proje dosyalarını değiştirme yetkisi verilsin mi? Önce checkpoint alınır. Birlikte modunda Codex yazar, Antigravity inceleme yapar.');
      if (!ok) return;
      window.__writeConfirmed = true;
    }

    inputEl.value = '';
    inpHistory.push(text);
    histCursor = -1;
    msgCount++;
    document.getElementById('sessMsgs').textContent = msgCount;

    chatEl.querySelectorAll('[data-welcome="1"]').forEach(el => el.remove());
    const userWrap = appendMsg('user', 'SEN', text, '', 'user', null, false, true);
    setThinking(true);

    logLine(`Ajan (${agent.toUpperCase()}) göreve başladı...`);

    const initialSender = agent === 'collaboration' ? 'codex' : agent;
    const initialLabel = agent === 'collaboration' ? 'CODEX · GRUP' : agent.toUpperCase();
    const botWrap = appendMsg('bot', initialLabel, '...', '', initialSender, null, false, true);
    activeBotBubble = botWrap.querySelector('.bubble');

    try {
      const resp = await window.pywebview.api.chat_send(text, agent, currentConvId, isWrite, confirmWrite, permissionLevel, selectedPermissionLevel);
      if (resp.status !== 'ok') {
        setThinking(false);
        activeBotBubble.textContent = 'Hata: ' + (resp.data || 'Bilinmeyen hata');
        setOrb('error');
        setTimeout(() => setOrb('idle'), 2500);
        return;
      }
      if (resp.data) {
        if (resp.data.conversation_id) currentConvId = resp.data.conversation_id;
        if (resp.data.user_message && resp.data.user_message.id) {
          userWrap.dataset.msgId = resp.data.user_message.id;
        }
        if (resp.data.assistant_message && resp.data.assistant_message.id) {
          botWrap.dataset.msgId = resp.data.assistant_message.id;
          const firstMsg = resp.data.assistant_message;
          const tagEl = botWrap.querySelector('.msg-sender-tag');
          if (tagEl && firstMsg.sender) {
            tagEl.className = `msg-sender-tag tag-${firstMsg.sender}`;
            tagEl.textContent = formatMessageLabel(firstMsg);
          }
        }
      }
      await pollAgentTurn();
      if (chatPollInterval) clearInterval(chatPollInterval);
      chatPollInterval = setInterval(pollAgentTurn, 120);
    } catch (e) {
      setThinking(false);
      activeBotBubble.textContent = 'Hata: ' + String(e);
    }
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || thinking) return;
    inputEl.value = '';
    inpHistory.push(text);
    histCursor = -1;
    msgCount++;
    document.getElementById('sessMsgs').textContent = msgCount;
    appendMsg('user', 'SEN', text);
    setThinking(true);
    logLine('Gönderildi: ' + text.slice(0, 50));
    try {
      const resp = await window.pywebview.api.send_chat(text);
      setThinking(false);
      if (resp.status === 'ok') {
        renderResponse(resp);
        logLine('Yanıt alındı (' + resp.data.length + ' karakter)');
      } else {
        appendMsg('err', 'HATA', resp.data || 'Bilinmeyen hata');
        setOrb('error');
        logLine('HATA: ' + (resp.data || '').slice(0, 50));
        setTimeout(() => setOrb('idle'), 2000);
      }
    } catch (e) {
      setThinking(false);
      appendMsg('err', 'HATA', String(e));
    }
  }

  sendBtn.addEventListener('click', sendAgentMessage);

  let navigationConversations = [];
  let deletionPending = false;
  async function requestChatDeletion(conversations, projectId = null) {
    if (deletionPending || thinking || !conversations.length) return;
    const projectName = mainProjectSelect.selectedOptions[0]?.textContent || 'Seçili proje';
    const message = projectId
      ? `“${projectName}” projesinin ${conversations.length} sohbeti silinsin mi?`
      : `“${conversations[0].title || 'Yeni sohbet'}” sohbeti silinsin mi?`;
    if (!window.confirm(message + '\nProje dosyaları silinmez. Sohbetlerin yerel kurtarma yedeği tutulur.')) return;
    deletionPending = true;
    try {
      const result = projectId
        ? await window.pywebview.api.chat_delete_project(projectId, conversations.map(c => c.id), true)
        : await window.pywebview.api.chat_delete(conversations[0].id, true);
      if (result.status !== 'ok') throw new Error(result.data || 'Sohbet silinemedi');
      if (chatPollInterval) { clearInterval(chatPollInterval); chatPollInterval = null; }
      activeBotBubble = null;
      await loadActiveConversation();
      logLine(`${result.data.deleted_count} sohbet silindi; yerel kurtarma yedeği oluşturuldu.`);
    } catch (error) {
      appendMsg('err', 'QUARTZ', String(error));
    } finally { deletionPending = false; }
  }

  function renderConversationNavigation(items) {
    const list=document.getElementById('conversationList'); if(!list)return;
    navigationConversations = items || [];
    const key=JSON.stringify([currentConvId,(items||[]).map(c=>[c.id,c.title,c.project_id])]);
    if(list.dataset.key===key)return;list.dataset.key=key;
    const top=list.scrollTop;list.replaceChildren();
    for(const conv of items||[]){
      const row=document.createElement('div');row.className='conversation-row';
      const button=document.createElement('button');button.className='conversation-entry'+(conv.id===currentConvId?' active':'');
      button.textContent=conv.title||'Yeni sohbet';button.title=button.textContent;
      button.onclick=async()=>{if(thinking||deletionPending)return;const result=await window.pywebview.api.chat_select(conv.id);if(result.status==='ok')await loadActiveConversation();};
      const remove=document.createElement('button');remove.className='conversation-delete';remove.textContent='×';
      remove.title='Sohbeti sil';remove.setAttribute('aria-label',`${button.textContent} sohbetini sil`);
      remove.onclick=()=>requestChatDeletion([conv]);row.append(button,remove);list.append(row);
    }
    list.scrollTop=top;
  }

  function initializeWorkspaceLayout() {
    const left=document.querySelector('.rail.left'), right=document.querySelector('.rail.right');
    const old=document.createElement('details');old.id='legacyTools';
    const summary=document.createElement('summary');summary.textContent='Eski araçlar ve gelişmiş teşhis';old.append(summary);
    [...left.children].forEach(item=>old.append(item));right.append(old);
    for(const id of ['btnWake','btnTts'])old.append(document.getElementById(id));
    const heading=document.createElement('div');heading.className='workspace-nav-title';heading.textContent='Çalışma alanı';
    const project=document.createElement('div');project.className='workspace-project';project.append(mainProjectSelect,document.getElementById('btnAddProject'));
    const newChat=document.createElement('button');newChat.className='conversation-entry';newChat.textContent='＋ Yeni sohbet';newChat.onclick=()=>document.getElementById('btnNewChat').click();
    const title=document.createElement('div');title.className='workspace-nav-title';title.textContent='Sohbetler';
    const clearProject=document.createElement('button');clearProject.id='btnDeleteProjectChats';
    clearProject.className='project-chats-delete';clearProject.textContent='Bu projenin sohbetlerini temizle';
    clearProject.onclick=()=>requestChatDeletion(navigationConversations.filter(c=>(c.project_id||'squad-pilot')===mainProjectSelect.value),mainProjectSelect.value);
    const history=document.createElement('div');history.id='conversationList';history.className='conversation-list';
    const setting=document.getElementById('responseDetail').closest('.card');
    const agentsTitle=document.createElement('div');agentsTitle.className='workspace-nav-title';agentsTitle.id='agentConnectionsTitle';agentsTitle.textContent='Ajanlar';
    const agents=document.createElement('div');agents.id='agentConnections';agents.className='agent-connections';
    agents.setAttribute('role','list');agents.setAttribute('aria-labelledby','agentConnectionsTitle');
    left.append(heading,project,newChat,title,history,clearProject,agentsTitle,agents,setting);
    renderAgentConnections();
    document.getElementById('btnPanels').textContent='Gelişmiş';
    document.getElementById('btnAgentCenter').textContent='Ajan tanılama';
    document.getElementById('signatureIntro')?.remove();
    inputEl.placeholder='Ekibe yazın veya görev verin…';
  }
  initializeWorkspaceLayout();

"""
