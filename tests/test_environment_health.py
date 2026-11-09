"""Unit tests for core/environment_health.py (INTEGRATION_REQUEST_ENVIRONMENT_HEALTH_20261109.md)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import environment_health


def _fake_runner(*, python_out="", python_code=0, git_ver="git version 2.47.0.windows.1", git_ver_code=0, is_repo="true", is_repo_code=0):
    calls = []

    def run(cmd, **_kwargs):
        calls.append(list(cmd))
        exe = Path(cmd[0]).stem.lower()
        if exe == "python":
            return SimpleNamespace(returncode=python_code, stdout=python_out, stderr="" if python_code == 0 else "python error")
        if exe == "git" and "--version" in cmd:
            return SimpleNamespace(returncode=git_ver_code, stdout=git_ver, stderr="" if git_ver_code == 0 else "git missing")
        if exe == "git" and "--is-inside-work-tree" in cmd:
            return SimpleNamespace(returncode=is_repo_code, stdout=is_repo, stderr="" if is_repo_code == 0 else "fatal: not a git repository")
        return SimpleNamespace(returncode=1, stdout="", stderr="unexpected command")

    return run, calls


def _ready_agents(*, squad_connected=True):
    return {
        "codex": {"installed": True, "authenticated": True, "ready": True, "version": "codex 0.1.0"},
        "antigravity": {"installed": True, "authenticated": True, "ready": True, "version": "agy 1.2.0"},
        "squad": {
            "installed": True,
            "initialized": squad_connected,
            "connected": squad_connected,
            "database": "C:\\repo\\.squad\\messages.db",
            "error": "" if squad_connected else "Squad çalışma alanı hazır değil.",
        },
    }


class EnvironmentHealthContractTests(unittest.TestCase):
    def setUp(self):
        environment_health.clear_cache()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        environment_health.clear_cache()
        self.temp.cleanup()

    def _by_id(self, res: dict) -> dict[str, dict]:
        return {item["id"]: item for item in res["checks"]}

    def test_all_green_environment_returns_ok_and_contract_fields(self):
        py_exe = r"C:\Users\LENAVO\AppData\Local\Programs\Python\Python313\python.exe"
        runner, _ = _fake_runner(python_out=f"{py_exe}\n3.13.17\n")
        which = lambda name: py_exe if name == "python" else r"C:\Program Files\Git\cmd\git.exe"

        res = environment_health.check(
            self.root,
            mode="collaboration",
            agents=_ready_agents(squad_connected=True),
            runner=runner,
            which_fn=which,
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["mode"], "collaboration")
        self.assertIsInstance(res["checked_at"], float)
        self.assertEqual(Path(res["project_path"]), self.root.resolve())

        by_id = self._by_id(res)
        self.assertEqual(
            set(by_id.keys()),
            {"python", "git", "project_folder", "squad", "codex_cli", "antigravity_cli"},
        )
        for item in res["checks"]:
            self.assertEqual(item["status"], "ok", item)
            self.assertLessEqual(len(item["summary_tr"]), 120)
            self.assertLessEqual(len(item["fix_tr"]), 160)
            self.assertLessEqual(len(item["detail"]), 500)
            self.assertIsInstance(item["evidence"], dict)

    def test_windows_store_python_alias_warns_even_when_exit_code_is_zero(self):
        store_which = r"C:\Users\LENAVO\AppData\Local\Microsoft\WindowsApps\python.EXE"
        store_exe = r"C:\Users\LENAVO\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
        runner, _ = _fake_runner(python_out=f"{store_exe}\n3.13.14\n")
        which = lambda name: store_which if name == "python" else r"C:\Program Files\Git\cmd\git.exe"

        res = environment_health.check(
            self.root,
            mode="codex",
            agents=_ready_agents(squad_connected=True),
            runner=runner,
            which_fn=which,
        )
        by_id = self._by_id(res)
        self.assertEqual(by_id["python"]["status"], "warn")
        self.assertIn("Store", by_id["python"]["summary_tr"])
        self.assertIn("python.org", by_id["python"]["fix_tr"])
        self.assertTrue(by_id["python"]["evidence"]["store_alias"])
        # Python never blocks a task on its own.
        self.assertEqual(res["status"], "warn")

    def test_missing_python_warns_and_never_blocks(self):
        runner, _ = _fake_runner(python_out="", python_code=1)
        which = lambda name: None if name == "python" else r"C:\Program Files\Git\cmd\git.exe"

        res = environment_health.check(
            self.root,
            mode="codex",
            agents=_ready_agents(squad_connected=True),
            runner=runner,
            which_fn=which,
        )
        by_id = self._by_id(res)
        self.assertEqual(by_id["python"]["status"], "warn")
        self.assertEqual(res["status"], "warn")

    def test_squad_unconnected_blocks_collaboration_and_desktop_but_warns_single_agent(self):
        py_exe = r"C:\Users\LENAVO\AppData\Local\Programs\Python\Python313\python.exe"
        runner, _ = _fake_runner(python_out=f"{py_exe}\n3.13.17\n")
        which = lambda name: py_exe if name == "python" else r"C:\Program Files\Git\cmd\git.exe"
        agents = _ready_agents(squad_connected=False)

        collab_res = environment_health.check(
            self.root, mode="collaboration", agents=agents, runner=runner, which_fn=which, force=True
        )
        self.assertEqual(self._by_id(collab_res)["squad"]["status"], "blocked")
        self.assertEqual(collab_res["status"], "blocked")

        desk_res = environment_health.check(
            self.root, mode="codex", desktop=True, agents=agents, runner=runner, which_fn=which, force=True
        )
        self.assertEqual(self._by_id(desk_res)["squad"]["status"], "blocked")
        self.assertEqual(desk_res["status"], "blocked")

        single_res = environment_health.check(
            self.root, mode="codex", desktop=False, agents=agents, runner=runner, which_fn=which, force=True
        )
        self.assertEqual(self._by_id(single_res)["squad"]["status"], "warn")
        self.assertEqual(single_res["status"], "warn")

    def test_git_missing_blocks_writer_and_warns_read_only_and_non_repo_warns(self):
        py_exe = r"C:\Users\LENAVO\AppData\Local\Programs\Python\Python313\python.exe"
        which = lambda name: py_exe if name == "python" else None
        runner_no_git, _ = _fake_runner(python_out=f"{py_exe}\n3.13.17\n", git_ver="", git_ver_code=1)

        write_res = environment_health.check(
            self.root, mode="codex", write=True, agents=_ready_agents(), runner=runner_no_git, which_fn=which, force=True
        )
        self.assertEqual(self._by_id(write_res)["git"]["status"], "blocked")
        self.assertEqual(write_res["status"], "blocked")

        ro_res = environment_health.check(
            self.root, mode="codex", write=False, agents=_ready_agents(), runner=runner_no_git, which_fn=which, force=True
        )
        self.assertEqual(self._by_id(ro_res)["git"]["status"], "warn")
        self.assertEqual(ro_res["status"], "warn")

        runner_non_repo, _ = _fake_runner(
            python_out=f"{py_exe}\n3.13.17\n", is_repo="false", is_repo_code=128
        )
        non_repo_res = environment_health.check(
            self.root, mode="codex", write=True, agents=_ready_agents(), runner=runner_non_repo, which_fn=which, force=True
        )
        self.assertEqual(self._by_id(non_repo_res)["git"]["status"], "warn")

    def test_project_folder_missing_blocks(self):
        py_exe = r"C:\Users\LENAVO\AppData\Local\Programs\Python\Python313\python.exe"
        runner, _ = _fake_runner(python_out=f"{py_exe}\n3.13.17\n")
        which = lambda name: py_exe
        missing = self.root / "does-not-exist"

        res = environment_health.check(
            missing, mode="codex", agents=_ready_agents(), runner=runner, which_fn=which
        )
        self.assertEqual(self._by_id(res)["project_folder"]["status"], "blocked")
        self.assertEqual(res["status"], "blocked")

    def test_cli_issue_blocks_selected_agent_and_warns_unselected_agent(self):
        py_exe = r"C:\Users\LENAVO\AppData\Local\Programs\Python\Python313\python.exe"
        runner, _ = _fake_runner(python_out=f"{py_exe}\n3.13.17\n")
        which = lambda name: py_exe
        agents = _ready_agents()
        agents["antigravity"] = {
            "installed": True,
            "authenticated": False,
            "ready": False,
            "error": "Authentication required for user@example.com token=sk-secret123456789012345",
        }

        codex_only = environment_health.check(
            self.root, mode="codex", agents=agents, runner=runner, which_fn=which, force=True
        )
        by_id_codex = self._by_id(codex_only)
        self.assertEqual(by_id_codex["codex_cli"]["status"], "ok")
        self.assertEqual(by_id_codex["antigravity_cli"]["status"], "warn")
        self.assertEqual(codex_only["status"], "warn")
        # Sensitive email/token in error detail must be redacted.
        self.assertNotIn("user@example.com", by_id_codex["antigravity_cli"]["detail"])
        self.assertNotIn("sk-secret", by_id_codex["antigravity_cli"]["detail"])

        agy_only = environment_health.check(
            self.root, mode="antigravity", agents=agents, runner=runner, which_fn=which, force=True
        )
        self.assertEqual(self._by_id(agy_only)["antigravity_cli"]["status"], "blocked")
        self.assertEqual(agy_only["status"], "blocked")

    def test_cache_reuses_result_for_60_seconds_unless_forced(self):
        py_exe = r"C:\Users\LENAVO\AppData\Local\Programs\Python\Python313\python.exe"
        runner, calls = _fake_runner(python_out=f"{py_exe}\n3.13.17\n")
        which = lambda name: py_exe
        agents = _ready_agents()

        first = environment_health.check(self.root, mode="codex", agents=agents, runner=runner, which_fn=which)
        call_count_after_first = len(calls)
        self.assertGreater(call_count_after_first, 0)

        second = environment_health.check(self.root, mode="codex", agents=agents, runner=runner, which_fn=which)
        self.assertEqual(len(calls), call_count_after_first)
        self.assertEqual(first["checked_at"], second["checked_at"])

        forced = environment_health.check(
            self.root, mode="codex", agents=agents, force=True, runner=runner, which_fn=which
        )
        self.assertGreater(len(calls), call_count_after_first)
        self.assertGreaterEqual(forced["checked_at"], first["checked_at"])

    def test_unknown_status_rolls_up_to_at_most_warn_and_text_bounds_are_enforced(self):
        py_exe = r"C:\Users\LENAVO\AppData\Local\Programs\Python\Python313\python.exe"
        runner, _ = _fake_runner(python_out=f"{py_exe}\n3.13.17\n")
        which = lambda name: py_exe
        agents = _ready_agents()
        agents["squad"] = {"checking": True, "message": "x" * 900}

        res = environment_health.check(self.root, mode="collaboration", agents=agents, runner=runner, which_fn=which)
        by_id = self._by_id(res)
        self.assertEqual(by_id["squad"]["status"], "unknown")
        self.assertEqual(res["status"], "warn")
        self.assertLessEqual(len(by_id["squad"]["detail"]), 500)

    def test_subprocess_timeout_is_caught_within_budget(self):
        def timeout_runner(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 1.5))

        res = environment_health.check(
            self.root,
            mode="codex",
            agents=_ready_agents(),
            runner=timeout_runner,
            which_fn=lambda _name: None,
        )
        by_id = self._by_id(res)
        self.assertEqual(by_id["python"]["status"], "warn")
        self.assertEqual(by_id["git"]["status"], "warn")


if __name__ == "__main__":
    unittest.main()
