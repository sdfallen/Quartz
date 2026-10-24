import unittest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.multi_agent_service import MultiAgentService


class MultiAgentServiceTests(unittest.TestCase):
    def make_service(self):
        with patch("core.multi_agent_service.CodexRuntime") as runtime_cls, \
             patch("core.multi_agent_service.AntigravityRuntime") as agy_cls:
            runtime = runtime_cls.return_value
            runtime.TERMINAL = {"completed", "failed", "cancelled"}
            runtime.probe.return_value = {"ready": True, "authenticated": True, "error": ""}
            runtime.start.return_value = {"id": "run-1", "status": "running"}
            agy = agy_cls.return_value
            agy.TERMINAL = {"completed", "failed", "cancelled"}
            agy.probe.return_value = {"ready": True, "authenticated": True, "error": ""}
            agy.start.return_value = {"id": "agy-run-1", "status": "running"}
            service = MultiAgentService(
                projects=[{"id": "test", "name": "Test", "path": ".", "protected": False}],
                squad_executable=__file__, codex_executable=__file__,
                antigravity_executable=__file__,
            )
        return service, runtime, agy

    def test_write_dispatch_requires_explicit_confirmation(self):
        service, _, _ = self.make_service()
        with self.assertRaises(PermissionError):
            service.dispatch_codex("change files", write=True, confirm_write=False)

    def test_antigravity_chat_project_write_does_not_enable_full_access(self):
        service, _, agy = self.make_service()
        with patch.object(service, "check_squad_connection", return_value={"connected": True}):
            with self.assertRaises(PermissionError):
                service.dispatch_antigravity("change files", write=True, confirm_write=True, chat_mode=True)
        agy.start.assert_not_called()

    def test_antigravity_readiness_reports_project_write_limit(self):
        service, _, _ = self.make_service()
        status = service._antigravity_status(time.monotonic())
        self.assertTrue(status["ready"])
        self.assertTrue(status["write_safety_blocked"])

    def test_writer_lock_is_shared_between_both_runtimes(self):
        service, codex, agy = self.make_service()
        project = service.projects.selected()
        codex.get.return_value = {"status": "running"}
        agy.get.return_value = {"status": "running"}
        with patch("core.multi_agent_service.create_checkpoint", return_value={"status": "snapshot", "complete": True, "archive": "mock.zip"}), \
             patch("core.multi_agent_service.snapshot_workspace_files", return_value={"files": {}, "warning": ""}):
            service._start_writer("codex", project, lambda: {"id": "codex-write"})
            self.assertTrue(service._writer_status(project["path"])["locked"])
            with self.assertRaises(RuntimeError):
                service._start_writer("antigravity", project, lambda: {"id": "agy-write"})
            codex.get.return_value = {"status": "completed"}
            for _ in range(30):
                if not service._writer_status(project["path"])["locked"]:
                    break
                time.sleep(.02)
            self.assertFalse(service._writer_status(project["path"])["locked"])

    def test_write_run_reports_observed_file_changes_even_without_cli_file_event(self):
        service, codex, _ = self.make_service()
        project = service.projects.selected()
        codex.get.return_value = {"id": "codex-write", "status": "completed", "files_changed": []}
        snapshots = [
            {"files": {}, "warning": ""},
            {"files": {"created.txt": (4, 123)}, "warning": ""},
        ]
        with patch("core.multi_agent_service.create_checkpoint", return_value={"status": "snapshot", "complete": True, "archive": "mock.zip"}), \
             patch("core.multi_agent_service.snapshot_workspace_files", side_effect=snapshots):
            service._start_writer("codex", project, lambda: {"id": "codex-write"})
            for _ in range(100):
                if service.get_run("codex-write").get("files_changed"):
                    break
                time.sleep(.01)
        self.assertEqual(service.get_run("codex-write")["files_changed"],
                         [str(Path(project["path"]) / "created.txt")])

    def test_dispatch_links_squad_task_and_real_runtime(self):
        service, runtime, _ = self.make_service()
        squad = MagicMock()
        squad.agents.return_value = [{"id": "quartz-codex"}]
        squad.create_task.return_value = {"id": "task-1"}
        with patch.object(service, "_squad", return_value=squad), \
             patch("core.multi_agent_service.threading.Thread"):
            result = service.dispatch_codex("inspect code")
        squad.ack_task.assert_called_once_with("quartz-codex", "task-1")
        runtime.start.assert_called_once()
        self.assertEqual(result["task"]["id"], "task-1")
        self.assertEqual(runtime.start.call_args.kwargs["sandbox"], "read-only")

    def test_status_enriches_runtime_with_squad_reporting_state(self):
        service, runtime, _ = self.make_service()
        runtime.list.return_value = [{"id": "run-1", "project": ".", "sandbox": "read-only", "status": "running"}]
        service._links["run-1"] = {
            "coordination_status": "reporting", "coordination_error": "",
        }
        run = service._enriched_runs()[0]
        self.assertEqual(run["coordination_status"], "reporting")

    def test_coordination_error_is_visible_in_runtime_snapshot(self):
        service, runtime, _ = self.make_service()
        runtime.list.return_value = [{"id": "run-1", "project": ".", "sandbox": "read-only", "status": "completed"}]
        service._links["run-1"] = {
            "coordination_status": "error", "coordination_error": "Squad unavailable",
        }
        run = service._enriched_runs()[0]
        self.assertEqual(run["coordination_error"], "Squad unavailable")

    def test_antigravity_dispatch_uses_documented_squad_bridge(self):
        service, _, agy = self.make_service()
        squad = MagicMock()
        squad.agents.return_value = [{"id": "quartz-antigravity"}]
        squad.create_task.return_value = {"id": "task-agy"}
        with patch.object(service, "_squad", return_value=squad), \
             patch("core.multi_agent_service.threading.Thread"):
            result = service.dispatch_antigravity("review code")
        squad.ack_task.assert_called_once_with("quartz-antigravity", "task-agy")
        agy.start.assert_called_once()
        self.assertEqual(result["bridge"], "squad-cli")
        self.assertFalse(agy.start.call_args.kwargs["write"])

    def test_collaboration_rejects_write_mode(self):
        service, _, _ = self.make_service()
        with self.assertRaises(PermissionError):
            service.dispatch_collaboration("change code", write=True, confirm_write=True)

    def test_collaboration_bridge_sends_messages_in_both_directions(self):
        service, runtime, agy = self.make_service()
        service._collaborations["pair-1"] = {
            "models": {"codex": {"model": "gpt-6-luna", "effort": "low"}, "antigravity": {"model": "gemini-3.8-flash-low", "effort": "low"}},
            "id": "pair-1", "status": "starting", "prompt": "inspect",
            "title": "inspect", "project_id": "test", "run_ids": [],
            "task_ids": [], "messages": [], "result": "", "error": "",
            "started_at": 1, "finished_at": None,
        }
        squad = MagicMock()
        squad.agents.return_value = [
            {"id": "quartz-codex"}, {"id": "quartz-antigravity"},
        ]
        codex_dispatches = [
            {"run": {"id": "codex-1"}, "task": {"id": "task-1"}},
            {"run": {"id": "codex-2"}, "task": {"id": "task-3"}},
        ]
        agy_dispatch = {"run": {"id": "agy-1"}, "task": {"id": "task-2"}}
        completed = {
            "codex-1": {"status": "completed", "result": "analysis"},
            "agy-1": {"status": "completed", "result": "review"},
            "codex-2": {"status": "completed", "result": "final"},
        }
        with patch.object(service, "_squad", return_value=squad), \
             patch.object(service, "dispatch_codex", side_effect=codex_dispatches), \
             patch.object(service, "dispatch_antigravity", return_value=agy_dispatch) as agy_call, \
             patch.object(service, "_wait_for", side_effect=lambda _runtime, run_id: completed[run_id]):
            service._collaboration_worker("pair-1")
        self.assertIn("Independently inspect the relevant files", agy_call.call_args.args[0])
        directions = [(call.args[0], call.args[1]) for call in squad.send.call_args_list]
        self.assertEqual(directions, [
            ("quartz-codex", "quartz-antigravity"),
            ("quartz-antigravity", "quartz-codex"),
            ("quartz-codex", "quartz-antigravity"),
        ])
        self.assertEqual(service._collaborations["pair-1"]["status"], "completed")
        self.assertEqual(service._collaborations["pair-1"]["result"], "final")

    def test_collaboration_retries_antigravity_without_tools_after_permission_denial(self):
        service, runtime, agy = self.make_service()
        service._collaborations["pair-retry"] = {
            "models": {"codex": {"model": "gpt-6-luna", "effort": "low"}, "antigravity": {"model": "gemini-3.8-flash-low", "effort": "low"}},
            "id": "pair-retry", "status": "starting", "prompt": "review text",
            "title": "review text", "project_id": "test", "run_ids": [],
            "task_ids": [], "messages": [], "result": "", "error": "",
            "started_at": 1, "finished_at": None,
        }
        squad = MagicMock()
        squad.agents.return_value = [
            {"id": "quartz-codex"}, {"id": "quartz-antigravity"},
        ]
        codex_dispatches = [
            {"run": {"id": "codex-1"}, "task": {"id": "task-1"}},
            {"run": {"id": "codex-2"}, "task": {"id": "task-4"}},
        ]
        agy_dispatches = [
            {"run": {"id": "agy-denied"}, "task": {"id": "task-2"}},
            {"run": {"id": "agy-retry"}, "task": {"id": "task-3"}},
        ]
        completed = {
            "codex-1": {"status": "completed", "result": "analysis", "errors": []},
            "agy-denied": {
                "status": "failed", "result": "",
                "errors": ["Antigravity permission policy denied: command"],
            },
            "agy-retry": {"status": "completed", "result": "review", "errors": []},
            "codex-2": {"status": "completed", "result": "final", "errors": []},
        }
        with patch.object(service, "_squad", return_value=squad), \
             patch.object(service, "dispatch_codex", side_effect=codex_dispatches), \
             patch.object(service, "dispatch_antigravity", side_effect=agy_dispatches) as dispatch_agy, \
             patch.object(service, "_wait_for", side_effect=lambda _runtime, run_id: completed[run_id]):
            service._collaboration_worker("pair-retry")

        self.assertEqual(dispatch_agy.call_count, 2)
        self.assertEqual(dispatch_agy.call_args_list[0].kwargs["model"], "gemini-3.8-flash-low")
        self.assertEqual(dispatch_agy.call_args_list[1].kwargs["model"], "gemini-3.8-flash-low")
        self.assertEqual(dispatch_agy.call_args_list[1].kwargs["effort"], "low")
        retry_prompt = dispatch_agy.call_args_list[1].args[0]
        self.assertIn("MUST NOT invoke any tool or command", retry_prompt)
        self.assertEqual(service._collaborations["pair-retry"]["status"], "completed")
        self.assertEqual(service._collaborations["pair-retry"]["run_ids"], [
            "codex-1", "agy-denied", "agy-retry", "codex-2",
        ])

    def test_collaboration_stops_immediately_when_cancelled_after_antigravity_phase(self):
        service, runtime, agy = self.make_service()
        collab_id = "pair-cancel-after-agy"
        service._collaborations[collab_id] = {
            "models": {"codex": {"model": "gpt-6-luna", "effort": "low"}, "antigravity": {"model": "gemini-3.8-flash-low", "effort": "low"}},
            "id": collab_id, "status": "starting", "prompt": "inspect",
            "title": "inspect", "project_id": "test", "run_ids": [],
            "task_ids": [], "messages": [], "result": "", "error": "",
            "started_at": 1, "finished_at": None,
        }
        squad = MagicMock()
        squad.agents.return_value = [
            {"id": "quartz-codex"}, {"id": "quartz-antigravity"},
        ]
        codex_dispatch = {"run": {"id": "codex-1"}, "task": {"id": "task-1"}}
        agy_dispatch = {"run": {"id": "agy-1"}, "task": {"id": "task-2"}}

        def fake_wait(rt, run_id):
            if run_id == "codex-1":
                return {"status": "completed", "result": "first analysis"}
            if run_id == "agy-1":
                # Simulate user cancellation requested right after Antigravity finishes
                service.cancel_collaboration(collab_id)
                return {"status": "completed", "result": "agy review"}
            return {"status": "completed", "result": "should not reach here"}

        dispatch_codex_mock = MagicMock(return_value=codex_dispatch)

        with patch.object(service, "_squad", return_value=squad), \
             patch.object(service, "dispatch_codex", dispatch_codex_mock), \
             patch.object(service, "dispatch_antigravity", return_value=agy_dispatch), \
             patch.object(service, "_wait_for", side_effect=fake_wait):
            service._collaboration_worker(collab_id)

        # dispatch_codex should only have been called ONCE (the first analysis), NOT twice (no synthesis)
        self.assertEqual(dispatch_codex_mock.call_count, 1)
        self.assertEqual(service._collaborations[collab_id]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
