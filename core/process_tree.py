"""Stop only processes descended from an owned CLI Popen process."""

from __future__ import annotations

import subprocess


def stop_process_tree(process: subprocess.Popen, timeout: float = 5) -> bool:
    if process is None:
        return True
    if process.poll() is not None:
        return True
    try:
        import psutil
    except ImportError:
        try:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        except OSError:
            pass
        return process.poll() is not None
    try:
        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
        for child in reversed(descendants):
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        try:
            parent.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        _, alive = psutil.wait_procs([*descendants, parent], timeout=timeout)
        for item in alive:
            try:
                item.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if alive:
            psutil.wait_procs(alive, timeout=2)
    except (psutil.Error, OSError):
        if process.poll() is None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            except OSError:
                pass
    try:
        process.poll()
    except Exception:
        pass
    return process.poll() is not None
