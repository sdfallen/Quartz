"""Read-only UIA point lookup on our owned fixture; never sends input."""
from pathlib import Path
import concurrent.futures
import json
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.desktop_native import NativeDesktopBackend

backend = NativeDesktopBackend()
fixture = subprocess.Popen([sys.executable, str(ROOT / "scripts/desktop_acceptance_fixture.py")],
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
try:
    for _ in range(30):
        targets = [w for w in backend.windows() if w["pid"] == fixture.pid]
        if targets: break
        time.sleep(.2)
    target = targets[0]
    # Let the WebView document expose its accessibility provider, not just the
    # initially empty host Pane.
    time.sleep(3)
    def observed_probe():
        try:
            phases = {"before": probe()}
            with backend.controller._desktop() as desktop:
                controls = backend.controller._window(desktop, target["handle"]).descendants(depth=7)[:800]
                phases["after_descendants"] = probe()
                for control in controls:
                    item = backend.controller._describe(control)
                    check = probe()
                    if any("error" in result for result in check):
                        phases["first_describe_failure"] = {"item": item, "check": check}
                        break
            backend._safe_controls(target)
            phases["after_safe_controls"] = probe()
            try:
                import comtypes
                from pywinauto.uia_defines import IUIA
                from ctypes.wintypes import POINT
                with backend.controller._desktop():
                    client = IUIA().ui_automation_client
                    local = comtypes.CoCreateInstance(client.CUIAutomation().IPersist_GetClassID(),
                              interface=client.IUIAutomation, clsctx=comtypes.CLSCTX_INPROC_SERVER)
                    element = local.ElementFromPoint(POINT(target["rect"][0]+394, target["rect"][1]+256))
                    phases["fresh_client"] = str(element.CurrentName)
            except Exception:
                phases["fresh_client"] = traceback.format_exc()
            backend.controller.inspect(target["handle"])
            phases["after_inspect"] = probe()
            with backend.controller._desktop() as desktop:
                win = backend.controller._window(desktop, target["handle"])
                focused = [c for c in win.descendants(depth=7)[:800] if c.has_keyboard_focus()]
                phases["focus_count"] = len(focused)
                if focused: backend.controller._describe(focused[0])
            phases["after_focused"] = probe()
            from PIL import ImageGrab
            ImageGrab.grab(bbox=tuple(target["rect"]), all_screens=True)
            phases["after_capture"] = probe()
            return phases
        except Exception:
            return {"observe_error": traceback.format_exc()}
    def probe():
        try:
            if "--with-input-import" in sys.argv:
                import pyautogui  # import only; no input is sent
            with backend.controller._desktop() as desktop:
                win = backend.controller._window(desktop, target["handle"])
                rect = win.rectangle()
                if "--with-input-import" in sys.argv:
                    import ctypes
                    from ctypes import wintypes
                    user32 = backend._user32()
                    user32.WindowFromPoint.argtypes = [wintypes.POINT]
                    user32.WindowFromPoint.restype = wintypes.HWND
                    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
                    user32.GetAncestor.restype = wintypes.HWND
                    user32.WindowFromPoint(wintypes.POINT(rect.left + 401, rect.top + 360))
                points = [(401, 360), (394, 256), (50, 50)]
                results = []
                for x, y in points:
                    try:
                        element = desktop.from_point(rect.left + x, rect.top + y)
                        results.append({"xy": [x, y], "point_lookup": backend.controller._describe(element)})
                    except Exception:
                        results.append({"xy": [x, y], "error": traceback.format_exc()})
                return results
        except Exception:
            return {"error": traceback.format_exc()}
    result = {"main_thread": probe()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        result["worker_thread"] = executor.submit(probe).result(timeout=15)
    # Broker HTTP calls use a new thread for each request. Check that lifecycle
    # separately from a worker whose COM apartment remains alive.
    for n in range(3):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            result[f"replacement_worker_{n}"] = executor.submit(probe).result(timeout=15)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        result["observe_then_point"] = executor.submit(observed_probe).result(timeout=15)
    def mta_observed_probe():
        import pythoncom
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        try: return observed_probe()
        finally: pythoncom.CoUninitialize()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        result["mta_observe_then_point"] = executor.submit(mta_observed_probe).result(timeout=15)
    path = ROOT / "labs/desktop-bridge-20261020/uia-point-probe.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value.get("fresh_client") if isinstance(value, dict) else
                     ["error" in row for row in value] for key, value in result.items()}, indent=2))
finally:
    if fixture.poll() is None: fixture.terminate(); fixture.wait(timeout=10)
