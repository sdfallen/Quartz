"""Test NaturalDesktopTask with Antigravity as operator."""
from pathlib import Path
import subprocess, sys, time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.desktop_broker import DesktopBroker
from core.desktop_native import NativeDesktopBackend
from core.natural_desktop import NaturalDesktopTask

FIXTURE_DIR = ROOT / "labs/natural-desktop-20261022"
FIXTURE_EXE = FIXTURE_DIR / "QuartzTestApp.exe"

backend = NativeDesktopBackend()
backend.ensure_input_desktop()

fixture_proc = subprocess.Popen([str(FIXTURE_EXE)], cwd=str(FIXTURE_DIR))
time.sleep(1.5)

broker = DesktopBroker(backend)
events = []
def emit(cid, sender, content, metadata):
    events.append({"sender": sender, "content": content})
    print(f"[{sender.upper()}]: {content[:100]}")

service = NaturalDesktopTask(
    SimpleNamespace(broker=broker, windows=backend.windows),
    emit,
    evidence_root=FIXTURE_DIR / "evidence"
)

models = {"antigravity": {"model": "gemini-3.8-flash-low", "effort": "low"}}
prompt = "Gemini, açık test uygulamasındaki sorunu incele ve düzelt."

try:
    print("Starting NaturalDesktopTask with Antigravity as operator...")
    service.start(prompt, {"path": str(FIXTURE_DIR), "id": "fixture-proj"}, "test-conv", models)
    deadline = time.monotonic() + 120
    approved = False
    while time.monotonic() < deadline and service.status()["active"]:
        status = service.status()
        pending = status.get("pending")
        if pending and not approved:
            print(f"Approving inline permission request {pending['id']}...")
            service.approve(pending["id"], confirmed=True)
            approved = True

        verif = status.get("job", {}).get("verification", {})
        if verif.get("status") == "OBSERVED UI CRITERION VERIFIED":
            print(">>> VERIFICATION SUCCEEDED!")
            break
        time.sleep(1)

    print("Task active:", service.status()["active"])
    print("Broker actions:", broker.status()["actions"])
    print("Verification:", service.status().get("job", {}).get("verification"))
finally:
    service.stop()
    broker.close()
    if fixture_proc.poll() is None:
        fixture_proc.terminate()
