"""Adversarial acquisition regressions. Temporary packages only, never executed."""
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from core.tool_workbench.acquisition import ToolAcquirer, _CheckedRedirect, manifest_fingerprint
from core.tool_workbench.contracts import AcquisitionPolicy, ToolManifest
from core.tool_workbench.errors import CancellationError, SecurityViolationError, DownloadError

SOURCE = "https://github.com/example/tool/releases/download/v1/tool.zip"


def package(**files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return stream.getvalue()


class Response(io.BytesIO):
    def geturl(self):
        return SOURCE


class AcquisitionSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.managed = self.root / "managed"
        self.acquirer = ToolAcquirer(self.managed)
        self.payload = package(**{"tool/main.py": "print('fixture')", "tool/dependency.txt": "expected"})
        self.manifest = ToolManifest(tool_id="safe-tool", name="Safe fixture", version="1",
            source_url=SOURCE, pinned_revision="v1", package_digest=hashlib.sha256(self.payload).hexdigest(),
            license="MIT", platform=["win32"], capabilities=["fixture"], executable_subpath="tool/main.py",
            supported_operations={"inspect": {}})

    def acquire(self, manifest=None, **kwargs):
        with patch("core.tool_workbench.acquisition.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = lambda *args, **kw: Response(self.payload)
            return self.acquirer.acquire(manifest or self.manifest, **kwargs)

    def test_identifiers_cannot_delete_outside_directory_even_offline(self):
        victim = self.root / "victim" / "v1"
        victim.mkdir(parents=True)
        sentinel = victim / "sentinel.txt"
        sentinel.write_text("preserve")
        for identifier in ("../victim", str(self.root / "victim"), "..", "evil/name", "evil\\name"):
            with self.subTest(identifier=identifier):
                with self.assertRaises(SecurityViolationError):
                    self.acquirer.acquire(replace(self.manifest, tool_id=identifier), AcquisitionPolicy(allow_network=False))
                self.assertEqual(sentinel.read_text(), "preserve")
        self.assertFalse(self.managed.exists())

    def test_revision_traversal_is_rejected_before_mutation(self):
        with self.assertRaises(SecurityViolationError):
            self.acquirer.acquire(replace(self.manifest, pinned_revision="../outside"))
        self.assertFalse(self.managed.exists())

    def test_executable_cannot_nominate_external_or_traversal_file(self):
        external = self.root / "outside.py"
        external.write_text("external")
        for name in (str(external), "../outside.py", "C:/Windows/evil.exe", "tool/../../outside.py"):
            with self.subTest(name=name), self.assertRaises(SecurityViolationError):
                self.acquire(replace(self.manifest, executable_subpath=name))
        self.assertEqual(external.read_text(), "external")
        self.assertFalse(self.managed.exists())

    def test_policy_cannot_redirect_managed_root(self):
        with self.assertRaises(SecurityViolationError):
            self.acquire(policy=AcquisitionPolicy(managed_dir=str(self.root / "other")))
        self.assertFalse((self.root / "other").exists())

    def test_digest_verification_cannot_be_disabled(self):
        with self.assertRaises(SecurityViolationError):
            self.acquire(policy=AcquisitionPolicy(verify_digest=False))
        self.assertFalse(self.managed.exists())

    def test_actual_executable_and_dependency_hashes_are_rechecked(self):
        result = self.acquire()
        self.assertEqual(result["status"], "acquired")
        for relative in ("tool/main.py", "tool/dependency.txt"):
            target = Path(result["install_dir"]) / relative
            original = target.read_bytes()
            target.write_bytes(b"tampered")
            with self.assertRaises(SecurityViolationError):
                self.acquirer.validate_installation(self.manifest, result)
            target.write_bytes(original)
            self.assertEqual(self.acquirer.validate_installation(self.manifest, result)["status"], "cached")

    def test_manifest_replacement_invalidates_cached_tool(self):
        result = self.acquire()
        changed = replace(self.manifest, supported_operations={"unrelated": {}}, source_url=SOURCE + "?changed")
        self.assertNotEqual(manifest_fingerprint(changed), result["manifest_fingerprint"])
        with self.assertRaises(SecurityViolationError):
            self.acquirer.validate_installation(changed, result)

    def test_offline_tampered_cache_is_preserved_not_deleted(self):
        result = self.acquire()
        exe = Path(result["executable_path"])
        exe.write_text("tampered for inspection")
        with self.assertRaises(DownloadError):
            self.acquirer.acquire(self.manifest, AcquisitionPolicy(allow_network=False))
        self.assertEqual(exe.read_text(), "tampered for inspection")

    def test_extra_file_in_installation_is_detected(self):
        result = self.acquire()
        (Path(result["install_dir"]) / "unexpected.dll").write_text("not in package")
        with self.assertRaises(SecurityViolationError):
            self.acquirer.validate_installation(self.manifest, result)

    def test_precancelled_and_expired_calls_never_open_network(self):
        event = threading.Event(); event.set()
        for kwargs in ({"cancel_event": event}, {"deadline_monotonic": time.monotonic() - 1}):
            with patch("core.tool_workbench.acquisition.urllib.request.build_opener") as opener:
                with self.assertRaises(CancellationError):
                    self.acquirer.acquire(self.manifest, **kwargs)
                opener.assert_not_called()
        self.assertFalse(self.managed.exists())

    def test_nonfinite_deadline_and_invalid_limits_are_rejected(self):
        for deadline in (float("nan"), float("inf")):
            with self.assertRaises(SecurityViolationError):
                self.acquirer.acquire(self.manifest, deadline_monotonic=deadline)
        with self.assertRaises(SecurityViolationError):
            self.acquire(policy=AcquisitionPolicy(max_archive_entries=-1))

    def test_close_retains_pending_acquisition_and_prevents_publication(self):
        entered = threading.Event(); resume = threading.Event()
        errors = []
        class BlockingResponse(Response):
            def read(inner, amount):
                entered.set()
                if not resume.wait(5):
                    raise TimeoutError()
                return super().read(amount)
        def worker():
            try:
                self.acquirer.acquire(self.manifest)
            except Exception as error:
                errors.append(error)
        with patch("core.tool_workbench.acquisition.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = lambda *a, **k: BlockingResponse(self.payload)
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                receipt = self.acquirer.close()
                self.assertEqual(receipt["status"], "pending")
                self.assertFalse(receipt["all_exited"])
            finally:
                resume.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], CancellationError)
        self.assertEqual(self.acquirer.close()["status"], "confirmed")
        self.assertFalse((self.managed / "safe-tool" / "v1").exists())
        self.assertEqual(list(self.managed.glob(".staging*")), [])
        with self.assertRaises(CancellationError):
            self.acquire()

    def test_separate_acquirers_serialize_publication(self):
        peer = ToolAcquirer(self.managed)
        results, errors = [], []
        calls = []
        def download(*args, **kwargs):
            calls.append(1)
            time.sleep(.05)
            return Response(self.payload)
        def worker(acquirer):
            try:
                results.append(acquirer.acquire(self.manifest))
            except Exception as exc:
                errors.append(exc)
        with patch("core.tool_workbench.acquisition.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = download
            threads = [threading.Thread(target=worker, args=(item,)) for item in (self.acquirer, peer)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(item["status"] for item in results), ["acquired", "cached"])
        self.assertEqual(len(calls), 1)

    def test_source_prefix_spoof_and_untrusted_redirect_are_rejected(self):
        for source in ("https://github.com.evil.invalid/tool.zip", "https://github.com@evil.invalid/tool.zip"):
            with self.assertRaises(SecurityViolationError):
                self.acquire(replace(self.manifest, source_url=source))
        redirect = _CheckedRedirect(["https://github.com/"], SOURCE)
        with self.assertRaises(SecurityViolationError):
            redirect.redirect_request(None, None, 302, "Found", {}, "https://evil.invalid/tool.zip")

    def test_linked_managed_ancestor_is_rejected(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("Local account cannot create test symlink")
        with self.assertRaises(SecurityViolationError):
            ToolAcquirer(link / "managed")

    def test_archive_cannot_override_receipt_or_include_windows_traversal(self):
        for name in ("tool_receipt.json", "tool\\..\\..\\outside", "tool/CON.txt", "tool/space .txt "):
            with self.subTest(name=name):
                self.payload = package(**{"tool/main.py": "fixture", name: "malicious"})
                manifest = replace(self.manifest, package_digest=hashlib.sha256(self.payload).hexdigest())
                with self.assertRaises(SecurityViolationError):
                    self.acquire(manifest)


if __name__ == "__main__":
    unittest.main()
