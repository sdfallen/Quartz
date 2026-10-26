import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gui
from core.chat_coordination import ChatCoordination, proposed_roles
from core.desktop_task_ui import desktop_intent, desktop_view
from tests.test_chat_coordination import Operator, MODELS


class IntentTests(unittest.TestCase):
    def test_chat_is_the_only_task_entry_and_status_stop_remain(self):
        self.assertNotIn('id="btnDesktopTask"',gui._HTML)
        self.assertNotIn('showDesktopTaskDraft',gui._HTML)
        self.assertNotIn('showCoordinationApproval',gui._HTML)
        self.assertNotIn('coordination_prepare(',gui._HTML)
        self.assertIn('id="desktopTaskLabel">Normal sohbet',gui._HTML)
        self.assertIn('id="btnDesktopTaskStop"',gui._HTML)
    def test_plain_requests_need_no_magic_two_agent_sentence(self):
        for text in ("Masaüstünü kontrol et", "Bilgisayar kontrolünü al", "A penceresine tıkla", "Not Defteri penceresini kullan", "Notepad aç"):
            with self.subTest(text=text):self.assertEqual(desktop_intent(text),"task")
    def test_permission_questions_get_local_help_not_authority(self):
        for text in ("Masaüstü erişiminiz var mı?", "Bilgisayardaki dosyalara erişim versem masaüstü kontrol yetkisi sorununu çözebilir misiniz?",
                     "Bilgisayar kontrolüne neden erişimin yok?", "Masaüstünü kontrol etme", "Kendinize yetkiyi verebilir misiniz, kaynak kodlarını ekleyerek?"):
            with self.subTest(text=text):self.assertEqual(desktop_intent(text),"help")
    def test_ordinary_code_chat_unchanged(self):
        for text in ("Merhaba", "Kod hatasını düzelt", "Bu test nasıl çalışıyor?", "Pencere çizim sınıfını açıklayabilir misin?"):
            with self.subTest(text=text):self.assertIsNone(desktop_intent(text))
    def test_defaults_propose_codex_and_observer_without_grant(self):
        self.assertEqual(proposed_roles("Test düğmesini bir kez etkinleştir",allow_defaults=True),{"operator":"codex","observer":"antigravity"})
        self.assertEqual(proposed_roles("Gemini test penceresine tıkla",allow_defaults=True),{"operator":"antigravity","observer":"codex"})
        with self.assertRaises(ValueError):proposed_roles("Codex bilgisayarı al ve logları izle",allow_defaults=True)
        with self.assertRaises(ValueError):proposed_roles("Bilgisayar kontrolünü alma",allow_defaults=True)


class ViewTests(unittest.TestCase):
    def test_normal_is_not_desktop_permission(self):
        state=desktop_view()
        self.assertEqual(state["code"],"normal");self.assertFalse(state["control_active"]);self.assertIsNone(state["stop_ref"])
    def test_pending_and_expired_never_claim_control(self):
        pending={"id":"p","expires_at":100,"conversation_id":"c"}
        self.assertEqual(desktop_view(pending=pending,now=0)["label"],"Onay bekliyor")
        self.assertEqual(desktop_view(pending=pending,now=101)["label"],"Onay süresi doldu")
        self.assertFalse(desktop_view(pending=pending,now=0)["control_active"])
    def test_active_is_based_on_real_broker_not_completed_model_text(self):
        job={"id":"j","conversation_id":"c","status":"running"}
        op={"session":{"active":True,"id":"s","provider":"codex","targets":[{},{}]}}
        view=desktop_view({"active":True,"job":job,"operator":op})
        self.assertTrue(view["control_active"]);self.assertEqual(view["stop_ref"],"coord:j")
        op["session"]={"active":False,"stop_reason":"foreground changed"}
        view=desktop_view({"active":True,"job":job,"operator":op})
        self.assertEqual(view["code"],"released");self.assertFalse(view["control_active"])
    def test_legacy_session_has_distinct_generation_bound_stop(self):
        view=desktop_view(desktop={"session":{"active":True,"id":"legacy1","provider":"antigravity","targets":[{}]}})
        self.assertEqual(view["stop_ref"],"desktop:legacy1")
    def test_starting_without_broker_is_not_active(self):
        view=desktop_view({"active":True,"job":{"id":"j","status":"starting"}})
        self.assertEqual(view["code"],"preparing");self.assertFalse(view["control_active"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.operator=Operator();self.service=ChatCoordination(self.operator,lambda *a:None)
        self.api=gui.Api()
        self.state={"status":"ok","data":{"active_conversation":{"id":"c"},"active_turn":None,
                  "projects":[{"id":"p","path":str(self.root)}]}}
    def tearDown(self):self.service.stop();self.temp.cleanup()
    def ipc(self,action,*args):return self.state if action=="chat_status" else {"status":"ok"}
    def test_help_and_status_never_construct_native_service(self):
        with patch.object(self.api,"_coordination_service",side_effect=AssertionError("native created")),patch("gui.ipc_send",side_effect=self.ipc):
            response=self.api.coordination_route("Masaüstü erişiminiz var mı?","c","p",MODELS)
            self.assertIn("desktop_help",response["data"])
            self.assertEqual(self.api.desktop_task_status()["data"]["code"],"normal")
    def test_button_prepare_has_pending_card_no_operator_start(self):
        with patch.object(self.api,"_coordination_service",return_value=self.service),patch("gui.ipc_send",side_effect=self.ipc):
            result=self.api.coordination_prepare("Test düğmesini bir kez çalıştır","c","p",MODELS)
        self.assertEqual(result["status"],"ok");self.assertTrue(self.service.pending)
        self.assertEqual(self.operator.calls,[]);self.assertFalse(self.operator.active)
        self.assertEqual(result["data"]["plan"]["roles"]["operator"],"codex")
    def test_natural_request_starts_tool_selection_not_a_grant(self):
        with patch.object(self.api,"natural_start",return_value={"status":"ok","data":{"handled":True,"natural_started":True}}) as start:
            result=self.api.coordination_route("Masaüstünü kontrol et","c","p",MODELS)
        self.assertTrue(result["data"]["natural_started"]);self.assertFalse(self.operator.active)
        start.assert_called_once()
    def test_stale_conversation_and_active_chat_block_preparation(self):
        with patch.object(self.api,"_coordination_service",side_effect=AssertionError("should not construct")),patch("gui.ipc_send",side_effect=self.ipc):
            self.assertEqual(self.api.coordination_prepare("task","old","p",MODELS)["status"],"error")
            self.state["data"]["active_turn"]={"status":"running"}
            self.assertEqual(self.api.coordination_prepare("task","c","p",MODELS)["status"],"error")
    def test_failed_chat_persistence_cancels_prepared_card(self):
        def bad(action,*args):return self.state if action=="chat_status" else {"status":"error"}
        with patch.object(self.api,"_coordination_service",return_value=self.service),patch("gui.ipc_send",side_effect=bad):
            self.assertEqual(self.api.coordination_prepare("task","c","p",MODELS)["status"],"error")
        self.assertIsNone(self.service.pending);self.assertFalse(self.operator.active)
    def test_pending_cancel_is_generation_bound(self):
        plan=self.service.propose("test",{"path":str(self.root)},"c",MODELS,allow_defaults=True)
        with self.assertRaises(PermissionError):self.service.cancel_plan("old")
        self.service.cancel_plan(plan["id"]);self.assertIsNone(self.service.pending)
    def test_expired_card_does_not_start(self):
        plan=self.service.propose("test",{"path":str(self.root)},"c",MODELS,allow_defaults=True)
        self.service.pending["expires_at"]=0
        with self.assertRaises(PermissionError):self.service.approve(plan["id"],1,"not-read.log",60,confirmed=True,agy_ack=True)
        self.assertEqual(self.operator.calls,[])
    def test_new_request_does_not_expand_active_control(self):
        self.operator.active=True
        with self.assertRaises(RuntimeError):self.service.propose("test",{"path":str(self.root)},"c",MODELS,allow_defaults=True)
    def test_old_toolbar_stop_cannot_stop_new_coordination(self):
        self.api._coordination=self.service;self.service.job={"id":"new","status":"completed"}
        with patch.object(self.service,"stop",side_effect=AssertionError("new job stopped")):
            self.assertEqual(self.api.desktop_task_stop("coord:old")["status"],"error")
        self.service.job=None
    def test_legacy_stale_toolbar_stop_is_rejected(self):
        stopped=[]
        desktop=SimpleNamespace(_lock=threading.RLock(),broker=SimpleNamespace(status=lambda:{"id":"new"}),stop=lambda:stopped.append(True))
        self.api._desktop_agents=desktop
        self.assertEqual(self.api.desktop_task_stop("desktop:old")["status"],"error");self.assertFalse(stopped)
