import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_initialize_does_not_pollute_project_root_and_hides_squad_dir(self):
        project = Path(self.tmp.name) / "clean_proj"
        project.mkdir()
        (project / ".git" / "info").mkdir(parents=True)
        (project / "CLAUDE.md").write_bytes(b"# Original Claude instructions\n")
        adapter = SquadAdapter(project, executable=self.exe)

        def fake_run(args, **_kwargs):
            if args == ["init"]:
                (project / ".squad" / "roles").mkdir(parents=True, exist_ok=True)
                (project / ".squad" / "teams").mkdir(parents=True, exist_ok=True)
                (project / ".gitignore").write_text(".squad/\n", encoding="utf-8")
                (project / "AGENTS.md").write_text("## Squad Collaboration\n", encoding="utf-8")
                (project / "CLAUDE.md").write_text("## Overwritten by squad init\n", encoding="utf-8")
                (project / "GEMINI.md").write_text("## Squad Collaboration\n", encoding="utf-8")
                return {"ok": True, "returncode": 0, "stdout": "Initialized", "stderr": "", "error": ""}
            if args == ["agents", "--json"]:
                (project / ".squad" / "messages.db").touch()
                return {"ok": True, "returncode": 0, "stdout": "", "stderr": "", "error": ""}
            return {"ok": True, "returncode": 0, "stdout": "", "stderr": "", "error": ""}

        with patch.object(adapter, "_run", side_effect=fake_run):
            res = adapter.initialize()
        self.assertTrue(res["initialized"])
        self.assertFalse(res["existing"])
        self.assertTrue((project / ".squad" / "messages.db").is_file())
        self.assertFalse((project / ".gitignore").exists())
        self.assertFalse((project / "AGENTS.md").exists())
        self.assertFalse((project / "GEMINI.md").exists())
        self.assertEqual((project / "CLAUDE.md").read_bytes(), b"# Original Claude instructions\n")
        self.assertIn(".squad/", (project / ".git" / "info" / "exclude").read_text(encoding="utf-8"))
        if os.name == "nt":
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(project / ".squad"))
            self.assertTrue(bool(attrs & 0x02))

    def test_corrupted_messages_db_is_detected_and_repaired(self):
        project = Path(self.tmp.name) / "corrupt_proj"
        (project / ".squad").mkdir(parents=True)
        corrupt_db = project / ".squad" / "messages.db"
        corrupt_db.write_bytes(b"corrupted text data " * 20)
        adapter = SquadAdapter(project, executable=self.exe)

        self.assertTrue(SquadAdapter._is_db_corrupt(corrupt_db))
        self.assertFalse(adapter.initialized)

        def fake_subprocess_run(cmd, **_kwargs):
            from types import SimpleNamespace
            sub = cmd[1] if len(cmd) > 1 else ""
            if sub == "init":
                (project / ".squad" / "roles").mkdir(parents=True, exist_ok=True)
                (project / ".squad" / "teams").mkdir(parents=True, exist_ok=True)
                return SimpleNamespace(returncode=0, stdout="Initialized", stderr="")
            if sub == "agents":
                if SquadAdapter._is_db_corrupt(corrupt_db):
                    return SimpleNamespace(
                        returncode=1,
                        stdout="",
                        stderr="Error: database disk image is malformed\nCaused by:\n  Error code 11: The database disk image is malformed",
                    )
                import sqlite3
                conn = sqlite3.connect(str(corrupt_db))
                conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT);")
                conn.commit()
                conn.close()
                return SimpleNamespace(returncode=0, stdout='{"id":"worker","role":"worker","status":"active"}\n', stderr="")
            if sub == "--version":
                return SimpleNamespace(returncode=0, stdout="squad 0.7.6\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("core.squad_adapter.subprocess.run", side_effect=fake_subprocess_run):
            rows = adapter.agents()
            st = adapter.status()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "worker")
        self.assertFalse(SquadAdapter._is_db_corrupt(corrupt_db))
        self.assertTrue(adapter.initialized)
        self.assertTrue(st["initialized"])


if __name__ == "__main__":
    unittest.main()
