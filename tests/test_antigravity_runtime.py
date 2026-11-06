import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.antigravity_runtime import AntigravityRuntime
from core.process_tree import CREATE_SUSPENDED


class FakeProcess:
    def __init__(self, stdout, stderr="", exit_code=0):
        self.pid = 5252
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


class AntigravityRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exe = self.root / "agy.exe"
        self.exe.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def test_stream_json_tracks_conversation_result_usage_and_pid(self):
        stream = (
            '{"event":"init","conversation_id":"conversation-1","init":{"permission_mode":"request-review"}}\n'
            '{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"done"}}\n'
            '{"event":"result","result":{"conversation_id":"conversation-1","status":"SUCCESS","response":"done","usage":{"total_tokens":7}}}\n'
        )
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)) as popen:
            started = runtime.start("inspect", self.root)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["pid"], 5252)
        self.assertEqual(current["conversation_id"], "conversation-1")
        self.assertEqual(current["result"], "done")
        self.assertEqual(current["usage"]["total_tokens"], 7)
        command = popen.call_args.args[0]
        self.assertIn("-p", command)
        self.assertIn("stream-json", command)
        self.assertIn("--sandbox", command)
        self.assertIn("plan", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_model_and_effort_are_explicit_cli_overrides(self):
        runtime = AntigravityRuntime(self.exe)
        fake = FakeProcess('{"event":"result","result":{"status":"SUCCESS","response":"ok"}}\n')
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=fake) as popen:
            run = runtime.start("inspect", self.root, model="gemini-3.8-flash-low", effort="low")
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--model")+1], "gemini-3.8-flash-low")
        self.assertNotIn("--effort", command)  # encoded variant rejected an extra CLI effort
        self.assertIn("--sandbox", command)
        self.assertNotIn("--dangerously-skip-permissions", command)
        self.assertEqual(run["model"], "gemini-3.8-flash-low")

    def test_encoded_effort_mismatch_fails_before_process(self):
        runtime=AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen") as popen:
            with self.assertRaises(ValueError): runtime.start("inspect",self.root,model="gemini-3.8-flash-low",effort="high")
            popen.assert_not_called()

    def test_resume_uses_conversation_id(self):
        runtime = AntigravityRuntime(self.exe)
        runtime._runs["old"] = {
            "id": "old", "status": "completed", "conversation_id": "conversation-2",
            "project": str(self.root), "sandbox": "sandbox", "errors": [], "events": [],
        }
        with patch.object(runtime, "start", return_value={"id": "new"}) as start:
            runtime.resume("old", "continue")
        self.assertEqual(start.call_args.kwargs["conversation_id"], "conversation-2")
        self.assertFalse(start.call_args.kwargs["write"])

    def test_permission_denial_is_visible_when_success_has_no_response(self):
        stream = (
            '{"event":"result","result":{"status":"SUCCESS","response":"",'
            '"denied_actions":[{"action":"command"}]}}\n'
        )
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("inspect", self.root)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)
        self.assertEqual(current["status"], "failed")
        self.assertTrue(any("permission policy denied" in item for item in current["errors"]))

    def test_denied_action_fails_even_when_response_text_exists(self):
        stream = ('{"event":"result","result":{"status":"SUCCESS","response":"I tried",'
                  '"denied_actions":[{"action":"command"}]}}\n')
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("run test", self.root, write=True, full_access=True)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)
        self.assertEqual(current["status"], "failed")
        self.assertEqual(current["denied_actions"][0]["action"], "command")

    def test_completed_edit_file_event_reports_changed_path(self):
        changed = str(self.root / "edited.txt").replace("\\", "\\\\")
        stream = (
            '{"event":"step_update","step_update":{"state":"DONE","step_type":"tool",'
            '"tool_name":"edit_file","tool_info":{"parameters":{"Path":"' + changed + '"}}}}\n'
            '{"event":"result","result":{"status":"SUCCESS","response":"edited"}}\n'
        )
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("edit", self.root, write=True, full_access=True)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)
        self.assertEqual(current["files_changed"], [str(self.root / "edited.txt")])

    def test_write_mode_uses_dangerously_skip_permissions_without_sandbox(self):
        stream = '{"event":"result","result":{"status":"SUCCESS","response":"created"}}\n'
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)) as popen:
            started = runtime.start("create file", self.root, write=True, full_access=True)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)
        self.assertEqual(current["status"], "completed")
        command = popen.call_args.args[0]
        self.assertIn("--dangerously-skip-permissions", command)
        self.assertIn("accept-edits", command)
        self.assertNotIn("--sandbox", command)

    def test_project_write_is_not_silently_upgraded(self):
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen") as popen:
            with self.assertRaises(PermissionError):
                runtime.start("edit", self.root, write=True)
        popen.assert_not_called()

    def test_full_access_single_writer_rule(self):
        runtime = AntigravityRuntime(self.exe)
        fake = FakeProcess("")
        fake.wait = lambda timeout=None: time.sleep(0.3) or 0
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=fake):
            runtime.start("edit", self.root, full_access=True)
            with self.assertRaises(RuntimeError):
                runtime.start("second", self.root, full_access=True)

    def test_p0_3_oracle_fields_record_command_exit_codes_file_changes_and_error_events(self):
        changed = str(self.root / "calc.py").replace("\\", "\\\\")
        stream = (
            '{"event":"init","conversation_id":"conv-oracle"}\n'
            '{"event":"step_update","step_update":{"id":"s1","state":"RUNNING","tool_name":"run_command","tool_info":{"parameters":{"CommandLine":"pytest -q"}}}}\n'
            '{"event":"step_update","step_update":{"id":"s1","state":"ERROR","tool_name":"run_command","tool_info":{"output":"Command exited with code 1\\n1 failed"}}}\n'
            '{"event":"step_update","step_update":{"id":"s2","state":"DONE","tool_name":"edit_file","tool_info":{"parameters":{"Path":"' + changed + '"}}}}\n'
            '{"event":"step_update","step_update":{"id":"s3","state":"DONE","tool_name":"run_command","tool_info":{"parameters":{"CommandLine":"pytest -q"},"exit_code":0,"output":"1 passed"}}}\n'
            '{"event":"result","result":{"conversation_id":"conv-oracle","status":"SUCCESS","response":"Fixed calc.py"}}\n'
        )
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("fix", self.root, write=True, full_access=True)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["command_exit_codes"], [1, 0])
        self.assertEqual(len(current["command_results"]), 2)
        self.assertEqual(current["command_results"][0]["seq"], 1)
        self.assertEqual(current["command_results"][0]["command"], "pytest -q")
        self.assertEqual(current["command_results"][0]["exit_code"], 1)
        self.assertFalse(current["command_results"][0]["ok"])
        self.assertEqual(current["command_results"][1]["seq"], 3)
        self.assertEqual(current["command_results"][1]["exit_code"], 0)
        self.assertTrue(current["command_results"][1]["ok"])
        self.assertEqual(current["file_changes"], [{
            "seq": 2,
            "path": str(self.root / "calc.py"),
            "kind": "update",
            "tool": "edit_file",
            "state": "DONE",
        }])
        self.assertEqual(len(current["error_events"]), 1)
        self.assertEqual(current["error_events"][0]["seq"], 1)
        self.assertEqual(current["error_events"][0]["source"], "command")
        self.assertEqual(current["error_events"][0]["kind"], "nonzero_exit")
        self.assertEqual(current["error_events"][0]["exit_code"], 1)
        self.assertEqual(current["errors"], [])

    def test_p1_3_readonly_run_detects_and_fails_unauthorized_file_write(self):
        changed = str(self.root / "readonly_probe.txt").replace("\\", "\\\\")
        stream = (
            '{"event":"init","conversation_id":"conv-ro"}\n'
            '{"event":"step_update","step_update":{"id":"s1","state":"DONE","step_type":"tool",'
            '"tool_name":"write_file","tool_info":{"parameters":{"Path":"' + changed + '"}}}}\n'
            '{"event":"result","result":{"conversation_id":"conv-ro","status":"SUCCESS","response":"Wrote file"}}\n'
        )
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("inspect only", self.root, write=False, full_access=False)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current["status"], "failed")
        self.assertTrue(current["unauthorized_write_detected"])
        self.assertEqual(current["unauthorized_files_changed"], [str(self.root / "readonly_probe.txt")])
        self.assertTrue(any(e["kind"] == "unauthorized_readonly_write" for e in current["error_events"]))
        self.assertTrue(any(d.get("reason") == "read_only_violation" for d in current["denied_actions"]))

    def test_p1_3_readonly_run_does_not_blame_reader_for_concurrent_writer_disk_changes(self):
        stream = (
            '{"event":"init","conversation_id":"conv-ro-clean"}\n'
            '{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"Reviewed safely."}}\n'
            '{"event":"result","result":{"conversation_id":"conv-ro-clean","status":"SUCCESS","response":"Reviewed safely."}}\n'
        )
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            # Concurrent writer modifies a file in the project directory during the reader's run
            (self.root / "writer_owned.txt").write_text("concurrent writer change\n", encoding="utf-8")
            started = runtime.start("review", self.root, write=False, full_access=False)
            for _ in range(100):
                current = runtime.get(started["id"])
                if current["status"] in runtime.TERMINAL:
                    break
                time.sleep(0.01)

        self.assertEqual(current["status"], "completed")
        self.assertFalse(current["unauthorized_write_detected"])
        self.assertEqual(current["unauthorized_files_changed"], [])

    def test_r2_readonly_run_allows_quartz_chat_tool_temp_workspace_writes_but_blocks_project_writes(self):
        runtime = AntigravityRuntime(self.exe)
        with tempfile.TemporaryDirectory(prefix="quartz-chat-tool-") as scratch_tmp:
            scratch_dir = Path(scratch_tmp)
            scratch_note = str(scratch_dir / "operator_notes.md").replace("\\", "\\\\")
            # 1) Writing inside quartz-chat-tool-* temporary workspace is separated into scratch_files_changed
            stream_scratch = (
                '{"event":"init","conversation_id":"conv-r2-ok"}\n'
                '{"event":"step_update","step_update":{"id":"s1","state":"DONE","step_type":"tool",'
                '"tool_name":"write_file","tool_info":{"parameters":{"Path":"' + scratch_note + '"}}}}\n'
                '{"event":"result","result":{"conversation_id":"conv-r2-ok","status":"SUCCESS","response":"Operator done"}}\n'
            )
            with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream_scratch)):
                started = runtime.start("desktop operator", scratch_dir, write=False, full_access=False)
                for _ in range(100):
                    current = runtime.get(started["id"])
                    if current["status"] in runtime.TERMINAL:
                        break
                    time.sleep(0.01)
            self.assertEqual(current["status"], "completed")
            self.assertFalse(current["unauthorized_write_detected"])
            self.assertEqual(current["files_changed"], [])
            self.assertEqual(current["scratch_files_changed"], [str(scratch_dir / "operator_notes.md")])
            self.assertEqual(current["unauthorized_files_changed"], [])

            # 2) Escaping quartz-chat-tool-* to write into the user's project directory IS a violation
            escaped_path = str(self.root / "escaped.py").replace("\\", "\\\\")
            stream_escape = (
                '{"event":"init","conversation_id":"conv-r2-escape"}\n'
                '{"event":"step_update","step_update":{"id":"s1","state":"DONE","step_type":"tool",'
                '"tool_name":"write_file","tool_info":{"parameters":{"Path":"' + escaped_path + '"}}}}\n'
                '{"event":"result","result":{"conversation_id":"conv-r2-escape","status":"SUCCESS","response":"Escaped"}}\n'
            )
            with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream_escape)):
                started2 = runtime.start("desktop operator", scratch_dir, write=False, full_access=False)
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
            '{"event":"init","conversation_id":"conv-r3"}\n'
            '{"event":"result","result":{"conversation_id":"conv-r3","status":"SUCCESS","response":"ok"}}\n'
        )
        runtime = AntigravityRuntime(self.exe)

        def fake_bind(process, *, resume=False, error_sink=None):
            if callable(error_sink):
                error_sink("Simulated AssignProcessToJobObject failure")
            return False

        with patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)) as popen, \
             patch("core.antigravity_runtime.bind_kill_on_close_job", side_effect=fake_bind) as bind_mock:
            started = runtime.start("inspect", self.root, write=False, full_access=False)
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
        runtime = AntigravityRuntime(self.exe)
        isolated_temp = self.root / "isolated_temp"
        user_project = self.root / "user_project"
        outside_docs = self.root / "outside_docs"
        isolated_temp.mkdir(parents=True, exist_ok=True)
        user_project.mkdir(parents=True, exist_ok=True)
        outside_docs.mkdir(parents=True, exist_ok=True)
        leak_file = outside_docs / "leak.txt"
        leak_str = str(leak_file).replace("\\", "\\\\")
        stream = (
            '{"event":"init","conversation_id":"conv-p1"}\n'
            '{"event":"step_update","step_update":{"id":"s1","state":"DONE","step_type":"tool",'
            '"tool_name":"write_file","tool_info":{"parameters":{"Path":"' + leak_str + '"}}}}\n'
            '{"event":"result","result":{"conversation_id":"conv-p1","status":"SUCCESS","response":"Wrote outside"}}\n'
        )
        with patch("core.antigravity_runtime.tempfile.gettempdir", return_value=str(isolated_temp)), \
             patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream)):
            started = runtime.start("inspect", user_project, write=False, full_access=False)
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
        runtime = AntigravityRuntime(self.exe)
        isolated_temp = self.root / "isolated_temp"
        user_project = self.root / "user_project"
        subfolder = user_project / "quartz-chat-tool-sub"
        isolated_temp.mkdir(parents=True, exist_ok=True)
        subfolder.mkdir(parents=True, exist_ok=True)

        # 1) User project writing to a file in TEMP is NOT exempt
        temp_file = isolated_temp / "random_temp.txt"
        temp_str = str(temp_file).replace("\\", "\\\\")
        stream_temp = (
            '{"event":"init","conversation_id":"conv-p2a-temp"}\n'
            '{"event":"step_update","step_update":{"id":"s1","state":"DONE","step_type":"tool",'
            '"tool_name":"write_file","tool_info":{"parameters":{"Path":"' + temp_str + '"}}}}\n'
            '{"event":"result","result":{"conversation_id":"conv-p2a-temp","status":"SUCCESS","response":"Wrote temp"}}\n'
        )
        with patch("core.antigravity_runtime.tempfile.gettempdir", return_value=str(isolated_temp)), \
             patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream_temp)):
            started1 = runtime.start("inspect", user_project, write=False, full_access=False)
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
            '{"event":"init","conversation_id":"conv-p2a-sub"}\n'
            '{"event":"step_update","step_update":{"id":"s1","state":"DONE","step_type":"tool",'
            '"tool_name":"write_file","tool_info":{"parameters":{"Path":"' + sub_str + '"}}}}\n'
            '{"event":"result","result":{"conversation_id":"conv-p2a-sub","status":"SUCCESS","response":"Wrote sub"}}\n'
        )
        with patch("core.antigravity_runtime.tempfile.gettempdir", return_value=str(isolated_temp)), \
             patch("core.antigravity_runtime.subprocess.Popen", return_value=FakeProcess(stream_sub)):
            started2 = runtime.start("inspect", user_project, write=False, full_access=False)
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
