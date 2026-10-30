"""Low-spec hardware detection, memory trimming, lazy client proxies, and WebView2 optimization.

Designed to allow Quartz to run smoothly on older / low-RAM (4GB-8GB) and dual-core laptops
by minimizing startup imports, capping background WebView2 processes, throttling idle polling,
and reclaiming unused working-set pages after heavy tasks.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import gc
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable


_TRIM_LOCK = threading.Lock()
_LAST_TRIM_AT = 0.0
_HOUSEKEEPING_LOCK = threading.Lock()
_LAST_HOUSEKEEPING_AT = 0.0
_PROFILE_CACHE: dict[str, Any] | None = None
_PROFILE_CACHE_AT = 0.0

LOW_SPEC_WEBVIEW_FLAGS = (
    "--disable-features=Translate,OptimizationHints,MediaRouter,"
    "CalculateNativeWinOcclusion,BackForwardCache,SpareRendererForSitePerProcess",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--metrics-recording-only",
    "--no-first-run",
    "--renderer-process-limit=2",
)


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _query_windows_memory() -> tuple[float, float, float]:
    """Return (total_gb, avail_gb, percent_used) without importing psutil."""
    if sys.platform == "win32":
        try:
            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_gb = stat.ullTotalPhys / (1024 ** 3)
                avail_gb = stat.ullAvailPhys / (1024 ** 3)
                return (
                    round(total_gb, 2),
                    round(avail_gb, 2),
                    float(stat.dwMemoryLoad),
                )
        except Exception:
            pass
    try:
        import psutil
        vm = psutil.virtual_memory()
        return (
            round(vm.total / (1024 ** 3), 2),
            round(vm.available / (1024 ** 3), 2),
            float(vm.percent),
        )
    except Exception:
        return (8.0, 4.0, 50.0)


def detect_hardware_profile(force_refresh: bool = False) -> dict[str, Any]:
    """Return hardware capabilities and adaptive resource limits for Quartz."""
    global _PROFILE_CACHE, _PROFILE_CACHE_AT
    now = time.monotonic()
    if not force_refresh and _PROFILE_CACHE is not None and (now - _PROFILE_CACHE_AT) < 30.0:
        return dict(_PROFILE_CACHE)

    total_gb, avail_gb, mem_pct = _query_windows_memory()
    cpu_cores = os.cpu_count() or 2

    env_override = os.environ.get("QUARTZ_LOW_SPEC", "").strip().lower()
    if env_override in {"1", "true", "yes", "on"}:
        low_spec = True
    elif env_override in {"0", "false", "no", "off"}:
        low_spec = False
    else:
        # Consider <= 8.5 GB RAM, <= 4 logical cores, or high memory pressure (>= 82%) as low-spec
        low_spec = (total_gb <= 8.5) or (cpu_cores <= 4) or (mem_pct >= 82.0) or (avail_gb < 1.8)

    profile = {
        "low_spec_mode": bool(low_spec),
        "total_ram_gb": total_gb,
        "available_ram_gb": avail_gb,
        "ram_percent": round(mem_pct, 1),
        "cpu_cores": int(cpu_cores),
        "max_uia_elements": 150 if low_spec else 250,
        "max_uia_depth": 4 if low_spec else 5,
        "idle_poll_ms": 2400 if low_spec else 1500,
        "minimized_poll_ms": 5000,
        "stats_poll_ms": 6000 if low_spec else 3500,
        "tasks_poll_ms": 9000 if low_spec else 6000,
        "ping_poll_ms": 8000 if low_spec else 5000,
    }
    _PROFILE_CACHE = profile
    _PROFILE_CACHE_AT = now
    return dict(profile)


def configure_webview_environment() -> str:
    """Apply memory-saving WebView2 Chromium arguments before window creation."""
    existing = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "").strip()
    parts = [p for p in existing.split() if p]
    for flag in LOW_SPEC_WEBVIEW_FLAGS:
        prefix = flag.split("=", 1)[0]
        if not any(p == flag or p.startswith(prefix + "=") for p in parts):
            parts.append(flag)
    combined = " ".join(parts)
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = combined
    return combined


def trim_working_set(
    force: bool = False,
    min_interval_sec: float = 15.0,
    include_children: bool = True,
) -> dict[str, Any]:
    """Run garbage collection and ask the OS to reclaim unused working-set pages
    across both the main Quartz process and owned WebView2 child processes."""
    global _LAST_TRIM_AT
    now = time.monotonic()
    with _TRIM_LOCK:
        if not force and (now - _LAST_TRIM_AT) < min_interval_sec:
            return {"trimmed": False, "reason": "throttled"}
        _LAST_TRIM_AT = now

    collected = gc.collect()
    os_trimmed = False
    children_trimmed = 0
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetCurrentProcess()
            res = kernel32.SetProcessWorkingSetSizeEx(
                handle,
                ctypes.c_size_t(-1),
                ctypes.c_size_t(-1),
                0,
            )
            os_trimmed = bool(res)
            if include_children:
                try:
                    import psutil
                    PROCESS_SET_QUOTA = 0x0100
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    current = psutil.Process()
                    for child in current.children(recursive=True):
                        cname = (child.name() or "").lower()
                        if "webview2" not in cname and "quartz" not in cname:
                            continue
                        h_child = kernel32.OpenProcess(
                            PROCESS_SET_QUOTA | PROCESS_QUERY_LIMITED_INFORMATION,
                            False,
                            int(child.pid),
                        )
                        if h_child:
                            try:
                                if kernel32.SetProcessWorkingSetSizeEx(
                                    h_child,
                                    ctypes.c_size_t(-1),
                                    ctypes.c_size_t(-1),
                                    0,
                                ):
                                    children_trimmed += 1
                            finally:
                                kernel32.CloseHandle(h_child)
                except Exception:
                    pass
        except Exception:
            os_trimmed = False

    return {
        "trimmed": True,
        "gc_collected": int(collected),
        "os_working_set_trimmed": os_trimmed,
        "children_trimmed": int(children_trimmed),
    }


def measure_process_tree_resources(
    root_pid: int | None = None,
    cpu_interval: float = 0.0,
) -> dict[str, Any]:
    """Measure total RAM (RSS & private USS) and CPU across Quartz + WebView2 + CLI children."""
    try:
        import psutil
        root = psutil.Process(root_pid) if root_pid else psutil.Process()
        tree = [root] + root.children(recursive=True)
        if cpu_interval > 0:
            for p in tree:
                try:
                    p.cpu_percent(None)
                except Exception:
                    pass
            time.sleep(cpu_interval)
        cores = psutil.cpu_count() or 1
        total_rss = 0
        total_uss = 0
        total_cpu = 0.0
        breakdown = {
            "quartz_rss_mb": 0.0,
            "webview2_rss_mb": 0.0,
            "cli_rss_mb": 0.0,
            "quartz_cpu_pct": 0.0,
            "webview2_cpu_pct": 0.0,
            "cli_cpu_pct": 0.0,
        }
        alive_count = 0
        for p in tree:
            try:
                name = (p.name() or "").lower()
                mi = p.memory_full_info()
                rss = int(mi.rss)
                uss = int(getattr(mi, "uss", rss))
                cpu = (p.cpu_percent(None) / cores) if cpu_interval > 0 else 0.0
                total_rss += rss
                total_uss += uss
                total_cpu += cpu
                alive_count += 1
                if "webview2" in name:
                    breakdown["webview2_rss_mb"] += rss / 1048576
                    breakdown["webview2_cpu_pct"] += cpu
                elif p.pid == root.pid or name in {"quartz.exe", "python.exe", "pythonw.exe"}:
                    breakdown["quartz_rss_mb"] += rss / 1048576
                    breakdown["quartz_cpu_pct"] += cpu
                else:
                    breakdown["cli_rss_mb"] += rss / 1048576
                    breakdown["cli_cpu_pct"] += cpu
            except Exception:
                continue
        return {
            "root_pid": int(root.pid),
            "process_count": alive_count,
            "total_rss_mb": round(total_rss / 1048576, 2),
            "total_private_uss_mb": round(total_uss / 1048576, 2),
            "total_cpu_pct": round(total_cpu, 2),
            "breakdown": {k: round(v, 2) for k, v in breakdown.items()},
        }
    except Exception as exc:
        return {
            "root_pid": root_pid or os.getpid(),
            "process_count": 1,
            "total_rss_mb": 0.0,
            "total_private_uss_mb": 0.0,
            "total_cpu_pct": 0.0,
            "error": str(exc),
        }


def cleanup_stale_cli_artifacts(
    gemini_home: str | Path | None = None,
    *,
    max_age_hours: float = 48.0,
    keep_recent_logs: int = 40,
    keep_recent_backups: int = 5,
    force: bool = False,
) -> dict[str, Any]:
    """Controlled housekeeping of stale CLI logs, orphaned lock files, and old settings backups.

    Safety invariants:
    - Never deletes the most recent ``keep_recent_logs`` diagnostic log files.
    - Never deletes any file younger than ``max_age_hours``.
    - Never deletes ``presence/*.lock`` if any ``agy`` / ``antigravity`` CLI process is active.
    - Never touches conversations, credentials, or active configuration files.
    """
    global _LAST_HOUSEKEEPING_AT
    now_mono = time.monotonic()
    with _HOUSEKEEPING_LOCK:
        if not force and _LAST_HOUSEKEEPING_AT > 0 and (now_mono - _LAST_HOUSEKEEPING_AT) < 600.0:
            return {"cleaned": False, "reason": "throttled"}
        _LAST_HOUSEKEEPING_AT = now_mono

    base = Path(gemini_home) if gemini_home else (Path.home() / ".gemini" / "antigravity-cli")
    cutoff = time.time() - max(1.0, float(max_age_hours)) * 3600.0
    logs_removed = 0
    locks_removed = 0
    backups_removed = 0
    bytes_reclaimed = 0

    active_cli = False
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            pname = (proc.info.get("name") or "").lower()
            if pname in {"agy.exe", "agy", "antigravity.exe"}:
                active_cli = True
                break
    except Exception:
        active_cli = True

    log_dir = base / "log"
    if log_dir.is_dir():
        try:
            log_files = []
            for item in log_dir.iterdir():
                if item.is_file() and item.suffix.lower() == ".log":
                    try:
                        st = item.stat()
                        log_files.append((st.st_mtime, st.st_size, item))
                    except OSError:
                        continue
            log_files.sort(key=lambda t: t[0], reverse=True)
            for mtime, size, item in log_files[max(0, int(keep_recent_logs)):]:
                if mtime < cutoff:
                    try:
                        item.unlink()
                        logs_removed += 1
                        bytes_reclaimed += size
                    except OSError:
                        continue
        except OSError:
            pass

    presence_dir = base / "presence"
    if not active_cli and presence_dir.is_dir():
        try:
            for item in presence_dir.iterdir():
                if item.is_file() and item.suffix.lower() == ".lock":
                    try:
                        st = item.stat()
                        if st.st_mtime < cutoff:
                            item.unlink()
                            locks_removed += 1
                            bytes_reclaimed += st.st_size
                    except OSError:
                        continue
        except OSError:
            pass

    if base.is_dir():
        try:
            backups = []
            for item in base.glob("settings.before-quartz-desktop-*.json"):
                if item.is_file():
                    try:
                        st = item.stat()
                        backups.append((st.st_mtime, st.st_size, item))
                    except OSError:
                        continue
            backups.sort(key=lambda t: t[0], reverse=True)
            for mtime, size, item in backups[max(0, int(keep_recent_backups)):]:
                if mtime < cutoff:
                    try:
                        item.unlink()
                        backups_removed += 1
                        bytes_reclaimed += size
                    except OSError:
                        continue
        except OSError:
            pass

    return {
        "cleaned": True,
        "active_session_guard": active_cli,
        "logs_removed": logs_removed,
        "locks_removed": locks_removed,
        "backups_removed": backups_removed,
        "bytes_reclaimed": bytes_reclaimed,
        "reclaimed_mb": round(bytes_reclaimed / 1048576, 2),
    }


class LazyClientProxy:
    """Thread-safe lazy proxy for heavy SDK clients (such as OpenAI).

    Avoids importing openai/httpx/pydantic or loading Windows SSL certificate stores
    at startup until an API method is actually accessed.
    """

    def __init__(self, factory: Callable[[], Any]):
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_instance", None)
        object.__setattr__(self, "_lock", threading.Lock())

    def _resolve(self) -> Any:
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            lock = object.__getattribute__(self, "_lock")
            with lock:
                inst = object.__getattribute__(self, "_instance")
                if inst is None:
                    factory = object.__getattribute__(self, "_factory")
                    inst = factory()
                    object.__setattr__(self, "_instance", inst)
        return inst

    @property
    def is_initialized(self) -> bool:
        return object.__getattribute__(self, "_instance") is not None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._resolve(), name, value)

    def __repr__(self) -> str:
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            return "<LazyClientProxy (uninitialized)>"
        return repr(inst)
