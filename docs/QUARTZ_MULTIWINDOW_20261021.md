# Quartz task-scoped multiwindow control — 21 October 2026

Status: implementation, build and safe deployment complete; acceptance results below must
remain separated from packaged main-chat consent/visual acceptance.

## Preserved baseline

Before changes, the complete installed distribution was copied to
`C:/Users/LENAVO/.codex/backups/quartz-multiwindow-before-20261021/distribution`.
It was running, so this initial copy is a crash-consistent backup, not a claim
of quiescent user-data capture. Source checkpoint:
`source/agent-1792564267-a22989dd4d8343739bfa6ca1b8bd0875.zip` under that directory;
Git ref `refs/quartz-checkpoints/agent-1792564266-ff256371`.
Original installed EXE SHA256:
`ddb9c01afa44ab24fc72f990ea619c8271c2ee0605679c77b6f25bef58a971ac`.
No Warband process was launched and no WarbandIsland content was accessed.

## Implementation

- `desktop_broker.py`: one task capability, 1–12 explicitly approved HWNDs,
  one OS input lease; `desktop_windows`, `desktop_switch`, `desktop_launch`.
  Process PID/start/executable/HWND checked at consent, grant, switch and input.
  Snapshots invalidated on switch and geometry change. Foreground loss, expiry,
  Stop and current-window closure revoke input. No title-based adoption.
- `desktop_launch.py`: up to four GUI-selected local EXEs, exact hash/file
  identity, no shell or arguments, single-use including uncertain failure.
  Only a unique HWND of the exact new PID/start/executable is adopted.
  Singleton apps, launcher children, secondary/new HWNDs require fresh consent;
  no automatic process-tree trust. Launched apps are not killed on task Stop.
  This approval is **not** an OS sandbox for the chosen executable.
- `chat_coordination.py` / `gui.py`: main-chat multi-checkbox window approval
  plus explicit optional EXE picker and visible hash, log and deadline. One
  inline confirmation binds the selected identities and scope. New scope uses
  a new plan/consent, not an instruction appended to an active task.
- `desktop_agents.py` / MCP: six exact broker tools. Agent run gets a private,
  expiring capability environment; observer never gets it. Codex operator uses
  the existing per-run restricted feature profile with only Quartz MCP restored.
  Antigravity private PreToolUse guard permits only those exact MCP calls and
  denies shell/files/other tools. Existing observer deny-all guard remains.
- `desktop_native.py` / `desktop_control.py`: final identity/geometry/foreground
  guard immediately before input. Broker UIA calls no longer automatically
  refocus a target after a user takeover during control enumeration. Standalone
  legacy controller retains its old optional-focus behavior.
- Existing authenticated IPC still cannot grant desktop authority. Old cards,
  stopped tokens and old snapshots cannot authorize another task/window.
- Q artwork, layout, models, detail levels, history and single-window APIs remain.
  Generic Warband control stays denied: an actual UM adapter is still required.

## Observed CLI compatibility defect

First native attempt (`multiwindow-codex-20261021-093905`) stopped before input:
AGY rejected `--model gemini-3.8-flash-low --effort low`.
Variant model names already encode effort. The runtime now omits a redundant
flag, rejects mismatched explicit effort, and reports per-variant effort choices.
No model substitution, permission escalation or quota bypass was added.

AGY operator-hook protocol drift was separately diagnosed, not bypassed:
the real payload is `toolCall.name/args`, including `call_mcp_tool` with exact
`ServerName/ToolName`. The initial incorrect-hook attempts remain recorded in
`labs/multiwindow-antigravity-20261021-094439` and `...094756`.
The probe `labs/operator-hook-20261021-095339/acceptance.json` verifies the real
CLI-to-packaged-hook-to-broker protocol using a **fake window list**; it is not
native UI acceptance.

## Acceptance evidence (ongoing)

| Area | Level / result | Evidence / limitation |
|---|---|---|
| Source regressions | SOURCE, PASS | Final test count in delivery receipt/regression-final.log; no mock result is native acceptance |
| Codex operator, Gemini observer | LIVE VERIFIED, source harness | `labs/multiwindow-codex-20261021-094055/acceptance.json`: A1, B1, C0, actual A→B→A, rejected C, 3 observer rounds and real Squad exchange |
| Restricted Codex operator regression | LIVE VERIFIED, source harness | `labs/multiwindow-codex-20261021-095912/acceptance.json`: A1/B1/C0, 5 observer rounds, restricted per-run tools, physical pixel clicks |
| Gemini operator / Codex observer | LIVE VERIFIED, UIA not pixel | `labs/multiwindow-antigravity-20261021-100711/acceptance.json`: Gemini 3.8 Flash Medium, A1/B1/C0, actual A→B→A, C denied, 14 real observer rounds. Both button actions are real guarded UIA invoke callbacks; not physical mouse clicks |
| Gemini pixel operation | FAILED | `...095433`: Flash used malformed action/stale references; `...100154`: Argon generated no button callback and hit the bounded test deadline. Actual window switching is verified, full pixel workflow is not |
| Real lifecycle and launch | LIVE VERIFIED, packaged MCP + source broker | `labs/multiwindow-safety-20261021-094607/acceptance.json`: single lease, exact-child launch, repeat launch denied, closure, external focus, Stop/revoked token and unapproved new HWND denied |
| Hook exact-scope denial | SOURCE + real CLI evidence | `094439` denies attempted run_command/read_file as well as the then-misclassified desktop call; not a successful desktop test |
| Packaged main-chat consent | NOT VERIFIED | Initial Quartz capture: FrameArrived timeout, refreshed/activated retry: window capture timeout. No permission card was auto-approved through an alternate route |
| Final packaged startup | LIVE VERIFIED, accessibility only | PID2156/start10:09:53, HWND4326328, installed EXE hash below. AX exposed Quartz Q, online, original project/history, model selectors and detail preference. Fresh screenshot again failed `FrameArrived timed out` |
| Multi-monitor / changed DPI | NOT TESTED | Actual fixtures exercised current display/geometry only; no display settings changed |
| New HWND / reused identity | SOURCE PASS + native new-window rejection | PID/start/exe reuse covered deterministically; actual Windows HWND reuse was not manufactured |

These native tests are product self-tests with explicitly bounded fixture grants,
not claims that the real packaged main-chat approval button has been exercised.
Model-generated completion text is not sufficient: callbacks/audit/logs decide.

## Operational limits

At least one existing approved window is currently required for a task. Optional
EXEs may then be launched from that task. Only exact-child single-window apps
are supported by the narrow launcher; no shell, parameters, elevation or process
descendant adoption. Protected/private interfaces remain excluded even if their
app was selected. If the user changes focus, start a newly approved task; there
is no silent refocus/resume. Log paths remain bounded, project-contained and
rotation-sensitive. The desktop launcher never replaces UM checkpoint/save
protection. No ASTER acceptance is claimed by these fixture tests.

Implementation reference used for the per-run Codex restriction profile:
[official configuration basics](https://learn.chatgpt.com/docs/config-file/config-basic)
and [official MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Installed package and protection

Installed `dist/Quartz/Quartz.exe` SHA256:
`5654d1d36fc052c02499242f25066cc793462af6f072a13c65dc0330ce249331`.
Build/delivery root:
`C:/Users/LENAVO/.codex/backups/quartz-workspace-package-20261021-093628`.
Final safe suite: **289 PASS**, 58.060 seconds (delivery regression log).
All checked packaged code signatures, helper hash, CSS, Q assets and actual PE
icon bytes match source. This is BUILT verification, not a main-chat live claim.

The user explicitly approved a safe restart when idle. Native accessibility
showed no active cancel/task control; no CLI child remained (only WebView).
Original PID12608/start09:19:06 was closed with normal Alt+F4, not force-killed.
Quiescent old bundle remains at:
`C:/Users/LENAVO/.codex/backups/quartz-before-desktop-bridge-20261021-100353`.
`deployment-receipt.json` records all preserved top-level data files hash-equal,
including the distribution conversation file (distinct from root conversation
data). Root `.env`, memory and conversation hashes also stayed equal.

Checkpoint comparison, unlike `git diff` against older HEAD, isolates this task:
14 implementation/test files changed (9 core/GUI implementation, verifier and
4 tests), plus the operator/continuation documentation updated at delivery.
Added launch module, multiwindow tests/fixtures/probes/report separately.
No earlier dirty-worktree changes were reset, removed or attributed to this task.
Approved Q originals/assets and existing source user data remained unchanged.

## Continuation

Do not repeat failed hook guesses: the exact live protocol is recorded above.
All owned fixtures and CLI runs were closed and task leases revoked. Installed
Quartz was reopened under the user's restart approval, idle with no desktop
grant; it was intentionally left open. No conversation, API configuration or
memory bytes changed in root or the distribution's protected conversation file.

Final source checkpoints are in the delivery root's `final-multiwindow-source/`;
private evidence archive is `multiwindow-evidence.zip` in the same delivery root.
The full initial working bundle and quiescent prior deployment remain recoverable.

Remaining: actual packaged-main-chat inline approval→operator→Stop acceptance,
visual QA in a capturable desktop session, optional multi-monitor/DPI variation,
and reliable Gemini physical-pixel operation. Existing success must not be
reported as those unperformed tests. Computer-use safety boundaries prevented
approving desktop permission cards via an alternate hidden route; no guard was
disabled. Do not weaken snapshot freshness or identity policy for model errors.

Overall: **PARTIAL ACCEPTANCE**, not universal desktop control complete. The
task-scoped multiwindow implementation is installed; source/native harness
coverage is stronger than packaged-GUI live coverage.
