import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from core.project_registry import ProjectRegistry


class ProjectIPCTests(unittest.TestCase):
    def test_add_select_and_restart_keep_project_and_chat_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Sample"
            project.mkdir()
            default = root / "Default"
            default.mkdir()
            defaults = ({"id": "squad-pilot", "name": "Squad Pilot",
                         "path": str(default), "protected": False},)
            with patch.object(main, "BASE_DIR", root), patch.object(ProjectRegistry, "DEFAULTS", defaults):
                server = main.IPCServer(MagicMock())
                added = server._dispatch_action({"action": "project_add", "data": {"path": str(project)}})
                self.assertEqual(added["status"], "ok")
                project_id = added["data"]["project"]["id"]
                self.assertEqual(added["data"]["conversation"]["project_id"], project_id)
                self.assertTrue((project / ".squad" / "messages.db").is_file(),
                                added["data"]["project"].get("squad_error"))
                self.assertEqual(server._get_agent_center().projects.selected()["id"], project_id)
                selected = server._dispatch_action({"action": "project_select",
                                                    "data": {"project_id": "squad-pilot"}})
                self.assertEqual(selected["data"].get("project_id"), None)
                server2 = main.IPCServer(MagicMock())
                self.assertEqual(server2._get_agent_center().projects.selected()["id"], "squad-pilot")
                back = server2._dispatch_action({"action": "project_select",
                                                 "data": {"project_id": project_id}})
                self.assertEqual(back["data"]["id"], added["data"]["conversation"]["id"])
                self.assertEqual(server2._get_agent_center().projects.selected()["id"], project_id)


if __name__ == "__main__":
    unittest.main()
