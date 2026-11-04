import unittest
from unittest.mock import patch

import gui


class FakeWindow:
    def __init__(self, width=None, height=None, x=None, y=None):
        self.sizes = []
        self.moves = []
        self.width = width
        self.height = height
        self.x = x
        self.y = y

    def resize(self, width, height):
        self.sizes.append((width, height))
        if self.width is not None:
            self.width = width
        if self.height is not None:
            self.height = height

    def move(self, x, y):
        self.moves.append((x, y))
        if self.x is not None:
            self.x = x
        if self.y is not None:
            self.y = y


class CompactWindowTests(unittest.TestCase):
    def test_voice_system_is_deferred_until_requested(self):
        api = gui.Api()
        self.assertIsNone(api._voice_instance)

    def test_compact_and_full_sizes_are_applied(self):
        api = gui.Api.__new__(gui.Api)
        api._compact = False
        window = FakeWindow()
        with patch.object(gui.webview, "windows", [window]),                 patch("core.ui_window.work_area", return_value=(0, 0, 1920, 1040)):
            self.assertEqual(api.set_compact(True), {"compact": True})
            self.assertEqual(api.set_compact(False), {"compact": False})
        self.assertEqual(window.sizes, [(390, 520), (1160, 740)])
        self.assertEqual(window.moves, [(380, 150)])

    def test_returning_from_compact_fits_a_small_screen(self):
        from core.ui_window import full_window_rect
        width, height, x, y = full_window_rect((0, 0, 1366, 728))
        self.assertLessEqual(x + width, 1366)
        self.assertLessEqual(y + height, 728)

    def test_creator_signature_is_present_in_both_layouts(self):
        self.assertIn("DESIGNED &amp; ENGINEERED BY", gui._HTML)
        self.assertIn("CREATED BY <strong>ALI MEHDI</strong>", gui._HTML)
        self.assertIn('class="signature-mark"', gui._HTML)

    def test_mobile_access_card_has_copy_button(self):
        self.assertIn("copy_mobile_token", gui._HTML)
        self.assertIn("ANAHTARI KOPYALA", gui._HTML)
        self.assertIn("mobile-access-card", gui._HTML)

    def test_quartz_mode_quick_action_is_present(self):
        self.assertEqual(gui._QUICK_ACTIONS["quartz_mode"], "Quartz Mode")
        self.assertIn('data-action="quartz_mode"', gui._HTML)

    def test_operator_controls_are_present(self):
        self.assertIn('id="btnAdvisor"', gui._HTML)
        self.assertIn('id="operationStatus"', gui._HTML)
        self.assertIn('id="btnLearnOperation"', gui._HTML)
        self.assertIn('id="btnFinishOperation"', gui._HTML)

    def test_agent_center_matches_existing_ui_and_exposes_safe_controls(self):
        self.assertIn('id="btnAgentCenter"', gui._HTML)
        self.assertIn('id="agentOverlay"', gui._HTML)
        self.assertIn('id="agentPrompt"', gui._HTML)
        self.assertIn('id="agentWrite"', gui._HTML)
        self.assertIn('id="agentProvider"', gui._HTML)
        self.assertIn('value="antigravity"', gui._HTML)
        self.assertIn('value="collaboration"', gui._HTML)
        self.assertIn('id="confirmModal"', gui._HTML)
        self.assertIn('requestUiConfirm(', gui._HTML)
        self.assertNotIn('window.confirm(', gui._HTML)

    def test_toggle_maximize_and_restore_button(self):
        self.assertIn('id="btnWinMaximize"', gui._HTML)
        api = gui.Api.__new__(gui.Api)
        api._compact = False
        api._maximized = False
        api._restore_rect = None
        window = FakeWindow(width=980, height=640, x=120, y=90)
        with patch.object(gui.webview, "windows", [window]), \
                patch("core.ui_window.work_area", return_value=(10, 20, 1910, 1020)):
            # Maximizing fits the work area (1900x1000 at 10, 20) without covering the taskbar.
            self.assertEqual(api.toggle_maximize(), {"maximized": True, "compact": False})
            self.assertEqual(window.sizes[-1], (1900, 1000))
            self.assertEqual(window.moves[-1], (10, 20))
            # Restoring returns to the saved custom bounds (980x640 at 120, 90).
            self.assertEqual(api.toggle_maximize(), {"maximized": False, "compact": False})
            self.assertEqual(window.sizes[-1], (980, 640))
            self.assertEqual(window.moves[-1], (120, 90))
            # External maximize to work area is detected by window_state and toggle_maximize.
            window.width, window.height, window.x, window.y = 1900, 1000, 10, 20
            self.assertEqual(api.window_state(), {"maximized": True, "compact": False})
            self.assertEqual(api.toggle_maximize(), {"maximized": False, "compact": False})
            # Maximizing from compact mode clears compact state and fits work area.
            api.set_compact(True)
            self.assertEqual(api.toggle_maximize(True), {"maximized": True, "compact": False})
            self.assertEqual(window.sizes[-1], (1900, 1000))
            # Entering compact mode from maximized clears maximized state.
            self.assertEqual(api.set_compact(True), {"compact": True})
            self.assertFalse(api._maximized)
            self.assertEqual(window.sizes[-1], (390, 520))

    def test_mobile_token_is_sent_to_windows_clipboard(self):
        api = gui.Api()
        response = {"status": "ok", "data": {"token": "private-token"}}
        with patch.object(gui, "ipc_send", return_value=response), \
                patch.object(gui.subprocess, "run") as run:
            result = api.copy_mobile_token()
        self.assertEqual(result["status"], "ok")
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["input"], "private-token")


if __name__ == "__main__":
    unittest.main()
