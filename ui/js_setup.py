"""Quartz setup JavaScript fragment; composed in the shared application scope."""

JAVASCRIPT = r"""
  const chatEl      = document.getElementById('chat');
  const inputEl     = document.getElementById('msgInput');
  const sendBtn     = document.getElementById('btnSend');
  const micBtn      = document.getElementById('btnMic');
  const wakeBtn     = document.getElementById('btnWake');
  const ttsBtn      = document.getElementById('btnTts');
  const thinkingRow = document.getElementById('thinkingRow');
  const orbCore     = document.getElementById('orbCore');
  const statusPill  = document.getElementById('statusPill');
  const statusText  = document.getElementById('statusText');
  const clockEl     = document.getElementById('clock');
  const logBox      = document.getElementById('logBox');
  const safeBtn     = document.getElementById('btnSafe');
  const advisorBtn  = document.getElementById('btnAdvisor');
  const cancelBtn   = document.getElementById('btnCancel');
  const thinkingText= document.getElementById('thinkingText');
  const taskList     = document.getElementById('taskList');
  const operationStatus = document.getElementById('operationStatus');
  const providerStatus = document.getElementById('providerStatus');
  const providerProbeBtn = document.getElementById('btnProviderProbe');
  const learnOperationBtn = document.getElementById('btnLearnOperation');
  const finishOperationBtn = document.getElementById('btnFinishOperation');
  const signatureIntro = document.getElementById('signatureIntro');
  const apiSetup = document.getElementById('apiSetup');
  const apiKey = document.getElementById('apiKey');
  const apiSubmit = document.getElementById('apiSubmit');
  const apiError = document.getElementById('apiError');
  const agentOverlay = document.getElementById('agentOverlay');
  const agentProject = document.getElementById('agentProject');
  const agentPrompt = document.getElementById('agentPrompt');
  const agentWrite = document.getElementById('agentWrite');
  const agentProvider = document.getElementById('agentProvider');
  const agentError = document.getElementById('agentError');
  const mainAgentSelect = document.getElementById('mainAgentSelect');
  const chatConvTitle = document.getElementById('chatConvTitle');
  const chatProjectTag = document.getElementById('chatProjectTag');
  const mainProjectSelect = document.getElementById('mainProjectSelect');
  const btnAddProject = document.getElementById('btnAddProject');
  const writerBadge = document.getElementById('writerBadge');
  const btnNewChat = document.getElementById('btnNewChat');
  let currentConvId = null;
  let chatPollInterval = null;
  let activeBotBubble = null;
  let antigravitySafetyWarning = '';
  let antigravityWarningAccepted = false;

  let agentPollToken = 0;

  function updateAntigravitySafety(status) {
    antigravitySafetyWarning = String(status?.safety_warning || '');
    for (const [agent, label] of [['antigravity', '◈ Antigravity'], ['collaboration', '◈ Birlikte']]) {
      const button = document.querySelector(`.agent-seg-btn[data-agent="${agent}"]`);
      if (!button) continue;
      button.textContent = label + (antigravitySafetyWarning ? ' ⚠' : '');
      button.title = antigravitySafetyWarning;
    }
  }

  function confirmAntigravitySafety() {
    if (!antigravitySafetyWarning || antigravityWarningAccepted) return true;
    const accepted = window.confirm('ANTIGRAVITY WINDOWS UYARISI\n\n' + antigravitySafetyWarning +
      '\n\nBu oturumda inceleme görevlerine devam etmek istiyor musun?');
    if (accepted) antigravityWarningAccepted = true;
    return accepted;
  }

  signatureIntro.addEventListener('animationend', () => signatureIntro.remove());

  async function checkApiSetup() {
    try {
      const response = await window.pywebview.api.onboarding_status();
      if (response.status !== 'ok') return;
      renderCliStatus(response.data);
      if (response.data.needs_setup) document.getElementById('cliSetup').classList.add('show');
    } catch (_) {}
  }

  let cliPollTimer = null;
  let cliState = null;
  function renderCliStatus(data) {
    cliState = data;
    const providers = data.providers || {};
    document.getElementById('cliProviderState').textContent = ['codex','gemini'].map(p => {
      const state = providers[p] || {};
      const label = state.ready ? 'Bağlı' : !state.installed ? 'CLI kurulacak' : state.configured ? 'Bağlantı doğrulanmalı' : 'Hesap bağlantısı bekleniyor';
      const name = p === 'codex' ? 'Codex' : state.backend === 'agy' ? 'Gemini · Antigravity CLI' : 'Gemini CLI';
      return `${name}: ${label}${state.auth_message ? '\n' + state.auth_message : ''}`;
    }).join('\n');
    document.getElementById('cliMessage').textContent = data.job?.message || '';
    const busy = data.job?.state === 'running';
    ['cliValidate','cliAccount','cliInstall'].forEach(id => document.getElementById(id).disabled = busy);
    document.getElementById('cliContinue').disabled = !Object.values(providers).some(p=>p.ready);
    document.querySelectorAll('.agent-seg-btn[data-agent]').forEach(button => {
      const agent = button.dataset.agent;
      const ready = ['codex','antigravity','collaboration'].includes(agent) && (agent === 'collaboration' ? providers.codex?.ready && providers.gemini?.ready : providers[agent === 'antigravity' ? 'gemini' : agent]?.ready);
      button.disabled = !ready;
      button.setAttribute('aria-disabled', ready ? 'false' : 'true');
      button.title = ready ? '' : 'Hesaplar ve CLI kurulumu bölümünden bu ajanı bağlayabilirsiniz';
    });
    renderAgentConnections(providers);
    clearTimeout(cliPollTimer);
    if ((busy || Object.values(providers).some(p=>p.login_pending)) && document.getElementById('cliSetup').classList.contains('show')) cliPollTimer = setTimeout(()=>refreshCliStatus(false), 1500);
  }
  // Sidebar connection list. Readiness comes from authenticated backend checks.
  let agentConnectionView = {providers: null, active: ''};
  function renderAgentConnections(providers, activeAgent) {
    if (providers !== undefined) agentConnectionView.providers = providers;
    if (activeAgent !== undefined) agentConnectionView.active = activeAgent;
    const box = document.getElementById('agentConnections');
    if (!box) return;
    const known = agentConnectionView.providers;
    const describe = state => {
      if (!known) return ['unknown', 'Kontrol ediliyor'];
      if (!state) return ['missing', 'Bağlı değil'];
      if (state.checking && !state.ready) return ['unknown', 'Kontrol ediliyor'];
      if (state.ready) return ['ready', 'Bağlı'];
      if (state.login_pending) return ['pending', 'Giriş bekleniyor'];
      if (!state.installed) return ['missing', 'CLI kurulmamış'];
      return ['pending', state.configured ? 'Bağlantı doğrulanmalı' : 'Hesap bağlantısı bekleniyor'];
    };
    const active = agentConnectionView.active;
    const rows = [
      ['codex', 'Codex', describe(known?.codex), active === 'codex' || active === 'collaboration'],
      ['antigravity', 'Antigravity', describe(known?.gemini), active === 'antigravity' || active === 'collaboration'],
    ];
    box.replaceChildren();
    for (const [id, name, [state, text], current] of rows) {
      const row = document.createElement('div');
      row.className = 'agent-conn'; row.setAttribute('role', 'listitem');
      row.dataset.agentId = id; row.dataset.state = state;
      row.setAttribute('aria-current', current ? 'true' : 'false');
      const dot = document.createElement('span'); dot.className = 'conn-dot'; dot.setAttribute('aria-hidden', 'true');
      const label = document.createElement('span'); label.className = 'conn-name'; label.textContent = name;
      const detail = document.createElement('span'); detail.className = 'conn-state'; detail.textContent = text;
      row.append(dot, label, detail);
      box.append(row);
    }
  }
  async function refreshCliStatus(force=true) {
    try {
      const response = await window.pywebview.api.onboarding_status(force);
      if (response.status !== 'ok') throw Error(response.data);
      renderCliStatus(response.data);
    } catch (e) { document.getElementById('cliMessage').textContent = String(e.message || e); }
  }
  async function beginCli(operation) {
    const input = document.getElementById('cliKey');
    const key = operation === 'key' ? input.value.trim() : '';
    input.value = '';
    try {
      const response = await window.pywebview.api.onboarding_begin(operation, document.getElementById('cliProvider').value, key);
      if (response.status !== 'ok') throw Error(response.data);
      await refreshCliStatus(false);
    } catch (e) { document.getElementById('cliMessage').textContent = String(e.message || e); }
  }
  document.getElementById('cliAccount').onclick = ()=>beginCli(document.getElementById('cliProvider').value === 'gemini' ? 'account_agy' : 'account');
  document.getElementById('cliValidate').onclick = ()=>beginCli('key');
  document.getElementById('cliInstall').onclick = ()=>beginCli(document.getElementById('cliProvider').value === 'gemini' ? 'install_agy' : 'install');
  document.getElementById('cliCheck').onclick = ()=>refreshCliStatus(true);
  document.getElementById('btnCliConnections').onclick = async()=>{ document.getElementById('cliSetup').classList.add('show'); await refreshCliStatus(true); };
  document.getElementById('cliLater').onclick = ()=>{ clearTimeout(cliPollTimer); document.getElementById('cliSetup').classList.remove('show'); };
  document.getElementById('cliContinue').onclick = async()=>{
    const result = await window.pywebview.api.onboarding_refresh();
    if (result.status !== 'ok') { document.getElementById('cliMessage').textContent=result.data; return; }
    document.getElementById('cliSetup').classList.remove('show');
    const provider = cliState?.providers?.gemini?.ready ? 'antigravity' : 'codex';
    if (currentConvId) await window.pywebview.api.chat_set_agent(currentConvId, provider);
    syncAgentUI(provider);
    await loadActiveConversation();
  };

  apiSubmit.addEventListener('click', async () => {
    const key = apiKey.value.trim();
    if (!key) { apiError.textContent = 'Lütfen API anahtarını gir.'; return; }
    apiSubmit.disabled = true;
    apiSubmit.textContent = 'DOĞRULANIYOR...';
    apiError.textContent = '';
    try {
      const result = await window.pywebview.api.configure_api(
        document.getElementById('apiProvider').value, key);
      apiKey.value = '';
      if (result.status !== 'ok') throw new Error(result.data || 'Anahtar doğrulanamadı');
      apiSetup.classList.remove('show');
      appendMsg('bot', 'QUARTZ', 'API bağlantısı doğrulandı. Quartz kullanıma hazır.');
    } catch (error) {
      apiError.textContent = 'Doğrulama başarısız: ' + String(error.message || error);
    } finally {
      apiSubmit.disabled = false;
      apiSubmit.textContent = 'DOĞRULA VE BAŞLAT';
    }
  });
  apiKey.addEventListener('keydown', event => {
    if (event.key === 'Enter') apiSubmit.click();
  });

"""
