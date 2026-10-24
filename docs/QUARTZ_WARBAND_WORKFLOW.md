# Quartz · ASTER / Warband workflow

Select **ASTER · Warband / Universal Modder** in the normal project selector,
then write the task in the main chat. For example:

> Codex, Gate B'nin son raporunu incele, kalan bağımsız testi yürüt ve gerçek
> bir hata bulursan checkpoint alarak düzelt. Gemini, kaynak değişikliğini ve
> RGL kanıtlarını bağımsız kontrol edip Squad üzerinden Codex'e ilet.

Quartz uses the existing Codex/Gemini CLI login and selected models. The main
chat asks for the task capabilities it actually needs. No separate desktop
control screen or paid API-key migration is required.

## Task capabilities

- **Inspect:** bounded source/document reading, literal search, RGL tail,
  existing contract tests, frozen-world/resource/714-ID checks, and UM backups.
- **Develop:** an exact replacement against a fresh source SHA256, a new UM
  source checkpoint before every write, official Python 2.7 syntax check and
  `build.ps1 -CodeOnly`. A failed build/preservation check restores the exact
  pre-build module through UM. Authored source and failure evidence remain.
- **Play:** the existing UM-backed Standard150 launcher, temporary shared
  `battle_size`, original-save read locks, GPU screenshots, normal bounded
  mouse/keyboard/look input, exact process identity and normal owned close.

The collaborator can inspect the approved source and logs and exchange actual
Squad messages. Only the assigned operator edits/builds or drives the game.
Generic full-access/file workflows remain blocked for this protected profile.
Native, saves, build tools and game resources cannot be edited through the
authored Gate B replacement tool. Its current allowlist is returned by
`warband_source(mode="list")`; new content needs an intentional profile change.

## Normal development/test sequence

1. `warband_status`, request the minimum inline capabilities.
2. Read project `AGENTS.md`, the continuation note and actual current source.
3. `warband_run(prepare)` creates verified UM source/module/save archives.
4. Inspect/patch only an evidenced bug, run contracts and preservation, and
   build only if source changed. Source/static and build results are distinct.
5. Launch through UM. Steam startup must settle; authentication remains human.
6. Observe the real launcher. Native controls must confirm AI_Island_Test.
   Custom-rendered Play is clicked only from the fresh actual screenshot.
7. Wait for the Native window/loading transition, then inspect the actual
   runtime screenshot and fresh RGL module. One observation allows one action.
8. Record image/log hashes, actor/mission readbacks and tested build. A scoped
   exact RGL assertion does not certify the whole feature or Gate B.
9. Close the owned game normally and check the actual lease manifest plus
   config field and the final nine-save checksum report.

Stop revokes further input. If the owned game remains open, its existing
launcher watcher still owns restoration; save locks remain until it exits.
The application must remain running for that save-lock watcher. A force-killed
Quartz cannot keep process-owned file locks alive. Backups and manifests remain.
No automatic force-kill, reboot, driver/Overlay/security change is included.

## Evidence and present scope

`labs/warband-adapter-20261023-204529/warband/acceptance.json` verifies actual
UM checkpoints, official legacy DSL tests and frozen world/equipment/ID checks.
The installed gameplay build stayed at scripts SHA256
`27d6f9b7612e942f02e274dd967de6eba1d4afbb27ef268b2fa2277506345d60`.
All nine original saves matched their initial hashes in those checks.

Real CLI/Squad smoke runs are under `labs/warband-agent-*`. Earlier runs exposed
Steam bootstrap readiness, role selection, a custom-rendered launcher button
and expected launcher-to-game window replacement. Failed/partial runs remain
there. The final delivery note records the latest successful and blocked scope.

`tests/test_warband_workspace.py` includes actual Windows file-sharing checks
on disposable files (read allowed, overwrite and rename denied), fail-closed
patching/rollback and reviewer/input separation. This is not a new native-save
write acceptance. The original SG08 permission is not reused.

Universal Modder's Drive gained an optional exact PID/start-time mode; ordinary
callers keep the original default. Quartz uses the pinned mode and never its
automatic refocus retry. Invalid-PID no-input probe returned `ready no-window`
and `rect=none`. UM pre-change archive:
`quartz-um-before-pid-drive-20261023/20261023-205359.zip`.

The historical Gate B campaign freeze is not declared fixed. A screenshot
failure is a blocked observation, and a model's completion message is not an
acceptance result. Gates C–G and new gameplay content remain outside this work.
