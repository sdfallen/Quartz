"""ApplicationServices: lazy single ownership, shutdown fence, independent cleanup."""
import ast
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.application_services import (
    CLOSE_ORDER, CONFIRMED, FAILED, NOT_STARTED, PENDING,
    ApplicationServices, ServiceFactories, ServicesClosed)

ROOT = Path(__file__).resolve().parents[1]


class FakeBroker:
    def __init__(self):
        self.admission_guard = None
        self.active = False


class FakeDesktop:
    def __init__(self, log, fail=False):
        self.broker = FakeBroker(); self.log = log; self.fail = fail; self.closed = 0

    def close(self):
        self.closed += 1; self.log.append("desktop")
        if self.fail:
            raise OSError("C:\\Users\\secret\\path must not leak")

    def status(self):
        return {"session": {"active": self.broker.active}}


class FakeTask:
    """Shape of NaturalDesktopTask / ChatCoordination status()+stop()."""
    def __init__(self, name, log, *, fail=False, stays_active=False, cleanup="completed"):
        self.name = name; self.log = log; self.fail = fail; self.stays_active = stays_active
        self.cleanup = cleanup; self.stopped = 0; self.args = None

    def stop(self, *args, **kwargs):
        self.stopped += 1; self.log.append(self.name)
        if self.fail:
            raise RuntimeError("boom")
        return self.status()

    def status(self):
        return {"active": self.stays_active, "job": {"cleanup": {"status": self.cleanup}}}


class FakeDiagnostics:
    def __init__(self, path, log):
        self.path = path; self.log = log; self.threads = {}; self.shut = 0

    def shutdown(self):
        self.shut += 1; self.log.append("artifact_diagnostics:" + self.path)


class FakeVoice:
    def __init__(self, log):
        self.log = log; self.wake_active = True

    def stop_wake_loop(self):
        self.wake_active = False; self.log.append("voice")

    def stop_speaking(self):
        pass


class FakeOnboarding:
    def __init__(self, running=False):
        self.lock = threading.RLock()
        self.job = {"state": "running" if running else "idle"}
        self.login_processes = {}


def make(log=None, **overrides):
    log = [] if log is None else log
    counts = {}

    def counted(name, build):
        def factory(*args):
            counts[name] = counts.get(name, 0) + 1
            return build(*args)
        return factory

    defaults = dict(
        onboarding=counted("onboarding", lambda: FakeOnboarding()),
        desktop=counted("desktop", lambda: FakeDesktop(log)),
        coordination=counted("coordination", lambda desktop, emit: FakeTask("coordination", log)),
        natural=counted("natural", lambda desktop, emit: FakeTask("natural", log)),
        artifact_diagnostics=counted("artifact_diagnostics", lambda path: FakeDiagnostics(path, log)),
        repair=counted("repair", lambda: SimpleNamespace(prepare=lambda p: {"plan": p})),
        voice=counted("voice", lambda: FakeVoice(log)),
    )
    defaults.update(overrides)
    return ApplicationServices(ServiceFactories(**defaults)), counts, log


def guard():
    return None


class LazyConstructionTests(unittest.TestCase):
    def test_nothing_is_constructed_until_requested(self):
        services, counts, _ = make()
        self.assertEqual(counts, {})
        self.assertTrue(all(services.peek(name) is None for name in CLOSE_ORDER))

    def test_shared_components_are_reused(self):
        services, counts, _ = make()
        desktop = services.desktop(guard)
        self.assertIs(services.desktop(guard), desktop)
        coord = services.coordination(lambda: services.desktop(guard), None)
        self.assertIs(services.coordination(lambda: services.desktop(guard), None), coord)
        self.assertIs(services.onboarding(), services.onboarding())
        self.assertIs(services.voice(), services.voice())
        self.assertEqual(counts, {"desktop": 1, "coordination": 1, "onboarding": 1, "voice": 1})

    def test_desktop_never_escapes_without_writer_recovery_guard(self):
        services, _, _ = make()
        self.assertIs(services.desktop(guard).broker.admission_guard, guard)

    def test_per_request_components_replace_the_previous_one(self):
        services, counts, log = make()
        first = services.replace_artifact_diagnostics("a.exe")
        second = services.replace_artifact_diagnostics("b.exe")
        self.assertIsNot(first, second)
        self.assertEqual(first.shut, 1)  # previous inspection is shut down first
        self.assertIs(services.peek("artifact_diagnostics"), second)
        t1 = services.start_natural("desk", None); t2 = services.start_natural("desk", None)
        self.assertIs(services.peek("natural"), t2); self.assertIsNot(t1, t2)
        self.assertEqual(counts["natural"], 2)

    def test_concurrent_first_use_builds_one_instance(self):
        services, counts, _ = make()
        barrier = threading.Barrier(8)
        results = []

        def worker():
            barrier.wait(); results.append(services.desktop(guard))
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(counts["desktop"], 1)
        self.assertEqual(len({id(r) for r in results}), 1)


class ShutdownFenceTests(unittest.TestCase):
    def test_no_new_instance_during_or_after_shutdown(self):
        services, counts, _ = make()
        services.shutdown()
        for call in (lambda: services.desktop(guard), services.onboarding, services.voice,
                     lambda: services.coordination(lambda: None, None),
                     lambda: services.start_natural(None, None),
                     lambda: services.replace_artifact_diagnostics("x.exe"),
                     services.new_repair, lambda: services.adopt("natural", object())):
            with self.assertRaises(ServicesClosed):
                call()
        self.assertEqual(counts, {})

    def test_factory_racing_with_shutdown_is_closed_not_leaked(self):
        started, release = threading.Event(), threading.Event()
        log = []

        def slow_desktop():
            started.set(); release.wait(5); return FakeDesktop(log)
        services, _, _ = make(log, desktop=slow_desktop)
        builder = threading.Thread(target=lambda: services.desktop(guard)); builder.start()
        started.wait(5)
        receipts = []
        closer = threading.Thread(target=lambda: receipts.append(services.shutdown())); closer.start()
        release.set(); builder.join(5); closer.join(5)
        # The construction that won the lock is closed by the shutdown that followed.
        self.assertEqual(receipts[0]["components"]["desktop"], CONFIRMED)
        self.assertEqual(services.peek("desktop").closed, 1)

    def test_reads_stay_available_after_shutdown(self):
        services, _, _ = make()
        task = services.start_natural(None, None)
        services.shutdown()
        self.assertIs(services.peek("natural"), task)


class IndependentCleanupTests(unittest.TestCase):
    def test_one_failure_does_not_skip_the_others(self):
        log = []
        services, _, _ = make(log, natural=lambda d, e: FakeTask("natural", log, fail=True))
        services.replace_artifact_diagnostics("a.exe")
        services.start_natural(services.desktop(guard), None)
        services.coordination(lambda: services.desktop(guard), None)
        services.voice()
        receipt = services.shutdown()
        self.assertEqual(log, ["artifact_diagnostics:a.exe", "natural", "coordination", "desktop", "voice"])
        self.assertEqual(receipt["status"], FAILED)
        self.assertEqual(receipt["components"]["natural"], FAILED)
        for name in ("artifact_diagnostics", "coordination", "desktop", "voice"):
            self.assertEqual(receipt["components"][name], CONFIRMED)
        self.assertEqual(receipt["errors"], [{"component": "natural", "code": "close_failed", "type": "RuntimeError"}])

    def test_errors_carry_no_exception_text(self):
        log = []
        services, _, _ = make(log, desktop=lambda: FakeDesktop(log, fail=True))
        services.desktop(guard)
        receipt = services.shutdown()
        self.assertNotIn("secret", repr(receipt))
        self.assertEqual(receipt["errors"][0]["type"], "OSError")

    def test_unverified_stop_is_pending_not_confirmed(self):
        log = []
        services, _, _ = make(log, coordination=lambda d, e: FakeTask("coordination", log, stays_active=True),
                              onboarding=lambda: FakeOnboarding(running=True))
        services.coordination(lambda: services.desktop(guard), None); services.onboarding()
        receipt = services.shutdown()
        self.assertEqual(receipt["components"]["coordination"], PENDING)
        self.assertEqual(receipt["components"]["onboarding"], PENDING)
        self.assertEqual(receipt["status"], PENDING)

    def test_natural_cleanup_failure_reported_from_its_own_report(self):
        log = []
        services, _, _ = make(log, natural=lambda d, e: FakeTask("natural", log, cleanup="failed"))
        services.start_natural(None, None)
        self.assertEqual(services.shutdown()["components"]["natural"], FAILED)

    def test_untouched_components_are_not_started_and_overall_confirmed(self):
        services, _, _ = make()
        receipt = services.shutdown()
        self.assertEqual(set(receipt["components"].values()), {NOT_STARTED})
        self.assertEqual(receipt["status"], CONFIRMED)

    def test_repeat_shutdown_is_idempotent_and_retries_only_failures(self):
        log = []
        flaky = FakeTask("natural", log, fail=True)
        services, counts, _ = make(log, natural=lambda d, e: flaky)
        services.start_natural(services.desktop(guard), None)
        first = services.shutdown()
        self.assertEqual(first["components"]["natural"], FAILED)
        flaky.fail = False
        second = services.shutdown()
        self.assertEqual(second["components"]["natural"], CONFIRMED)
        self.assertEqual(second["status"], CONFIRMED)
        self.assertEqual(services.peek("desktop").closed, 1)  # confirmed one not closed again
        third = services.shutdown()
        self.assertEqual(third, {**second, "errors": []})
        self.assertEqual(flaky.stopped, 2)
        self.assertEqual(counts["desktop"], 1)

    def test_repair_plan_under_apply_is_pending_not_dropped(self):
        services, _, _ = make()
        plan = services.new_repair()
        holder_ready, release = threading.Event(), threading.Event()

        def apply():
            with services.diagnostics_lock:
                holder_ready.set(); release.wait(5)
        t = threading.Thread(target=apply); t.start(); holder_ready.wait(5)
        try:
            # shrink the wait: the lock is held by another thread
            receipt = services.shutdown()
        finally:
            release.set(); t.join(5)
        self.assertEqual(receipt["components"]["repair"], PENDING)
        self.assertIs(services.peek("repair"), plan)
        self.assertEqual(services.shutdown()["components"]["repair"], CONFIRMED)
        self.assertIsNone(services.peek("repair"))


class LayeringTests(unittest.TestCase):
    def test_composition_does_not_import_gui_webview_or_ipc_at_module_level(self):
        tree = ast.parse((ROOT / "core" / "application_services.py").read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module)
        self.assertFalse({"gui", "webview", "core.local_ipc", "socket"} & names)

    def test_default_factories_import_lazily(self):
        tree = ast.parse((ROOT / "core" / "application_services.py").read_text(encoding="utf-8"))
        top = {n.module for n in tree.body if isinstance(n, ast.ImportFrom)}
        self.assertFalse({m for m in top if m and m.startswith("core.")})


if __name__ == "__main__":
    unittest.main()
