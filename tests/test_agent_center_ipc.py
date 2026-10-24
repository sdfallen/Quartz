import unittest
from unittest.mock import MagicMock

from main import IPCServer


class AgentCenterIPCTests(unittest.TestCase):
    def setUp(self):
        self.assistant = MagicMock()
        self.server = IPCServer(self.assistant)
        self.center = MagicMock()
        self.server._agent_center = self.center

    def test_status_uses_requested_project(self):
        self.center.status.return_value = {"codex": {"ready": True}}
        response = self.server._dispatch_action({
            "action": "agent_center_status",
            "data": {"project_id": "squad-pilot"},
        })
        self.center.status.assert_called_once_with("squad-pilot")
        self.assertTrue(response["data"]["codex"]["ready"])

    def test_dispatch_preserves_write_confirmation_boundary(self):
        self.center.dispatch.return_value = {"run": {"id": "run-1"}}
        response = self.server._dispatch_action({
            "action": "agent_center_dispatch",
            "data": {
                "prompt": "inspect", "title": "probe",
                "project_id": "squad-pilot", "write": True,
                "confirm_write": True, "provider": "antigravity",
            },
        })
        self.assertEqual(response["status"], "ok")
        self.center.dispatch.assert_called_once_with(
            "antigravity", "inspect", title="probe", project_id="squad-pilot",
            write=True, confirm_write=True,
        )

    def test_empty_dispatch_is_rejected_without_starting_runtime(self):
        response = self.server._dispatch_action({
            "action": "agent_center_dispatch", "data": {"prompt": "  "},
        })
        self.assertEqual(response["status"], "error")
        self.center.dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
