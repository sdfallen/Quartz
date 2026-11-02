"""Quartz diagnostics JavaScript fragment; composed in the shared application scope."""

JAVASCRIPT = r"""  // ── Self-Diagnostics (REA-Supported Compact Chat Card) ──
  function renderRepairPlan(plan) {
    if (!plan) { appendMsg('bot', 'QUARTZ', 'Referans seçimi iptal edildi; dosya değiştirilmedi.'); return; }
    const card = document.createElement('div');
    card.className = 'coordination-card diagnostics-card';
    const title = document.createElement('strong'); title.textContent = 'Quartz kaynak onarımı';
    const description = document.createElement('p'); description.textContent = plan.message;
    const files = document.createElement('pre'); files.textContent = (plan.files || []).join('\n') || 'Onarılacak kaynak farkı yok.';
    card.append(title, description, files);
    if (plan.requires_confirmation) {
      const confirm = document.createElement('button'); confirm.type = 'button';
      confirm.textContent = 'Bu referansa güveniyorum — yedekle ve onar';
      const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.textContent = 'Vazgeç';
      dismiss.addEventListener('click', async () => {
        confirm.disabled = true; dismiss.disabled = true;
        description.textContent = 'Onarım uygulanmadı; dosyalar değişmedi.';
        await window.pywebview.api.diagnostics_discard_repair();
      });
      confirm.addEventListener('click', async () => {
        confirm.disabled = true; dismiss.disabled = true;
        description.textContent = 'Kaynaklar yedekleniyor ve doğrulanıyor…';
        try {
          const result = await window.pywebview.api.diagnostics_apply_repair(plan.id);
          description.textContent = result.status === 'ok' ? result.data.message : result.data;
          card.dataset.repairState = result.status === 'ok' ? result.data.state : 'failed';
        } catch (_) { description.textContent = 'Onarım yanıtı alınamadı; tekrar uygulamadan önce teşhis çalıştırın.'; }
      });
      card.append(confirm, dismiss);
    }
    chatEl.append(card);
  }
  const DIAG_PHASE_LABELS = {
    queued: 'Sıraya alındı',
    scope: 'Kapsam ve kimlik doğrulaması',
    resources: 'Gerekli kaynak bileşenleri kontrolü',
    manifest: 'Paket manifesti ve SHA-256 doğrulaması',
    rea: 'REA statik ikili / arşiv incelemesi',
    analysis: 'Yapı ve bağımlılık ilişkileri inceleniyor',
    tool_permission: 'Kayıtlı araç izni bekleniyor',
    tool_acquire: 'Kayıtlı araç sürümü doğrulanıyor',
    report: 'Teşhis kanıtları kaydediliyor',
    done: 'Ölçüm tamamlandı',
  };
  const DIAG_CHECK_TITLES = {
    scope: 'İncelenen uygulama kapsamı',
    artifact: 'Seçilen uygulama dosyası',
    pe: 'Windows PE mimarisi ve başlığı',
    resources: 'Gerekli paket bileşenleri',
    manifest: 'Paket manifesti ve bütünlük',
    rea: 'REA statik paket incelemesi',
    analysis: 'Yapı ve bağımlılık çözümlemesi',
    inspection: 'Teşhis yürütme durumu',
  };
  const DIAG_STATUS_BADGES = {
    PASS: 'PASS · GEÇTİ',
    FAIL: 'FAIL · BAŞARISIZ',
    UNKNOWN: 'UNKNOWN · BELİRSİZ',
    NOT_TESTED: 'NOT TESTED · TEST EDİLMEDİ',
  };
  const DIAG_STATUS_EXPLANATIONS = {
    PASS: 'Bu kontrol doğrulandı; beklenen yapı ve özet değerleriyle uyumlu.',
    FAIL: 'Bu kontrolde uyumsuzluk veya eksiklik saptandı; kanıt ayrıntılarını inceleyin.',
    UNKNOWN: 'Bu kontrolün sonucu mevcut çalışma koşulunda kesinleştirilemedi.',
    NOT_TESTED: 'Bu kontrol mevcut modda (ör. kaynak kodu modu veya REA seçilmemesi/bulunmaması) çalıştırılmadı.',
  };
  const DIAG_SCOPE_NOTICE = 'Not: Başarılı paket kontrolü; model erişimi, arayüz işlevleri, güvenlik veya tüm uygulamanın hatasız olduğu anlamına gelmez.';

  function normalizeDiagStatus(raw) {
    const val = String(raw || 'UNKNOWN').trim().toUpperCase().replace(/[\s-]+/g, '_');
    if (val === 'PASS') return 'PASS';
    if (val === 'FAIL') return 'FAIL';
    if (val === 'NOT_TESTED') return 'NOT_TESTED';
    return 'UNKNOWN';
  }

  function redactDiagText(text) {
    return String(text || '')
      .replace(/\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|nvapi-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9]{16,}|sk-(?:proj-)?[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,})\b/g, '[gizli]')
      .replace(/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, '[gizli-anahtar]');
  }

  function formatDiagEvidence(evidence) {
    if (!evidence || typeof evidence !== 'object') return '';
    const keys = Object.keys(evidence).filter(k => evidence[k] !== undefined && evidence[k] !== null && evidence[k] !== '');
    if (!keys.length) return '';
    const safeCopy = {};
    for (const key of keys) {
      if (/secret|token|password|api_key|report_path/i.test(key)) continue;
      safeCopy[key] = evidence[key];
    }
    if (!Object.keys(safeCopy).length) return '';
    return redactDiagText(JSON.stringify(safeCopy, null, 2));
  }

  function buildSelfDiagnosticsView(job) {
    if (!job || typeof job !== 'object') {
      return {
        id: 'invalid',
        state: 'failed',
        phase: 'done',
        phaseLabel: 'Geçersiz teşhis verisi',
        progress: 0,
        progressText: 'Başarısız (%0)',
        message: 'Teşhis durumu okunamadı.',
        verdictCode: 'UNKNOWN',
        badgeCode: 'UNKNOWN',
        badgeText: 'UNKNOWN · BELİRSİZ',
        fillCode: 'FAIL',
        isSuccessReady: false,
        canCancel: false,
        reaUsed: false,
        reaTagText: 'REA: Belirsiz',
        counts: { PASS: 0, FAIL: 0, UNKNOWN: 0, NOT_TESTED: 0 },
        checks: [],
        limitations: [],
        scopeNotice: DIAG_SCOPE_NOTICE,
        technicalSummaryText: '',
      };
    }
    const state = ['idle', 'running', 'completed', 'cancelled', 'failed'].includes(job.state) ? job.state : 'unknown';
    const phase = String(job.phase || 'queued');
    const phaseLabel = DIAG_PHASE_LABELS[phase] || phase;
    const rawProgress = Number(job.progress);
    const progress = Number.isFinite(rawProgress) ? Math.max(0, Math.min(100, Math.round(rawProgress))) : 0;
    const rawChecks = Array.isArray(job.checks) ? job.checks : [];
    const counts = { PASS: 0, FAIL: 0, UNKNOWN: 0, NOT_TESTED: 0 };
    const checks = rawChecks.map((item, idx) => {
      const c = item && typeof item === 'object' ? item : {};
      const checkId = String(c.id || `check-${idx + 1}`);
      const status = normalizeDiagStatus(c.status);
      counts[status] = (counts[status] || 0) + 1;
      const title = String(c.title || DIAG_CHECK_TITLES[checkId] || checkId);
      const rawMsg = redactDiagText(c.message || '');
      const explanation = rawMsg || DIAG_STATUS_EXPLANATIONS[status];
      return {
        id: checkId,
        status,
        statusBadge: DIAG_STATUS_BADGES[status],
        title,
        explanation,
        statusHint: DIAG_STATUS_EXPLANATIONS[status],
        evidenceText: formatDiagEvidence(c.evidence),
      };
    });

    const rawVerdict = String(job.verdict || 'UNKNOWN').trim().toUpperCase().replace(/[\s-]+/g, '_');
    const isRunning = state === 'running' || (state === 'idle' && Boolean(job.id));
    const isSuccessReady = (
      state === 'completed' &&
      rawVerdict === 'PASS' &&
      job.finished_at != null &&
      checks.length > 0 &&
      counts.FAIL === 0 &&
      counts.UNKNOWN === 0 &&
      counts.NOT_TESTED === 0
    );

    let verdictCode = 'UNKNOWN';
    let badgeCode = 'UNKNOWN';
    let badgeText = 'UNKNOWN · BELİRSİZ';
    let fillCode = 'UNKNOWN';

    if (isRunning) {
      verdictCode = 'UNKNOWN';
      badgeCode = 'RUNNING';
      badgeText = phase === 'queued' ? 'SIRADA' : 'ÇALIŞIYOR';
      fillCode = 'RUNNING';
    } else if (state === 'cancelled') {
      verdictCode = 'UNKNOWN';
      badgeCode = 'CANCELLED';
      badgeText = 'İPTAL EDİLDİ (UNKNOWN)';
      fillCode = 'CANCELLED';
    } else if (state === 'failed') {
      verdictCode = rawVerdict === 'FAIL' ? 'FAIL' : 'UNKNOWN';
      badgeCode = verdictCode;
      badgeText = verdictCode === 'FAIL' ? 'FAIL · BAŞARISIZ' : 'TAMAMLANAMADI (UNKNOWN)';
      fillCode = 'FAIL';
    } else if (state === 'completed') {
      if (rawVerdict === 'FAIL' || counts.FAIL > 0) {
        verdictCode = 'FAIL';
        badgeCode = 'FAIL';
        badgeText = 'FAIL · SORUN SAPTANDI';
        fillCode = 'FAIL';
      } else if (isSuccessReady) {
        verdictCode = 'PASS';
        badgeCode = 'PASS';
        badgeText = 'PASS · DOĞRULANDI';
        fillCode = 'PASS';
      } else if (rawVerdict === 'PARTIAL' || (rawVerdict === 'PASS' && !isSuccessReady)) {
        verdictCode = 'PARTIAL';
        badgeCode = 'PARTIAL';
        badgeText = 'PARTIAL · KISMİ KAPSAM';
        fillCode = 'PARTIAL';
      } else {
        verdictCode = 'UNKNOWN';
        badgeCode = 'UNKNOWN';
        badgeText = 'UNKNOWN · BELİRSİZ';
        fillCode = 'UNKNOWN';
      }
    }

    let progressText = `${phaseLabel} · %${progress}`;
    if (state === 'cancelled') {
      progressText = `İptal edildi (%${progress} aşamasında durduruldu; başarı sayılmadı)`;
    } else if (state === 'failed') {
      progressText = `Tamamlanamadı (%${progress} aşamasında kesildi)`;
    } else if (state === 'completed') {
      if (verdictCode === 'PASS') progressText = `Ölçüm tamamlandı (%${progress}) · Tüm kontroller geçti`;
      else if (verdictCode === 'PARTIAL') progressText = `Ölçüm tamamlandı (%${progress}) · Kısmi kapsam (test edilmeyen/belirsiz adım var)`;
      else if (verdictCode === 'FAIL') progressText = `Ölçüm tamamlandı (%${progress}) · Sorun bulgusu var`;
      else progressText = `Ölçüm tamamlandı (%${progress}) · Sonuç belirsiz`;
    }

    const reaCheck = checks.find(c => c.id === 'rea');
    const reaUsed = Boolean(job.rea_used);
    const investigation = job.investigation && typeof job.investigation === 'object' ? job.investigation : {};
    const knowledgeReused = investigation.knowledge_reused === true;
    const reaTagText = reaUsed
      ? 'REA: Kullanıldı'
      : (knowledgeReused ? 'REA: Önceki kanıt doğrulandı' : (reaCheck?.status === 'NOT_TESTED' ? 'REA: Test Edilmedi' : (isRunning ? 'REA: Hazırlanıyor' : 'REA: Devre Dışı')));

    const limitations = Array.isArray(job.limitations)
      ? job.limitations.map(item => redactDiagText(item)).filter(Boolean)
      : [];

    const knowledgeSaved = Boolean(job.knowledge_saved);
    const summaryMeta = {
      schema_version: job.schema_version ?? 1,
      job_id: job.id || null,
      state,
      phase,
      verdict: verdictCode,
      progress,
      rea_used: reaUsed,
      knowledge_saved: knowledgeSaved,
      counts,
      report_saved: Boolean(job.report_path),
      chat_task: job.chat_task && typeof job.chat_task === 'object' ? {
        task_id: String(job.chat_task.task_id || ''),
        state: String(job.chat_task.state || ''),
        permission_pending: Boolean(job.chat_task.pending_permission),
      } : null,
      investigation: {
        evidence_count: Number.isInteger(investigation.evidence_count) && investigation.evidence_count >= 0 && investigation.evidence_count <= 128 ? investigation.evidence_count : 0,
        findings_count: Number.isInteger(investigation.findings_count) && investigation.findings_count >= 0 && investigation.findings_count <= 128 ? investigation.findings_count : 0,
        knowledge_reused: knowledgeReused,
        knowledge_saved: job.investigation_knowledge_saved === true,
        learning_quality: Object.fromEntries(['verified_procedure', 'observed', 'hypothesis', 'unverified', 'contradicted'].map(key => {
          const n = investigation.learning_quality?.tier_counts?.[key];
          return [key, Number.isInteger(n) && n >= 0 && n <= 128 ? n : 0];
        })),
        instruction_authority: false,
      },
    };

    return {
      id: String(job.id || 'latest'),
      state,
      phase,
      phaseLabel,
      progress,
      progressText,
      message: redactDiagText(job.message || ''),
      verdictCode,
      badgeCode,
      badgeText,
      fillCode,
      isSuccessReady,
      canCancel: state === 'running',
      reaUsed,
      reaTagText,
      knowledgeSaved,
      counts,
      checks,
      limitations,
      scopeNotice: DIAG_SCOPE_NOTICE,
      technicalSummaryText: JSON.stringify(summaryMeta, null, 2),
    };
  }

  let activeDiagJobId = null;
  let activeDiagConversationId = null;
  let diagPollTimer = null;
  let diagPollBusy = false;
  const diagPollFailures = new Map();
  const diagScopeDecisions = new Map();

  function hasActiveDiagnosticsJob() {
    return Boolean(activeDiagJobId && (diagPollFailures.get(activeDiagJobId) || 0) <= 3);
  }

  function renderLearnedApplicationsCard(items, targetContainer = null) {
    const container = targetContainer || (typeof chatEl !== 'undefined' ? chatEl : null);
    if (!container) return null;
    const card = document.createElement('section');
    card.className = 'coordination-card diagnostics-card';
    card.setAttribute('aria-label', 'Quartz Öğrenilen Uygulama Hafızası');
    const head = document.createElement('div');
    head.className = 'diag-head';
    const titleWrap = document.createElement('div');
    titleWrap.className = 'diag-title-wrap';
    const titleEl = document.createElement('strong');
    titleEl.className = 'diag-title';
    titleEl.textContent = 'QUARTZ UYGULAMA HAFIZASI (REA + DENEYİM)';
    const countTag = document.createElement('span');
    countTag.className = 'diag-rea-tag';
    countTag.textContent = `${Array.isArray(items) ? items.length : 0} Kayıtlı Profil`;
    titleWrap.append(titleEl, countTag);
    head.append(titleWrap);
    card.append(head);

    const checksBox = document.createElement('div');
    checksBox.className = 'diag-checks';
    if (!Array.isArray(items) || !items.length) {
      const empty = document.createElement('div');
      empty.className = 'diag-empty';
      empty.textContent = 'Henüz öğrenilmiş bir uygulama kaydı bulunmuyor. "Başka bir uygulamayı incele" komutuyla veya onaylı görevlerle uygulama profilleri öğrenilir.';
      checksBox.append(empty);
    } else {
      items.forEach((rec, idx) => {
        const row = document.createElement('div');
        row.className = 'diag-check-item';
        const status = normalizeDiagStatus(rec.verdict === 'PARTIAL' ? 'PASS' : rec.verdict);
        row.dataset.checkStatus = status;
        const top = document.createElement('div');
        top.className = 'diag-check-top';
        const cTitle = document.createElement('span');
        cTitle.className = 'diag-check-title';
        const shortHash = String(rec.sha256 || '').slice(0, 12);
        cTitle.textContent = `Uygulama #${idx + 1} · SHA-256: ${shortHash}…`;
        const cStatus = document.createElement('span');
        cStatus.className = 'diag-status-pill';
        cStatus.dataset.status = status;
        cStatus.textContent = String(rec.verdict || 'UNKNOWN');
        top.append(cTitle, cStatus);

        const facts = Array.isArray(rec.facts) ? rec.facts : [];
        const peFact = facts.find(f => f.source === 'pe')?.values || {};
        const reaFact = facts.find(f => f.source === 'rea')?.values || {};
        const opFact = facts.find(f => f.source === 'operational')?.values || {};
        const parts = [];
        if (peFact.architecture) parts.push(`Mimari: ${peFact.architecture}${peFact.pe_format ? ` (${peFact.pe_format})` : ''}`);
        if (peFact.subsystem) parts.push(`Alt sistem: ${peFact.subsystem}`);
        if (reaFact.format) parts.push(`REA biçimi: ${reaFact.format} (düğüm: ${reaFact.nodes ?? 0})`);
        if (opFact.verified_runs !== undefined) {
          parts.push(`Doğrulanmış görev: ${opFact.verified_runs}, Doğrulanmış eylem: ${opFact.verified_actions ?? 0}`);
        }
        if (opFact.requires_elevation) parts.push('UAC yükseltme gerekiyor');
        const cMsg = document.createElement('div');
        cMsg.className = 'diag-check-msg';
        cMsg.textContent = parts.length ? parts.join(' · ') : 'Statik dosya kimliği ve SHA-256 doğrulandı.';
        row.append(top, cMsg);

        const evDetails = document.createElement('details');
        evDetails.className = 'technical-details diag-evidence';
        const evSummary = document.createElement('summary');
        evSummary.textContent = 'Öğrenilen yapısal ve operasyonel kanıtlar';
        const evPre = document.createElement('pre');
        evPre.className = 'diag-evidence-pre';
        evPre.textContent = formatDiagEvidence(rec);
        evDetails.append(evSummary, evPre);
        row.append(evDetails);
        checksBox.append(row);
      });
    }
    card.append(checksBox);
    container.appendChild(card);
    if (typeof scrollToBottom === 'function' && typeof userPinnedToBottom !== 'undefined' && userPinnedToBottom) {
      scrollToBottom(true);
    }
    return card;
  }

  function appendInvestigationPermission(card, job, container) {
    card.dataset.investigationPermission = '';
    const task = job.chat_task;
    const request = task?.pending_permission;
    const conversationId = typeof currentConvId === 'string' ? currentConvId : '';
    if (!task || task.state !== 'awaiting_permission' || !request || !conversationId ||
        task.conversation_id !== conversationId || typeof task.task_id !== 'string' || !task.task_id ||
        typeof request.request_id !== 'string' || !request.request_id ||
        !Number.isSafeInteger(request.generation) || request.generation < 0 ||
        typeof request.effect !== 'string' || !request.effect) return;
    // Only host-supplied primitive identities are captured. UI text cannot supply
    // a scope, callback, script or approval value to the backend.
    const bound = Object.freeze({taskId:task.task_id, requestId:request.request_id,
      generation:request.generation, effect:request.effect, conversationId, jobId:String(job.id)});
    const key = JSON.stringify(bound);
    card.dataset.investigationPermission = key;
    const box = document.createElement('div'); box.className = 'diag-scope-permission';
    box.setAttribute('role', 'group'); box.setAttribute('aria-label', 'İnceleme kapsamı izni');
    const title = document.createElement('strong'); title.textContent = 'İnceleme için ek izin gerekiyor';
    const reason = document.createElement('p'); reason.textContent = redactDiagText(request.reason || 'İstenen işlem için kararınızı bekliyor.');
    const scope = document.createElement('p'); scope.textContent = 'İstenen kapsam: ' + redactDiagText(bound.effect);
    const feedback = document.createElement('p'); feedback.setAttribute('role', 'status');
    const approve = document.createElement('button'); approve.type = 'button'; approve.className = 'control-btn';
    approve.dataset.investigationApprove = bound.requestId; approve.textContent = 'Bu kapsam için izin ver';
    const deny = document.createElement('button'); deny.type = 'button'; deny.className = 'control-btn';
    deny.dataset.investigationDeny = bound.requestId; deny.textContent = 'İzin verme';
    const decision = diagScopeDecisions.get(key);
    if (decision) { approve.disabled = true; deny.disabled = true; feedback.textContent = decision.message; }
    const stillCurrent = () => typeof currentConvId === 'string' && currentConvId === bound.conversationId &&
      card.dataset.investigationPermission === key;
    async function answer(granted) {
      if (!stillCurrent() || diagScopeDecisions.has(key)) return;
      const receipt = {message:'İzin kararı uygulanıyor…'};
      diagScopeDecisions.set(key, receipt);
      approve.disabled = true; deny.disabled = true; feedback.textContent = receipt.message;
      try {
        const result = await window.pywebview.api.investigation_grant_scope(
          bound.taskId, bound.requestId, bound.generation, bound.effect, granted === true, bound.conversationId);
        if (!stillCurrent()) return;
        const data = result?.data;
        if (result?.status !== 'ok' || !data?.diagnostics || data.diagnostics.id !== bound.jobId ||
            data.chat_task?.task_id !== bound.taskId || data.chat_task?.conversation_id !== bound.conversationId) {
          throw new Error('scope-decision-unconfirmed');
        }
        receipt.message = granted ? 'İzin uygulandı; aynı inceleme devam ediyor.' : 'İzin verilmedi; kapsam genişletilmedi.';
        renderSelfDiagnosticsCard({...data.diagnostics, chat_task:data.chat_task}, container);
        if (data.diagnostics.state === 'running' || ['running','awaiting_permission'].includes(data.chat_task.state)) {
          scheduleSelfDiagnosticsPoll(bound.jobId);
        }
      } catch (_) {
        receipt.message = 'İzin kararı doğrulanamadı veya istek güncel değil. Durumu yeniden okuyun; yeni görev başlatılmadı.';
        if (stillCurrent()) {
          feedback.textContent = receipt.message;
          const refresh = document.createElement('button'); refresh.type = 'button'; refresh.className = 'control-btn';
          refresh.textContent = 'Durumu yeniden oku';
          refresh.onclick = async () => { if (!stillCurrent() || refresh.disabled) return; refresh.disabled = true; await pollSelfDiagnostics(bound.jobId); };
          box.append(refresh);
        }
      }
    }
    approve.onclick = () => answer(true);
    deny.onclick = () => answer(false);
    box.append(title, reason, scope, feedback, approve, deny);
    card.append(box);
  }

  function renderSelfDiagnosticsCard(job, targetContainer = null) {
    const container = targetContainer || (typeof chatEl !== 'undefined' ? chatEl : null);
    if (!container) return null;
    if (job?.chat_task?.conversation_id && typeof currentConvId === 'string' &&
        job.chat_task.conversation_id !== currentConvId) return null;
    const view = buildSelfDiagnosticsView(job);
    const selector = `[data-diagnostics-job="${view.id.replace(/["\\]/g, '')}"]`;
    let card = container.querySelector ? container.querySelector(selector) : null;
    const openDetailsKeys = new Set();
    if (card && card.querySelectorAll) {
      card.querySelectorAll('details[data-detail-key]').forEach(d => {
        if (d.open) openDetailsKeys.add(d.dataset.detailKey);
      });
    } else {
      card = document.createElement('section');
      card.className = 'coordination-card diagnostics-card';
      card.dataset.diagnosticsJob = view.id;
      card.setAttribute('aria-label', 'Quartz Öz Teşhis Kartı');
      container.appendChild(card);
    }

    card.dataset.state = view.state;
    card.dataset.verdict = view.verdictCode;
    card.classList.toggle('diag-complete-pass', view.isSuccessReady);
    card.replaceChildren();

    // 1. Header: Title + REA tag + Verdict Badge + Cancel Button
    const head = document.createElement('div');
    head.className = 'diag-head';
    const titleWrap = document.createElement('div');
    titleWrap.className = 'diag-title-wrap';
    const titleEl = document.createElement('strong');
    titleEl.className = 'diag-title';
    titleEl.textContent = job.scope === 'artifact' ? 'SEÇİLEN UYGULAMA İNCELEMESİ' : 'QUARTZ ÖZ TEŞHİS';
    const reaTag = document.createElement('span');
    reaTag.className = 'diag-rea-tag';
    reaTag.textContent = view.reaTagText;
    titleWrap.append(titleEl, reaTag);
    if (view.knowledgeSaved) {
      const learnTag = document.createElement('span');
      learnTag.className = 'diag-rea-tag';
      learnTag.textContent = 'ÖĞRENME: Hafızaya Kaydedildi';
      titleWrap.append(learnTag);
    }

    const actions = document.createElement('div');
    actions.className = 'diag-actions';
    const badge = document.createElement('span');
    badge.className = 'diag-badge';
    badge.dataset.badge = view.badgeCode;
    badge.textContent = view.badgeText;
    actions.append(badge);

    if (view.canCancel) {
      const cancelBtnEl = document.createElement('button');
      cancelBtnEl.type = 'button';
      cancelBtnEl.className = 'control-btn';
      cancelBtnEl.dataset.diagnosticsCancel = view.id;
      cancelBtnEl.textContent = 'İptal Et';
      cancelBtnEl.onclick = async () => {
        cancelBtnEl.disabled = true;
        cancelBtnEl.textContent = 'İptal ediliyor…';
        await cancelSelfDiagnostics(view.id);
      };
      actions.append(cancelBtnEl);
    }
    head.append(titleWrap, actions);
    card.append(head);

    // 2. Progress & Current Message
    const progRow = document.createElement('div');
    progRow.className = 'diag-progress-row';
    const phaseLine = document.createElement('div');
    phaseLine.className = 'diag-phase-line';
    const phaseText = document.createElement('span');
    phaseText.className = 'diag-phase-text';
    phaseText.textContent = view.message || view.progressText;
    const phasePct = document.createElement('span');
    phasePct.className = 'diag-phase-pct';
    phasePct.textContent = view.progressText;
    phaseLine.append(phaseText, phasePct);

    const bar = document.createElement('div');
    bar.className = 'diag-progress-bar';
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', '100');
    bar.setAttribute('aria-valuenow', String(view.progress));
    const fill = document.createElement('div');
    fill.className = 'diag-progress-fill';
    fill.dataset.fill = view.fillCode;
    fill.style.width = `${view.progress}%`;
    bar.append(fill);
    progRow.append(phaseLine, bar);
    card.append(progRow);
    appendInvestigationPermission(card, job, container);

    // 3. Status Counts (PASS / FAIL / UNKNOWN / NOT TESTED)
    const countsRow = document.createElement('div');
    countsRow.className = 'diag-counts';
    for (const [code, label] of [
      ['PASS', `PASS (Geçti): ${view.counts.PASS}`],
      ['FAIL', `FAIL (Başarısız): ${view.counts.FAIL}`],
      ['UNKNOWN', `UNKNOWN (Belirsiz): ${view.counts.UNKNOWN}`],
      ['NOT_TESTED', `NOT TESTED (Test Edilmedi): ${view.counts.NOT_TESTED}`],
    ]) {
      const pill = document.createElement('span');
      pill.className = 'diag-count-pill';
      pill.dataset.countStatus = code;
      pill.textContent = label;
      countsRow.append(pill);
    }
    card.append(countsRow);

    // 4. Checks List
    const checksBox = document.createElement('div');
    checksBox.className = 'diag-checks';
    if (!view.checks.length) {
      const empty = document.createElement('div');
      empty.className = 'diag-check-msg';
      empty.textContent = view.canCancel ? 'Kontrol adımları yürütülüyor…' : 'Bu koşuda kontrol adımı kaydı oluşmadı.';
      checksBox.append(empty);
    } else {
      for (const chk of view.checks) {
        const row = document.createElement('div');
        row.className = 'diag-check-row';
        row.dataset.checkId = chk.id;
        row.dataset.checkStatus = chk.status;

        const top = document.createElement('div');
        top.className = 'diag-check-top';
        const cTitle = document.createElement('span');
        cTitle.className = 'diag-check-title';
        cTitle.textContent = chk.title;
        const cStatus = document.createElement('span');
        cStatus.className = 'diag-status-pill';
        cStatus.dataset.status = chk.status;
        cStatus.textContent = chk.statusBadge;
        top.append(cTitle, cStatus);

        const cMsg = document.createElement('div');
        cMsg.className = 'diag-check-msg';
        cMsg.textContent = chk.explanation;
        row.append(top, cMsg);

        if (chk.evidenceText) {
          const evDetails = document.createElement('details');
          evDetails.className = 'technical-details diag-evidence';
          const detailKey = `ev:${chk.id}`;
          evDetails.dataset.detailKey = detailKey;
          evDetails.open = openDetailsKeys.has(detailKey);
          const evSummary = document.createElement('summary');
          evSummary.textContent = 'Kanıt ve teknik ayrıntılar';
          const evPre = document.createElement('pre');
          evPre.className = 'diag-evidence-pre';
          evPre.textContent = chk.evidenceText;
          evDetails.append(evSummary, evPre);
          row.append(evDetails);
        }
        checksBox.append(row);
      }
    }
    card.append(checksBox);

    // 5. Limitations & Scope Notice
    const limBox = document.createElement('div');
    limBox.className = 'diag-limitations';
    const noticeP = document.createElement('p');
    noticeP.textContent = view.scopeNotice;
    limBox.append(noticeP);
    if (view.limitations.length) {
      const ul = document.createElement('ul');
      for (const item of view.limitations) {
        const li = document.createElement('li');
        li.textContent = item;
        ul.append(li);
      }
      limBox.append(ul);
    }
    card.append(limBox);

    // 6. Card-level Technical Summary
    const metaDetails = document.createElement('details');
    metaDetails.className = 'technical-details diag-meta-details';
    metaDetails.dataset.detailKey = 'meta:summary';
    metaDetails.open = openDetailsKeys.has('meta:summary');
    const metaSummary = document.createElement('summary');
    metaSummary.textContent = 'Teşhis özeti ve teknik kayıt';
    const metaPre = document.createElement('pre');
    metaPre.textContent = view.technicalSummaryText;
    metaDetails.append(metaSummary, metaPre);
    card.append(metaDetails);

    if (typeof scrollToBottom === 'function' && typeof userPinnedToBottom !== 'undefined' && userPinnedToBottom) {
      scrollToBottom(true);
    }
    return card;
  }

  async function pollSelfDiagnostics(jobId = activeDiagJobId) {
    if (diagPollBusy || !jobId) return;
    if (typeof activeDiagConversationId !== 'undefined' && activeDiagConversationId &&
        activeDiagJobId === jobId && typeof currentConvId === 'string' &&
        activeDiagConversationId !== currentConvId) return;
    diagPollBusy = true;
    const polledConversationId = typeof currentConvId === 'string' ? currentConvId : null;
    let keepPolling = false;
    let terminal = false;
    try {
      const resp = await window.pywebview.api.diagnostics_status(jobId);
      if (polledConversationId !== null && currentConvId !== polledConversationId) return;
      if (!resp || resp.status !== 'ok' || !resp.data || resp.data.id !== jobId) throw new Error('diagnostics-status-unavailable');
      if (resp.data.chat_task?.conversation_id && resp.data.chat_task.conversation_id !== polledConversationId) return;
      renderSelfDiagnosticsCard(resp.data);
      diagPollFailures.delete(jobId);
      keepPolling = resp.data.state === 'running' || ['running','awaiting_permission'].includes(resp.data.chat_task?.state);
      terminal = !keepPolling;
    } catch (_) {
      if (polledConversationId !== null && currentConvId !== polledConversationId) return;
      const failures = (diagPollFailures.get(jobId) || 0) + 1;
      diagPollFailures.set(jobId, failures);
      keepPolling = failures <= 3;
      showDiagnosticsPollError(jobId, keepPolling);
    } finally {
      diagPollBusy = false;
    }
    if (keepPolling) {
      scheduleSelfDiagnosticsPoll(jobId);
    } else if (terminal && activeDiagJobId === jobId) {
      activeDiagJobId = null;
      if (diagPollTimer) {
        clearTimeout(diagPollTimer);
        diagPollTimer = null;
      }
    }
  }

  function showDiagnosticsPollError(jobId, retrying) {
    const card = chatEl.querySelector(`[data-diagnostics-job="${String(jobId).replace(/["\\]/g, '')}"]`);
    if (!card) return;
    let warning = card.querySelector('.diag-connection-warning');
    if (!warning) {
      warning = document.createElement('div'); warning.className = 'diag-connection-warning';
      warning.setAttribute('role', 'alert'); card.append(warning);
    }
    warning.replaceChildren();
    const text = document.createElement('p');
    text.textContent = retrying ? 'Güncel teşhis durumu alınamadı; yeniden deneniyor…' :
      'Güncel sonuç doğrulanamadı. Yukarıdaki ilerleme son alınan bilgidir.';
    warning.append(text);
    if (!retrying) {
      const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'control-btn';
      retry.textContent = 'Durumu yeniden oku';
      retry.onclick = () => { diagPollFailures.delete(jobId); pollSelfDiagnostics(jobId); };
      warning.append(retry);
    }
  }

  function scheduleSelfDiagnosticsPoll(jobId) {
    if (!jobId) return;
    activeDiagJobId = jobId;
    if (typeof activeDiagConversationId !== 'undefined') {
      activeDiagConversationId = typeof currentConvId === 'string' ? currentConvId : null;
    }
    if (diagPollTimer) {
      clearTimeout(diagPollTimer);
      diagPollTimer = null;
    }
    const hidden = typeof isUiHidden === 'function' && isUiHidden();
    const lowSpec = typeof lowSpecHardware !== 'undefined' && Boolean(lowSpecHardware);
    const delay = Math.max(hidden ? 4000 : (lowSpec ? 1800 : 900),
      diagPollFailures.has(jobId) ? Math.min(8000, 1000 * 2 ** diagPollFailures.get(jobId)) : 0);
    diagPollTimer = setTimeout(() => pollSelfDiagnostics(jobId), delay);
  }

  async function startSelfDiagnostics(includeRea = true) {
    try {
      const resp = await window.pywebview.api.diagnostics_start(Boolean(includeRea));
      if (!resp || resp.status !== 'ok' || !resp.data) {
        if (typeof appendMsg === 'function') appendMsg('err', 'QUARTZ', (resp && resp.data) || 'Öz teşhis başlatılamadı');
        return null;
      }
      if (typeof chatEl !== 'undefined' && chatEl?.querySelectorAll) {
        chatEl.querySelectorAll('[data-welcome="1"]').forEach(el => el.remove());
      }
      renderSelfDiagnosticsCard(resp.data);
      if (resp.data.state === 'running' && resp.data.id) {
        scheduleSelfDiagnosticsPoll(resp.data.id);
      }
      return resp.data;
    } catch (e) {
      if (typeof appendMsg === 'function') appendMsg('err', 'QUARTZ', String(e.message || e));
      return null;
    }
  }

  async function cancelSelfDiagnostics(jobId) {
    if (!jobId) return null;
    try {
      const resp = await window.pywebview.api.diagnostics_cancel(jobId);
      if (!resp || resp.status !== 'ok' || !resp.data) {
        if (typeof appendMsg === 'function') appendMsg('err', 'QUARTZ', (resp && resp.data) || 'Öz teşhis iptal edilemedi');
        return null;
      }
      renderSelfDiagnosticsCard(resp.data);
      if (resp.data.state !== 'running' && activeDiagJobId === jobId) {
        activeDiagJobId = null;
        if (diagPollTimer) {
          clearTimeout(diagPollTimer);
          diagPollTimer = null;
        }
      }
      return resp.data;
    } catch (e) {
      if (typeof appendMsg === 'function') appendMsg('err', 'QUARTZ', String(e.message || e));
      return null;
    }
  }

  document.getElementById('btnSelfDiagnostics')?.addEventListener('click', () => {
    startSelfDiagnostics(true);
  });
  document.addEventListener('visibilitychange', () => {
    if (typeof isUiHidden === 'function' && !isUiHidden() && activeDiagJobId && !diagPollBusy) {
      pollSelfDiagnostics(activeDiagJobId);
    }
  });

  safeBtn.addEventListener('click', async () => {
    const r = await window.pywebview.api.set_safe_mode(!safeMode);
    safeMode = !!(r.data && r.data.enabled);
    safeBtn.classList.toggle('active', safeMode);
    safeBtn.textContent = `Güvenli Mod: ${safeMode ? 'AÇIK' : 'KAPALI'}`;
  });

  providerProbeBtn.addEventListener('click', async () => {
    providerProbeBtn.disabled = true;
    providerStatus.textContent = 'Bağlantı test ediliyor...';
    try {
      const response = await window.pywebview.api.provider_probe();
      if (response.status !== 'ok') throw new Error(response.data || 'Test başarısız');
      renderProvider(response.data);
    } catch (error) {
      providerStatus.textContent = `Test başarısız: ${error.message || error}`;
    } finally { providerProbeBtn.disabled = false; }
  });

"""
