import tempfile
import unittest
from pathlib import Path

from core.project_registry import ProjectRegistry


class ProjectRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = ProjectRegistry([{
            "id": "pilot", "name": "Pilot", "path": str(self.root),
            "protected": False,
        }])

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_registered_project_can_be_selected(self):
        with self.assertRaises(KeyError):
            self.registry.select("aster")

    def test_squad_workspace_is_required_when_requested(self):
        with self.assertRaises(RuntimeError):
            self.registry.resolve("pilot", require_squad=True)
        squad = self.root / ".squad"
        squad.mkdir()
        (squad / "messages.db").touch()
        self.assertEqual(self.registry.resolve("pilot", require_squad=True), self.root.resolve())

    def test_project_list_exposes_real_workspace_state(self):
        project = self.registry.list()[0]
        self.assertTrue(project["exists"])
        self.assertFalse(project["squad_initialized"])
        self.assertTrue(project["selected"])

    def test_added_projects_and_selection_survive_restart(self):
        other = self.root / "Second"
        other.mkdir()
        store = self.root / "projects.json"
        registry = ProjectRegistry([{"id": "pilot", "path": str(self.root)}], storage_path=store)
        added = registry.add(other, "Second Project")
        self.assertEqual(registry.add(other)["id"], added["id"])
        restarted = ProjectRegistry([{"id": "pilot", "path": str(self.root)}], storage_path=store)
        self.assertEqual(restarted.selected()["id"], added["id"])
        self.assertEqual(restarted.get(added["id"])["path"], str(other.resolve()))
        restarted.select("pilot")
        self.assertEqual(ProjectRegistry([{"id": "pilot", "path": str(self.root)}],
                                         storage_path=store).selected()["id"], "pilot")


if __name__ == "__main__":
    unittest.main()
