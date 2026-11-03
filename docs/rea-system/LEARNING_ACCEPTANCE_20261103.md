# Learning/memory acceptance — scope and reproducible checks

2026-11-03. The human-operated packaged search recorded raw evidence but reported `investigation_knowledge_saved=false`. No claim of learning/reuse was accepted from that run.

## Reproduced persistence failure and minimal correction

An isolated source diagnostic reproduced the failure at the same138-character investigation-root length. The final knowledge path is251 characters, but the old atomic writer repeated the entire destination filename in its temporary prefix, making the temporary path265 characters. Creation raised FileNotFoundError and the diagnostics job correctly retained `memory_saved=false`. A shorter-root comparison saved successfully.

Pre-change Git bundle: private `learning-publication-prechange-9483d59.bundle`. Both new boundary regressions failed before the patch. `core/atomic_json.py` now uses a short fixed temporary prefix while retaining unique `mkstemp` creation in the destination directory, flush/fsync, atomic replace, failure preservation and temporary cleanup. No registry/path-policy change is made. The correction also avoids filesystem component-length overflow for valid long destination names.

## Actual three-process source experiment

Private driver `learning_memory_roundtrip_20261103.py` uses only an isolated copied ZIP, the real ArtifactDiagnosticsService/InvestigationSession/InvestigationMemory, and three independent Python processes. No model call, UI input, selected application execution or fabricated memory record.

| Phase | Measurement | Acceptance |
| --- | --- | --- |
| First inspection | PID13616; memory saved=true; previous record=false; one knowledge file. | VERIFIED — actual publication |
| Fresh process, same file/question/tool identity | PID8672; saved=true; previous record=true; matching target SHA; two verified prior evidence records loaded. | VERIFIED — persistent retrieval across processes |
| Changed disposable ZIP version | PID11064; target hash changed; previous record=false; new observation saved=true. | VERIFIED — old version is not trusted as current |

All three workers/processes completed with exit0 and confirmed owned cleanup. The same138-character memory root was used. Source hash for the corrected atomic writer is recorded in the private result manifest; the experiment ran against uncommitted corrected source based on9483d59, not against the unchanged installed EXE.

After the correction,90 targeted storage/memory/approval/worker regressions passed. The full safe suite completed1234 cases with zero failures/errors and two explicit skips in220.308 seconds. Current-source publish audit passed478 files with no findings. The first post-patch long-component test exposed a fixture cleanup issue (not a publication failure); it now removes its own extended-path test file before TemporaryDirectory cleanup. The failed log remains preserved.

## What this establishes

- Static observations with verifiable source/evidence can persist and be retrieved for the matching file version.
- Restarting the process does not erase those observations.
- A changed target does not silently inherit old evidence.

The experiment reports `verified_procedure=0` and `has_reusable_procedure=false`. It does not show application operation/repair procedure learning, model-weight training, arbitrary engine understanding or packaged GUI acceptance of the correction. `knowledge_reused` for cached external REA inventory is a different field; this test directly observes validated prior-record retrieval.

## Remaining product acceptance

After a newly built package containing the correction is verified and safely deployed, perform the same-file → normal close → reopen → same-question test through the real chat. Then test a modified copy, cancellation and corrupt evidence rejection. A real operational procedure needs independent successful executions and current preconditions; a saved static inventory is insufficient.

At this source checkpoint the installed package has not been changed. The user's manual test window remains under their control.

## Private evidence root

`C:\Users\LENAVO\.codex\backups\quartz-final-integration-20261102`

- `learning-publication-diagnostic-20261103/result.json`
- `learning-publication-diagnostic-20261103/matched-length-result.json`
- `learning-atomic-prepatch.log`
- `learning-atomic-postpatch.log` (contains a test-fixture long-path cleanup error; preserved)
- `learning-memory-roundtrip-20261103/result.json` plus the three phase records and real knowledge/evidence stores
- `learning-publication-targets-final.log` (90 tests PASS)
- `learning-publication-full-suite.log` (1234 cases, OK, skipped2)
- `learning-preservation-check.json` (36 non-log user files unchanged; installed EXE unchanged)
