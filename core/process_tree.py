"""Stop only a Popen-owned tree; retain observed child identities until reaped."""
from __future__ import annotations
import logging
import os
import subprocess
import threading
import time


log = logging.getLogger(__name__)
CREATE_SUSPENDED = 0x00000004 if os.name == "nt" else 0
_POPEN_TYPE = subprocess.Popen
_LOCK_CREATION = threading.Lock()
_RLOCK_TYPE = type(threading.RLock())
_JOB_OBJECT_EXTENDED_LIMIT_INFO_CLASS = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


def _assign_pid_to_job(k32, job: int, pid: int) -> bool:
    handle = k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, int(pid))
    if not handle:
        return False
    try:
        return bool(k32.AssignProcessToJobObject(wintypes.HANDLE(job), handle))
    finally:
        k32.CloseHandle(handle)


def _record_job_error(process, message: str, error_sink=None) -> None:
    log.warning("Job Object assignment failed (pid=%s): %s", getattr(process, "pid", None), message)
    try:
        process._quartz_job_error = message
    except Exception:
        pass
    if callable(error_sink):
        try:
            error_sink(message)
        except Exception:
            pass


def resume_process(process: subprocess.Popen | None) -> bool:
    """Resume a process started with CREATE_SUSPENDED."""
    if process is None or os.name != "nt":
        return False
    if getattr(process, "_quartz_resumed", False):
        return True
    proc_handle = getattr(process, "_handle", None)
    if isinstance(process, _POPEN_TYPE):
        try:
            import psutil
            psutil.Process(int(process.pid)).resume()
            process._quartz_resumed = True
            return True
        except Exception:
            pass
    if isinstance(proc_handle, int) and proc_handle > 0:
        try:
            ntdll = ctypes.windll.ntdll
            ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
            ntdll.NtResumeProcess.restype = wintypes.LONG
            if ntdll.NtResumeProcess(wintypes.HANDLE(proc_handle)) == 0:
                process._quartz_resumed = True
                return True
        except Exception:
            pass
    return False


def _resume_or_stop(process: subprocess.Popen, error_sink=None) -> bool:
    if resume_process(process):
        return True
    _record_job_error(
        process,
        "Failed to resume suspended process; terminating process",
        error_sink,
    )
    _stop_owned_root(process, timeout=1)
    close_process_job(process)
    return False


def bind_kill_on_close_job(
    process: subprocess.Popen | None,
    *,
    resume: bool = False,
    error_sink=None,
) -> bool:
    """Attach a Windows Job Object with KILL_ON_JOB_CLOSE before resuming a suspended process."""
    if process is None or os.name != "nt":
        return False
    proc_handle = getattr(process, "_handle", None)
    if not isinstance(proc_handle, int) or proc_handle <= 0:
        if isinstance(process, _POPEN_TYPE):
            _record_job_error(process, "Process handle is missing for Job Object assignment", error_sink)
            if resume:
                _resume_or_stop(process, error_sink)
        return False
    with _state_lock(process):
        assigned = False
        try:
            if getattr(process, "_quartz_job_handle", None):
                sync_process_job(process)
                assigned = True
            else:
                try:
                    k32 = ctypes.windll.kernel32
                    k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
                    k32.CreateJobObjectW.restype = wintypes.HANDLE
                    k32.SetInformationJobObject.argtypes = [
                        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD
                    ]
                    k32.SetInformationJobObject.restype = wintypes.BOOL
                    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
                    k32.AssignProcessToJobObject.restype = wintypes.BOOL
                    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    k32.OpenProcess.restype = wintypes.HANDLE
                    k32.CloseHandle.argtypes = [wintypes.HANDLE]
                    k32.CloseHandle.restype = wintypes.BOOL

                    job = k32.CreateJobObjectW(None, None)
                    if not job:
                        _record_job_error(
                            process,
                            f"CreateJobObjectW failed (winerr={ctypes.GetLastError()})",
                            error_sink,
                        )
                    else:
                        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                        ok_set = k32.SetInformationJobObject(
                            job,
                            _JOB_OBJECT_EXTENDED_LIMIT_INFO_CLASS,
                            ctypes.byref(info),
                            ctypes.sizeof(info),
                        )
                        if not ok_set:
                            err_code = ctypes.GetLastError()
                            k32.CloseHandle(job)
                            _record_job_error(
                                process,
                                f"SetInformationJobObject failed (winerr={err_code})",
                                error_sink,
                            )
                        else:
                            ok_assign = k32.AssignProcessToJobObject(job, wintypes.HANDLE(proc_handle))
                            if not ok_assign:
                                err_code = ctypes.GetLastError()
                                k32.CloseHandle(job)
                                _record_job_error(
                                    process,
                                    f"AssignProcessToJobObject failed (winerr={err_code})",
                                    error_sink,
                                )
                            else:
                                process._quartz_job_handle = int(job)
                                process._quartz_job_assigned_pids = {int(process.pid)}
                                process._quartz_job_error = ""
                                sync_process_job(process)
                                assigned = True
                except Exception as exc:
                    _record_job_error(
                        process,
                        f"Job Object assignment exception: {type(exc).__name__}: {exc}",
                        error_sink,
                    )
        finally:
            if resume and not _resume_or_stop(process, error_sink):
                assigned = False
        return assigned


def sync_process_job(process: subprocess.Popen | None) -> None:
    """Assign any newly-spawned descendant processes into the owned kill-on-close Job Object."""
    if process is None or os.name != "nt":
        return
    job = getattr(process, "_quartz_job_handle", None)
    if not isinstance(job, int) or job <= 0:
        return
    try:
        import psutil
        k32 = ctypes.windll.kernel32
        assigned = getattr(process, "_quartz_job_assigned_pids", None)
        if not isinstance(assigned, set):
            assigned = set()
            process._quartz_job_assigned_pids = assigned
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            if child.pid not in assigned:
                _assign_pid_to_job(k32, job, child.pid)
                assigned.add(child.pid)
    except Exception:
        pass


def wait_process_with_job_sync(process: subprocess.Popen, timeout: float | None = None, interval: float = 0.2) -> int:
    """Wait for process exit while periodically binding new descendants to the kill-on-close job."""
    if os.name != "nt" or not isinstance(getattr(process, "_quartz_job_handle", None), int):
        return process.wait(timeout=timeout)
    deadline = None if timeout is None else (time.monotonic() + float(timeout))
    while True:
        sync_process_job(process)
        if deadline is None:
            step = interval
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(getattr(process, "args", ["process"]), timeout)
            step = min(interval, remaining)
        try:
            return process.wait(timeout=step)
        except subprocess.TimeoutExpired:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(getattr(process, "args", ["process"]), timeout)


def close_process_job(process: subprocess.Popen | None) -> None:
    """Close the owned Windows Job Object handle (terminating any remaining job members)."""
    if process is None or os.name != "nt":
        return
    with _state_lock(process):
        job = getattr(process, "_quartz_job_handle", None)
        if not isinstance(job, int) or job <= 0:
            return
        process._quartz_job_handle = None
        try:
            ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(job))
        except Exception:
            pass


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
            close_process_job(process)
            return getattr(process, '_quartz_tree_discovery_incomplete', False) is not True
        process._quartz_stop_requested = True
        try:
            import psutil
        except ImportError:
            process._quartz_tree_discovery_incomplete = True
            _stop_owned_root(process, timeout)
            close_process_job(process)
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
            clean = (process.poll() is not None and not _pending(process)
                     and getattr(process, '_quartz_tree_discovery_incomplete', False) is not True)
            if clean:
                close_process_job(process)
            return clean
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
            close_process_job(process)
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
