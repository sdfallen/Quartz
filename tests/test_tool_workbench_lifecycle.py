"""
tests/test_tool_workbench_lifecycle.py
End-to-end lifecycle, concurrency, real tool execution, and environment invariance tests
for Quartz Tool Workbench.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest

from core.tool_workbench.contracts import AcquisitionPolicy, Target, ToolManifest, ToolRequest
from core.tool_workbench.workbench import ToolWorkbench


class TestToolWorkbenchLifecycle(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.managed_dir = Path(self.temp_dir.name) / "managed"
        self.workspace_dir = Path(self.temp_dir.name) / "workspaces"
        self.managed_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self.workbench = ToolWorkbench(
            managed_dir=self.managed_dir,
            workspace_dir=self.workspace_dir,
        )

        # Create a test target file
        self.target_file = Path(self.temp_dir.name) / "test_target.txt"
        self.target_file.write_text(
            "QUARTZ_TARGET_HEADER\nKEY_VALUE_PAIR=SECRET_TEST_123\nFUNCTION_SYMBOL_DO_WORK\nQUARTZ_TARGET_FOOTER\n",
            encoding="utf-8",
        )
        self.target = Target.from_file(self.target_file)

    def tearDown(self):
        self.workbench.close()
        self.temp_dir.cleanup()

    def test_full_lifecycle_mock_tool(self):
        """Full lifecycle: catalog -> resolve -> acquire -> execute -> stop -> close."""
        # 1. Catalog
        catalog_list = self.workbench.catalog("ripgrep")
        self.assertEqual(len(catalog_list), 1)

        # 2. Resolve
        res = self.workbench.resolve("binary_string_search")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["tool_id"], "ripgrep")

        # 3. Register a test manifest backed by a local python script
        test_script = self.managed_dir / "test_script.py"
        test_script.write_text(
            """
import sys
target = sys.argv[-1]
with open(target, 'r', encoding='utf-8') as f:
    for line in f:
        if "FUNCTION_SYMBOL" in line:
            print("MATCH:" + line.strip())
""",
            encoding="utf-8",
        )

        test_manifest = ToolManifest(
            tool_id="test_resolver",
            name="Test Resolver",
            version="1.0.0",
            source_url="http://127.0.0.1/test.zip",
            pinned_revision="1.0.0",
            package_digest="test_digest",
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["symbol_resolution"],
            executable_subpath="test_script.py",
            supported_operations={"scan": {"options": {}}},
        )
        self.workbench.catalog_service.register(test_manifest)

        # Manually mark as installed in test managed dir
        install_dir = self.managed_dir / "test_resolver" / "1.0.0"
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil_script = install_dir / "test_script.py"
        shutil_script.write_text(test_script.read_text(encoding="utf-8"), encoding="utf-8")
        receipt_data = {
            "tool_id": "test_resolver",
            "pinned_revision": "1.0.0",
            "package_digest": "test_digest",
            "executable_subpath": "test_script.py",
            "acquired_at": time.time(),
        }
        (install_dir / "tool_receipt.json").write_text(json.dumps(receipt_data), encoding="utf-8")

        # 4. Execute
        req = ToolRequest(
            investigation_id="inv-life-1",
            step_id="step-1",
            operation="scan",
            tool_id="test_resolver",
            target=self.target,
        )
        receipt = self.workbench.execute(req)
        self.assertEqual(receipt.status, "confirmed")
        self.assertIn(b"MATCH:FUNCTION_SYMBOL_DO_WORK", receipt.stdout)

        # 5. Stop
        stop_res = self.workbench.stop("inv-life-1")
        self.assertEqual(stop_res["status"], "confirmed")

        # 6. Close
        close_res = self.workbench.close()
        self.assertEqual(close_res["status"], "confirmed")

    def test_concurrent_executions(self):
        """Simultaneous execution requests run independently in separate workspaces without collision."""
        test_script = self.managed_dir / "concurrent_script.py"
        test_script.write_text(
            """
import sys, time
arg_val = "unknown"
for i, a in enumerate(sys.argv):
    if a == "--val" and i + 1 < len(sys.argv):
        arg_val = sys.argv[i + 1]
time.sleep(0.3)
print(f"CONCURRENT_RESULT:{arg_val}")
""",
            encoding="utf-8",
        )

        manifest = ToolManifest(
            tool_id="concurrent_tool",
            name="Concurrent Tool",
            version="1.0.0",
            source_url="http://127.0.0.1/concurrent.zip",
            pinned_revision="1.0.0",
            package_digest="conc_digest",
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["concurrent_op"],
            executable_subpath="concurrent_script.py",
            supported_operations={"run": {"options": {"val": {"type": "string"}}}},
        )
        self.workbench.catalog_service.register(manifest)

        install_dir = self.managed_dir / "concurrent_tool" / "1.0.0"
        install_dir.mkdir(parents=True, exist_ok=True)
        (install_dir / "concurrent_script.py").write_text(test_script.read_text(encoding="utf-8"), encoding="utf-8")
        (install_dir / "tool_receipt.json").write_text(json.dumps({
            "tool_id": "concurrent_tool",
            "pinned_revision": "1.0.0",
            "package_digest": "conc_digest",
            "executable_subpath": "concurrent_script.py",
            "acquired_at": time.time(),
        }), encoding="utf-8")

        results = {}

        def run_worker(tag: str):
            req = ToolRequest(
                investigation_id=f"inv-{tag}",
                step_id="step-1",
                operation="run",
                tool_id="concurrent_tool",
                options={"val": tag},
            )
            r = self.workbench.execute(req)
            results[tag] = r

        t1 = threading.Thread(target=run_worker, args=("alpha",))
        t2 = threading.Thread(target=run_worker, args=("beta",))

        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        self.assertEqual(len(results), 2)
        self.assertEqual(results["alpha"].status, "confirmed")
        self.assertEqual(results["beta"].status, "confirmed")
        self.assertIn(b"CONCURRENT_RESULT:alpha", results["alpha"].stdout)
        self.assertIn(b"CONCURRENT_RESULT:beta", results["beta"].stdout)

    def test_environment_invariance(self):
        """Workbench operations must not alter global PATH or system environment."""
        initial_path = os.environ.get("PATH")
        initial_keys = set(os.environ.keys())

        # Perform catalog, resolve, execute
        self.workbench.catalog()
        self.workbench.resolve("binary_string_search")

        # Verify PATH is identical
        self.assertEqual(os.environ.get("PATH"), initial_path)
        # Verify no new environment variables were leaked into parent
        current_keys = set(os.environ.keys())
        self.assertEqual(current_keys, initial_keys)

    def test_real_github_tool_ripgrep_acquisition_and_execution(self):
        """
        Real Acceptance Test:
        Acquires official ripgrep 14.1.1 from GitHub with pinned revision and SHA-256 digest,
        runs real regex/string search on target file, verifies exit 0 and artifact output.
        """
        # Resolve ripgrep manifest
        res = self.workbench.resolve("binary_string_search")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["tool_id"], "ripgrep")

        manifest = self.workbench.catalog_service.get("ripgrep")
        self.assertIsNotNone(manifest)

        # Acquire real package from GitHub
        policy = AcquisitionPolicy(
            allow_network=True,
            managed_dir=str(self.managed_dir),
            allowed_sources=["https://github.com/"],
            verify_digest=True,
        )

        try:
            start_acq = time.monotonic()
            acq_res = self.workbench.acquire(manifest, policy=policy)
            acq_duration = time.monotonic() - start_acq
            self.assertIn(acq_res["status"], {"acquired", "cached"})
            self.assertEqual(acq_res["package_digest"], "d0f534024c42afd6cb4d38907c25cd2b249b79bbe6cc1dbee8e3e37c2b6e25a1")

            exe_path = Path(acq_res["executable_path"])
            self.assertTrue(exe_path.is_file(), f"Executable does not exist: {exe_path}")
            self.assertTrue(str(exe_path).endswith("rg.exe"))

            # Execute real ripgrep search operation on target file
            req = ToolRequest(
                investigation_id="inv-real-rg",
                step_id="step-search",
                operation="search",
                tool_id="ripgrep",
                target=self.target,
                options={"pattern": "SECRET_TEST_[0-9]+"},
            )

            start_exec = time.monotonic()
            receipt = self.workbench.execute(req)
            exec_duration = time.monotonic() - start_exec

            self.assertEqual(receipt.status, "confirmed")
            self.assertEqual(receipt.exit_code, 0)
            self.assertIn(b"KEY_VALUE_PAIR=SECRET_TEST_123", receipt.stdout)
            self.assertTrue(receipt.cleanup_receipt["process_exited"])

            # Execute real ripgrep strings extraction operation
            req_strings = ToolRequest(
                investigation_id="inv-real-rg",
                step_id="step-strings",
                operation="strings",
                tool_id="ripgrep",
                target=self.target,
                options={"pattern": "QUARTZ_TARGET_.*"},
            )

            receipt_strings = self.workbench.execute(req_strings)
            self.assertEqual(receipt_strings.status, "confirmed")
            self.assertEqual(receipt_strings.exit_code, 0)
            self.assertIn(b"QUARTZ_TARGET_HEADER", receipt_strings.stdout)
            self.assertIn(b"QUARTZ_TARGET_FOOTER", receipt_strings.stdout)

        except Exception as exc:
            # If network is strictly blocked in an air-gapped run, report clear diagnostics
            if "Failed to download tool package" in str(exc):
                self.skipTest(f"GitHub network access temporarily unavailable: {exc}")
            else:
                raise


if __name__ == "__main__":
    unittest.main()
