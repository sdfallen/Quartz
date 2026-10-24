import tempfile
import unittest
from pathlib import Path

from core.continuity_engine import ContinuityEngine


class ContinuityEngineTests(unittest.TestCase):
    def make_engine(self, root):
        return ContinuityEngine(root / "operation.json", root / "workflows.json")

    def test_operation_survives_restart_and_keeps_app_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = self.make_engine(root)
            engine.record_tool(
                "Steam'i aç", "smart_open",
                {"args": ["steam"], "kwargs": {}}, "opened")
            engine.add_message("Kütüphaneme gir")
            restored = self.make_engine(root).active()
            self.assertEqual(restored["app_context"], "steam")
            self.assertEqual(restored["messages"][-1]["content"], "Kütüphaneme gir")
            self.assertEqual(restored["actions"][0]["tool"], "smart_open")

    def test_learning_redacts_secrets_and_provides_hint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = self.make_engine(root)
            engine.record_tool(
                "Steam oyun indir", "smart_open",
                {"args": ["steam"], "kwargs": {"api_key": "private"}}, "ok")
            workflow = engine.learn_active("Steam oyun indirme")
            self.assertEqual(
                workflow["steps"][0]["arguments"]["kwargs"]["api_key"],
                "<redacted>")
            engine.complete()
            hint = engine.workflow_hint("Steam oyun indirme işlemini yap")
            self.assertIn("LEARNED WORKFLOW MATCH", hint)
            self.assertIn("smart_open", hint)

    def test_complete_clears_active_context(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory))
            engine.ensure("bir görev")
            self.assertIsNotNone(engine.complete("bitti"))
            self.assertIsNone(engine.active())


    def test_opening_a_different_app_starts_fresh_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory))
            engine.record_tool("Open Chrome", "smart_open",
                               {"args": ["chrome"]}, "opened")
            engine.record_tool("Open Steam", "smart_open",
                               {"args": ["steam"]}, "opened")
            state = engine.active()
            self.assertEqual(state["root_goal"], "Open Steam")
            self.assertEqual(state["app_context"], "steam")
            self.assertEqual(len(state["actions"]), 1)


if __name__ == "__main__":
    unittest.main()
