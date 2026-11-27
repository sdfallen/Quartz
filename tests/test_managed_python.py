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

    def test_reuse_proves_the_recorded_runtime_again(self):
        first = self.install()
        probes = []

        def counting(cmd, **kwargs):
            probes.append(cmd[0])
            return self.run_ok(cmd, **kwargs)
        again = self.install(run=counting)
        self.assertTrue(again["reused"])
        self.assertEqual(probes, [first["executable"]])
        self.assertEqual(self.signed, ["Python Software Foundation"] * 2)

    def test_a_runtime_that_fails_again_is_replaced_and_never_deleted(self):
        first = self.install()
        old = Path(first["executable"])
        broken = lambda cmd, **kw: (subprocess.CompletedProcess(cmd, 1, "", "No module named tkinter")
                                    if cmd[0] == str(old) else self.run_ok(cmd, **kw))
        fresh = self.install(run=broken)
        self.assertFalse(fresh["reused"])
        self.assertNotEqual(fresh["executable"], str(old))
        self.assertEqual(mp.published(), Path(fresh["executable"]))
        self.assertTrue(old.is_file())  # a running job or a venv may still use it

    def test_a_failed_signature_on_reuse_is_not_reused(self):
        first = self.install()
        old = first["executable"]

        def refuse_old(exe, publisher):
            if str(exe) == old:
                raise ValueError("imza")
            return {"status": "Valid", "publisher": publisher}
        self.verify = refuse_old
        fresh = self.install()
        self.assertFalse(fresh["reused"])
        self.assertTrue(Path(old).is_file())

    def offline(self, url, destination, *, allowed, limit):
        raise OSError("çevrimdışı")

    def broken_for(self, old):
        return lambda cmd, **kw: (subprocess.CompletedProcess(cmd, 1, "", "No module named tkinter")
                                  if cmd[0] == str(old) else self.run_ok(cmd, **kw))

    def test_re1_a_runtime_that_failed_is_not_selected_when_no_replacement_comes(self):
        old = Path(self.install()["executable"])
        self.download = self.offline
        with self.assertRaises(OSError):
            self.install(run=self.broken_for(old))
        self.assertTrue(old.is_file())  # kept on disk
        self.assertIsNone(mp.published())
        self.assertNotEqual(mp.interpreter(), str(old))
        self.assertTrue(json.loads((self.root / "installed.json").read_text(encoding="utf-8"))["python"]["unproven"])

    def test_re1_a_failed_mark_holds_in_process_even_when_the_record_cannot_be_written(self):
        old = Path(self.install()["executable"])
        self.download = self.offline
        from core import atomic_json
        with patch.object(atomic_json, "atomic_write_json", side_effect=OSError("disk dolu")):
            with self.assertRaises(OSError):
                self.install(run=self.broken_for(old))
        self.assertIsNone(mp.published())

    def test_re1_only_a_passed_proof_brings_a_failed_runtime_back(self):
        old = Path(self.install()["executable"])
        self.download = self.offline
        with self.assertRaises(OSError):
            self.install(run=self.broken_for(old))
        again = self.install()  # it works again (the probe passes): reused, mark cleared
        self.assertTrue(again["reused"])
        self.assertEqual(mp.published(), old)
        self.assertNotIn("unproven", json.loads((self.root / "installed.json").read_text(encoding="utf-8"))["python"])

    def test_re1_a_stale_mark_never_touches_a_newer_record(self):
        old = Path(self.install()["executable"])
        fresh = Path(self.install(run=self.broken_for(old))["executable"])
        mp._set_unproven(self.root, old, True)
        self.assertEqual(mp.published(), fresh)
        self.assertNotIn("unproven", json.loads((self.root / "installed.json").read_text(encoding="utf-8"))["python"])

    def test_reading_the_runtime_runs_nothing(self):
        self.install()
        with patch.object(mp, "prove", side_effect=AssertionError("no proof while reading")):
            self.assertIsNotNone(mp.published())
            self.assertIsNotNone(mp.interpreter())

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

    def fake_venv_run(self, fail=False):
        def run(cmd, **kwargs):
            self.assertEqual(cmd[1:4], ["-I", "-m", "venv"])
            folder = Path(cmd[4])
            (folder / "Scripts").mkdir(parents=True)
            if not fail:
                (folder / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
                (folder / "Scripts" / "python.exe").write_bytes(b"MZ")
            return subprocess.CompletedProcess(cmd, 1 if fail else 0, "", "")
        return run

    def test_venv_a_code_project_gets_its_own_environment_from_spes_runtime(self):
        self.install()
        project = Path(self.tmp.name) / "oyun"
        project.mkdir()
        (project / ".gitignore").write_text("__pycache__/", encoding="utf-8")
        made = mp.ensure_project_venv(project, run=self.fake_venv_run())
        self.assertEqual(made, project / ".venv" / "Scripts" / "python.exe")
        self.assertEqual(mp.project_interpreter(project), str(made))
        self.assertIn(".venv/", (project / ".gitignore").read_text(encoding="utf-8").splitlines())
        env = mp.task_environment(project=project)
        self.assertEqual(env["VIRTUAL_ENV"], str(project / ".venv"))
        self.assertEqual(Path(env["PATH"].split(os.pathsep)[0]), made.parent)
        from core import launch_check
        self.assertEqual(launch_check.python_interpreter(project), str(made))

    def test_venv_an_existing_venv_and_a_computer_without_spes_runtime_are_left_alone(self):
        project = Path(self.tmp.name) / "eski"
        (project / ".venv" / "Scripts").mkdir(parents=True)
        (project / ".venv" / "pyvenv.cfg").write_text("home = mine\n", encoding="utf-8")
        (project / ".venv" / "Scripts" / "python.exe").write_bytes(b"mine")
        never = lambda *a, **k: self.fail("no venv is made over an existing one")
        self.assertEqual(mp.ensure_project_venv(project, run=never), project / ".venv" / "Scripts" / "python.exe")
        bare = Path(self.tmp.name) / "bos"
        bare.mkdir()
        self.assertIsNone(mp.ensure_project_venv(bare, run=never))  # no SpeS runtime: nothing is made
        self.assertFalse((bare / ".venv").exists())

    def test_venv_a_failed_creation_deletes_nothing_and_is_never_used(self):
        self.install()
        project = Path(self.tmp.name) / "yarim"
        project.mkdir()
        self.assertIsNone(mp.ensure_project_venv(project, run=self.fake_venv_run(fail=True)))
        # Something was left (an empty Scripts): kept, marked incomplete, never taken as a venv.
        self.assertTrue((project / ".venv" / mp.INCOMPLETE).is_file())
        self.assertTrue((project / ".venv" / "Scripts").is_dir())
        self.assertIsNone(mp.project_venv(project))
        self.assertFalse((project / ".gitignore").exists())
        empty = Path(self.tmp.name) / "bos-kaldi"
        empty.mkdir()
        nothing = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "")
        self.assertIsNone(mp.ensure_project_venv(empty, run=nothing))
        self.assertFalse((empty / ".venv").exists())  # an empty reservation is simply given back

    def test_v2r_a_foreign_file_deep_inside_is_kept_on_failure(self):
        self.install()
        project = Path(self.tmp.name) / "derin"
        project.mkdir()

        def nested_foreign(cmd, **kwargs):
            scripts = Path(cmd[4]) / "Scripts"
            scripts.mkdir(parents=True)
            (scripts / "external-user-data.txt").write_text("benim", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 1, "", "")
        self.assertIsNone(mp.ensure_project_venv(project, run=nested_foreign))
        self.assertEqual((project / ".venv" / "Scripts" / "external-user-data.txt").read_text(encoding="utf-8"),
                         "benim")

    def test_vr1_a_failed_venv_is_never_used_even_when_no_mark_can_be_written(self):
        self.install()
        project = Path(self.tmp.name) / "isaretsiz"
        project.mkdir()

        def complete_but_failed(cmd, **kwargs):
            folder = Path(cmd[4])
            (folder / "Scripts").mkdir(parents=True)
            (folder / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
            (folder / "Scripts" / "python.exe").write_bytes(b"MZ")
            return subprocess.CompletedProcess(cmd, 1, "", "")
        original = Path.write_text

        def no_incomplete_mark(path, *args, **kwargs):
            if path.name == mp.INCOMPLETE:
                raise OSError("disk dolu")
            return original(path, *args, **kwargs)
        with patch.object(Path, "write_text", no_incomplete_mark):
            self.assertIsNone(mp.ensure_project_venv(project, run=complete_but_failed))
        self.assertFalse((project / ".venv" / mp.INCOMPLETE).exists())
        self.assertIsNone(mp.project_venv(project))  # the CREATING mark written first keeps it unused
        self.assertNotEqual(mp.project_interpreter(project), str(project / ".venv" / "Scripts" / "python.exe"))

    def test_vr1_without_the_first_mark_nothing_is_run(self):
        self.install()
        project = Path(self.tmp.name) / "isaret-yok"
        project.mkdir()
        original = Path.write_text

        def no_creating_mark(path, *args, **kwargs):
            if path.name == mp.CREATING:
                raise OSError("yazılamadı")
            return original(path, *args, **kwargs)
        with patch.object(Path, "write_text", no_creating_mark):
            self.assertIsNone(mp.ensure_project_venv(project, run=lambda *a, **k: self.fail("no run")))
        self.assertFalse((project / ".venv").exists())

    def test_vr1_a_proven_venv_carries_only_the_created_mark(self):
        self.install()
        project = Path(self.tmp.name) / "tamam"
        project.mkdir()
        made = mp.ensure_project_venv(project, run=self.fake_venv_run())
        self.assertIsNotNone(made)
        self.assertFalse((project / ".venv" / mp.CREATING).exists())
        self.assertTrue((project / ".venv" / "spes-created.txt").is_file())

    def test_v1r_a_refused_second_start_never_removes_the_first_jobs_venv(self):
        self.install()
        from core.long_job import JobError
        from core.long_job_chat import LongJobChatMixin
        import threading
        project = Path(self.tmp.name) / "iki-baslatma"
        project.mkdir()
        made = mp.ensure_project_venv(project, run=self.fake_venv_run())
        running = type("J", (), {"ledger": type("L", (), {"data": {"status": "running"}})()})()
        chat = LongJobChatMixin.__new__(LongJobChatMixin)
        chat._lock = threading.RLock()
        chat.__dict__.update(_plan_generation=0, _closed=False, _long_jobs={"first": running})
        conv = {"id": "c1", "space": "work", "project_id": "p1"}
        chat.store = type("S", (), {"get": lambda self, cid: conv, "get_active": lambda self: conv,
                                    "get_agent_model": lambda self, c, a: {}})()
        chat.agent_service = type("A", (), {"projects": type("P", (), {
            "get": lambda self, pid: {"path": str(project)}})()})()
        chat._jobs = lambda: chat.__dict__["_long_jobs"]
        with self.assertRaises(JobError):
            chat.job_start({"goal": "oyun", "milestones": [{"title": "a", "acceptance": "b"}],
                            "permission_level": "full", "conversation_id": "c1"})
        self.assertEqual(mp.project_venv(project), made)

    def test_venv_the_check_the_writer_and_pip_all_use_the_project_environment(self):
        self.install()
        project = Path(self.tmp.name) / "hazir"
        project.mkdir()
        (project / "test_a.py").write_text("", encoding="utf-8")
        made = mp.ensure_project_venv(project, run=self.fake_venv_run())
        ledger, seen = self.run_real_job(project)
        self.assertEqual(seen["argv"][0], str(made))
        self.assertEqual(seen["env"]["VIRTUAL_ENV"], str(project / ".venv"))
        from core.long_job import milestone_prompt, VENV_RULE
        self.assertIn(VENV_RULE, milestone_prompt(ledger, ledger.data["milestones"][0], "claude"))
        from core.cli_installer import cli_environment
        self.assertEqual(cli_environment()["PIP_REQUIRE_VIRTUALENV"], "1")

    def test_v2_a_venv_someone_else_creates_meanwhile_is_never_removed(self):
        self.install()
        project = Path(self.tmp.name) / "yaris"
        project.mkdir()

        def racing_run(cmd, **kwargs):
            # Another owner writes into .venv while SpeS's venv command fails.
            (Path(cmd[4]) / "external-user-data.txt").write_text("benim", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 1, "", "")
        self.assertIsNone(mp.ensure_project_venv(project, run=racing_run))
        self.assertEqual((project / ".venv" / "external-user-data.txt").read_text(encoding="utf-8"), "benim")
        # A .venv that already exists (even empty, without pyvenv.cfg) is never reserved or touched.
        other = Path(self.tmp.name) / "dolu"
        (other / ".venv").mkdir(parents=True)
        self.assertIsNone(mp.ensure_project_venv(other, run=lambda *a, **k: self.fail("no run")))
        self.assertTrue((other / ".venv").is_dir())

    def test_v2_a_stop_before_the_command_makes_nothing(self):
        self.install()
        project = Path(self.tmp.name) / "dur"
        project.mkdir()
        self.assertIsNone(mp.ensure_project_venv(project, run=lambda *a, **k: self.fail("no run"),
                                                 cancelled=lambda: True))
        self.assertFalse((project / ".venv").exists())

    def test_v3_every_agents_start_environment_gets_the_project_venv(self):
        self.install()
        project = Path(self.tmp.name) / "ajan"
        project.mkdir()
        made = mp.ensure_project_venv(project, run=self.fake_venv_run())
        from core.cli_installer import with_project, cli_environment
        base = {"PATH": "C:/base", "PYTHONPATH": "x", "QUARTZ_DESKTOP_URL": "u", "CODEX_HOME": "h"}
        env = with_project(base, project)
        self.assertEqual(env["PATH"].split(os.pathsep)[0], str(made.parent))
        self.assertEqual(env["VIRTUAL_ENV"], str(project / ".venv"))
        self.assertNotIn("PYTHONPATH", env)
        self.assertEqual((env["QUARTZ_DESKTOP_URL"], env["CODEX_HOME"]), ("u", "h"))  # the runtime's own env kept
        other = Path(self.tmp.name) / "baska"
        other.mkdir()
        self.assertIs(with_project(base, other), base)  # no venv, no change, no leak between projects
        self.assertIsNone(with_project(None, other))
        # The three runtimes apply it at their real start.
        root = Path(__file__).resolve().parents[1]
        for name in ("codex_runtime.py", "claude_runtime.py", "antigravity_runtime.py"):
            self.assertIn("with_project", (root / "core" / name).read_text(encoding="utf-8"), name)

    def test_v1_a_refused_plan_prepares_nothing(self):
        from core.long_job import JobError
        from core.long_job_chat import LongJobChatMixin
        import threading
        project = Path(self.tmp.name) / "plan"
        project.mkdir()
        calls = []
        chat = LongJobChatMixin.__new__(LongJobChatMixin)
        chat._lock = threading.RLock()
        chat.__dict__.update(_plan_generation=1, _closed=False, _long_jobs={})
        conv = {"id": "c1", "space": "work", "project_id": "p1"}
        chat.store = type("S", (), {"get": lambda self, cid: conv, "get_active": lambda self: conv,
                                    "get_agent_model": lambda self, c, a: {}})()
        chat.agent_service = type("A", (), {"projects": type("P", (), {
            "get": lambda self, pid: {"path": str(project)}})()})()
        with patch("core.managed_python.ensure_project_venv", side_effect=lambda *a, **k: calls.append(1)):
            with self.assertRaises(JobError):
                chat.job_start({"goal": "oyun", "milestones": [{"title": "a", "acceptance": "b"}],
                                "permission_level": "full", "plan_generation": 0, "conversation_id": "c1"})
        self.assertEqual(calls, [])
        self.assertFalse((project / ".venv").exists())

    def test_the_pin_is_an_exact_official_release(self):
        self.assertTrue(mp.URL.startswith("https://www.python.org/ftp/python/" + mp.VERSION + "/"))
        self.assertRegex(mp.SHA256, r"^[0-9a-f]{64}$")

    def test_auto_setup_prepares_python_first(self):
        from core.auto_setup import TOOLS
        self.assertEqual(TOOLS[0][0], "python")


if __name__ == "__main__":
    unittest.main()
