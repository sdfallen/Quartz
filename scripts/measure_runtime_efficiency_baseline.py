"""Runtime efficiency and resource measurement harness for Quartz.

Measures process tree working set, private memory (USS), CPU over bounded interval,
thread counts, polling/wakeup intervals, AsyncSnapshot thread churn, Stop responsiveness,
and log cleanup boundaries.
Separates simulated fixtures and live measurements with clear labels.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

# Ensure workspace root is in sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.async_snapshot import AsyncSnapshot
from core.low_spec_optimizer import (
    cleanup_stale_cli_artifacts,
    detect_hardware_profile,
    measure_process_tree_resources,
    trim_working_set,
)
from core.process_tree import stop_process_tree


def measure_current_process_resources(cpu_interval: float = 0.5) -> dict[str, Any]:
    """Live measurement of current Python process and any owned children."""
    data = measure_process_tree_resources(cpu_interval=cpu_interval)
    try:
        import psutil
        proc = psutil.Process()
        data["thread_count"] = proc.num_threads()
        data["handles_count"] = proc.num_handles() if hasattr(proc, "num_handles") else None
    except Exception:
        data["thread_count"] = threading.active_count()
        data["handles_count"] = None
    return data


def measure_stop_latency_simulated(descendant_count: int = 3) -> dict[str, Any]:
    """Measure cancellation responsiveness on a simulated multi-level process tree."""
    child_code = "import time; time.sleep(120)"
    tree_code = (
        "import subprocess, sys, time\n"
        f"procs = [subprocess.Popen([sys.executable, '-c', {child_code!r}], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) for _ in range({descendant_count})]\n"
        "pids = [p.pid for p in procs]\n"
        "print(','.join(map(str, pids)), flush=True)\n"
        "time.sleep(120)\n"
    )

    t0 = time.perf_counter()
    parent = subprocess.Popen(
        [sys.executable, "-c", tree_code],
        stdout=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    line = parent.stdout.readline().strip()
    spawn_time_ms = (time.perf_counter() - t0) * 1000.0
    child_pids = [int(p) for p in line.split(",") if p.isdigit()]

    # Now measure Stop responsiveness
    t_stop_start = time.perf_counter()
    stop_process_tree(parent, timeout=4.0)
    stop_latency_ms = (time.perf_counter() - t_stop_start) * 1000.0

    try:
        import psutil
        alive_children = [pid for pid in child_pids if psutil.pid_exists(pid)]
    except Exception:
        alive_children = []

    return {
        "status": "PASS" if len(alive_children) == 0 else "FAIL",
        "spawn_time_ms": round(spawn_time_ms, 2),
        "stop_latency_ms": round(stop_latency_ms, 2),
        "descendants_requested": descendant_count,
        "descendants_terminated": descendant_count - len(alive_children),
        "leaked_pids": alive_children,
    }


def measure_async_snapshot_profile(reads: int = 150) -> dict[str, Any]:
    """Measure snapshot read overhead, thread creations, and cache performance."""
    load_count = 0
    lock = threading.Lock()

    def fake_loader(key: str) -> dict[str, Any]:
        nonlocal load_count
        with lock:
            load_count += 1
        time.sleep(0.005)
        return {"key": key, "timestamp": time.time(), "counter": load_count}

    snapshot = AsyncSnapshot(fake_loader, ttl=0.1)
    threads_before = threading.active_count()

    t0 = time.perf_counter()
    keys = ["proj_a", "proj_a", "proj_a", "proj_b", "proj_b"]
    for i in range(reads):
        key = keys[i % len(keys)]
        val, state = snapshot.read(key, seed={"initial": True})
        time.sleep(0.002)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    snapshot.close()

    return {
        "reads_completed": reads,
        "elapsed_ms": round(elapsed_ms, 2),
        "avg_read_us": round((elapsed_ms / reads) * 1000.0, 2),
        "loader_invocations": load_count,
        "threads_delta": threading.active_count() - threads_before,
    }


def measure_hardware_profile_overhead(iterations: int = 50) -> dict[str, Any]:
    """Measure CPU/latency cost of hardware detection and cached profile retrieval."""
    t0 = time.perf_counter()
    for _ in range(iterations):
        detect_hardware_profile(force_refresh=False)
    cached_us = ((time.perf_counter() - t0) / iterations) * 1_000_000.0

    t1 = time.perf_counter()
    p = detect_hardware_profile(force_refresh=True)
    refresh_us = (time.perf_counter() - t1) * 1_000_000.0

    return {
        "cached_lookup_us": round(cached_us, 2),
        "force_refresh_us": round(refresh_us, 2),
        "low_spec_mode": p.get("low_spec_mode"),
        "total_ram_gb": p.get("total_ram_gb"),
        "available_ram_gb": p.get("available_ram_gb"),
        "ram_percent": p.get("ram_percent"),
        "idle_poll_ms": p.get("idle_poll_ms"),
    }


def measure_log_cleanup_boundaries() -> dict[str, Any]:
    """Simulate log directory growth and verify bound enforcement and speed."""
    with tempfile.TemporaryDirectory(prefix="quartz_bench_log_") as tmp:
        base = Path(tmp)
        log_dir = base / "log"
        log_dir.mkdir(parents=True)

        now = time.time()
        # Create 100 simulated log files (50 old > 72h, 50 fresh < 2h)
        for i in range(100):
            p = log_dir / f"session_{i:03d}.log"
            content = f"timestamp={now} log_entry_{i}\n" * 100
            p.write_text(content, encoding="utf-8")
            if i < 50:
                old_time = now - (72 * 3600 + i * 60)
                os.utime(p, (old_time, old_time))
            else:
                fresh_time = now - (i * 60)
                os.utime(p, (fresh_time, fresh_time))

        t0 = time.perf_counter()
        result = cleanup_stale_cli_artifacts(
            base,
            max_age_hours=48.0,
            keep_recent_logs=20,
            force=True,
        )
        duration_ms = (time.perf_counter() - t0) * 1000.0

        remaining_logs = list(log_dir.glob("*.log"))
        return {
            "initial_logs": 100,
            "remaining_logs": len(remaining_logs),
            "logs_removed": result["logs_removed"],
            "bytes_reclaimed": result["bytes_reclaimed"],
            "reclaimed_mb": result["reclaimed_mb"],
            "duration_ms": round(duration_ms, 2),
            "boundary_respected": len(remaining_logs) >= 20,
        }


def run_full_baseline_benchmark() -> dict[str, Any]:
    print("Running Quartz Runtime Efficiency Baseline Measurements...")
    current = measure_current_process_resources(cpu_interval=0.5)
    print(f"  [LIVE] Process resources: {current['process_count']} procs, RSS={current.get('total_rss_mb')}MB, USS={current.get('total_private_uss_mb')}MB, CPU={current.get('total_cpu_pct')}%, Threads={current.get('thread_count')}")

    hw = measure_hardware_profile_overhead()
    print(f"  [LIVE] Hardware profile: cached={hw['cached_lookup_us']}us, refresh={hw['force_refresh_us']}us, low_spec={hw['low_spec_mode']}")

    stop_bench = measure_stop_latency_simulated(descendant_count=3)
    print(f"  [SIMULATED] Stop latency: {stop_bench['stop_latency_ms']}ms, terminated {stop_bench['descendants_terminated']}/{stop_bench['descendants_requested']}")

    snap_bench = measure_async_snapshot_profile(reads=150)
    print(f"  [SIMULATED] Snapshot read overhead: {snap_bench['avg_read_us']}us/read over {snap_bench['reads_completed']} reads")

    log_bench = measure_log_cleanup_boundaries()
    print(f"  [SIMULATED] Log cleanup: removed {log_bench['logs_removed']} logs ({log_bench['reclaimed_mb']}MB) in {log_bench['duration_ms']}ms")

    trim_res = trim_working_set(force=True)
    print(f"  [LIVE] Working-set trim: gc_collected={trim_res.get('gc_collected')}, os_trimmed={trim_res.get('os_working_set_trimmed')}")

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "platform": sys.platform,
            "python_version": sys.version.split()[0],
            "cpu_cores": os.cpu_count(),
        },
        "live_metrics": {
            "process_tree": current,
            "hardware_profile": hw,
            "trim_working_set": trim_res,
        },
        "simulated_metrics": {
            "stop_cancellation": stop_bench,
            "async_snapshot": snap_bench,
            "log_cleanup": log_bench,
        },
    }
    return report


if __name__ == "__main__":
    report = run_full_baseline_benchmark()
    output_path = Path("docs") / "ANTIGRAVITY_PERFORMANCE_BASELINE.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nBaseline written to {output_path}")
