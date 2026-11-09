"""Safe subprocess adapter for the documented Squad CLI surface."""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path


_AGENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TASK_ID = re.compile(r"^[0-9a-fA-F-]{36}$")
_TASK_HEADER = re.compile(r"^\[task ([0-9a-fA-F-]{36})\] (\S+)$")
_HISTORY = re.compile(
    r"^\*?\s*\[([^]]+)]\s+([^ ]+)\s+->\s+([^:]+):\s?(.*)$"
)
_ROOT_POLLUTION_FILES = (".gitignore", "AGENTS.md", "CLAUDE.md", "GEMINI.md")
_SQLITE_HEADER = b"SQLite format 3\x00"
_FILE_ATTRIBUTE_HIDDEN = 0x02
_INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
_CORRUPT_DB_TOKENS = (
    "database disk image is malformed",
    "file is not a database",
    "not a database file",
    "no such table",
)


class SquadCommandError(RuntimeError):
    def __init__(self, message, *, args=None, returncode=None, stderr=""):
        super().__init__(message)
        self.args_list = list(args or [])
        self.returncode = returncode
        self.stderr = stderr


class SquadAdapter:
    CLIENTS = {"claude", "gemini", "codex", "opencode"}
    _DB_LOCK = threading.RLock()

    def __init__(self, project_path, executable=None, timeout=15):
        self.project_path = Path(project_path).resolve(strict=True)
        if not self.project_path.is_dir():
            raise NotADirectoryError(str(self.project_path))
        self.executable = self._find_executable(executable)
        self.timeout = max(1, int(timeout))

    @staticmethod
    def _find_executable(explicit=None) -> str:
        candidates = [explicit, os.getenv("QUARTZ_SQUAD_PATH"), shutil.which("squad.exe"), shutil.which("squad")]
        bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        candidates.append(bundle / "assets" / "bin" / "squad.exe")
        candidates.append(r"C:\squad\squad.exe")
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        raise FileNotFoundError("Squad CLI was not found")

    @staticmethod
    def _is_db_corrupt(db_path: Path) -> bool:
        """Return True if messages.db exists as a real file (>=100 bytes) with a corrupt SQLite image."""
        try:
            if not db_path.is_file():
                return False
            size = db_path.stat().st_size
            # Unit tests may touch 0-byte or tiny placeholder files (e.g. b'fixture') with mocked CLI calls.
            if size < 100:
                return False
            with db_path.open("rb") as fh:
                header = fh.read(16)
            if header != _SQLITE_HEADER:
                return True
            uri = f"file:{db_path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=0.5)
            try:
                rows = conn.execute("PRAGMA quick_check(1);").fetchall()
            finally:
                conn.close()
            if not rows or str(rows[0][0]).strip().lower() != "ok":
                return True
            return False
        except sqlite3.DatabaseError:
            return True
        except OSError:
            return False

    def _snapshot_root_files(self) -> dict[str, tuple[bytes, int, int] | None]:
        snapshot: dict[str, tuple[bytes, int, int] | None] = {}
        for name in _ROOT_POLLUTION_FILES:
            target = self.project_path / name
            try:
                if target.is_file():
                    st = target.stat()
                    snapshot[name] = (target.read_bytes(), st.st_atime_ns, st.st_mtime_ns)
                else:
                    snapshot[name] = None
            except OSError:
                snapshot[name] = None
        return snapshot

    def _restore_root_files(self, snapshot: dict[str, tuple[bytes, int, int] | None]) -> None:
        """Prevent `squad init` from polluting the project root with untracked CLAUDE.md/AGENTS.md/GEMINI.md/.gitignore."""
        for name, state in snapshot.items():
            target = self.project_path / name
            try:
                if state is None:
                    if target.is_file():
                        target.unlink(missing_ok=True)
                else:
                    raw, atime_ns, mtime_ns = state
                    if not target.is_file() or target.read_bytes() != raw:
                        target.write_bytes(raw)
                    os.utime(target, ns=(atime_ns, mtime_ns))
            except OSError:
                pass
        git_exclude = self.project_path / ".git" / "info" / "exclude"
        try:
            if git_exclude.parent.is_dir():
                existing = git_exclude.read_text(encoding="utf-8", errors="replace") if git_exclude.is_file() else ""
                lines = {line.strip() for line in existing.splitlines()}
                if ".squad/" not in lines and ".squad" not in lines:
                    prefix = "" if (not existing or existing.endswith("\n")) else "\n"
                    git_exclude.write_text(existing + prefix + ".squad/\n", encoding="utf-8")
        except OSError:
            pass

    def _hide_squad_dir(self) -> None:
        """Mark .squad as hidden on Windows (matching .git) so recursive shell globs skip it."""
        if os.name != "nt":
            return
        squad_root = self.project_path / ".squad"
        if not squad_root.is_dir():
            return
        try:
            kernel32 = ctypes.windll.kernel32
            attrs = kernel32.GetFileAttributesW(str(squad_root))
            if attrs != _INVALID_FILE_ATTRIBUTES and not (attrs & _FILE_ATTRIBUTE_HIDDEN):
                kernel32.SetFileAttributesW(str(squad_root), attrs | _FILE_ATTRIBUTE_HIDDEN)
        except Exception:
            pass

    def _remove_corrupt_db_files(self) -> None:
        squad_root = self.project_path / ".squad"
        for suffix in ("messages.db", "messages.db-wal", "messages.db-shm"):
            try:
                (squad_root / suffix).unlink(missing_ok=True)
            except OSError:
                pass

    @property
    def initialized(self) -> bool:
        squad_root = self.project_path / ".squad"
        db_path = squad_root / "messages.db"
        if self._is_db_corrupt(db_path):
            return False
        return db_path.is_file() or (
            (squad_root / "roles").is_dir() and (squad_root / "teams").is_dir()
        )

    def _repair_workspace(self) -> bool:
        """Rebuild a corrupted or partially-initialized .squad directory in place."""
        with self._DB_LOCK:
            self._remove_corrupt_db_files()
            snap = self._snapshot_root_files()
            try:
                init_res = self._run(["init"], require_workspace=False, _allow_repair=False)
            finally:
                self._restore_root_files(snap)
            if not init_res.get("ok"):
                return False
            self._hide_squad_dir()
            db_path = self.project_path / ".squad" / "messages.db"
            if not db_path.is_file():
                self._run(["agents", "--json"], require_workspace=False, _allow_repair=False)
            self._hide_squad_dir()
            return self.initialized

    def initialize(self) -> dict:
        with self._DB_LOCK:
            squad_root = self.project_path / ".squad"
            db_path = squad_root / "messages.db"
            if self._is_db_corrupt(db_path):
                self._remove_corrupt_db_files()
            if self.initialized and db_path.is_file():
                self._hide_squad_dir()
                return {"initialized": True, "existing": True}
            snap = self._snapshot_root_files()
            try:
                result = self._run(["init"], require_workspace=False, _allow_repair=False)
            finally:
                self._restore_root_files(snap)
            if not result["ok"]:
                raise SquadCommandError(result["error"] or "Squad init failed", args=["init"],
                                        returncode=result["returncode"])
            self._hide_squad_dir()
            if not db_path.is_file():
                # `squad init` only creates roles/ and teams/; running `agents --json` materializes messages.db.
                self._run(["agents", "--json"], require_workspace=False, _allow_repair=False)
            self._hide_squad_dir()
            return {"initialized": self.initialized, "existing": False, "output": result["stdout"]}

    def status(self) -> dict:
        squad_root = self.project_path / ".squad"
        db_path = squad_root / "messages.db"
        if squad_root.is_dir():
            if self._is_db_corrupt(db_path):
                self._repair_workspace()
            else:
                self._hide_squad_dir()
        result = self._run(["--version"], require_workspace=False, _allow_repair=False)
        return {
            "installed": result["ok"],
            "version": result["stdout"].strip(),
            "executable": self.executable,
            "workspace": str(self.project_path),
            "initialized": self.initialized,
            "database": str(db_path),
            "error": result["error"],
        }

    def agents(self, include_archived=False) -> list[dict]:
        args = ["agents"]
        if include_archived:
            args.append("--all")
        args.append("--json")
        result = self._checked(args)
        return self._json_lines(result["stdout"])

    def join(self, agent_id, role="worker", client="codex", protocol_version=2) -> dict:
        self._agent(agent_id)
        self._agent(role)
        if client not in self.CLIENTS:
            raise ValueError(f"Unsupported Squad client: {client}")
        result = self._checked([
            "join", agent_id, "--role", role, "--client", client,
            "--protocol-version", str(int(protocol_version)),
        ])
        match = re.search(r"Joined as ([^\s(]+)", result["stdout"])
        return {"id": match.group(1) if match else agent_id, "output": result["stdout"]}

    def leave(self, agent_id) -> dict:
        self._agent(agent_id)
        return self._checked(["leave", agent_id])

    def send(self, sender, recipient, message, task_id=None) -> dict:
        self._agent(sender)
        if recipient != "@all":
            self._agent(recipient)
        text = self._text(message, "message", 50_000)
        args = ["send"]
        if task_id:
            self._task(task_id)
            args += ["--task-id", task_id]
        args += [sender, recipient, text]
        return self._checked(args)

    def receive(self, agent_id) -> list[dict]:
        self._agent(agent_id)
        result = self._checked(["receive", agent_id, "--json"])
        return self._json_lines(result["stdout"])

    def create_task(self, sender, recipient, title, body="") -> dict:
        self._agent(sender)
        self._agent(recipient)
        args = [
            "task", "create", sender, recipient, "--title",
            self._text(title, "title", 500),
        ]
        if body:
            args += ["--body", self._text(body, "body", 50_000)]
        result = self._checked(args)
        match = re.search(r"Created task ([0-9a-fA-F-]{36})", result["stdout"])
        if not match:
            raise SquadCommandError("Squad did not return a task id", args=args)
        return {"id": match.group(1), "output": result["stdout"]}

    def ack_task(self, agent_id, task_id) -> dict:
        self._agent(agent_id); self._task(task_id)
        return self._checked(["task", "ack", agent_id, task_id])

    def complete_task(self, agent_id, task_id, summary) -> dict:
        self._agent(agent_id); self._task(task_id)
        return self._checked([
            "task", "complete", agent_id, task_id, "--summary",
            self._text(summary, "summary", 50_000),
        ])

    def requeue_task(self, task_id, recipient=None) -> dict:
        self._task(task_id)
        args = ["task", "requeue", task_id]
        if recipient:
            self._agent(recipient)
            args += ["--to", recipient]
        return self._checked(args)

    def tasks(self, agent_id=None, status=None) -> list[dict]:
        args = ["task", "list"]
        if agent_id:
            self._agent(agent_id); args += ["--agent", agent_id]
        if status:
            args += ["--status", str(status)]
        result = self._checked(args)
        return self._parse_tasks(result["stdout"])

    def history(self, agent_id=None) -> list[dict]:
        args = ["history"]
        if agent_id:
            self._agent(agent_id); args.append(agent_id)
        result = self._checked(args)
        rows = []
        for line in result["stdout"].splitlines():
            match = _HISTORY.match(line.strip())
            if match:
                rows.append({
                    "timestamp": match.group(1), "from": match.group(2),
                    "to": match.group(3), "content": match.group(4),
                    "unread": line.lstrip().startswith("*"),
                })
        return rows

    def _run(self, args, *, require_workspace=True, timeout=None, _allow_repair=True) -> dict:
        if require_workspace and not self.initialized:
            if _allow_repair and (self.project_path / ".squad").is_dir():
                self._repair_workspace()
            if not self.initialized:
                raise SquadCommandError(f"Squad is not initialized in {self.project_path}")
        command = [self.executable, *map(str, args)]
        env = os.environ.copy()
        env.setdefault("HOME", str(Path.home()))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        last_result = None
        for attempt in range(3):
            with self._DB_LOCK:
                try:
                    completed = subprocess.run(
                        command, cwd=str(self.project_path), env=env,
                        stdin=subprocess.DEVNULL, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=timeout or self.timeout,
                        creationflags=flags, check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise SquadCommandError("Squad command timed out", args=args) from exc
            stderr = completed.stderr.strip()
            last_result = {
                "ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": stderr,
                "error": stderr if completed.returncode else "",
            }
            if last_result["ok"]:
                return last_result
            combined_lower = (stderr + " " + completed.stdout).lower()
            if _allow_repair and attempt == 0 and any(tok in combined_lower for tok in _CORRUPT_DB_TOKENS):
                if self._repair_workspace():
                    continue
            if ("locked" in combined_lower or "unable to open database" in combined_lower) and attempt < 2:
                time.sleep(0.15 * (attempt + 1))
                continue
            break
        return last_result

    def _checked(self, args) -> dict:
        result = self._run(args)
        if not result["ok"]:
            raise SquadCommandError(
                result["stderr"] or result["stdout"].strip() or "Squad command failed",
                args=args, returncode=result["returncode"], stderr=result["stderr"],
            )
        return result

    @staticmethod
    def _json_lines(text) -> list[dict]:
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SquadCommandError(f"Invalid Squad JSON output: {line[:120]}") from exc
            if isinstance(value, dict):
                rows.append(value)
        return rows

    @staticmethod
    def _parse_tasks(text) -> list[dict]:
        tasks, current = [], None
        for raw in text.splitlines():
            line = raw.rstrip()
            header = _TASK_HEADER.match(line.strip())
            if header:
                current = {"id": header.group(1), "status": header.group(2)}
                tasks.append(current)
            elif current and line.startswith("  ") and ":" in line:
                key, value = line.strip().split(":", 1)
                current[key] = value.strip()
        return tasks

    @staticmethod
    def _agent(value):
        if not _AGENT_ID.fullmatch(str(value or "")):
            raise ValueError(f"Invalid Squad agent id: {value!r}")

    @staticmethod
    def _task(value):
        if not _TASK_ID.fullmatch(str(value or "")):
            raise ValueError(f"Invalid Squad task id: {value!r}")

    @staticmethod
    def _text(value, name, limit):
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{name} cannot be empty")
        if len(text) > limit:
            raise ValueError(f"{name} exceeds {limit} characters")
        return text
