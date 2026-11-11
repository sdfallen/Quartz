# Frontend finalization — 2026-11-02

Baseline: `eb40780`; branch: `codex/pyramid-finalization-20261102`.

`gui.py` now assembles `SHELL_MARKUP + SCRIPT_DOCUMENT`. It no longer owns the application JavaScript. No Api method, DOM identifier, bridge name, style, model selection, animation or application behavior was changed in this slice.

## Static composition

`ui/app_js.py` imports fragments in this exact order and joins them without adding separators or wrappers. They intentionally share the existing lexical script scope; this is a source-boundary refactor, not an ES-module migration.

| Fragment | Responsibility | JS lines |
|---|---|---:|
| `ui/js_setup.py` | DOM bindings, onboarding and connection setup | 196 |
| `ui/js_messages.py` | Message rendering, scroll, thinking and task/event presentation | 460 |
| `ui/js_chat.py` | Conversations, agent/model selection, sending and permissions | 612 |
| `ui/js_desktop.py` | Desktop task state, controls and permission rendering | 127 |
| `ui/js_diagnostics.py` | Application diagnostics, evidence and repair cards | 683 |
| `ui/js_advanced.py` | Advanced agent/operator panels, providers, compact and voice controls | 348 |
| `ui/js_lifecycle.py` | Activity, polling, keyboard wiring and bootstrap | 214 |

All fragments are ordinary statically imported Python modules, so existing PyInstaller import analysis can collect them without new data files. No remote script, new UI runtime or Notion control is introduced.

## Preservation evidence

The script document was compared directly with the `_HTML_BODY` literal extracted by AST from `git show eb40780:gui.py`. Equality is exact. Rebuilding the baseline and current document with the same existing assets produces byte-identical `_HTML`:

- HTML SHA-256: `db61e6fb9e979dd3eb39800881afd0d08fe7a0f5563f21512ee30927a695bd02`
- Application JS SHA-256: `a4c633409855a358c6ea0616e594f48d6a50fa76f2b79c4dc479a9aa4a7ce4b9`

`scripts/check_gui_javascript.py` reads the same static composition used by the GUI rather than scanning the bridge source. It rejects missing/empty fragments, malformed/empty/duplicate script blocks and a composition mismatch, then checks the entire shipped script together with Node.

## Verification

- `python -B scripts/check_gui_javascript.py`: PASS, Node exit 0.
- `python -B scripts/run_safe_tests.py tests.test_gui_frontend_boundary tests.test_gui_modern_theme tests.test_gui_connection_polling tests.test_chat_keyboard tests.test_gui_compact tests.test_notion_tools_ui tests.test_pyramid_integration_review`: PASS, 70 tests.
- `git diff --check`: PASS.

These are SOURCE/STATIC and offline regression results. No packaged build or live application/model test was performed by this frontend task. No user profile, credentials, conversations, ASTER data or running application was accessed.

## Integration handoff

The frontend bridge file is released for the backend owner's Api/service decomposition. Preserve its two assembly lines and static UI imports. Package verification should explicitly check `ui.app_js` plus the seven fragment modules when inspecting the frozen archive; the source dependencies are already static. The parent owns final full-suite, package and live acceptance.
