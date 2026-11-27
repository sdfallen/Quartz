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


def root(base=None):
    """Fides MP2: an installer's own root is kept; the default is SpeS's private folder."""
    if base is not None:
        return Path(base)
    from core.cli_installer import managed_root
    return managed_root()


def published(base=None) -> Path | None:
    """The managed python.exe SpeS recorded after all gates, or None."""
    from core.atomic_json import load_json
    entry = load_json(root(base) / "installed.json", {}).get("python") or {}
    exe = Path(str(entry.get("executable") or ""))
    return exe if entry.get("version") == VERSION and exe.is_file() else None


def interpreter(base=None) -> str | None:
    """SpeS's own Python first; else the user's Python on PATH (never changed by SpeS); else None."""
    managed = published(base)
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


VENV = ".venv"


def project_venv(project) -> Path | None:
    """A project's own virtual environment (Fides P2, first choice): <project>/.venv with its
    pyvenv.cfg and python.exe, whoever made it. None when there is none."""
    folder = Path(str(project or "")) / VENV
    exe = folder / "Scripts" / "python.exe"
    return exe if ((folder / "pyvenv.cfg").is_file() and exe.is_file()
                   and not (folder / INCOMPLETE).exists()) else None


def project_interpreter(project, base=None) -> str | None:
    """The one interpreter for a project's checks, launches and agents: its own venv first, then
    SpeS's runtime, then the user's Python."""
    venv = project_venv(project)
    return str(venv) if venv is not None else interpreter(base)


def _ignore_in_git(project: Path) -> None:
    """The venv is the computer's, not the project's: it never enters the job's commits."""
    ignore = project / ".gitignore"
    try:
        lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
        if not any(line.strip().rstrip("/") == VENV for line in lines):
            prefix = "" if not lines or ignore.read_text(encoding="utf-8").endswith("\n") else "\n"
            with ignore.open("a", encoding="utf-8") as stream:
                stream.write(prefix + VENV + "/\n")
    except OSError:
        pass


_VENV_LOCKS: dict = {}
_VENV_LOCKS_GUARD = __import__("threading").Lock()
INCOMPLETE = "spes-incomplete.txt"


def _leave_failed_venv(folder: Path) -> None:
    """Fides V2-R (27 Nov): nothing in a failed environment is deleted by name. An empty reserved
    folder is removed; anything else stays, marked incomplete, and is never used as a venv."""
    try:
        folder.rmdir()  # succeeds only when the folder is empty
        return
    except OSError:
        pass
    try:
        (folder / INCOMPLETE).write_text("SpeS bu sanal ortamı kuramadı; içindekiler silinmedi. "
                                         "Klasörü inceleyip kendin silebilirsin.\n", encoding="utf-8")
    except OSError:
        pass


def ensure_project_venv(project, run=None, base=None, cancelled=None) -> Path | None:
    """A new venv for a project from SpeS's own runtime, so packages a job installs stay in the
    project and never in SpeS's shared runtime (Fides: protect the managed base). An existing
    .venv is never touched; without SpeS's runtime nothing is made (the user's Python is not ours
    to build on). Owned process; a failure leaves no half venv behind."""
    existing = project_venv(project)
    if existing is not None:
        return existing
    managed = published(base)
    root_dir = Path(str(project or ""))
    if managed is None or not root_dir.is_dir():
        return None
    key = os.path.normcase(str(root_dir.resolve()))
    with _VENV_LOCKS_GUARD:
        lock = _VENV_LOCKS.setdefault(key, __import__("threading").Lock())
    with lock:  # one SpeS creator per project at a time
        existing = project_venv(project)
        if existing is not None:
            return existing
        folder = root_dir / VENV
        try:
            folder.mkdir()  # Fides V2: an exclusive reservation; anything already there is not ours
        except OSError:
            return None
        from core.cli_installer import owned_run
        run = run or owned_run
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH"}}
        try:
            if callable(cancelled) and cancelled():
                raise RuntimeError("durduruldu")
            result = run([str(managed), "-I", "-m", "venv", str(folder)], capture_output=True, text=True,
                         timeout=180, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            made = project_venv(project)
            if result.returncode or made is None or (callable(cancelled) and cancelled()):
                raise RuntimeError("venv oluşturulamadı")
            (folder / "spes-created.txt").write_text("SpeS bu sanal ortamı projenin paketleri için oluşturdu.\n",
                                                     encoding="utf-8")
            _ignore_in_git(root_dir)
            return made
        except Exception:
            _leave_failed_venv(folder)
            return None


def task_environment(base=None, project=None) -> dict:
    """The environment SpeS's own Python commands run in (Fides MP1): the managed runtime and its
    Scripts first on PATH, no PYTHONHOME/PYTHONPATH from the host; nothing system-wide changes."""
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH"}}
    first = []
    venv = project_venv(project) if project is not None else None
    if venv is not None:
        env["VIRTUAL_ENV"] = str(venv.parent.parent)
        first.append(str(venv.parent))
    managed = published(base)
    if managed is not None:
        first += [str(managed.parent), str(managed.parent / "Scripts")]
    if first:
        env["PATH"] = os.pathsep.join([*first, env.get("PATH", "")])
    return env


def install(run=None, download=None, verify=None, base=None) -> dict:
    """Download, check, extract, prove and publish the pinned runtime; reuse it when present.

    Fides MP3: the whole install, from the reuse check to the manifest commit, holds the installer
    lock every provider's manifest write holds, so no record is lost and no second copy is made."""
    from core.cli_installer import _LOCK
    with _LOCK:
        return _install(run, download, verify, root(base))


def _install(run, download, verify, base) -> dict:
    from core.atomic_json import atomic_write_json, load_json
    from core.cli_installer import owned_run
    from core import install_security
    run = run or owned_run
    download = download or install_security.download
    verify = verify or install_security.verify_publisher
    existing = published(base)
    if existing is not None:
        return {"installed": True, "executable": str(existing), "version": VERSION, "reused": True}
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
        try:
            manifest = load_json(base / "installed.json", {})
            manifest["python"] = entry
            atomic_write_json(base / "installed.json", manifest)
        except BaseException:
            # Fides MP4: this call's own folder goes with a failed commit; nothing else is touched.
            shutil.rmtree(final, ignore_errors=True)
            raise
        return {"installed": True, **entry, "reused": False}
    finally:
        shutil.rmtree(stage, ignore_errors=True)
