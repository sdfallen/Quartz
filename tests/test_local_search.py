import tempfile
import unittest
from pathlib import Path

from core.local_search import LocalSearchEngine


class LocalSearchTests(unittest.TestCase):
    def test_indexes_selected_folder_and_returns_matching_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text(
                "Quartz yerel belge araması özel ve hızlıdır.", encoding="utf-8")
            (root / "other.md").write_text(
                "Bu belgede yalnızca hava durumu bilgisi var.", encoding="utf-8")
            engine = LocalSearchEngine(root / "index.json")

            summary = engine.index_folder(str(root))
            results = engine.search("yerel belge araması")

            self.assertEqual(summary["files"], 2)
            self.assertTrue(results)
            self.assertEqual(Path(results[0]["path"]).name, "notes.txt")
            self.assertIn("Quartz", results[0]["snippet"])

    def test_empty_query_returns_no_results(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = LocalSearchEngine(Path(directory) / "index.json")
            self.assertEqual(engine.search(" "), [])


if __name__ == "__main__":
    unittest.main()
