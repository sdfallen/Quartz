"""Screenshots never carry another application's pixels (known gap; fixed 24 Nov 2026).

The capture is a crop of the screen at the target window. A window above it (an always-on-top
tool, a notification, a second app dragged over it) used to appear in the evidence image.
"""
import unittest

from PIL import Image

from core.desktop_native import mask_occluded, outside_frame


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


class InvisibleBorderTests(unittest.TestCase):
    """Live 24 Nov: the 7 px resize border showed another window's text at the crop's left edge."""

    def test_the_strips_outside_the_visible_frame_are_masked(self):
        rect, frame = (156, 156, 812, 615), (163, 156, 805, 608)  # measured on Windows 10
        strips = outside_frame(rect, frame)
        self.assertEqual(sorted(strips), sorted([(156, 608, 812, 615), (156, 156, 163, 608), (805, 156, 812, 608)]))
        img = Image.new("RGB", (656, 459), (255, 255, 255))
        mask_occluded(img, rect, strips)
        self.assertEqual(img.getpixel((0, 200)), (0, 0, 0))
        self.assertEqual(img.getpixel((655, 200)), (0, 0, 0))
        self.assertEqual(img.getpixel((300, 458)), (0, 0, 0))
        self.assertEqual(img.getpixel((300, 200)), (255, 255, 255))

    def test_no_frame_information_masks_nothing_extra(self):
        self.assertEqual(outside_frame((0, 0, 10, 10), None), [])
        self.assertEqual(outside_frame((0, 0, 10, 10), (0, 0, 10, 10)), [])


class CaptureRefusesUnknownStackingTests(unittest.TestCase):
    def test_capture_code_masks_and_refuses_when_z_order_is_unreadable(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1].joinpath("core", "desktop_native.py").read_text(encoding="utf-8")
        self.assertIn("masked = mask_occluded(image, (left, top, right, bottom), covering)", source)
        self.assertIn("Window stacking could not be read; no screenshot", source)


if __name__ == "__main__":
    unittest.main()


class BlankFrameTests(unittest.TestCase):
    """Full-screen games (25 Nov): a black screen crop falls back to the window's own render,
    and a frame that stays black carries a hint instead of passing as an observation."""

    def test_only_nearly_black_frames_count_as_blank(self):
        from core.desktop_native import is_blank
        self.assertTrue(is_blank(Image.new("RGB", (40, 40), (0, 0, 0))))
        self.assertTrue(is_blank(Image.new("RGB", (40, 40), (6, 6, 6))))
        self.assertFalse(is_blank(Image.new("RGB", (40, 40), (30, 38, 48))), "a dark theme is not blank")
        img = Image.new("RGB", (40, 40), (0, 0, 0))
        img.putpixel((5, 5), (255, 255, 255))
        self.assertFalse(is_blank(img), "one bright pixel is content")

    def test_capture_falls_back_and_reports_a_black_frame(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1].joinpath("core", "desktop_native.py").read_text(encoding="utf-8")
        self.assertIn("if image is None or is_blank(image):", source)
        self.assertIn('image, source = rendered, "window-render"', source)
        self.assertIn('"image_blank": True', source)
