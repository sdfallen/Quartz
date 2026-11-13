"""gui.Api as bridge: service ownership via ApplicationServices and exit receipt."""
import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import gui
from core.application_services import (
    CONFIRMED, FAILED, NOT_STARTED, PENDING, ApplicationServices, ServiceFactories)
from tests.test_application_composition import FakeDesktop, FakeTask, FakeVoice, make

ROOT = Path(__file__).resolve().parents[1]
SHARED_STATE = {"status": "ok", "data": {"active_turn": None,
                "active_conversation": {"id": "c", "messages": []},
                "projects": [{"id": "p", "path": "."}]}}


def ipc(record, shutdown=None):
    def send(action, data=None):
        record.append(action)
        if action == "chat_status":
            return SHARED_STATE
        if action == "shutdown":
            return shutdown if shutdown is not None else {"status": "ok", "data": "stopping"}
        if action == "writer_recovery_status":
            return {"status": "ok", "data": {"blocked": False}}
        return {"status": "ok"}
    return send


class BridgeOwnershipTests(unittest.TestCase):
    def test_default_api_constructs_no_component(self):
        api = gui.Api()
        self.assertIsInstance(api._services, ApplicationServices)
        for attr in ("_natural", "_coordination", "_desktop_agents", "_artifact_diagnostics",
                     "_repair", "_onboarding", "_voice_instance"):
            self.assertIsNone(getattr(api, attr))

    def test_api_holds_no_component_state_of_its_own(self):
        api = gui.Api()
        own = set(vars(api))
        self.assertEqual(own, {"_services", "_compact", "_natural_start_lock", "_shutdown_receipt"})

    def test_bridge_getters_reuse_composition_instances(self):
        services, counts, _ = make()
        api = gui.Api(services)
        desktop = api._desktop_service()
        self.assertIs(api._desktop_service(), desktop)
        self.assertIs(api._desktop_agents, desktop)
        # The bridge's writer-recovery check is the guard installed on the broker.
        self.assertEqual(desktop.broker.admission_guard, api._writer_recovery_input_guard)
        coord = api._coordination_service()
        self.assertIs(api._coordination_service(), coord)
        self.assertIs(api._onboarding_service(), api._onboarding_service())
        self.assertIs(api._voice, api._voice)
        self.assertEqual(counts, {"desktop": 1, "coordination": 1, "onboarding": 1, "voice": 1})

    def test_compat_assignment_goes_into_the_composition(self):
        services, _, _ = make()
        api = gui.Api(services)
        fake = Mock()
        api._desktop_agents = fake
        self.assertIs(services.peek("desktop"), fake)
        self.assertIs(api._desktop_service(), fake)

    def test_natural_start_registers_the_task_in_the_composition(self):
        services, counts, _ = make()
        task = Mock(); task.start.return_value = {"id": "t"}
        services = ApplicationServices(ServiceFactories(
            desktop=lambda: FakeDesktop([]), natural=lambda desktop, emit: task))
        api = gui.Api(services)
        calls = []
        with patch("gui.ipc_send", side_effect=ipc(calls)):
            result = api.natural_start("Başlayın", "c", "p", {}, "full")
        self.assertEqual(result["status"], "ok", result)
        self.assertIs(services.peek("natural"), task)
        self.assertEqual(task.start.call_args.kwargs["requested_permission_level"], "full")

    def test_picker_selected_path_builds_diagnostics_in_composition(self):
        built = []
        services = ApplicationServices(ServiceFactories(
            artifact_diagnostics=lambda path: built.append(path) or Mock(start=lambda: {"state": "running"})))
        api = gui.Api(services)
        window = Mock(); window.create_file_dialog.return_value = ["C:/app.exe"]
        with patch.object(gui.webview, "windows", [window]):
            self.assertEqual(api.diagnostics_select_application()["status"], "ok")
        self.assertEqual(built, ["C:/app.exe"])  # path came only from the native dialog


class CleanupBeforeExitTests(unittest.TestCase):
    def build(self, log, **overrides):
        services, _, _ = make(log, **overrides)
        api = gui.Api(services)
        services.replace_artifact_diagnostics("a.exe")
        services.start_natural(services.desktop(api._writer_recovery_input_guard), None)
        services.coordination(lambda: services.desktop(None), None)
        services.voice()
        return api, services

    def test_failure_in_one_component_still_closes_others_and_backend(self):
        log, calls = [], []
        api, _ = self.build(log, natural=lambda d, e: FakeTask("natural", log, fail=True))
        with patch("gui.ipc_send", side_effect=ipc(calls)):
            self.assertIs(api.cleanup_before_exit(), True)
        self.assertEqual(log, ["artifact_diagnostics:a.exe", "natural", "coordination", "desktop", "voice"])
        self.assertEqual(calls, ["shutdown"])
        receipt = api._shutdown_receipt
        self.assertEqual(receipt["status"], FAILED)
        self.assertEqual(receipt["components"]["natural"], FAILED)
        self.assertEqual(receipt["components"]["desktop"], CONFIRMED)
        self.assertEqual(receipt["components"]["backend"], PENDING)

    def test_backend_ack_without_receipt_is_pending_not_success(self):
        calls = []
        api = gui.Api(make()[0])
        with patch("gui.ipc_send", side_effect=ipc(calls)):
            api.cleanup_before_exit()
        self.assertEqual(api._shutdown_receipt["status"], PENDING)

    def test_backend_receipt_is_respected(self):
        for backend, expected in (({"status": "confirmed"}, CONFIRMED), ({"status": "failed"}, FAILED),
                                  ({"status": "pending"}, PENDING)):
            api = gui.Api(make()[0])
            with patch("gui.ipc_send", side_effect=ipc([], {"status": "ok", "data": backend})):
                api.cleanup_before_exit()
            self.assertEqual(api._shutdown_receipt["components"]["backend"], expected)
            self.assertEqual(api._shutdown_receipt["status"], expected)

    def test_ipc_error_and_exception_are_failures(self):
        api = gui.Api(make()[0])
        with patch("gui.ipc_send", return_value={"status": "error", "data": "SpeS bağlantısı kapalı"}):
            self.assertIs(api.cleanup_before_exit(), True)
        self.assertEqual(api._shutdown_receipt["components"]["backend"], FAILED)
        self.assertNotIn("bağlantısı", repr(api._shutdown_receipt))
        api = gui.Api(make()[0])
        with patch("gui.ipc_send", side_effect=OSError("boom")):
            self.assertIs(api.cleanup_before_exit(), True)
        self.assertEqual(api._shutdown_receipt["errors"][-1]["code"], "ipc_failed")

    def test_repeat_cleanup_does_not_resend_acknowledged_shutdown(self):
        log, calls = [], []
        api, services = self.build(log)
        with patch("gui.ipc_send", side_effect=ipc(calls)):
            api.cleanup_before_exit(); api.cleanup_before_exit()
        self.assertEqual(calls, ["shutdown"])
        self.assertEqual(services.peek("desktop").closed, 1)
        self.assertEqual(log.count("natural"), 1)

    def test_repeat_cleanup_retries_a_failed_backend_request(self):
        api = gui.Api(make()[0])
        with patch("gui.ipc_send", return_value={"status": "error", "data": "x"}):
            api.cleanup_before_exit()
        calls = []
        with patch("gui.ipc_send", side_effect=ipc(calls)):
            api.cleanup_before_exit()
        self.assertEqual(calls, ["shutdown"])
        self.assertEqual(api._shutdown_receipt["components"]["backend"], PENDING)

    def test_composition_crash_still_requests_backend_shutdown(self):
        services = make()[0]
        services.shutdown = Mock(side_effect=RuntimeError("x"))
        api, calls = gui.Api(services), []
        with patch("gui.ipc_send", side_effect=ipc(calls)):
            self.assertIs(api.cleanup_before_exit(), True)
        self.assertEqual(calls, ["shutdown"])
        self.assertEqual(api._shutdown_receipt["status"], FAILED)

    def test_untouched_gui_components_report_not_started(self):
        api = gui.Api(make()[0])
        with patch("gui.ipc_send", side_effect=ipc([], {"status": "ok", "data": {"status": "confirmed"}})):
            api.cleanup_before_exit()
        components = api._shutdown_receipt["components"]
        self.assertEqual({v for k, v in components.items() if k != "backend"}, {NOT_STARTED})
        self.assertEqual(api._shutdown_receipt["status"], CONFIRMED)


class NoNewWorkAfterShutdownTests(unittest.TestCase):
    def setUp(self):
        self.services, self.counts, _ = make()
        self.api = gui.Api(self.services)
        with patch("gui.ipc_send", side_effect=ipc([])):
            self.api.cleanup_before_exit()

    def test_bridge_calls_return_errors_and_construct_nothing(self):
        window = Mock()
        calls = []
        with patch("gui.ipc_send", side_effect=ipc(calls)), patch.object(gui.webview, "windows", [window]):
            results = [self.api.natural_start("Başlayın", "c", "p", {}, "full"),
                       self.api.coordination_prepare("görev", "c", "p", {}),
                       self.api.desktop_operator_windows(),
                       self.api.onboarding_status(),
                       self.api.diagnostics_select_application(),
                       self.api.diagnostics_prepare_repair(),
                       self.api.coordination_pick_app("plan")]
        self.assertTrue(all(r["status"] == "error" for r in results), results)
        window.create_file_dialog.assert_not_called()  # no native picker after exit began
        self.assertNotIn("chat_coordination_message", calls)  # nothing written to chat
        self.assertEqual(self.counts, {})

    def test_status_reads_still_work(self):
        with patch("gui.ipc_send", side_effect=ipc([])):
            self.assertEqual(self.api.natural_status(), {"status": "ok", "data": {"active": False}})
            self.assertEqual(self.api.desktop_task_status()["status"], "ok")

    def test_no_new_housekeeping_thread_after_shutdown(self):
        with patch("threading.Thread") as thread:
            self.api.get_stats()
        thread.assert_not_called()


class BridgeCompatibilityTests(unittest.TestCase):
    def test_quartz_ui_still_hooks_cleanup_on_window_closing(self):
        source = (ROOT / "gui.py").read_text(encoding="utf-8")
        self.assertIn("self._window.events.closing += (\n            self._api.cleanup_before_exit)", source)

    def test_api_no_longer_imports_component_classes(self):
        tree = ast.parse((ROOT / "gui.py").read_text(encoding="utf-8"))
        api = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Api")
        imported = {alias.name for node in ast.walk(api) if isinstance(node, ast.ImportFrom)
                    for alias in node.names}
        imported |= {node.module for node in ast.walk(api) if isinstance(node, ast.ImportFrom)}
        # Pure intent helpers (e.g. chat_coordination.proposed_roles) may stay.
        for module in ("core.natural_desktop", "core.desktop_agents", "core.artifact_diagnostics",
                       "core.package_repair", "core.onboarding", "voice_system", "ChatCoordination"):
            self.assertNotIn(module, imported)
        constructed = {node.func.id for node in ast.walk(api)
                       if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertFalse({"NaturalDesktopTask", "ChatCoordination", "DesktopAgentService",
                          "ArtifactDiagnosticsService", "PackageRepair", "OnboardingService",
                          "VoiceSystem"} & constructed)

    def test_api_can_still_be_created_without_arguments(self):
        self.assertIsInstance(gui.Api(), gui.Api)


if __name__ == "__main__":
    unittest.main()
