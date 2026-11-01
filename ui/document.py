"""Assemble the single HTML document that pywebview loads.

``gui.py`` still owns the body markup and the application JavaScript (the
JavaScript syntax check and many tests read them from there). This module owns
the document head, the base theme and the offline asset injection that used to
run at the bottom of ``gui.py``, plus two frontend layers that gui.py does not
own: the modern theme (``ui/theme.py``) and the Notion tool-status renderer.
"""
import base64
import sys
from pathlib import Path

from ui.styles import BASE_CSS
from ui.theme import MODERN_CSS

WORKSPACE_CSS = "workspace.css"
BRAND_MARK = "branding/quartz-q-48.png"
BRAND_PLACEHOLDER = '<div class="brand">QUARTZ</div>'


def asset_root() -> Path:
    """Source checkout ``assets/`` or the PyInstaller bundle's ``assets/``."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parents[1]
    return Path(base) / "assets"


def brand_markup(png: bytes) -> str:
    return ('<div class="brand"><img class="brand-icon" alt="Quartz Q" width="28" height="28" '
            'src="data:image/png;base64,' + base64.b64encode(png).decode("ascii") + '">QUARTZ</div>')


# Notion local-tool status for the main chat (docs/notion-tools/PLAN.md, the
# local ``notion_tools`` field). This is a renderer only: it never calls the
# pywebview API, never approves, never stops. Approval stays on the existing
# permission card and Stop on the existing desktop task strip. gui.py feeds it
# with ``window.QuartzNotionTools.update(payload, {conversationId, agent})``.
# All text goes through textContent. Shipped with its own id so the
# gui.py script-block contract (scripts/check_gui_javascript.py) is unchanged.
NOTION_TOOLS_SCRIPT_ID = "quartz-notion-tools"
NOTION_TOOLS_SCRIPT = r"""
(function () {
  'use strict';
  var SCHEMA = 1;
  var ACTIVE = { observing: 1, awaiting_approval: 1, executing: 1, verifying: 1 };
  var TERMINAL = { completed: 1, blocked: 1, failed: 1, cancelled: 1 };
  var AVAILABILITY = {
    unavailable: ['Yerel araçlar bağlı değil', 'Notion bu sohbette metin ve kod analizi yapabilir; bilgisayarınızda işlem yapamaz.'],
    checking: ['Araç bağlantısı kontrol ediliyor', 'Kontrol bitene kadar yerel işlem başlatılmaz.'],
    ready: ['Yerel araçlar hazır', 'Her işlem için kapsam izin kartında sorulur.'],
    blocked: ['Araç bağlantısı engellendi', 'Yerel işlem başlatılmaz.']
  };
  var STATES = {
    observing: 'Gözlem yapılıyor',
    awaiting_approval: 'İzin bekleniyor',
    executing: 'Yürütülüyor',
    verifying: 'Sonuç doğrulanıyor',
    blocked: 'Engellendi',
    failed: 'Başarısız oldu',
    cancelled: 'İptal edildi'
  };
  var COMPLETED = {
    verified: ['Tamamlandı ve doğrulandı', 'verified'],
    observed: ['Tamamlandı · sonuç gözlendi, doğrulanmadı', 'observed'],
    none: ['Ajan tamamlandığını bildirdi · Quartz doğrulamadı', 'unverified']
  };
  var OPERATORS = { notion: 'Notion', codex: 'Codex', antigravity: 'Antigravity', quartz: 'Quartz' };

  var view = { el: null, key: '', task: null, retired: Object.create(null) };

  function text(value, limit) {
    var s = value == null ? '' : String(value);
    return s.length > (limit || 600) ? s.slice(0, limit || 600) + '…' : s;
  }
  function make(tag, cls, content) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (content !== undefined) node.textContent = text(content);
    return node;
  }
  function mount() {
    if (view.el) return view.el;
    var el = document.getElementById('notionToolsPanel');
    if (!el) {
      el = document.createElement('section');
      el.id = 'notionToolsPanel';
      el.className = 'notion-tools';
      el.setAttribute('aria-label', 'Notion araç durumu');
      el.hidden = true;
      var anchor = document.getElementById('desktopTaskBar');
      if (!anchor || !anchor.parentNode) return null;
      anchor.parentNode.insertBefore(el, anchor.nextSibling);
    }
    view.el = el;
    return el;
  }
  function hide() {
    var el = mount();
    if (el && !el.hidden) { el.hidden = true; el.replaceChildren(); }
    view.key = '';
  }
  function stopAvailable() {
    var stop = document.getElementById('btnDesktopTaskStop');
    return !!(stop && !stop.hidden && !stop.disabled);
  }

  // Decide whether an incoming task replaces, updates or must be ignored.
  function acceptTask(task) {
    if (!task || typeof task !== 'object' || !task.task_id) return null;
    var id = String(task.task_id);
    if (view.retired[id]) return 'stale';
    var current = view.task;
    if (current && current.id === id) {
      if (current.terminal) return 'stale';
      var rev = Number(task.revision);
      if (isFinite(rev) && isFinite(current.revision) && rev <= current.revision) return 'stale';
      return 'update';
    }
    if (current && current.id !== id) view.retired[current.id] = true;
    return 'new';
  }

  function update(payload, context) {
    context = context || {};
    if (!payload || typeof payload !== 'object' || payload.schema_version !== SCHEMA) { hide(); return 'hidden'; }
    var task = payload.task || null;
    if (task && task.conversation_id && context.conversationId && task.conversation_id !== context.conversationId) {
      hide(); return 'other-conversation';
    }
    var decision = task ? acceptTask(task) : null;
    if (decision === 'stale') return 'stale';
    if (task && decision) {
      var state = String(task.state || '');
      view.task = {
        id: String(task.task_id),
        revision: isFinite(Number(task.revision)) ? Number(task.revision) : NaN,
        terminal: !!TERMINAL[state]
      };
    } else if (!task && view.task) {
      view.retired[view.task.id] = true;
      view.task = null;
    }
    var availability = AVAILABILITY[payload.availability] ? payload.availability : 'unavailable';
    if (!task && context.agent !== 'notion') { hide(); return 'hidden'; }
    var key = JSON.stringify([availability, payload.message, payload.capabilities, task, stopAvailable()]);
    if (key === view.key) return 'unchanged';
    var el = mount();
    if (!el) return 'no-mount';
    view.key = key;
    render(el, payload, availability, task);
    return task ? 'task' : 'availability';
  }

  function render(el, payload, availability, task) {
    el.replaceChildren();
    el.dataset.availability = availability;
    var head = make('div', 'notion-tools-head');
    head.append(make('span', 'notion-tools-dot'));
    var copy = make('div', 'notion-tools-copy');
    if (!task) {
      delete el.dataset.state; delete el.dataset.verification;
      copy.append(make('strong', 'notion-tools-title', AVAILABILITY[availability][0]));
      copy.append(make('span', 'notion-tools-detail', payload.message || AVAILABILITY[availability][1]));
      if (availability === 'ready' && Array.isArray(payload.capabilities) && payload.capabilities.length) {
        copy.append(make('span', 'notion-tools-caps', 'Araçlar: ' + payload.capabilities.slice(0, 8).map(function (c) { return text(c, 40); }).join(', ')));
      }
      head.append(copy); el.append(head); el.hidden = false; return;
    }
    var state = String(task.state || '');
    var verification = ['verified', 'observed', 'none'].indexOf(task.verification) >= 0 ? task.verification : 'none';
    var title, badge;
    if (state === 'completed') { title = COMPLETED[verification][0]; badge = COMPLETED[verification][1]; }
    else { title = STATES[state] || 'Durum bilinmiyor'; badge = STATES[state] ? state : 'unknown'; }
    el.dataset.state = (STATES[state] || state === 'completed') ? state : 'unknown';
    el.dataset.verification = badge;
    var operatorId = String(task.operator || '');
    var operator = OPERATORS[operatorId] || 'Belirtilmedi';
    var title_el = make('strong', 'notion-tools-title', title);
    title_el.setAttribute('aria-live', 'polite');
    copy.append(title_el);
    var who = make('span', 'notion-tools-operator');
    who.dataset.operator = OPERATORS[operatorId] ? operatorId : 'unknown';
    who.textContent = operatorId === 'notion' ? 'Yürüten: Notion'
      : OPERATORS[operatorId] ? 'Yürüten: ' + operator + ' · Notion bu işi devretti'
      : 'Yürüten: belirtilmedi';
    copy.append(who);
    if (task.message) copy.append(make('span', 'notion-tools-detail', task.message));
    var request = task.request && typeof task.request === 'object' ? task.request : null;
    if (state === 'awaiting_approval') {
      var scope = request && (request.scope_summary || request.tool_name);
      copy.append(make('span', 'notion-tools-detail', scope
        ? 'İstenen kapsam: ' + text(scope, 200) + '. Onay veya ret izin kartından verilir.'
        : 'Onay veya ret izin kartından verilir.'));
    }
    if (ACTIVE[state]) {
      copy.append(make('span', 'notion-tools-stop', stopAvailable()
        ? 'Durdurmak için görev şeridindeki Görevi durdur düğmesini kullanın.'
        : 'Bu görev için Quartz durdurma yolu görünmüyor; yeni işlem başlatılmaz.'));
    }
    head.append(copy);
    el.append(head);
    var details = document.createElement('details');
    details.className = 'notion-tools-details';
    details.append(make('summary', '', 'Teknik ayrıntılar'));
    details.append(make('pre', '', JSON.stringify({
      task_id: task.task_id, session_id: task.session_id, revision: task.revision,
      state: task.state, operator: task.operator, verification: task.verification,
      request: request ? { tool_name: request.tool_name, scope_summary: request.scope_summary } : undefined
    }, null, 2)));
    el.append(details);
    el.hidden = false;
  }

  function reset() {
    if (view.task) view.retired[view.task.id] = true;
    view.task = null;
    hide();
  }

  window.QuartzNotionTools = Object.freeze({ version: SCHEMA, update: update, reset: reset });
})();
"""


# Everything before the stylesheet. The leading newline matches the former
# ``r\"\"\"`` literal in gui.py, which started with a line break. The Notion
# renderer only defines an object here; it touches the DOM on first update.
DOCUMENT_HEAD = (
    "\n"
    "<!DOCTYPE html>\n"
    '<html lang="tr">\n'
    "<head>\n"
    '<meta charset="UTF-8">\n'
    "<title>Quartz</title>\n"
    '<script id="' + NOTION_TOOLS_SCRIPT_ID + '">' + NOTION_TOOLS_SCRIPT + "</script>\n"
)


def build_document(body: str, assets: Path | None = None) -> str:
    """Return the full document.

    ``body`` is everything from ``</head>`` to ``</html>``, exactly as it sits
    in gui.py. The modern theme (``ui/theme.py``) is appended after
    ``workspace.css`` so it wins the cascade. ``workspace.css`` is required (as before, a missing file raises);
    the brand mark is optional and only replaces the text placeholder when the
    PNG exists. The Notion tool-status renderer ships in ``DOCUMENT_HEAD``;
    it only defines ``window.QuartzNotionTools`` and mounts lazily on update.
    """
    assets = asset_root() if assets is None else Path(assets)
    html = DOCUMENT_HEAD + "<style>\n" + BASE_CSS + "</style>" + body
    workspace_css = (assets / WORKSPACE_CSS).read_text(encoding="utf-8")
    html = html.replace("</head>", "<style>" + workspace_css + "</style>"
                        + '<style id="quartz-modern-theme">' + MODERN_CSS + "</style></head>")
    mark = assets / BRAND_MARK
    if mark.is_file():
        html = html.replace(BRAND_PLACEHOLDER, brand_markup(mark.read_bytes()))
    return html
