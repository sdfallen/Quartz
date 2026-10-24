"""End-to-end natural desktop task acceptance verification.

Tests the full lifecycle:
1. Natural user prompt in chat
2. Automatic intent detection and role assignment (Codex operator, Gemini observer)
3. Inline permission request generation in chat
4. User inline approval
5. Live screenshot capture & UIA inspection
6. Real visual interpretation and bounded UI action on QuartzTestApp.exe
7. Fresh post-action observation & verification with desktop_verify
8. Real Squad messaging and callback verification
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.desktop_broker import DesktopBroker
from core.desktop_native import NativeDesktopBackend
from core.natural_desktop import NaturalDesktopTask
from core.squad_adapter import SquadAdapter

FIXTURE_DIR = ROOT / "labs/natural-desktop-20261022"
FIXTURE_EXE = FIXTURE_DIR / "QuartzTestApp.exe"


def main():
    if not FIXTURE_EXE.is_file():
        raise FileNotFoundError(f"Fixture executable not found: {FIXTURE_EXE}")

    destination = FIXTURE_DIR
    backend = NativeDesktopBackend()

    # Clear previous callback if exists
    cb_path = FIXTURE_DIR / "callback.json"
    if cb_path.exists():
        cb_path.unlink()

    # Launch the disposable test fixture
    print("Launching QuartzTestApp.exe...")
    fixture_proc = subprocess.Popen([str(FIXTURE_EXE)], cwd=str(FIXTURE_DIR))
    time.sleep(1.5)

    broker = DesktopBroker(backend)
    events = []
    def emit(cid, sender, content, metadata):
        events.append({"sender": sender, "content": content, "metadata": metadata, "at": time.time()})
        print(f"[{sender.upper()}]: {content[:120]}")

    service = NaturalDesktopTask(
        SimpleNamespace(broker=broker, windows=backend.windows),
        emit,
        evidence_root=FIXTURE_DIR / "evidence"
    )

    models = {
        "codex": {"model": "gpt-6-luna", "effort": "low"},
        "antigravity": {"model": "gemini-3.8-flash-low", "effort": "low"}
    }
    prompt = "Codex, açık test uygulamasındaki sorunu incele ve düzelt. Gemini, test loglarını kontrol et."

    try:
        print(f"Starting NaturalDesktopTask with prompt: '{prompt}'")
        service.start(prompt, {"path": str(FIXTURE_DIR), "id": "fixture-proj"}, "natural-e2e-conv", models)

        # Wait for inline permission request
        deadline = time.monotonic() + 180
        approved_ids = set()
        while time.monotonic() < deadline and service.status()["active"]:
            status = service.status()
            pending = status.get("pending")
            if pending and pending["id"] not in approved_ids:
                print(f"Inline permission requested: id={pending['id']}, reason='{pending.get('reason')}'")
                print(f"Targets requested: {pending.get('targets')}")
                # Simulate inline user approval
                service.approve(pending["id"], confirmed=True)
                approved_ids.add(pending["id"])
                print(f"Inline permission APPROVED: {pending['id']}")

            # Check if verification achieved or runs finished
            verif = status.get("job", {}).get("verification", {})
            if verif.get("status") == "OBSERVED UI CRITERION VERIFIED":
                print(">>> VERIFICATION SUCCEEDED: Observed UI criterion verified!")
                break

            time.sleep(1.0)

        # Allow extra time for agents to post final wrap-up
        wrap_deadline = time.monotonic() + 20
        while time.monotonic() < wrap_deadline and service.status()["active"]:
            time.sleep(1.0)

        if service.status()["active"]:
            service.stop("acceptance test completed")

        if service.thread:
            service.thread.join(timeout=10)

        # Inspect outcome
        final_status = service.status()
        callback_data = json.loads(cb_path.read_text(encoding="utf-8")) if cb_path.exists() else None
        log_content = (FIXTURE_DIR / "test.log").read_text(encoding="utf-8") if (FIXTURE_DIR / "test.log").exists() else ""

        report = {
            "prompt": prompt,
            "approved": list(approved_ids),
            "verification": final_status.get("job", {}).get("verification"),
            "callback": callback_data,
            "actions": (callback_data.get("action_count", 0) if callback_data else broker.status().get("actions", 0)),
            "broker_audit_count": len(broker.audit),
            "events_count": len(events),
            "evidence_dir": str(service.evidence) if hasattr(service, "evidence") else None,
            "runs": {p: r.get(rid) for p, (r, rid) in service.runs.items()},
        }

        report_path = FIXTURE_DIR / "e2e_acceptance_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n=== E2E ACCEPTANCE REPORT ===")
        print(f"Report written to: {report_path}")
        print(f"Callback data: {callback_data}")
        print(f"Actions performed: {report['actions']}")
        print(f"Verification status: {report['verification']}")

        passed = bool(approved_ids and callback_data and callback_data.get("matches_reference") and (report["actions"] > 0 or report["broker_audit_count"] > 0))
        print(f"Overall Acceptance Passed: {passed}")
        return 0 if passed else 1

    finally:
        service.stop()
        broker.close()
        if fixture_proc.poll() is None:
            fixture_proc.terminate()
            fixture_proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
