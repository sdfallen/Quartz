"""SpeS tries a program inside its window (core.launch_interact) — Fides's design review 26 Nov.

No test sends real input: the backend is a fake that records every action it receives, so "no
input" is measured as an empty action list."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import launch_interact as li


class FakeBackend:
    def __init__(self, foreground=True, act_error=None):
        self.acts, self.foreground, self.act_error = [], foreground, act_error
        self.focused = 0
        self.input_cancelled = None
        self.observed = 0

    def identity(self, hwnd):
        return {"handle": hwnd, "pid": 7, "started": 1.0, "exe": r"C:\py\python.exe", "title": "Sayaç",
                "rect": [100, 100, 400, 340]}

    def validate_target(self, target):
        pass

    def validate_input_session(self):
        pass

    def focus(self, target):
        self.focused += 1

    def is_foreground(self, target):
        return self.foreground() if callable(self.foreground) else self.foreground

    def observe(self, target):
        self.observed += 1
        return {"ui": {}, "image_base64": "iVBORw0KGgo=", "width": 300, "height": 240}

    def act(self, target, observation, args):
        if self.act_error:
            raise self.act_error
        self.acts.append(args)

    def _before_input(self, target):
        if not self.is_foreground(target):
            raise PermissionError("Target lost foreground before input")


class Probe:
    """Writes a probe report the way the probe does (pid, seq, time)."""

    def __init__(self, folder, pid=7):
        self.path, self.pid, self.seq = Path(folder) / "probe.json", pid, 0

    def write(self, widgets=(), kind="tk", w=300, h=200, errors=(), at=None, pid=None):
        self.seq += 1
        self.path.write_text(json.dumps({
            "kind": kind, "w": w, "h": h, "widgets": list(widgets), "errors": list(errors),
            "error_count": len(errors), "pid": self.pid if pid is None else pid, "seq": self.seq,
            "at": time.time() if at is None else at}), encoding="utf-8")


def widget(text, x=10, y=10, w=40, h=20, enabled=True, cls="Button"):
    return {"class": cls, "text": text, "x": x, "y": y, "w": w, "h": h, "enabled": enabled}


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def load(self, text):
        (self.root / li.SCENARIO_NAME).write_text(text, encoding="utf-8")
        return li.load_scenario(self.root)

    def test_no_file_is_no_scenario(self):
        self.assertEqual(li.load_scenario(self.root), (None, "senaryo yok"))

    def test_a_valid_scenario_is_read_once_with_its_hash(self):
        loaded, why = self.load('{"surum": 1, "adimlar": [{"tikla": "Artır"}, {"beklenen": "Sayı:  1"}]}')
        self.assertEqual(why, "")
        self.assertEqual(loaded["steps"][1], {"do": "expect", "text": "Sayı: 1", "contains": False})
        self.assertEqual(len(loaded["sha256"]), 64)

    def test_d4_the_whole_scenario_is_refused_for_one_bad_step(self):
        for text in ('{"adimlar": [{"tikla": "A"}, {"sil": "x"}]}',
                     '{"adimlar": [{"tikla": "A", "tikla": "B"}]}',
                     '{"adimlar": [{"bekle": NaN}]}',
                     '{"adimlar": [{"bekle": true}]}',
                     '{"adimlar": [{"bas": "right", "sure": 0}]}',
                     '{"adimlar": [{"bas": "right", "sure": 2}]}',
                     '{"adimlar": [{"bekle": 9}]}',
                     '{"adimlar": [{"tikla": [1.5, 2]}]}',
                     '{"adimlar": [{"tikla": "A", "tus": "a"}]}',
                     '{"adimlar": [], "komut": "x"}',
                     '{"surum": 2, "adimlar": [{"tikla": "A"}]}',
                     '{"adimlar": []}'):
            loaded, why = self.load(text)
            self.assertIsNone(loaded, text)
            self.assertTrue(why.startswith("senaryo geçersiz"), (text, why))

    def test_d1_scenario_keys_are_a_small_subset(self):
        for keys in ("win", "alt", "ctrl", "f4", "volumemute", "browserback", "shift"):
            self.assertIsNone(self.load('{"adimlar": [{"tus": "%s"}]}' % keys)[0], keys)
        self.assertIsNotNone(self.load('{"adimlar": [{"tus": "Left left SPACE enter 1 a"}]}')[0])

    def test_d1_a_consequential_button_text_is_refused_before_any_step(self):
        loaded, why = self.load('{"adimlar": [{"tikla": "Kaydet"}]}')
        self.assertIsNone(loaded)
        self.assertIn("SpeS basmaz", why)

    def test_too_many_steps_and_too_big_files_are_refused(self):
        self.assertIsNone(self.load(json.dumps({"adimlar": [{"bekle": 0.1}] * (li.MAX_STEPS + 1)}))[0])
        self.assertIsNone(self.load('{"adimlar": [{"bekle": 0.1}], "x": "%s"}' % ("a" * li.MAX_BYTES))[0])


class PixelTests(unittest.TestCase):
    TARGET = {"rect": [100, 100, 400, 340]}

    def test_d3_the_client_corner_and_frame_offset_are_both_counted(self):
        # client area starts 8 px right and 31 px down of the window rectangle (frame + title)
        x, y = li.to_window_pixels(self.TARGET, {"w": 280, "h": 200}, 10, 20, (108, 131, 280, 200))
        self.assertEqual((x, y), (18, 51))

    def test_d3_a_dpi_scale_is_applied_from_the_measured_sizes(self):
        x, y = li.to_window_pixels(self.TARGET, {"w": 200, "h": 100}, 100, 50, (108, 131, 300, 150))
        self.assertEqual((x, y), (158, 106))

    def test_d3_disagreeing_axes_and_an_unknown_size_click_nothing(self):
        with self.assertRaises(PermissionError):
            li.to_window_pixels(self.TARGET, {"w": 200, "h": 100}, 10, 10, (108, 131, 300, 200))
        with self.assertRaises(PermissionError):
            li.to_window_pixels(self.TARGET, None, 10, 10, (108, 131, 300, 200))

    def test_a_point_outside_the_client_area_is_refused(self):
        with self.assertRaises(ValueError):
            li.to_window_pixels(self.TARGET, {"w": 280, "h": 200}, 290, 20, (108, 131, 280, 200))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.probe = Probe(self.tmp.name)

    def test_d4_another_process_a_stale_or_a_broken_report_is_none(self):
        self.probe.write([widget("A")], pid=99)
        self.assertIsNone(li.read_report(self.probe.path, pid=7))
        self.probe.write([widget("A")], at=time.time() - 60)
        self.assertIsNone(li.read_report(self.probe.path, pid=7))
        self.probe.path.write_text("{yarım", encoding="utf-8")
        self.assertIsNone(li.read_report(self.probe.path, pid=7))
        self.probe.write([widget("A")])
        self.assertEqual(li.read_report(self.probe.path, pid=7)["widgets"][0]["text"], "A")


class RunTests(unittest.TestCase):
    CLIENT = (108, 131, 300, 200)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.probe = Probe(self.tmp.name)
        self.review = Path(self.tmp.name) / "denetci"
        self.stop = threading.Event()

    def run_steps(self, steps, backend=None, alive=lambda: True, cursor=lambda: (5, 5), **kw):
        self.backend = backend or FakeBackend()
        return li.run(self.backend, 42, li.validate(steps), self.stop, report_path=self.probe.path,
                      review_dir=self.review, alive=alive, pid=7, settle=0, client_area=lambda h: self.CLIENT,
                      cursor=cursor, **kw)

    def test_minimum_a_real_click_then_a_measured_expectation(self):
        self.probe.write([widget("Artır", x=40, y=60, w=60, h=30), widget("0", cls="Label")])
        clicks = []

        def act(target, observation, args):
            clicks.append(args)
            self.probe.write([widget("Artır", x=40, y=60, w=60, h=30), widget("1", cls="Label")])
        backend = FakeBackend()
        backend.act = act
        result = self.run_steps([{"beklenen": "0"}, {"tikla": "Artır"}, {"beklenen": "1"}], backend)
        self.assertEqual(result["state"], "passed", result)
        self.assertEqual(clicks, [{"action": "click", "x": 78, "y": 106}])
        self.assertEqual((result["actions"], result["asserted"]), (1, 2))
        self.assertTrue((self.review / "adim-02-once.png").is_file())
        self.assertIn("hepsi tuttu (sonda ölçümü)", li.summary(result))

    def test_q2_exact_is_the_default_so_10_is_not_1(self):
        self.probe.write([widget("Sayı: 10", cls="Label")])
        result = self.run_steps([{"beklenen": "Sayı: 1"}])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["steps"][0]["seen"], ["Sayı: 10"])
        self.probe.write([widget("Sayı: 10", cls="Label")])
        self.assertEqual(self.run_steps([{"beklenen_icerir": "Sayı: 1"}])["state"], "passed")

    def test_minimum_no_unique_visible_enabled_match_sends_no_input(self):
        for widgets in ([], [widget("Artır"), widget("Artır", x=80)], [widget("Artır", enabled=False)],
                        [widget("Artır", w=0, h=0)]):
            self.probe.write(widgets)
            result = self.run_steps([{"tikla": "Artır"}])
            self.assertEqual(result["state"], "failed", widgets)
            self.assertEqual(self.backend.acts, [], widgets)

    def test_d4_no_fresh_report_blocks_a_text_click_and_leaves_expectations_unmeasured(self):
        result = self.run_steps([{"beklenen": "1"}])
        self.assertEqual(result["state"], "unproven")
        self.assertEqual(result["unmeasured"], 1)
        result = self.run_steps([{"tikla": "Artır"}])
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.backend.acts, [])

    def test_q2_input_without_an_assertion_is_only_smoke(self):
        self.probe.write([], kind="pygame", w=300, h=200)
        result = self.run_steps([{"tus": "space"}, {"tikla": [10, 10]}])
        self.assertEqual(result["state"], "smoke")
        self.assertEqual(len(self.backend.acts), 2)
        self.assertIn("yalnız duman testi", li.summary(result))

    def test_stop_before_any_step_sends_nothing(self):
        self.probe.write([widget("Artır")])
        self.stop.set()
        result = self.run_steps([{"tikla": "Artır"}, {"tus": "space"}])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(self.backend.acts, [])

    def test_stop_during_a_wait_ends_it(self):
        threading.Timer(0.1, self.stop.set).start()
        began = time.monotonic()
        result = self.run_steps([{"bekle": 3}, {"tus": "space"}])
        self.assertEqual(result["state"], "cancelled")
        self.assertLess(time.monotonic() - began, 2)
        self.assertEqual(self.backend.acts, [])

    def test_q4_a_mouse_moved_by_someone_else_stops_the_run(self):
        positions = iter([(5, 5), (5, 5), (5, 5), (300, 300)])
        result = self.run_steps([{"tus": "a"}, {"tus": "b"}], cursor=lambda: next(positions))
        self.assertEqual(result["state"], "blocked")
        self.assertIn("fare", result["reason"])
        self.assertEqual(self.backend.acts, [{"action": "key", "key": "a"}])

    def test_a_lost_foreground_is_blocked_never_refocused(self):
        backend = FakeBackend()
        states = iter([True, False])
        backend.is_foreground = lambda target: next(states, False)
        result = self.run_steps([{"tus": "a"}], backend)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(backend.focused, 1)
        self.assertEqual(backend.acts, [])

    def test_a_refused_action_is_blocked_not_a_defect(self):
        result = self.run_steps([{"tus": "a"}], FakeBackend(act_error=PermissionError("Consequential control")))
        self.assertEqual(result["state"], "blocked")

    def test_a_callback_error_fails_the_step(self):
        self.probe.write([widget("Böl")])
        backend = FakeBackend()
        backend.act = lambda t, o, a: self.probe.write([widget("Böl")], errors=["ZeroDivisionError"])
        result = self.run_steps([{"tikla": "Böl"}], backend)
        self.assertEqual(result["state"], "failed")
        self.assertIn("ZeroDivisionError", result["error"])

    def test_a_program_that_ends_mid_scenario_is_crashed(self):
        alive = iter([True, False, False, False])
        result = self.run_steps([{"tus": "a"}, {"tus": "b"}], alive=lambda: next(alive, False))
        self.assertEqual(result["state"], "crashed")

    def native(self, focused="Sayaç"):
        """The real NativeDesktopBackend.act with the window and keyboard faked (Fides's probe shape)."""
        from contextlib import nullcontext
        from types import SimpleNamespace
        from core.desktop_native import NativeDesktopBackend
        backend = NativeDesktopBackend.__new__(NativeDesktopBackend)
        backend.is_foreground = lambda target: True
        backend._safe_controls = lambda target: None
        backend._before_input = lambda target: None
        backend.controller = SimpleNamespace(_desktop=lambda: nullcontext(object()), _window=lambda d, h: object(),
                                             focused_control=lambda w: object(),
                                             _describe=lambda c: {"name": focused})
        return backend

    def test_d2_i4_a_hold_goes_through_native_act_and_stop_releases_the_key(self):
        downs, ups = [], []
        fake = type("P", (), {"FAILSAFE": True, "keyDown": staticmethod(downs.append),
                              "keyUp": staticmethod(ups.append)})
        threading.Timer(0.1, self.stop.set).start()
        with patch.dict("sys.modules", {"pyautogui": fake}):
            with self.assertRaises(PermissionError):
                li._hold(self.native(), {"handle": 42}, "right", 1, self.stop)
        self.assertEqual((downs, ups), (["right"], ["right"]))

    def test_i4_a_hold_on_a_consequential_focused_control_presses_nothing(self):
        downs = []
        fake = type("P", (), {"FAILSAFE": True, "keyDown": staticmethod(downs.append),
                              "keyUp": staticmethod(lambda key: None)})
        with patch.dict("sys.modules", {"pyautogui": fake}):
            with self.assertRaises(PermissionError):
                li._hold(self.native(focused="Kaydet"), {"handle": 42}, "enter", 0.2, self.stop)
        self.assertEqual(downs, [])

    def test_i1_one_unmeasured_expectation_is_never_a_pass(self):
        self.probe.write([widget("1", cls="Label")])
        reports = iter([li.read_report(self.probe.path, pid=7)] * 2 + [None])
        with patch.object(li, "read_report", side_effect=lambda *a, **k: next(reports)):
            result = self.run_steps([{"beklenen": "1"}, {"beklenen": "2"}])
        self.assertEqual(result["state"], "unproven")
        self.assertIn("kanıtlanamadı", li.summary(result))

    def test_i2_an_error_in_the_same_sample_as_a_match_fails(self):
        self.probe.write([widget("1", cls="Label")])
        self.assertEqual(self.run_steps([{"beklenen": "1"}])["state"], "passed")
        self.probe.write([widget("1", cls="Label")], errors=["ValueError"])
        self.assertEqual(self.run_steps([{"bekle": 0.1}])["state"], "failed")

    def test_i3_a_window_whose_owner_changed_gets_no_input(self):
        backend = FakeBackend()
        original, calls = backend.identity, [0]

        def identity(hwnd):
            calls[0] += 1
            found = original(hwnd)
            if calls[0] > 1:
                found.update(pid=8, started=99.0, exe=r"C:\other.exe")
            return found
        backend.identity = identity
        result = self.run_steps([{"tus": "a"}], backend)
        self.assertEqual((result["state"], backend.acts), ("blocked", []))

    def test_i3_a_window_not_of_the_launched_process_is_never_focused(self):
        backend = FakeBackend()
        result = li.run(backend, 42, li.validate([{"tus": "a"}]), self.stop, report_path=self.probe.path,
                        review_dir=self.review, alive=lambda: True, pid=8, settle=0,
                        client_area=lambda h: self.CLIENT, cursor=lambda: (5, 5))
        self.assertEqual((result["state"], backend.focused, backend.acts), ("blocked", 0, []))

    def test_i5_a_blocked_observation_returns_at_stop_and_stays_owned(self):
        entered, release = threading.Event(), threading.Event()
        backend = FakeBackend()
        original = backend.observe

        def observe(target):
            entered.set()
            release.wait(5)
            return original(target)
        backend.observe = observe
        workers, result = [], {}
        runner = threading.Thread(target=lambda: result.update(self.run_steps([{"tus": "a"}], backend,
                                                                                workers=workers)))
        try:
            runner.start()
            self.assertTrue(entered.wait(2))
            self.stop.set()
            runner.join(0.5)
            self.assertFalse(runner.is_alive(), "Stop is not held by a blocked call")
            self.assertEqual(result["state"], "cancelled")
            self.assertEqual(len(workers), 1)
            self.assertFalse(workers[0].finished(0), "the given-up call is still on record")
        finally:
            release.set()
        self.assertTrue(workers[0].finished(2))
        self.assertEqual(backend.acts, [])

    def test_i5_a_given_up_call_cannot_send_late_input(self):
        backend = FakeBackend()
        seen = []
        backend._before_input = lambda target: seen.append("original")
        release = threading.Event()

        def act(target, observation, args):
            release.wait(5)
            backend._before_input(target)  # what Native does right before pressing
            backend.acts.append(args)
        backend.act = act
        workers = []
        result = self.run_steps([{"tus": "a"}], backend, workers=workers, call_seconds=0.1)
        self.assertEqual(result["state"], "blocked")
        release.set()
        self.assertTrue(workers[-1].finished(2))
        self.assertIsInstance(workers[-1].error, PermissionError)
        self.assertEqual((backend.acts, seen), ([], []))

    def test_i6_no_input_after_the_deadline_passed_during_observation(self):
        backend = FakeBackend()
        original = backend.observe
        backend.observe = lambda target: time.sleep(0.08) or original(target)
        result = self.run_steps([{"tus": "a"}], backend, max_seconds=0.02)
        self.assertEqual((result["state"], backend.acts), ("blocked", []))

    def test_the_time_budget_ends_the_run(self):
        result = self.run_steps([{"bekle": 0.2}, {"tus": "a"}], max_seconds=0.05)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.backend.acts, [])


class ProbeTests(unittest.TestCase):
    """The probe really runs a program (no window: Tk is never created)."""

    def test_the_probe_runs_the_entry_as_main_with_its_folder_on_the_path(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "yardim.py").write_text("X = 41\n", encoding="utf-8")
            (root / "main.py").write_text(
                "import sys, yardim\nif __name__ == '__main__':\n    print(yardim.X + 1, sys.argv[0].endswith('main.py'))\n",
                encoding="utf-8")
            probe = li.write_probe(root)
            out = subprocess.run([sys.executable, "-B", str(probe), str(root / "main.py")], cwd=folder,
                                 capture_output=True, text=True, timeout=30,
                                 env={"SPES_PROBE_OUT": str(root / "probe.json"), "SYSTEMROOT": "C:\\Windows"})
            self.assertEqual(out.stdout.strip(), "42 True", out.stderr)


@unittest.skipUnless(__import__("os").name == "nt", "Windows Job Object")
class ObserveWiringTests(unittest.TestCase):
    """launch_check.observe with a real (windowless) process; the window and capture are faked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "p").mkdir()
        self.entry = self.root / "p" / "main.py"
        self.entry.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

    def observe(self, interact, state="captured"):
        import sys
        from core import launch_check as lc

        def capture(hwnd, result, verify):
            result.update(state=state, png=b"png")
        with patch.object(lc, "_owner_pid", side_effect=lambda hwnd: self.pid[0]):
            return lc.observe(self.entry, self.root / "p", self.root / "kanit", threading.Event(), sys.executable,
                              windows=lambda pids: self.pid.__setitem__(0, min(pids)) or [(1234, min(pids), "T")],
                              settle=0.2, capture=capture, interact=interact)

    def test_the_scenario_runs_through_the_probe_in_the_proved_window_and_cleanup_stays_one(self):
        from core import launch_check as lc
        self.pid, seen = [0], []

        def interact(hwnd, stop, **kw):
            seen.append((hwnd, kw["pid"], kw["alive"](), Path(kw["report_path"]).name))
            return {"state": "passed", "steps": [{"n": 1, "do": "key", "ok": True}], "actions": 1, "asserted": 1}
        receipt = self.observe(interact)
        self.assertEqual(seen, [(1234, self.pid[0], True, "probe.json")])
        self.assertTrue((self.root / "kanit" / "spes_probe.py").is_file())
        self.assertEqual(receipt["cleanup_state"], "confirmed")
        self.assertEqual(lc.verdict(receipt), "window_seen")
        self.assertIn("hepsi tuttu", lc.evidence_text(receipt))

    def test_d2_no_interaction_over_a_capture_that_did_not_finish(self):
        self.pid, seen = [0], []
        receipt = self.observe(lambda *a, **k: seen.append(1), state="timeout")
        self.assertEqual(seen, [])
        self.assertEqual(receipt["interaction"]["state"], "blocked")
        self.assertEqual(receipt["cleanup_state"], "confirmed")

    def test_a_failing_interact_callback_never_skips_the_cleanup(self):
        self.pid = [0]

        def interact(*a, **k):
            raise RuntimeError("COM")
        receipt = self.observe(interact)
        self.assertEqual(receipt["interaction"]["state"], "blocked")
        self.assertEqual(receipt["cleanup_state"], "confirmed")


class JobInteractionTests(unittest.TestCase):
    def make(self, look):
        from tests.test_long_job import Clock, nullctx
        from core.long_job import JobLedger, LongJob
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "p").mkdir()
        ledger = JobLedger.create({"goal": "Oyun", "project_path": str(root / "p"), "hours": 2, "review": True,
                                   "milestones": [{"title": "Düğme", "acceptance": "Artır düğmesine tıklayınca sayı artar"}]},
                                  root=root / "jobs", clock=Clock())
        self.seen = []
        job = LongJob(ledger, run_milestone=lambda l, m, w, s: {"status": "completed"},
                      verify=lambda stop: {"ok": True, "summary": "ok"},
                      checkpoint=lambda: {"status": "snapshot", "ref": "cp"},
                      baseline=lambda: {"status": "snapshot", "ref": "b"}, snapshot=lambda: {},
                      changed=lambda a, b: [], commit=lambda f, m: None,
                      notify=lambda *a, **k: None, clock=Clock(), awake=nullctx,
                      accept=lambda l, m, w, c, s: self.seen.append(c) or {"ok": True, "by": "claude"},
                      launch=lambda l, m, s: look)
        return job, ledger

    def test_a_failed_expectation_sends_the_milestone_back_without_review(self):
        look = {"verdict": "window_seen", "entry": "main.py", "scenario": "2 adım",
                "interaction": {"state": "failed", "reason": "'1' görülmedi", "actions": 1, "asserted": 1,
                                "steps": [{"n": 2, "do": "expect", "ok": False, "note": "'1' görülmedi",
                                           "seen": ["0"]}]}}
        job, ledger = self.make(look)
        job.run()
        milestone = ledger.data["milestones"][0]
        self.assertFalse(self.seen)
        self.assertIn("'1' görülmedi", milestone["history"][0]["note"] + milestone.get("last_failure", ""))

    def test_an_invalid_scenario_is_the_writers_to_fix(self):
        job, ledger = self.make({"verdict": "window_seen", "entry": "main.py",
                                 "scenario": "senaryo geçersiz: adım 1: 'Kaydet' sonuçlu bir işlem; SpeS basmaz"})
        job.run()
        self.assertFalse(self.seen)
        self.assertIn("SpeS basmaz", ledger.data["milestones"][0]["history"][0]["note"]
                      + ledger.data["milestones"][0].get("last_failure", ""))

    def test_a_blocked_desktop_is_not_a_defect_and_the_report_says_what_happened(self):
        from core.long_job import finish_report
        look = {"verdict": "window_seen", "entry": "main.py", "window_title": "Sayaç", "scenario": "1 adım",
                "interaction": {"state": "blocked", "reason": "fare SpeS dışında hareket etti; deneme durdu",
                                "actions": 0, "asserted": 0, "steps": [{"n": 1, "do": "key", "ok": False}]}}
        job, ledger = self.make(look)
        job.run()
        self.assertEqual(ledger.data["milestones"][0]["status"], "done")
        self.assertIn("Etkileşim denenemedi: adım 1 — fare", finish_report(ledger))

    def test_the_writer_is_asked_for_a_scenario_only_in_full_permission_window_milestones(self):
        from core.long_job import milestone_prompt
        job, ledger = self.make(None)
        milestone = ledger.data["milestones"][0]
        ledger.data["permission_level"] = "full"
        self.assertIn("spes_deneme.json", milestone_prompt(ledger, milestone, "claude"))
        ledger.data["permission_level"] = "project"
        self.assertNotIn("spes_deneme.json", milestone_prompt(ledger, milestone, "claude"))


if __name__ == "__main__":
    unittest.main()
