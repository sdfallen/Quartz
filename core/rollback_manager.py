"""Backup/restore primitives shared by plugin upgrade workflows."""

import os
import stat
import shutil
from pathlib import Path


def rmtree_safe(path: str | Path) -> None:
    """Remove a directory tree on Windows handling read-only files cleanly."""
    def _handle_remove_readonly(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    try:
        shutil.rmtree(path, onexc=_handle_remove_readonly)
    except TypeError:
        shutil.rmtree(path, onerror=_handle_remove_readonly)


class RollbackManager:
    IGNORED = staticmethod(
        shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "*.log"))

    def backup(self, source, destination) -> Path:
        source, destination = Path(source), Path(destination)
        if not source.is_dir():
            raise FileNotFoundError(source)
        if destination.exists():
            rmtree_safe(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, ignore=self.IGNORED)
        return destination

    def restore(self, backup, destination) -> Path:
        backup, destination = Path(backup), Path(destination)
        if not backup.is_dir():
            raise FileNotFoundError(backup)
        temporary = destination.with_name(destination.name + ".restoring")
        if temporary.exists():
            rmtree_safe(temporary)
        shutil.copytree(backup, temporary, ignore=self.IGNORED)
        if destination.exists():
            rmtree_safe(destination)
        temporary.replace(destination)
        return destination
