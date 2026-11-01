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
        try:
            from core.low_spec_optimizer import configure_webview_environment
            configure_webview_environment()
        except Exception:
            pass
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
    if '--quartz-overlay' in sys.argv:
        from core.screen_overlay import run_overlay_child
        run_overlay_child()
        sys.exit(0)
    log("=" * 40)
    log("Quartz Entry Point Started")
    log(f"BASE_DIR: {BASE_DIR}")
    log(f"Frozen: {getattr(sys, 'frozen', False)}")

    from core.windows_prerequisites import ensure_webview2
    if not ensure_webview2():
        sys.exit(1)

    # Start the window immediately while the backend imports in parallel.
    backend_thread = start_backend_thread()
    start_gui()

    log("GUI closed. Joining backend thread cooperatively...")

    # If GUI closing hook did not stop the backend, ensure cooperative stop is called
    try:
        from main import get_ipc_server
        srv = get_ipc_server()
        if srv and srv._running:
            srv.stop()
    except Exception as exc:
        log(f"Notice: entry stop check: {exc}")

    # Observably join backend thread with bounded timeout
    backend_thread.join(timeout=8.0)

    from core.shutdown import get_shutdown_coordinator
    coordinator = get_shutdown_coordinator()
    receipt = coordinator.get_receipt()

    if backend_thread.is_alive():
        log(f"WARNING: Backend thread did not terminate within 8.0s timeout. Status: pending. Receipt: {receipt}")
    else:
        log(f"Backend thread joined successfully. Receipt: {receipt}")

    log("Quartz Exit")
