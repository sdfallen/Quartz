"""Stop only a Popen-owned tree; retain observed child identities until reaped."""
from __future__ import annotations
import subprocess
import threading
import time


_LOCK_CREATION = threading.Lock()
_RLOCK_TYPE = type(threading.RLock())


class OwnedCleanupUnconfirmed(RuntimeError):
    """The owned root exited, but discovery did not establish tree coverage."""
    def __init__(self, root_returncode):
        super().__init__('tree_discovery_incomplete')
        self.root_returncode = root_returncode


def _state_lock(process):
    with _LOCK_CREATION:
        lock = getattr(process, '_quartz_cleanup_lock', None)
        if not isinstance(lock, _RLOCK_TYPE):
            lock = process._quartz_cleanup_lock = threading.RLock()
        return lock


def _pending(process):
    value = getattr(process, '_quartz_pending_children', [])
    return value if isinstance(value, list) else []


def owned_cleanup_pending(process, *, include_root=True):
    if process is None:return False
    with _state_lock(process):
        return (include_root and process.poll() is None or bool(_pending(process))
                or getattr(process, '_quartz_tree_discovery_incomplete', False) is True)


def _stop_owned_root(process, timeout):
    """Use the original Popen handle, even when PID-based discovery is denied."""
    try:
        if process.poll() is not None:return
        try:process.terminate()
        except OSError:pass
        try:process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass  # The caller keeps the cleanup unconfirmed.


def _stop_observed(process, members, psutil, timeout):
    # Save identities BEFORE termination/wait: verification itself may fail.
    process._quartz_pending_children = list(members)
    for child in reversed(members):
        try:child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):pass
    _, alive = psutil.wait_procs(members, timeout=timeout)
    process._quartz_pending_children = list(alive)
    for child in alive:
        try:child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):pass
    if alive:
        _, alive = psutil.wait_procs(alive, timeout=2)
    process._quartz_pending_children = list(alive)


def stop_process_tree(process: subprocess.Popen, timeout: float = 5) -> bool:
    if process is None:
        return True
    with _state_lock(process):
        pending = _pending(process)
        if process.poll() is not None and not pending:
            return getattr(process, '_quartz_tree_discovery_incomplete', False) is not True
        process._quartz_stop_requested = True
        try:
            import psutil
        except ImportError:
            process._quartz_tree_discovery_incomplete = True
            _stop_owned_root(process, timeout)
            return False
        try:
            if process.poll() is None:
                process._quartz_tree_discovery_incomplete = True
                parent = psutil.Process(process.pid)
                members = list(dict.fromkeys([parent, *pending]))
                process._quartz_pending_children = members
                for child in parent.children(recursive=True):
                    if child not in members:members.append(child)
                process._quartz_tree_discovery_incomplete = False
            else:
                members = pending
            _stop_observed(process, members, psutil, timeout)
            if process.poll() is None:
                _stop_owned_root(process, timeout)
            return (process.poll() is not None and not _pending(process)
                    and getattr(process, '_quartz_tree_discovery_incomplete', False) is not True)
        except (psutil.Error, OSError):
            _stop_owned_root(process, timeout)
            # Prior observed children remain actionable without inventing PIDs.
            known = _pending(process)
            if known:
                try:_stop_observed(process, known, psutil, timeout)
                except (psutil.Error, OSError):pass
            return False


def wait_for_owned_cleanup(process, report_pending):
    """Continue the existing watcher; never release ownership of a live process."""
    while True:
        with _state_lock(process):
            pending = list(_pending(process))
            code = process.poll()
            incomplete = getattr(process, '_quartz_tree_discovery_incomplete', False) is True
        if code is not None and not pending:
            if incomplete:
                report_pending()
                raise OwnedCleanupUnconfirmed(code)
            return code
        report_pending()
        if code is None:
            if getattr(process, '_quartz_stop_requested', False) is True:
                stop_process_tree(process, timeout=1)
            try:
                process.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError):
                time.sleep(.1)
        else:
            stop_process_tree(process, timeout=1)
            time.sleep(.1)
