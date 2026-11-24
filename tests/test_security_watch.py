"""Eos the security watcher: report, ring, act only on the user's tap (14 Nov 2026)."""
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import security_watch
from core.security_watch import SecurityWatch
from tests.test_team_turn import make_chat


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.downloads, self.temp = base / "Downloads", base / "Temp"
        self.downloads.mkdir()
        self.temp.mkdir()
        self.dirs = patch.object(security_watch, "_user_dirs", return_value={"temp": self.temp, "downloads": self.downloads})
        self.dirs.start()
        self.procs, self.autoruns, self.defender = [], [], []
        self.emitted = []
        self.clock = Clock()
        self.watch = SecurityWatch(self.emitted.append, clock=self.clock, quarantine_root=base / "q", collectors={
            "processes": lambda: list(self.procs), "autoruns": lambda: list(self.autoruns),
            "downloads": security_watch.collect_downloads,
            "defender": lambda after: [r for r in self.defender if r["record"] > after]})

    def tearDown(self):
        self.dirs.stop()
        self.tmp.cleanup()

    def tick(self):
        self.clock.now += 200
        self.watch.tick(force=True)

    def test_first_scan_is_a_baseline(self):
        self.procs.append({"pid": 1, "name": "x.exe", "exe": str(self.downloads / "x.exe"), "create": 1.0,
                           "cmdline": "powershell -enc " + "A" * 40})
        (self.downloads / "kurulum.exe").write_bytes(b"MZ")
        self.defender.append({"record": 5, "event": 1116, "threat": "Old", "path": "C:/old"})
        self.watch.tick(force=True)
        self.assertEqual(self.emitted, [])

    def test_new_findings_are_reported_with_their_own_actions(self):
        self.watch.tick(force=True)
        self.procs.append({"pid": 10, "name": "fatura.exe", "exe": str(self.downloads / "fatura.exe"), "create": 2.0, "cmdline": ""})
        (self.downloads / "fatura.exe").write_bytes(b"MZ-fatura")
        self.procs.append({"pid": 11, "name": "powershell.exe", "exe": "C:/Windows/powershell.exe", "create": 3.0,
                           "cmdline": "powershell.exe -NoP -enc " + "SQBFAFgA" * 6})
        self.autoruns.append({"kind": "registry", "hive": "HKLM", "key": r"Software\Microsoft\Windows\CurrentVersion\Run",
                              "name": "Guncelleyici", "data": "C:/x.exe"})
        self.defender.append({"record": 9, "event": 1116, "threat": "Trojan:Win32/Test", "path": "C:/t.exe", "action": ""})
        self.tick()
        titles = {a["title"]: a for a in self.emitted}
        downloaded = next(a for t, a in titles.items() if "İndirilenler klasöründen" in t)
        self.assertEqual((downloaded["severity"], downloaded["actions"]), ("medium", ["stop", "quarantine", "ignore"]))
        encoded = next(a for t, a in titles.items() if "kodlanmış" in t)
        self.assertEqual(encoded["severity"], "high")
        self.assertNotIn("SQBFAFgA", encoded["detail"])  # command line is not repeated
        autorun = next(a for t, a in titles.items() if "açılışına" in t)
        self.assertEqual(autorun["actions"], ["ignore"])  # HKLM needs admin: not offered
        self.assertTrue(any(a["title"].startswith("Windows Defender") and a["severity"] == "high" for a in self.emitted))
        self.assertTrue(any(a["kind"] == "download" and a["severity"] == "low" for a in self.emitted))
        self.assertNotIn("_target", downloaded)

    def test_spes_own_helpers_are_not_reported(self):
        # Live 14 Nov: SpeS's read-guard.exe ran from a Temp workspace and Eos reported it.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(self.watch.is_own(child.pid))  # our own child
            self.watch.tick(force=True)
            self.procs.append({"pid": child.pid, "name": "read-guard.exe",
                               "exe": str(self.temp / "quartz-text-chat-x" / "read-guard.exe"), "create": 5.0, "cmdline": ""})
            self.tick()
            self.assertEqual([a for a in self.emitted if a["kind"] == "process"], [])
        finally:
            child.kill()
        self.assertFalse(self.watch.is_own(4))  # the System process is not ours

    def test_a_copy_of_the_spes_helper_is_recognised_by_its_content(self):
        helper = self.temp / "QuartzDesktopMCP.exe"
        helper.write_bytes(b"MZ-spes-helper")
        copy = self.temp / "quartz-text-chat-y" / ".agents" / "read-guard.exe"
        copy.parent.mkdir(parents=True)
        copy.write_bytes(b"MZ-spes-helper")
        stranger = self.temp / "read-guard2.exe"
        stranger.write_bytes(b"MZ-something-else")
        with patch.object(SecurityWatch, "_own_hashes", {security_watch._sha256(helper)}):
            self.assertTrue(self.watch.is_own(4, str(copy)))
            self.assertFalse(self.watch.is_own(4, str(stranger)))  # same name idea, other bytes

    def test_stop_acts_only_on_the_exact_process_once(self):
        import psutil
        self.watch.is_own = lambda pid, exe=None: False  # the test's own child stands in for a stranger
        self.watch.tick(force=True)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            proc = psutil.Process(child.pid)
            self.procs.append({"pid": child.pid, "name": proc.name(), "exe": str(self.temp / "fake.exe"),
                               "create": proc.create_time(), "cmdline": ""})
            self.tick()
            alert = next(a for a in self.emitted if a["kind"] == "process")
            stale = dict(self.watch._alerts[alert["id"]]["_target"])
            result = self.watch.act(alert["id"], "stop")
            self.assertTrue(result["ok"], result)
            child.wait(timeout=10)
            self.assertFalse(self.watch.act(alert["id"], "stop")["ok"])  # single use
            self.assertFalse(self.watch.act(alert["id"], "quarantine")["ok"])  # not one of its actions
            # A recycled PID (different start time) is never touched.
            self.assertFalse(self.watch._stop_process({**stale, "pid": psutil.Process().pid, "create": 1.0})["ok"])
        finally:
            if child.poll() is None:
                child.kill()

    def test_quarantine_checks_the_hash_and_can_be_undone(self):
        self.watch.tick(force=True)
        target = self.downloads / "kampanya.exe"
        target.write_bytes(b"MZ-1")
        self.tick()
        alert = next(a for a in self.emitted if a["kind"] == "download")
        result = self.watch.act(alert["id"], "quarantine")
        self.assertTrue(result["ok"] and result["undo"], result)
        self.assertFalse(target.exists())
        self.assertTrue(self.watch.act(alert["id"], "undo")["ok"])
        self.assertEqual(target.read_bytes(), b"MZ-1")
        # Changed after the alert: refused.
        other = self.downloads / "degisen.exe"
        other.write_bytes(b"MZ-a")
        self.tick()
        second = next(a for a in self.emitted if a["kind"] == "download" and "degisen" in a["detail"])
        other.write_bytes(b"MZ-b")
        self.assertFalse(self.watch.act(second["id"], "quarantine")["ok"])
        self.assertTrue(other.exists())

    def test_expired_and_unknown_alerts_do_nothing(self):
        self.watch.tick(force=True)
        (self.downloads / "eski.exe").write_bytes(b"MZ")
        self.tick()
        alert = self.emitted[-1]
        self.clock.now += security_watch.ALERT_TTL + 1
        self.assertFalse(self.watch.act(alert["id"], "quarantine")["ok"])
        self.assertFalse(self.watch.act("yok", "ignore")["ok"])

    def test_low_and_medium_alerts_are_rate_limited_high_never(self):
        self.watch.tick(force=True)
        for n in range(10):
            (self.downloads / f"f{n}.exe").write_bytes(b"MZ")
        self.defender.append({"record": 50, "event": 1116, "threat": "X", "path": "C:/x"})
        self.tick()
        self.assertEqual(sum(1 for a in self.emitted if a["severity"] != "high"), security_watch.MAX_ALERTS_PER_10_MIN)
        self.assertTrue(any(a["severity"] == "high" for a in self.emitted))


class RepeatQuietTests(WatchTests):
    """Live 24 Nov: DismHost.exe and Visual Studio's BackgroundDownload.exe started from Temp
    dozens of times and each start was said in the chat."""

    def start(self, pid, name, folder="a"):
        exe = self.temp / folder / name
        self.procs.append({"pid": pid, "name": name, "exe": str(exe), "create": float(pid), "cmdline": ""})

    def test_the_same_temp_program_is_said_once_a_day(self):
        self.watch.tick(force=True)
        self.start(20, "DismHost.exe", "6CE3586A")
        self.tick()
        self.start(21, "DismHost.exe", "A3C8DB23")
        self.start(22, "kurulum.exe")
        self.tick()
        said = [a["detail"].split(" ")[0] for a in self.emitted if a["kind"] == "process"]
        self.assertEqual(said, ["DismHost.exe", "kurulum.exe"])
        self.assertEqual(sum(a["detail"].startswith("DismHost.exe") for a in self.watch.alerts()), 2,
                         "the repeat stays in the list and can still be acted on")
        self.clock.now += security_watch.REPEAT_QUIET
        self.start(23, "DismHost.exe", "B1")
        self.tick()
        self.assertEqual([a["detail"].split(" ")[0] for a in self.emitted if a["kind"] == "process"][-1], "DismHost.exe")

    def test_a_high_finding_is_never_quieted(self):
        self.watch.tick(force=True)
        for pid in (30, 31):
            self.procs.append({"pid": pid, "name": "powershell.exe", "exe": "C:/Windows/powershell.exe",
                               "create": float(pid), "cmdline": "powershell -NoP -enc " + "SQBFAFgA" * 6})
            self.tick()
        self.assertEqual(sum(a["severity"] == "high" for a in self.emitted), 2)


class ChatTests(unittest.TestCase):
    def test_alerts_reach_the_chat_and_high_ones_ring(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            cid = chat.store.get_active()["id"]
            chat._post_security_alert({"id": "a1", "severity": "low", "title": "İndirme", "detail": "x", "actions": []})
            chat._post_security_alert({"id": "a2", "severity": "high", "title": "Defender tehdit buldu", "detail": "Trojan",
                                       "actions": ["ignore"]})
            messages = chat.store.get(cid)["messages"]
            self.assertEqual(chat.security_act("a2", "ignore"), {"ok": False, "message": "Güvenlik izleyicisi çalışmıyor."})
            chat._diagnostics.close()
        posted = [m for m in messages if (m.get("metadata") or {}).get("security_alert")]
        self.assertEqual(len(posted), 1)  # the low one stays in the watcher's list
        self.assertEqual(posted[0]["metadata"]["notify"], "call")
        self.assertEqual(posted[0]["metadata"]["persona"], "Eos")


if __name__ == "__main__":
    unittest.main()
