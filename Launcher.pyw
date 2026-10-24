"""
launcher.pyw
Starts JARVIS backend + GUI silently.
No console window appears.
"""

import subprocess
import sys
import os
import time
import socket

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__))

# Use venv Python if it exists
VENV_PY = os.path.join(
    BASE_DIR, "venv",
    "Scripts", "python.exe")

PYTHON  = (
    VENV_PY if os.path.exists(VENV_PY)
    else sys.executable)

MAIN_PY = os.path.join(BASE_DIR, "main.py")
GUI_PY  = os.path.join(BASE_DIR, "gui.py")


def log(msg: str):
    try:
        path = os.path.join(
            BASE_DIR, "launcher.log")
        ts = time.strftime("%H:%M:%S")
        with open(path, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def start_backend():
    log(f"Starting backend...")
    log(f"Python : {PYTHON}")
    log(f"main.py: {MAIN_PY}")
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= (
            subprocess.STARTF_USESHOWWINDOW)
        info.wShowWindow = 0
        proc = subprocess.Popen(
            [PYTHON, MAIN_PY],
            startupinfo=info,
            creationflags=(
                subprocess.CREATE_NO_WINDOW),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=BASE_DIR,
        )
        log(f"Backend PID: {proc.pid}")
        return proc
    except Exception as e:
        log(f"Backend error: {e}")
    return None


def wait_for_backend(timeout=20) -> bool:
    log("Waiting for backend socket...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(
                    ("127.0.0.1", 55123),
                    timeout=1):
                log("Backend ready!")
                return True
        except Exception:
            time.sleep(0.5)
    log("Backend wait timeout!")
    return False


def start_gui():
    log("Starting GUI...")
    try:
        proc = subprocess.Popen(
            [PYTHON, GUI_PY],
            cwd=BASE_DIR,
        )
        log(f"GUI PID: {proc.pid}")
    except Exception as e:
        log(f"GUI error: {e}")


if __name__ == "__main__":
    log("=" * 35)
    log("JARVIS Launcher started")

    # Show the window immediately. The GUI already polls backend health,
    # so loading AI, vision and MCP modules no longer blocks first paint.
    start_backend()
    start_gui()
    log("Launcher done; backend continues loading in parallel")
