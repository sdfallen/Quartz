# Desktop pixel input repair — 21 October 2026

## Outcome and scope

Source-run real CLI → MCP → native backend tests now execute a coordinate mouse
click followed by Space in the owned local HTML/WebView fixture. The fixture's
real JavaScript Click callback records count2; no UIA Invoke was used for these
runs. This is bounded-window input, not unrestricted computer or game support.

| Test | Evidence under `labs/desktop-bridge-20261020/` | Actual callback |
|---|---|---|
| Before fix, Codex | `native-codex-20261020-235450.json` | none; ElementFromPoint COM error |
| Codex Luna/low, first repair | `native-codex-20261020-235943.json` | count2 |
| Gemini Flash/low, first repair | `native-antigravity-20261021-000038.json` | count2 |
| Final guard regression, Codex | `native-codex-20261021-000200.json` | count2 |
| Classic UIA text/invoke regression, Codex | `native-codex-20261021-000227.json` | QUARTZ_CODEX, count1 |
| Later Gemini rerun with final guard additions | `native-antigravity-20261021-000327.json` | BLOCKED before input: could not focus; foreground PID5780 |

The raw-input task explicitly forbids action=ui/Invoke. Broker audit records
successful `click` then `key`; the callback is accepted only if written after
that test began. These are real test application events, not agent claims.

## Diagnosis and targeted change

The fresh before-fix trace locates `0x80070057` inside UIA ElementFromPoint,
before any pyautogui click. Read-only differential probe
`uia-point-mta-ab-before-fix.json` shows point lookup initially passing, failing
after a safety scan's short-lived COM scope, and passing in an operation-wide
MTA scope. Recreating only the UIA client after failure did not fix that case.

`core/desktop_control.py` now initializes MTA with CoInitializeEx and balances
CoUninitialize only after successful initialization. An existing incompatible
apartment is preserved on RPC_E_CHANGED_MODE, rather than silently ignoring
that result and uninitializing an apartment we did not initialize.

`core/desktop_native.py` keeps one outer COM scope across each native operation,
including nested safety scan and point lookup. No blanket exception swallowing,
UIA guard removal, focus retry loop or forced background input was introduced.
This follows Microsoft's [UI Automation threading guidance](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading).
The differential test establishes the lifecycle-sensitive failure; it does not
claim to prove every internal Windows provider failure mechanism.

Additional safety: pixel targets are checked for password/authentication as
well as consequential names. Foreground is rechecked immediately before raw
click/key input, after the potentially slow UIA checks.

## Regression and preservation

- 233 tests PASS; embedded GUI JavaScript syntax PASS; git diff whitespace PASS.
- Tests cover COM balance, changed-mode preservation, failure propagation,
  operation scope, relative click coordinates, private/critical targets,
  occlusion and late foreground loss.
- Pre-change checkpoint:
  `C:\Users\LENAVO\.codex\backups\quartz-pixel-fix-20261020\agent-1792529739-e3302039c75444dbafde0e2373171caa.zip`.
- Package and deployment receipts are stored in
  `C:\Users\LENAVO\.codex\backups\quartz-pixel-package-20261021-000300`.

## Delivery

Installed `dist/Quartz/Quartz.exe`, SHA256
`f7b2d2c3ce397174f3d6522f0519e1134e8006919c0dcfbe619044cb04fbdabb`.
The packaged GUI, controller, native backend, broker and CLI adapters matched
source. The helper hash/protocol and capability-denial checks passed.
Deployment reran all233 tests successfully and preserved the old full distribution
at `C:\Users\LENAVO\.codex\backups\quartz-before-desktop-bridge-20261021-001157`.
All copied local data files were byte-identical. Source .env, memory and
conversations also retained their initial hashes. No user Quartz process was
closed; the updated GUI was intentionally not started. Owned test windows,
provider runs and capabilities were closed/revoked by the acceptance runner.

## Limits retained

The live results above use source-run adapters. Packaged code/protocol checks
are a separate BUILT level, not automatically a packaged GUI live acceptance.
Warband remains denied in this generic bridge until its Universal Modder
protected-save adapter exists. No Warband files, saves or configuration changed.

This does not prove every website/application works. In particular, raw text
typing into arbitrary renderer-owned web fields, launching new targets,
cross-application handoff and elevated/secure surfaces are not newly accepted.
Foreground takeover still cancels the grant; one provider owns input at a time.
The existing Gemini terminal-sandbox limitation is unchanged.

Earlier failed HTML/pixel runs remain recorded in the 20 October report; the
new successes do not erase them or count as user acceptance.
