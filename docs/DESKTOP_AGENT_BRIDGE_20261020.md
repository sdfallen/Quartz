# Quartz desktop operator — 20 October 2026

## Delivery status

Implemented first, window-scoped desktop operator slice. **Not a verified
whole-computer/game operator.** Real Windows input acceptance is BLOCKED in
this session; no real click/text success is claimed.

The Agent Center now has a separate computer-operator section, target window
selector, per-task consent, model selection, status and stop button. Normal chat
and file permission levels do not implicitly grant desktop access.

## Boundaries

- One provider owns input per session; an OS-released byte lock also excludes a
  second Quartz process using this bridge. This does not lock out unrelated
  automation tools or human input inside the same window.
- Host grants bind HWND + PID + process start time + executable. Moving the
  window invalidates the previous geometry. Foreground loss revokes the grant;
  there is no repeated force-focus loop.
- 15-second, single-use observations; one action then fresh observation. Default
  session 10 minutes, maximum 30 minutes, at most 100 actions, holds <=1 second.
- A random, expiring capability protects a separate loopback endpoint. Desktop
  grants are GUI-local, **not** added to the unauthenticated legacy IPC API.
  Tokens travel in child environment, not prompt/CLI arguments/global config.
- Allowed actions: bounded window click, literal text into a verified focused
  Edit control, limited keys, short hold, and selected UIA actions. No shell,
  arbitrary application launch, clipboard export, elevation or Windows-key chords.
- Password/security/authentication applications and consequential named controls
  are denied. Labels/prompt rules are additional guards, not proof that every
  consequential action in every custom app can be classified perfectly.
- Protected Warband input is intentionally denied until the Universal Modder
  multi-root save/checkpoint adapter is integrated and live tested. No mod, Native
  installation, game saves, battle-size config or Gate B acceptance was changed.
- Multi-app workflows and automatic approved-window handoff are not implemented.
  This is not unrestricted unattended machine authority.

## Provider integration

Codex: per-run MCP configuration, only three enabled tools, their explicit
approval is scoped to the user-confirmed desktop capability. CLI stays read-only;
no global Codex config or dangerous bypass flag was added. The supported MCP
approval and environment-forwarding mechanism was checked against
[official OpenAI documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Antigravity: registered the `quartz-desktop` stdio server through `agy mcp add`.
`~/.gemini/config/mcp_config.json` contains the helper command, not a capability.
Created previously absent `~/.gemini/antigravity-cli/settings.json` with ONLY:

```
mcp(quartz-desktop/desktop_focus)
mcp(quartz-desktop/desktop_observe)
mcp(quartz-desktop/desktop_act)
```

No wildcard tool grant, terminal/file allow-rule, credentials or provider-model
settings were changed. Existing settings, if present on another installation,
are merged with a timestamped pre-change backup and deny rules preserved.
Outside an explicitly granted Quartz run the server has no desktop token.

**Antigravity limitation:** `--mode auto --sandbox` reports that terminal sandbox
is unavailable on this Windows host and falls back to default mode. This is NOT
OS-enforced read-only file isolation. The GUI explicitly warns before these
sessions; the desktop broker scope remains enforced independently. No dangerous
skip-permissions switch is used to make tests pass.

## Evidence and outcomes

SOURCE/STATIC: 221 tests passed (21.235 seconds), including capability auth,
expiration, strict confirmation, concurrent owner rejection, stale reference,
PID/start-time reuse, layout change, foreground takeover, cancellation,
standalone-helper denial, exact AGY grants and per-run model/MCP routing.
Embedded JavaScript `node --check` passed. `git diff --check` passed (existing
LF/CRLF warnings only).

LIVE PROVIDER / TRANSPORT: Codex `gpt-6-luna / low` and Antigravity
`gemini-3.8-flash-low / low` both focused/observed a **synthetic in-memory
transport fixture** and correctly read `7319` from real MCP image content.
No native window or native input was involved in that successful test.
Evidence: `labs/desktop-bridge-20261020/mcp-provider-transport*.json`.

Initial attempts failed because CLI tool approval was not yet scoped; AGY plan
mode produced a plan rather than executing. Those are not counted as successes.
The working transport configuration uses the exact explicit grants above.

LIVE WINDOWS INPUT: BLOCKED. Created only the disposable local test window
`Quartz Disposable Desktop Test`, PID12940, start19:53:23.768, handle723210.
Codex and AGY attempts could not acquire foreground; action count was zero.
Latest diagnostic record: `native-codex-20261020-195700.json`. Broker audit says
`Could not acquire the selected window`, not "success".

Independent Computer Use observation also timed out (`FrameArrived`), then its
safe activation check failed `GetCursorPos: access denied (0x80070005)`. Existing
LockApp/LogonUI processes alone are not conclusive proof of why input is denied.
No lock-screen interaction, forced focus, elevation, security change or bypass
was attempted. Added read-only cursor-access preflight so new native sessions
fail before starting a model when interactive input is unavailable.

The owned fixture was stopped after exact command/start-time verification.
The unrelated existing Python process was not touched. No desktop session or
agent CLI run was left active.

## Source / recovery

Pre-change dirty source preserved at:
`C:\Users\LENAVO\.codex\backups\quartz-desktop-bridge-20261020-194217`.
New code: `core/desktop_broker.py`, `desktop_mcp.py`, `desktop_native.py`,
`desktop_agents.py`. Small runtime hooks in both CLI adapters and GUI panel.
Packaging adds a separate console stdio helper (not a recursive GUI EXE).

Local Windows validation and user-data separation followed the Computer Use
skill; the denied input session was not bypassed. No memory files were updated.

## Next acceptance, after interactive desktop access is available

1. Run `scripts/desktop_acceptance_fixture.py` (disposable local window).
2. Run the native acceptance once per provider, independently observe that the
   correct text and click count actually appear. Keep zero-action failures.
3. Verify foreground takeover + stop in a live session.
4. Verify the packaged GUI and helper end-to-end, not only source tests.
5. Only then integrate the existing UM game-control/checkpoint/lease systems;
   test disposable/read-only Warband fixtures before allowing protected saves.

Until then, Windows input and Warband control remain NOT LIVE VERIFIED.

## Packaged handoff

- Updated in place: `dist/Quartz/Quartz.exe`.
- SHA256: `82a917a720b728677edbeef3ebcff6189da1cd8a378517b43aa15684d2a7074a`.
- Previous complete distribution preserved:
  `C:\Users\LENAVO\.codex\backups\quartz-before-desktop-bridge-20261020-200210`.
- Six top-level data/log files were copied byte-identically; no reset of
  conversations, project selection or `.env`. Source `.env`, memory and
  conversations also hash-identical across final validation.
- Delivery evidence:
  `C:\Users\LENAVO\.codex\backups\quartz-desktop-package-20261020-200000`:
  `regression-final.log`, `package-verification.json`, `deployment-receipt.json`.
- Six packaged GUI/runtime/broker modules matched source code signatures; the
  standalone helper hash matched its build. The packaged helper successfully
  initialized, listed tools and denied an observe call with no parent capability.
  That is **BUILT + protocol acceptance**, not native Windows input acceptance.
- Final source checkpoint: `source-checkpoint/agent-1792515745-2088d081512140029848789afc33a5e4.zip`,
  161 files / 3511651 bytes, under that delivery evidence directory. Generated
  before this final receipt paragraph; captures all production changes/tests.
- GUI intentionally not launched into the denied interactive session. No active
  computer-control grant or test CLI was left behind. Existing user applications
  were not closed.
