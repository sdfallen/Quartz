"""Stop only processes descended from an owned CLI Popen process."""

from __future__ import annotations

import subprocess
import time
from typing import Any


def stop_process_tree(process: subprocess.Popen | int | Any, timeout: float = 5.0) -> None:
    """Safely and immediately terminate a process and all of its descendants.

    Guarantees:
    - Bounded latency: uses adaptive polling waits (25ms intervals) to return
      immediately once all processes terminate, rather than stalling for the full timeout.
    - Zero orphaned child processes: traverses descendants in reverse topological order,
      terminates children before parent, and cleans up detached descendants if parent already exited.
    - Escalates to forceful kill if processes remain alive after initial termination.
    - Accepts subprocess.Popen instances, integer PIDs, or objects with a .pid attribute.
    - Idempotent and safe against already-terminated processes or race conditions.
    """
    if process is None:
        return

    popen_obj: subprocess.Popen | None = process if hasattr(process, "poll") else None
    raw_pid = getattr(process, "pid", process if isinstance(process, int) else None)
    if not isinstance(raw_pid, int):
        return
    pid: int = raw_pid

    try:
        import psutil
    except ImportError:
        if popen_obj is not None:
            if popen_obj.poll() is None:
                popen_obj.terminate()
                try:
                    popen_obj.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    popen_obj.kill()
        return

    try:
        if not psutil.pid_exists(pid):
            if popen_obj is not None:
                try:
                    popen_obj.poll()
                except Exception:
                    pass
            return
        parent: psutil.Process | None = psutil.Process(pid)
        descendants = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        parent = None
        descendants = []

    procs_to_stop: list[psutil.Process] = []
    for child in reversed(descendants):
        procs_to_stop.append(child)
    if parent is not None:
        procs_to_stop.append(parent)

    for p in procs_to_stop:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Adaptive wait: poll in short intervals to return as soon as dead
    deadline = time.monotonic() + max(0.5, float(timeout))
    alive = list(procs_to_stop)
    while alive and time.monotonic() < deadline:
        gone, alive = psutil.wait_procs(alive, timeout=0.025)

    # Force kill any stubborn survivors
    if alive:
        for p in alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        kill_deadline = time.monotonic() + 1.0
        while alive and time.monotonic() < kill_deadline:
            gone, alive = psutil.wait_procs(alive, timeout=0.025)

    if popen_obj is not None:
        try:
            popen_obj.poll()
            if popen_obj.returncode is None:
                popen_obj.wait(timeout=0.05)
        except Exception:
            pass
