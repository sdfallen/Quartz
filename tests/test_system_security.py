import unittest
from pathlib import Path

import system_controller


class SystemSecurityTests(unittest.TestCase):
    def test_protected_system_paths_cannot_be_deleted(self):
        self.assertTrue(system_controller._is_protected(Path("C:\\Windows")))
        self.assertTrue(system_controller._is_protected(Path.home()))

    def test_command_is_split_without_a_shell(self):
        args = system_controller._command_args('python "hello world.py" --safe')
        self.assertEqual(args, ["python", "hello world.py", "--safe"])

    def test_empty_command_is_rejected(self):
        with self.assertRaises(ValueError):
            system_controller._command_args("   ")


if __name__ == "__main__":
    unittest.main()
