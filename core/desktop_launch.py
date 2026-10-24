"""Explicit GUI-selected executable launches. No shell, arguments or descendants.

An approval binds file identity and bytes. Only a new window of the exact child
PID/start/exe can join the task; singleton/launcher/child-process apps fail closed.
This is not a claim to sandbox a user-selected executable.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import time
import uuid

from core.desktop_native import NativeDesktopBackend, DENIED_EXES

INTERPRETERS = {"python.exe", "pythonw.exe", "node.exe", "wscript.exe", "cscript.exe",
                "mshta.exe", "rundll32.exe", "regsvr32.exe", "msiexec.exe", "bash.exe",
                "wsl.exe", "java.exe", "javaw.exe", "dotnet.exe", "explorer.exe"}


def describe_launch(path):
    raw = Path(path)
    if not raw.is_absolute() or str(raw).startswith(("\\\\", "//")) or raw.is_symlink():
        raise PermissionError("Select a local, non-linked absolute EXE")
    resolved = raw.resolve(strict=True)
    if (resolved.suffix.lower() != ".exe" or not resolved.is_file() or
            resolved.name.lower() in DENIED_EXES | INTERPRETERS or
            any(part.lower() in {"warbandisland", "ai_island_test"} for part in resolved.parts)):
        raise PermissionError("Executable is outside the bounded launch profile")
    NativeDesktopBackend.validate_target({"exe": str(resolved), "title": ""})
    stat = resolved.stat()
    if stat.st_nlink != 1: raise PermissionError("Linked executable requires separate review")
    with resolved.open("rb") as stream:
        if stream.read(2) != b"MZ": raise PermissionError("Not a Windows executable")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"id": uuid.uuid4().hex, "exe": str(resolved), "sha256": digest,
            "identity": [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]}


def validate_launch(approval):
    if not isinstance(approval, dict) or set(approval) != {"id", "exe", "sha256", "identity"}:
        raise PermissionError("Invalid launch approval")
    current = describe_launch(approval["exe"])
    if any(current[k] != approval[k] for k in ("exe", "sha256", "identity")):
        raise PermissionError("Executable changed; new approval required")
    return dict(approval)


def launch_approved(approval, backend):
    validate_launch(approval)
    backend.validate_input_session()
    import psutil
    child = subprocess.Popen([approval["exe"]], shell=False, cwd=str(Path(approval["exe"]).parent),
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    proc = psutil.Process(child.pid)
    started = proc.create_time()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if child.poll() is not None: break
        candidates = [w for w in backend.windows() if w["pid"] == child.pid and
                      w["started"] == started and os.path.normcase(w["exe"]) == os.path.normcase(approval["exe"])]
        if len(candidates) == 1:
            backend.validate_target(candidates[0])
            return candidates[0]
        time.sleep(.1)
    raise RuntimeError("No unique window from the exact approved child. No other window was adopted; app was not killed.")
