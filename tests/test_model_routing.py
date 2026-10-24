"""Model/effort routing regressions. No live model or GUI process."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.agent_chat import AgentChatService
from core.multi_agent_service import MultiAgentService


def selections():
    return {"codex": {"model": "gpt-6-luna", "effort": "low"},
            "antigravity": {"model": "gemini-3.8-flash-low", "effort": "low"}}


class ModelIPCTests(unittest.TestCase):
    def server(self):
        import main
        server = main.IPCServer.__new__(main.IPCServer)
        server._get_agent_center = MagicMock()
        center = server._get_agent_center.return_value
        center.validate_model_selections.side_effect = MultiAgentService.validate_model_selections
        server._get_agent_chat = MagicMock()
        server._get_agent_chat.return_value.get_model_selection.return_value = selections()
        return server, center

    def send(self, server, **data):
        return server._dispatch_action({"action": "agent_center_dispatch", "data": {
            "prompt": "inspect only", "provider": "collaboration", "permission_level": "read-only", **data}})

    def test_explicit_models_bypass_saved_lookup_and_reach_collaboration(self):
        server, center = self.server()
        self.send(server, models=selections())
        server._get_agent_chat.assert_not_called()
        self.assertEqual(center.dispatch.call_args.kwargs["models"], selections())
        self.assertFalse(center.dispatch.call_args.kwargs["write"])

    def test_legacy_request_uses_saved_conversation_not_cli_defaults(self):
        server, center = self.server()
        self.send(server, conversation_id="chosen-chat")
        server._get_agent_chat.return_value.get_model_selection.assert_called_once_with("chosen-chat")
        self.assertEqual(center.dispatch.call_args.kwargs["models"], selections())

    def test_invalid_explicit_models_do_not_fall_back(self):
        server, center = self.server()
        with self.assertRaises(ValueError):
            self.send(server, models={})
        server._get_agent_chat.assert_not_called()
        center.dispatch.assert_not_called()

    def test_single_provider_aliases_get_explicit_model_and_effort(self):
        for provider, key in (("codex", "codex"), ("agy", "antigravity"), ("AGY", "antigravity"), ("antigravity", "antigravity")):
            server, center = self.server()
            self.send(server, provider=provider, models={key: selections()[key]})
            kwargs = center.dispatch.call_args.kwargs
            self.assertEqual(kwargs["model"], selections()[key]["model"])
            self.assertEqual(kwargs["effort"], "low")
            self.assertNotIn("models", kwargs)

    def test_gui_bridge_keeps_models_and_conversation(self):
        import gui
        with patch("gui.ipc_send") as ipc:
            gui.Api.__new__(gui.Api).agent_center_dispatch("inspect", provider="collaboration",
                                                       models=selections(), conversation_id="chat")
        data = ipc.call_args.args[1]
        self.assertEqual(data["models"], selections())
        self.assertEqual(data["conversation_id"], "chat")
        self.assertFalse(data["confirm_write"])
        self.assertIn("models, currentConvId || ''", gui._HTML)
        self.assertIn("İstenen model:", gui._HTML)

    def test_chat_snapshot_is_detached(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = AgentChatService(MagicMock(), Path(directory)/"conversations.json")
            snap = chat.get_model_selection()
            snap["codex"]["model"] = "not-saved"
            self.assertNotEqual(chat.get_model_selection()["codex"]["model"], "not-saved")


class CollaborationModelTests(unittest.TestCase):
    def setUp(self):
        with patch("core.multi_agent_service.CodexRuntime"), patch("core.multi_agent_service.AntigravityRuntime"):
            self.service = MultiAgentService(projects=[{"id": "test", "path": "."}])
        self.service.codex.probe.return_value = {"ready": True}
        self.service.antigravity.probe.return_value = {"ready": True}

    def record(self):
        self.service._collaborations["test"] = {
            "id": "test", "status": "starting", "prompt": "inspect", "title": "test", "project_id": "test",
            "models": selections(), "run_ids": [], "task_ids": [], "messages": [], "error": ""}

    def test_selections_are_required_and_validated_before_launch(self):
        for models in (None, {}, {"codex": {"model": "", "effort": "low"}},
                       {**selections(), "antigravity": {"model": "gemini-test", "effort": "ultra"}},
                       {**selections(), "codex": {"model": "--model-injection", "effort": "low"}}):
            with self.subTest(models=models), self.assertRaises(ValueError):
                self.service.dispatch_collaboration("inspect", models=models)
        self.service.codex.probe.assert_not_called()

    def test_selection_snapshot_does_not_mutate_with_callers_dict(self):
        cfg = selections()
        with patch("core.multi_agent_service.threading.Thread"):
            result = self.service.dispatch_collaboration("inspect", models=cfg)
        cfg["codex"]["model"] = "changed-later"
        self.assertEqual(result["collaboration"]["models"]["codex"]["model"], "gpt-6-luna")

    def run_worker(self, completed):
        squad = MagicMock()
        squad.agents.return_value = [{"id": "quartz-codex"}, {"id": "quartz-antigravity"}]
        with patch.object(self.service, "_squad", return_value=squad), \
             patch.object(self.service, "dispatch_codex", side_effect=[
                 {"run": {"id": "analysis"}, "task": {"id": "task1"}},
                 {"run": {"id": "synthesis"}, "task": {"id": "task3"}}]) as codex, \
             patch.object(self.service, "dispatch_antigravity", return_value={
                 "run": {"id": "review"}, "task": {"id": "task2"}}) as agy, \
             patch.object(self.service, "_wait_for", side_effect=lambda rt, rid: completed[rid]):
            self.service._collaboration_worker("test")
        return codex, agy

    def test_same_codex_selection_for_analysis_and_synthesis(self):
        self.record()
        done = {key: {"status": "completed", "result": key} for key in ("analysis", "review", "synthesis")}
        codex, agy = self.run_worker(done)
        self.assertEqual(codex.call_count, 2)
        for call in codex.call_args_list:
            self.assertEqual(call.kwargs["model"], "gpt-6-luna")
            self.assertEqual(call.kwargs["effort"], "low")
            self.assertFalse(call.kwargs["write"])
        self.assertEqual(agy.call_args.kwargs["model"], "gemini-3.8-flash-low")
        self.assertEqual(agy.call_args.kwargs["effort"], "low")
        self.assertIn("ONLY the first Codex analyst", codex.call_args_list[0].args[0])
        self.assertIn("do not label it independent source verification", codex.call_args_list[1].args[0])
        self.assertEqual(self.service._collaborations["test"]["status"], "completed")

    def test_quota_does_not_retry_switch_model_or_synthesize(self):
        self.record()
        codex, agy = self.run_worker({
            "analysis": {"status": "completed", "result": "analysis"},
            "review": {"status": "failed", "errors": ["permission policy denied", "429 RESOURCE_EXHAUSTED Individual quota reached"], "exit_code": 3}})
        self.assertEqual(codex.call_count, 1)
        self.assertEqual(agy.call_count, 1)
        item = self.service._collaborations["test"]
        self.assertEqual(item["failure_kind"], "quota")
        self.assertEqual(item["failed_provider"], "antigravity")
        self.assertEqual(item["failed_model"], "gemini-3.8-flash-low")
        self.assertIn("429 RESOURCE_EXHAUSTED", item["error"])
        self.assertIn("model=gemini-3.8-flash-low", item["error"])
        self.assertEqual(item["status"], "failed")

    def test_synthesis_failure_is_attributed_to_codex_selection(self):
        self.record()
        self.run_worker({"analysis": {"status": "completed", "result": "a"},
                         "review": {"status": "completed", "result": "r"},
                         "synthesis": {"status": "failed", "errors": ["provider rejected request"]}})
        item = self.service._collaborations["test"]
        self.assertEqual(item["failed_provider"], "codex")
        self.assertEqual(item["failed_phase"], "synthesis")
        self.assertIn("model=gpt-6-luna", item["error"])
