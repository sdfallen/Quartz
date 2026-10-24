# Quartz desktop live retest — 20 October 2026

## Scope and verdict

**LIVE VERIFIED:** Codex and Gemini performed real Windows UIA Edit/Invoke
operations in an owned, disposable classic WinForms window. **Not** a general
all-app, raw mouse/keyboard or Warband acceptance.

The computer was available after the earlier sleep/denied session. No security,
power-plan, Overlay, registry or driver settings were changed.

## Live runs

| Provider/model | Run | Actual fixture event | Outcome |
|---|---|---|---|
| Codex `gpt-6-luna / low` | `2241eb0680034f2d94a0fa0f36e685a5` | `QUARTZ_CODEX`, count1 | VERIFIED, 15.85s |
| Gemini `gemini-3.8-flash-low / low` | `ec357f2911e1479db42dde6c9e5994ec` | `QUARTZ_ANTIGRAVITY`, count1 | VERIFIED, 33.95s |

Both read the actual challenge number4826, changed the real TextBox and invoked
the real Button. The application's Click event wrote a timestamp-checked callback
after the test started. These were not in-memory backend successes or claims
accepted from agent text alone. The successful action sequence was `text`, `ui`
(UIA Invoke), **not** raw coordinate mouse injection.

Evidence under `labs/desktop-bridge-20261020/`:

- `native-codex-20261020-233241.json`.
- `native-antigravity-20261020-233344.json`.
- `native-fixture-state.json` (last fixture event; the per-run JSONs preserve both).

## Defects found and fixes

1. Old Codex tool binding supplied `{}` instead of action parameters. The
   missing snapshot was reported as stale even when observation age was ~2s.
   A minimal all-required schema probe delivered parameters correctly. The
   production catalog now uses a flat, all-required, nullable-for-unused-fields
   schema. Parameter transport then passed on the synthetic backend, followed
   by the real classic Windows successes above. No stale timeout was relaxed.
2. UIA's internal snapshot ID and broker's action ID shared a field name in
   model output. Internal handle is now omitted from agent-visible data; the
   backend retains it. Regression test verifies this separation.
3. Windows MCP pipe encoding was cp1254. The helper now explicitly uses UTF-8
   for stdin/stdout, including non-ASCII errors and Turkish text. A subprocess
   test with an intentionally cp1254 parent verifies a Turkish/Chinese JSON ID.
4. Added separate mismatch/expiry diagnostics and safe action metadata; no
   capability or typed text is logged in broker audit. Foreground diagnostics
   record only HWND/PID. A single focus request gets up to0.5s acknowledgement
   wait; no repeated focus loop or background input was added.

## Failures and limitations retained

- The pywebview/HTML fixture returned UIA COM `0x80070057` (invalid parameter)
  during a coordinate-click attempt. No Click callback was observed. This is
  **FAILED for that fixture**, not overwritten by the classic-window passes.
- A separate raw mouse/Space test (`c4afab0f385e42c480c0cd253edbefe4`) stopped
  on foreground loss before successful actions. Raw coordinate/key acceptance
  remains **NOT VERIFIED / BLOCKED by focus loss**.
- Independent Computer Use capture again timed out (`FrameArrived`), with no
  accessibility tree. It is not used to claim a successful independent visual
  review. Product image readback + application callback are the live evidence.
- Read-only main/worker UIA point probes succeeded; no COM-apartment rewrite was
  justified by that probe. The HTML COM-error root cause remains unresolved.
  The [pywinauto COM guidance](https://pywinauto.readthedocs.io/en/latest/HowTo.html#com-threading-model)
  was checked, but threading was not declared the cause without evidence.
- Some earlier runs were cancelled on actual foreground change. One recorded
  Explorer PID6312. No foreground guard was disabled. User input takeover is
  not a gameplay bug.
- Gemini attempted a terminal fallback after tool errors; the CLI rejected it.
  No command wildcard or dangerous skip-permissions flag was granted. Its
  existing warning that terminal sandbox is unavailable on this Windows host
  still applies; desktop scope is not OS-wide file isolation.
- Warband remains disabled in the generic broker pending its UM protected-save
  adapter; no mod, save, battle-size or gameplay changes occurred here.

## Regression and preservation

Final full source run: **225 tests PASS, 25.095s**. One earlier full run had a
checkpoint-test archive KeyError; isolated rerun and final full rerun passed.
The earlier failure is not hidden or counted as a pass.

Pre-change checkpoint:
`C:\Users\LENAVO\.codex\backups\quartz-desktop-live-fix-20261020\agent-1792526062-382f00c6ff174d8cb48ea4f95a112a2e.zip`.

No user Quartz process was closed. Owned fixture processes were closed after
tests; unrelated existing agent processes were not targeted. Some shell sessions
were interrupted by new user turns; fixture and runner now share one invocation
to avoid a detached test window surviving its operator.

Runtime results above belong to source-run adapters, not automatically to the
previously running EXE. Packaging/deployment receipt is recorded separately.

## Packaged delivery

Updated `dist/Quartz/Quartz.exe`; SHA256:
`fc001fc364df5bd3c9736395080543df6ce89f7ce69ab5bfa9136acbf3a0d5e7`.
Old complete distribution remains at
`C:\Users\LENAVO\.codex\backups\quartz-before-desktop-bridge-20261020-234438`.
All copied local data files were byte-identical. Source `.env`, memory and
conversations were unchanged across final validation.

Receipt, full final regression log and packaged code verification:
`C:\Users\LENAVO\.codex\backups\quartz-desktop-live-package-20261020-234000`.
Packaged GUI/runtime/broker code matched source and helper hash matched build.
Packaged helper passed UTF-8 Unicode-ID initialization and denied use without
a live capability. These are BUILT/protocol results, not a new GUI live run.

The GUI was not launched automatically after delivery. No active desktop grant,
fixture or CLI operator was left running. The package is still experimental:
classic UIA is verified; web/pixel input and Warband integration are not.
