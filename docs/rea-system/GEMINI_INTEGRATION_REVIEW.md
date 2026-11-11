# Gemini ToolWorkbench integration review

Date: 2026-11-02. Review/fix integration tree: `C:/Users/LENAVO/.codex/worktrees/quartz-rea-codex`.
Original delivery: `c6ada13a3184826d406f5c0dce516fda62b2f776`, documentation `2a9e1f8`, in the separate `quartz-rea-gemini` tree. The original delivery was preserved. Review findings and integration fixes are separate from its original production/live claims.

## Original findings and integration scope

| Original finding | Integration treatment |
| --- | --- |
| Manifest tool/revision traversal could delete a directory outside the managed root, before offline rejection. | Acquisition validates identifiers, contained paths and links before mutation; policy cannot change its configured root. |
| Absolute executable subpaths could nominate an existing executable absent from the verified archive. | Acquisition requires a contained relative package path and rejects links/reparse points. |
| Cached executables/dependencies were not hashed; same-ID cache entries could execute bytes under different reported provenance. | Full manifest fingerprints, package-derived file inventories, cache verification and facade pre-execution provenance validation. Local receipt/file rewriting by the same OS account remains outside this integrity guarantee. |
| Close could confirm during an unregistered spawn and permit late work; acquisition was not owned by Stop. | Executor reservations precede spawn, closed/admission states reject late work, and facade/acquisition lifecycle owns its outstanding operations. |
| Child cleanup was asserted unconditionally; failures/drains/duplicate IDs could lose ownership. | Suspended Windows creation assigns a kernel Job Object before resume. Parent exit does not release descendants. Reservations remain until observed job/process/drain completion; uncertain cleanup stays pending, duplicate live IDs are rejected. |
| Returned dataclass/status/cleanup shape did not satisfy the investigation gateway. | Facade dictionary requests return the canonical serialized receipt, preserving the gateway request ID and mapping terminal statuses; typed callers retain compatibility. Cleanup has an explicit observed status. |
| Default executor construction referenced an unimported `tempfile`. | Default construction fixed and covered. |
| Pre-cancelled/expired work still spawned; deadlines/output/options lacked finite/type bounds. | Admission checks precede side effects; finite deadlines, manifest timeout ceilings, bounded output and option types/ranges/enums are enforced. Target file scope/hash/size is revalidated around execution. |
| Arbitrary/stale workspaces and unbounded/link-following artifact reads corrupted scope and evidence. | Configured-root containment, fresh per-run directories, regular-file/link checks, streaming bounded hashes, entry/count/byte/time bounds. Artifact paths are relative to the supplied workspace. |
| Serialized stdout-only results retained counts but no match evidence. | Bounded stdout/stderr are persisted as SHA-256 artifact files. Parent evidence ingestion can retain and independently verify the result. |

The default catalog retains the actual ripgrep candidate; unverified `quartz-assistant/pe-inspector` and `quartz-assistant/rea-agents` remote entries were removed. Generic Python execution in a frozen Quartz process fails explicitly rather than using `Quartz.exe` as a Python interpreter. Job ownership, cwd and environment filtering are process supervision/policy controls, not an OS filesystem/network sandbox. Packaged application/UI acceptance and official live tool acquisition are separate gates; mock success and original benchmark text do not prove those gates.

## Actual full-suite fixture failure and correction

The frozen-candidate source suite at `d69e04f` found one failure: `test_child_process_tree_termination` expected `timeout`, received `failed`. Parent log: `C:/Users/LENAVO/.codex/backups/quartz-final-integration-20261102/rea-final-frozen-suite.log`.

A focused 24-run diagnostic reproduced 13 `failed` and 11 `timeout` receipts. All 24 had exit code 1 and confirmed process/child/drain cleanup. Failed stderr identified the actual operation:

```text
runner.py:46, p = subprocess.Popen(cmd)
cmd = ["cmd.exe", "/c", "ping", "127.0.0.1", "-n", "20"]
_winapi.CreateProcess(...)
FileNotFoundError: [WinError 2]
```

The tool environment deliberately strips PATH. The fixture depended on resolving `cmd.exe` by name. Its former 500 ms deadline sometimes arrived before this startup error was observed, so a passing timeout did not prove a child started. `COMSPEC` and `SYSTEMROOT` were present; cleanup was not pending. The diagnostic also observed Windows-generated `%SystemDrive%/ProgramData/Microsoft/Windows/Caches/` files within some disposable run directories; those were temporary fixture artifacts, not proof of a process leak. Temporary diagnostic fixtures were removed by their teardown.

Only the test fixture changed for this failure; production execution code was not relaxed. It now uses the explicit `sys.executable` to start a local sleeping child, emits a `CHILD_READY` handshake and raw child PID, and allows two seconds for startup before the real deadline. Assertions still require `timeout`, additionally require the handshake/PID, verify both root and child PIDs are gone, and require confirmed process/child/drain cleanup. Failure diagnostics include the full receipt/stdout/stderr.

Verification after the fixture correction:

```text
python -B -m unittest tests.test_tool_workbench_execution.TestToolWorkbenchExecution.test_child_process_tree_termination -v
Ran 1 test in 2.144s — OK

python -B -m unittest tests.test_tool_workbench_execution tests.test_tool_workbench_execution_safety -q
Ran 25 tests in 17.950s — OK
```

These are real harmless local process tests plus event-controlled unit regressions, with no network/provider/UI calls. They do not constitute deployment or live user-task acceptance. No production rebuild is required solely for this test/documentation correction; the integration owner retains final suite, packaging and deployment authority.
