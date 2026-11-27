"""SpeS's own Python (core.managed_python, 27 Nov; Fides option E). No test downloads anything: the
download, signature check and probe are fakes; extraction and publishing are real, in a temp folder."""
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core import managed_python as mp


def make_zip(path, members):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in members.items():
            bundle.writestr(name, data)


class ManagedPythonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "bin"
        patcher = patch.dict(os.environ, {"QUARTZ_CLI_ROOT": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = Path(self.tmp.name) / "source.zip"
        make_zip(self.source, {"python.exe": b"MZ fake", "Lib/tkinter/__init__.py": b""})
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.signed = []

    def download(self, url, destination, *, allowed, limit):
        self.assertEqual((url, allowed), (mp.URL, mp.ALLOWED))
        Path(destination).write_bytes(self.source.read_bytes())
        return Path(destination)

    def verify(self, exe, publisher):
        self.signed.append(publisher)
        return {"status": "Valid", "publisher": publisher}

    def run_ok(self, cmd, **kwargs):
        self.assertIn("-I", cmd)
        return subprocess.CompletedProcess(cmd, 0, f"{mp.VERSION}|8.6.15\n", "")

    def install(self, run=None):
        with patch.object(mp, "SHA256", self.digest):
            return mp.install(run=run or self.run_ok, download=self.download, verify=self.verify)

    def test_a_proven_runtime_is_published_atomically_and_then_reused(self):
        result = self.install()
        self.assertTrue(result["installed"])
        self.assertEqual(self.signed, ["Python Software Foundation"])
        self.assertTrue(Path(result["executable"]).is_file())
        self.assertEqual(mp.published(), Path(result["executable"]))
        self.assertEqual(mp.interpreter(), result["executable"])
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith("python-stage-")], [])
        self.assertTrue(self.install()["reused"])

    def test_a_wrong_hash_publishes_nothing(self):
        with patch.object(mp, "SHA256", "0" * 64):
            with self.assertRaises(ValueError):
                mp.install(run=self.run_ok, download=self.download, verify=self.verify)
        self.assertIsNone(mp.published())
        self.assertFalse((self.root / "packages").exists())

    def test_a_failed_probe_or_signature_publishes_nothing(self):
        bad = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "No module named tkinter")
        with self.assertRaises(RuntimeError):
            self.install(run=bad)
        self.assertIsNone(mp.published())
        self.verify = lambda exe, publisher: (_ for _ in ()).throw(ValueError("imza"))
        with self.assertRaises(ValueError):
            self.install()
        self.assertIsNone(mp.published())

    def test_unsafe_archives_are_refused_before_any_file_is_written(self):
        for members in ({"../outside.txt": b"x"}, {"/abs.txt": b"x"}, {"a/../../b.txt": b"x"}):
            archive = Path(self.tmp.name) / "bad.zip"
            make_zip(archive, members)
            target = Path(self.tmp.name) / "out"
            with self.assertRaises(ValueError):
                mp.safe_extract(archive, target)
            self.assertFalse((Path(self.tmp.name) / "outside.txt").exists())
        bomb = Path(self.tmp.name) / "bomb.zip"
        make_zip(bomb, {"big.bin": b"\0" * (5 * 1024 * 1024)})
        with self.assertRaises(ValueError):
            mp.safe_extract(bomb, Path(self.tmp.name) / "out2")

    def test_without_the_managed_runtime_the_users_python_is_used_unchanged(self):
        with patch.object(mp.shutil, "which", return_value=None):
            self.assertIsNone(mp.interpreter())
        self.assertIsNone(mp.published())

    def test_launch_check_and_the_agents_use_the_managed_runtime(self):
        result = self.install()
        from core import launch_check
        from core.cli_installer import cli_environment
        self.assertEqual(launch_check.python_interpreter(), result["executable"])
        first = cli_environment()["PATH"].split(os.pathsep)[0]
        self.assertEqual(Path(first), Path(result["executable"]).parent)

    def test_the_pin_is_an_exact_official_release(self):
        self.assertTrue(mp.URL.startswith("https://www.python.org/ftp/python/" + mp.VERSION + "/"))
        self.assertRegex(mp.SHA256, r"^[0-9a-f]{64}$")

    def test_auto_setup_prepares_python_first(self):
        from core.auto_setup import TOOLS
        self.assertEqual(TOOLS[0][0], "python")


if __name__ == "__main__":
    unittest.main()
