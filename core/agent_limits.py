"""Usage-limit snapshot for the three agents (a small indicator in the UI).

Sources are local, read-only and never credentials:
- Codex: the ``rate_limits`` block Codex itself writes into its session logs
  (~/.codex/sessions/**/rollout-*.jsonl); only that field is parsed.
- Claude: the ``rate_limit_event`` that ``claude -p`` streams; ClaudeRuntime
  stores the last one in ~/.quartz/agent_limits.json.
- Antigravity: its CLI exposes no quota data, so the state is "unknown".
Values are percentages of the provider's own windows (5 hours / 7 days).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

STORE = Path.home() / ".quartz" / "agent_limits.json"
_TAIL_BYTES = 256 * 1024


def _state(percent):
    if percent is None:
        return "unknown"
    return "full" if percent >= 100 else "warn" if percent >= 80 else "ok"


def _entry(five_hour=None, week=None, resets_at=None, source="", observed_at=None):
    worst = max([p for p in (five_hour, week) if p is not None], default=None)
    return {"state": _state(worst), "five_hour": five_hour, "week": week,
            "resets_at": resets_at, "source": source, "observed_at": observed_at}


def _find_key(value, key):
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def codex_limits(home=None):
    root = Path(home or os.getenv("CODEX_HOME") or (Path.home() / ".codex")) / "sessions"
    try:
        files = sorted(root.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    except OSError:
        files = []
    for path in files:
        try:
            with path.open("rb") as handle:
                handle.seek(max(0, path.stat().st_size - _TAIL_BYTES))
                lines = handle.read().decode("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"rate_limits"' not in line:
                continue
            try:
                limits = _find_key(json.loads(line), "rate_limits")
            except ValueError:
                continue
            if not isinstance(limits, dict):
                continue
            primary, secondary = limits.get("primary") or {}, limits.get("secondary") or {}
            return _entry(primary.get("used_percent"), secondary.get("used_percent"),
                          primary.get("resets_at"), "codex-session", path.stat().st_mtime)
    return _entry(source="none")


def record_claude_event(event, store=STORE):
    """Called by ClaudeRuntime for every ``rate_limit_event``; best effort."""
    info = (event or {}).get("rate_limit_info") or {}
    windows = info.get("unifiedWindows") or {}
    five, week = windows.get("five_hour") or {}, windows.get("seven_day") or {}
    pct = lambda w: round(float(w["utilization"]) * 100, 1) if isinstance(w.get("utilization"), (int, float)) else None
    snapshot = _entry(pct(five), pct(week), five.get("resetsAt") or info.get("resetsAt"),
                      "claude-stream", time.time())
    if info.get("status") == "rejected":
        snapshot["state"] = "full"
    try:
        store.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
        data["claude"] = snapshot
        tmp = store.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, store)
    except (OSError, ValueError):
        pass
    return snapshot


def claude_limits(store=STORE):
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
        entry = data.get("claude")
        if isinstance(entry, dict):
            return entry
    except (OSError, ValueError):
        pass
    return _entry(source="none")


def snapshot(codex_home=None, store=STORE):
    return {"codex": codex_limits(codex_home), "claude": claude_limits(store),
            "antigravity": _entry(source="unavailable")}
