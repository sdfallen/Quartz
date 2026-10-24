import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.codex_runtime import CodexRuntime


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
        prompt = 'You are Codex. "Quartz" icin gorev: kendinizi tanitin. Türkçe.'
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


if __name__ == "__main__":
    unittest.main()
