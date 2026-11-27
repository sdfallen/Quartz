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

    def test_mp1_the_auto_detected_check_runs_with_the_chosen_interpreter(self):
        result = self.install()
        from core import long_job
        project = Path(self.tmp.name) / "proje"
        (project / "tests").mkdir(parents=True)
        (project / "tests" / "test_a.py").write_text("", encoding="utf-8")
        ledger = type("L", (), {"data": {"permission_level": "full", "verify": None, "auto_check": True,
                                         "project_path": str(project)}})()
        seen = {}

        def popen(argv, **kwargs):
            seen.update(argv=argv, env=kwargs.get("env"))
            raise FileNotFoundError("stop here")
        with patch.object(long_job.subprocess, "Popen", side_effect=popen):
            long_job.run_verify(ledger, __import__("threading").Event())
        self.assertEqual(seen["argv"][0], result["executable"])
        self.assertEqual(Path(seen["env"]["PATH"].split(os.pathsep)[0]), Path(result["executable"]).parent)
        from core import launch_check
        self.assertEqual(launch_check.python_interpreter(), seen["argv"][0])  # one choice everywhere

    def test_mp1_a_check_the_user_gave_is_never_rewritten(self):
        self.install()
        from core import long_job
        ledger = type("L", (), {"data": {"permission_level": "full", "verify": ["python", "kontrol.py"],
                                         "project_path": self.tmp.name}})()
        seen = {}
        with patch.object(long_job.subprocess, "Popen",
                          side_effect=lambda argv, **kw: seen.update(argv=argv) or (_ for _ in ()).throw(OSError("x"))):
            long_job.run_verify(ledger, __import__("threading").Event())
        self.assertEqual(seen["argv"], ["python", "kontrol.py"])

    def run_real_job(self, project, **spec_changes):
        """The production path: job_spec -> JobLedger.create -> run_verify (Popen observed only)."""
        from core import long_job
        from core.job_intent import job_spec
        spec = job_spec("Bir hesap makinesi yap", [{"title": "a", "acceptance": "b"}], project, "0101",
                        full_access=True)
        spec.update(project_path=str(project), permission_level="full", **spec_changes)
        ledger = long_job.JobLedger.create(spec, root=Path(self.tmp.name) / "jobs")
        ledger.data["permission_level"] = "full"
        seen = {}

        def popen(argv, **kwargs):
            seen.update(argv=argv, env=kwargs.get("env"))
            raise FileNotFoundError("stop here")
        with patch.object(long_job.subprocess, "Popen", side_effect=popen):
            long_job.run_verify(ledger, __import__("threading").Event())
        return ledger, seen

    def test_mp1_a_project_with_tests_from_the_start_uses_the_chosen_interpreter(self):
        result = self.install()
        project = Path(self.tmp.name) / "hazir-proje"
        project.mkdir()
        (project / "test_hesap.py").write_text("", encoding="utf-8")
        ledger, seen = self.run_real_job(project)
        self.assertEqual(ledger.data["verify_source"], "detected")
        self.assertEqual(seen["argv"][0], result["executable"])
        self.assertNotIn("PYTHONPATH", seen["env"])
        self.assertEqual(Path(seen["env"]["PATH"].split(os.pathsep)[0]), Path(result["executable"]).parent)

    def test_mp1_a_users_own_check_stays_exactly_as_given(self):
        self.install()
        project = Path(self.tmp.name) / "kullanici-proje"
        project.mkdir()
        (project / "test_hesap.py").write_text("", encoding="utf-8")
        ledger, seen = self.run_real_job(project, verify=["python", "benim_kontrolum.py"], verify_source=None)
        self.assertEqual(ledger.data["verify_source"], "user")
        self.assertEqual(seen["argv"], ["python", "benim_kontrolum.py"])
        self.assertIsNone(seen["env"])

    def test_mp1l_an_older_ledgers_stored_check_is_kept_even_when_it_equals_the_generated_one(self):
        self.install()
        from core import long_job
        from core.job_intent import detected_check
        project = Path(self.tmp.name) / "eski-proje"
        project.mkdir()
        (project / "test_x.py").write_text("", encoding="utf-8")
        stored = detected_check(project)
        ledger = type("L", (), {"data": {"permission_level": "full", "auto_check": True,
                                         "verify": stored, "project_path": str(project)}})()
        seen = {}
        with patch.object(long_job.subprocess, "Popen",
                          side_effect=lambda argv, **kw: seen.update(argv=argv, env=kw.get("env")) or
                          (_ for _ in ()).throw(OSError("x"))):
            long_job.run_verify(ledger, __import__("threading").Event())
        self.assertEqual((seen["argv"], seen["env"]), (stored, None))

    def test_mp2_an_installers_own_root_is_kept_and_roots_never_cross(self):
        from core.cli_installer import CliInstaller
        other = Path(self.tmp.name) / "selected-bin"
        with patch.object(mp, "SHA256", self.digest), \
                patch("core.install_security.download", side_effect=self.download), \
                patch("core.install_security.verify_publisher", side_effect=self.verify):
            result = CliInstaller(root=other, run=self.run_ok).install("python")
        self.assertIn(str(other), result["executable"])
        self.assertIsNone(mp.published())  # the default root is untouched
        self.assertEqual(mp.published(other), Path(result["executable"]))

    def test_mp3_a_concurrent_provider_record_survives(self):
        from core.atomic_json import atomic_write_json, load_json
        import threading
        self.root.mkdir(parents=True, exist_ok=True)
        entered, release = threading.Event(), threading.Event()
        original = self.verify

        def slow_verify(exe, publisher):
            entered.set()
            release.wait(5)
            return original(exe, publisher)
        self.verify = slow_verify
        worker = threading.Thread(target=self.install)
        worker.start()
        self.assertTrue(entered.wait(5))
        from core.cli_installer import _LOCK

        def other_provider():
            with _LOCK:  # what every other provider's install does around its manifest write
                manifest = load_json(self.root / "installed.json", {})
                manifest["agy"] = {"executable": "agy.exe", "version": "1"}
                atomic_write_json(self.root / "installed.json", manifest)
        writer = threading.Thread(target=other_provider)
        writer.start()
        release.set()
        worker.join(10)
        writer.join(10)
        self.assertEqual(set(load_json(self.root / "installed.json", {})), {"python", "agy"})

    def test_mp4_a_failed_manifest_commit_leaves_no_runtime_folder(self):
        with patch("core.atomic_json.atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.install()
        self.assertIsNone(mp.published())
        packages = self.root / "packages"
        self.assertEqual(list(packages.iterdir()) if packages.exists() else [], [])

    def test_the_pin_is_an_exact_official_release(self):
        self.assertTrue(mp.URL.startswith("https://www.python.org/ftp/python/" + mp.VERSION + "/"))
        self.assertRegex(mp.SHA256, r"^[0-9a-f]{64}$")

    def test_auto_setup_prepares_python_first(self):
        from core.auto_setup import TOOLS
        self.assertEqual(TOOLS[0][0], "python")


if __name__ == "__main__":
    unittest.main()
