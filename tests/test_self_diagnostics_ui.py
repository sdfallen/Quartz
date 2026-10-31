"""Frontend and GUI bridge tests for the REA-supported self-diagnostics card."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import gui


class SelfDiagnosticsBridgeTests(unittest.TestCase):
    def test_api_bridge_uses_contract_ipc_actions(self):
        api = gui.Api()
        with patch("gui.ipc_send", return_value={"status": "ok", "data": {"id": "j1"}}) as ipc:
            api.diagnostics_start()
            self.assertEqual(ipc.call_args.args, ("diagnostics_start", {"include_rea": True}))

            api.diagnostics_start(False)
            self.assertEqual(ipc.call_args.args, ("diagnostics_start", {"include_rea": False}))

            api.diagnostics_status()
            self.assertEqual(ipc.call_args.args, ("diagnostics_status", {}))

            api.diagnostics_status("job-42")
            self.assertEqual(ipc.call_args.args, ("diagnostics_status", {"job_id": "job-42"}))

            api.diagnostics_cancel("job-42")
            self.assertEqual(ipc.call_args.args, ("diagnostics_cancel", {"job_id": "job-42"}))

    def test_main_chat_starts_and_cancels_self_diagnostics_without_task_center(self):
        api = gui.Api()
        job = {"id": "diag-1", "state": "running", "phase": "queued", "progress": 0, "checks": [], "verdict": "UNKNOWN"}
        with patch.object(api, "diagnostics_start", return_value={"status": "ok", "data": job}) as start, \
                patch.object(api, "natural_start") as natural:
            res = api.coordination_route("Öz teşhis başlat", "conv-1", "proj-1", {}, "read-only")
            self.assertEqual(res["status"], "ok")
            self.assertTrue(res["data"]["handled"])
            self.assertTrue(res["data"]["diagnostics_started"])
            self.assertEqual(res["data"]["diagnostics"]["id"], "diag-1")
            start.assert_called_once_with(include_rea=True)
            natural.assert_not_called()

        with patch.object(api, "diagnostics_start", return_value={"status": "ok", "data": job}) as start:
            api.coordination_route("REA olmadan öz teşhis başlat", "conv-1", "proj-1", {}, "read-only")
            start.assert_called_once_with(include_rea=False)

        cancelled = {**job, "state": "cancelled", "phase": "done", "progress": 25}
        with patch.object(api, "diagnostics_status", return_value={"status": "ok", "data": job}) as status, \
                patch.object(api, "diagnostics_cancel", return_value={"status": "ok", "data": cancelled}) as cancel:
            res = api.coordination_route("Öz teşhisi durdur", "conv-1", "proj-1", {}, "read-only")
            self.assertTrue(res["data"]["handled"])
            self.assertTrue(res["data"]["diagnostics_cancelled"])
            self.assertEqual(res["data"]["diagnostics"]["state"], "cancelled")
            status.assert_called_once_with()
            cancel.assert_called_once_with("diag-1")

    def test_questions_and_no_tool_prompts_never_trigger_self_diagnostics(self):
        for prompt in (
            "Öz teşhis nedir?",
            '"Öz teşhis başlat" komutu ne işe yarar?',
            "Araç kullanma, öz teşhis başlat",
            "Sadece sohbet edelim; kendini teşhis et",
        ):
            with self.subTest(prompt=prompt):
                api = gui.Api()
                with patch.object(api, "diagnostics_start") as start, patch("gui.ipc_send") as ipc:
                    res = api.coordination_route(prompt, "conv-1", "proj-1", {}, "read-only")
                start.assert_not_called()
                ipc.assert_not_called()
                self.assertEqual(res["data"]["intent"], "conversation")

    def test_css_and_header_button_present_with_reduced_motion_and_low_spec_rules(self):
        css = (Path(__file__).resolve().parents[1] / "assets" / "workspace.css").read_text(encoding="utf-8")
        self.assertIn(".diagnostics-card", css)
        self.assertIn('.diag-status-pill[data-status="NOT_TESTED"]', css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("body.low-spec .diagnostics-card", css)
        self.assertIn("body.ui-idle .diagnostics-card", css)
        self.assertIn('id="btnSelfDiagnostics"', gui._HTML)
        self.assertIn('alt="Quartz Q"', gui._HTML)


class SelfDiagnosticsJavaScriptTests(unittest.TestCase):
    def _extract_diag_js(self) -> str:
        start = gui._HTML.index("  // ── Self-Diagnostics (REA-Supported Compact Chat Card) ──")
        end = gui._HTML.index("  safeBtn.addEventListener('click'", start)
        return gui._HTML[start:end]

    def _run_node(self, script: str) -> str:
        # stdin avoids the Windows 32 KB command-line limit as the card JS grows.
        res = subprocess.run(
            ["node", "-"],
            input=script,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def test_status_separation_and_no_premature_or_false_success(self):
        diag_js = self._extract_diag_js()
        harness = r"""
const assert = require('node:assert/strict');
let lowSpecHardware = false;
function isUiHidden() { return false; }
const document = { getElementById: () => null, addEventListener: () => {} };
"""
        checks = r"""
// 1. Running job must NEVER allow success animation even at 95% with all PASS checks so far
const runningView = buildSelfDiagnosticsView({
  id: 'job-run',
  state: 'running',
  phase: 'manifest',
  progress: 95,
  message: 'Paket dosyaları karşılaştırılıyor',
  verdict: 'PASS',
  finished_at: null,
  checks: [{ id: 'scope', status: 'PASS', title: 'Kapsam', message: 'Tamam' }],
});
assert.equal(runningView.isSuccessReady, false);
assert.equal(runningView.badgeCode, 'RUNNING');
assert.equal(runningView.canCancel, true);

// 2. Four statuses (PASS, FAIL, UNKNOWN, NOT_TESTED / NOT TESTED) remain strictly distinct
const mixedView = buildSelfDiagnosticsView({
  id: 'job-mixed',
  state: 'completed',
  phase: 'done',
  progress: 100,
  verdict: 'FAIL',
  finished_at: 1700000000,
  checks: [
    { id: 'scope', status: 'PASS', title: 'Kapsam', message: 'Doğrulandı' },
    { id: 'resources', status: 'FAIL', title: 'Kaynaklar', message: 'Eksik dosya' },
    { id: 'manifest', status: 'NOT TESTED', title: 'Manifest', message: 'Manifest yok' },
    { id: 'rea', status: 'UNKNOWN', title: 'REA', message: 'Sonuç belirsiz' },
  ],
});
assert.deepEqual(mixedView.counts, { PASS: 1, FAIL: 1, UNKNOWN: 1, NOT_TESTED: 1 });
assert.equal(mixedView.checks[0].status, 'PASS');
assert.equal(mixedView.checks[1].status, 'FAIL');
assert.equal(mixedView.checks[2].status, 'NOT_TESTED');
assert.equal(mixedView.checks[2].statusBadge, 'NOT TESTED · TEST EDİLMEDİ');
assert.equal(mixedView.checks[3].status, 'UNKNOWN');
assert.equal(mixedView.checks[3].statusBadge, 'UNKNOWN · BELİRSİZ');
assert.equal(mixedView.verdictCode, 'FAIL');
assert.equal(mixedView.isSuccessReady, false);

// 3. Completed with PARTIAL (e.g. source mode NOT_TESTED) must NOT show PASS
const partialView = buildSelfDiagnosticsView({
  id: 'job-partial',
  state: 'completed',
  phase: 'done',
  progress: 100,
  verdict: 'PARTIAL',
  finished_at: 1700000000,
  checks: [
    { id: 'scope', status: 'NOT_TESTED', title: 'Çalışma biçimi', message: 'Kaynak modunda çalışılıyor' },
  ],
});
assert.equal(partialView.verdictCode, 'PARTIAL');
assert.equal(partialView.isSuccessReady, false);
assert.match(partialView.badgeText, /PARTIAL/);

// 4. Cancelled job at 35% must stay at 35% and never show 100% or PASS
const cancelledView = buildSelfDiagnosticsView({
  id: 'job-cancel',
  state: 'cancelled',
  phase: 'done',
  progress: 35,
  verdict: 'UNKNOWN',
  finished_at: 1700000000,
  checks: [{ id: 'scope', status: 'PASS', title: 'Kapsam', message: 'Tamam' }],
});
assert.equal(cancelledView.progress, 35);
assert.equal(cancelledView.fillCode, 'CANCELLED');
assert.equal(cancelledView.isSuccessReady, false);
assert.equal(cancelledView.canCancel, false);

// 5. Completed with all PASS checks and finished_at != null enables isSuccessReady
const passView = buildSelfDiagnosticsView({
  id: 'job-pass',
  state: 'completed',
  phase: 'done',
  progress: 100,
  verdict: 'PASS',
  finished_at: 1700000005,
  rea_used: true,
  report_path: 'C:\\Users\\secret\\AppData\\Local\\Quartz\\diagnostics\\job-pass.json',
  checks: [
    { id: 'scope', status: 'PASS', title: 'Kapsam', message: 'Tamam', evidence: { sha256: 'abc', api_key: 'fixture-private-value' } },
    { id: 'manifest', status: 'PASS', title: 'Manifest', message: 'Tamam', evidence: { compared: 45 } },
  ],
});
assert.equal(passView.isSuccessReady, true);
assert.equal(passView.verdictCode, 'PASS');
assert.equal(passView.reaTagText, 'REA: Kullanıldı');
// Raw report_path and api_key must never appear in evidence or technicalSummaryText
assert(!passView.technicalSummaryText.includes('C:\\Users\\secret'));
assert(passView.technicalSummaryText.includes('"report_saved": true'));
assert(!passView.checks[0].evidenceText.includes('fixture-private-value'));
"""
        self._run_node(harness + diag_js + checks)

    def test_dom_card_updates_in_place_preserves_open_details_and_handles_cancel_and_polling(self):
        diag_js = self._extract_diag_js()
        harness = r"""
const assert = require('node:assert/strict');
let lowSpecHardware = false;
let hiddenState = false;
let cancelCalls = [];
let statusCalls = [];
let timers = [];
function isUiHidden() { return hiddenState; }
function setTimeout(fn, ms) { timers.push({ fn, ms }); return timers.length; }
function clearTimeout() {}

function makeElement(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    className: '',
    dataset: {},
    style: {},
    attributes: {},
    children: [],
    textContent: '',
    open: false,
    disabled: false,
    onclick: null,
    classList: {
      _set: new Set(),
      toggle(cls, force) {
        if (force) this._set.add(cls);
        else this._set.delete(cls);
      },
      contains(cls) { return this._set.has(cls); },
    },
    setAttribute(k, v) { this.attributes[k] = String(v); },
    append(...nodes) { this.children.push(...nodes); },
    appendChild(node) { this.children.push(node); return node; },
    replaceChildren(...nodes) { this.children = [...nodes]; },
    querySelector(sel) {
      if (sel.startsWith('[data-diagnostics-job=')) {
        const id = sel.split('"')[1];
        return this.children.find(c => c.dataset && c.dataset.diagnosticsJob === id) || null;
      }
      return null;
    },
    querySelectorAll(sel) {
      const results = [];
      const walk = (node) => {
        for (const child of (node.children || [])) {
          if (sel === 'details[data-detail-key]' && child.tagName === 'DETAILS' && child.dataset.detailKey) {
            results.push(child);
          }
          if (sel === '[data-diagnostics-cancel]' && child.dataset && child.dataset.diagnosticsCancel) {
            results.push(child);
          }
          walk(child);
        }
      };
      walk(this);
      return results;
    },
  };
  Object.defineProperty(el, 'innerHTML', {
    set() { throw new Error('innerHTML must not be used in diagnostics card'); },
  });
  return el;
}

const chatEl = makeElement('div');
const document = {
  createElement: makeElement,
  getElementById: () => null,
  addEventListener: () => {},
};
let nextStatusJob = null;
const window = {
  pywebview: {
    api: {
      diagnostics_start: async (includeRea) => ({
        status: 'ok',
        data: {
          id: 'job-1',
          state: 'running',
          phase: 'manifest',
          progress: 40,
          message: 'Manifest inceleniyor',
          verdict: 'UNKNOWN',
          checks: [
            { id: 'scope', status: 'PASS', title: '<img src=x onerror=alert(1)>', message: 'Güvenli metin', evidence: { files: 1918 } },
          ],
        },
      }),
      diagnostics_status: async (jobId) => {
        statusCalls.push(jobId);
        return { status: 'ok', data: nextStatusJob };
      },
      diagnostics_cancel: async (jobId) => {
        cancelCalls.push(jobId);
        return {
          status: 'ok',
          data: {
            id: jobId,
            state: 'cancelled',
            phase: 'done',
            progress: 40,
            message: 'Teşhis iptal edildi',
            verdict: 'UNKNOWN',
            finished_at: 1700000100,
            checks: [
              { id: 'scope', status: 'PASS', title: 'Kapsam', message: 'Tamam', evidence: { files: 1918 } },
            ],
          },
        };
      },
    },
  },
};
"""
        checks = r"""
(async () => {
  const started = await startSelfDiagnostics(true);
  assert.equal(started.id, 'job-1');
  assert.equal(chatEl.children.length, 1);
  const card = chatEl.children[0];
  assert.equal(card.dataset.state, 'running');
  assert.equal(card.classList.contains('diag-complete-pass'), false);
  // Normal visible polling delay is 900ms
  assert.equal(timers.at(-1).ms, 900);

  // Open the evidence <details> and verify re-render preserves open=true
  const detailsBefore = card.querySelectorAll('details[data-detail-key]');
  assert.equal(detailsBefore.length, 2);
  detailsBefore[0].open = true;

  // Test low-spec polling interval (1800ms)
  lowSpecHardware = true;
  nextStatusJob = {
    id: 'job-1',
    state: 'running',
    phase: 'rea',
    progress: 70,
    message: 'REA çalışıyor',
    verdict: 'UNKNOWN',
    checks: [
      { id: 'scope', status: 'PASS', title: 'Kapsam', message: 'Tamam', evidence: { files: 1918 } },
    ],
  };
  await pollSelfDiagnostics('job-1');
  assert.equal(chatEl.children.length, 1); // Updated in-place, no duplicate card
  const detailsAfter = card.querySelectorAll('details[data-detail-key]');
  assert.equal(detailsAfter[0].open, true); // Preserved open state!
  assert.equal(timers.at(-1).ms, 1800);

  // Test hidden window polling interval (4000ms)
  hiddenState = true;
  scheduleSelfDiagnosticsPoll('job-1');
  assert.equal(timers.at(-1).ms, 4000);

  // Click cancel button on the card
  const cancelButtons = card.querySelectorAll('[data-diagnostics-cancel]');
  assert.equal(cancelButtons.length, 1);
  await cancelButtons[0].onclick();
  assert.deepEqual(cancelCalls, ['job-1']);
  assert.equal(card.dataset.state, 'cancelled');
  assert.equal(card.querySelectorAll('[data-diagnostics-cancel]').length, 0);
})().catch(e => { console.error(e); process.exitCode = 1; });
"""
        self._run_node(harness + diag_js + checks)

    def test_real_backend_service_snapshot_renders_accurately_in_js_view(self):
        import tempfile
        import time
        from core.self_diagnostics import SelfDiagnosticsService

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "app"
            reports = Path(tmp) / "reports"
            root.mkdir()
            service = SelfDiagnosticsService(base=root, reports=reports)
            started = service.start(include_rea=False)
            deadline = time.monotonic() + 5.0
            snap = started
            while snap["state"] == "running" and time.monotonic() < deadline:
                time.sleep(0.02)
                snap = service.status(started["id"])
            service.shutdown()

        diag_js = self._extract_diag_js()
        script = (
            "const assert = require('node:assert/strict');\n"
            "let lowSpecHardware = false;\n"
            "function isUiHidden() { return false; }\n"
            "const document = { getElementById: () => null, addEventListener: () => {} };\n"
            + diag_js
            + f"\nconst job = {json.dumps(snap)};\n"
            + """
const view = buildSelfDiagnosticsView(job);
assert.equal(view.state, 'completed');
assert.equal(view.verdictCode, 'PARTIAL');
assert.equal(view.isSuccessReady, false);
assert.equal(view.counts.NOT_TESTED, 1);
assert.equal(view.checks[0].status, 'NOT_TESTED');
assert(!view.technicalSummaryText.includes(String(job.report_path || '')));
assert(view.technicalSummaryText.includes('"report_saved": true'));
"""
        )
        self._run_node(script)

    def test_has_active_diagnostics_prevents_ui_idle(self):
        diag_js = self._extract_diag_js()
        script = (
            "const assert = require('node:assert/strict');\n"
            "let lowSpecHardware = false;\n"
            "const document = { getElementById: () => null, addEventListener: () => {} };\n"
            "let thinking = false, chatPollInterval = null, desktopView = { stop_ref: null };\n"
            "let lastUserActivityAt = Date.now() - 30000;\n"
            "function isUiHidden() { return false; }\n"
            "function hasActiveDesktopTask() { return !!desktopView.stop_ref; }\n"
            + diag_js
            + "\n"
            + "function isUiIdle() {\n"
            + "  return !thinking && !chatPollInterval && !hasActiveDesktopTask() && (typeof hasActiveDiagnosticsJob === 'function' ? !hasActiveDiagnosticsJob() : true) && (Date.now() - lastUserActivityAt > 20000);\n"
            + "}\n"
            + "assert.equal(isUiIdle(), true);\n"
            + "activeDiagJobId = 'job-active';\n"
            + "assert.equal(hasActiveDiagnosticsJob(), true);\n"
            + "assert.equal(isUiIdle(), false);\n"
            + "diagPollFailures.set('job-active', 4);\n"
            + "assert.equal(hasActiveDiagnosticsJob(), false);\n"
            + "assert.equal(isUiIdle(), true);\n"
            + "diagPollFailures.delete('job-active');\n"
            + "assert.equal(hasActiveDiagnosticsJob(), true);\n"
            + "activeDiagJobId = null;\n"
            + "assert.equal(hasActiveDiagnosticsJob(), false);\n"
            + "assert.equal(isUiIdle(), true);\n"
        )
        self._run_node(script)


if __name__ == "__main__":
    unittest.main()
