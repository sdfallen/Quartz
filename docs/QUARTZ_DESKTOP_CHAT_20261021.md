# Quartz — main-chat desktop entry, 21 October 2026

## Scope

The main workspace now exposes **Bilgisayar görevi başlat** (Alt+B). Opening the
draft or preparing a request does not grant control. The existing bounded
window/log/duration consent remains mandatory. Default roles are Codex operator
and Gemini/Antigravity observer. Explicit complementary reversed roles remain
supported. Normal chat and file access do not imply desktop authority.

The toolbar reports actual broker state: normal chat, pending approval, active
operator, preparing, or released. Observer analysis after operator release is not
reported as active input control. Stop/cancel calls are generation-bound. Pending
requests expire after ten minutes and cannot expand an active grant.

## Changed components

- `core/desktop_task_ui.py`: pure intent/help and actual-state formatting.
- `core/chat_coordination.py`: optional default roles, bounded pending lifecycle.
- `core/desktop_broker.py`: session identity for generation-bound Stop.
- `core/agent_chat.py`: accurate ordinary-chat capability guidance.
- `gui.py`, `assets/workspace.css`: visible entry, draft, consent cancellation,
  actual-state toolbar and scoped Stop. No new authority from natural language.
- `tests/test_desktop_task_ui.py`, existing coordination tests: regressions.
- `scripts/desktop_chat_acceptance.py`: isolated real-agent GUI-API test.
- `scripts/workspace_preview.py`: authority-free browser preview.
- `scripts/verify_desktop_package.py`: packaged task-UI code verification.

## Evidence boundaries

| Layer | Result | Evidence |
|---|---|---|
| Real GUI-local API / Native broker / CLI / Squad | VERIFIED: A callback1, B callback1, C denied; normal → pending → active → released | `labs/desktop-chat-20261021-130215/acceptance.json` |
| Input method for that passing run | UIA Invoke, **not physical pixel click** | Same archive and operator/observer logs |
| Pixel-input attempt | FAILED: operator chose coordinates outside actual buttons; A/B callbacks absent, C remained denied | `labs/desktop-chat-20261021-125950/acceptance.json` |
| Initial harness retry | FAILED before role execution: string concatenation; harness fixed | `labs/desktop-chat-20261021-130200/failure.json` |
| Browser visual/DOM preview | VERIFIED in synthetic preview: draft, prepare, pending state, cancel, local capability help; no consent granted | `labs/desktop-chat-ui-preview.png` |
| Final safe regressions | VERIFIED: 309 tests, 49.566 seconds | Package `regression-final.log` |
| Final actual packaged code/helper/CSS/icon checks | VERIFIED; helper also rejects ungranted calls | Package `package-verification.json`, `deployment-receipt.json` |
| Installed main-window entry/status | AX VERIFIED: task button with Alt+B help, Normal sohbet, no active grant | `labs/desktop-chat-packaged-ax.txt` |
| Installed draft opening/visual capture | BLOCKED: `failed to activate captured window`; one refreshed activation also failed; capture `FrameArrived timed out` | Current native computer-use observations; no blind retries or permission bypass |
| Packaged main-window consent → real-agent full task | NOT VERIFIED; API test is not an actual approval-button click | Requires separate explicit user consent through card |

The preview is not a screenshot of the installed native app. The live API harness
uses disposable IPC and a bounded fixture grant; it does not modify app history.

## Preservation and delivery

Before edits, source and distribution were preserved under
`C:/Users/LENAVO/.codex/backups/quartz-desktop-chat-before-20261021`.
The source archive is
`source/agent-1792576132-7254e72c949044d0ab2e98056df0393e.zip`.

Final package, safe-suite log, code verification and deployment receipt are under
`C:/Users/LENAVO/.codex/backups/quartz-workspace-package-20261021-125939`.
The receipt is authoritative for installed EXE hash, original distribution backup,
and before/after user-data hashes. Deployment refuses a running Quartz process.
It preserves current installed data, not stale root copies, and keeps the old
distribution recoverable. No reset/clean, registry/driver/Overlay/security change,
Warband launch, ASTER write or public upload is part of this work.

Installed EXE SHA256:
`21d1404c79bf441612c8a228211d62e1f95fbd1c7e6e86ff39fc87db5242dbb6`.
Old closed distribution is preserved at
`C:/Users/LENAVO/.codex/backups/quartz-before-desktop-bridge-20261021-192153`.
After launch, installed conversations remain SHA256
`991e0c3650cd407e66d274018a8fcd21a6cc69da97ef30336603858cdf62be9f`;
root conversations/memory and both .env hashes also remain unchanged. Only
expected entry/runtime logs grow. New Quartz PID14648 was launched by this test;
no permission was granted and no fixture/MCP helper remains active. PID is
historical evidence, not authority to terminate a future process.

Warband remains blocked in the generic desktop bridge: a separate Universal
Modder protection adapter is still required. This UI change does not make ASTER
desktop tasks fully accepted.

## Next acceptance

Use the visible task button, enter a harmless scoped task, select actual allowed
windows plus the intended observer log and duration, then personally approve the
card. A full packaged-flow acceptance must distinguish actual pixel input from
UIA invocation, and must inspect real callbacks rather than agent claims.
