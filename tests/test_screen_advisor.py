import unittest

from PIL import Image

from core.screen_advisor import ScreenAdvisor


class ScreenAdvisorTests(unittest.TestCase):
    def test_fingerprint_difference_detects_visual_change(self):
        black = Image.new("RGB", (200, 120), "black")
        white = Image.new("RGB", (200, 120), "white")
        before = ScreenAdvisor.fingerprint(black)
        self.assertEqual(ScreenAdvisor.difference(before, before), 0)
        self.assertGreater(ScreenAdvisor.difference(
            before, ScreenAdvisor.fingerprint(white)), .9)

    def test_disabled_by_default(self):
        advisor = ScreenAdvisor(lambda **_: None, lambda *_a, **_k: "",
                                lambda _text: None, lambda: False)
        self.assertFalse(advisor.enabled)


if __name__ == "__main__":
    unittest.main()
