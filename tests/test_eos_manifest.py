"""Eos's security manifest and system, rewritten 25 Nov 2026 (user: "En baştan ve gerçekten sağlam").

The regression table is the real history: all 36 alerts recorded until 25 Nov were harmless.
"""
import json
import tempfile
import unittest
from pathlib import Path

from core import security_watch
from core.security_manifest import RULES, Signals, classify, manifest_markdown
from core.security_signals import SignatureChecker, command_target, publisher, verdict_from
from core.security_watch import SecurityWatch

ROOT = Path(__file__).resolve().parents[1]


class RealHistoryTests(unittest.TestCase):
    """Every alert Eos raised until 25 Nov, with the verdict it must get now."""

    CASES = [
        ("BackgroundDownload.exe from Temp (Visual Studio, 24x)", Signals("process", "temp", "microsoft"), "silent"),
        ("DismHost.exe from Temp (Windows, 4x)", Signals("process", "temp", "microsoft"), "silent"),
        ("msedge_cleanup RunOnce -> Edge setup.exe (3x)", Signals("autorun", "other", "microsoft", hive="HKLM"), "silent"),
        ("SpeS's own read-guard.exe in an agent's Temp workspace", Signals("process", "temp", "unsigned", own=True), "silent"),
        ("a copy of PING.EXE run from Temp (test)", Signals("process", "temp", "microsoft"), "silent"),
        ("encoded PowerShell (3x)", Signals("process", "other", "microsoft", abuse="Gizlenmiş (kodlanmış) PowerShell komutu"), "high"),
    ]

    def test_the_recorded_history_gets_the_right_verdict(self):
        for name, signals, severity in self.CASES:
            with self.subTest(name):
                self.assertEqual(classify(signals).severity, severity)


class RuleTests(unittest.TestCase):
    def verdict(self, **kw):
        return classify(Signals(**{"kind": "process", **kw}))

    def test_an_unsigned_program_from_temp_or_downloads_is_said(self):
        self.assertEqual(self.verdict(location="temp", signature="unsigned").rule, "unsigned-temp")
        self.assertEqual(self.verdict(location="downloads", signature="unsigned").rule, "unsigned-downloads")
        self.assertEqual(self.verdict(location="temp", signature="unknown").severity, "medium",
                         "a check that could not finish is not trust")

    def test_behaviour_is_never_muted_by_trust_or_by_being_ours(self):
        for signature in ("microsoft", "signed", "unsigned"):
            self.assertEqual(self.verdict(signature=signature, abuse="x", own=True).rule, "abuse")

    def test_a_broken_signature_is_high(self):
        self.assertEqual(self.verdict(location="other", signature="invalid").severity, "high")

    def test_quiet_cases(self):
        self.assertEqual(self.verdict(location="temp", signature="signed").severity, "low")
        self.assertEqual(self.verdict(location="temp", signature="missing").severity, "low")
        self.assertEqual(self.verdict(location="temp", signature="unsigned", empty=True).severity, "silent")
        self.assertEqual(classify(Signals("download", "downloads", "unsigned")).severity, "low")

    def test_autostart(self):
        self.assertEqual(classify(Signals("autorun", "other", "unsigned", hive="HKCU")).severity, "medium")
        self.assertEqual(classify(Signals("startup", "other", "unknown")).severity, "medium")
        self.assertEqual(classify(Signals("autorun", "other", "signed")).severity, "low")

    def test_defender_is_always_high_and_the_table_ends_with_a_catch_all(self):
        self.assertEqual(classify(Signals("defender")).severity, "high")
        self.assertEqual(RULES[-1].id, "other")
        self.assertEqual(len({r.id for r in RULES}), len(RULES))
        self.assertTrue(all(r.severity in ("high", "medium", "low", "silent") for r in RULES))

    def test_the_manifest_document_is_generated_from_the_table(self):
        document = (ROOT / "docs" / "EOS_GUVENLIK_MANIFESTI.md").read_text(encoding="utf-8")
        self.assertEqual(document, manifest_markdown(),
                         "regenerate: python -c \"from core.security_manifest import manifest_markdown; ...\"")
        for rule in RULES:
            self.assertIn(f"`{rule.id}`", document)


class SignalTests(unittest.TestCase):
    def test_windows_answers_map_to_manifest_words(self):
        ms = "CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US"
        self.assertEqual(verdict_from("Valid", ms, True), "microsoft")
        self.assertEqual(verdict_from("Valid", "CN=Valve, O=Valve Corp., C=US", True), "signed")
        self.assertEqual(verdict_from("Valid", "CN=Evil, O=Not Microsoft Corporation Ltd", True), "signed")
        self.assertEqual(verdict_from("NotSigned", "", True), "unsigned")
        self.assertEqual(verdict_from("HashMismatch", ms, True), "invalid")
        self.assertEqual(verdict_from("UnknownError", "", True), "unknown")
        self.assertEqual(verdict_from("", "", True), "unknown")
        self.assertEqual(verdict_from("Valid", ms, False), "missing")
        self.assertEqual(publisher(ms), "Microsoft Corporation")

    def test_the_autostart_target_is_found(self):
        self.assertEqual(command_target('"C:\\Program Files (x86)\\Microsoft\\Edge\\setup.exe" --msedge --x'),
                         "C:\\Program Files (x86)\\Microsoft\\Edge\\setup.exe")
        self.assertEqual(command_target("C:\\Program Files\\Tool\\tool.exe --tray"), "C:\\Program Files\\Tool\\tool.exe")
        self.assertEqual(command_target("C:/x.exe"), "C:/x.exe")

    def test_paths_travel_as_data_and_results_are_cached(self):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs["env"]["SPES_SIGNATURE_PATHS"]))
            paths = json.loads(kwargs["env"]["SPES_SIGNATURE_PATHS"])
            return type("Done", (), {"stdout": json.dumps([{"path": p, "status": "NotSigned", "subject": ""} for p in paths])})()

        with tempfile.TemporaryDirectory() as folder:
            odd = Path(folder) / "a'; Remove-Item -Recurse x; '.exe"
            odd.write_bytes(b"MZ")
            checker = SignatureChecker(run=run)
            self.assertEqual(checker.check([str(odd), str(Path(folder) / "gone.exe")]),
                             {str(odd): {"verdict": "unsigned", "publisher": ""},
                              str(Path(folder) / "gone.exe"): {"verdict": "missing", "publisher": ""}})
            checker.check([str(odd)])
        self.assertEqual(len(calls), 1, "the second check is served from the cache")
        argv, env_paths = calls[0]
        self.assertNotIn("Remove-Item", " ".join(argv), "paths never enter the command text")
        self.assertNotIn("-EncodedCommand", argv)
        self.assertIn("Remove-Item", env_paths)

    def test_a_failed_check_is_unknown_and_not_cached(self):
        def broken(argv, **kwargs):
            raise OSError("powershell missing")
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "x.exe"
            exe.write_bytes(b"MZ")
            checker = SignatureChecker(run=broken)
            self.assertEqual(checker.check([str(exe)])[str(exe)]["verdict"], "unknown")
            self.assertEqual(checker._cache, {})


@unittest.skipUnless(Path(r"C:\Windows\System32\PING.EXE").is_file(), "Windows Authenticode only")
class RealSignatureTests(unittest.TestCase):
    def test_a_batch_of_paths_gets_one_answer_each(self):
        # Live 25 Nov: PowerShell 5.1 wrapped a 2-path list into one item; every answer was 'unknown'.
        with tempfile.TemporaryDirectory() as folder:
            mine = Path(folder) / "imzasiz.ps1"  # an unsigned script: a fake exe would be 'unknown'
            mine.write_text("Write-Output 1", encoding="utf-8")
            result = SignatureChecker().check([r"C:\Windows\System32\PING.EXE", str(mine), str(Path(folder) / "yok.exe")])
        self.assertEqual(result[r"C:\Windows\System32\PING.EXE"]["verdict"], "microsoft")
        self.assertEqual(result[str(mine)]["verdict"], "unsigned")
        self.assertEqual(result[str(Path(folder) / "yok.exe")]["verdict"], "missing")


class WatcherBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.temp, self.downloads = base / "Temp", base / "Downloads"
        self.temp.mkdir()
        self.downloads.mkdir()
        self.dirs = unittest.mock.patch.object(security_watch, "_user_dirs",
                                               return_value={"temp": self.temp, "downloads": self.downloads})
        self.dirs.start()
        self.base, self.procs, self.autoruns, self.emitted, self.signed = base, [], [], [], {}
        self.now = [1000.0]
        self.watch = self.make()

    def tearDown(self):
        self.dirs.stop()
        self.tmp.cleanup()

    def make(self):
        return SecurityWatch(self.emitted.append, clock=lambda: self.now[0], quarantine_root=self.base / "q",
                             collectors={"processes": lambda: list(self.procs), "autoruns": lambda: list(self.autoruns),
                                         "downloads": lambda: [], "defender": lambda after: []},
                             signatures=lambda paths: {p: {"verdict": self.signed.get(p, "unsigned"), "publisher": ""}
                                                       for p in paths})

    def tick(self, watch=None):
        self.now[0] += 200
        (watch or self.watch).tick(force=True)

    def program(self, pid, name, content):
        exe = self.temp / name
        exe.write_bytes(content)
        self.procs.append({"pid": pid, "name": name, "exe": str(exe), "create": float(pid), "cmdline": ""})
        return str(exe)

    def test_a_microsoft_signed_helper_from_temp_is_not_said(self):
        self.watch.tick(force=True)
        self.signed[self.program(10, "DismHost.exe", b"MZ-dism")] = "microsoft"
        self.program(11, "bilinmeyen.exe", b"MZ-x")
        self.tick()
        said = [a["detail"].split(" ")[0] for a in self.emitted]
        self.assertEqual(said, ["bilinmeyen.exe"])
        self.assertEqual(self.emitted[0]["rule"], "unsigned-temp")
        self.assertIn("imzasız", self.emitted[0]["detail"])

    def test_a_burst_never_blinds_the_record(self):
        # Before 25 Nov the limit returned before storing: six harmless finds hid the seventh.
        self.watch.tick(force=True)
        for n in range(10):
            self.program(100 + n, f"arac{n}.exe", b"MZ-%d" % n)
        self.tick()
        self.assertEqual(len(self.emitted), security_watch.MAX_ALERTS_PER_10_MIN)
        self.assertEqual(len([a for a in self.watch.alerts() if a["kind"] == "process"]), 10)

    def test_an_autostart_added_while_spes_was_closed_is_reported(self):
        self.autoruns.append({"kind": "registry", "hive": "HKCU", "key": r"Software\Microsoft\Windows\CurrentVersion\Run",
                              "name": "Eski", "data": "C:/eski.exe"})
        self.watch.tick(force=True)  # first run: baseline, saved to disk
        self.assertTrue((self.base / "eos_state.json").is_file())
        self.autoruns.append({"kind": "registry", "hive": "HKCU", "key": r"Software\Microsoft\Windows\CurrentVersion\Run",
                              "name": "Yeni", "data": "C:/yeni.exe"})
        restarted = self.make()       # SpeS closed and opened again
        restarted.tick(force=True)
        names = [a["detail"] for a in self.emitted if a["kind"] == "autorun"]
        self.assertEqual(len(names), 1)
        self.assertIn("'Yeni'", names[0])

    def test_what_was_said_is_remembered_across_a_restart(self):
        self.watch.tick(force=True)
        self.program(20, "arac.exe", b"MZ-same")
        self.tick()
        restarted = self.make()
        restarted.tick(force=True)
        self.program(21, "arac.exe", b"MZ-same")
        self.tick(restarted)
        self.assertEqual(len([a for a in self.emitted if a["kind"] == "process"]), 1)


import unittest.mock  # noqa: E402  (used above through unittest.mock)

if __name__ == "__main__":
    unittest.main()
