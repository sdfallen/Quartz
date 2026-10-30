import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os

from core.squad_adapter import SquadAdapter


class SquadAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / ".squad").mkdir()
        (root / ".squad" / "messages.db").touch()
        self.exe = root / "squad.exe"
        self.exe.touch()
        self.adapter = SquadAdapter(root, executable=self.exe)

    def tearDown(self):
        self.tmp.cleanup()

    def test_agents_parses_json_lines(self):
        output = '{"id":"worker","role":"worker","status":"active"}\n'
        with patch.object(self.adapter, "_checked", return_value={"stdout": output}):
            self.assertEqual(self.adapter.agents()[0]["id"], "worker")

    def test_packaged_squad_is_found_without_global_install(self):
        root = Path(self.tmp.name) / "bundle"
        executable = root / "assets/bin/squad.exe"
        executable.parent.mkdir(parents=True)
        executable.touch()
        with patch('core.squad_adapter.shutil.which', return_value=None), patch.dict(os.environ, {}, clear=True), patch('core.squad_adapter.sys._MEIPASS',str(root),create=True):
            self.assertEqual(SquadAdapter._find_executable(),str(executable.resolve()))

    def test_task_and_history_output_are_parsed(self):
        task_output = (
            "[task 12345678-1234-1234-1234-123456789abc] completed\n"
            "  assigned_to: worker\n  title: probe\n"
        )
        history_output = "* [2026-10-19T17:01:48Z] manager -> worker: hello\n"
        with patch.object(self.adapter, "_checked", side_effect=[
            {"stdout": task_output}, {"stdout": history_output},
        ]):
            task = self.adapter.tasks()[0]
            message = self.adapter.history()[0]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["assigned_to"], "worker")
        self.assertTrue(message["unread"])
        self.assertEqual(message["content"], "hello")

    def test_invalid_agent_id_is_rejected_before_process_launch(self):
        with self.assertRaises(ValueError):
            self.adapter.send("manager & whoami", "worker", "hello")

    def test_create_task_uses_argument_array_and_extracts_id(self):
        output = "Created task 12345678-1234-1234-1234-123456789abc for worker: probe\n"
        with patch.object(self.adapter, "_checked", return_value={"stdout": output}) as checked:
            result = self.adapter.create_task("manager", "worker", "probe", "body")
        self.assertEqual(result["id"], "12345678-1234-1234-1234-123456789abc")
        args = checked.call_args.args[0]
        self.assertEqual(args[:4], ["task", "create", "manager", "worker"])
        self.assertIn("body", args)


if __name__ == "__main__":
    unittest.main()
