import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.codex_runtime import CodexRuntime
from core.process_tree import CREATE_SUSPENDED


class CaptureStdin(io.StringIO):
    def close(self):
        self.was_closed = True


class FakeProcess:
    def __init__(self, stdout, stderr="", exit_code=0):
        self.pid = 4242
        self.stdin = CaptureStdin()
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self._code = exit_code
        self.terminated = False

    def wait(self, timeout=None):
        return self._code

    def poll(self):
        return self._code if self.terminated else None

    def terminate(self):
        self.terminated = True
        self._code = 1

    def kill(self):
        self.terminate()


class CodexRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exe = self.root / "codex.exe"
        self.exe.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def test_jsonl_run_tracks_real_pid_thread_result_and_usage(self):
        stream = (
            '{"type":"thread.started","thread_id":"thread-1"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":2}}\n'
        )
        fake = FakeProcess(stream)
        runtime = CodexRuntime(self.exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen:
            started = runtime.start("inspect", self.root)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["pid"], 4242)
        self.assertEqual(current["thread_id"], "thread-1")
        self.assertEqual(current["result"], "done")
        command = popen.call_args.args[0]
        self.assertIn("--json", command)
        self.assertIn("read-only", command)
        self.assertNotIn("inspect", command)
        self.assertEqual(fake.stdin.getvalue(), "inspect")

    def test_prompt_with_quotes_and_unicode_is_sent_through_stdin(self):
        prompt = 'You are Codex. "SpeS" icin gorev: kendinizi tanitin. Türkçe.'
        fake = FakeProcess(
            '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
        )
        runtime = CodexRuntime(self.exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen:
            started = runtime.start(prompt, self.root)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current["status"], "completed")
        command = popen.call_args.args[0]
        self.assertEqual(command[-1], "-")
        self.assertNotIn(prompt, command)
        self.assertEqual(fake.stdin.getvalue(), prompt)

    def test_model_and_effort_are_explicit_cli_overrides(self):
        runtime = CodexRuntime(self.exe)
        fake = FakeProcess('{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n')
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen:
            run = runtime.start("inspect", self.root, model="gpt-6-luna", effort="low")
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("-m")+1], "gpt-6-luna")
        self.assertIn('model_reasoning_effort="low"', command)
        self.assertEqual(run["model"], "gpt-6-luna")
        self.assertEqual(run["effort"], "low")

    def test_single_writer_rule_rejects_second_writer(self):
        runtime = CodexRuntime(self.exe)
        fake = FakeProcess("")
        fake.wait = lambda timeout=None: time.sleep(0.3) or 0
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake):
            runtime.start("write", self.root, sandbox="workspace-write", approval="on-request")
            with self.assertRaises(RuntimeError):
                runtime.start("second", self.root, sandbox="workspace-write", approval="on-request")

    def test_project_write_uses_auto_review_without_conflicting_sandbox_flag(self):
        runtime = CodexRuntime(self.exe)
        fake = FakeProcess('{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n')
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake) as popen:
            runtime.start("write", self.root, sandbox="workspace-write", approval="on-request")
        command = popen.call_args.args[0]
        self.assertIn("--approve-for-me", command)
        self.assertNotIn("--sandbox", command)

    def test_full_access_is_also_a_writer(self):
        runtime = CodexRuntime(self.exe)
        fake = FakeProcess("")
        fake.wait = lambda timeout=None: time.sleep(0.3) or 0
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake):
            runtime.start("write", self.root, sandbox="danger-full-access")
            with self.assertRaises(RuntimeError):
                runtime.start("second", self.root, sandbox="danger-full-access")

    @unittest.skipUnless(os.name == "nt", "Windows launcher behavior")
    def test_cmd_launcher_uses_comspec_without_shell_true(self):
        cmd = self.root / "codex.cmd"
        cmd.touch()
        runtime = CodexRuntime(cmd)
        built = runtime._command(["--version"])
        self.assertEqual(Path(built[0]).name.lower(), Path(os.environ.get("COMSPEC", "cmd.exe")).name.lower())
        self.assertIn("/c", [part.lower() for part in built])

    def test_p0_3_oracle_fields_record_command_exit_codes_file_changes_and_error_events(self):
        stream = (
            '{"type":"thread.started","thread_id":"th-oracle"}\n'
            '{"type":"item.completed","item":{"type":"command_execution","command":"pytest -q","exit_code":1,"aggregated_output":"1 failed"}}\n'
            '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"calc.py","kind":"update"}]}}\n'
            '{"type":"item.completed","item":{"type":"command_execution","command":"pytest -q","exit_code":0,"aggregated_output":"1 passed"}}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"Fixed calc.py and tests pass."}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n'
        )
        runtime = CodexRuntime(self.exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("fix bug", self.root, sandbox="workspace-write", approval="on-request")
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["command_exit_codes"], [1, 0])
        self.assertEqual(len(current["command_results"]), 2)
        self.assertEqual(current["command_results"][0]["seq"], 1)
        self.assertFalse(current["command_results"][0]["ok"])
        self.assertEqual(current["command_results"][0]["exit_code"], 1)
        self.assertEqual(current["command_results"][1]["seq"], 3)
        self.assertTrue(current["command_results"][1]["ok"])
        self.assertEqual(current["command_results"][1]["exit_code"], 0)
        self.assertEqual(current["file_changes"], [{
            "seq": 2,
            "path": "calc.py",
            "kind": "update",
            "tool": "file_change",
            "state": "DONE",
        }])
        self.assertEqual(current["files_changed"], ["calc.py"])
        self.assertEqual(len(current["error_events"]), 1)
        self.assertEqual(current["error_events"][0]["seq"], 1)
        self.assertEqual(current["error_events"][0]["source"], "command")
        self.assertEqual(current["error_events"][0]["kind"], "nonzero_exit")
        self.assertEqual(current["error_events"][0]["exit_code"], 1)
        # Internal command failure must not pollute top-level runtime errors list when repaired
        self.assertEqual(current["errors"], [])

    def test_p1_3_readonly_run_detects_and_fails_unauthorized_file_write(self):
        stream = (
            '{"type":"thread.started","thread_id":"th-ro"}\n'
            '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"leaked.py","kind":"add"}]}}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"Created leaked.py"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":4,"output_tokens":2}}\n'
        )
        runtime = CodexRuntime(self.exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("inspect", self.root, sandbox="read-only")
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current["status"], "failed")
        self.assertTrue(current["unauthorized_write_detected"])
        self.assertEqual(current["unauthorized_files_changed"], ["leaked.py"])
        self.assertTrue(any(e["kind"] == "unauthorized_readonly_write" for e in current["error_events"]))

    def test_p1_3_readonly_run_does_not_blame_reader_for_concurrent_writer_disk_changes(self):
        stream = (
            '{"type":"thread.started","thread_id":"th-ro-clean"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"Read-only check ok"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":4,"output_tokens":2}}\n'
        )
        runtime = CodexRuntime(self.exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            (self.root / "writer_owned.txt").write_text("concurrent writer change\n", encoding="utf-8")
            started = runtime.start("inspect", self.root, sandbox="read-only")
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current["status"], "completed")
        self.assertFalse(current["unauthorized_write_detected"])
        self.assertEqual(current["unauthorized_files_changed"], [])

    def test_r2_readonly_run_allows_quartz_chat_tool_temp_workspace_writes_but_blocks_project_writes(self):
        runtime = CodexRuntime(self.exe)
        with tempfile.TemporaryDirectory(prefix="quartz-chat-tool-") as scratch_tmp:
            scratch_dir = Path(scratch_tmp)
            # 1) Writing inside quartz-chat-tool-* temporary workspace is separated into scratch_files_changed
            stream_scratch = (
                '{"type":"thread.started","thread_id":"th-r2-ok"}\n'
                '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"plan.md","kind":"add"}]}}\n'
                '{"type":"item.completed","item":{"type":"agent_message","text":"Desktop plan ready"}}\n'
                '{"type":"turn.completed","usage":{"input_tokens":4,"output_tokens":2}}\n'
            )
            with patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream_scratch)):
                started = runtime.start("desktop operator", scratch_dir, sandbox="read-only")
                for _ in range(100):
                    current = runtime.get(started["id"])
                    if current["status"] in runtime.TERMINAL:
                        break
                    time.sleep(0.01)
            self.assertEqual(current["status"], "completed")
            self.assertFalse(current["unauthorized_write_detected"])
            self.assertEqual(current["files_changed"], [])
            self.assertEqual(current["scratch_files_changed"], ["plan.md"])
            self.assertEqual(current["unauthorized_files_changed"], [])

            # 2) Escaping quartz-chat-tool-* to write into the user's project directory IS a violation
            escaped_path = str(self.root / "escaped.py").replace("\\", "\\\\")
            stream_escape = (
                '{"type":"thread.started","thread_id":"th-r2-escape"}\n'
                '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"' + escaped_path + '","kind":"add"}]}}\n'
                '{"type":"item.completed","item":{"type":"agent_message","text":"Escaped"}}\n'
                '{"type":"turn.completed","usage":{"input_tokens":4,"output_tokens":2}}\n'
            )
            with patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream_escape)):
                started2 = runtime.start("desktop operator", scratch_dir, sandbox="read-only")
                for _ in range(100):
                    current2 = runtime.get(started2["id"])
                    if current2["status"] in runtime.TERMINAL:
                        break
                    time.sleep(0.01)
            self.assertEqual(current2["status"], "failed")
            self.assertTrue(current2["unauthorized_write_detected"])
            self.assertEqual(current2["unauthorized_files_changed"], [str(self.root / "escaped.py")])
            self.assertEqual(current2["scratch_files_changed"], [])

    def test_r3_start_uses_create_suspended_and_records_job_assignment_failure(self):
        stream = (
            '{"type":"thread.started","thread_id":"th-r3"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":2}}\n'
        )
        runtime = CodexRuntime(self.exe)

        def fake_bind(process, *, resume=False, error_sink=None):
            if callable(error_sink):
                error_sink("Simulated AssignProcessToJobObject failure")
            return False

        with patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream)) as popen, \
             patch("core.codex_runtime.bind_kill_on_close_job", side_effect=fake_bind) as bind_mock:
            started = runtime.start("inspect", self.root, sandbox="read-only")
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        if os.name == "nt":
            self.assertTrue(bool(popen.call_args.kwargs.get("creationflags", 0) & CREATE_SUSPENDED))
        self.assertTrue(bind_mock.call_args.kwargs.get("resume"))
        self.assertFalse(current["job_bound"])
        self.assertEqual(current["job_assignment_error"], "Simulated AssignProcessToJobObject failure")
        self.assertTrue(any(e["kind"] == "job_assignment_failed" for e in current["error_events"]))

    def test_p1_readonly_write_outside_project_and_outside_temp_sets_unauthorized_write_detected(self):
        runtime = CodexRuntime(self.exe)
        isolated_temp = self.root / "isolated_temp"
        user_project = self.root / "user_project"
        outside_docs = self.root / "outside_docs"
        isolated_temp.mkdir(parents=True, exist_ok=True)
        user_project.mkdir(parents=True, exist_ok=True)
        outside_docs.mkdir(parents=True, exist_ok=True)
        leak_file = outside_docs / "leak.txt"
        leak_str = str(leak_file).replace("\\", "\\\\")
        stream = (
            '{"type":"thread.started","thread_id":"th-p1"}\n'
            '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"' + leak_str + '","kind":"add"}]}}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"Wrote outside project and temp"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":4,"output_tokens":2}}\n'
        )
        with patch("core.codex_runtime.tempfile.gettempdir", return_value=str(isolated_temp)), \
             patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("inspect", user_project, sandbox="read-only")
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current["status"], "failed")
        self.assertTrue(current["unauthorized_write_detected"])
        self.assertEqual(current["unauthorized_files_changed"], [str(leak_file)])
        self.assertEqual(current["scratch_files_changed"], [])
        self.assertTrue(any("modified file without write permission" in err for err in current["errors"]))

    def test_p2a_user_project_does_not_exempt_temp_files_or_quartz_chat_tool_subfolders(self):
        runtime = CodexRuntime(self.exe)
        isolated_temp = self.root / "isolated_temp"
        user_project = self.root / "user_project"
        subfolder = user_project / "quartz-chat-tool-sub"
        isolated_temp.mkdir(parents=True, exist_ok=True)
        subfolder.mkdir(parents=True, exist_ok=True)

        # 1) User project writing to a file in TEMP is NOT exempt
        temp_file = isolated_temp / "random_temp.txt"
        temp_str = str(temp_file).replace("\\", "\\\\")
        stream_temp = (
            '{"type":"thread.started","thread_id":"th-p2a-temp"}\n'
            '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"' + temp_str + '","kind":"add"}]}}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"Wrote to temp"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":4,"output_tokens":2}}\n'
        )
        with patch("core.codex_runtime.tempfile.gettempdir", return_value=str(isolated_temp)), \
             patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream_temp)):
            started1 = runtime.start("inspect", user_project, sandbox="read-only")
            for _ in range(100):
                current1 = runtime.get(started1["id"])
                if current1["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current1["status"], "failed")
        self.assertTrue(current1["unauthorized_write_detected"])
        self.assertEqual(current1["unauthorized_files_changed"], [str(temp_file)])
        self.assertEqual(current1["scratch_files_changed"], [])

        # 2) User project writing to a "quartz-chat-tool-*" subfolder inside the project is NOT exempt
        sub_file = subfolder / "a.py"
        sub_str = str(sub_file).replace("\\", "\\\\")
        stream_sub = (
            '{"type":"thread.started","thread_id":"th-p2a-sub"}\n'
            '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"' + sub_str + '","kind":"add"}]}}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"Wrote to subfolder"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":4,"output_tokens":2}}\n'
        )
        with patch("core.codex_runtime.tempfile.gettempdir", return_value=str(isolated_temp)), \
             patch("core.codex_runtime.subprocess.Popen", return_value=FakeProcess(stream_sub)):
            started2 = runtime.start("inspect", user_project, sandbox="read-only")
            for _ in range(100):
                current2 = runtime.get(started2["id"])
                if current2["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current2["status"], "failed")
        self.assertTrue(current2["unauthorized_write_detected"])
        self.assertEqual(current2["unauthorized_files_changed"], [str(sub_file)])
        self.assertEqual(current2["scratch_files_changed"], [])


if __name__ == "__main__":
    unittest.main()
