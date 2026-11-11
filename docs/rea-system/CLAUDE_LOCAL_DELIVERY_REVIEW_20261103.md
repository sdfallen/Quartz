# Claude local delivery review

2026-11-03. Delivery `ea4c31b` on `claude/delivery-review-record-20261103`, based on current source `05890c7`.

## What was delivered

- `docs/CLAUDE_INTEGRATION_REQUEST_A02_20261103.md`: current Stop/discovery defect reproduction and proposed owner-scoped correction.
- `docs/CODEX_ORCHESTRATION_DELIVERY_REVIEW_20261101.md`: historical review, retained as historical evidence. It does not reopen all old findings in current source.
- No production code changes, package build, deployment or packaged GUI acceptance. The two documentation files were fast-forward integrated. The storage/memory correction `05890c7` is preserved.

## Independent A-02 reproduction

Codex launched one owned Python sleep fixture and injected `psutil.AccessDenied` only into process-tree discovery. `stop_process_tree` returned false and the root was still alive; the fixture was then explicitly cleaned up through its own Popen handle. No user process, permission setting or game was touched.

Evidence: private `claude-A02-independent-reproduction-20261103.json`. This is real root-process execution with fault-injected discovery failure, not evidence that Windows actually denied access during a user task.

**A-02 is confirmed and remains open.** Current code correctly avoids claiming discovery success, but fails to attempt root termination in that exception path.

## Constraint on the proposed patch

Terminating an owned Popen root is preferable to leaving it running. Root termination does not establish that unenumerated descendants exited. The supplied fallback returns false, but runtime watchers currently can later confirm cleanup from root exit plus an empty known-child list. A safe integration must review that downstream behavior as well; do not replace one Stop defect with false full-tree cleanup confirmation.

Required correction/tests for the process/runtime owner:

1. Attempt terminate/wait/kill using the owned Popen handle on discovery failure, without accepting raw PIDs or reconstructing guessed children.
2. Retain known child identities and represent incomplete discovery honestly. A root exit alone must not confirm an unknown tree as cleaned up.
3. Cover AccessDenied/NoSuchProcess, timeout escalation, terminate/kill errors, existing pending children and watcher/claim retention.
4. Run relevant runtime regressions and full suite; normal real owned root/child cleanup should remain functional. Distinguish injected failures from naturally observed Windows permission failures.
5. Build and verify a candidate separately; no automatic replacement of an active user app.

This review integrates the delivery documents only. No speculative runtime patch was applied and no new package was installed. Installed build remains `955df5be…`; the source storage correction still awaits packaging/deployment. Historical and human-operated GUI evidence retain their original scope.
