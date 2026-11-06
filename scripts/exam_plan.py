"""Validate the Görev Sınavı task list, bind per-run nonces and report oracle coverage.

Reads only the task list; starts nothing. Offline regression tasks become a manifest for
scripts/task_exam_runner.py. Account/desktop tasks are listed with what still blocks them.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exam_oracle import CHECKS  # noqa: E402

NONCE = re.compile(r"<nonce(\d*)>")
NEEDS = {"account", "desktop"}
MODES = {"any", "codex", "antigravity", "together", "offline"}


def validate(data: dict) -> list:
    errors = []
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return ["tasks must be a non-empty list"]
    seen = set()
    for task in tasks:
        tid = task.get("id")
        if not isinstance(tid, str) or not re.fullmatch(r"exam-[a-z]+-\d{2}", tid or ""):
            errors.append(f"bad id: {tid!r}"); continue
        if tid in seen: errors.append(f"duplicate id: {tid}")
        seen.add(tid)
        if not set(task.get("needs", [])) <= NEEDS: errors.append(f"{tid}: unknown needs")
        if task.get("mode") not in MODES: errors.append(f"{tid}: unknown mode")
        if not task.get("success"): errors.append(f"{tid}: no success checks")
        if task.get("mode") == "offline" and (task.get("needs") or task.get("kind") != "regression"):
            errors.append(f"{tid}: offline tasks must be needs-free regression tasks")
    for tid in data.get("adapter_order", []):
        if tid not in seen: errors.append(f"adapter_order names unknown task {tid}")
    return errors


def bind_nonces(task: dict, rng=secrets) -> tuple[dict, dict]:
    """Replace <nonce>, <nonce1>... with fresh host values; the model never chooses them."""
    values = {}
    def value(match):
        key = match.group(0)
        if key not in values:
            values[key] = "q" + rng.token_hex(4)
        return values[key]
    def walk(item):
        if isinstance(item, str): return NONCE.sub(value, item)
        if isinstance(item, list): return [walk(i) for i in item]
        if isinstance(item, dict): return {k: walk(v) for k, v in item.items()}
        return item
    return walk(copy.deepcopy(task)), values


def coverage(task: dict) -> dict:
    names = [c.get("check") for c in task.get("success", [])]
    human = [n for n in names if n == "human_grade"]
    missing = [n for n in names if n not in CHECKS and n not in {"human_grade", "regression_passes"}]
    return {"id": task["id"], "needs": task.get("needs", []), "checks": len(names),
            "host_implemented": len(names) - len(human) - len(missing), "human": len(human),
            "missing": missing, "auto_verifiable": not human and not missing}


def offline_manifest(data: dict) -> dict:
    return {"tasks": [{"id": t["id"], "kind": "regression", "modules": t["modules"]}
                      for t in data["tasks"] if t.get("mode") == "offline"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=ROOT / "docs/task_exam/tasks_20261105.json")
    parser.add_argument("--manifest-out", type=Path)
    args = parser.parse_args(argv)
    data = json.loads(args.tasks.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        print(json.dumps({"status": "INVALID", "errors": errors}, ensure_ascii=False, indent=1))
        return 2
    rows = [coverage(t) for t in data["tasks"]]
    report = {"status": "VALID", "tasks": len(rows),
              "auto_verifiable": sum(r["auto_verifiable"] for r in rows),
              "needs_human_grade": sum(bool(r["human"]) for r in rows),
              "missing_checks": sorted({m for r in rows for m in r["missing"]}),
              "rows": rows}
    if args.manifest_out:
        args.manifest_out.write_text(json.dumps(offline_manifest(data), indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
