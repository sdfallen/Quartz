"""Window-scoped Windows UI Automation with expiring observation references."""

import json
import threading
import time
import uuid
from contextlib import contextmanager


class DesktopController:
    def __init__(self, desktop_factory=None, clock=time.monotonic):
        self._factory = desktop_factory
        self._clock = clock
        self._lock = threading.RLock()
        self._snapshots = {}

    @contextmanager
    def _desktop(self):
        if self._factory:
            yield self._factory()
            return
        import pythoncom
        # CoInitialize silently ignores RPC_E_CHANGED_MODE. Calling
        # CoUninitialize after that non-incrementing failure tears down an
        # existing apartment (e.g. comtypes' MTA), invalidating UIA proxies.
        # Preserve an existing apartment and balance only our successful init.
        initialized = False
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            initialized = True
        except pythoncom.com_error as exc:
            if exc.hresult != -2147417850:  # RPC_E_CHANGED_MODE
                raise
        try:
            from pywinauto import Desktop
            yield Desktop(backend="uia")
        finally:
            if initialized:
                pythoncom.CoUninitialize()

    @staticmethod
    def _describe(element):
        info = element.element_info
        native = getattr(info, "element", None)
        password = (bool(native.CurrentIsPassword) if native is not None
                    else bool(getattr(info, "is_password", False)))
        return {
            "name": str(info.name or "")[:300],
            "type": str(info.control_type or ""),
            "automation_id": str(info.automation_id or ""),
            "runtime_id": list(info.runtime_id or []),
            "enabled": bool(element.is_enabled()),
            "visible": bool(element.is_visible()),
            "password": password,
        }

    @staticmethod
    def _window(desktop, handle):
        if int(handle) <= 0:
            raise ValueError("Select a window handle from desktop_windows first")
        win = desktop.window(handle=int(handle)).wrapper_object()
        if not win.is_visible():
            raise ValueError("Window is not visible; restore it before inspecting")
        return win

    def windows(self):
        with self._lock, self._desktop() as desktop:
            result = []
            for win in desktop.windows():
                try:
                    if win.is_visible() and win.window_text():
                        result.append({"handle": int(win.handle),
                                       "title": win.window_text(),
                                       "process_id": win.process_id()})
                except Exception:
                    continue
            return {"windows": result[:80]}

    def _inspect(self, desktop, handle, query=""):
        win = self._window(desktop, handle)
        snapshot_id = uuid.uuid4().hex[:12]
        elements, references = [], {}
        # Limit both tree depth and returned data for large Chromium documents.
        for element in win.descendants(depth=7)[:800]:
            try:
                item = self._describe(element)
                if not item["visible"] or item["password"]:
                    continue
                if query and query.casefold() not in (
                        item["name"] + " " + item["type"]).casefold():
                    continue
                ref = str(len(elements) + 1)
                references[ref] = item.copy()
                public = {k: v for k, v in item.items()
                          if k not in {"runtime_id", "password"}}
                public["ref"] = ref
                elements.append(public)
                if len(elements) >= 120:
                    break
            except Exception:
                continue
        self._snapshots = {k: v for k, v in self._snapshots.items()
                           if self._clock() - v["at"] < 120}
        self._snapshots[snapshot_id] = {
            "at": self._clock(), "handle": int(handle),
            "pid": win.process_id(), "elements": references}
        return {"snapshot_id": snapshot_id, "handle": int(handle),
                "title": win.window_text(), "elements": elements,
                "note": "Use refs from this snapshot only; inspect again after each action."}

    def inspect(self, handle: int, query: str = ""):
        with self._lock, self._desktop() as desktop:
            return self._inspect(desktop, handle, query)

    def action(self, snapshot_id: str, ref: str, action: str, text: str = "", *, input_guard=None):
        if action not in {"invoke", "select", "expand", "collapse", "toggle", "set_text"}:
            raise ValueError("Unsupported UI action")
        with self._lock, self._desktop() as desktop:
            snapshot = self._snapshots.get(snapshot_id)
            if not snapshot or self._clock() - snapshot["at"] >= 120:
                raise ValueError("Observation expired; call desktop_inspect again")
            expected = snapshot["elements"].get(str(ref))
            if not expected:
                raise ValueError("Unknown element reference; inspect again")
            win = self._window(desktop, snapshot["handle"])
            if win.process_id() != snapshot["pid"]:
                raise ValueError("Window process changed; inspect again")
            matches = []
            for element in win.descendants(depth=7)[:800]:
                try:
                    current = self._describe(element)
                    if (current["runtime_id"] and current["runtime_id"] == expected["runtime_id"]
                            and current["name"] == expected["name"]
                            and current["type"] == expected["type"]):
                        matches.append(element)
                except Exception:
                    continue
            if len(matches) != 1:
                raise ValueError("UI element changed or disappeared; inspect again")
            element = matches[0]
            state = self._describe(element)
            if state["password"] or not state["enabled"] or not state["visible"]:
                raise ValueError("Element is protected, disabled or hidden")
            if action == "set_text" and state["type"] != "Edit":
                raise ValueError("set_text requires an Edit control")
            # A snapshot is single-use for actions, including failed attempts.
            self._snapshots.pop(snapshot_id, None)
            if input_guard is not None:
                input_guard()  # broker-owned input must never steal changed focus
            else:
                win.set_focus()
            if action == "set_text":
                element.set_edit_text(text)
            else:
                getattr(element, action)()
            time.sleep(.3)
            try:
                after = self._inspect(desktop, snapshot["handle"])
            except Exception as exc:
                after = {"window_unavailable": str(exc), "windows": self.windows()["windows"]}
            return {"action_executed": action, "target": expected["name"],
                    "verified_goal": False, "after": after,
                    "note": "Compare observed state with the user's goal before claiming completion."}


desktop_controller = DesktopController()


def desktop_windows() -> str:
    """List visible desktop windows and stable handles to select a target application."""
    return json.dumps(desktop_controller.windows(), ensure_ascii=False)


def desktop_inspect(handle: int, query: str = "") -> str:
    """Read a window's UI controls; returns expiring snapshot and element references."""
    return json.dumps(desktop_controller.inspect(handle, query), ensure_ascii=False)


def desktop_action(snapshot_id: str, ref: str, action: str, text: str = "") -> str:
    """Act on an observed control: invoke/select/expand/collapse/toggle/set_text; returns fresh UI."""
    return json.dumps(desktop_controller.action(snapshot_id, ref, action, text), ensure_ascii=False)
