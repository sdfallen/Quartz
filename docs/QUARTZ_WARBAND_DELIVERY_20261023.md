# Quartz / ASTER integration - 23 October 2026

## Implemented

Normal main-chat tasks can use the protected **ASTER · Warband / Universal
Modder** profile. Inspect, develop and play are separate inline capabilities.
Codex/Gemini retain existing CLI login/model selection. Squad collaborates;
only one operator owns keyboard/mouse and only the operator can patch/build.

UM checkpoints precede source changes. Exact-hash single replacements are
restricted to authored Gate B source, syntax checked with official Python 2.7,
and built using the existing CodeOnly procedure. Build/preservation failure
restores the exact pre-build module. No arbitrary shell tool is exposed.

Owned-process launch uses the existing reversible Standard150 lease. Screenshots
are actual GPU client images supplied to the model. Each input needs a fresh,
one-use observation, current process identity and foreground/input lease.
Takeover/Stop revokes input. Original saves are opened with OS read-sharing
locks denying overwrite/rename during play; final hashes are compared.

## Acceptance, without inflated claims

| Scope | Result | Evidence |
|---|---|---|
| Local safety/routing/rollback/schema regressions | 345 tests PASS | final package regression-final.log |
| Actual UM archives, source contracts, frozen world/resources/IDs | VERIFIED | labs/warband-adapter-20261023-204529/warband/acceptance.json |
| Real Codex + Gemini/Squad launcher and menu observation | AUTONOMOUS LIVE VERIFIED | labs/warband-agent-20261023-211757 |
| Existing campaign read-only load, paused map, Native no-save exit | AUTONOMOUS LIVE VERIFIED | labs/warband-agent-20261023-212948 |
| Original saves and shared battle_size | 9/9 hash equal; actual 3.9167 restored | same run, warband/closing-state.json and agent-acceptance.json |
| Mod source edit and official build/rollback through a real agent | NOT LIVE TESTED; guarded implementation/unit tests present | tests/test_warband_workspace.py |
| New adapter battle movement, combat diagnosis/fix, complete Gate B | NOT TESTED in this delivery | existing Gate B evidence remains separate |
| Packaged main-chat full permission-card-to-game acceptance | BLOCKED: Windows capture timed out; UIA-only launch evidence, not full visual acceptance | final GUI smoke below |

Actual read-only campaign run: task bf9795c72e844d61a6c2b98b9e623235,
8 real observations, 6 actions including launcher/menu input. Models were
gpt-6-luna/low and gemini-3.8-flash-low/low. Loaded visible slot was reported
as Aster Faction Tester, Day 1 (10:26); exact SG index was not asserted.
Image game-35b6dec3f3fa461b956c6f8c027ce902.png shows the paused campaign.

## Failures found and corrected

Steam bootstrap readiness; explicit operator assignment precedence; Native
custom-rendered Play gating; expected launcher-to-runtime HWND transition;
unnecessary slow UIA scanning of the GPU runtime causing stale screenshots;
Escape key aliasing. Earlier partial/failed runs remain under labs/warband-agent-*.
No distance, timeout or Gate B diplomacy success criterion was weakened.

## Preservation and limits

Installed gameplay scripts remained SHA256
27d6f9b7612e942f02e274dd967de6eba1d4afbb27ef268b2fa2277506345d60.
No gameplay rebuild, save write, Native resource edit, security/driver/Overlay
change, EXE patch or WSE2 dependency was introduced. MODLOG received only an
additive integration note after the live test. Existing 300/500 profiles remain.

Original-save locks are process-owned: force-killing Quartz releases them.
Keep Quartz running while its owned game is open; Stop is not a forced game
kill. Authentication still requires the user. Historical Warband freeze is
not diagnosed or fixed by this work. Gate B remains IN PROGRESS; C-G untouched.

Usage and exact workflow: [QUARTZ_WARBAND_WORKFLOW.md](QUARTZ_WARBAND_WORKFLOW.md).

## Final package and preservation

Installed `dist/Quartz/Quartz.exe` SHA256:
`ffbda2b7ecf9505c0b682b801fd0dfb0543f17687906cd87a4e8a7035ef3190b`.
All packaged module signatures, helper schema/hash, workspace CSS and supplied
Q branding checks passed. Final regression: 345 tests, PASS. Embedded JS: PASS.
Delivery receipt and complete output:
`C:/Users/LENAVO/.codex/backups/quartz-workspace-package-20261023-210703`.
Previous distribution retained at
`C:/Users/LENAVO/.codex/backups/quartz-before-desktop-bridge-20261023-213941`.
Source .env, conversation/memory and copied local data hashes were unchanged.

Final UM module and nine-save diffs had no added/removed/changed files.
Only authored ASTER difference was the additive MODLOG entry. No owned Warband
remained; actual shared battle_size was 3.9167. UM final toolkit archive:
`quartz-um-pid-drive-final-20261023/20261023-213548.zip`.

Packaged Quartz launched as PID 11660. UIA confirmed the real main chat,
existing conversations, model/effort selectors, project selector and Q graphic.
GPU capture failed twice (`FrameArrived timed out`, then `window capture timed
out`); a guarded project-selector click returned `coordinate input geometry
is unavailable`. No blind input, permission bypass or further click retry was
used. Full packaged-chat acceptance remains BLOCKED, distinct from the actual
successful CLI/Squad/game load test. Quartz is left open and idle for the user.
