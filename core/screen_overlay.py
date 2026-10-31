"""Native Windows top-left 'Görevi Durdur' HUD and subtle screen-edge glow effect.

When Quartz / Agents control the computer screen:
1. Displays a sleek, always-on-top control capsule at the top-left of the primary
   monitor with an active status indicator and a '⏹ GÖREVİ DURDUR' button.
2. Renders a subtle, click-through (WS_EX_TRANSPARENT) breathing cyan border along
   the edges of the screen to indicate that Quartz has active screen control.
3. Never steals keyboard focus (WS_EX_NOACTIVATE) and never intercepts mouse clicks
   outside the 'Görevi Durdur' button itself.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import json
import subprocess
from pathlib import Path
from typing import Callable


class ScreenControlOverlay:
    """Thread-safe native Windows HUD + screen-edge glow controller."""

    def __init__(self):
        self._lock = threading.RLock()
        self._active = False
        self._agent_label = "QUARTZ"
        self._stop_callback: Callable[[], None] | None = None
        self._thread: threading.Thread | None = None
        self._close_event = threading.Event()
        self._process = None

    def show(self, agent_label: str = "QUARTZ", on_stop: Callable[[], None] | None = None, *, force: bool = False):
        if not force and ("unittest" in sys.modules or os.environ.get("QUARTZ_DISABLE_OVERLAY") == "1"):
            return
        with self._lock:
            self._agent_label = str(agent_label or "QUARTZ").upper()[:80]
            if on_stop is not None:
                self._stop_callback = on_stop
            if self._active and self._process and self._process.poll() is None:
                self._send({'command':'label','label':self._agent_label})
                return
            self._active = True
            self._close_event.clear()
            command = ([sys.executable, '--quartz-overlay'] if getattr(sys,'frozen',False) else
                       [sys.executable, str(Path(__file__).resolve().parents[1]/'quartz_entry.py'), '--quartz-overlay'])
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self._process = process
                self._send({'command':'show','label':self._agent_label})
            except Exception:
                self._active = False
                self._safe_invoke_stop(self._stop_callback or (lambda:None))
                return
            self._thread = threading.Thread(
                target=self._read_child, args=(process,),
                name="quartz-screen-overlay",
                daemon=True,
            )
            self._thread.start()

    def _send(self, message):
        if self._process and self._process.stdin:
            try:
                self._process.stdin.write(json.dumps(message,ensure_ascii=True)+'\n')
                self._process.stdin.flush()
            except (OSError,ValueError):
                pass

    def _read_child(self, process):
        try:
            for line in process.stdout:
                if line.strip() == 'STOP':
                    with self._lock:
                        if self._process is not process: return
                    self._trigger_stop()
                    return
        finally:
            callback = None
            with self._lock:
                if self._process is process:
                    if self._active: callback = self._stop_callback
                    self._active = False
                    self._process = None
            if process.stdout: process.stdout.close()
            if process.stdin:
                try: process.stdin.close()
                except OSError: pass
            process.wait()
            if callback: self._safe_invoke_stop(callback)

    def update_label(self, agent_label: str):
        with self._lock:
            self._agent_label = str(agent_label or "QUARTZ").upper()[:80]
            self._send({'command':'label','label':self._agent_label})

    def hide(self):
        with self._lock:
            self._active = False
            self._close_event.set()
            self._send({'command':'hide'})
            if self._process and self._process.stdin:
                try: self._process.stdin.close()
                except OSError: pass
            self._process = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def _trigger_stop(self):
        cb = None
        with self._lock:
            self._active = False
            self._close_event.set()
            cb = self._stop_callback
            self._send({'command':'hide'})
        if cb is not None:
            threading.Thread(target=self._safe_invoke_stop, args=(cb,), daemon=True).start()

    @staticmethod
    def _safe_invoke_stop(cb: Callable[[], None]):
        try:
            cb()
        except Exception:
            pass

    @staticmethod
    def _apply_win32_styles(hwnd: int, *, click_through: bool = False):
        if os.name != "nt" or not hwnd:
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOPMOST = 0x00000008
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000

            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            if click_through:
                style |= WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            # Keep topmost without activating (SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE = 0x0013)
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0013)
        except Exception:
            pass

    def _run_tk_loop(self):
        try:
            import tkinter as tk
        except Exception:
            with self._lock:
                self._active = False
            return

        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()

            # 1. Subtle 4-edge glowing frame (click-through, 3px thick)
            edge_thickness = 3
            edge_color = "#34eaff"
            edges: list[tk.Toplevel] = []
            geometries = [
                f"{screen_w}x{edge_thickness}+0+0",  # Top
                f"{screen_w}x{edge_thickness}+0+{screen_h - edge_thickness}",  # Bottom
                f"{edge_thickness}x{screen_h}+0+0",  # Left
                f"{edge_thickness}x{screen_h}+{screen_w - edge_thickness}+0",  # Right
            ]
            for geom in geometries:
                bar = tk.Toplevel(root)
                bar.overrideredirect(True)
                bar.attributes("-topmost", True)
                bar.attributes("-alpha", 0.62)
                bar.configure(bg=edge_color)
                bar.geometry(geom)
                bar.update_idletasks()
                self._apply_win32_styles(bar.winfo_id(), click_through=True)
                edges.append(bar)

            # 2. Top-Left "Görevi Durdur" HUD Capsule (x=18, y=18)
            hud = tk.Toplevel(root)
            hud.title("Quartz Ekran Kontrolü")
            hud.overrideredirect(True)
            hud.attributes("-topmost", True)
            hud.attributes("-alpha", 0.94)
            hud.configure(bg="#34eaff")  # Outer 1px neon cyan border
            hud.geometry("356x48+18+18")

            inner = tk.Frame(hud, bg="#06121c", highlightthickness=0)
            inner.pack(fill="both", expand=True, padx=1, pady=1)

            dot_label = tk.Label(
                inner,
                text="◉",
                fg="#34eaff",
                bg="#06121c",
                font=("Segoe UI", 13, "bold"),
            )
            dot_label.pack(side="left", padx=(10, 6))

            text_frame = tk.Frame(inner, bg="#06121c")
            text_frame.pack(side="left", fill="y", pady=5)

            title_lbl = tk.Label(
                text_frame,
                text="QUARTZ KONTROLDE",
                fg="#34eaff",
                bg="#06121c",
                font=("Segoe UI", 8, "bold"),
                anchor="w",
            )
            title_lbl.pack(fill="x")

            sub_lbl = tk.Label(
                text_frame,
                text=f"Ajan: {self._agent_label}",
                fg="#b8d9eb",
                bg="#06121c",
                font=("Segoe UI", 8),
                anchor="w",
            )
            sub_lbl.pack(fill="x")

            stop_btn = tk.Button(
                inner,
                text="⏹ GÖREVİ DURDUR",
                fg="#ffffff",
                bg="#e62e50",
                activeforeground="#ffffff",
                activebackground="#ff4769",
                relief="flat",
                bd=0,
                padx=12,
                pady=5,
                cursor="hand2",
                font=("Segoe UI", 9, "bold"),
                command=self._trigger_stop,
            )
            stop_btn.pack(side="right", padx=8, pady=7)

            def on_enter(_):
                stop_btn.configure(bg="#ff4769")

            def on_leave(_):
                stop_btn.configure(bg="#e62e50")

            stop_btn.bind("<Enter>", on_enter)
            stop_btn.bind("<Leave>", on_leave)

            hud.update_idletasks()
            self._apply_win32_styles(hud.winfo_id(), click_through=False)

            step = 0

            def tick():
                nonlocal step
                if self._close_event.is_set() or not self._active:
                    try:
                        root.destroy()
                    except Exception:
                        pass
                    return
                step += 1
                # Smooth breathing effect on screen edges and status orb
                phase = (step % 20) / 20.0
                tri = phase * 2.0 if phase <= 0.5 else (1.0 - phase) * 2.0
                alpha = 0.35 + 0.40 * tri
                for bar in edges:
                    try:
                        bar.attributes("-alpha", alpha)
                        bar.lift()
                    except Exception:
                        pass
                try:
                    dot_label.configure(fg="#34eaff" if step % 10 < 6 else "#7c6cff")
                    sub_lbl.configure(text=f"Ajan: {self._agent_label}")
                    hud.lift()
                except Exception:
                    pass
                root.after(90, tick)

            root.after(90, tick)
            root.mainloop()
        except Exception:
            pass
        finally:
            with self._lock:
                self._active = False
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass


overlay_manager = ScreenControlOverlay()


def run_overlay_child():
    """Own Tcl exclusively on this child process's main thread.

    EOF is a lease end: a dead parent cannot leave an active HUD behind.
    Only bounded label/hide messages are accepted, never commands or paths.
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Overlay must own the main thread')
    # PyInstaller's windowed bootloader sets sys.std* to None, even when
    # CreateProcess inherited pipe handles. Reopen only those inherited pipes.
    if os.name == 'nt' and (sys.stdin is None or sys.stdout is None):
        import ctypes
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        for name, handle_id, mode, flags in (
            ('stdin', -10, 'r', os.O_RDONLY), ('stdout', -11, 'w', os.O_WRONLY)):
            if getattr(sys,name) is not None: continue
            handle = kernel.GetStdHandle(handle_id & 0xffffffff)
            if not handle or handle == ctypes.c_void_p(-1).value: return
            fd = msvcrt.open_osfhandle(handle, flags | os.O_BINARY)
            setattr(sys, name, os.fdopen(fd, mode, encoding='utf-8', buffering=1))
    if sys.stdin is None or sys.stdout is None: return
    first = sys.stdin.readline(4097)
    if len(first)>4096: return
    try: data=json.loads(first)
    except ValueError: return
    if not isinstance(data,dict) or data.get('command')!='show': return
    hud=ScreenControlOverlay()
    hud._active=True
    hud._agent_label=str(data.get('label','QUARTZ'))[:80]
    hud._stop_callback=lambda: print('STOP',flush=True)
    def listen():
        try:
            while True:
                line=sys.stdin.readline(4097)
                if not line or len(line)>4096: break
                try: message=json.loads(line)
                except ValueError: break
                if not isinstance(message,dict): break
                if message.get('command')=='hide': break
                if message.get('command')=='label':
                    with hud._lock: hud._agent_label=str(message.get('label','QUARTZ'))[:80]
        finally: hud.hide()
    threading.Thread(target=listen,daemon=True,name='overlay-input').start()
    hud._run_tk_loop()
