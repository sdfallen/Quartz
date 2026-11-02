"""
tests/test_tool_workbench_execution.py
Unit tests for isolated process execution in Quartz Tool Workbench:
- Argv schema validation and shell-injection rejection
- Environment sanitization (secret and credential stripping)
- Monotonic deadline and timeout handling
- Output limit bounding and overflow protection
- Cancellation and process-tree termination
- Non-zero exit code reporting
- Workspace artifact discovery and cryptographic hashing
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from core.tool_workbench.contracts import Target, ToolManifest, ToolRequest
from core.tool_workbench.errors import SchemaValidationError
from core.tool_workbench.execution import ToolExecutor


class TestToolWorkbenchExecution(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temp_dir.name).resolve()
        self.executor = ToolExecutor(workspace_root=self.workspace_root)

        # Helper python script tool
        self.script_path = self.workspace_root / "runner.py"
        self.script_path.write_text(
            """
import sys, os, time

op = sys.argv[1] if len(sys.argv) > 1 else "default"

if op in {"echo", "--echo"}:
    # Find --text argument if passed
    text_val = ""
    for i, a in enumerate(sys.argv):
        if a == "--text" and i + 1 < len(sys.argv):
            text_val = sys.argv[i + 1]
    if not text_val and len(sys.argv) > 2:
        text_val = sys.argv[2]
    print(f"OUTPUT_ECHO:{text_val}")
elif op in {"env-check", "--env-check"}:
    for k, v in sorted(os.environ.items()):
        print(f"ENV:{k}={v}")
elif op in {"sleep", "--sleep"}:
    dur = 5.0
    for i, a in enumerate(sys.argv):
        if a == "--duration" and i + 1 < len(sys.argv):
            dur = float(sys.argv[i + 1])
    time.sleep(dur)
    print("SLEEP_DONE")
elif op in {"overflow", "--overflow"}:
    # Output substantial data to trigger overflow
    for _ in range(500):
        print("OVERFLOW_DATA_" * 10)
        sys.stdout.flush()
elif op in {"fail", "--fail"}:
    sys.stderr.write("INTENTIONAL_ERROR\\n")
    sys.stderr.flush()
    sys.exit(42)
elif op in {"create-artifact", "--create-artifact"}:
    filename = "output.txt"
    for i, a in enumerate(sys.argv):
        if a == "--filename" and i + 1 < len(sys.argv):
            filename = sys.argv[i + 1]
    with open(filename, "w", encoding="utf-8") as f:
        f.write("ARTIFACT_CONTENT_HELLO_WORLD")
    print(f"CREATED:{filename}")
elif op in {"spawn-child", "--spawn-child"}:
    import subprocess
    # Use the explicit interpreter: the tool environment deliberately has no PATH.
    # Child output is a handshake proving it actually started before timeout.
    cmd = [sys.executable, "-I", "-S", "-c",
           "import time; print('CHILD_READY', flush=True); time.sleep(20)"]
    p = subprocess.Popen(cmd)
    print(f"CHILD_PID:{p.pid}", flush=True)
    time.sleep(10)
""",
            encoding="utf-8",
        )

        self.manifest = ToolManifest(
            tool_id="test_runner",
            name="Test Runner Script",
            version="1.0.0",
            source_url="https://github.com/example/runner.zip",
            pinned_revision="1.0.0",
            package_digest="abcd1234",
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["test_run"],
            executable_subpath=str(self.script_path),
            supported_operations={
                "echo": {
                    "options": {
                        "text": {"type": "string", "required": True},
                    }
                },
                "env-check": {"options": {}},
                "sleep": {
                    "options": {
                        "duration": {"type": "string", "default": "5.0"},
                    }
                },
                "overflow": {"options": {}},
                "fail": {"options": {}},
                "create-artifact": {
                    "options": {
                        "filename": {"type": "string", "default": "output.txt"},
                    }
                },
                "spawn-child": {"options": {}},
            },
        )

    def tearDown(self):
        self.executor.stop_all()
        self.temp_dir.cleanup()

    def test_execute_echo_success(self):
        """Standard tool execution returns exit 0, status confirmed, and captured output."""
        req = ToolRequest(
            investigation_id="inv-1",
            step_id="step-1",
            operation="echo",
            tool_id="test_runner",
            options={"text": "hello_quartz"},
        )

        receipt = self.executor.execute(self.manifest, str(self.script_path), req)
        self.assertEqual(receipt.status, "confirmed")
        self.assertEqual(receipt.exit_code, 0)
        self.assertIn(b"OUTPUT_ECHO:hello_quartz", receipt.stdout)
        self.assertTrue(receipt.cleanup_receipt["process_exited"])

    def test_argv_schema_validation_rejects_unknown_option(self):
        """Passing an unrecognized option raises SchemaValidationError."""
        req = ToolRequest(
            investigation_id="inv-1",
            step_id="step-1",
            operation="echo",
            tool_id="test_runner",
            options={"text": "ok", "unrecognized_flag": "bad"},
        )

        with self.assertRaises(SchemaValidationError) as ctx:
            self.executor.execute(self.manifest, str(self.script_path), req)
        self.assertIn("Unrecognized option", str(ctx.exception))

    def test_argv_schema_validation_rejects_shell_injection(self):
        """Options containing shell injection characters are rejected."""
        dangerous = ["text; rm -rf /", "text | cat", "text & calc.exe", "text `dir`", "text\nevil"]
        for bad_val in dangerous:
            req = ToolRequest(
                investigation_id="inv-1",
                step_id="step-1",
                operation="echo",
                tool_id="test_runner",
                options={"text": bad_val},
            )
            with self.assertRaises(SchemaValidationError) as ctx:
                self.executor.execute(self.manifest, str(self.script_path), req)
            self.assertIn("Disallowed shell character", str(ctx.exception))

    def test_environment_sanitization_strips_secrets(self):
        """Environment variables containing API_KEY, TOKEN, SECRET, PASSWORD are not passed."""
        os.environ["QUARTZ_TEST_API_KEY"] = "super_secret_api_key_12345"
        os.environ["GITHUB_AUTH_TOKEN"] = "ghp_secret_token_9999"
        os.environ["DATABASE_PASSWORD"] = "p@ssword_hidden"

        try:
            req = ToolRequest(
                investigation_id="inv-1",
                step_id="step-1",
                operation="env-check",
                tool_id="test_runner",
            )
            receipt = self.executor.execute(self.manifest, str(self.script_path), req)
            self.assertEqual(receipt.status, "confirmed")
            output_str = receipt.stdout.decode("utf-8", "replace")

            self.assertNotIn("super_secret_api_key_12345", output_str)
            self.assertNotIn("ghp_secret_token_9999", output_str)
            self.assertNotIn("p@ssword_hidden", output_str)
            self.assertNotIn("QUARTZ_TEST_API_KEY", output_str)
            self.assertNotIn("GITHUB_AUTH_TOKEN", output_str)
        finally:
            os.environ.pop("QUARTZ_TEST_API_KEY", None)
            os.environ.pop("GITHUB_AUTH_TOKEN", None)
            os.environ.pop("DATABASE_PASSWORD", None)

    def test_timeout_handling(self):
        """Execution exceeding monotonic deadline terminates process tree and reports timeout."""
        req = ToolRequest(
            investigation_id="inv-1",
            step_id="step-1",
            operation="sleep",
            tool_id="test_runner",
            options={"duration": "5.0"},
            deadline_monotonic=time.monotonic() + 0.3,  # Strict 0.3s timeout
        )

        start = time.monotonic()
        receipt = self.executor.execute(self.manifest, str(self.script_path), req)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 2.5)  # Definitely not 5s
        self.assertEqual(receipt.status, "timeout")
        self.assertTrue(receipt.cleanup_receipt["process_exited"])
        self.assertTrue(any("exceeded deadline" in lim for lim in receipt.limitations))

    def test_output_limit_overflow(self):
        """Output exceeding max_output_bytes is bounded and reports output_limit status."""
        req = ToolRequest(
            investigation_id="inv-1",
            step_id="step-1",
            operation="overflow",
            tool_id="test_runner",
            max_output_bytes=512,  # Bounded to 512 bytes
        )

        receipt = self.executor.execute(self.manifest, str(self.script_path), req)
        self.assertEqual(receipt.status, "output_limit")
        self.assertLessEqual(len(receipt.stdout), 512)
        self.assertTrue(any("Output truncated" in lim for lim in receipt.limitations))

    def test_cancellation(self):
        """Triggering cancel_event during execution terminates process immediately."""
        cancel_ev = threading.Event()

        req = ToolRequest(
            investigation_id="inv-1",
            step_id="step-1",
            operation="sleep",
            tool_id="test_runner",
            options={"duration": "5.0"},
        )

        # Trigger cancel shortly after start
        threading.Timer(0.2, cancel_ev.set).start()

        start = time.monotonic()
        receipt = self.executor.execute(self.manifest, str(self.script_path), req, cancel_event=cancel_ev)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 2.5)
        self.assertEqual(receipt.status, "cancelled")
        self.assertTrue(receipt.cleanup_receipt["process_exited"])

    def test_exit_code_failure_reporting(self):
        """Non-zero exit code is recorded with failed status."""
        req = ToolRequest(
            investigation_id="inv-1",
            step_id="step-1",
            operation="fail",
            tool_id="test_runner",
        )

        receipt = self.executor.execute(self.manifest, str(self.script_path), req)
        self.assertEqual(receipt.status, "failed")
        self.assertEqual(receipt.exit_code, 42)
        self.assertIn(b"INTENTIONAL_ERROR", receipt.stderr)

    def test_artifact_generation_and_hashing(self):
        """Files created in workspace are detected, hashed with SHA-256, and recorded in receipt."""
        req = ToolRequest(
            investigation_id="inv-1",
            step_id="step-1",
            operation="create-artifact",
            tool_id="test_runner",
            options={"filename": "artifact_report.txt"},
        )

        receipt = self.executor.execute(self.manifest, str(self.script_path), req)
        self.assertEqual(receipt.status, "confirmed")
        self.assertGreaterEqual(len(receipt.artifacts), 1)

        art = next(a for a in receipt.artifacts if a["path"] == "artifact_report.txt")
        self.assertEqual(art["size"], len("ARTIFACT_CONTENT_HELLO_WORLD"))
        self.assertTrue(art["sha256"])

    def test_child_process_tree_termination(self):
        """Stopping process tree terminates child processes spawned by tool."""
        req = ToolRequest(
            investigation_id="inv-1",
            step_id="step-1",
            operation="spawn-child",
            tool_id="test_runner",
            # Allow both Python interpreters to start, then exercise the real deadline.
            deadline_monotonic=time.monotonic() + 2.0,
        )

        receipt = self.executor.execute(self.manifest, str(self.script_path), req)
        diagnostics = {"receipt": receipt.to_dict(), "stdout": receipt.stdout.decode("utf-8", "replace"),
                       "stderr": receipt.stderr.decode("utf-8", "replace")}
        self.assertEqual(receipt.status, "timeout", diagnostics)
        self.assertIn(b"CHILD_READY", receipt.stdout, diagnostics)
        self.assertRegex(receipt.stdout, rb"CHILD_PID:[0-9]+", diagnostics)
        import psutil
        child_line = next(line for line in receipt.stdout.splitlines() if line.startswith(b"CHILD_PID:"))
        child_pid = int(child_line.split(b":", 1)[1])
        self.assertFalse(psutil.pid_exists(child_pid), diagnostics)
        self.assertFalse(psutil.pid_exists(receipt.process_identity["pid"]), diagnostics)
        self.assertEqual(receipt.cleanup_receipt["status"], "confirmed", diagnostics)
        self.assertTrue(receipt.cleanup_receipt["process_exited"], diagnostics)
        self.assertTrue(receipt.cleanup_receipt["children_reaped"], diagnostics)
        self.assertTrue(receipt.cleanup_receipt["drains_finished"], diagnostics)


if __name__ == "__main__":
    unittest.main()
