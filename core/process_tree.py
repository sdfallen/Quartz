"""Stop only processes descended from an owned CLI Popen process."""

from __future__ import annotations

import subprocess


def stop_process_tree(process: subprocess.Popen, timeout: float = 5) -> None:
    if process.poll() is not None:
        return
    try:
        import psutil
    except ImportError:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
        return
    try:
        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
        for child in reversed(descendants):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
        _, alive = psutil.wait_procs([*descendants, parent], timeout=timeout)
        for item in alive:
            try:
                item.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=2)
    except (psutil.Error, OSError):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
