import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.squad_adapter import SquadAdapter, SquadCommandError


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
        # Live 14 Nov: .squad/ was left in a client's project. A new workspace lives outside it.
        project = Path(self.tmp.name) / "clean_proj"
        project.mkdir()
        (project / ".git" / "info").mkdir(parents=True)
        (project / "CLAUDE.md").write_bytes(b"# Original Claude instructions\n")
        with patch.dict(os.environ, {"QUARTZ_SQUAD_HOME": str(Path(self.tmp.name) / "homes")}):
            adapter = SquadAdapter(project, executable=self.exe)
        home = adapter.workspace_path
        self.assertNotEqual(home, project.resolve())
        self.assertTrue(str(home).startswith(str(Path(self.tmp.name) / "homes")))

        def fake_run(args, **_kwargs):
            if args == ["init"]:
                (home / ".squad" / "roles").mkdir(parents=True, exist_ok=True)
                (home / ".squad" / "teams").mkdir(parents=True, exist_ok=True)
                (home / ".gitignore").write_text(".squad/\n", encoding="utf-8")
                (home / "AGENTS.md").write_text("## Squad Collaboration\n", encoding="utf-8")
                (home / "GEMINI.md").write_text("## Squad Collaboration\n", encoding="utf-8")
                return {"ok": True, "returncode": 0, "stdout": "Initialized", "stderr": "", "error": ""}
            if args == ["agents", "--json"]:
                (home / ".squad" / "messages.db").touch()
                return {"ok": True, "returncode": 0, "stdout": "", "stderr": "", "error": ""}
            return {"ok": True, "returncode": 0, "stdout": "", "stderr": "", "error": ""}

        with patch.object(adapter, "_run", side_effect=fake_run):
            res = adapter.initialize()
        self.assertTrue(res["initialized"])
        self.assertFalse(res["existing"])
        self.assertTrue((home / ".squad" / "messages.db").is_file())
        self.assertFalse((home / ".gitignore").exists())
        self.assertFalse((home / "AGENTS.md").exists())
        self.assertEqual(sorted(p.name for p in project.iterdir()), [".git", "CLAUDE.md"])  # project untouched
        self.assertEqual((project / "CLAUDE.md").read_bytes(), b"# Original Claude instructions\n")
        self.assertFalse((project / ".git" / "info" / "exclude").exists())
        if os.name == "nt":
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(home / ".squad"))
            self.assertTrue(bool(attrs & 0x02))

    def test_a_project_that_already_has_squad_keeps_it_in_place(self):
        from core.squad_adapter import squad_home
        project = Path(self.tmp.name) / "legacy_proj"
        (project / ".squad").mkdir(parents=True)
        self.assertEqual(squad_home(project), project.resolve())
        with patch.dict(os.environ, {"QUARTZ_SQUAD_HOME": str(Path(self.tmp.name) / "homes")}):
            first, second = Path(self.tmp.name) / "a", Path(self.tmp.name) / "b"
            first.mkdir(); second.mkdir()
            self.assertEqual(squad_home(first), squad_home(first))  # stable per project
            self.assertNotEqual(squad_home(first), squad_home(second))
            self.assertFalse((first / ".squad").exists())

    def test_locked_healthy_db_is_never_marked_corrupt_and_status_preserves_500_messages(self):
        project = Path(self.tmp.name) / "locked_proj"
        (project / ".squad").mkdir(parents=True)
        db_path = project / ".squad" / "messages.db"
        setup_conn = sqlite3.connect(str(db_path))
        setup_conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT);")
        setup_conn.executemany("INSERT INTO messages (body) VALUES (?);", [(f"msg-{i}",) for i in range(500)])
        setup_conn.commit()
        setup_conn.close()

        adapter = SquadAdapter(project, executable=self.exe)
        self.assertFalse(SquadAdapter._is_db_corrupt(db_path))

        writer = sqlite3.connect(str(db_path), timeout=1.0, isolation_level=None)
        try:
            writer.execute("BEGIN EXCLUSIVE;")
            writer.execute("INSERT INTO messages (body) VALUES ('in-flight');")
            # While another writer holds BEGIN EXCLUSIVE, _is_db_corrupt MUST return False (never True).
            self.assertFalse(SquadAdapter._is_db_corrupt(db_path))
            self.assertTrue(adapter.initialized)
        finally:
            writer.execute("ROLLBACK;")
            writer.close()

        # Even after the short-lived writer releases its lock, status() must keep the 500-message DB intact.
        with patch(
            "core.squad_adapter.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="squad 0.7.6\n", stderr=""),
        ):
            st = adapter.status()
        self.assertTrue(st["initialized"])
        self.assertEqual(st["error"], "")
        self.assertTrue(db_path.is_file())
        self.assertEqual(list((project / ".squad").glob("messages.db.corrupt-*")), [])

        verify_conn = sqlite3.connect(str(db_path))
        try:
            count = verify_conn.execute("SELECT COUNT(*) FROM messages;").fetchone()[0]
        finally:
            verify_conn.close()
        self.assertEqual(count, 500)

    def test_status_and_read_commands_never_repair_or_delete_corrupt_db(self):
        project = Path(self.tmp.name) / "readonly_corrupt_proj"
        (project / ".squad").mkdir(parents=True)
        corrupt_db = project / ".squad" / "messages.db"
        original_bytes = b"corrupted text data " * 20
        corrupt_db.write_bytes(original_bytes)
        adapter = SquadAdapter(project, executable=self.exe)

        self.assertTrue(SquadAdapter._is_db_corrupt(corrupt_db))
        self.assertFalse(adapter.initialized)

        with patch(
            "core.squad_adapter.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="squad 0.7.6\n", stderr=""),
        ):
            st = adapter.status()
        self.assertFalse(st["initialized"])
        self.assertIn("bozuk", st["error"])
        # status() must NEVER delete or quarantine messages.db.
        self.assertTrue(corrupt_db.is_file())
        self.assertEqual(corrupt_db.read_bytes(), original_bytes)
        self.assertEqual(list((project / ".squad").glob("messages.db.corrupt-*")), [])

        # Read-only commands like agents() must fail cleanly without quarantining or repairing.
        with self.assertRaises(SquadCommandError):
            adapter.agents()
        self.assertTrue(corrupt_db.is_file())
        self.assertEqual(list((project / ".squad").glob("messages.db.corrupt-*")), [])

    def test_corrupted_messages_db_is_quarantined_not_deleted_on_initialize_and_write(self):
        project = Path(self.tmp.name) / "quarantine_proj"
        (project / ".squad").mkdir(parents=True)
        corrupt_db = project / ".squad" / "messages.db"
        corrupt_bytes = b"corrupted text data " * 20
        corrupt_db.write_bytes(corrupt_bytes)
        adapter = SquadAdapter(project, executable=self.exe)

        def fake_subprocess_run(cmd, **_kwargs):
            sub = cmd[1] if len(cmd) > 1 else ""
            if sub == "init":
                (project / ".squad" / "roles").mkdir(parents=True, exist_ok=True)
                (project / ".squad" / "teams").mkdir(parents=True, exist_ok=True)
                return SimpleNamespace(returncode=0, stdout="Initialized", stderr="")
            if sub == "agents":
                conn = sqlite3.connect(str(corrupt_db))
                conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT);")
                conn.commit()
                conn.close()
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if sub == "join":
                return SimpleNamespace(returncode=0, stdout="Joined as manager (role: worker).\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("core.squad_adapter.subprocess.run", side_effect=fake_subprocess_run):
            joined = adapter.join("manager", role="worker", client="codex")
        self.assertEqual(joined["id"], "manager")
        self.assertTrue(corrupt_db.is_file())
        self.assertFalse(SquadAdapter._is_db_corrupt(corrupt_db))

        quarantined = list((project / ".squad").glob("messages.db.corrupt-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_bytes(), corrupt_bytes)
        self.assertEqual(Path(adapter.last_quarantined_db).resolve(), quarantined[0].resolve())

    def test_no_such_table_error_does_not_trigger_workspace_repair(self):
        project = Path(self.tmp.name) / "schema_proj"
        (project / ".squad").mkdir(parents=True)
        db_path = project / ".squad" / "messages.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dummy (id INT);")
        conn.commit()
        conn.close()
        adapter = SquadAdapter(project, executable=self.exe)

        calls = []

        def fake_subprocess_run(cmd, **_kwargs):
            calls.append(list(cmd))
            return SimpleNamespace(returncode=1, stdout="", stderr="Error: no such table: agents")

        with patch("core.squad_adapter.subprocess.run", side_effect=fake_subprocess_run):
            with self.assertRaises(SquadCommandError):
                adapter.join("manager", role="worker", client="codex")
        # Must not call `squad init` or quarantine the database on `no such table`.
        self.assertEqual(len(calls), 1)
        self.assertEqual(list((project / ".squad").glob("messages.db.corrupt-*")), [])

    def test_wal_replace_failure_rolls_back_messages_db_and_does_not_run_init(self):
        project = Path(self.tmp.name) / "wal_fail_proj"
        squad_root = project / ".squad"
        squad_root.mkdir(parents=True)
        corrupt_db = squad_root / "messages.db"
        wal_file = squad_root / "messages.db-wal"
        corrupt_bytes = b"corrupted sqlite main " * 20
        wal_bytes = b"stale wal frames " * 10
        corrupt_db.write_bytes(corrupt_bytes)
        wal_file.write_bytes(wal_bytes)
        adapter = SquadAdapter(project, executable=self.exe)

        orig_replace = Path.replace

        def fail_on_wal(self_path: Path, target: Path):
            if self_path.name == "messages.db-wal":
                raise OSError(13, "Permission denied on -wal")
            return orig_replace(self_path, target)

        calls = []
        with patch.object(Path, "replace", fail_on_wal), patch(
            "core.squad_adapter.subprocess.run",
            side_effect=lambda cmd, **_kw: calls.append(list(cmd)) or SimpleNamespace(returncode=0, stdout="", stderr=""),
        ):
            self.assertIsNone(adapter._quarantine_corrupt_db_files())
            self.assertTrue(corrupt_db.is_file())
            self.assertEqual(corrupt_db.read_bytes(), corrupt_bytes)
            self.assertTrue(wal_file.is_file())
            self.assertEqual(wal_file.read_bytes(), wal_bytes)
            self.assertEqual(list(squad_root.glob("messages.db.corrupt-*")), [])

            with self.assertRaises(SquadCommandError):
                adapter.initialize()
            # `squad init` must NOT run when -wal could not be quarantined.
            self.assertEqual(calls, [])
            self.assertTrue(corrupt_db.is_file())
            self.assertEqual(corrupt_db.read_bytes(), corrupt_bytes)

    def test_restore_root_files_preserves_concurrent_user_edits(self):
        project = Path(self.tmp.name) / "concurrent_edit_proj"
        project.mkdir()
        claude_md = project / "CLAUDE.md"
        claude_md.write_text("# Old header\n", encoding="utf-8")
        adapter = SquadAdapter(project, executable=self.exe)
        snap = adapter._snapshot_root_files()

        # Simulate concurrent user edit to CLAUDE.md + squad init appending boilerplate,
        # and concurrent user creation of AGENTS.md with custom text.
        concurrent_claude = "# Concurrent user header\nCustom rule\n\n## Squad Collaboration\n"
        claude_md.write_text(concurrent_claude, encoding="utf-8")
        agents_md = project / "AGENTS.md"
        concurrent_agents = "# My Custom Agents Doc\nMentions Squad Collaboration in prose.\n"
        agents_md.write_text(concurrent_agents, encoding="utf-8")

        adapter._restore_root_files(snap)
        self.assertEqual(claude_md.read_text(encoding="utf-8"), concurrent_claude)
        self.assertTrue(agents_md.is_file())
        self.assertEqual(agents_md.read_text(encoding="utf-8"), concurrent_agents)


if __name__ == "__main__":
    unittest.main()
