"""jarvis_open_app must not walk the Desktop for a command alias (live exam 9 Nov, exam-desk-03)."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import advanced_controller


class SmartOpenFastTests(unittest.TestCase):
    def test_command_and_turkish_names_launch_without_a_folder_search(self):
        for name, command in (("calc", "calc"), ("Calc.exe", "calc"), ("Hesap Makinesi", "calc"),
                              ("notepad", "notepad"), ("Not Defteri", "notepad"), ("calculator", "calc")):
            with patch("core.elevation.launch_normal") as launch, \
                    patch.object(advanced_controller, "_search_dir_limited") as search:
                advanced_controller.smart_open(name)
                launch.assert_called_once_with(command)
                search.assert_not_called()

    def test_folder_search_is_bounded_by_files_examined_and_time(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(60):
                (Path(root) / f"other{i}.lnk").write_text("x")
            (Path(root) / "zz_target.lnk").write_text("x")
            self.assertIsNone(advanced_controller._search_dir_limited(Path(root), "*.lnk", "nothing", max_items=10))
            started = time.monotonic()
            self.assertIsNone(advanced_controller._search_dir_limited(Path(root), "*.lnk", "nothing", seconds=0))
            self.assertLess(time.monotonic() - started, 0.5)
            found = advanced_controller._search_dir_limited(Path(root), "*.lnk", "zz_target")
            self.assertEqual(found.name, "zz_target.lnk")


if __name__ == "__main__":
    unittest.main()
