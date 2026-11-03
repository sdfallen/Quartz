# Stop A-02 — owned-process cancellation

Owner: Codex. Learning-record work remains Claude's responsibility.
Baseline: `ccecffe53e6575f655cdd880c8efbe02754c2ad3`.
Pre-change checkpoint: private `stop-A02-prechange-ccecffe.bundle`.

## Confirmed defect

When psutil process-tree discovery raised AccessDenied/NoSuchProcess, Stop
returned false without trying to terminate its original owned Popen root.
Independently reproduced with a real owned Python process and an injected
discovery error. This was not an observed Windows account permission failure.

## Change

- Always attempt termination through the original Popen handle when tree
  discovery/verification fails; escalate to kill only after the normal wait.
- Retain previously observed process identities when verification fails.
- Record incomplete tree discovery separately from root termination. An exited
  root does not prove all descendants exited.
- Serialize Stop and cleanup snapshots on the owned Popen object so a watcher
  cannot release ownership while tree verification is in progress.
- Codex and Antigravity watchers retain process/writer ownership and report
  cleanup uncertainty rather than claiming cancellation completed. The watcher
  exits instead of spinning forever when the root is gone but discovery was
  incomplete. Shutdown rejects unconfirmed cleanup.
- Tool Workbench fallback also respects this uncertainty; an actual Windows
  Job Object's independent empty result remains authoritative.

No model, UI, permission, learning-record, game, or user-data behavior changed.

## Verification levels

- SOURCE/STATIC: publication audit PASS (483 files, no findings); diff check PASS.
- REGRESSION: 1245 tests OK, 14 skipped. Twelve require the worktree's built
  desktop helper; those were subsequently rerun after copying the unchanged,
  hash-verified helper. The other two remain skips, not successful acceptance.
  Helper-dependent module rerun: 22 tests OK, no skips.
- Targeted cancellation/lifecycle regression: 63 tests PASS, then all 11 new
  fault/concurrency tests PASS after the concurrency case was added.
- REAL PROCESS: four runtime cancel/watcher cases PASS: Codex and Antigravity,
  each with normal discovery and injected discovery denial. These use real
  owned Python parent/child processes, not real provider CLI/model calls.
- GUI: NOT TESTED for this patch. No packaged main-chat Stop click acceptance
  is implied by runtime fixtures or source tests.

Private evidence root:
`C:\Users\LENAVO\.codex\backups\quartz-final-integration-20261102`.
Logs: `stop-A02-full-suite.log`, `stop-A02-targets-final.log`,
`stop-A02-concurrency-tests.log`, `stop-A02-helper-restored-tests.log`.
Process evidence: `stop-A02-live-20261103-first/result.json`, including source
hashes. Its source_commit is the parent baseline plus recorded working-file
hashes, not a claim that the patch was already committed during that run.
The final four-case run `stop-A02-live-b27f8ae/result.json` is VERIFIED and
records the exact committed source `b27f8ae030cf9e6bab3581daa01a95bf0b99a658`.

## Honest boundary

If discovery fails before a child can be observed, an owned root handle cannot
prove or force closure of that unknown descendant. The injected tests explicitly
observe this possibility, retain the writer claim, and clean up their own
creation-bound fixture child afterward. This patch does not bypass access
controls, guess PIDs, or claim full-tree cleanup in that case. Such a job needs
recovery/independent containment verification before the writer can be reused.

The legacy REA subprocess caller is not converted into a provider runtime owner
registry by this patch. No broad REA or learning rewrite was attempted.

## Delivery

Keep the installed Quartz unchanged until integration with Claude's learning
delivery is coordinated. Deliver the scoped commit and private package evidence.
Runtime fixtures are not USER ACCEPTED and do not establish whole-system completion.

Private candidate: `stop-A02-dist/Quartz/Quartz.exe` beneath the evidence root.
SHA256: `c3711a17207e4de590054aebdac41b7efa47365664fed746be7f1d44dc494221`.
BUILT: PyInstaller completed. Package/source verification: 88 checks, zero
failures; all four changed runtime modules match source. See
`stop-A02-package-verification.json`. This does not launch the GUI.
Clean distribution audit: PASS, 1919 files, zero findings
(`stop-A02-package-audit.json`).

Preservation check: all 43 previously recorded user files still exist; only
`assistant.log` and `quartz_entry.log` differ. Installed EXE remains SHA256
`955df5bec7e35cb20f51574485313fccbd450accee7a59ef5ece09cc58530498`.
See private `stop-A02-preservation.json`. No production deployment in this task.
