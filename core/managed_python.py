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
- Reuse contract (Fides, open item of the MP reviews): a recorded runtime is reused only after the
  same two gates pass again (PSF signature, capability probe). One that fails is not reused: a fresh
  copy is proven and published into a new folder and the record moves to it. Fides RE1: a runtime
  that failed is marked UNPROVEN (in the record and, should that write fail, in this process) and is
  never selected again until it passes both gates; only a passed proof or a fresh copy clears it.
  The old folder is never
  deleted while SpeS runs (a running job or a project venv may still use it); SpeS's uninstaller
  removes the whole folder. This proves the runtime still works; it is not a guard against changes
  made by the same Windows user.
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


_UNPROVEN: set[str] = set()  # Fides RE1: runtimes this process saw fail, even if the record could not say so


def _entry(base) -> dict:
    from core.atomic_json import load_json
    return load_json(root(base) / "installed.json", {}).get("python") or {}


def published(base=None) -> Path | None:
    """The managed python.exe SpeS recorded after all gates and not since found failing, or None.
    Reading only: never runs anything."""
    entry = _entry(base)
    exe = Path(str(entry.get("executable") or ""))
    if entry.get("version") != VERSION or not exe.is_file():
        return None
    if entry.get("unproven") or str(exe) in _UNPROVEN:
        return None
    return exe


def _set_unproven(base, exe: Path, failed: bool) -> None:
    """Record (or clear) a failed proof for the runtime the record still names; called under _LOCK."""
    from core.atomic_json import atomic_write_json, load_json
    if failed:
        _UNPROVEN.add(str(exe))
    else:
        _UNPROVEN.discard(str(exe))
    try:
        manifest = load_json(base / "installed.json", {})
        entry = manifest.get("python") or {}
        if str(entry.get("executable") or "") != str(exe):
            return  # the record moved on: never touch a newer entry
        if failed:
            entry["unproven"] = True
        else:
            entry.pop("unproven", None)
        manifest["python"] = entry
        atomic_write_json(base / "installed.json", manifest)
    except OSError:
        pass  # the in-process mark still keeps a failed runtime from being selected


def interpreter(base=None) -> str | None:
    """SpeS's own Python first; else the user's Python on PATH (never changed by SpeS); else None."""
    managed = published(base)
    if managed is not None:
        return str(managed)
    return _user_python(base)


def _same(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return False


def _own_runtime_folder(folder: str, base=None) -> bool:
    """True for a PATH entry inside SpeS's runtime folder or one of a runtime this process saw fail."""
    if not folder.strip():
        return False
    try:
        entry = os.path.normcase(str(Path(folder).resolve()))
        packages = os.path.normcase(str((root(base) / "packages").resolve()))
    except OSError:
        return False
    if entry == packages or entry.startswith(packages + os.sep):
        return True
    for bad in list(_UNPROVEN):
        try:
            home = os.path.normcase(str(Path(bad).resolve().parent))
        except OSError:
            continue
        if entry == home or entry.startswith(home + os.sep):
            return True
    return False


def foreign_path(path: str, base=None) -> str:
    """Fides REF-ENV: an inherited PATH without any of SpeS's own runtime folders, so an agent's
    environment never reaches a runtime SpeS did not select. The caller puts the published runtime
    (if any) first itself. Reading only; the user's PATH setting is never changed."""
    return os.pathsep.join(part for part in (path or "").split(os.pathsep)
                           if not _own_runtime_folder(part, base))


def _user_python(base=None) -> str | None:
    """Fides RE1-F: the first python on PATH that is NOT one of SpeS's own runtimes (an unpublished,
    unproven or older copy under SpeS's folder is never "the user's Python"). Reading only."""
    packages = root(base) / "packages"
    failed = [Path(p) for p in _UNPROVEN]
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder.strip():
            continue
        found = shutil.which("python", path=folder)
        if not found:
            continue
        exe = Path(found).resolve()
        try:
            inside = os.path.normcase(str(exe)).startswith(os.path.normcase(str(packages.resolve())) + os.sep)
        except OSError:
            inside = False
        if inside or any(_same(exe, bad) for bad in failed):
            continue
        return str(exe)
    return None


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
    # Fides VR1: a venv SpeS is (or was) creating carries CREATING until it is proven; a venv
    # with that mark, or one SpeS left incomplete, is never used.
    return exe if ((folder / "pyvenv.cfg").is_file() and exe.is_file()
                   and not (folder / CREATING).exists() and not (folder / INCOMPLETE).exists()) else None


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
CREATING = "spes-creating.txt"


def _leave_failed_venv(folder: Path) -> None:
    """Fides V2-R (27 Nov): nothing in a failed environment is deleted by name. An empty reserved
    folder is removed; anything else stays, marked incomplete, and is never used as a venv."""
    try:
        if [entry.name for entry in folder.iterdir()] == [CREATING]:
            (folder / CREATING).unlink()  # only our own mark was there: give the folder back
        folder.rmdir()  # succeeds only when the folder is empty
        return
    except OSError:
        pass
    try:  # best effort: CREATING already keeps this folder from ever being used
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
        try:
            # Fides VR1: the mark goes first; without it nothing is run.
            (folder / CREATING).write_text("SpeS bu sanal ortamı kuruyor.\n", encoding="utf-8")
        except OSError:
            try:
                folder.rmdir()
            except OSError:
                pass
            return None
        from core.cli_installer import owned_run
        run = run or owned_run
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH"}}
        try:
            if callable(cancelled) and cancelled():
                raise RuntimeError("durduruldu")
            result = run([str(managed), "-I", "-m", "venv", str(folder)], capture_output=True, text=True,
                         timeout=180, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            ready = (folder / "pyvenv.cfg").is_file() and (folder / "Scripts" / "python.exe").is_file()
            if result.returncode or not ready or (callable(cancelled) and cancelled()):
                raise RuntimeError("venv oluşturulamadı")
            # Proven: the mark becomes "created" in one step; if that fails the venv stays unused.
            os.replace(folder / CREATING, folder / "spes-created.txt")
            _ignore_in_git(root_dir)
            return project_venv(project)
        except Exception:
            _leave_failed_venv(folder)
            return None


def task_environment(base=None, project=None) -> dict:
    """The environment SpeS's own Python commands run in (Fides MP1): the managed runtime and its
    Scripts first on PATH, no PYTHONHOME/PYTHONPATH from the host; nothing system-wide changes."""
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH"}}
    env["PATH"] = foreign_path(env.get("PATH", ""), base)
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


def prove(exe: Path, run, verify) -> str:
    """The two gates every runtime passes before it is published or reused: python.exe signed by the
    Python Software Foundation, and the isolated capability probe. Returns the probe's output."""
    verify(exe, "Python Software Foundation")
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH"}}
    probe = run([str(exe), "-I", "-c", PROBE], capture_output=True, text=True, timeout=60, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = (probe.stdout or "").strip()
    if probe.returncode or not out.startswith(VERSION + "|"):
        raise RuntimeError("SpeS'in Python'u denetimden geçmedi (tkinter/venv/pip)")
    return out


def _install(run, download, verify, base) -> dict:
    from core.atomic_json import atomic_write_json, load_json
    from core.cli_installer import owned_run
    from core import install_security
    run = run or owned_run
    download = download or install_security.download
    verify = verify or install_security.verify_publisher
    entry = _entry(base)
    recorded = Path(str(entry.get("executable") or ""))
    if entry.get("version") == VERSION and recorded.is_file():
        # Also a runtime marked unproven gets its chance: a passed proof is the only way back.
        try:
            prove(recorded, run, verify)
        except Exception:
            _set_unproven(base, recorded, True)  # not selected again; the folder stays in place
        else:
            if entry.get("unproven") or str(recorded) in _UNPROVEN:
                _set_unproven(base, recorded, False)
            return {"installed": True, "executable": str(recorded), "version": VERSION, "reused": True}
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
        out = prove(exe, run, verify)
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
