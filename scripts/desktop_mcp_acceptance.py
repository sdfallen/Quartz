"""Live provider/tool-transport acceptance, with NO native desktop actions.

The deterministic in-memory backend is explicitly NOT a Windows UI acceptance.
Only this transport test is allowed to use it; production uses NativeDesktopBackend.
"""
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.desktop_agents import DesktopAgentService
from tests.test_desktop_broker import FakeBackend


def main():
    directory = ROOT / "labs" / "desktop-bridge-20261020"
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    attempt = time.strftime("%Y%m%d-%H%M%S")
    for provider, model in (("codex", "gpt-6-luna"), ("antigravity", "gemini-3.8-flash-low")):
        if len(sys.argv) > 1 and provider != sys.argv[1]: continue
        backend = FakeBackend()
        # A real valid PNG, but still a synthetic protocol fixture, NOT a desktop screenshot.
        import base64, io
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (400, 160), "white")
        ImageDraw.Draw(image).text((20, 40), "MCP TRANSPORT TEST ONLY - QUARTZ 7319", fill="black")
        output = io.BytesIO(); image.save(output, "PNG")
        png = base64.b64encode(output.getvalue()).decode()
        backend.observe = lambda _: {"image_base64": png, "width": 400, "height": 160, "ui": {"elements": []},
                                     "synthetic_transport_fixture": True}
        service = DesktopAgentService(backend)
        try:
            print("START", provider, flush=True)
            task = "This is a synthetic MCP TRANSPORT test, not a desktop test. Focus once and inspect the image. Read the four-digit number visible in it. Do not take any input action. Report that number and that no Windows UI was tested."
            if "--action" in sys.argv:
                task = ("This is a SYNTHETIC IN-MEMORY MCP PARAMETER test, not Windows input. "
                        "Call desktop_focus once, then call desktop_act exactly once with the top-level snapshot_id "
                        "from that result, action=click, x=23, y=24. The backend only records the parameters in memory, "
                        "it does not click anything. Do not use any other tool. Report the result and whether you could supply those arguments.")
            if "--minimal-schema" in sys.argv:
                with patch("core.desktop_agents.mcp_command", return_value=[sys.executable, str(ROOT / "scripts/desktop_mcp_schema_probe.py")]):
                    service.start(provider, 1, task, model, "low", confirmed=True)
            else:
                service.start(provider, 1, task, model, "low", confirmed=True)
            while True:
                status = service.status(); run = status.get("run", {})
                if run.get("status") in {"completed", "failed", "cancelled"}: break
                time.sleep(.5)
            results.append({"provider": provider, "model": model, "run": run, "audit": service.broker.audit,
                            "native_ui_tested": False, "input_actions": backend.actions})
            results[-1]["tool_calls"] = [{key: item.get(key) for key in ("server", "tool", "arguments", "error")}
                for event in service._runtime.get(service._run_id).get("events", [])
                if (item := event.get("item") or {}).get("type") == "mcp_tool_call"]
            print(provider, run.get("status"), run.get("result"), run.get("errors"), flush=True)
        finally:
            service.close()
            (directory / "mcp-provider-transport.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            (directory / f"mcp-provider-transport-{attempt}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__": raise SystemExit(main())
