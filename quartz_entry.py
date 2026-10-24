"""
quartz_entry.py
Main entry point for Quartz exe.
Starts backend + GUI together.
Shows in taskbar.
"""

import os
import sys
import threading
import time

# ── Base directory ────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(
        os.path.abspath(__file__))

# ── Add to path ───────────────────────────────────────────────
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)


def log(msg: str):
    """Write to log file."""
    try:
        log_path = os.path.join(
            BASE_DIR, "quartz_entry.log")
        ts = time.strftime("%H:%M:%S")
        with open(log_path, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def get_python() -> str:
    """Get the right Python executable."""
    if getattr(sys, "frozen", False):
        return sys.executable

    # Check venv
    venv_py = os.path.join(
        BASE_DIR, "venv",
        "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py

    return sys.executable


def start_backend_thread():
    """Load and run the backend without spawning the frozen exe again."""
    def run_backend():
        try:
            from main import main
            main(register_signals=False)
        except Exception as exc:
            log(f"Backend error: {exc}")

    thread = threading.Thread(
        target=run_backend, name="quartz-backend", daemon=True)
    thread.start()
    return thread


def start_gui():
    """Import and run the GUI directly."""
    log("Starting GUI...")
    try:
        from gui import QuartzUI
        app = QuartzUI()
        log("GUI created successfully")
        app.run()
    except Exception as e:
        log(f"GUI error: {e}")
        import traceback
        log(traceback.format_exc())

        # Show error to user
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Quartz Error",
                f"Failed to start GUI:\n{e}\n\n"
                f"Check quartz_entry.log for details."
            )
            root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    log("=" * 40)
    log("Quartz Entry Point Started")
    log(f"BASE_DIR: {BASE_DIR}")
    log(f"Frozen: {getattr(sys, 'frozen', False)}")

    # Start the window immediately while the backend imports in parallel.
    start_backend_thread()
    start_gui()

    log("Quartz Exit")

    # Belt-and-suspenders: guarantee this process
    # actually dies. Some background threads (e.g. the
    # speech-recognition listener, or pywebview on some
    # backends) aren't always daemon threads, which can
    # leave a python.exe hanging around in Task Manager
    # even after the window is gone. This forces an
    # immediate, unconditional exit.
    os._exit(0)
