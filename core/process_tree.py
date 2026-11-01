"""Stop only a Popen-owned tree; retain observed child identities until reaped."""
from __future__ import annotations
import subprocess
import time


def stop_process_tree(process: subprocess.Popen, timeout: float = 5) -> bool:
    if process is None:
        return True
    pending = getattr(process, "_quartz_pending_children", [])
    pending = pending if isinstance(pending, list) else []
    if process.poll() is not None and not pending:
        return True
    try:
        import psutil
    except ImportError:
        if pending:
            return False  # Cannot verify previously observed children.
        try:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return process.poll() is not None
    try:
        if process.poll() is None:
            parent = psutil.Process(process.pid)
            members = list(dict.fromkeys([parent, *pending, *parent.children(recursive=True)]))
        else:
            members = pending
        # psutil Process objects retain their creation identity; do not rebuild
        # orphaned children from guessed/reused integer PIDs.
        for child in reversed(members):
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        _, alive = psutil.wait_procs(members, timeout=timeout)
        for child in alive:
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if alive:
            _, alive = psutil.wait_procs(alive, timeout=2)
        process._quartz_pending_children = list(alive)
        return process.poll() is not None and not alive
    except (psutil.Error, OSError):
        # Discovery/verification failure is uncertainty, not confirmed cleanup.
        return False


def wait_for_owned_cleanup(process, report_pending):
    """Continue the existing watcher; never release ownership of a live process."""
    while True:
        pending = getattr(process, "_quartz_pending_children", [])
        pending = pending if isinstance(pending, list) else []
        code = process.poll()
        if code is not None and not pending:
            return code
        report_pending()
        if code is None:
            try:
                process.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError):
                time.sleep(.1)
        else:
            stop_process_tree(process, timeout=1)
            time.sleep(.1)
