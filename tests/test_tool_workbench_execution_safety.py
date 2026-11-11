"""Owned local processes and event-controlled regressions; no downloads/providers/UI."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import psutil
from core.tool_workbench.contracts import Target, ToolManifest, ToolRequest
from core.tool_workbench.errors import CancellationError, ExecutionError, SchemaValidationError, TimeoutExpiredError
from core.tool_workbench.execution import ToolExecutor


class ExecutionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quartz_execution_safety_")
        self.root = Path(self.temp.name)
        self.executor = ToolExecutor(self.root / "runs")
        self.script = self.root / "runner.py"
        self.script.write_text("print('durable match')", encoding="utf-8")
        self.manifest = ToolManifest("fixture", "Fixture", "1", "https://github.com/fixture/tool", "1", "a" * 64,
            "MIT", ["any"], ["local-fixture"], "runner.py", {"run": {"options": {}}}, max_timeout_seconds=10)

    def tearDown(self):
        result = self.executor.close()
        self.assertEqual(result["status"], "confirmed", result)
        self.temp.cleanup()

    def request(self, **kwargs):
        return ToolRequest("safety", "step", "run", "fixture", **kwargs)

    def run_tool(self, request=None, cancel=None):
        return self.executor.execute(self.manifest, str(self.script), request or self.request(), cancel)

    def test_default_constructor(self):
        with patch("core.tool_workbench.execution.tempfile.gettempdir", return_value=str(self.root)):
            executor = ToolExecutor()
            self.assertTrue(executor.workspace_root.is_dir())
            self.assertEqual(executor.close()["status"], "confirmed")

    def test_precancel_and_expired_deadline_never_spawn(self):
        event = threading.Event(); event.set()
        with patch.object(self.executor, "_spawn") as spawn:
            with self.assertRaises(CancellationError):
                self.run_tool(cancel=event)
            with self.assertRaises(TimeoutExpiredError):
                self.run_tool(self.request(deadline_monotonic=time.monotonic() - 1))
            spawn.assert_not_called()

    def test_nonfinite_and_unbounded_limits_never_spawn(self):
        with patch.object(self.executor, "_spawn") as spawn:
            for deadline in (float("nan"), float("inf"), -float("inf")):
                with self.assertRaises(SchemaValidationError):
                    self.run_tool(self.request(deadline_monotonic=deadline))
            for limit in (0, -1, True, self.executor.MAX_OUTPUT_BYTES + 1):
                with self.assertRaises(SchemaValidationError):
                    self.run_tool(self.request(max_output_bytes=limit))
            spawn.assert_not_called()

    def test_close_during_reserved_spawn_stays_pending_then_rejects_late_execute(self):
        entered, release = threading.Event(), threading.Event()
        original = self.executor._spawn
        results = []
        def blocked(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test barrier timed out")
            return original(*args)
        def execute():
            try:
                results.append(self.run_tool())
            except Exception as exc:
                results.append(exc)
        with patch.object(self.executor, "_spawn", side_effect=blocked):
            worker = threading.Thread(target=execute)
            worker.start()
            self.assertTrue(entered.wait(3))
            self.assertEqual(self.executor.close()["status"], "pending")
            release.set(); worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(self.executor.close()["status"], "confirmed")
        with self.assertRaises(ExecutionError):
            self.run_tool()
        self.assertTrue(results)

    def test_duplicate_live_id_never_overwrites_owned_reservation(self):
        entered, release = threading.Event(), threading.Event()
        original = self.executor._spawn
        def blocked(*args):
            entered.set(); release.wait(3)
            return original(*args)
        result = []
        with patch.object(self.executor, "_spawn", side_effect=blocked):
            worker = threading.Thread(target=lambda: result.append(self.run_tool()))
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                active = next(iter(self.executor._active_processes.values()))
                with self.assertRaisesRegex(ExecutionError, "Duplicate"):
                    self.run_tool(self.request(request_id=next(iter(self.executor._active_processes))))
                self.assertIs(active, next(iter(self.executor._active_processes.values())))
            finally:
                release.set(); worker.join(5)
        self.assertTrue(result)

    def test_workspace_containment_and_stale_results(self):
        outside = self.root / "outside"
        with patch.object(self.executor, "_spawn") as spawn:
            with self.assertRaisesRegex(ExecutionError, "outside"):
                self.run_tool(self.request(workspace=str(outside)))
            spawn.assert_not_called()
        workspace = self.executor.workspace_root / "approved"; workspace.mkdir()
        (workspace / "old.txt").write_text("stale")
        receipt = self.run_tool(self.request(workspace=str(workspace)))
        self.assertEqual(receipt.status, "confirmed")
        self.assertFalse(any("old.txt" in item["path"] for item in receipt.artifacts))
        for artifact in receipt.artifacts:
            source = workspace / artifact["path"]
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), artifact["sha256"])
        self.assertTrue(any(b"durable match" in (workspace / item["path"]).read_bytes() for item in receipt.artifacts))
        self.assertTrue(json.dumps(receipt.to_dict()))

    def test_ancestor_named_tmp_keeps_output_artifacts(self):
        executor = ToolExecutor(self.root / "tmp" / "runs")
        try:
            receipt = executor.execute(self.manifest, str(self.script), self.request())
            self.assertTrue(receipt.artifacts)
        finally:
            executor.close()

    def test_target_change_and_directory_scope_rejected_before_spawn(self):
        target = self.root / "target.bin"; target.write_bytes(b"first")
        captured = Target.from_file(target)
        target.write_bytes(b"other")
        with patch.object(self.executor, "_spawn") as spawn:
            with self.assertRaisesRegex(ExecutionError, "digest"):
                self.run_tool(self.request(target=captured))
            captured.canonical_path = str(self.root)
            with self.assertRaisesRegex(ExecutionError, "regular file"):
                self.run_tool(self.request(target=captured))
            spawn.assert_not_called()

    def test_target_change_after_execution_fails_receipt(self):
        target = self.root / "target.bin"; target.write_bytes(b"first")
        self.script.write_text("import sys; from pathlib import Path; Path(sys.argv[-1]).write_bytes(b'other')")
        receipt = self.run_tool(self.request(target=Target.from_file(target)))
        self.assertEqual(receipt.status, "failed")
        self.assertTrue(any("digest" in limitation for limitation in receipt.limitations))
        self.assertEqual(receipt.cleanup_receipt["status"], "confirmed")

    def test_option_schema_types_ranges_and_enums(self):
        self.manifest.supported_operations["run"]["options"] = {"limit": {"type": "integer", "minimum": 1, "maximum": 5},
            "mode": {"type": "string", "enum": ["safe"]}}
        with patch.object(self.executor, "_spawn") as spawn:
            for options in ({"limit": True}, {"limit": "2"}, {"limit": 6}, {"mode": "unsafe"}):
                with self.assertRaises(SchemaValidationError):
                    self.run_tool(self.request(options=options))
            spawn.assert_not_called()

    def test_small_overflow_stops_without_waiting_for_full_buffer(self):
        self.script.write_text("import sys,time; sys.stdout.write('x'*513); sys.stdout.flush(); time.sleep(5)")
        started = time.monotonic()
        receipt = self.run_tool(self.request(max_output_bytes=512))
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertEqual(receipt.status, "output_limit")
        self.assertEqual(len(receipt.stdout), 512)
        self.assertEqual(receipt.cleanup_receipt["status"], "confirmed")

    def test_artifact_byte_limit_fails_without_reading_entire_file(self):
        self.script.write_text("from pathlib import Path; f=Path('large.bin').open('wb'); f.truncate(2048); f.close()")
        with patch.object(self.executor, "MAX_ARTIFACT_BYTES", 1024):
            receipt = self.run_tool()
        self.assertEqual(receipt.status, "failed")
        self.assertTrue(any("limit" in limitation for limitation in receipt.limitations))

    def test_packaged_executable_cannot_be_used_as_python_interpreter(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(self.executor, "_spawn") as spawn:
            with self.assertRaisesRegex(ExecutionError, "managed interpreter"):
                self.run_tool()
            spawn.assert_not_called()

    def test_pending_output_drains_retain_ownership_until_observed_eof(self):
        release = threading.Event()
        class Stream:
            def read(self, size):
                release.wait(5)
                return b""
            def close(self):
                pass
        class Process:
            pid = -1
            returncode = 0
            stdout, stderr = Stream(), Stream()
            def poll(self):
                return self.returncode
        with patch.object(self.executor, "_spawn", return_value=Process()), \
             patch.object(self.executor, "_tree_empty", return_value=True), \
             patch.object(self.executor, "_terminate"), patch.object(self.executor, "CLEANUP_SECONDS", .05):
            try:
                receipt = self.run_tool()
                self.assertEqual(receipt.cleanup_receipt["status"], "pending")
                self.assertFalse(receipt.cleanup_receipt["drains_finished"])
                self.assertEqual(self.executor.stop_all()["status"], "pending")
                self.assertTrue(self.executor._active_processes)
                different = self.request()
                different.investigation_id = "new-investigation"
                with self.assertRaises(CancellationError):
                    self.run_tool(different)
            finally:
                release.set()
                until = time.monotonic() + 3
                while self.executor._active_processes and time.monotonic() < until:
                    time.sleep(.01)
            self.assertFalse(self.executor._active_processes)
            self.assertEqual(self.executor.close()["status"], "confirmed")

    @unittest.skipUnless(os.name == "nt", "Windows job ownership acceptance")
    def test_real_parent_exit_leaves_no_running_child(self):
        # Parent intentionally exits; the child holds inherited pipes and remains alive without job cleanup.
        self.script.write_text("""import subprocess,sys,time
from pathlib import Path
if '--child' in sys.argv:
    time.sleep(20)
else:
    child=subprocess.Popen([sys.executable,__file__,'--child'])
    Path('child.pid').write_text(str(child.pid))
""")
        receipt = self.run_tool()
        self.assertEqual(receipt.cleanup_receipt["status"], "confirmed")
        artifact = next(item for item in receipt.artifacts if item["path"] == "child.pid")
        pid = int(Path(artifact["absolute_path"]).read_text())
        self.assertFalse(psutil.pid_exists(pid), f"owned child {pid} survived")
        self.assertEqual(self.executor.close()["status"], "confirmed")


if __name__ == "__main__":
    unittest.main()
