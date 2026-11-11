# Claude memory delivery — Windows integration review

2026-11-02. Reviewed the delivery merged at `503e5c4` (Claude commit `01b079e`), then made bounded fixes in the assigned memory/evidence ownership. No staging or commits by this specialist. No native-analysis/session/gateway/workbench/package changes by this specialist during this review.

## Observed baseline and final verification

The supplied Windows command passed before review changes:

```text
python -X utf8 -B scripts/run_safe_tests.py tests.test_investigation_evidence tests.test_rea_learning tests.test_learning_integrity tests.test_learning_quality
58 tests, 0 failures, 0 skips
```

Focused negative tests still reproduced gaps outside that coverage. Final command:

```text
python -X utf8 -B scripts/run_safe_tests.py tests.test_learning_review tests.test_learning_integrity tests.test_learning_quality tests.test_investigation_evidence tests.test_rea_learning
81 tests, 0 failures, 0 skips; 22.692 seconds
```

`tests/test_learning_review.py` adds23 regression methods, including real files and a real separate Python process testing the Windows OS publication lock. It is SOURCE/STATIC and local persistence verification. LIVE-labelled schema fixtures in those tests are explicitly fixtures, not live application/UI acceptance. Final full-suite/package verification belongs to the parent and must use the final hashes below.

## Additional fixes and reasons

- `core/investigation/evidence.py`: `ingest_file` streams256KiB chunks directly to the owned artifact, checking size, total budget, cancellation, source fingerprint and expected/copied digests. The old `read(MAX_FILE_BYTES+1)` allocated64MiB for very small snapshots. A focused3.5KiB capture now measured285,330 bytes peak Python allocation with tracemalloc; the regression requires less than8MiB. Earlier whole-analysis measurements around67MiB included the old host ingestion. These are measurement scopes, not a claimed speedup factor.
- Manifest attestation now binds scope, artifact path and observation timestamp as well as identity/kind/level/origin/digest/size/target. Manifest schema/session/target identity and record scalar types are checked. A knowledge JSON edit cannot redirect an attested record or change its scope/timestamp while retaining the original manifest.
- `core/investigation/contracts.py`: malformed referenced evidence produces typed failure; duplicate evidence refs remain rejected. Procedure success-check locator/path/expected values receive the same scope and type checks as steps; compare_digest requires an actual SHA-256 expectation.
- `core/investigation/memory.py`: publication and reload share nested coverage/inventory/limitations validation. Malformed evidence entries, NaN and forged nested inventory become typed failures/cache misses. Dedupe cannot bypass the final target fence. Bounded latest-context scanning counts unrelated candidates, rather than allowing the matching-record count to hide extra reads.
- Failed-procedure invalidation uses attested supporting verification timestamps, not the time a knowledge record happened to be republished. Adding a new observation cannot make old failed procedure evidence fresh. One new verification alongside an old one stays invalidated; two independently identified new host verifications can restore eligibility. An older failure artifact cannot overwrite a later failed run. Malformed or rewound failure metadata fails closed.
- `core/investigation/learning.py`: malformed nested references/retrieval limits have typed failures; an observation with no actual supporting evidence is unverified. Quality remains structurally derived rather than based on model confidence prose.
- `core/application_knowledge.py`: fresh learning now writes to the explicit investigation_root used by cache-hit retrieval, avoiding a custom-root split between first and later tasks.

## Final publication cancellation/IO cleanup correction

The review found that the previous add_bytes/add_json path could leave a new, untracked artifact after cancellation immediately following write/fsync. The parent explicitly authorized this follow-up before rebuilding.

Both byte/JSON and streaming publication now track whether this call actually created the file and added the record. Under the same owner lock, failure rolls back the records dictionary and byte count, restores the old manifest if publication had reached that stage, and removes only this call's new artifact. A final cancellation fence also catches Stop arriving after manifest persistence. Rollback does not depend on a still-active cancellation token.

Tests cover cancellation after artifact fsync, cancellation after successful manifest write, fsync failure, manifest failure both before and after replacement, persistent rollback failure, UUID collisions and cleanup denial. Committed earlier evidence and preexisting files survive. In particular, a failed exclusive create never authorizes deleting that preexisting path. The streaming path received the same ownership protection.

Cleanup failure is not silently claimed successful: stable typed errors include `evidence-cleanup-failed`, `evidence-manifest-rollback-failed` and the combined failure. If the filesystem denies deletion, a residual file necessarily remains and the operation fails explicitly; the test verifies this. If the filesystem refuses manifest restoration, in-memory rollback and owned-file removal still occur, but the error reports that durable restoration was not confirmed. No older committed artifact is deleted to compensate.

## Final source hashes

| File | SHA-256 |
|---|---|
| core/investigation/evidence.py | 5ab830780d8f0e2611a50f9e15ccd213f9afef53676524dcc7f5d6478ece4ba8 |
| core/investigation/contracts.py | 6fa091ea1af350acb87d92b1f4f7d880cb380502d3979789d6a6da3b47d34076 |
| core/investigation/memory.py | b6788d82aa1be5b806d3f1cd2d46a096d871489460b3fce2cca0f14da89b5e39 |
| core/investigation/learning.py | 9da699492e9ef9df088c8d254c64aa5086279cea116e7680554be71dfec638fe |
| core/application_knowledge.py | 7eb3bf8a715cac3bc4336befdc5e36b25cca49770b76a285e2b77f141dc2a2c9 |
| tests/test_learning_review.py | b2a4617a16caa31e9db96c0916463ecb099ccfdf25d09fcab24866499fb2794e |

## Trust and acceptance limits

Manifest attestation is consistency against a trusted same-account host manifest, not cryptographic protection against an attacker who can rewrite both manifest and knowledge. Two distinct LIVE evidence IDs are a structural independence requirement; genuine separate execution/success semantics still depend on the trusted host verification producer. Current Broker grants remain mandatory; no stored memory grants authority or executes a procedure. Clock anomalies or corrupt failure metadata may conservatively suppress reuse.

These regressions establish bounded local data/persistence behavior. They do not establish real UI procedures, packaged Quartz chat behavior, acquisition/disassembler correctness or successful game modifications. No network or UI was used in this review. No credentials, user history or protected project data were inspected.
