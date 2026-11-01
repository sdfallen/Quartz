"""Comprehensive lifecycle tests for Quartz pyramid runtime layer.

Verifies:
1. Failed start (validation, missing dirs, missing executable)
2. Normal exit (stream parsing, exit code 0, completion status)
3. Timeout (bounded execution, process tree stopped, error recorded)
4. Stop / Cancellation (cancel_requested vs exit verification, idempotent stop)
5. Two consecutive runs (writer lock released, sequential reuse)
6. Provider absence (graceful init, probe installed=False, start error)
7. Child cleanup (descendant process termination via stop_process_tree)
8. Late output (events arriving after terminal state do not overwrite result)
9. Probe caching (repeated polling does not spawn new login/model subprocesses)
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import psutil

from core.antigravity_runtime import AntigravityRuntime
from core.codex_runtime import CodexRuntime
from core.gemini_runtime import GeminiRuntime
from core.process_tree import stop_process_tree


class MockProcess:
    def __init__(self, stdout="", stderr="", exit_code=0, delay=0.0):
        self.pid = 9999
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.stdin = io.StringIO()
        self._exit_code = exit_code
        self._delay = delay
        self._terminated = False
        self._killed = False

    def wait(self, timeout=None):
        if self._delay > 0 and not (self._terminated or self._killed):
            if timeout is not None and timeout < self._delay:
                time.sleep(0.05)
                raise subprocess.TimeoutExpired(["mock"], timeout)
            time.sleep(min(0.1, self._delay))
        return self._exit_code if (self._terminated or self._killed or self._delay == 0) else self._exit_code

    def poll(self):
        if self._terminated or self._killed or self._delay == 0:
            return self._exit_code
        return None

    def terminate(self, *args, **kwargs):
        self._terminated = True

    def kill(self, *args, **kwargs):
        self._killed = True


class PyramidRuntimeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="quartz-lifecycle-test-")
        self.project_path = Path(self.tmp.name)
        self.fake_codex_exe = self.project_path / "codex.exe"
        self.fake_codex_exe.touch()
        self.fake_agy_exe = self.project_path / "agy.exe"
        self.fake_agy_exe.touch()

    def tearDown(self):
        self.tmp.cleanup()

    # 1. Failed start
    def test_failed_start_validations(self):
        codex = CodexRuntime(self.fake_codex_exe)
        with self.assertRaises(ValueError):
            codex.start("", self.project_path)

        missing_dir = self.project_path / "non_existent_folder"
        with self.assertRaises((NotADirectoryError, FileNotFoundError)):
            codex.start("hello", missing_dir)

        with self.assertRaises(ValueError):
            codex.start("hello", self.project_path, sandbox="invalid-sandbox")

        agy = AntigravityRuntime(self.fake_agy_exe)
        with self.assertRaises(ValueError):
            agy.start("", self.project_path)
        with self.assertRaises((NotADirectoryError, FileNotFoundError)):
            agy.start("hello", missing_dir)

    # 2. Normal exit
    def test_normal_exit_codex(self):
        stream = (
            '{"type":"thread.started","thread_id":"th-123"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"Codex success response"}}\n'
            '{"type":"turn.completed","usage":{"tokens":10}}\n'
        )
        fake = MockProcess(stdout=stream, exit_code=0)
        runtime = CodexRuntime(self.fake_codex_exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake):
            run = runtime.start("Do task", self.project_path, sandbox="workspace-write", approval="never")
            for _ in range(50):
                current = runtime.get(run["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.02)
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["exit_code"], 0)
        self.assertEqual(current["result"], "Codex success response")
        self.assertEqual(current["thread_id"], "th-123")
        # Writer lock released
        project_key = os.path.normcase(str(self.project_path))
        self.assertNotIn(project_key, runtime._writers)

    def test_normal_exit_antigravity(self):
        stream = (
            '{"event":"init","conversation_id":"conv-456"}\n'
            '{"event":"result","result":{"status":"SUCCESS","response":"Agy success response"}}\n'
        )
        fake = MockProcess(stdout=stream, exit_code=0)
        runtime = AntigravityRuntime(self.fake_agy_exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=fake):
            run = runtime.start("Do task", self.project_path, write=True, full_access=True)
            for _ in range(50):
                current = runtime.get(run["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.02)
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["exit_code"], 0)
        self.assertEqual(current["result"], "Agy success response")
        self.assertEqual(current["conversation_id"], "conv-456")
        project_key = os.path.normcase(str(self.project_path))
        self.assertNotIn(project_key, runtime._writers)

    # 3. Timeout
    def test_timeout_codex_stops_process_and_records_error(self):
        fake = MockProcess(stdout="", exit_code=0, delay=5.0)
        runtime = CodexRuntime(self.fake_codex_exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake), \
             patch("core.codex_runtime.stop_process_tree", side_effect=fake.terminate) as mock_stop:
            run = runtime.start("Do task", self.project_path, timeout="1s")
            for _ in range(60):
                current = runtime.get(run["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.03)
        self.assertEqual(current["status"], "failed")
        self.assertTrue(any("timed out after" in e for e in current["errors"]))
        mock_stop.assert_called_once()
        project_key = os.path.normcase(str(self.project_path))
        self.assertNotIn(project_key, runtime._writers)

    def test_timeout_antigravity_stops_process_and_records_error(self):
        fake = MockProcess(stdout="", exit_code=0, delay=5.0)
        runtime = AntigravityRuntime(self.fake_agy_exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=fake), \
             patch("core.antigravity_runtime.stop_process_tree", side_effect=fake.terminate) as mock_stop:
            run = runtime.start("Do task", self.project_path, timeout="1s")
            for _ in range(60):
                current = runtime.get(run["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.03)
        self.assertEqual(current["status"], "failed")
        self.assertTrue(any("timed out after" in e for e in current["errors"]))
        mock_stop.assert_called_once()

    # 4. Stop / Cancellation
    def test_stop_cancellation_codex(self):
        fake = MockProcess(stdout="", exit_code=0, delay=5.0)
        runtime = CodexRuntime(self.fake_codex_exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake), \
             patch("core.codex_runtime.stop_process_tree", side_effect=fake.terminate):
            run = runtime.start("Do task", self.project_path)
            cancelling = runtime.cancel(run["id"])
            self.assertIn(cancelling["status"], {"cancelling", "cancelled"})
            self.assertTrue(cancelling["cancel_requested"])

            for _ in range(60):
                current = runtime.get(run["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.02)
            self.assertEqual(current["status"], "cancelled")
            # Idempotent second cancel
            after = runtime.cancel(run["id"])
            self.assertEqual(after["status"], "cancelled")

    def test_stop_cancellation_antigravity(self):
        fake = MockProcess(stdout="", exit_code=0, delay=5.0)
        runtime = AntigravityRuntime(self.fake_agy_exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=fake), \
             patch("core.antigravity_runtime.stop_process_tree", side_effect=fake.terminate):
            run = runtime.start("Do task", self.project_path)
            cancelling = runtime.cancel(run["id"])
            self.assertIn(cancelling["status"], {"cancelling", "cancelled"})
            self.assertTrue(cancelling["cancel_requested"])

            for _ in range(60):
                current = runtime.get(run["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.02)
            self.assertEqual(current["status"], "cancelled")

    # 5. Consecutive runs (writer lock released)
    def test_consecutive_writer_runs_on_same_project_succeed(self):
        stream = '{"type":"item.completed","item":{"type":"agent_message","text":"first"}}\n'
        fake1 = MockProcess(stdout=stream, exit_code=0)
        runtime = CodexRuntime(self.fake_codex_exe)

        with patch("core.codex_runtime.subprocess.Popen", return_value=fake1):
            run1 = runtime.start("first task", self.project_path, sandbox="workspace-write", approval="never")
            for _ in range(50):
                if runtime.get(run1["id"])["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.02)

        self.assertEqual(runtime.get(run1["id"])["status"], "completed")

        # Second write run on same project must NOT raise "already has an active write-capable agent"
        stream2 = '{"type":"item.completed","item":{"type":"agent_message","text":"second"}}\n'
        fake2 = MockProcess(stdout=stream2, exit_code=0)
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake2):
            run2 = runtime.start("second task", self.project_path, sandbox="workspace-write", approval="never")
            for _ in range(50):
                if runtime.get(run2["id"])["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.02)

        self.assertEqual(runtime.get(run2["id"])["status"], "completed")
        self.assertEqual(runtime.get(run2["id"])["result"], "second")

    # 6. Provider absence
    def test_provider_absence_codex_and_antigravity(self):
        with patch.object(CodexRuntime, "_find_executable", side_effect=FileNotFoundError("Codex CLI was not found")), \
             patch.object(AntigravityRuntime, "_find_executable", side_effect=FileNotFoundError("Antigravity CLI was not found")):
            codex = CodexRuntime(None)
            probe_c = codex.probe()
            self.assertFalse(probe_c["installed"])
            self.assertFalse(probe_c["ready"])
            with self.assertRaises(RuntimeError):
                codex.start("prompt", self.project_path)

            agy = AntigravityRuntime(None)
            probe_a = agy.probe()
            self.assertFalse(probe_a["installed"])
            self.assertFalse(probe_a["ready"])
            with self.assertRaises(RuntimeError):
                agy.start("prompt", self.project_path)

    # 7. Child cleanup
    def test_child_cleanup_terminates_descendants(self):
        # Spawn parent python process that spawns a child sleeper
        child_code = "import time; time.sleep(60)"
        parent_code = (
            "import subprocess,sys,time; "
            f"p=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
            "print(p.pid,flush=True); time.sleep(60)"
        )
        parent = subprocess.Popen(
            [sys.executable, "-c", parent_code],
            stdout=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        child_pid_str = parent.stdout.readline().strip()
        self.assertTrue(child_pid_str.isdigit())
        child_pid = int(child_pid_str)

        try:
            stopped = stop_process_tree(parent, timeout=3)
            self.assertTrue(stopped)
            self.assertIsNotNone(parent.poll())
            self.assertFalse(psutil.pid_exists(child_pid))
        finally:
            if parent.poll() is None:
                parent.kill()
            if psutil.pid_exists(child_pid):
                try:
                    psutil.Process(child_pid).kill()
                except psutil.NoSuchProcess:
                    pass
            parent.stdout.close()

    # 8. Late output does not corrupt terminal state
    def test_late_output_isolation_codex(self):
        runtime = CodexRuntime(self.fake_codex_exe)
        run_id = "test-late-output"
        runtime._runs[run_id] = {
            "id": run_id, "status": "completed", "result": "original final result",
            "errors": [], "events": [], "pid": 1111, "first_event_at": 100.0,
            "first_text_at": 100.0,
        }
        # Simulate late incoming stdout line after completion
        fake_proc = MockProcess(
            stdout='{"type":"item.completed","item":{"type":"agent_message","text":"late mutation attempt"}}\n'
        )
        runtime._read_stdout(run_id, fake_proc)

        current = runtime.get(run_id)
        # Original result must remain untouched
        self.assertEqual(current["result"], "original final result")
        self.assertEqual(current["status"], "completed")

    # 9. Probe caching avoids subprocess spawning during UI polling
    def test_probe_caching_does_not_spawn_subprocess_on_repeated_poll(self):
        codex = CodexRuntime(self.fake_codex_exe)
        with patch.object(codex, "_probe") as mock_probe:
            mock_probe.side_effect = [
                {"returncode": 0, "stdout": "codex 1.0", "stderr": ""},
                {"returncode": 1, "stdout": "", "stderr": "Not logged in"},
            ]
            first = codex.probe()
            self.assertFalse(first["ready"])
            self.assertEqual(mock_probe.call_count, 2)

            # Second poll within TTL should return cached result without calling _probe again
            second = codex.probe()
            self.assertFalse(second["ready"])
            self.assertEqual(mock_probe.call_count, 2)

    # 10. Gemini runtime lifecycle specific validations
    def test_gemini_runtime_lifecycle(self):
        fake_gemini_exe = self.project_path / "gemini.cmd"
        fake_gemini_exe.touch()
        runtime = GeminiRuntime(fake_gemini_exe)
        # Unsupported effort is rejected upfront
        with self.assertRaises(ValueError):
            runtime.start("hello", self.project_path, effort="high")

        # Provider absence handling
        with patch.object(GeminiRuntime, "_find_executable", side_effect=FileNotFoundError("Gemini CLI was not found")):
            missing_rt = GeminiRuntime(None)
            probe_res = missing_rt.probe()
            self.assertFalse(probe_res["installed"])
            self.assertFalse(probe_res["ready"])
            with self.assertRaises(RuntimeError):
                missing_rt.start("hello", self.project_path)


if __name__ == "__main__":
    unittest.main()
