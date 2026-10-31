import base64
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.natural_desktop import NaturalDesktopTask, task_roles
from core.desktop_broker import DesktopBroker
from core.desktop_task_ui import desktop_intent
from core.desktop_mcp import handle
from tests.test_desktop_broker import FakeBackend


class NaturalTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = FakeBackend()
        self.broker = DesktopBroker(self.backend)
        self.desktop = SimpleNamespace(broker=self.broker, windows=self.backend.windows)
        self.events = []
        self.task = NaturalDesktopTask(self.desktop, lambda *a:self.events.append(a), factories={}, evidence_root=self.root)
        self.task.job = {"id":"test", "conversation_id":"chat", "project":{"path":str(self.root)},
                         "scope":"test task", "roles":{"operator":"codex", "observer":"antigravity"},
                         "expires_at":time.time()+600, "status":"running", "events":[], "task_id":"squad-task",
                         "verification":{"status":"NOT VERIFIED"}}
        self.task.evidence = self.root / "evidence"
        self.task.evidence.mkdir()
        self.task.tokens = {"codex":"op", "antigravity":"review"}
        self.task.squad = Mock()
        self.task.squad.receive.return_value = []
        self.task.agent_ids = {"codex":"c-task", "antigravity":"g-task"}

    def tearDown(self):
        self.task.stop()
        self.broker.close()
        self.temp.cleanup()

    def call(self, name, args=None, token="op"):
        return self.task.call(token,{"name":name,"arguments":args or {}})

    def request(self):
        return self.call("desktop_request_access",{"handles":[1],"log_paths":[],"reason":"Test uygulamasındaki sonucu gözlemlemek gerekiyor"})

    def approve(self):
        self.request()
        self.task.approve(self.task.pending["id"],confirmed=True)

    def test_plain_acceptance_and_real_chrome_request_route(self):
        for text in ("Codex, açık test uygulamasındaki sorunu incele ve düzelt. Gemini, test loglarını kontrol et.",
                     "Codex Chrome u açıp youtube a gir Ve Gemini Sende Kafana göre bir şarkı seçimi yap codexe bildir"):
            self.assertEqual(desktop_intent(text),"task")

    def test_roles_are_task_specific_not_fixed_log_only(self):
        roles=task_roles("Gemini test uygulamasını aç ve incele. Codex, sonuçları yorumla.")
        self.assertEqual(roles["operator"],"antigravity")
        self.assertIn("sonuçları yorumla",roles["assignments"]["codex"])

    def test_metadata_and_model_request_never_grant_input(self):
        self.call("task_context")
        self.request()
        self.assertFalse(self.broker.status()["active"])
        self.assertEqual(self.backend.actions,[])
        with self.assertRaises(PermissionError):self.call("desktop_focus")

    def test_no_chat_string_or_truthy_value_is_approval(self):
        self.request()
        for confirmed in (False,None,1,"true"):
            with self.assertRaises(PermissionError):self.task.approve(self.task.pending["id"],confirmed=confirmed)

    def test_changed_process_cannot_inherit_permission(self):
        self.request();self.backend.target["pid"]+=1
        with self.assertRaises(PermissionError):self.task.approve(self.task.pending["id"],confirmed=True)
        self.assertFalse(self.broker.status()["active"])

    def test_collaborator_never_gets_input_or_screenshot(self):
        with self.assertRaises(PermissionError):self.call("desktop_request_access",{"handles":[1],"reason":"please"},"review")
        self.approve()
        for name in ("desktop_focus","desktop_observe","desktop_act"):
            with self.assertRaises(PermissionError):self.call(name,token="review")

    def test_squad_is_real_transport_not_fabricated_dialogue(self):
        self.call("task_message",{"text":"Log bulgusu"},"review")
        self.task.squad.send.assert_called_once_with("g-task","c-task","Log bulgusu",task_id="squad-task")
        self.assertEqual(self.events[-1][1],"antigravity")

    def test_read_log_requires_separate_explicit_scope(self):
        (self.root/"test.log").write_text("VISIBLE_EVIDENCE",encoding="utf-8")
        result=self.call("task_read_log",{"path":"test.log"},"review")
        self.assertEqual(result["status"],"waiting_for_inline_permission")
        self.assertNotIn("VISIBLE_EVIDENCE",json.dumps(result))
        self.task.approve(self.task.pending["id"],confirmed=True)
        self.assertFalse(self.broker.status()["active"])
        self.assertIn("VISIBLE_EVIDENCE",self.call("task_read_log",{"path":"test.log"},"review")["untrusted_log"]["text"])

    def test_log_scope_cannot_escape_project(self):
        with self.assertRaises((PermissionError,FileNotFoundError)):
            self.call("task_read_log",{"path":"../secret.log"},"review")

    def test_new_request_invalidates_old_card(self):
        self.request();old=self.task.pending["id"]
        (self.root/"extra.log").write_text("scope expanded",encoding="utf-8")
        self.call("desktop_request_access",{"handles":[1],"log_paths":["extra.log"],"reason":"Fixture günlüğü de gerekli"})
        with self.assertRaises(PermissionError):self.task.approve(old,confirmed=True)

    def test_repeated_pending_request_keeps_one_permission_card(self):
        first=self.request()
        second=self.request()
        self.assertEqual(first["request_id"],second["request_id"])
        self.assertEqual(len([event for event in self.task.job["events"] if event.get("permission_request")]),1)
        self.assertFalse(self.broker.status()["active"])

    def test_stop_revokes_and_wakes_pending_wait(self):
        self.request();errors=[]
        def wait():
            try:self.call("task_wait")
            except PermissionError:errors.append("revoked")
        thread=threading.Thread(target=wait);thread.start()
        time.sleep(.03);self.task.stop();thread.join(1)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,["revoked"])
        with self.assertRaises(PermissionError):self.call("task_context")

    def test_no_screenshot_blocks_action(self):
        self.approve()
        self.backend.observe=lambda _: {"ui":{"elements":[]},"image_available":False}
        observed=self.call("desktop_focus")
        with self.assertRaises(PermissionError):self.call("desktop_act",{"action":"key","key":"tab","snapshot_id":observed["snapshot_id"]})
        self.assertEqual(self.backend.actions,[])

    def test_verification_needs_fresh_real_observation_after_action(self):
        self.approve()
        self.backend.observe=lambda _: {"ui":{"elements":[{"name":"Durum: Düzeltildi","visible":True}]},"image_base64":base64.b64encode(b"fixture-image").decode()}
        observed=self.call("desktop_focus")
        args={"snapshot_id":observed["snapshot_id"],"expected_text":"Durum: Düzeltildi"}
        self.assertEqual(self.call("desktop_verify",args)["status"],"NOT VERIFIED")
        observed=self.call("desktop_act",{"snapshot_id":observed["snapshot_id"],"action":"key","key":"tab"})
        args["snapshot_id"]=observed["snapshot_id"]
        self.assertEqual(self.call("desktop_verify",args)["status"],"OBSERVED UI CRITERION VERIFIED")
        args["expected_text"]="başardım"
        self.assertEqual(self.call("desktop_verify",args)["status"],"NOT VERIFIED")
        self.task.latest["at"]-=16
        with self.assertRaises(PermissionError):self.call("desktop_verify",args)

    def test_mcp_returns_image_not_only_a_file_path(self):
        self.approve()
        result=handle({"method":"tools/call","params":{"name":"desktop_focus","arguments":{}}},transport=lambda p:self.task.call("op",p))
        self.assertTrue(any(item["type"]=="image" for item in result["content"]))
        self.assertNotIn("token",json.dumps(result))

    def test_failed_post_action_observation_cannot_verify_old_success(self):
        self.approve()
        first=self.call("desktop_focus")
        self.backend.observe=Mock(side_effect=RuntimeError("capture failed after click"))
        with self.assertRaises(RuntimeError):
            self.call("desktop_act",{"snapshot_id":first["snapshot_id"],"action":"key","key":"tab"})
        self.assertIsNone(self.task.latest)
        with self.assertRaises(PermissionError):
            self.call("desktop_verify",{"snapshot_id":first["snapshot_id"],"expected_text":"Durum: Düzeltildi"})

    def test_repeated_in_scope_request_does_not_revoke_or_ask_again(self):
        self.approve()
        session=self.broker.status()["id"]
        self.assertEqual(self.request()["status"],"already_approved")
        self.assertIsNone(self.task.pending)
        self.assertEqual(self.broker.status()["id"],session)

    def test_focus_loss_recovers_with_fresh_observation_and_same_grant(self):
        self.approve();self.call("desktop_focus");self.backend.foreground=False
        session = self.broker.status()["id"]
        result = self.call("desktop_observe")
        self.assertTrue(result["focus_recovered"])
        self.assertTrue(self.backend.foreground)
        self.assertTrue(self.broker.status()["active"])
        self.assertEqual(session, self.broker.status()["id"])
        self.assertEqual(self.backend.actions, [])

    def test_start_runs_both_selected_models_without_granting_input(self):
        from tests.test_chat_coordination import MODELS
        class Runtime:
            TERMINAL={"completed","failed","cancelled"}
            executable="test-runtime.exe"
            def __init__(self):self.state={"id":"run","status":"running"};self.started=[]
            def start(self,prompt,workspace,**opts):
                self.started.append((prompt,workspace,opts));return self.state
            def get(self,rid):return self.state
            def cancel(self,rid):self.state["status"]="cancelled"
        codex, gemini=Runtime(),Runtime()
        squad=Mock();squad.initialized=True;squad.create_task.return_value={"id":"task"};squad.receive.return_value=[]
        task=NaturalDesktopTask(self.desktop,lambda *a:None,factories={"codex":lambda:codex,"antigravity":lambda:gemini},
            squad_factory=lambda p:squad,evidence_root=self.root/"bootstrap")
        try:
            with patch("core.natural_desktop.subprocess.run",return_value=SimpleNamespace(returncode=0)), \
                 patch("core.natural_desktop.ensure_antigravity_tool_grants"),patch("core.natural_desktop.write_operator_hooks"):
                result=task.start("Codex test uygulamasını incele. Gemini logları kontrol et.",{"path":str(self.root)},"chat",MODELS)
            self.assertTrue(result["active"])
            self.assertEqual(len(codex.started),1);self.assertEqual(len(gemini.started),1)
            self.assertFalse(self.broker.status()["active"])
            self.assertNotEqual(codex.started[0][2]["desktop_connection"]["token"],gemini.started[0][2]["desktop_connection"]["token"])
            self.assertEqual(codex.started[0][2]["model"],MODELS["codex"]["model"])
            self.assertFalse(gemini.started[0][2]["write"])
            self.assertEqual(codex.started[0][2]["sandbox"],"read-only")
        finally:task.stop()

    def test_finished_cli_turns_wait_for_consent_then_continue_same_task(self):
        from tests.test_chat_coordination import MODELS
        class Runtime:
            TERMINAL={"completed","failed","cancelled"}
            executable="test-runtime.exe"
            def __init__(self):self.states={};self.started=[]
            def start(self,prompt,workspace,**opts):
                rid="run"+str(len(self.started)+1)
                self.started.append((prompt,workspace,opts))
                self.states[rid]={"id":rid,"status":"running","result":"finished waiting"}
                return self.states[rid]
            def get(self,rid):return self.states[rid]
            def cancel(self,rid):self.states[rid]["status"]="cancelled"
        codex,gemini=Runtime(),Runtime()
        squad=Mock();squad.initialized=True;squad.create_task.return_value={"id":"task"};squad.receive.return_value=[]
        task=NaturalDesktopTask(self.desktop,lambda *a:None,factories={"codex":lambda:codex,"antigravity":lambda:gemini},
            squad_factory=lambda p:squad,evidence_root=self.root/"consent-continuation")
        try:
            with patch("core.natural_desktop.subprocess.run",return_value=SimpleNamespace(returncode=0)), \
                 patch("core.natural_desktop.ensure_antigravity_tool_grants"),patch("core.natural_desktop.write_operator_hooks"):
                task.start("Codex test uygulamasını incele. Gemini logları kontrol et.",{"path":str(self.root)},"chat",MODELS)
                token=task.tokens["codex"]
                task.call(token,{"name":"desktop_request_access","arguments":{"handles":[1],"reason":"Test penceresi için izin"}})
                codex.states["run1"]["status"]="completed"
                gemini.states["run1"]["status"]="completed"
                time.sleep(.45)
                self.assertTrue(task.status()["active"])
                self.assertIsNotNone(task.pending)
                self.assertFalse(self.broker.status()["active"])
                task.approve(task.pending["id"],confirmed=True)
            self.assertEqual(len(codex.started),2)
            self.assertEqual(len(gemini.started),2)
            self.assertEqual(codex.started[1][2]["desktop_connection"]["token"],token)
            self.assertIn("same task",codex.started[1][0].lower())
            self.assertTrue(task.status()["active"])
            self.assertTrue(self.broker.status()["active"])
            self.assertEqual(task.job["verification"]["status"],"NOT VERIFIED")
        finally:task.stop()

    def test_cli_finishes_just_after_approval_continues_same_task(self):
        from tests.test_chat_coordination import MODELS
        class Runtime:
            TERMINAL={"completed","failed","cancelled"}
            executable="test-runtime.exe"
            def __init__(self):self.states={};self.started=[]
            def start(self,prompt,workspace,**opts):
                rid="run"+str(len(self.started)+1)
                self.started.append((prompt,workspace,opts))
                self.states[rid]={"id":rid,"status":"running","result":"finished waiting"}
                return self.states[rid]
            def get(self,rid):return self.states[rid]
            def cancel(self,rid):self.states[rid]["status"]="cancelled"
        codex,gemini=Runtime(),Runtime()
        squad=Mock();squad.initialized=True;squad.create_task.return_value={"id":"task"};squad.receive.return_value=[]
        task=NaturalDesktopTask(self.desktop,lambda *a:None,factories={"codex":lambda:codex,"antigravity":lambda:gemini},
            squad_factory=lambda p:squad,evidence_root=self.root/"consent-continuation")
        try:
            with patch("core.natural_desktop.subprocess.run",return_value=SimpleNamespace(returncode=0)), \
                 patch("core.natural_desktop.ensure_antigravity_tool_grants"),patch("core.natural_desktop.write_operator_hooks"):
                task.start("Codex test uygulamasını incele. Gemini logları kontrol et.",{"path":str(self.root)},"chat",MODELS)
                token=task.tokens["codex"]
                task.call(token,{"name":"desktop_request_access","arguments":{"handles":[1],"reason":"Test penceresi için izin"}})
                task.approve(task.pending["id"],confirmed=True)
                codex.states["run1"]["status"]="completed"
                gemini.states["run1"]["status"]="completed"
                time.sleep(.7)
            self.assertEqual(len(codex.started),2)
            self.assertEqual(len(gemini.started),2)
            self.assertEqual(codex.started[1][2]["desktop_connection"]["token"],token)
            self.assertIn("same task",codex.started[1][0].lower())
            self.assertTrue(task.status()["active"])
            self.assertTrue(self.broker.status()["active"])
            self.assertEqual(task.job["verification"]["status"],"NOT VERIFIED")
        finally:task.stop()


if __name__ == "__main__":unittest.main()
