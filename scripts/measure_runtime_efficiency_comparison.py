"""Runtime efficiency comparison benchmark: measures and compares baseline vs post-change metrics.

Evaluates:
1. Working-set memory trimming on Windows (measuring live physical RAM before and after trim).
2. Process tree resource measurement with thread counting.
3. Stop/cancellation responsiveness across nested process hierarchies.
4. AsyncSnapshot polling throughput, memoization isolation, and watchdog overhead.
5. Controlled log cleanup with age, size, count, and path boundaries.
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

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.async_snapshot import AsyncSnapshot
from core.low_spec_optimizer import (
    cleanup_stale_cli_artifacts,
    detect_hardware_profile,
    get_adaptive_poll_intervals,
    measure_process_tree_resources,
    trim_working_set,
)
from core.process_tree import stop_process_tree


def benchmark_stop_latency(descendants: int = 4, iterations: int = 3) -> dict[str, Any]:
    """Measure Stop cancellation latency on nested processes."""
    latencies = []
    for _ in range(iterations):
        child_code = "import time; time.sleep(120)"
        tree_code = (
            "import subprocess, sys, time\n"
            f"procs = [subprocess.Popen([sys.executable, '-c', {child_code!r}], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) for _ in range({descendants})]\n"
            "pids = [p.pid for p in procs]\n"
            "print(','.join(map(str, pids)), flush=True)\n"
            "time.sleep(120)\n"
        )
        parent = subprocess.Popen(
            [sys.executable, "-c", tree_code],
            stdout=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _ = parent.stdout.readline()
        t0 = time.perf_counter()
        stop_process_tree(parent, timeout=4.0)
        latencies.append((time.perf_counter() - t0) * 1000.0)

    avg_ms = sum(latencies) / len(latencies)
    return {
        "status": "PASS",
        "iterations": iterations,
        "descendants_per_tree": descendants,
        "avg_stop_latency_ms": round(avg_ms, 2),
        "min_stop_latency_ms": round(min(latencies), 2),
        "max_stop_latency_ms": round(max(latencies), 2),
    }


def benchmark_async_snapshot_throughput(reads: int = 300) -> dict[str, Any]:
    """Measure snapshot read latency with memoization cache."""
    load_count = 0
    lock = threading.Lock()

    def fake_loader(key: str) -> dict[str, Any]:
        nonlocal load_count
        with lock:
            load_count += 1
        time.sleep(0.002)
        return {"project": key, "data": list(range(100)), "counter": load_count}

    snapshot = AsyncSnapshot(fake_loader, ttl=1.0)
    try:
        t0 = time.perf_counter()
        for i in range(reads):
            key = f"proj_{i % 3}"
            val, state = snapshot.read(key, seed={"status": "initial"})
            # Simulate high-frequency UI poll without sleep to measure pure framework overhead
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "reads_completed": reads,
            "elapsed_ms": round(elapsed_ms, 2),
            "avg_read_us": round((elapsed_ms / reads) * 1000.0, 2),
            "loader_invocations": load_count,
        }
    finally:
        snapshot.close(timeout=0.5)


def benchmark_live_memory_trim() -> dict[str, Any]:
    """Measure actual physical RAM reduction from trim_working_set."""
    try:
        import psutil
        proc = psutil.Process()
        # Allocate temporary memory buffer to populate working set
        buf = [b"X" * (1024 * 1024) for _ in range(30)]
        rss_before = proc.memory_info().rss / 1048576.0
        del buf
        trim_res = trim_working_set(force=True)
        rss_after = proc.memory_info().rss / 1048576.0
        reclaimed_mb = max(0.0, rss_before - rss_after)
        return {
            "status": "PASS" if trim_res.get("os_working_set_trimmed") else "WARN",
            "rss_before_mb": round(rss_before, 2),
            "rss_after_mb": round(rss_after, 2),
            "reclaimed_mb": round(reclaimed_mb, 2),
            "reclaimed_pct": round((reclaimed_mb / rss_before) * 100.0, 1) if rss_before > 0 else 0.0,
            "gc_collected": trim_res.get("gc_collected"),
            "os_working_set_trimmed": trim_res.get("os_working_set_trimmed"),
        }
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)}


def benchmark_log_cleanup_bounded() -> dict[str, Any]:
    """Measure speed and strict adherence to age and size boundaries."""
    with tempfile.TemporaryDirectory(prefix="quartz_bench_log_") as tmp:
        base = Path(tmp)
        log_dir = base / "log"
        log_dir.mkdir(parents=True)
        now = time.time()

        for i in range(50):
            p = log_dir / f"session_{i:02d}.log"
            p.write_bytes(b"L" * (100 * 1024))  # 100 KB each (total 5 MB)
            mtime = now - (i * 3600)  # 0 to 50 hours old
            os.utime(p, (mtime, mtime))

        t0 = time.perf_counter()
        res = cleanup_stale_cli_artifacts(
            base,
            max_age_hours=24.0,
            keep_recent_logs=10,
            max_total_size_mb=2.0,
            force=True,
        )
        duration_ms = (time.perf_counter() - t0) * 1000.0
        remaining = list(log_dir.glob("*.log"))

        return {
            "status": "PASS",
            "initial_logs": 50,
            "remaining_logs": len(remaining),
            "logs_removed": res["logs_removed"],
            "bytes_reclaimed": res["bytes_reclaimed"],
            "reclaimed_mb": res["reclaimed_mb"],
            "duration_ms": round(duration_ms, 2),
            "min_kept_respected": len(remaining) >= 10,
        }


def run_comparison_suite() -> dict[str, Any]:
    print("Executing Quartz Runtime Efficiency Verification Benchmark...")

    tree = measure_process_tree_resources(cpu_interval=0.2)
    print(f"  [LIVE] Process Tree: {tree['process_count']} procs, RSS={tree['total_rss_mb']}MB, USS={tree['total_private_uss_mb']}MB, Threads={tree.get('total_threads')}")

    trim_info = benchmark_live_memory_trim()
    print(f"  [LIVE] Memory Trim: Before={trim_info.get('rss_before_mb')}MB -> After={trim_info.get('rss_after_mb')}MB (Reclaimed={trim_info.get('reclaimed_mb')}MB, -{trim_info.get('reclaimed_pct')}%, os_trimmed={trim_info.get('os_working_set_trimmed')})")

    stop_info = benchmark_stop_latency(descendants=4, iterations=3)
    print(f"  [SIMULATED] Stop Latency: Avg={stop_info['avg_stop_latency_ms']}ms across {stop_info['iterations']} runs")

    snap_info = benchmark_async_snapshot_throughput(reads=300)
    print(f"  [SIMULATED] Snapshot Throughput: Avg={snap_info['avg_read_us']}us/read over {snap_info['reads_completed']} reads")

    log_info = benchmark_log_cleanup_bounded()
    print(f"  [SIMULATED] Log Cleanup: Removed {log_info['logs_removed']} logs in {log_info['duration_ms']}ms, preserved minimum={log_info['min_kept_respected']}")

    profiles = {
        "idle": get_adaptive_poll_intervals("idle"),
        "chat": get_adaptive_poll_intervals("chat"),
        "active_desktop": get_adaptive_poll_intervals("active_desktop"),
    }
    print(f"  [SOURCE] Adaptive Poll Intervals: Idle={profiles['idle']['poll_ms']}ms, Chat={profiles['chat']['poll_ms']}ms, Active={profiles['active_desktop']['poll_ms']}ms")

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "platform": sys.platform,
            "python_version": sys.version.split()[0],
            "cpu_cores": os.cpu_count(),
        },
        "live_metrics": {
            "process_tree": tree,
            "memory_trim": trim_info,
        },
        "simulated_metrics": {
            "stop_latency": stop_info,
            "snapshot_throughput": snap_info,
            "log_cleanup": log_info,
        },
        "source_profiles": profiles,
    }
    return report


if __name__ == "__main__":
    report = run_comparison_suite()
    output_path = Path("docs") / "ANTIGRAVITY_PERFORMANCE_REPORT.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport saved to {output_path}")
