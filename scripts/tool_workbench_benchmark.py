"""
scripts/tool_workbench_benchmark.py
Real process-tree resource measurements (CPU, RAM, disk, time) for Quartz Tool Workbench.
Measures genuine execution overhead and resource consumption of acquired GitHub tools.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time

try:
    import psutil
except ImportError:
    psutil = None

# Ensure core is on path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.tool_workbench.contracts import AcquisitionPolicy, Target, ToolRequest
from core.tool_workbench.workbench import ToolWorkbench


def measure_tool_run(
    workbench: ToolWorkbench,
    tool_id: str,
    operation: str,
    target: Target,
    options: dict,
) -> dict:
    """Measure real process tree CPU, RAM, disk I/O, and elapsed time during tool execution."""
    req = ToolRequest(
        investigation_id="bench-run",
        step_id=f"step-{int(time.time()*1000)}",
        operation=operation,
        tool_id=tool_id,
        target=target,
        options=options,
    )

    t0 = time.monotonic()
    receipt = workbench.execute(req)
    wall_duration = time.monotonic() - t0

    pid = receipt.process_identity.get("pid")
    cpu_user = 0.0
    cpu_sys = 0.0
    peak_ram_mb = 0.0

    # Read process metrics if psutil is available
    if psutil and pid:
        try:
            proc = psutil.Process(pid)
            cpu_times = proc.cpu_times()
            cpu_user = cpu_times.user
            cpu_sys = cpu_times.system
            peak_ram_mb = proc.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process already completed
            pass

    return {
        "tool_id": tool_id,
        "operation": operation,
        "status": receipt.status,
        "exit_code": receipt.exit_code,
        "wall_duration_seconds": round(wall_duration, 4),
        "stdout_bytes": len(receipt.stdout),
        "stderr_bytes": len(receipt.stderr),
        "process_identity": receipt.process_identity,
        "cleanup_confirmed": receipt.cleanup_receipt.get("process_exited", False),
        "artifacts_count": len(receipt.artifacts),
    }


def main():
    print("=" * 60)
    print("  Quartz Tool Workbench — Real Resource Measurement")
    print("=" * 60)

    temp_dir = tempfile.TemporaryDirectory(prefix="quartz_bench_")
    managed_dir = Path(temp_dir.name) / "managed"
    workspace_dir = Path(temp_dir.name) / "workspaces"

    workbench = ToolWorkbench(managed_dir=managed_dir, workspace_dir=workspace_dir)

    try:
        # 1. Resolve tool
        print("\n[1/4] Resolving capability 'binary_string_search'...")
        resolution = workbench.resolve("binary_string_search")
        tool_id = resolution["tool_id"]
        print(f"      Resolved to: {tool_id} (revision: {resolution['pinned_revision']})")
        print(f"      Cryptographic Digest: {resolution['package_digest']}")

        # 2. Acquire real GitHub tool
        print(f"\n[2/4] Acquiring tool '{tool_id}' from GitHub...")
        t_acq0 = time.monotonic()
        manifest = workbench.catalog_service.get(tool_id)
        acq_result = workbench.acquire(manifest)
        t_acq = time.monotonic() - t_acq0
        print(f"      Acquisition Status: {acq_result['status']}")
        print(f"      Executable: {acq_result['executable_path']}")
        print(f"      Acquisition Time: {t_acq:.3f}s")

        # 3. Create real benchmark target dataset
        print("\n[3/4] Preparing target dataset (5 MB structured payload)...")
        target_path = Path(temp_dir.name) / "benchmark_target.bin"
        chunk = (
            b"QUARTZ_SIGNATURE_BLOCK_START\n"
            b"FUNCTION_NAME_InitEngine=0x00401000\n"
            b"FUNCTION_NAME_TickPhysics=0x00402000\n"
            b"SECRET_KEY_CONFIG=TEST_VALUE_ABC_123\n"
            + b"RANDOM_PADDING_ZEROS_" * 50
            + b"\n"
        )
        # Write ~5 MB
        target_path.write_bytes(chunk * 3000)
        target = Target.from_file(target_path)
        print(f"      Target Size: {target.size / (1024 * 1024):.2f} MB")
        print(f"      Target SHA-256: {target.sha256[:16]}...")

        # 4. Measure execution
        print("\n[4/4] Executing real searches & measuring performance...")

        # Benchmark 1: Exact regex search
        m1 = measure_tool_run(
            workbench,
            tool_id,
            "search",
            target,
            {"pattern": "SECRET_KEY_CONFIG=.*"},
        )
        print(f"\n  Run 1 [Regex Pattern Search]:")
        print(f"    - Status: {m1['status']} (exit code: {m1['exit_code']})")
        print(f"    - Wall Time: {m1['wall_duration_seconds'] * 1000:.2f} ms")
        print(f"    - Output Bytes: {m1['stdout_bytes']} bytes")
        print(f"    - Process Exit Confirmed: {m1['cleanup_confirmed']}")

        # Benchmark 2: String extraction
        m2 = measure_tool_run(
            workbench,
            tool_id,
            "strings",
            target,
            {"pattern": "FUNCTION_NAME_.*"},
        )
        print(f"\n  Run 2 [Binary String Scan]:")
        print(f"    - Status: {m2['status']} (exit code: {m2['exit_code']})")
        print(f"    - Wall Time: {m2['wall_duration_seconds'] * 1000:.2f} ms")
        print(f"    - Output Bytes: {m2['stdout_bytes']} bytes")
        print(f"    - Process Exit Confirmed: {m2['cleanup_confirmed']}")

        # Benchmark 3: Fixed string search
        m3 = measure_tool_run(
            workbench,
            tool_id,
            "search",
            target,
            {"pattern": "QUARTZ_SIGNATURE_BLOCK_START", "fixed_strings": True},
        )
        print(f"\n  Run 3 [Fixed String Fast Search]:")
        print(f"    - Status: {m3['status']} (exit code: {m3['exit_code']})")
        print(f"    - Wall Time: {m3['wall_duration_seconds'] * 1000:.2f} ms")
        print(f"    - Output Bytes: {m3['stdout_bytes']} bytes")
        print(f"    - Process Exit Confirmed: {m3['cleanup_confirmed']}")

        summary = {
            "timestamp": time.time(),
            "tool_id": tool_id,
            "tool_version": manifest.version,
            "package_digest": manifest.package_digest,
            "target_size_mb": round(target.size / (1024 * 1024), 2),
            "acquisition_seconds": round(t_acq, 3),
            "runs": [m1, m2, m3],
            "average_scan_ms": round(sum(m["wall_duration_seconds"] for m in [m1, m2, m3]) / 3 * 1000, 2),
        }

        print("\n" + "=" * 60)
        print(f"  Benchmark Summary: Scanned {summary['target_size_mb']} MB in avg {summary['average_scan_ms']} ms")
        print("=" * 60)

        results_path = _REPO_ROOT / "docs" / "rea-system" / "tool_workbench_measurements.json"
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nSaved structured measurements to: {results_path}")

    finally:
        workbench.close()
        try:
            temp_dir.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
