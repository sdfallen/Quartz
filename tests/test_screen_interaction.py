import unittest

import assistant
from core.screen_interaction import parse_target_json


class ScreenInteractionTests(unittest.TestCase):
    def test_normalized_coordinates_are_mapped_to_screen_pixels(self):
        target = parse_target_json(
            'result: {"x": 500, "y": 250, "confidence": 0.91, '
            '"description": "YouTube düğmesi"}',
            width=1920, height=1080, target="YouTube düğmesi")
        self.assertEqual((target.x, target.y), (960, 270))
        self.assertEqual(target.confidence, 0.91)

    def test_out_of_screen_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_target_json(
                '{"x": 1001, "y": 10, "confidence": 0.8}',
                width=1920, height=1080, target="düğme")

    def test_zero_coordinate_hallucination_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_target_json(
                '{"x": 0, "y": 0, "confidence": 0.98}',
                width=1920, height=1080, target="Library")

    def test_screen_click_is_a_confirmed_system_action(self):
        self.assertIn("screen_click_target", assistant.DANGEROUS_TOOLS)
        self.assertEqual(assistant.TOOL_RISK_LEVELS["screen_click_target"], "system")


if __name__ == "__main__":
    unittest.main()
