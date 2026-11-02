# REA three-owner integration review — 2026-11-02

Status: **INTEGRATION CANDIDATE; NOT DEPLOYED; packaged investigation acceptance BLOCKED**.

The installed user build remains `de512a5d362bf7bf073a3e32af5ac2d6e8725c27686dabce54edf1a3ddb68d05`. All work took place in the separate `codex/rea-system-codex-20261102` worktree. No public push/release, ASTER access, system setting change, account change or production data migration was performed.

## Delivery and checkpoint identity

| Owner | Original delivery | Review outcome |
|---|---|---|
| Codex | `e476c2f` investigation foundation; `40930b2` structured analysis/host integration | Bounded PE/CLI/package/PCK analysis, existing-owner integration and real local evidence |
| Gemini | `c6ada13`, delivery `2a9e1f8` | Original worktree/commits retained. Serious acquisition/execution defects reproduced and fixed before any deployment |
| Claude | Downloads `claude-rea-memory.zip`, SHA256 `11a4bc7ef13e6a94e02efa07cde565094c5dac8a273804d7b7c1a423e66610ba`; bundle commit `01b079e` based on `e476c2f` | Original package retained; merged at `503e5c4`, followed by Windows integrity review and additional fixes |

Reviewed production code checkpoint: `d69e04f`. Child-fixture correction/review documents: `8ddbc40`; it changes no production module. The candidate EXE is `5aa67fd7599927bf7d4c8ba63f2904acf8b722a240b43339591a735b16daf1d6`. A fresh, clean collection in private `rea-release-dist/Quartz` has the exact same EXE hash,87 verified checks and1919-file clean audit. The separate `rea-candidate-dist/Quartz` contains the disposable GUI test profile and is not the clean distribution.

Original handoff bundles/patches remain in private evidence and original delivery history; duplicate bundles/patches were removed from the current repository tree. Reproducible lab source moved to `scripts/rea_validation`; generated runtime evidence stays outside the repository/package.

## What changed

- The existing diagnostics worker owns investigation sessions, cancellation, evidence publication and parser gateways. There is no second task engine, desktop operator or permission system.
- Native analysis records PE import descriptors/symbols and their IAT RVAs, export ordinals/RVAs/forwarders and x64 unwind ranges. Managed analysis records assembly/AssemblyRef, TypeDef-to-MethodDef and P/Invoke relationships. ZIP, PyInstaller CArchive and unencrypted standalone Godot PCK v2/v3/v4 have bounded structural adapters. These facts are SOURCE evidence, not observed function semantics.
- Host evidence binds target identity, artifact digest and manifest provenance. Claims, hypotheses and structurally verified procedures stay distinct. Failure invalidation uses the attested verification time, preventing old failed procedures from being revived by republishing a new observation. Retrieval never restores a grant or executes a memory recipe.
- Evidence capture streams rather than allocating64MiB for tiny files. A measured3.5KiB ingest peaked at285,330 Python-allocation bytes. Cancellation/IO failure rolls back only the current call's owned file, record, byte counter and manifest; cleanup refusal is a typed failure.
- Managed tool acquisition rejects traversal, external executables, links/reparse points, archive collisions, untrusted hosts/ports/redirects and changed manifests/files. Package identity and every installed file are revalidated before execution. Publication has an OS lock and cancellation fence.
- Execution reserves ownership before spawn. Windows tools start suspended, enter an owned Job Object and then resume. Stop cannot confirm while a spawn, process, descendant or output drain is pending. Output becomes bounded hashed artifacts. The Python API keeps typed receipts; JSON gateways receive canonical statuses and exact request IDs.
- Only the independently checked official ripgrep14.1.1 release remains in the default external catalog. Two unsubstantiated remote repositories were removed. A matching README/name is not a trusted manifest; automatic arbitrary GitHub repository discovery/installation is **not implemented**.

## Evidence levels and acceptance

Private evidence root: `quartz-final-integration-20261102` under the Codex backups directory. Paths below are relative to that root unless stated otherwise.

| Acceptance area | Result and actual scope | Evidence |
|---|---|---|
| Source regressions | VERIFIED — final1148 cases in200.774s,0 failures,2 skips, recorded in `FINAL_VALIDATION.json`; earlier1137 and1140 runs also passed with2 skips. The later1148 run exposed one defective child fixture; the failure was preserved and fixed, not hidden | `rea-combined-safe-tests.log`, `rea-reviewed-final-safe-tests.log`, `rea-final-frozen-suite.log`, `rea-final-confirmed-suite.log` |
| Native/managed/package relationships | VERIFIED — SOURCE, plus real compiler/package construction provenance.24 domain tests and host integration tests; no target executable was run by the static parser | Repository `CODEX_ANALYSIS_REPORT.md`; original `labs/rea-analysis/validation-20261102T133751Z/manifest.json` |
| Actual engine loading boundary | VERIFIED — isolated Godot4.7.1 headless tool experiment: base7, replacement disabled7, replacement enabled42. Original/copy tool hashes unchanged; existing game source/assets not read | Original `labs/rea-analysis/godot-20261102T133550Z/manifest.json`, `process.json` and generated PCKs |
| Evidence/memory integrity | VERIFIED —81 Windows targeted cases, including separate-process lock, real persistence, malformed inputs, failed-procedure replay and cancellation rollback. LIVE-labelled fixture records remain test fixtures | Repository `CLAUDE_MEMORY_INTEGRATION_REVIEW.md`, `tests/test_learning_review.py` |
| Real REA persistence/reuse | VERIFIED — actual REA6.8.0 success on copied compiled helper;190 nodes/189 member hashes/66 archive entries. Following task completed with `rea_used=false`, `knowledge_reused=true`, saved=true, unchanged target, confirmed cleanup | `live-investigation-5a2d16df9de340739a3ae496830cb91f/result.json`, `third-reuse-result.json` |
| Official GitHub tool acquisition | VERIFIED — pinned SHA256 release, actual managed executable, two real searches, canonical gateway evidence, replay without a second spawn, unchanged target/environment, confirmed cleanup | `workbench-live-d69e04f-retry/result.json`, `metrics.json` |
| Stop and process identity | VERIFIED within tested Windows cases — real parent/child exit, pending drains, late spawn reservations, pre-cancel/deadline rejection and exact acquisition fences. Mocked race barriers are separate from real child tests | `tests/test_tool_workbench_execution_safety.py`, acquisition safety tests, `GEMINI_INTEGRATION_REVIEW.md` |
| Actual GUI hypothesis→fix→verification | BLOCKED — no new end-to-end application correction through the packaged GUI was completed | UI input/capture limitations below |
| Packaged source/assets/helper/branding | BUILT/VERIFIED —87 checks matched the current source, helper/schema, theme and supplied Q assets. Clean new-user package audit1919 files,0 findings | `rea-package-first-verification.json`, `rea-clean-package-audit.json`, final `rea-clean-release-verification.json`, `rea-clean-release-audit.json` |
| Packaged startup and shutdown | LIVE accessibility/startup and normal shutdown VERIFIED. Selected only generated test project; both existing providers reported connected. GUI/backend/backend_thread confirmed at18:06:35; owned process14992 exited | `rea-ui-process.json`, candidate `quartz_entry.log` |
| Packaged main-chat investigation | BLOCKED — UIA set_value populated the visible message, but Send failed `coordinate input geometry is unavailable`; Ctrl+L left focus at RootWebArea. Screenshot capture timed out. No message/task was sent, no file picker/investigation ran, no pixel QA claim | `rea-ui-acceptance.json`; candidate conversation and shutdown logs |
| User-data preservation | VERIFIED —44 production-root files hash-identical, including the installed EXE. Package was kept private and not copied into production | `rea-production-before.json`, `rea-preservation-final.json` |

## Measurements and failures retained

Official-tool acceptance: acquisition6.656s, searches0.8031s/0.4656s, two hashed output artifacts per search. The10ms sampler saw peak56,713,216 bytes RSS for the Python acceptance controller and its descendants. Very short peaks may be missed. This is not Quartz's idle RAM, a UI latency measurement or a performance improvement. Evidence directory size was6,570,697 bytes at measurement time.

One reviewed-code download timed out during a network read, produced FAILED evidence and confirmed cleanup; a bounded fresh attempt succeeded. No permanent networking fix is claimed. Real REA first returned UNKNOWN for its startup/version probe, then succeeded; the third task reused the verified evidence. Neither transient was rewritten as success or hidden with a longer timeout.

The1148-case full run's only failure was a test fixture resolving `cmd.exe` in the intentionally sanitized environment: actual WinError2, exit1, confirmed cleanup. Earlier timeout passes sometimes masked that startup failure. The corrected fixture uses an explicit Python child, readiness handshake, real two-second deadline and both PIDs observed gone. Production execution code was unchanged. Focused25/25 execution cases passed; the final complete1148-case suite passed after this correction (2 documented skips).

## Honest capability limits

Native instruction disassembly, semantic call xrefs, live engine internals and arbitrary-game mod compatibility are unavailable. Imports/IAT and x64 unwind tables are useful structural relationships, not decompilation. Parser input128MiB/report512KiB/snapshot4MiB bounds remain explicit. Encrypted/embedded/delta PCK, Unreal PAK and unimplemented formats return unsupported.

The external workbench is a verified registered-tool mechanism, not an OS malware sandbox or an autonomous installer for any repository. No hard per-tool CPU/RAM cap or privileged runtime attach is claimed. Same-account manifest consistency is not protection against an attacker rewriting the entire local account. Distinct LIVE evidence IDs still depend on trusted host verification semantics; no real new UI procedure was promoted by these source fixtures.

The current diagnostics host connects the builtin parser and evidence memory. The external-tool gateway is tested with actual tools and an injected executor; automatic main-chat selection/acquisition of new external adapters has not been accepted. A large autonomous investigation/fix loop, actual bad-hypothesis recovery and new UI procedure learning need their own real scenario evidence. No whole-system COMPLETE claim is made.

## Next exact work

Close the packaged main-chat acceptance with functioning GUI observation/input, using only the generated `rea-ui-fixture/sample-package.zip`. Then validate an isolated actual application correction and second-task procedure reuse. Add further domain tool adapters only behind current grant, manifest, evidence and Stop contracts. Keep the installed user build unchanged until the relevant acceptance passes. No ASTER, Notion third-agent revival or unrelated framework work.
