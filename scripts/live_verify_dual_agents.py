"""Live, read-only Codex + Antigravity + Squad bridge verification."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.multi_agent_service import MultiAgentService  # noqa: E402


PROMPT = (
    "Without using tools, commands, or modifying files, explain in one concise sentence "
    "why a bounded work queue prevents unbounded memory growth in a long-running service."
)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    service = MultiAgentService()
    try:
        status = service.status("squad-pilot")
        if not status["codex"]["ready"]:
            raise RuntimeError(f"Codex is not ready: {status['codex'].get('error', '')}")
        if not status["antigravity"]["ready"]:
            raise RuntimeError(
                f"Antigravity is not ready: {status['antigravity'].get('error', '')}"
            )
        started = service.dispatch_collaboration(
            PROMPT, title="Quartz real dual-agent bridge verification",
            project_id="squad-pilot", write=False,
        )
        collaboration_id = started["collaboration"]["id"]
        deadline = time.monotonic() + 15 * 60
        while time.monotonic() < deadline:
            current = next(
                item for item in service.status("squad-pilot")["collaborations"]
                if item["id"] == collaboration_id
            )
            if current["status"] in {"completed", "failed"}:
                print(json.dumps(current, indent=2, ensure_ascii=False))
                if current["status"] != "completed":
                    raise RuntimeError(current["error"] or "Dual-agent verification failed")
                if len(current["run_ids"]) != 3 or len(current["messages"]) != 3:
                    raise RuntimeError("The complete bidirectional bridge lifecycle was not observed")
                return
            time.sleep(1)
        raise TimeoutError("Dual-agent verification timed out")
    finally:
        service.shutdown()


if __name__ == "__main__":
    main()
