# Codex native / managed / package analysis delivery

Date: 2026-11-02. Shared baseline: `e476c2fbd42c19f050d1a1e896959fe2e3ccd19d`.
No staging, commits, installation, public upload, target patching or live Quartz replacement was performed by this specialist. Parent owns integration and release acceptance.

## Delivered implementation

- `core/rea_analysis/__init__.py`: public `AnalysisService` import.
- `core/rea_analysis/service.py`: `capabilities(target)` and synchronous `analyze(request, tool_executor, cancel_event)` JSON v1 facade, cancellation/deadline and target revalidation, bounded snapshots, host evidence linkage, cleanup receipts and explicit unsupported capabilities. `runtime_identity()` hashes trusted loaded code/defaults/parser constants/class bases and descriptors, with Python bytecode/patch version; no source-file or loader reads, subprocess or filename/line-table dependency. Tested fingerprint changes on real code/limit changes, while debug-path/line changes preserve it.
- `core/rea_analysis/binary.py`: real PE/COFF parsing; section/RVA mappings, named/ordinal import thunks with IAT relationships, named/ordinal exports and forwarders, x64 exception function range/unwind relationships.
- `core/rea_analysis/managed.py`: CLI header/BSJB streams, correctly sized ECMA-335 metadata table layouts; assembly identities, AssemblyRefs, TypeDef-to-MethodDef ownership, method RVAs/flags, public top-level type API declarations and ImplMap-to-ModuleRef P/Invoke relationships. Arbitrary embedded strings are not treated as metadata.
- `core/rea_analysis/packages.py`: classic ZIP central directory and bounded public package.json dependency metadata; PyInstaller 2.1+ CArchive cookie/TOC with per-member type, offsets, compressed/uncompressed sizes and declared Python runtime; standalone unencrypted Godot PCK v2/v3/v4 with actual resource path/range mapping and chunked MD5+SHA256 payload validation. No extraction or target execution.
- `tests/test_rea_analysis_structure.py`: 24 meaningful tests including real installed native binaries, an actually compiled managed fixture, real installed PyInstaller writer/reader agreement, exact real Godot4.7.1 PCKPacker output, identity invalidation and real host capture/acceptance.
- `labs/rea-analysis/validate.py`: repeatable isolated validation harness. It writes only under its own lab, copies two installed CPython artifacts, compiles a local C# library with already-installed Microsoft csc and creates genuine ZIP/CArchive fixtures. No downloads or target process execution.
- `labs/rea-analysis/godot_experiment.py`: explicitly separate experimental host harness; copies only the approved Godot tool executable into the lab, runs a tiny fresh headless project there, generates genuine PCKs, verifies actual resource replacement semantics and then invokes the static facade on those files. It does not read the older game's project source/assets. This harness executes the engine; AnalysisService never does.

The module has no subprocess launcher, downloader, runtime injector, alternate acquisition manager, repository instruction interpreter, global evidence writer or memory store. Any external request is routed only through injected `tool_executor.execute`; its raw receipt is not interpreted as disassembly or promoted to verified semantics.

## Host interface

Parent implemented the requested boundary in its owned `core/investigation/gateway.py`:

```python
tool_executor.capture_analysis(artifact_path, expected_sha256, request, cancel_event)
# -> {"evidence_ids": [...], "instruction_authority": False, ...}
```

Snapshot operation is `builtin-analysis-snapshot`, tool ID `quartz-builtin-analysis`. It contains schema_version, parser/version, target_sha256, evidence_level=SOURCE, runtime_observed=false and concrete observed structures. The gateway validates target identity, workspace ownership, expected digest, scope and step replay, then persists the snapshot. A missing capture callback produces no findings or invented evidence IDs. Workspace snapshots are deleted after capture; artifacts in the report use snapshot_name/digest/evidence_ids rather than a nonexistent local path. Persisted paths are in the host manifest.

Request contains investigation_id, step_id, target (complete Target dict), workspace, deadline_monotonic and max_output_bytes. Builtin analysis needs read_target + write_workspace in the host policy, with no execute_tool effect. Options may be empty or `external_tool={tool_id,operation,options}`; external effects and pinned tool provenance remain the gateway/workbench responsibility. Avoid assigning user-provided shell commands to these fields.

Capability IDs used: `pe-structure`, `dotnet-metadata`, `package-inventory`, and `engine-signatures` only when an actual structural engine dependency is observed. `native-disassembly` and `runtime-observation` are unavailable. `capabilities()` performs a non-executing header/footer probe; `analyze()` revalidates the full target before accepting anything. No SOURCE result becomes LIVE or verified_procedure.

## Verification and real artifacts

Command: `python -B -m unittest tests.test_rea_analysis_structure -v`.
Final result: **24 tests, 0 failures, 0 skips**, recorded in `labs/rea-analysis/targeted-tests.log`.

Command: `python -B labs/rea-analysis/validate.py`.
Final frozen-parser run: `labs/rea-analysis/validation-20261102T133751Z/manifest.json`.
The manifest binds exact parser/gateway/test/harness hashes, runtime semantic identity, compiler digest, artifact digests, Python/platform and tool versions, per-case measured wall/process-CPU/traced-allocation data, target unchanged checks, host evidence IDs/digests and cleanup receipts. Earlier validation runs remain evidence for their earlier source hashes; use the 13:37:51 run for this delivery. The final run also reanalyzes genuine base/mod PCKs from the separately recorded 13:35:50 actual engine experiment.

| Case | Actual structural result | Evidence scope |
|---|---|---|
| CPython native executable copy | PE64, 26 imported libraries, actual symbol-to-IAT records and 233 x64 unwind relationships | SOURCE static analysis of installed-binary copy; no process run |
| CPython `_socket.pyd` copy | Actual named export `PyInit__socket` mapped to ordinal/RVA, imports and 223 unwind relationships | SOURCE static analysis of installed-binary copy; no module load |
| Microsoft csc-built Fixture.dll | Actual `QuartzFixture.Counter`, interface/generic types, Add/Describe methods and TypeDef ownership, assembly version1.2.3.4, mscorlib AssemblyRef and kernel32/GetTickCount P/Invoke | BUILT fixture provenance; analysis evidence remains SOURCE |
| Installed PyInstaller6.20.0 CArchiveWriter package | Genuine archive inventory of Fixture.dll and settings.json; independently checked against installed CArchiveReader and exact extracted settings payload | BUILT package provenance; parser output SOURCE |
| ZIP of compiled library/data/manifest | Actual three-member central directory and public package metadata | BUILT packaging fixture; parser output SOURCE |
| Unknown file containing engine names | No findings/capabilities; explicit unsupported format | SOURCE negative fixture; engine text does not become engine detection |
| Actual Godot4.7.1-generated base/mod PCKs | PCKv4, declared writer4.7.1, actual res://data/settings.json paths/ranges, independently computed member MD5+SHA256 | Actual engine-generated fixture provenance; facade evidence remains SOURCE |

Every supported report was accepted by the real `InvestigationSession.accept_analysis`, and every cited ID resolves to a real host-captured SOURCE artifact with matching digest. Analyzed target hashes stayed equal; parser workspaces were empty after successful cleanup. Cancellation during the capture fence clears findings; repeated identical analysis reuses the host capture identity; changed targets, output limits, missing write scope and missing capture are rejected. Cleanup failures are reported. External unknown outcomes remain pending rather than claiming confirmed cleanup.

The measured traced allocation includes existing host evidence ingestion. The current `EvidenceRepository.ingest_file()` allocates about64MiB because it reads MAX_FILE_BYTES+1 in one call, even for small snapshots. This finding was sent to the parent for Claude's ownership; this specialist did not edit evidence.py. Do not attribute that allocation to successful parser optimization.

REA6.8.0 was actually discoverable through `ReaAdapter.discover()` during this work. This facade does not pretend its existing inventory-only operation provides instruction decoding, native call xrefs, method semantics or live engine behavior. No REA package revision was changed.

### Actual isolated engine experiment

Command: `python -B labs/rea-analysis/godot_experiment.py`.
Evidence: `labs/rea-analysis/godot-20261102T133550Z/manifest.json`, `process.json`, engine.stdout/stderr/log, fresh GDScript/project/payload sources, generated base/mod.pck and host-store manifests.

The copied tool reported actual `4.7.1-stable (official)` engine hash `a13da4feb8d8aefc283c3763d33a2f170a18d541`. Its source and copied executable SHA-256 values stayed equal. Original-tool file only was read/copied; no older project source/assets were read. The headless test ran inside the new lab project with child TEMP/TMP/profile variables redirected and an explicit lab log path. It exited0 and was reaped. Fresh fixture source/payload digests stayed equal.

The real engine generated both packs. Base load produced `{value:7}`; mod load with `replace_files=false` retained7; mod load with `replace_files=true` produced42. That demonstrates the specified Godot4.7.1 resource replacement boundary on these JSON packs. It does not claim a UI test, all-game modding support, script compatibility or packaged Quartz acceptance. The static facade produced three host-captured SOURCE findings per PCK and never promoted this separate runtime log into LIVE evidence. The actual179MB engine binary exceeds the128MiB static reader limit, so its native executable was not falsely marked analyzed.

## Open acceptance items and limits

- The Godot4.7.1 PCK/data replacement experiment above is complete within its narrow observed scope. Structural UnityPlayer imports or UnityEngine/GodotSharp AssemblyRefs are additional implemented detection paths; none was fabricated as a live Unity/managed-Godot test. ZIP Electron dependencies are explicitly described as manifest declarations, not working runtime proof.
- Native instruction disassembly, semantic function behavior, instruction call xrefs, runtime/UI behavior, packaged Quartz chat integration, Stop of an externally owned actual disassembler process and installed-build acceptance remain outside this delivered static scope. Parent and workbench owners retain those gates.
- Input maximum128MiB; up to96 PE sections,8192 observed import/export/runtime-function/package/managed items (managed aggregate bound),32 metadata streams. Snapshot maximum4MiB and final report maximum512KiB, additionally limited by request output budget. Exceeding limits fails honestly; a large game may require a later streaming adapter.
- Delay-loaded imports, debug/PDB symbols, signature verification, native ABI signatures, CLR IL semantics/signature-blob decoding, metadata pointer tables and extended table layouts are unsupported. x64 unwind tables do not cover every function. Absence from these tables is not proof of absence from runtime behavior.
- ZIP64/multi-disk, encrypted manifest payloads, embedded/encrypted/sparse/delta/removal Godot PCK variants, Unreal PAK and old pre-2.1 PyInstaller cookie formats are unsupported. ZIP declared CRC/size metadata is not independently verified payload integrity. CArchive member names/types are inventory, not decompiled Python code.
- Native loader imports and public CLR methods describe declared loading/API boundaries. They are not claims of supported mod APIs, exercised plugin discovery or compatible mods.
- `labs/` is gitignored in this checkout. Recommended force-included review sources: only `labs/rea-analysis/validate.py` and `godot_experiment.py`. Preserve `validation-*`, `godot-*` directories, generated/compiled binaries, engine copies and host-store artifacts in the private checkpoint; keep them out of the production installer. No git index mutation was performed here.

## Primary references

- [Microsoft PE/COFF specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format): headers, import/export directories and platform exception tables.
- [ECMA-335, sixth edition](https://ecma-international.org/publications-and-standards/standards/ecma-335/), PartitionII sections22/24: metadata tables, streams and coded/table indexes.
- [PyInstaller CArchive documentation/source](https://github.com/pyinstaller/pyinstaller/blob/develop/doc/advanced-topics.rst): cookie/TOC layout, additionally verified against the actual installed6.20.0 writer and reader source/API. Current upstream capabilities were not assumed to describe REA6.8.0.
- Godot pinned4.7.1 official [pack header flags](https://raw.githubusercontent.com/godotengine/godot/4.7.1-stable/core/io/file_access_pack.h), [reader](https://raw.githubusercontent.com/godotengine/godot/4.7.1-stable/core/io/file_access_pack.cpp), [writer](https://raw.githubusercontent.com/godotengine/godot/4.7.1-stable/core/io/pck_packer.cpp) and [resource-pack API documentation](https://docs.godotengine.org/en/stable/classes/class_pckpacker.html).
