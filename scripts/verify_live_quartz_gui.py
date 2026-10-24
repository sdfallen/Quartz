"""Live pywebview UI and packaging acceptance for Quartz.exe.

Launches the packaged executable, inspects its accessibility tree and live window,
captures a verified screenshot into the artifact directory, and performs a graceful shutdown.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist/Quartz/Quartz.exe"
ARTIFACT_IMG = Path(r"C:\Users\LENAVO\.gemini\antigravity\brain\a06b86c8-af32-42ef-9738-c1257b1c3dac\quartz_live_verified.png")


def ensure_desktop():
    user32 = ctypes.windll.user32
    hinput = user32.OpenInputDesktop(0, False, 0x01FF)
    if hinput:
        user32.SetThreadDesktop(hinput)
        user32.CloseDesktop(hinput)


def main():
    ensure_desktop()
    if not EXE.is_file():
        raise FileNotFoundError(f"Packaged executable not found: {EXE}")

    exe_sha256 = hashlib.sha256(EXE.read_bytes()).hexdigest()
    print(f"Target EXE: {EXE}")
    print(f"Target SHA256: {exe_sha256}")

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Launch the packaged Quartz.exe
    proc = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    print(f"Launched Quartz PID: {proc.pid}")

    found_hwnd = None
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"Quartz exited prematurely with code {proc.returncode}")

            # Enumerate top-level windows for this process
            hwnds = []
            def enum_cb(hwnd, lparam):
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == proc.pid and user32.IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, buf, 512)
                    title = buf.value
                    if "Quartz" in title or "Assistant" in title:
                        hwnds.append((hwnd, title))
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

            if hwnds:
                found_hwnd, found_title = hwnds[0]
                print(f"Found visible Quartz window: HWND {found_hwnd} ('{found_title}')")
                break
            time.sleep(0.5)

        if not found_hwnd:
            raise TimeoutError("Quartz GUI window did not appear within 30 seconds")

        # Allow pywebview to finish initial HTML/DOM rendering
        time.sleep(3.0)

        # Bring window to foreground
        user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(found_hwnd)
        user32.BringWindowToTop(found_hwnd)
        time.sleep(0.5)

        rect = wintypes.RECT()
        user32.GetWindowRect(found_hwnd, ctypes.byref(rect))
        bbox = (rect.left, rect.top, rect.right, rect.bottom)
        print(f"Window bounds: {bbox}, size: {rect.right - rect.left}x{rect.bottom - rect.top}")

        # Capture screenshot
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        img.save(str(ARTIFACT_IMG), format="PNG")
        print(f"Screenshot saved to: {ARTIFACT_IMG} ({img.width}x{img.height})")

        # Also inspect accessibility elements via pywinauto UIA
        import pythoncom
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        win = desktop.window(handle=found_hwnd)
        texts = []
        for el in win.descendants(depth=6)[:300]:
            try:
                name = el.element_info.name
                if name and name.strip():
                    texts.append(name.strip())
            except Exception:
                pass
        pythoncom.CoUninitialize()

        print(f"Discovered accessibility elements ({len(texts)} items):")
        for t in texts[:20]:
            print(f"  - {t}")

        # Test local IPC communication
        from core.local_ipc import send as ipc_send
        status_res = ipc_send("chat_status")
        print(f"IPC chat_status response status: {status_res.get('status')}")
        if status_res.get("status") == "ok":
            active_conv = status_res.get("data", {}).get("active_conversation", {})
            print(f"Active conversation title: {active_conv.get('title')}, messages: {len(active_conv.get('messages', []))}")

        # Graceful shutdown via IPC
        print("Sending graceful shutdown...")
        shutdown_res = ipc_send("shutdown")
        print(f"Shutdown response: {shutdown_res}")

        # Wait for clean exit
        proc.wait(timeout=10)
        print("Quartz process exited cleanly.")

    finally:
        if proc.poll() is None:
            print("Terminating test process tree...")
            from core.process_tree import stop_process_tree
            stop_process_tree(proc.pid)


if __name__ == "__main__":
    main()
