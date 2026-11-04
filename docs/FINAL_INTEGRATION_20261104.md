# Local integration closeout — 2026-11-04

Current source is on local `main` in
`C:\Users\LENAVO\.codex\worktrees\quartz-rea-chat-review`.
There previously was no local main; `origin/main` was an ancestor with no
divergent changes. Main was created from the reviewed integration, including
Claude focus commit `19601a2`, Stop `b27f8ae`, and storage fix `05890c7`.
No remote branch was pushed. The original Desktop checkout remains on its own
historical branch: do not build that older checkout as though it were current.

Installed EXE SHA256:
`87fd63861d814f1ef5b6668b43bac1be14f20186b14217bf8a1b340f2a726df1`.
All 88 installed-package/source checks pass. No replacement build or deployment
was needed in this closeout; following documentation-only commits do not change
the packaged implementation.

## Checks and honest remaining scope

- Focus/broker/agent/Stop targeted regression: 89 tests OK.
- Publication audit before this report: 486 files PASS, zero findings.
- First full suite: 1252 tests, one failure, two skips. A job was still running
  at the integration test's three-second join deadline. The entire affected
  six-test module then passed independently. This is evidence of an intermittent
  timing-sensitive test, not proof of a diagnosed production defect. No timeout
  or production behavior was changed to conceal the failure.
- Final full suite recheck without concurrent GUI testing: 1252 tests OK,
  two skips, 193.701 seconds. The failed first run remains available; passing
  this rerun does not establish a permanent fix for the timing-sensitive test.
- Existing source learning roundtrip and owned-process Stop evidence remain
  scoped to their original runs; they are not GUI acceptance of this package.
- GUI acceptance: BLOCKED. Installed Quartz launched and reported successful GUI
  creation. Screenshot attempts returned `FrameArrived timed out: timed out waiting
  on channel` and `window capture timed out: timed out waiting on channel`.
  Accessibility-only recovery returned `foreground window did not report a
  process id`. No blind clicks, task submission, permissions or model input were
  sent. A normal Alt+F4 closed this test app; entry log confirms all GUI/backend
  cleanup and `Quartz Exit`. No Quartz process remained at the final census.

The actual chat memory-reuse-after-restart and active-task GUI Stop checks remain
unverified. This prevents a whole-system COMPLETE claim; local source/package
integration is complete.

## Preservation

No user file was restored over newer user changes. Against the older promotion
receipt, 40/43 files match; two logs and the conversation store differ. Semantic
comparison found zero removed conversations and zero changed/removed old message
sequences, with 72 later messages preserved. The receipt predates this session;
those later changes are not attributed to the attempted launch test. No chats
were sent during this closeout. Installed EXE remains unchanged.

Private evidence root:
`C:\Users\LENAVO\.codex\backups\quartz-final-integration-20261102`.

- `focus-final-full-suite-20261104.log` (failed first run preserved)
- `focus-final-timing-investigation-20261104.log`
- `focus-final-full-suite-recheck-20261104.log`
- `focus-installed-verification-20261104.json`
- `focus-final-publish-audit-20261104.json`
- `focus-final-preservation-20261104.json`
- `focus-final-conversation-preservation-20261104.json`
- `pre-main-finalization-e924726.bundle`

See `CLAUDE_FOCUS_PERSISTENCE_20261104.md` and
`rea-system/STOP_LEARNING_COMBINED_DELIVERY_20261104.md` for delivery provenance.
