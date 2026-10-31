# Quartz Runtime Efficiency — Baseline Measurement Report

**Date:** 2026-10-31<br>
**Target Branch:** `antigravity/runtime-efficiency`<br>
**Baseline Commit:** `ee41b4005be2fc52c31dbe540886977aa95331cb` (Coordination Baseline on `main`)<br>
**Assigned Model / Role:** Antigravity 3.8 Flash High<br>
**Measurement Environment:**
- OS: Windows 10/11 x64 (Build 19045 / 22621)
- Python: 3.13.14 (64-bit)
- Hardware: 4 logical CPU cores, 8.0 GB RAM
- Baseline Suite: `scripts/measure_runtime_efficiency_baseline.py`

---

## 1. Initial Baseline Measurements (Pre-Optimization)

| Metric Category | Metric Name | Measured Baseline Value | Evidence Classification |
|---|---|---:|---|
| **Process Tree** | Process Count | 1 | LIVE |
| **Process Tree** | Total RSS | 24.94 MB | LIVE |
| **Process Tree** | Total Private USS | 10.32 MB | LIVE |
| **Process Tree** | CPU Usage (bounded 0.5s) | 0.0% | LIVE |
| **Process Tree** | Thread Count | 9 threads | LIVE |
| **Hardware Profile** | Cached lookup latency | 44.24 µs | LIVE |
| **Hardware Profile** | Force refresh latency | 82.20 µs | LIVE |
| **Hardware Profile** | Low-spec detection | `True` | LIVE |
| **Stop Responsiveness** | Simulated nested tree termination | 100.52 ms | SIMULATED |
| **AsyncSnapshot** | Snapshot read overhead | 3,022.32 µs / read | SIMULATED |
| **Log Cleanup** | Removal throughput (50 logs, 0.2 MB) | 257.06 ms | SIMULATED |
| **Working-Set Trim** | `os_working_set_trimmed` | **`False` (Failed)** | LIVE |

---

## 2. Identified Evidenced Hotspots

1. **64-bit Windows ctypes Handle Truncation in Working-Set Trimming (`core/low_spec_optimizer.py`):**
   - `ctypes.windll.kernel32.GetCurrentProcess()` default return type in ctypes was 32-bit `c_int`, returning `0xFFFFFFFF` instead of `(HANDLE)-1` (`0xFFFFFFFFFFFFFFFF`).
   - Passing `0xFFFFFFFF` to `SetProcessWorkingSetSize` caused `ERROR_INVALID_HANDLE` (Win32 Error 6), completely failing working-set reclamation on all 64-bit Windows machines.
2. **Stop Cancellation Latency in Process Tree Termination (`core/process_tree.py`):**
   - `psutil.wait_procs` was invoked with a fixed 5.0-second timeout block instead of an adaptive short-polling deadline, causing unnecessary stalling during Stop actions.
   - If parent process exited right before `stop_process_tree`, child processes were not inspected, leaving detached orphaned child processes running indefinitely.
3. **AsyncSnapshot Object Churn and Worker Hang Risk (`core/async_snapshot.py`):**
   - `deepcopy(self.value)` was re-executed unconditionally on every poll (every 1.5s - 2.5s) even when value was unchanged, producing high GC pressure.
   - If `loader` hung indefinitely, `self.worker` remained non-None forever, permanently stalling future refreshes without watchdog recovery.
4. **Coarse Polling Intervals and Log Boundary Gaps (`core/low_spec_optimizer.py`):**
   - Idle, normal chat, and active desktop task states lacked distinct adaptive intervals.
   - Log cleanup lacked total size capping (`max_total_size_mb`) and strict path-containment verification against symlink escapes.
