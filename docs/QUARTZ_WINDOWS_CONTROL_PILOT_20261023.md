# Quartz Windows control pilot — 23 October 2026

## Decision

Use `sbroenne/mcp-windows` as a reference for Windows UIA, screenshot and
physical-coordinate handling, **not** as a raw MCP server connected to Codex or
Gemini. Its broad app/process/clipboard/input tool set and global CLI daemon do
not enforce Quartz's exact HWND/PID/start/exe grant, one-operator lease,
single-use observation, Stop/user-takeover or per-app approval. A tool filter
is not a Windows sandbox. The existing Quartz Desktop Broker remains the only
authority boundary; no new API-key billing or provider login was introduced.

Reference inspected: upstream commit `3fd081571e0206c718f860627f98eaa41bb8a88d`.
The upstream checkout is isolated at
`C:\Users\LENAVO\.codex\vendor\mcp-windows-20261023`; it was not executed or
registered. It targets .NET SDK `10.0.401`; this computer has `10.0.400`.
Quartz does not acquire a new runtime dependency from this pilot.

## Measured failure and narrow changes

The older pixel-input A/B/C run at
`labs/multiwindow-codex-20261023-172357/acceptance.json` recorded a permitted
click at screenshot coordinate `(350,210)`, but fixture A's button callback
remained zero. Its actual screenshot places that point at the bottom edge of
the button, not its center. The same screenshot shows fixture C's error dialog;
three processes wrote the same observer log without retry. This evidence does
not establish a general Quartz DPI bug.

- The disposable fixture now retries sharing violations, preserves a separate
  error marker if all attempts fail, and does not present a modal error over
  the test target for a transient log race.
- The pixel acceptance prompt asks for the **visual center** of the button.
  The normal operator instructions prefer a fresh UIA reference for ordinary
  controls, using screenshot pixels only for custom-rendered targets.
- The native broker now refuses pixel input when image dimensions differ from
  the approved window geometry, or when the point is outside/covered. It does
  not rescale guessed coordinates, bypass occlusion or expand app scope.

## Evidence and limits

- Pre-change complete project checkpoint: 
  `C:\Users\LENAVO\.codex\backups\quartz-mcpwindows-20261023\agent-1792767039-676f7ccb94964cddbab6efa2fb4c76d0.zip`.
- Source regression: `python -B scripts\run_safe_tests.py` — 332 passed.
- Native single-window diagnostic: the owned fixture launched, but the Windows
  image-capture helper timed out twice (`FrameArrived` / `window capture timed
  out`). No click was sent; fixture callback stayed zero. The verified owned
  fixture process was closed normally. This is **BLOCKED live input evidence**,
  not a successful pixel acceptance.
- The already-running packaged Quartz process was not restarted or replaced.
  Therefore these source changes are **not yet deployed** to the packaged app.
- No ASTER, Warband, saved games, system settings or provider credentials were
  touched. The broad upstream MCP service was not exposed to either agent.

## Next acceptance gate

The source-run three-window test now passes (details below). Next, package and
test the real Quartz main chat with inline consent, Codex operator + Gemini
observer, one input owner, Stop and user takeover. Do not call source tests or
a standalone test window packaged-chat acceptance.

## Same-day live retest

The independent Computer Use screenshot helper still timed out twice on the
owned `Quartz Multiwindow Fixture LAUNCH` window. No input was sent through that
helper. This is a limitation of that diagnostic channel, not proof that
Quartz's own bounded capture is unavailable.

Quartz's own source-run broker and real Windows fixture then passed:

- `labs/multiwindow-codex-20261023-180843/acceptance.json`: Codex made two
  real screenshot-relative center clicks, A=1 and B=1; C had no callback.
  Broker recorded one denied switch to C. Gemini independently observed the
  fixture log. No fixture log-error marker occurred. All three owned test
  processes were closed by the harness.
- `labs/workflow-20261023-181055/acceptance.json`: the visual color choice,
  repair and final UIA callback succeeded once each, but the strict test was
  **FAILED** because Codex did not attempt a switch to C when it was absent
  from the approved window list. This is a coverage failure, not evidence of
  unauthorized input.
- `labs/workflow-20261023-181434/acceptance.json`: after giving the exact C
  handle explicitly in the disposable test prompt, the complete workflow was
  **VERIFIED**: one correct color choice, one final verification callback,
  two approved UIA actions, one denied C switch, no C callback.

These are real source-run GUI/CLI/Squad tests. They do **not** prove that the
already-running, unchanged packaged Quartz EXE has the new source fixes or
that the actual packaged main-chat inline approval card has been clicked.
