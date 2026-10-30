"""Windows backend for Quartz's explicit desktop sessions.

No elevation, terminal execution, global screenshot, or arbitrary shell tool.
Games with protected saves need their dedicated orchestration adapter first.
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
import re
import time
import uuid
from functools import wraps

from core.desktop_control import DesktopController


DENIED_EXES = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
               "conhost.exe", "regedit.exe", "taskmgr.exe", "systemsettings.exe",
               "sechealthui.exe", "consent.exe", "credentialuibroker.exe", "logonui.exe",
               "lockapp.exe", "keepass.exe", "1password.exe", "bitwarden.exe",
               "codex.exe", "chatgpt.exe", "quartz.exe", "codex-computer-use.exe",
               "antigravity.exe"}
SENSITIVE = re.compile(r"password|parola|şifre|sign.in|oturum aç|authentication|verify.*identity|"
                       r"user account control|kullanıcı hesabı denetimi|windows security", re.I)
CRITICAL = re.compile(r"\b(delete|remove|overwrite|purchase|buy|pay|send|upload|save|sil|"
                      r"kaydet|üzerine yaz|satın al|öde|gönder|yükle|izin ver|allow|install)\b", re.I)
SAFE_KEYS = {
    "enter", "tab", "escape", "esc", "up", "down", "left", "right", "space",
    "backspace", "delete", "insert", "home", "end", "pageup", "pagedown",
    "capslock", "shift", "ctrl", "alt", "win",
    "volumeup", "volumedown", "volumemute", "playpause", "nexttrack", "prevtrack",
    "browserback", "browserforward", "browserrefresh",
    *{chr(c) for c in range(ord("a"), ord("z") + 1)},
    *{str(d) for d in range(10)},
    *{f"f{i}" for i in range(1, 13)},
}


def _uia_operation(method):
    """Keep COM alive across nested scans, point lookup and fresh observation.

    HTTP workers are short-lived. Per-helper init/uninit can invalidate UIA
    provider proxies between the safety scan and ElementFromPoint. One outer
    MTA scope keeps that entire operation in the same live apartment.
    """
    @wraps(method)
    def scoped(self, *args, **kwargs):
        with self.controller._desktop():
            return method(self, *args, **kwargs)
    return scoped


class NativeDesktopBackend:
    def __init__(self):
        self.controller = DesktopController()

    @staticmethod
    def _user32():
        import ctypes
        from ctypes import wintypes
        result = ctypes.windll.user32
        result.GetForegroundWindow.restype = wintypes.HWND
        return result

    @classmethod
    def ensure_input_desktop(cls):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            pt = wintypes.POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                return
            hinput = user32.OpenInputDesktop(0, False, 0x01FF)
            if hinput:
                user32.SetThreadDesktop(hinput)
                user32.CloseDesktop(hinput)
        except Exception:
            pass

    @classmethod
    def validate_input_session(cls):
        # A read-only preflight, never try to unlock/switch desktops or elevate.
        import ctypes
        from ctypes import wintypes
        point = wintypes.POINT()
        if not cls._user32().GetCursorPos(ctypes.byref(point)):
            cls.ensure_input_desktop()
            if not cls._user32().GetCursorPos(ctypes.byref(point)):
                if not cls._user32().GetTopWindow(0):
                    raise PermissionError("Interactive desktop input is unavailable (locked/disconnected/denied). Unlock the normal desktop yourself; no agent was started.")

    @_uia_operation
    def windows(self):
        result = []
        for window in self.controller.windows()["windows"]:
            try:
                target = self.identity(window["handle"])
                self.validate_target(target)
                result.append(target)
            except Exception:
                continue
        return result

    @_uia_operation
    def identity(self, handle):
        import psutil
        with self.controller._desktop() as desktop:
            win = self.controller._window(desktop, handle)
            proc = psutil.Process(win.process_id())
            rect = win.rectangle()
            return {"handle": int(handle), "pid": proc.pid, "started": proc.create_time(),
                    "exe": proc.exe(), "title": win.window_text(),
                    "rect": [rect.left, rect.top, rect.right, rect.bottom]}

    @staticmethod
    def validate_target(target):
        name = Path(target["exe"]).name.lower()
        if name in DENIED_EXES or SENSITIVE.search(target["title"]):
            raise PermissionError("Protected application/dialog is not a desktop-control target")
        if name in {"mb_warband.exe", "mb_warband_old.exe", "warband.exe"}:
            raise PermissionError("Warband input requires the Universal Modder save-protection adapter; not enabled by this generic bridge")
        if any(part in name for part in ("password", "security", "antimalware")):
            raise PermissionError("Protected application")

    @staticmethod
    def acquire_lease():
        # OS-released byte-range lock also excludes a second Quartz process.
        import msvcrt
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Quartz"
        root.mkdir(parents=True, exist_ok=True)
        stream = (root / "desktop-operator.lock").open("a+b")
        try:
            stream.seek(0)
            if not stream.read(1): stream.write(b"0"); stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return stream
        except Exception:
            stream.close()
            raise RuntimeError("Another Quartz instance owns desktop input")

    def _desk_name(self, hwnd):
        if not hwnd:
            return ""
        try:
            import ctypes
            from ctypes import wintypes
            u = self._user32()
            tid = u.GetWindowThreadProcessId(wintypes.HWND(hwnd), None)
            if not tid:
                return ""
            u.GetThreadDesktop.restype = wintypes.HANDLE
            u.GetThreadDesktop.argtypes = [wintypes.DWORD]
            hdesk = u.GetThreadDesktop(tid)
            if not hdesk:
                return ""
            buf = ctypes.create_unicode_buffer(256)
            size = wintypes.DWORD()
            if u.GetUserObjectInformationW(hdesk, 2, buf, ctypes.sizeof(buf), ctypes.byref(size)):
                return buf.value
        except Exception:
            pass
        return ""

    def _input_desktop_matches(self, target):
        """Reject a visible window whose session is behind the lock screen.

        UIA can still read the application's controls while ImageGrab returns
        pixels from Winlogon. A screenshot and its UIA tree must describe the
        same interactive desktop before either is offered as evidence.
        """
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        user32.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        handle = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if not handle:
            return False
        try:
            name = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            if not user32.GetUserObjectInformationW(handle, 2, name, ctypes.sizeof(name), ctypes.byref(needed)):
                return False
            target_name = self._desk_name(target["handle"])
            return bool(target_name and name.value and target_name == name.value)
        finally:
            user32.CloseDesktop(handle)

    def is_foreground(self, target):
        if not self._input_desktop_matches(target):
            return False
        user32 = self._user32()
        hwnd = target["handle"]
        fg = int(user32.GetForegroundWindow() or 0)
        if fg == hwnd:
            return True
        if fg != 0:
            if int(user32.GetAncestor(fg, 2) or 0) == hwnd:  # GA_ROOT
                return True
        return False

    def foreground_identity(self):
        """Diagnostic metadata only; never focus or act on this other window."""
        import ctypes
        from ctypes import wintypes
        handle = int(self._user32().GetForegroundWindow() or 0)
        pid = wintypes.DWORD()
        self._user32().GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self._user32().GetWindowThreadProcessId(wintypes.HWND(handle), ctypes.byref(pid))
        return {"handle": handle, "pid": pid.value}

    @_uia_operation
    def focus(self, target):
        hwnd = target["handle"]
        try:
            user32 = self._user32()
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        except Exception:
            pass
        with self.controller._desktop() as desktop:
            self.controller._window(desktop, hwnd).set_focus()
        # Windows can complete the single focus request asynchronously. Wait
        # briefly for its acknowledgement; never issue repeated focus requests
        # and never send input while the target is still in the background.
        deadline = time.monotonic() + .5
        while not self.is_foreground(target) and time.monotonic() < deadline:
            time.sleep(.02)

    def _safe_controls(self, target):
        with self.controller._desktop() as desktop:
            win = self.controller._window(desktop, target["handle"])
            for control in self.controller._get_descendants(win):
                try:
                    item = self.controller._describe(control)
                except Exception:
                    continue
                if item["visible"] and (item["password"] or SENSITIVE.search(item["name"])):
                    raise PermissionError("Authentication/private input appeared; hand off to user")

    def _before_input(self, target):
        self.validate_input_session()
        current = self.identity(target["handle"])
        if any(current.get(k) != target.get(k) for k in ("handle", "pid", "started", "exe", "rect")):
            raise PermissionError("Window identity or input geometry changed")
        self.validate_target(current)
        if not self.is_foreground(target): raise PermissionError("Target lost foreground before input")

    @_uia_operation
    def observe(self, target):
        if not self._input_desktop_matches(target):
            raise PermissionError("Target is not on the active input desktop")
        # Single unified traversal pass: extracts UI elements, detects keyboard focus,
        # and asserts password/sensitive control safety all in one fast scan.
        with self.controller._desktop() as desktop:
            win = self.controller._window(desktop, target["handle"])
            elements, references = [], {}
            snapshot_id = uuid.uuid4().hex[:12]
            focused_item = None
            for control in self.controller._get_descendants(win):
                try:
                    item = self.controller._describe(control)
                    if not item["visible"]:
                        continue
                    if item["password"] or SENSITIVE.search(item["name"]):
                        raise PermissionError("Authentication/private input appeared; hand off to user")
                    if focused_item is None and control.has_keyboard_focus():
                        focused_item = item.copy()
                    if len(elements) < 120:
                        ref = str(len(elements) + 1)
                        references[ref] = item.copy()
                        public = {k: v for k, v in item.items() if k not in {"runtime_id", "password"}}
                        public["ref"] = ref
                        elements.append(public)
                except PermissionError:
                    raise
                except Exception:
                    continue
            self.controller._snapshots = {k: v for k, v in self.controller._snapshots.items()
                                          if self.controller._clock() - v["at"] < 120}
            self.controller._snapshots[snapshot_id] = {
                "at": self.controller._clock(), "handle": int(target["handle"]),
                "pid": win.process_id(), "elements": references
            }
            state = {
                "snapshot_id": snapshot_id, "handle": int(target["handle"]),
                "title": win.window_text(), "elements": elements,
                "focused": focused_item,
                "note": "Use refs from this snapshot only; inspect again after each action."
            }
        # Only capture a foreground target. No hidden whole-desktop capture.
        if not self.is_foreground(target):
            return {"ui": state, "image_available": False, "note": "Focus once to obtain a bounded screenshot"}
        from PIL import ImageGrab
        left, top, right, bottom = target["rect"]
        if right <= left or bottom <= top: raise ValueError("Invalid window bounds")
        try:
            image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        except Exception:
            import ctypes
            from ctypes import wintypes
            from PIL import Image
            user32 = self._user32()
            gdi32 = ctypes.windll.gdi32
            hwnd = target["handle"]
            w, h = right - left, bottom - top
            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            gdi32.SelectObject(hdc_mem, hbm)
            user32.PrintWindow(hwnd, hdc_mem, 2)
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG), ('biHeight', wintypes.LONG),
                            ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                            ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG), ('biYPelsPerMeter', wintypes.LONG),
                            ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)]
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)
            image = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB')
            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)
        if not self.is_foreground(target):
            raise PermissionError("Input desktop or foreground changed during capture")
        if image.size != (right - left, bottom - top):
            raise PermissionError("Screenshot pixels and target window geometry disagree")
        output = io.BytesIO()
        image.save(output, format="PNG", compress_level=1)
        return {"ui": state, "width": image.width, "height": image.height,
                "image_base64": base64.b64encode(output.getvalue()).decode(),
                "capture": "foreground-window-crop; GPU compatibility not guaranteed"}

    @_uia_operation
    def act(self, target, observation, args):
        if not self.is_foreground(target): raise PermissionError("Target lost foreground")
        self._safe_controls(target)
        action = args.get("action")
        if action == "ui":
            ref = str(args.get("ref", ""))
            item = next((i for i in observation["ui"]["elements"] if i["ref"] == ref), None)
            if not item or CRITICAL.search(item["name"]):
                raise PermissionError("Unknown or consequential UI action; user confirmation required outside the agent")
            operation = args.get("ui_action")
            if operation not in {"invoke", "select", "expand", "collapse"}:
                raise ValueError("Unsupported UI operation")
            self.controller.action(observation["ui"]["snapshot_id"], ref, operation,
                                   input_guard=lambda: self._before_input(target))
            return
        if action == "text":
            text = args.get("text", "")
            if not isinstance(text, str) or len(text) > 2000 or any(c in text for c in "\r\n\x00"):
                raise ValueError("Only bounded literal single-line text is allowed")
            with self.controller._desktop() as desktop:
                win = self.controller._window(desktop, target["handle"])
                # Never type into a guessed surface or another process.
                focused = [c for c in win.descendants(depth=7)[:800] if c.has_keyboard_focus()]
                if len(focused) != 1: raise PermissionError("No unique focused edit control")
                control = focused[0]
                item = self.controller._describe(control)
                if (control.process_id() != target["pid"] or item["type"] != "Edit" or item["password"]):
                    raise PermissionError("Observe and focus a normal Edit control before typing")
                old_focus = observation["ui"].get("focused") or {}
                if item["runtime_id"] != old_focus.get("runtime_id"):
                    raise PermissionError("Keyboard focus changed since observation")
                if CRITICAL.search(win.window_text()):
                    raise PermissionError("File/critical dialog requires a separate user decision")
                self._before_input(target)
                try:
                    control.set_edit_text(text)
                except Exception:
                    import pyperclip
                    import pyautogui
                    pyautogui.FAILSAFE = False
                    pyperclip.copy(text)
                    pyautogui.hotkey("ctrl", "v")
            return
        import pyautogui
        pyautogui.FAILSAFE = False
        if action == "click":
            x, y = args.get("x"), args.get("y")
            if (type(x) is not int or type(y) is not int or not observation.get("image_base64") or
                    not 0 <= x < observation["width"] or not 0 <= y < observation["height"]):
                raise ValueError("Click must reference the fresh bounded screenshot")
            left, top, right, bottom = target["rect"]
            if (observation["width"], observation["height"]) != (right - left, bottom - top):
                raise PermissionError("Screenshot and target coordinates use different geometry")
            import ctypes
            from ctypes import wintypes
            point = wintypes.POINT(left + x, top + y)
            user32 = self._user32()
            user32.WindowFromPoint.argtypes = [wintypes.POINT]
            user32.WindowFromPoint.restype = wintypes.HWND
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            hit = user32.WindowFromPoint(point)
            ancestor = int(user32.GetAncestor(hit, 2) or 0)
            if ancestor != target["handle"] and hit != target["handle"]:
                raise PermissionError("Point is outside or covered by another window")
            # Block consequential named controls even for coordinate actions.
            with self.controller._desktop() as desktop:
                item = self.controller._describe(desktop.from_point(left + x, top + y))
                if item["password"] or SENSITIVE.search(item["name"]):
                    raise PermissionError("Private control requires user handoff")
                if CRITICAL.search(item["name"]): raise PermissionError("Consequential control requires user handoff")
            self._before_input(target)
            pyautogui.click(left + x, top + y)
        elif action in {"key", "hold"}:
            key = args.get("key")
            if key not in SAFE_KEYS: raise PermissionError("Key/chord is outside the bounded operator profile")
            with self.controller._desktop() as desktop:
                win = self.controller._window(desktop, target["handle"])
                focused = [c for c in win.descendants(depth=7)[:800] if c.has_keyboard_focus()]
                if any(CRITICAL.search(self.controller._describe(c)["name"]) for c in focused):
                    raise PermissionError("Focused consequential control requires user handoff")
            self._before_input(target)
            if action == "key": pyautogui.press(key)
            else:
                duration = args.get("seconds", 0.1)
                if type(duration) not in {int, float} or not 0 < duration <= 1:
                    raise ValueError("Hold duration must be 0..1 seconds")
                pyautogui.keyDown(key)
                try:
                    deadline = time.monotonic() + duration
                    while time.monotonic() < deadline:
                        if not self.is_foreground(target): raise PermissionError("Foreground changed during key hold")
                        time.sleep(.02)
                finally: pyautogui.keyUp(key)
        else:
            raise ValueError("Unsupported action")
