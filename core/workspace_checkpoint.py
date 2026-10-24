"""Verified project checkpoints before agent writes; never a whole-machine backup."""

from __future__ import annotations

import subprocess
import time
import uuid
import os
import fnmatch
import hashlib
import json
import zipfile
from pathlib import Path


def create_checkpoint(workspace: str | Path, *, backup_root=None,
                      max_files=20_000, max_bytes=512 * 1024 * 1024) -> dict:
    """Preserve Git tracked/nonignored files (including untracked) outside the project.

    Non-Git projects use a bounded file archive excluding credentials/runtime/cache
    outputs. Ignored files, external install directories and system state are NOT
    covered. Failure never returns a usable checkpoint.
    """
    ref = None
    partial = None
    try:
        root = Path(workspace).resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        destination = Path(backup_root or (Path.home() / ".quartz" / "checkpoints")).resolve()
        if destination == root or root in destination.parents:
            raise ValueError("Checkpoint destination must be outside the project")
    except (OSError, ValueError) as exc:
        return {"status": "error", "ref": None, "warning": str(exc)}

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    try:
        found = git("rev-parse", "--show-toplevel")
        is_git = found.returncode == 0 and Path(found.stdout.strip()).resolve() == root
        commit = None
        paths = []
        if is_git:
            snapshot = git("stash", "create", "Quartz agent pre-write checkpoint")
            if snapshot.returncode != 0:
                raise RuntimeError(snapshot.stderr.strip() or "Git checkpoint oluşturulamadı.")
            commit = snapshot.stdout.strip()
            if not commit:
                head = git("rev-parse", "HEAD")
                if head.returncode != 0:
                    raise RuntimeError("Git HEAD bulunamadı.")
                commit = head.stdout.strip()
            ref = f"refs/quartz-checkpoints/agent-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            saved = git("update-ref", ref, commit)
            if saved.returncode != 0:
                raise RuntimeError(saved.stderr.strip() or "Git checkpoint kaydedilemedi.")
            listing = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
            if listing.returncode != 0:
                raise RuntimeError("Checkpoint file inventory failed")
            paths = sorted(set(p for p in listing.stdout.split("\0") if p))
        else:
            skipped = {".git", ".squad", ".quartz", "node_modules", ".venv", "venv",
                       "__pycache__", ".pytest_cache", "dist", "build", "vision_captures"}
            private = {"mobile_access.json", "chat_history.json", "quartz_conversations.json",
                       "quartz_memory.json", "jarvis_memory.json", "quartz_operation.json"}
            for folder, dirs, names in os.walk(root):
                dirs[:] = sorted(name for name in dirs if name not in skipped)
                if any((Path(folder) / name).is_symlink() for name in dirs):
                    raise ValueError("Symbolic-link directories require a dedicated backup policy")
                for name in sorted(names):
                    if name in private or name == ".env" or name.startswith(".env.") or any(
                            fnmatch.fnmatch(name, pattern) for pattern in ("*.log", "*.pyc", "*.pyo")):
                        continue
                    paths.append(str((Path(folder) / name).relative_to(root)))
                    if len(paths) > max_files:
                        raise ValueError("Checkpoint file limit exceeded")
        if len(paths) > max_files:
            raise ValueError("Checkpoint file limit exceeded")
        destination.mkdir(parents=True, exist_ok=True)
        archive = destination / f"agent-{int(time.time())}-{uuid.uuid4().hex}.zip"
        partial = archive.with_suffix(".partial")
        manifest = {"version": 1, "workspace": str(root), "git_ref": ref, "files": {}}
        total = 0
        with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED) as output:
            for relative in paths:
                path = root / relative
                if path.is_symlink() or root not in path.resolve(strict=False).parents:
                    raise ValueError("Unsafe checkpoint path")
                if not path.exists():
                    manifest["files"][relative] = {"exists": False}
                    continue
                before = path.stat()
                total += before.st_size
                if total > max_bytes:
                    raise ValueError("Checkpoint byte limit exceeded")
                digest = hashlib.sha256()
                count = 0
                with path.open("rb") as source, output.open("files/" + Path(relative).as_posix(), "w") as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        count += len(chunk)
                        if count > before.st_size:
                            raise RuntimeError("File changed while checkpointing")
                        digest.update(chunk)
                        target.write(chunk)
                after = path.stat()
                if count != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError("File changed while checkpointing")
                manifest["files"][relative] = {"exists": True, "bytes": count, "sha256": digest.hexdigest()}
            output.writestr("checkpoint-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        with zipfile.ZipFile(partial) as verified:
            if verified.testzip() is not None:
                raise RuntimeError("Checkpoint archive CRC failed")
        partial.replace(archive)
        return {"status": "git" if is_git else "snapshot", "complete": True,
                "ref": ref or str(archive), "commit": commit, "archive": str(archive),
                "file_count": len(paths), "bytes": total,
                "warning": "Yalnız proje dosyaları; Git-ignored/dış dosyalar ve sistem ayarları kapsam dışı."}
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        if partial is not None:
            try:
                if partial.exists():
                    partial.unlink(missing_ok=True)
            except Exception:
                pass
        return {"status": "error", "complete": False, "ref": ref, "warning": str(exc)}


def snapshot_workspace_files(workspace: str | Path, max_files: int = 20_000) -> dict:
    """Record file metadata so CLI writes remain visible even when tools use shell commands."""
    try:
        root = Path(workspace).resolve(strict=True)
    except OSError as exc:
        return {"files": None, "warning": str(exc)}
    files = {}
    skipped = {".git", ".squad", "node_modules", ".venv", "venv", "__pycache__"}
    try:
        for folder, dirs, names in os.walk(root):
            dirs[:] = [name for name in dirs if name not in skipped]
            for name in names:
                path = Path(folder) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if not path.is_file():
                    continue
                files[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
                if len(files) > max_files:
                    return {"files": None, "warning": "Dosya sayısı sınırı aşıldı; değişiklik listesi eksik olabilir."}
    except OSError as exc:
        return {"files": None, "warning": str(exc)}
    return {"files": files, "warning": ""}


def changed_workspace_files(workspace: str | Path, before: dict, after: dict) -> tuple[list[str], str]:
    if before["files"] is None or after["files"] is None:
        return [], before["warning"] or after["warning"]
    root = Path(workspace).resolve(strict=False)
    previous, current = before["files"], after["files"]
    changed = sorted(key for key in previous.keys() | current.keys()
                     if previous.get(key) != current.get(key))
    warning = "Değişiklik listesi ilk 200 dosyayla sınırlandı." if len(changed) > 200 else ""
    return [str(root / key) for key in changed[:200]], warning
