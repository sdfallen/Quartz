"""Measure full owned process-tree CPU and RAM for Quartz pyramid runtimes.

Profiles:
- Idle: base Python process tree before runtime initialization
- Startup: runtime instance creation + probe execution
- Active: running CLI process with child worker tree
- Stop: cancellation and stop_process_tree latency and resource release
- Shutdown: runtime shutdown and working set trimming

Usage:
    python -B scripts/measure_runtime_efficiency_pyramid.py [--json]
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.low_spec_optimizer import measure_process_tree_resources, trim_working_set
from core.codex_runtime import CodexRuntime
from core.antigravity_runtime import AntigravityRuntime
from core.process_tree import stop_process_tree


def run_benchmark():
    results = {}
    cores = os.cpu_count() or 2

    # 1. Idle Baseline
    idle_metrics = measure_process_tree_resources(cpu_interval=0.2)
    results["idle"] = {
        "status": "LIVE_MEASURED",
        "description": "Baseline Python process tree before runtime instantiation",
        "process_count": idle_metrics.get("process_count", 1),
        "total_rss_mb": idle_metrics.get("total_rss_mb", 0.0),
        "total_private_uss_mb": idle_metrics.get("total_private_uss_mb", 0.0),
        "total_cpu_pct": idle_metrics.get("total_cpu_pct", 0.0),
    }

    # 2. Startup Profile (Instantiate runtimes + probe cache)
    with tempfile.TemporaryDirectory(prefix="quartz-bench-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        fake_codex = tmp_path / "codex.exe"
        fake_codex.touch()
        t0 = time.perf_counter()
        codex_rt = CodexRuntime(fake_codex)
        probe_res = codex_rt.probe()
        t_startup = round((time.perf_counter() - t0) * 1000, 2)

        startup_metrics = measure_process_tree_resources(cpu_interval=0.2)
        results["startup"] = {
            "status": "LIVE_MEASURED",
            "description": "CodexRuntime instantiated and probed with probe caching",
            "startup_latency_ms": t_startup,
            "process_count": startup_metrics.get("process_count", 1),
            "total_rss_mb": startup_metrics.get("total_rss_mb", 0.0),
            "total_private_uss_mb": startup_metrics.get("total_private_uss_mb", 0.0),
            "total_cpu_pct": startup_metrics.get("total_cpu_pct", 0.0),
            "probe_installed": probe_res.get("installed", False),
        }

        # 3. Active Running Profile (Simulated child process tree)
        child_code = "import time; time.sleep(10)"
        parent_code = (
            "import subprocess,sys,time; "
            f"p=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
            "print(p.pid,flush=True); time.sleep(10)"
        )
        active_proc = subprocess.Popen(
            [sys.executable, "-c", parent_code],
            stdout=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _child_pid = active_proc.stdout.readline().strip()

        active_metrics = measure_process_tree_resources(cpu_interval=0.2)
        results["active_running"] = {
            "status": "LIVE_MEASURED",
            "description": "Active execution with parent + descendant child process tree",
            "process_count": active_metrics.get("process_count", 1),
            "total_rss_mb": active_metrics.get("total_rss_mb", 0.0),
            "total_private_uss_mb": active_metrics.get("total_private_uss_mb", 0.0),
            "total_cpu_pct": active_metrics.get("total_cpu_pct", 0.0),
            "breakdown": active_metrics.get("breakdown", {}),
        }

        # 4. Stop / Cancellation Responsiveness
        t_stop_0 = time.perf_counter()
        stop_success = stop_process_tree(active_proc, timeout=3.0)
        t_stop_ms = round((time.perf_counter() - t_stop_0) * 1000, 2)
        active_proc.stdout.close()

        stop_metrics = measure_process_tree_resources(cpu_interval=0.2)
        results["stop_cancellation"] = {
            "status": "LIVE_MEASURED",
            "description": "Process tree stopped via stop_process_tree",
            "stop_latency_ms": t_stop_ms,
            "stop_verified": stop_success,
            "process_count": stop_metrics.get("process_count", 1),
            "total_rss_mb": stop_metrics.get("total_rss_mb", 0.0),
            "total_private_uss_mb": stop_metrics.get("total_private_uss_mb", 0.0),
            "total_cpu_pct": stop_metrics.get("total_cpu_pct", 0.0),
        }

        # 5. Shutdown and Trim
        codex_rt.shutdown()
        trim_res = trim_working_set()
        shutdown_metrics = measure_process_tree_resources(cpu_interval=0.2)
        results["shutdown_trimmed"] = {
            "status": "LIVE_MEASURED",
            "description": "Post-shutdown memory trim and complete cleanup",
            "process_count": shutdown_metrics.get("process_count", 1),
            "total_rss_mb": shutdown_metrics.get("total_rss_mb", 0.0),
            "total_private_uss_mb": shutdown_metrics.get("total_private_uss_mb", 0.0),
            "total_cpu_pct": shutdown_metrics.get("total_cpu_pct", 0.0),
            "gc_collected": trim_res.get("gc_collected", 0),
            "os_working_set_trimmed": trim_res.get("os_working_set_trimmed", False),
        }

    return results


def main():
    results = run_benchmark()
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
        return 0

    print("=" * 70)
    print("QUARTZ PYRAMID RUNTIME & PROCESS TREE EFFICIENCY BENCHMARK")
    print("=" * 70)
    for profile, data in results.items():
        print(f"\n[{profile.upper()}] ({data.get('status')})")
        print(f"  Description:   {data.get('description')}")
        print(f"  Process Count: {data.get('process_count')}")
        print(f"  Total RSS:     {data.get('total_rss_mb')} MB")
        print(f"  Private USS:   {data.get('total_private_uss_mb')} MB")
        print(f"  Total CPU:     {data.get('total_cpu_pct')} %")
        if "startup_latency_ms" in data:
            print(f"  Startup Time:  {data.get('startup_latency_ms')} ms")
        if "stop_latency_ms" in data:
            print(f"  Stop Latency:  {data.get('stop_latency_ms')} ms (Verified: {data.get('stop_verified')})")
        if "os_working_set_trimmed" in data:
            print(f"  OS Trimmed:    {data.get('os_working_set_trimmed')} (GC: {data.get('gc_collected')})")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
