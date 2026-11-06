"""Host-side checks for the Görev Sınavı task list (docs/task_exam/tasks_*.json).

The host evaluates; a model never does. Every check reads host-held state only: the
fixture folder, a baseline taken before the run, a host-owned fixture state file and the
run record Quartz itself wrote. A check that is not implemented here, or that needs a
human (`human_grade`), can never make a task VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import py_compile
import tempfile

HOST, HUMAN, MISSING = "host", "human", "not-implemented"


def _safe(root: Path, relative) -> Path:
    relative = Path(str(relative))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("Fixture-relative path required")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Fixture path escapes the fixture root")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root) -> dict:
    """Map of every file under the fixture root to its SHA-256 (taken by the host)."""
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Fixture must not contain links")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha(path)
    return result


def _normalize(text: str, how: str | None) -> str:
    if how and "BOM" in how:
        text = text.lstrip("﻿")
    if how and "CRLF" in how:
        text = text.replace("\r\n", "\n")
    return text


def _changed(before: dict, after: dict) -> set:
    return {p for p in set(before) | set(after) if before.get(p) != after.get(p)}


class Context:
    """What the host observed for one run. Every field is host-written."""

    def __init__(self, root, *, baseline=None, after=None, state=None, events=None,
                 reply=None, outcome=None, turn_status=None):
        self.root = Path(root)
        self.baseline = baseline or {}
        self.after = after if after is not None else (snapshot(root) if Path(root).is_dir() else {})
        self.state = state or {}
        self.events = events or []
        self.reply = reply
        self.outcome = outcome or {}
        self.turn_status = turn_status


def _file_text_equals(c, check):
    path = _safe(c.root, check["path"])
    return path.is_file() and _normalize(path.read_text(encoding="utf-8"), check.get("normalize")) == check["text"]


def _file_sha_unchanged(c, check):
    rel = Path(check["path"]).as_posix(); _safe(c.root, rel)
    return rel in c.baseline and c.after.get(rel) == c.baseline[rel]


def _python_compiles(c, check):
    with tempfile.TemporaryDirectory() as scratch:
        for index, rel in enumerate(check["paths"]):
            path = _safe(c.root, rel)
            try:
                py_compile.compile(str(path), cfile=str(Path(scratch) / f"{index}.pyc"), doraise=True)
            except (py_compile.PyCompileError, OSError):
                return False
    return True


def _changed_subset(c, check):
    allowed = {Path(p).as_posix() for p in check["paths"]}
    return _changed(c.baseline, c.after) <= allowed


CHECKS = {
    "file_text_equals": _file_text_equals,
    "file_sha_unchanged": _file_sha_unchanged,
    "fixture_tree_sha_unchanged": lambda c, k: c.after == c.baseline,
    "no_files_created": lambda c, k: all(not _safe(c.root, p).exists() for p in k["paths"]),
    "directory_exists": lambda c, k: _safe(c.root, k["path"]).is_dir(),
    "changed_files_subset": _changed_subset,
    "no_other_changes_in_fixture": lambda c, k: _changed(
        {p: h for p, h in c.baseline.items() if not p.startswith(tuple(k.get("allow", [])))},
        {p: h for p, h in c.after.items() if not p.startswith(tuple(k.get("allow", [])))}) == set(),
    "python_compiles": _python_compiles,
    "fixture_state": lambda c, k: k["field"] in c.state and c.state[k["field"]] == k["equals"],
    "fixture_events_equal": lambda c, k: list(c.events) == list(k["sequence"]),
    "reply_present": lambda c, k: isinstance(c.reply, str) and bool(c.reply.strip()),
    "reply_contains": lambda c, k: isinstance(c.reply, str) and k["text"] in c.reply,
    "goal_verdict_not": lambda c, k: c.outcome.get("goal_verdict") not in (None, k["value"]),
    "status_in": lambda c, k: c.outcome.get("execution_status") in k["values"],
    "turn_status_in": lambda c, k: c.turn_status in k["values"],
    "participants_record": lambda c, k: (c.outcome.get("participants") or {}).get(k["agent"]) not in (None, k["value_not"]),
}


def evaluate(check: dict, context: Context) -> dict:
    name = check.get("check")
    if name == "human_grade":
        return {"check": name, "kind": HUMAN, "passed": None}
    function = CHECKS.get(name)
    if function is None:
        return {"check": name, "kind": MISSING, "passed": None}
    try:
        return {"check": name, "kind": HOST, "passed": bool(function(context, check))}
    except (KeyError, ValueError, OSError, UnicodeDecodeError) as exc:
        return {"check": name, "kind": HOST, "passed": False, "error": type(exc).__name__}


def verdict(results: list) -> str:
    """FAILED if any host check failed; VERIFIED only if every check is a passing host check."""
    if any(r["kind"] == HOST and r["passed"] is False for r in results):
        return "FAILED"
    if results and all(r["kind"] == HOST and r["passed"] is True for r in results):
        return "VERIFIED"
    return "NOT VERIFIED"


def load_state(path) -> dict:
    """Read a host-owned fixture state file (JSON object, at most 64 KiB)."""
    path = Path(path)
    if path.stat().st_size > 64 * 1024:
        raise ValueError("Fixture state too large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Fixture state must be an object")
    return value
