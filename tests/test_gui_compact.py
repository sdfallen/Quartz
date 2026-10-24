import unittest
from unittest.mock import patch

import gui


class FakeWindow:
    def __init__(self):
        self.sizes = []

    def resize(self, width, height):
        self.sizes.append((width, height))


class CompactWindowTests(unittest.TestCase):
    def test_voice_system_is_deferred_until_requested(self):
        api = gui.Api()
        self.assertIsNone(api._voice_instance)

    def test_compact_and_full_sizes_are_applied(self):
        api = gui.Api.__new__(gui.Api)
        api._compact = False
        window = FakeWindow()
        with patch.object(gui.webview, "windows", [window]):
            self.assertEqual(api.set_compact(True), {"compact": True})
            self.assertEqual(api.set_compact(False), {"compact": False})
        self.assertEqual(window.sizes, [(390, 520), (1160, 740)])

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
        self.assertIn('window.confirm(', gui._HTML)

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
