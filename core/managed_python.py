"""SpeS brings its own Python (27 Nov 2026), so a computer without Python can still run what SpeS's
jobs build, look at its window and try it (launch_check, launch_interact).

Fides's design review 27 Nov (ŞARTLI, option E): python.org's full Windows runtime ZIP — the one the
official offline index lists — extracted into SpeS's own folder. Unlike the installer it leaves no
registration behind (removing the folder removes it); unlike the minimal embeddable ZIP and the NuGet
package it carries tkinter, Tcl/Tk, pip and venv.

- One pinned release: URL and SHA-256 fixed here (never "latest"), checked after the download.
- Safe extraction: every member must stay inside the staging folder; entry count, size and ratio are
  bounded; links are refused.
- Gates before publishing: python.exe signed by the Python Software Foundation; a capability probe
  (version, tkinter with Tcl/Tk, venv, ensurepip) run owned (core.cli_installer.owned_run).
- Atomic publish: the staging folder is renamed into place and only then recorded in installed.json;
  a half-finished setup is never "ready".
- Resolution (P2): the managed runtime first, then the user's own Python only as a fallback; the user's
  Python is never changed, upgraded or removed.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

VERSION = "3.13.17"
URL = "https://www.python.org/ftp/python/3.13.17/python-3.13.17-amd64.zip"
SHA256 = "b26ca4b4ee51e157836049934d2b8eabd55939be296f3130254251b6df96ec2f"
ALLOWED = [("www.python.org", "/ftp/python/")]
DOWNLOAD_LIMIT = 80 * 1024 * 1024
MAX_ENTRIES = 10000
MAX_UNPACKED = 400 * 1024 * 1024
MAX_RATIO = 200
PROBE = ("import sys, tkinter, venv, ensurepip; "
         "t = tkinter.Tcl(); "
         "print(sys.version.split()[0], t.eval('info patchlevel'), sep='|')")


def root():
    from core.cli_installer import managed_root
    return managed_root()


def published() -> Path | None:
    """The managed python.exe SpeS recorded after all gates, or None."""
    from core.atomic_json import load_json
    entry = load_json(root() / "installed.json", {}).get("python") or {}
    exe = Path(str(entry.get("executable") or ""))
    return exe if entry.get("version") == VERSION and exe.is_file() else None


def interpreter() -> str | None:
    """SpeS's own Python first; else the user's Python on PATH (never changed by SpeS); else None."""
    managed = published()
    if managed is not None:
        return str(managed)
    found = shutil.which("python")
    return str(Path(found).resolve()) if found else None


def safe_extract(archive: Path, target: Path) -> None:
    """Every member inside ``target``; bounded count, size and compression ratio; no links."""
    target = target.resolve()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_ENTRIES:
            raise ValueError("Python arşivinde beklenenden çok dosya var")
        total = 0
        for member in members:
            total += member.file_size
            if total > MAX_UNPACKED:
                raise ValueError("Python arşivi açılınca beklenenden büyük")
            if member.compress_size and member.file_size / member.compress_size > MAX_RATIO:
                raise ValueError("Python arşivinde olağandışı sıkıştırma")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Python arşivinde bağlantı (link) var")
            destination = (target / member.filename).resolve()
            if destination != target and target not in destination.parents:
                raise ValueError("Python arşivinde klasör dışına çıkan dosya var")
        bundle.extractall(target)


def install(run=None, download=None, verify=None) -> dict:
    """Download, check, extract, prove and publish the pinned runtime; reuse it when present."""
    from core.atomic_json import atomic_write_json, load_json
    from core.cli_installer import owned_run
    from core import install_security
    run = run or owned_run
    download = download or install_security.download
    verify = verify or install_security.verify_publisher
    existing = published()
    if existing is not None:
        return {"installed": True, "executable": str(existing), "version": VERSION, "reused": True}
    base = root()
    base.mkdir(parents=True, exist_ok=True)
    stage = base / ("python-stage-" + uuid.uuid4().hex[:8])
    stage.mkdir()
    try:
        archive = download(URL, stage / "python.zip", allowed=ALLOWED, limit=DOWNLOAD_LIMIT)
        with Path(archive).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != SHA256:
                raise ValueError("Python arşivinin SHA-256 özeti sabitlenen değerle uyuşmuyor")
        unpacked = stage / "python"
        safe_extract(Path(archive), unpacked)
        exe = unpacked / "python.exe"
        if not exe.is_file():
            raise ValueError("Python arşivinde python.exe yok")
        verify(exe, "Python Software Foundation")
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH"}}
        probe = run([str(exe), "-I", "-c", PROBE], capture_output=True, text=True, timeout=60, env=env,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = (probe.stdout or "").strip()
        if probe.returncode or not out.startswith(VERSION + "|"):
            raise RuntimeError("SpeS'in Python'u denetimden geçmedi (tkinter/venv/pip)")
        final = base / "packages" / ("python-" + VERSION + "-" + uuid.uuid4().hex[:8])
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(unpacked, final)  # atomic publish of the folder
        entry = {"executable": str(final / "python.exe"), "version": VERSION, "sha256": SHA256,
                 "source": URL, "tcl": out.split("|", 1)[1]}
        manifest = load_json(base / "installed.json", {})
        manifest["python"] = entry
        atomic_write_json(base / "installed.json", manifest)
        return {"installed": True, **entry, "reused": False}
    finally:
        shutil.rmtree(stage, ignore_errors=True)
