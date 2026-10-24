import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.desktop_control import DesktopController


class COMScopeTests(unittest.TestCase):
    class COMError(Exception):
        def __init__(self, hresult): self.hresult = hresult

    def modules(self, error=None):
        com = SimpleNamespace(COINIT_MULTITHREADED=0, com_error=self.COMError,
                              CoInitializeEx=MagicMock(side_effect=error),
                              CoUninitialize=MagicMock())
        uia = SimpleNamespace(Desktop=MagicMock(return_value="desktop"))
        return com, uia

    def test_successful_mta_scope_is_balanced(self):
        com, uia = self.modules()
        with patch.dict("sys.modules", {"pythoncom": com, "pywinauto": uia}):
            with DesktopController()._desktop() as desktop:
                self.assertEqual(desktop, "desktop")
                com.CoUninitialize.assert_not_called()
        com.CoInitializeEx.assert_called_once_with(0)
        com.CoUninitialize.assert_called_once()

    def test_changed_mode_keeps_existing_apartment_alive(self):
        com, uia = self.modules(self.COMError(-2147417850))
        with patch.dict("sys.modules", {"pythoncom": com, "pywinauto": uia}):
            with DesktopController()._desktop(): pass
        com.CoUninitialize.assert_not_called()

    def test_other_com_failure_is_not_swallowed(self):
        com, uia = self.modules(self.COMError(-1))
        with patch.dict("sys.modules", {"pythoncom": com, "pywinauto": uia}):
            with self.assertRaises(self.COMError):
                with DesktopController()._desktop(): pass
        uia.Desktop.assert_not_called()
        com.CoUninitialize.assert_not_called()

    def test_exception_still_balances_successful_init(self):
        com, uia = self.modules()
        with patch.dict("sys.modules", {"pythoncom": com, "pywinauto": uia}):
            with self.assertRaises(ValueError):
                with DesktopController()._desktop(): raise ValueError("test")
        com.CoUninitialize.assert_called_once()


class Control:
    def __init__(self, name="Input", kind="Edit", rid=1):
        self.element_info = SimpleNamespace(
            name=name, control_type=kind, automation_id="field",
            runtime_id=[rid], is_password=False)
        self.value = ""

    def is_enabled(self): return True
    def is_visible(self): return True
    def set_edit_text(self, text): self.value = text


class Window:
    handle = 123
    def __init__(self): self.controls = [Control()]
    def is_visible(self): return True
    def process_id(self): return 42
    def window_text(self): return "Quartz Test Window"
    def descendants(self, **kwargs): return self.controls
    def wrapper_object(self): return self
    def set_focus(self): pass


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.window = Window()
        self.time = 0
        desktop = SimpleNamespace(window=lambda **_: self.window,
                                  windows=lambda: [self.window])
        self.controller = DesktopController(lambda: desktop, lambda: self.time)

    def test_action_returns_new_observation_and_consumes_old_reference(self):
        before = self.controller.inspect(123)
        result = self.controller.action(before["snapshot_id"], "1", "set_text", "Merhaba")
        self.assertEqual(self.window.controls[0].value, "Merhaba")
        self.assertNotEqual(before["snapshot_id"], result["after"]["snapshot_id"])
        self.assertFalse(result["verified_goal"])
        with self.assertRaises(ValueError):
            self.controller.action(before["snapshot_id"], "1", "set_text", "again")

    def test_changed_control_is_not_acted_on(self):
        before = self.controller.inspect(123)
        self.window.controls = [Control("Different", rid=2)]
        with self.assertRaises(ValueError):
            self.controller.action(before["snapshot_id"], "1", "set_text", "wrong")
        self.assertEqual(self.window.controls[0].value, "")

    def test_expired_observation_is_rejected(self):
        before = self.controller.inspect(123)
        self.time = 121
        with self.assertRaises(ValueError):
            self.controller.action(before["snapshot_id"], "1", "set_text", "stale")

    def test_password_controls_are_not_exposed(self):
        self.window.controls[0].element_info.is_password = True
        self.assertEqual(self.controller.inspect(123)["elements"], [])

    def test_native_uia_password_property_is_respected(self):
        self.window.controls[0].element_info.element = SimpleNamespace(CurrentIsPassword=True)
        self.assertEqual(self.controller.inspect(123)["elements"], [])

    def test_recycled_window_handle_is_rejected(self):
        before = self.controller.inspect(123)
        self.window.process_id = lambda: 99
        with self.assertRaises(ValueError):
            self.controller.action(before["snapshot_id"], "1", "set_text", "wrong")
