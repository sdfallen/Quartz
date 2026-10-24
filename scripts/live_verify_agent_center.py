"""Harmless live verification for Quartz -> Squad -> Codex -> Squad."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.multi_agent_service import MultiAgentService  # noqa: E402


MARKER = "QUARTZ_AGENT_CENTER_LIVE_OK"


def main() -> int:
    service = MultiAgentService()
    initial = service.status()
    if not initial["squad"]["initialized"] or not initial["codex"]["ready"]:
        print(json.dumps({"ok": False, "stage": "probe", "status": initial}, ensure_ascii=False))
        return 1
    dispatched = service.dispatch_codex(
        f"Do not change files. Respond with exactly: {MARKER}",
        title="quartz-agent-center-live-verification",
        write=False,
    )
    run_id = dispatched["run"]["id"]
    deadline = time.monotonic() + 150
    run = dispatched["run"]
    while time.monotonic() < deadline:
        run = service.codex.get(run_id)
        if run["status"] in service.codex.TERMINAL:
            break
        time.sleep(0.5)
    if run["status"] != "completed" or MARKER not in run["result"]:
        print(json.dumps({"ok": False, "stage": "runtime", "run": run}, ensure_ascii=False))
        service.shutdown()
        return 2

    task_id = dispatched["task"]["id"]
    task_status = None
    while time.monotonic() < deadline:
        snapshot = service.status()
        task_status = next((task for task in snapshot["tasks"] if task["id"] == task_id), None)
        if task_status and task_status.get("status") == "completed":
            break
        time.sleep(0.25)
    result = {
        "ok": bool(task_status and task_status.get("status") == "completed"),
        "project": initial["project"]["path"],
        "squad_version": initial["squad"]["version"],
        "codex_version": initial["codex"]["version"],
        "authentication": initial["codex"]["authentication"],
        "run_id": run_id,
        "pid": run["pid"],
        "thread_id": run["thread_id"],
        "result": run["result"],
        "task": task_status,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    service.shutdown()
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
