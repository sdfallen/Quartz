import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.conversation_store import ConversationStore
from core.agent_chat import AgentChatService


class AgentChatServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.tmp.name) / "conv.json"
        self.agent_service = MagicMock()
        self.chat = AgentChatService(self.agent_service, self.store_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_initial_conversation_created(self):
        status = self.chat.status()
        self.assertIsNotNone(status["active_conversation"])
        self.assertEqual(len(status["conversations"]), 1)
        self.assertEqual(status["active_conversation"]["title"], "Yeni Sohbet")

    def test_new_conversation_and_switch(self):
        conv2 = self.chat.new_conversation(title="İkinci Sohbet", agent="codex")
        self.assertEqual(conv2["title"], "İkinci Sohbet")
        status = self.chat.status()
        self.assertEqual(len(status["conversations"]), 2)
        self.assertEqual(status["active_conversation"]["id"], conv2["id"])

    def test_agent_selection_and_persistence(self):
        conv = self.chat.status()["active_conversation"]
        self.chat.set_agent(conv["id"], "codex")
        updated = self.chat.store.get(conv["id"])
        self.assertEqual(updated["agent"], "codex")

    def test_send_message_dispatches_antigravity(self):
        fake_run = {
            "id": "run-agy-1", "status": "completed", "result": "Merhaba! Ben Antigravity.",
            "conversation_id": "agy-sess-123", "progress_log": [], "usage": None,
        }
        self.agent_service.dispatch_antigravity.return_value = {"run": fake_run}
        self.agent_service.antigravity.get.return_value = fake_run
        self.agent_service.antigravity.TERMINAL = {"completed", "failed", "cancelled"}

        res = self.chat.send_message("Merhaba", agent="antigravity")
        self.assertEqual(res["agent"], "antigravity")

        # Let the thread execute
        import time
        time.sleep(0.5)

        conv = self.chat.store.get(res["conversation_id"])
        self.assertEqual(len(conv["messages"]), 2)
        self.assertEqual(conv["messages"][0]["content"], "Merhaba")
        self.assertIn("Merhaba! Ben Antigravity.", conv["messages"][1]["content"])
        self.assertIsNone(conv["sessions"]["antigravity"])
        self.assertTrue(self.agent_service.dispatch_antigravity.call_args.kwargs['conversation_only'])

    def test_send_message_preserves_error_gracefully(self):
        self.agent_service.codex.probe.return_value = {"ready": False, "error": "Quota limit reached"}
        res = self.chat.send_message("Codex testi", agent="codex")
        
        import time
        time.sleep(0.5)

        conv = self.chat.store.get(res["conversation_id"])
        self.assertIn("Kota Hatası", conv["messages"][1]["content"])

    def test_send_message_propagates_write_flags(self):
        fake_run = {
            "id": "run-agy-write", "status": "completed", "result": "Dosya yazıldı.",
            "conversation_id": "sess-w", "progress_log": [], "usage": None,
        }
        self.agent_service.dispatch_antigravity.return_value = {"run": fake_run}
        self.agent_service.antigravity.get.return_value = fake_run
        self.agent_service.antigravity.TERMINAL = {"completed", "failed", "cancelled"}

        self.chat.send_message("Dosyayı güncelle", agent="antigravity", write=True, confirm_write=True)
        import time
        time.sleep(0.5)

        self.agent_service.dispatch_antigravity.assert_called_once()
        _, kwargs = self.agent_service.dispatch_antigravity.call_args
        self.assertTrue(kwargs.get("write"))
        self.assertTrue(kwargs.get("confirm_write"))

    def test_collaboration_group_chat_creates_separate_bubbles_and_exchanges_squad_messages(self):
        self.agent_service.check_squad_connection.return_value = {
            "connected": True, "version": "0.7.6", "db_path": "C:\\SquadPilot\\.squad\\messages.db"
        }
        self.agent_service.squad_create_group_task.return_value = {"id": "squad-task-999"}
        self.agent_service.codex.probe.return_value = {"ready": True}
        self.agent_service.antigravity.probe.return_value = {"ready": True}
        self.agent_service.codex.TERMINAL = {"completed", "failed", "cancelled"}
        self.agent_service.antigravity.TERMINAL = {"completed", "failed", "cancelled"}

        codex_runs = [
            {"id": "run-c1", "status": "completed", "result": "Codex 1. tur yanıtı", "session_id": "c-s1", "errors": []},
            {"id": "run-c2", "status": "completed", "result": "Codex 2. turda Antigravity'ye yanıt verdi", "session_id": "c-s1", "errors": []},
        ]
        agy_runs = [
            {"id": "run-a1", "status": "completed", "result": "Antigravity 1. tur yanıtı", "conversation_id": "a-s1", "errors": []},
            {"id": "run-a2", "status": "completed", "result": "Antigravity 2. turda Codex'e yanıt verdi", "conversation_id": "a-s1", "errors": []},
        ]
        c_idx = 0
        a_idx = 0

        def fake_dispatch_codex(*args, **kwargs):
            nonlocal c_idx
            run = codex_runs[min(c_idx, len(codex_runs) - 1)]
            c_idx += 1
            return {"run": run}

        def fake_get_codex(run_id):
            for r in codex_runs:
                if r["id"] == run_id:
                    return r
            return codex_runs[0]

        def fake_dispatch_agy(*args, **kwargs):
            nonlocal a_idx
            run = agy_runs[min(a_idx, len(agy_runs) - 1)]
            a_idx += 1
            return {"run": run}

        def fake_get_agy(run_id):
            for r in agy_runs:
                if r["id"] == run_id:
                    return r
            return agy_runs[0]

        self.agent_service.dispatch_codex.side_effect = fake_dispatch_codex
        self.agent_service.codex.get.side_effect = fake_get_codex
        self.agent_service.dispatch_antigravity.side_effect = fake_dispatch_agy
        self.agent_service.antigravity.get.side_effect = fake_get_agy
        self.agent_service.squad_receive_messages.side_effect = lambda agent_id, project_id=None: [
            {"from": "peer", "to": agent_id, "content": "Karşı ajan mesajı"}
        ]

        res = self.chat.send_message("İkiniz bu mimariyi tartışın", agent="collaboration")
        import time
        time.sleep(0.8)

        conv = self.chat.store.get(res["conversation_id"])
        # 1 user message + 4 separate agent bubbles (Round 1 Codex, Round 1 Antigravity, Round 2 Codex->Antigravity, Round 2 Antigravity->Codex)
        self.assertEqual(len(conv["messages"]), 5)
        self.assertEqual(conv["messages"][0]["sender"], "user")
        self.assertEqual(conv["messages"][1]["sender"], "codex")
        self.assertEqual(conv["messages"][1]["recipient"], "all")
        self.assertEqual(conv["messages"][2]["sender"], "antigravity")
        self.assertEqual(conv["messages"][2]["recipient"], "all")
        self.assertEqual(conv["messages"][3]["sender"], "codex")
        self.assertEqual(conv["messages"][3]["recipient"], "antigravity")
        self.assertEqual(conv["messages"][4]["sender"], "antigravity")
        self.assertEqual(conv["messages"][4]["recipient"], "codex")
        self.assertGreaterEqual(self.agent_service.squad_send_message.call_count, 4)
        self.assertGreaterEqual(self.agent_service.squad_receive_messages.call_count, 2)

    def test_cancel_active_collaboration(self):
        self.agent_service.check_squad_connection.return_value = {"connected": True}
        self.agent_service.squad_create_group_task.return_value = {"id": "squad-task-cancel"}
        self.agent_service.codex.probe.return_value = {"ready": True}
        self.agent_service.codex.TERMINAL = {"completed", "failed", "cancelled"}
        self.agent_service.antigravity.probe.return_value = {"ready": True}
        self.agent_service.antigravity.TERMINAL = {"completed", "failed", "cancelled"}

        is_cancelled = False
        def fake_get_codex(run_id):
            nonlocal is_cancelled
            if is_cancelled:
                return {"id": run_id, "status": "cancelled", "result": "", "errors": []}
            return {"id": run_id, "status": "running", "result": "Codex çalışıyor...", "errors": []}

        def fake_get_agy(run_id):
            nonlocal is_cancelled
            if is_cancelled:
                return {"id": run_id, "status": "cancelled", "result": "", "errors": []}
            return {"id": run_id, "status": "running", "result": "Antigravity çalışıyor...", "errors": []}

        def fake_cancel(run_id):
            nonlocal is_cancelled
            is_cancelled = True
            return {"id": run_id, "status": "cancelled"}

        self.agent_service.dispatch_codex.return_value = {"run": {"id": "run-collab-codex-1"}}
        self.agent_service.codex.get.side_effect = fake_get_codex
        self.agent_service.dispatch_antigravity.return_value = {"run": {"id": "run-collab-agy-1"}}
        self.agent_service.antigravity.get.side_effect = fake_get_agy
        self.agent_service.cancel.side_effect = fake_cancel

        res = self.chat.send_message("Birlikte çalış", agent="collaboration")
        import time
        # Wait for both real dispatch registrations, not an arbitrary sleep:
        # disk fsync/model-policy work can legitimately take longer on Windows.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            active = self.chat.status().get("active_turn") or {}
            if len(active.get("run_ids", [])) >= 2:
                break
            time.sleep(.01)

        cancel_res = self.chat.cancel_active()
        self.assertTrue(cancel_res["cancelled"])
        self.agent_service.cancel.assert_any_call("run-collab-codex-1")
        self.agent_service.cancel.assert_any_call("run-collab-agy-1")

    def test_cancel_antigravity_turn_does_not_convert_to_failed(self):
        is_cancelled = False
        def fake_get(run_id):
            nonlocal is_cancelled
            if is_cancelled:
                return {"id": run_id, "status": "cancelled", "result": "", "errors": []}
            return {"id": run_id, "status": "running", "result": "kısmi metin", "errors": []}

        def fake_cancel(run_id):
            nonlocal is_cancelled
            is_cancelled = True
            return {"id": run_id, "status": "cancelled"}

        self.agent_service.dispatch_antigravity.return_value = {"run": {"id": "run-cancel-test"}}
        self.agent_service.antigravity.get.side_effect = fake_get
        self.agent_service.cancel.side_effect = fake_cancel
        self.agent_service.antigravity.TERMINAL = {"completed", "failed", "cancelled"}

        res = self.chat.send_message("Uzun görev yap", agent="antigravity")
        import time
        time.sleep(0.1)

        cancel_res = self.chat.cancel_active()
        self.assertTrue(cancel_res["cancelled"])

        # Allow worker thread to finish
        time.sleep(0.5)

        conv = self.chat.store.get(res["conversation_id"])
        bot_msg = conv["messages"][-1]
        self.assertEqual(bot_msg["metadata"]["status"], "cancelled")
        self.assertNotIn("Hata", bot_msg["content"])
        self.assertIn("iptal edildi", bot_msg["content"])

    def test_independent_model_and_effort_selection_per_conversation(self):
        conv1 = self.chat.status()["active_conversation"]
        cid1 = conv1["id"]

        res_agy = self.chat.set_agent_model(cid1, "antigravity", model="gemini-3.8-flash-low", effort="low")
        self.assertEqual(res_agy["selection"]["model"], "gemini-3.8-flash-low")
        self.assertEqual(res_agy["selection"]["effort"], "low")

        res_codex = self.chat.set_agent_model(cid1, "codex", model="gpt-6-astra", effort="high")
        self.assertEqual(res_codex["selection"]["model"], "gpt-6-astra")
        self.assertEqual(res_codex["selection"]["effort"], "high")

        conv2 = self.chat.new_conversation(title="Ayrı Model Sohbeti", agent="collaboration")
        cid2 = conv2["id"]
        self.chat.set_agent_model(cid2, "codex", model="gpt-5.6-sol", effort="medium")

        reloaded1 = self.chat.store.get(cid1)
        reloaded2 = self.chat.store.get(cid2)
        self.assertEqual(reloaded1["models"]["codex"]["model"], "gpt-6-astra")
        self.assertEqual(reloaded1["models"]["codex"]["effort"], "high")
        self.assertEqual(reloaded1["models"]["antigravity"]["model"], "gemini-3.8-flash-low")
        self.assertEqual(reloaded2["models"]["codex"]["model"], "gpt-5.6-sol")
        self.assertEqual(reloaded2["models"]["codex"]["effort"], "medium")

    def test_birlikte_mode_passes_each_agents_selected_model_and_runs_in_parallel(self):
        import time

        conv = self.chat.status()["active_conversation"]
        cid = conv["id"]
        self.chat.set_agent_model(cid, "antigravity", model="gemini-3.8-flash-low", effort="low")
        self.chat.set_agent_model(cid, "codex", model="gpt-6-sol", effort="medium")

        self.agent_service.check_squad_connection.return_value = {"connected": True, "version": "0.7.6"}
        self.agent_service.squad_create_group_task.return_value = {"id": "squad-task-par"}
        self.agent_service.codex.probe.return_value = {"ready": True}
        self.agent_service.antigravity.probe.return_value = {"ready": True}
        self.agent_service.codex.TERMINAL = {"completed", "failed", "cancelled"}
        self.agent_service.antigravity.TERMINAL = {"completed", "failed", "cancelled"}

        codex_models_seen = []
        agy_models_seen = []
        dispatch_intervals = {"codex": [], "antigravity": []}

        def fake_dispatch_codex(*args, **kwargs):
            started = time.monotonic()
            codex_models_seen.append((kwargs.get("model"), kwargs.get("effort")))
            time.sleep(0.25)
            dispatch_intervals["codex"].append((started, time.monotonic()))
            return {"run": {"id": f"c-{len(codex_models_seen)}", "status": "completed", "result": "Codex paralel yanıt", "errors": []}}

        def fake_dispatch_agy(*args, **kwargs):
            started = time.monotonic()
            agy_models_seen.append((kwargs.get("model"), kwargs.get("effort")))
            time.sleep(0.25)
            dispatch_intervals["antigravity"].append((started, time.monotonic()))
            return {"run": {"id": f"a-{len(agy_models_seen)}", "status": "completed", "result": "Antigravity paralel yanıt", "errors": []}}

        self.agent_service.dispatch_codex.side_effect = fake_dispatch_codex
        self.agent_service.codex.get.side_effect = lambda rid: {"id": rid, "status": "completed", "result": "Codex paralel yanıt", "errors": []}
        self.agent_service.dispatch_antigravity.side_effect = fake_dispatch_agy
        self.agent_service.antigravity.get.side_effect = lambda rid: {"id": rid, "status": "completed", "result": "Antigravity paralel yanıt", "errors": []}
        self.agent_service.squad_receive_messages.return_value = [{"from": "peer", "content": "Squad mesajı"}]

        self.chat.send_message("Paralel model değerlendirmesini tartışın", agent="collaboration", conversation_id=cid)
        for _ in range(30):
            st = self.chat.poll_active()
            if not st.get("active"):
                break
            time.sleep(0.05)
        # Assert real overlap, without a wall-clock threshold that flakes when Windows is busy.
        c_start, c_end = dispatch_intervals["codex"][0]
        a_start, a_end = dispatch_intervals["antigravity"][0]
        self.assertLess(c_start, a_end)
        self.assertLess(a_start, c_end)
        self.assertIn(("gpt-6-sol", "medium"), codex_models_seen)
        self.assertIn(("gemini-3.8-flash-low", "low"), agy_models_seen)

        updated_conv = self.chat.store.get(cid)
        self.assertEqual(len(updated_conv["messages"]), 5)
        self.assertEqual(updated_conv["messages"][1]["metadata"]["model"], "gpt-6-sol")
        self.assertEqual(updated_conv["messages"][2]["metadata"]["model"], "gemini-3.8-flash-low")

        # Verify on-demand continue_discussion (+1 Tur)
        cont = self.chat.continue_discussion(cid)
        self.assertEqual(cont["round"], 3)
        for _ in range(30):
            st = self.chat.poll_active()
            if not st.get("active"):
                break
            time.sleep(0.05)
        after_cont = self.chat.store.get(cid)
        self.assertEqual(len(after_cont["messages"]), 7)
        self.assertEqual(after_cont["messages"][5]["metadata"]["round"], 3)
        self.assertEqual(after_cont["messages"][6]["metadata"]["round"], 3)

    def test_gui_has_scroll_controller_and_model_selectors(self):
        import gui
        self.assertIn('id="agyModelSelect"', gui._HTML)
        self.assertIn('id="agyEffortSelect"', gui._HTML)
        self.assertIn('id="codexModelSelect"', gui._HTML)
        self.assertIn('id="codexEffortSelect"', gui._HTML)
        self.assertIn('id="btnJumpBottom"', gui._HTML)
        self.assertIn('userPinnedToBottom', gui._HTML)
        self.assertIn('overflow-anchor: none', gui._HTML)
        self.assertIn('id="btnAddProject"', gui._HTML)
        self.assertIn('id="mainProjectSelect"', gui._HTML)
        self.assertIn('id="mainPermissionLevel"', gui._HTML)


if __name__ == "__main__":
    unittest.main()
