import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.atomic_json import atomic_write_json, load_json


class AtomicJsonTests(unittest.TestCase):
    def test_long_valid_filename_does_not_expand_temporary_component(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            if os.name == 'nt':
                parent = Path('\\\\?\\' + str(parent))
            path = parent / ('k' * 240 + '.json')
            try:
                atomic_write_json(path, {'observed': True})
                self.assertEqual(load_json(path, {}), {'observed': True})
                self.assertEqual([p.name for p in parent.iterdir()], [path.name])
            finally:
                # TemporaryDirectory uses a non-extended root on Windows.
                path.unlink(missing_ok=True)

    @unittest.skipUnless(os.name == 'nt', 'Windows legacy path-length boundary')
    def test_valid_251_character_destination_can_be_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            name = 'a' * 64 + '.' + 'b' * 32 + '.json'
            padding = 251 - len(str(base)) - len(name) - 2
            if padding < 1:
                self.skipTest('Temporary root too long for this boundary fixture')
            parent = base / ('d' * padding)
            path = parent / name
            self.assertEqual(len(str(path)), 251)
            atomic_write_json(path, {'persisted': True})
            self.assertEqual(load_json(path, {}), {'persisted': True})
            self.assertEqual([p.name for p in parent.iterdir()], [name])

    def test_round_trip_replaces_existing_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"old": true}', encoding="utf-8")
            atomic_write_json(path, {"new": [1, 2, 3]})
            self.assertEqual(load_json(path, {}), {"new": [1, 2, 3]})
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_invalid_json_returns_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(load_json(path, []), [])

    def test_replace_failure_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"keep": true}', encoding="utf-8")
            with patch("core.atomic_json.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(OSError):
                    atomic_write_json(path, {"new": True})
            self.assertEqual(path.read_text(encoding="utf-8"), '{"keep": true}')


if __name__ == "__main__":
    unittest.main()
