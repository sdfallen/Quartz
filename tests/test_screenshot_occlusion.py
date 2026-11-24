"""Screenshots never carry another application's pixels (known gap; fixed 24 Nov 2026).

The capture is a crop of the screen at the target window. A window above it (an always-on-top
tool, a notification, a second app dragged over it) used to appear in the evidence image.
"""
import unittest

from PIL import Image

from core.desktop_native import mask_occluded


class MaskOccludedTests(unittest.TestCase):
    def image(self):
        return Image.new("RGB", (200, 100), (255, 255, 255))

    def test_the_covered_part_is_black_and_the_rest_untouched(self):
        img = self.image()
        # Target at screen (100, 50)-(300, 150); another window covers its right half.
        masked = mask_occluded(img, (100, 50, 300, 150), [(200, 0, 400, 400)])
        self.assertEqual(masked, 1)
        self.assertEqual(img.getpixel((150, 50)), (0, 0, 0))
        self.assertEqual(img.getpixel((199, 99)), (0, 0, 0))
        self.assertEqual(img.getpixel((99, 50)), (255, 255, 255))
        self.assertEqual(img.getpixel((0, 0)), (255, 255, 255))

    def test_windows_beside_the_target_change_nothing(self):
        img = self.image()
        self.assertEqual(mask_occluded(img, (100, 50, 300, 150), [(0, 0, 100, 50), (300, 0, 500, 500)]), 0)
        self.assertEqual(img.getcolors(), [(200 * 100, (255, 255, 255))])

    def test_a_window_over_everything_blacks_out_the_whole_crop(self):
        img = self.image()
        self.assertEqual(mask_occluded(img, (100, 50, 300, 150), [(0, 0, 1920, 1080)]), 1)
        self.assertEqual(img.getcolors(), [(200 * 100, (0, 0, 0))])

    def test_no_occluders_is_a_no_op(self):
        self.assertEqual(mask_occluded(self.image(), (0, 0, 200, 100), []), 0)


class CaptureRefusesUnknownStackingTests(unittest.TestCase):
    def test_capture_code_masks_and_refuses_when_z_order_is_unreadable(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1].joinpath("core", "desktop_native.py").read_text(encoding="utf-8")
        self.assertIn("masked = mask_occluded(image, (left, top, right, bottom), covering)", source)
        self.assertIn("Window stacking could not be read; no screenshot", source)


if __name__ == "__main__":
    unittest.main()
