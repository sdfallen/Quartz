import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.atomic_json import atomic_write_json, load_json


class AtomicJsonTests(unittest.TestCase):
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
