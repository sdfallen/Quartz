"""Quartz repair-plan panel; composed in the shared application scope.

docs/INTEGRATION_REQUEST_REPAIR_PLAN_UI_20261110.md: the user, never the model, names the host
tests, their count and the Python path. Preview only reads and hashes on the host; registering
needs that exact preview and an explicit confirm. The host decides everything; this only asks.
"""

JAVASCRIPT = r"""
  // Repair plan panel + chip (user-approved repair entry, 10 Nov).
  const repairPlanPanel = document.getElementById('repairPlan');
  const repairPlanBtn = document.getElementById('btnRepairPlan');
  const repairChip = document.getElementById('repairChip');
  const rp = id => document.getElementById(id);
  let repairPreview = null;   // last valid host preview for the current form values
  let repairPlanKey = '';
  let repairPlanCid = null;   // conversation the chip belongs to (host-reported, not inferred)
  // Strict whole numbers only: "1e2", "1.9", "08x" are refused, never rounded into another count.
  function repairInt(value, min, max) {
    const raw = String(value ?? '').trim();
    if (!/^[0-9]{1,6}$/.test(raw)) return NaN;
    const n = Number(raw);
    return Number.isSafeInteger(n) && n >= min && n <= max ? n : NaN;
  }

  function repairLines(id) {
    return String(rp(id)?.value || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  }
  // The host never switches agent or model for a plan: it must be the conversation's single agent.
  function repairAgent() {
    const agent = typeof mainAgentSelect !== 'undefined' && mainAgentSelect ? mainAgentSelect.value : '';
    return agent === 'codex' || agent === 'antigravity' ? agent : '';
  }
  function syncRepairAgent() {
    const agent = repairAgent();
    if (rp('rpProvider')) rp('rpProvider').value = agent || 'codex';
  }
  function repairFormValues() {
    return {
      conversation_id: currentConvId,
      provider: repairAgent() || 'codex',
      test_files: repairLines('rpTests'),
      support_files: repairLines('rpSupport'),
      expected_tests: repairInt(rp('rpExpected')?.value, 1, 100000),
      python_executable: String(rp('rpPython')?.value || '').trim() || null,
      max_repairs: repairInt(rp('rpMax')?.value, 1, 3),
    };
  }
  function repairLocalError(v) {
    if (!v.conversation_id) return 'Önce bir sohbet seçin.';
    if (!repairAgent()) return 'Onarım planı tek ajanla çalışır; önce Codex veya Antigravity seçin.';
    if (!v.test_files.length) return 'En az bir test dosyası yazın.';
    if (v.test_files.length > 64 || v.support_files.length > 64) return 'En çok 64 dosya yazılabilir.';
    if (!Number.isSafeInteger(v.expected_tests)) return 'En az test sayısı 1 ile 100000 arasında bir tam sayı olmalı (örnek: 8).';
    if (!Number.isSafeInteger(v.max_repairs)) return 'En çok onarım 1, 2 veya 3 olmalı.';
    return '';
  }
  function setRepairError(text) {
    const box = rp('rpError');
    if (!box) return;
    box.textContent = text ? String(text) : '';
    box.hidden = !text;
  }
  function invalidateRepairPreview() {
    repairPreview = null;
    rp('rpRegister').disabled = true;
    rp('rpPreviewOut').hidden = true;
    rp('rpPreviewOut').replaceChildren();
  }
  function setRepairPanelOpen(open) {
    if (!repairPlanPanel || !repairPlanBtn) return;
    repairPlanPanel.hidden = !open;
    repairPlanBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    // The empty-state greeting would otherwise peek out above the open panel.
    document.body?.classList?.toggle('repair-plan-open', !!open);
    if (open) { syncRepairAgent(); rp('rpTests')?.focus(); }
  }

  function renderRepairPreview(data) {
    const out = rp('rpPreviewOut');
    const files = Array.isArray(data?.files) ? data.files : [];
    // The host sends model as {model, effort}; older drafts sent a string.
    const m = data?.model;
    const modelText = m && typeof m === 'object'
      ? [m.model, m.effort].filter(Boolean).map(String).join(' · ')
      : (m ? String(m) : '');
    const head = document.createElement('p');
    head.className = 'rp-preview-head';
    head.textContent = `${files.filter(f => f?.role === 'test').length} test dosyası, `
      + `${files.filter(f => f?.role === 'support').length} destek dosyası · en az ${Number(data?.expected_tests) || 0} test · `
      + `ajan ${data?.provider === 'antigravity' ? 'Antigravity' : 'Codex'}${modelText ? ' (' + modelText + ')' : ''}`;
    const list = document.createElement('ul');
    list.className = 'rp-files';
    for (const f of files) {
      const item = document.createElement('li');
      const role = document.createElement('span');
      role.className = 'rp-role';
      role.textContent = f?.role === 'support' ? 'destek' : 'test';
      const path = document.createElement('code');
      path.textContent = String(f?.path || '');
      const hash = document.createElement('span');
      hash.className = 'rp-hash';
      hash.title = String(f?.sha256 || '');
      hash.textContent = String(f?.sha256 || '').slice(0, 12);
      item.append(role, path, hash);
      list.append(item);
    }
    const parts = [head, list];
    if (data?.python_executable) {
      const py = document.createElement('p');
      py.className = 'rp-python';
      py.textContent = 'Python: ' + String(data.python_executable);
      parts.push(py);
    }
    for (const w of (Array.isArray(data?.warnings) ? data.warnings : [])) {
      const warn = document.createElement('p');
      warn.className = 'rp-warning';
      warn.textContent = String(w);
      parts.push(warn);
    }
    const note = document.createElement('p');
    note.className = 'rp-note';
    note.textContent = 'Önizleme hiçbir kod çalıştırmadı. Testler geçse bile onarım farkı bağımsız incelemeden kabul sayılmaz.';
    parts.push(note);
    out.replaceChildren(...parts);
    out.hidden = false;
    const list2 = rp('rpPythonList');
    if (list2 && Array.isArray(data?.python_candidates)) {
      list2.replaceChildren(...data.python_candidates.map(p => {
        const opt = document.createElement('option'); opt.value = String(p); return opt;
      }));
    }
    if (!rp('rpPython').value && data?.python_executable) rp('rpPython').value = String(data.python_executable);
  }

  async function previewRepairPlan() {
    const btn = rp('rpPreviewBtn');
    if (btn.disabled) return;
    invalidateRepairPreview();
    const values = repairFormValues();
    const local = repairLocalError(values);
    setRepairError(local);
    if (local) return;
    btn.disabled = true;
    btn.textContent = 'Önizleniyor…';
    try {
      const resp = await window.pywebview.api.repair_plan_preview(values);
      // A late answer for another conversation must not touch this one's form.
      if (currentConvId !== values.conversation_id) return;
      if (resp?.status !== 'ok' || !resp.data?.preview_id) {
        setRepairError(String(resp?.data || 'Önizleme yapılamadı.'));
        return;
      }
      // A preview only stands for the values it was made from.
      if (JSON.stringify(repairFormValues()) !== JSON.stringify(values)) return;
      repairPreview = resp.data;
      renderRepairPreview(resp.data);
      rp('rpRegister').disabled = false;
    } catch (error) {
      if (currentConvId === values.conversation_id) setRepairError('Önizleme yapılamadı: ' + String(error?.message || error));
    } finally {
      btn.disabled = false;
      btn.textContent = 'Önizle';
    }
  }

  // A preview belongs to one conversation and one agent; switching either retires it.
  function repairPreviewStale() {
    return !!repairPreview && (repairPreview.conversation_id !== currentConvId
      || repairPreview.provider !== repairAgent());
  }
  function retireStaleRepairPreview() {
    if (!repairPreviewStale()) return false;
    invalidateRepairPreview();
    setRepairError('Sohbet veya ajan değişti; planı yeniden önizleyin.');
    return true;
  }

  async function registerRepairPlan() {
    const btn = rp('rpRegister');
    if (btn.disabled || !repairPreview) return;
    // Checked before any IPC: never register c1's preview while the user is on c2 or another agent.
    if (retireStaleRepairPreview()) return;
    btn.disabled = true;
    btn.textContent = 'Kaydediliyor…';
    const previewId = repairPreview.preview_id;
    const cid = repairPreview.conversation_id || currentConvId;
    // Only the conversation that asked may show the answer; the next status poll reports the truth.
    const stillHere = () => currentConvId === cid;
    try {
      const resp = await window.pywebview.api.repair_plan_register(previewId, true);
      if (!stillHere()) return;
      if (resp?.status !== 'ok') {
        setRepairError(String(resp?.data || 'Plan kaydedilemedi.'));
        invalidateRepairPreview();
        return;
      }
      setRepairError('');
      invalidateRepairPreview();
      renderRepairPlanChip(resp.data || null, cid);
      setRepairPanelOpen(false);
      logLine('Onarım planı kaydedildi; görev mesajını gönderince kullanılacak.');
    } catch (error) {
      if (!stillHere()) return;
      setRepairError('Plan kaydedilemedi: ' + String(error?.message || error));
      invalidateRepairPreview();
    } finally {
      btn.textContent = 'Onayla ve kaydet';
    }
  }

  // cid: the conversation the host reported this plan for (status payload or the registering one).
  function renderRepairPlanChip(plan, cid) {
    if (!repairChip) return;
    // Every status poll lands here, so a conversation or agent switch retires an open preview.
    retireStaleRepairPreview();
    if (repairPlanPanel && !repairPlanPanel.hidden) syncRepairAgent();
    const valid = !!plan && typeof plan === 'object' && !!cid;
    const key = JSON.stringify([valid ? cid : null, valid ? plan : null]);
    if (key === repairPlanKey) return;
    repairPlanKey = key;
    repairPlanCid = valid ? cid : null;
    if (!valid) { repairChip.hidden = true; return; }
    const running = plan.status === 'running';
    repairChip.dataset.status = running ? 'running' : 'ready';
    rp('repairChipBadge').dataset.tone = running ? 'wait' : 'ok';
    rp('repairChipText').textContent = running
      ? 'Onarım döngüsü çalışıyor'
      : `Onarım planı hazır — en az ${Number(plan.expected_tests) || 0} test · `
        + `${Number(plan.files_count) || 0} dosya · `  // host total: tests + support files
        + `en çok ${Number(plan.max_repairs) || 0} onarım · ajan ${plan.provider === 'antigravity' ? 'Antigravity' : 'Codex'}`;
    rp('repairChipClear').hidden = running;
    repairChip.hidden = false;
  }

  // Live gate 3 (11 Nov): chat_status is not polled while a turn runs, so the chip stayed "hazır".
  // Purely a display hint; the host's next status (running/null) replaces it.
  function markRepairPlanRunning(on) {
    if (!on || !repairChip || repairChip.hidden || repairPlanCid !== currentConvId) return;
    repairPlanKey = '';  // let the next host status repaint whatever is true
    repairChip.dataset.status = 'running';
    rp('repairChipBadge').dataset.tone = 'wait';
    rp('repairChipText').textContent = 'Onarım döngüsü çalışıyor';
    rp('repairChipClear').hidden = true;
  }

  async function clearRepairPlan() {
    const btn = rp('repairChipClear');
    const target = repairPlanCid;
    // Never aim "Kaldır" at a conversation other than the one whose chip is shown.
    if (btn.disabled || !target || target !== currentConvId) return;
    btn.disabled = true;
    try {
      const resp = await window.pywebview.api.repair_plan_clear(target);
      if (repairPlanCid !== target) return;
      if (resp?.status === 'ok') renderRepairPlanChip(null, target);
      else logLine('Onarım planı kaldırılamadı: ' + String(resp?.data || 'bilinmeyen hata'));
    } catch (error) {
      logLine('Onarım planı kaldırılamadı: ' + String(error?.message || error));
    } finally {
      btn.disabled = false;
    }
  }

  repairPlanBtn?.addEventListener('click', () => setRepairPanelOpen(repairPlanPanel.hidden));
  rp('rpClose')?.addEventListener('click', () => { setRepairPanelOpen(false); repairPlanBtn?.focus(); });
  rp('rpPreviewBtn')?.addEventListener('click', previewRepairPlan);
  rp('rpRegister')?.addEventListener('click', registerRepairPlan);
  rp('repairChipClear')?.addEventListener('click', clearRepairPlan);
  for (const id of ['rpProvider', 'rpTests', 'rpSupport', 'rpExpected', 'rpPython', 'rpMax']) {
    rp(id)?.addEventListener('input', invalidateRepairPreview);
  }
  repairPlanPanel?.addEventListener('keydown', e => {
    if (e.key === 'Escape') { setRepairPanelOpen(false); repairPlanBtn?.focus(); }
  });
"""
