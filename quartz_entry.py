"""
quartz_entry.py
Main entry point for SpeS exe.
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
        target=run_backend, name="quartz-backend", daemon=False)
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
        return app
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
                "SpeS Error",
                f"Failed to start GUI:\n{e}\n\n"
                f"Check quartz_entry.log for details."
            )
            root.destroy()
        except Exception:
            pass


def finish_backend(backend_thread, app=None):
    """Keep ownership until GUI services and backend have actually settled.

    Bounded waits refresh receipts; they never convert pending into success.
    There is no PID-based kill or unconditional process exit here.
    """
    from main import stop_backend
    from core.application_services import overall_status
    import json
    first = True
    while True:
        try:
            gui_receipt = app._api._services.shutdown() if app is not None else {'status':'confirmed'}
        except Exception as exc:
            gui_receipt = {'status':'failed', 'error_type':type(exc).__name__}
        try:
            backend_receipt = stop_backend()
        except Exception as exc:
            backend_receipt = {'status':'failed', 'error_type':type(exc).__name__}
        backend_thread.join(timeout=.2)
        parts = {'gui':gui_receipt['status'], 'backend':backend_receipt['status'],
                 'backend_thread':'pending' if backend_thread.is_alive() else 'confirmed'}
        receipt = {'status':overall_status(parts), 'components':parts,
                   'backend':backend_receipt, 'gui':gui_receipt}
        if receipt['status'] == 'confirmed':
            log('Shutdown receipt: '+json.dumps(receipt, ensure_ascii=False))
            return receipt
        if first:
            log('Shutdown remains pending; owned workers retained. '+json.dumps(receipt, ensure_ascii=False))
            first = False
        time.sleep(.2)


if __name__ == "__main__":
    if '--quartz-overlay' in sys.argv:
        from core.screen_overlay import run_overlay_child
        run_overlay_child()
        sys.exit(0)
    log("=" * 40)
    log("SpeS Entry Point Started")
    log(f"BASE_DIR: {BASE_DIR}")
    log(f"Frozen: {getattr(sys, 'frozen', False)}")

    from core.windows_prerequisites import ensure_webview2
    if not ensure_webview2():
        sys.exit(1)

    # Start the window immediately while the backend imports in parallel.
    backend_thread = start_backend_thread()
    app = start_gui()
    finish_backend(backend_thread, app)
    log("SpeS Exit")
