"""Source integration: real CLI cancellation with an in-memory window fixture.

This sends NO Windows input and does NOT replace packaged GUI button acceptance.
"""
import json
from pathlib import Path
import sys
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.desktop_agents import DesktopAgentService
from tests.test_desktop_broker import FakeBackend
from gui import Api


def main():
    results = []
    for provider, model in (("codex", "gpt-6-luna"), ("antigravity", "gemini-3.8-flash-low")):
        for cause in ("stop-api", "simulated-foreground-loss"):
            backend = FakeBackend()
            service = DesktopAgentService(backend)
            api = Api(); api._desktop_agents = service
            result = {"provider":provider, "cause":cause, "native_ui_tested":False}
            try:
                response = api.desktop_operator_start(provider, 1, "Cancellation test only. Do not take input actions.", model, "low", True)
                if response.get("status") != "ok": raise RuntimeError(response)
                deadline = time.monotonic()+15
                while time.monotonic()<deadline:
                    run = service.status().get("run", {})
                    if run.get("pid"): break
                    time.sleep(.05)
                parent = psutil.Process(run["pid"])
                owned = [parent, *parent.children(recursive=True)]
                result["owned_processes"] = [{"pid":p.pid,"started":p.create_time()} for p in owned]
                started = time.monotonic()
                if cause == "stop-api": api.desktop_operator_stop()
                else:
                    token = service.broker._session["token"]  # test-only capability, never persisted
                    service.broker.call(token, {"name":"desktop_focus"})
                    backend.foreground = False
                deadline = time.monotonic()+15
                while time.monotonic()<deadline:
                    status = service.status()
                    if status.get("run",{}).get("status") in {"completed","cancelled","failed"} and not any(p.is_running() for p in owned): break
                    time.sleep(.1)
                service.close()
                result.update(seconds=round(time.monotonic()-started,3), status=service.status(),
                              owned_alive=[p.pid for p in owned if p.is_running()], input_actions=backend.actions,
                              leases_closed=all(lease.closed for lease in backend.leases))
                result["passed"] = (not result["owned_alive"] and result["leases_closed"] and
                                    not service.broker.status()["active"] and
                                    result["status"].get("run",{}).get("status") == "cancelled")
            except Exception as exc:
                result.update(passed=False,error=str(exc))
            finally:
                service.close()
                results.append(result)
                print(json.dumps({k:result[k] for k in ("provider","cause","passed")}),flush=True)
    path = ROOT/"labs/chat-style-20261021"/("cancellation-"+time.strftime("%Y%m%d-%H%M%S")+".json")
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(path,flush=True)


if __name__ == "__main__": main()
