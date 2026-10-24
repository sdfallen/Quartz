"""Product acceptance of the real CLI -> MCP -> native backend path.

Only targets our disposable, local test window by exact title. No game/save,
existing user document, system settings or unrelated window is selected.
"""
import json
from pathlib import Path
import sys
import time
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.desktop_agents import DesktopAgentService


def main():
    directory = ROOT / "labs" / "desktop-bridge-20261020"
    directory.mkdir(parents=True, exist_ok=True)
    attempt = time.strftime("%Y%m%d-%H%M%S")
    provider = sys.argv[1] if len(sys.argv) > 1 else "codex"
    click_only = "--click-only" in sys.argv
    model = "gpt-6-luna" if provider == "codex" else "gemini-3.8-flash-low"
    service = DesktopAgentService()
    fixture_process = None
    try:
        if "--fixture" in sys.argv:
            fixture_script = "desktop_winforms_fixture.py" if "--classic-fixture" in sys.argv else "desktop_acceptance_fixture.py"
            fixture_process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / fixture_script)],
                                               cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            print("FIXTURE PID", fixture_process.pid, flush=True)
            for _ in range(30):
                if fixture_process.poll() is not None: raise RuntimeError("Disposable fixture exited during startup")
                matches = [w for w in service.windows() if w["title"] == "Quartz Disposable Desktop Test" and w["pid"] == fixture_process.pid]
                if matches: break
                time.sleep(.2)
        matches = [w for w in service.windows() if w["title"] == "Quartz Disposable Desktop Test"]
        if len(matches) != 1: raise RuntimeError("Disposable test window is not unique")
        task = ("In this disposable local test window, read the visual challenge number. "
                "Click the Test text entry, enter QUARTZ_" + provider.upper() +
                ", then click TEST BUTTON exactly ONCE. Observe the resulting click count and text. "
                "Report the real number, count and entered text. Do not close the app. No file/terminal tools.")
        if click_only:
            task = ("Execute this now using ONLY quartz_desktop MCP tools. Focus the selected window ONCE. "
                    "Read the visual number from the returned image, then click TEST BUTTON exactly ONCE "
                    "using the top-level snapshot_id returned by that focus call and coordinates from its image. "
                    "Read the resulting Clicks counter. Do not type, do not invoke any command or shell tool, "
                    "do not call other agents or browser tools, and do not close the window. Report only real observations.")
        if "--raw-input" in sys.argv:
            task = ("Test actual mouse/key input, not UI Automation invocation. Focus once and read the image. "
                    "Click TEST BUTTON exactly once using desktop_act action=click with integer window-relative x,y. "
                    "Do NOT use action=ui or invoke. Observe the result and focused button, then send key=space "
                    "using desktop_act action=key exactly once. Read the final counter, which should reflect the real events. "
                    "Do not type text or use terminal/browser tools; stop on any error without alternate channels.")
        print("START", provider, matches[0], flush=True)
        started_at = time.time()
        service.start(provider, matches[0]["handle"], task, model, "low", confirmed=True)
        while True:
            status = service.status()
            if status.get("run", {}).get("status") in {"completed", "failed", "cancelled"}: break
            time.sleep(.5)
        state_path = directory / "native-fixture-state.json"
        callback = json.loads(state_path.read_text()) if state_path.is_file() and state_path.stat().st_mtime >= started_at else None
        result = {"status": status, "audit": service.broker.audit, "native_target": matches[0],
                  "fixture_callback_after_start": callback}
        runtime_run = service._runtime.get(service._run_id)
        result["tool_calls"] = []
        for event in runtime_run.get("events", []):
            item = event.get("item") or {}
            if item.get("type") == "mcp_tool_call":
                result["tool_calls"].append({key: item.get(key) for key in ("server", "tool", "arguments", "error")})
        (directory / f"native-{provider}-{attempt}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(status, ensure_ascii=True), flush=True)
    finally:
        service.close()
        if fixture_process is not None and fixture_process.poll() is None:
            fixture_process.terminate()
            fixture_process.wait(timeout=10)


if __name__ == "__main__": main()
