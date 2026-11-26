"""One SpeS per Windows session (live 25 Nov 2026).

Starting Quartz.exe a second time started a second backend on the same IPC port (the server
binds with SO_REUSEADDR, which Windows lets two processes share). The window then talked to
either backend: no projects, "Çevrimdışı", a conversation from nowhere. Now the second start
brings the running SpeS window to the front and exits before any backend or window starts.
"""
from __future__ import annotations

import sys

MUTEX_NAME = "Local\\SpeS-Quartz-Main"
ERROR_ALREADY_EXISTS = 183
WINDOW_TITLE = "SpeS"

_handle = None  # held for the life of the process; Windows frees it when the process ends


def acquire(name: str = MUTEX_NAME, *, kernel32=None, last_error=None) -> bool:
    """True when this process is the only SpeS; False when another one already runs.

    Off Windows, or if the mutex cannot be created at all, SpeS starts as before.
    """
    global _handle
    try:
        if kernel32 is None:
            if sys.platform != "win32":
                return True
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            # Fides 26 Nov (F7): HANDLE is pointer-sized; the default c_int would cut it.
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            last_error = ctypes.get_last_error
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return True
        if last_error is not None and last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        _handle = handle
        return True
    except Exception:
        return True


def show_running_window(title: str = WINDOW_TITLE, *, user32=None) -> bool:
    """Bring the running SpeS window forward (restored if minimised)."""
    try:
        if user32 is None:
            if sys.platform != "win32":
                return False
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            user32.FindWindowW.restype = wintypes.HWND
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.ShowWindow.restype = wintypes.BOOL
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            user32.SetForegroundWindow.restype = wintypes.BOOL
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False
