"""
tests/test_tool_workbench_acquisition.py
Comprehensive security and integrity tests for tool acquisition:
- Digest validation & mismatch rejection
- Zip-Slip path traversal defense
- Absolute path rejection
- Symlink archive rejection
- Corrupted archive handling
- Untrusted source rejection
- Policy network controls
- Staging cleanup on failure
- Cached installation verification
"""

from __future__ import annotations

import http.server
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest

from core.tool_workbench.acquisition import ToolAcquirer
from core.tool_workbench.contracts import AcquisitionPolicy, ToolManifest
from core.tool_workbench.errors import (
    CancellationError,
    CorruptedArchiveError,
    DigestMismatchError,
    DownloadError,
    SecurityViolationError,
)
from tests.test_tool_workbench_fixtures import (
    create_absolute_path_archive,
    create_corrupted_archive,
    create_symlink_archive,
    create_valid_tool_archive,
    create_zip_slip_archive,
)


class TestWebServer:
    """Threaded in-process HTTP server serving raw payloads for tests."""

    def __init__(self, payloads: dict[str, bytes]):
        self.payloads = payloads
        self.server: http.server.HTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.port: int = 0

    def start(self):
        payloads = self.payloads

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                if path in payloads:
                    data = payloads[path]
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Silence server logs in test output

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=2.0)


class TestToolWorkbenchAcquisition(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.managed_dir = Path(self.temp_dir.name).resolve()
        self.acquirer = ToolAcquirer(base_managed_dir=self.managed_dir)

        # Generate test archives
        self.valid_bytes, self.valid_digest = create_valid_tool_archive()
        self.slip_bytes, self.slip_digest = create_zip_slip_archive()
        self.abs_bytes, self.abs_digest = create_absolute_path_archive()
        self.sym_bytes, self.sym_digest = create_symlink_archive()
        self.corrupt_bytes, self.corrupt_digest = create_corrupted_archive()

        # Start mock server
        self.server = TestWebServer({
            "/valid.zip": self.valid_bytes,
            "/slip.zip": self.slip_bytes,
            "/abs.zip": self.abs_bytes,
            "/sym.zip": self.sym_bytes,
            "/corrupt.zip": self.corrupt_bytes,
        })
        self.server.start()

    def tearDown(self):
        self.server.stop()
        self.temp_dir.cleanup()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.server.port}{path}"

    def test_acquire_valid_package(self):
        """Test acquiring a valid package with verified digest and atomic installation."""
        manifest = ToolManifest(
            tool_id="sample_tool",
            name="Sample Test Tool",
            version="1.0.0",
            source_url=self._url("/valid.zip"),
            pinned_revision="1.0.0",
            package_digest=self.valid_digest,
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="tool/tool.bat",
            supported_operations={"run": {}},
        )

        res = self.acquirer.acquire(manifest)
        self.assertEqual(res["status"], "acquired")
        self.assertEqual(res["tool_id"], "sample_tool")
        self.assertEqual(res["package_digest"], self.valid_digest)

        exe_path = Path(res["executable_path"])
        self.assertTrue(exe_path.is_file())
        receipt_path = Path(res["receipt_file"])
        self.assertTrue(receipt_path.is_file())

        # Second call returns cached without redownloading
        res2 = self.acquirer.acquire(manifest)
        self.assertEqual(res2["status"], "cached")

    def test_tampered_cache_triggers_reacquisition(self):
        """If installed executable is deleted or corrupted, acquirer cleans and reinstalls."""
        manifest = ToolManifest(
            tool_id="sample_tool",
            name="Sample Test Tool",
            version="1.0.0",
            source_url=self._url("/valid.zip"),
            pinned_revision="1.0.0",
            package_digest=self.valid_digest,
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="tool/tool.bat",
            supported_operations={"run": {}},
        )

        res = self.acquirer.acquire(manifest)
        self.assertEqual(res["status"], "acquired")

        # Corrupt the executable
        Path(res["executable_path"]).unlink()

        # Re-acquisition detects corruption and reinstalls
        res2 = self.acquirer.acquire(manifest)
        self.assertEqual(res2["status"], "acquired")
        self.assertTrue(Path(res2["executable_path"]).is_file())

    def test_digest_mismatch_rejected(self):
        """Cryptographic digest mismatch raises DigestMismatchError and deletes files."""
        manifest = ToolManifest(
            tool_id="sample_tool",
            name="Sample Test Tool",
            version="1.0.0",
            source_url=self._url("/valid.zip"),
            pinned_revision="1.0.0",
            package_digest="0000000000000000000000000000000000000000000000000000000000000000",
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="tool/tool.bat",
            supported_operations={"run": {}},
        )

        with self.assertRaises(DigestMismatchError) as ctx:
            self.acquirer.acquire(manifest)

        self.assertIn("Cryptographic digest mismatch", str(ctx.exception))
        # Ensure target install directory was NOT created
        target_dir = self.managed_dir / "sample_tool" / "1.0.0"
        self.assertFalse(target_dir.exists())

    def test_zip_slip_traversal_rejected(self):
        """Archive with Zip-Slip traversal is detected and rejected with SecurityViolationError."""
        manifest = ToolManifest(
            tool_id="malicious_tool",
            name="Zip Slip Malicious Tool",
            version="1.0.0",
            source_url=self._url("/slip.zip"),
            pinned_revision="1.0.0",
            package_digest=self.slip_digest,
            license="Unknown",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="normal.txt",
            supported_operations={"run": {}},
        )

        with self.assertRaises(SecurityViolationError) as ctx:
            self.acquirer.acquire(manifest)

        self.assertTrue("traversal" in str(ctx.exception) or "Zip slip" in str(ctx.exception))
        # Verify no file escaped outside managed directory
        escaped_file = self.managed_dir.parent / "escaped_malicious.exe"
        self.assertFalse(escaped_file.exists())

    def test_absolute_path_in_archive_rejected(self):
        """Archive with absolute path member is rejected."""
        manifest = ToolManifest(
            tool_id="abs_tool",
            name="Absolute Path Malicious Tool",
            version="1.0.0",
            source_url=self._url("/abs.zip"),
            pinned_revision="1.0.0",
            package_digest=self.abs_digest,
            license="Unknown",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="C:/Windows/System32/evil.dll",
            supported_operations={"run": {}},
        )

        with self.assertRaises(SecurityViolationError) as ctx:
            self.acquirer.acquire(manifest)

        self.assertTrue("Absolute path" in str(ctx.exception) or "Zip slip" in str(ctx.exception))

    def test_symlink_archive_rejected(self):
        """Archive with Unix symlink is rejected."""
        manifest = ToolManifest(
            tool_id="sym_tool",
            name="Symlink Tool",
            version="1.0.0",
            source_url=self._url("/sym.zip"),
            pinned_revision="1.0.0",
            package_digest=self.sym_digest,
            license="Unknown",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="symlink_entry",
            supported_operations={"run": {}},
        )

        with self.assertRaises(SecurityViolationError) as ctx:
            self.acquirer.acquire(manifest)

        self.assertIn("Symlinks prohibited", str(ctx.exception))

    def test_corrupted_archive_rejected(self):
        """Corrupted/truncated archive is rejected with CorruptedArchiveError."""
        manifest = ToolManifest(
            tool_id="corrupt_tool",
            name="Corrupt Tool",
            version="1.0.0",
            source_url=self._url("/corrupt.zip"),
            pinned_revision="1.0.0",
            package_digest=self.corrupt_digest,
            license="Unknown",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="tool",
            supported_operations={"run": {}},
        )

        with self.assertRaises(CorruptedArchiveError):
            self.acquirer.acquire(manifest)

    def test_untrusted_source_url_rejected(self):
        """Source URL not matching allowed_sources is rejected immediately without request."""
        manifest = ToolManifest(
            tool_id="untrusted_tool",
            name="Untrusted Tool",
            version="1.0.0",
            source_url="http://untrusted-hacker-site.org/tool.zip",
            pinned_revision="1.0.0",
            package_digest="abcdef",
            license="Unknown",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="tool",
            supported_operations={"run": {}},
        )

        policy = AcquisitionPolicy(allowed_sources=["https://github.com/"])
        with self.assertRaises(SecurityViolationError) as ctx:
            self.acquirer.acquire(manifest, policy=policy)

        self.assertIn("Untrusted tool source URL", str(ctx.exception))

    def test_network_disabled_policy(self):
        """Policy with allow_network=False prevents download."""
        manifest = ToolManifest(
            tool_id="sample_tool",
            name="Sample Test Tool",
            version="1.0.0",
            source_url=self._url("/valid.zip"),
            pinned_revision="1.0.0",
            package_digest=self.valid_digest,
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="tool/tool.bat",
            supported_operations={"run": {}},
        )

        policy = AcquisitionPolicy(allow_network=False)
        with self.assertRaises(DownloadError) as ctx:
            self.acquirer.acquire(manifest, policy=policy)

        self.assertIn("prohibited", str(ctx.exception))

    def test_cancellation_during_download(self):
        """Cancel event set during acquisition aborts process and cleans up."""
        manifest = ToolManifest(
            tool_id="sample_tool",
            name="Sample Test Tool",
            version="1.0.0",
            source_url=self._url("/valid.zip"),
            pinned_revision="1.0.0",
            package_digest=self.valid_digest,
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["test_cap"],
            executable_subpath="tool/tool.bat",
            supported_operations={"run": {}},
        )

        cancel_ev = threading.Event()
        cancel_ev.set()  # Pre-cancelled

        with self.assertRaises(CancellationError):
            self.acquirer.acquire(manifest, cancel_event=cancel_ev)

        # Staging should be completely empty
        stagings = list(self.managed_dir.glob(".staging*"))
        self.assertEqual(len(stagings), 0)


if __name__ == "__main__":
    unittest.main()
