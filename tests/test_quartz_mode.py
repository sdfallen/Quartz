import unittest
from unittest.mock import patch

import advanced_controller
import assistant


class QuartzModeTests(unittest.TestCase):
    def test_intent_hint_recognizes_quartz_mode(self):
        self.assertIn("quartz_mode()", assistant._intent_hint("Quartz Mode"))

    def test_quartz_mode_activates_named_plan(self):
        listed = (
            "Power Scheme GUID: 11111111-2222-3333-4444-555555555555  "
            "(Quartz Sessiz Uzaktan Erişim)\n")
        with patch.object(advanced_controller.platform, "system", return_value="Windows"), \
                patch.object(advanced_controller.subprocess, "run") as run:
            run.return_value.stdout = listed
            result = advanced_controller.quartz_mode()
        self.assertIn("etkin", result)
        self.assertEqual(run.call_args_list[1].args[0][-1], "11111111-2222-3333-4444-555555555555")


if __name__ == "__main__":
    unittest.main()
