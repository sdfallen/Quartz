"""Crash-safe helpers for the small JSON stores used by Quartz."""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

_FILE_LOCK = threading.RLock()


def load_json(path, default: Any) -> Any:
    target = Path(path)
    with _FILE_LOCK:
        try:
            with target.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default


def atomic_write_json(path, value: Any, *, indent: int = 2) -> None:
    """Write JSON beside its destination, then atomically replace it."""
    target = Path(path)
    with _FILE_LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(value, indent=indent, ensure_ascii=False, default=str)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            replaced = False
            for attempt in range(10):
                try:
                    os.replace(temporary, target)
                    replaced = True
                    break
                except (PermissionError, OSError):
                    time.sleep(0.03 * (attempt + 1))
            if not replaced:
                # Never truncate the existing user-data file when replacement is blocked.
                # The old file remains intact; the caller can retry a later save.
                raise OSError(f"Could not atomically replace {target}")
        except Exception:
            try:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            except OSError:
                pass
            raise
