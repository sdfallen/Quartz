import copy
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.chat_coordination import ApprovedLog, ChatCoordination, proposed_roles
from tests.test_desktop_broker import FakeBackend

MODELS = {"codex":{"model":"gpt-6-luna","effort":"low"},
          "antigravity":{"model":"gemini-3.8-flash-low","effort":"low"}}
TASK = "Codex, bilgisayar kontrolünü al. Gemini, logları izle ve hataları analiz et."


class Operator:
    def __init__(self):
        self.broker = SimpleNamespace(backend=FakeBackend(),context_provider=None)
        self.run = None; self.calls = []; self.active = False
    def windows(self): return self.broker.backend.windows()
    def status(self):
        value = {"session":{"active":self.active,"stop_reason":"test"}}
        if self.run: value["run"] = dict(self.run)
        return value
    def start(self,*args,**kwargs):
        self.calls.append((args,kwargs)); self.active = True
        self.run = {"status":"running","result":""}
    def stop(self): self.active = False


class Reader:
    TERMINAL = {"completed","failed","cancelled"}
    def __init__(self): self.runs = {}; self.calls = []; self.cancelled = []
    def start(self,prompt,cwd,**options):
        self.calls.append((prompt,cwd,options))
        run = {"id":str(len(self.calls)),"status":"completed","result":"Observed real fixture log: ready.","commands":[],"files_changed":[]}
        self.runs[run["id"]] = run
        return dict(run)
    def get(self,run): return dict(self.runs[run])
    def cancel(self,run): self.cancelled.append(run)


class RoleTests(unittest.TestCase):
    def test_regular_chat_does_not_require_native_desktop_backend(self):
        import gui
        api=gui.Api()
        with patch.object(api,"_coordination_service",side_effect=RuntimeError("desktop unavailable")):
            result=api.coordination_route("Merhaba, projeyi konuşalım.","conversation","project",{})
        self.assertEqual(result,{"status":"ok","data":{"handled":False,"intent":"conversation"}})
    def test_authenticated_chat_messages_preserve_separate_senders(self):
        from core.agent_chat import AgentChatService
        from core.local_ipc import request_token
        from main import IPCServer
        with tempfile.TemporaryDirectory() as directory:
            chat=AgentChatService(MagicMock(),Path(directory)/"conversation.json")
            cid=chat.store.get_active()["id"]
            server=IPCServer(MagicMock()); server._agent_chat=chat
            for sender in ("user","quartz","codex","antigravity"):
                response=server._dispatch({"action":"chat_coordination_message","auth":request_token(),
                    "data":{"conversation_id":cid,"sender":sender,"content":"actual "+sender,"metadata":{"coordination_id":"test"}}})
                self.assertEqual(response["status"],"ok")
            messages=chat.store.get(cid)["messages"]
            self.assertEqual([m["sender"] for m in messages],["user","quartz","codex","antigravity"])
            self.assertTrue(all(m["metadata"]["coordination_id"]=="test" for m in messages))
            denied=server._dispatch({"action":"chat_coordination_message","data":{"conversation_id":cid,"sender":"codex","content":"not authorized"}})
            self.assertEqual(denied["status"],"error"); self.assertEqual(len(chat.store.get(cid)["messages"]),4)
    def test_old_gui_card_cannot_stop_a_new_job(self):
        import gui
        import threading
        api=gui.Api(); service=SimpleNamespace(lock=threading.RLock(),job={"id":"new"},stop=lambda: self.fail("stale card stopped current job"))
        with patch.object(api,"_coordination_service",return_value=service):
            self.assertEqual(api.coordination_stop("old")["status"],"error")
    def test_both_directions(self):
        self.assertEqual(proposed_roles(TASK),{"operator":"codex","observer":"antigravity"})
        self.assertEqual(proposed_roles("Gemini masaüstünü yönet. Codex log dosyasını incele."),
                         {"operator":"antigravity","observer":"codex"})
        self.assertEqual(proposed_roles("Codex, Universal Modder üzerinden Warband testini yürüt. Gemini logları takip et."),
                         {"operator":"codex","observer":"antigravity"})
    def test_questions_and_regular_chat_are_not_grants(self):
        for text in ("Merhaba", "Codex bilgisayar kontrolü nasıl çalışır?", "Gemini logları açıklayabilir mi?"):
            self.assertIsNone(proposed_roles(text))
    def test_ambiguous_and_same_owner_fail(self):
        for text in ("Codex bilgisayarı al. Gemini bilgisayarı yönet ve logları izle.",
                     "Codex bilgisayarı al ve logları izle.","Codex bilgisayar kontrolünü alma. Gemini logları izle."):
            with self.assertRaises(ValueError): proposed_roles(text)


class LogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quartz-log-test-")
        self.root = Path(self.temp.name); self.log = self.root/"test.log"
        self.log.write_text("ready\npassword=do-not-send\n",encoding="utf-8")
    def tearDown(self): self.temp.cleanup()
    def test_bounded_incremental_redacted_actual_bytes(self):
        reader = ApprovedLog(self.log,self.root); first=reader.read()
        self.assertNotIn("do-not-send",first["text"]); self.assertIn("[REDACTED]",first["text"])
        with self.log.open("a",encoding="utf-8") as stream: stream.write("actual event\n")
        second=reader.read(); self.assertEqual(second["text"].replace("\r\n","\n"),"actual event\n")
        self.assertEqual(second["byte_start"],first["byte_end"])
    def test_replace_or_shrink_requires_new_consent(self):
        reader = ApprovedLog(self.log,self.root); reader.read()
        self.log.write_text("x",encoding="utf-8")
        with self.assertRaises(PermissionError): reader.read()
        reader = ApprovedLog(self.log,self.root)
        self.log.rename(self.root/"old.log"); self.log.write_text("replacement")
        with self.assertRaises(PermissionError): reader.read()
    def test_outside_or_non_log_is_denied(self):
        for path in (self.root.parent/"outside.log",self.root/"secret.env",self.root):
            with self.assertRaises((PermissionError,FileNotFoundError)): ApprovedLog(path,self.root)
    def test_tail_is_bounded(self):
        self.log.write_bytes(b"a"*20000)
        read=ApprovedLog(self.log,self.root).read()
        self.assertEqual(read["byte_start"],3616); self.assertEqual(len(read["text"]),16384)


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quartz-coord-test-")
        self.root = Path(self.temp.name); self.log = self.root/"events.log"; self.log.write_text("fixture ready")
        from core.squad_adapter import SquadAdapter
        self.squad = SquadAdapter(self.root); self.squad.initialize()
        self.desktop=Operator(); self.reader=Reader(); self.events=[]
        self.service=ChatCoordination(self.desktop,lambda *args:self.events.append(args),
                                      codex_factory=lambda:self.reader,agy_factory=lambda:self.reader)
        self.plan=self.service.propose(TASK,{"id":"test","path":str(self.root)},"conversation",MODELS)
    def tearDown(self): self.service.stop(); self.temp.cleanup()
    def approve(self,**overrides):
        args={"confirmed":True,"agy_ack":True}; args.update(overrides)
        return self.service.approve(self.plan["id"],1,str(self.log),60,**args)
    def wait_for(self,predicate):
        limit=time.monotonic()+6
        while not predicate() and time.monotonic()<limit: time.sleep(.05)
        self.assertTrue(predicate())
    def test_explicit_boolean_consent(self):
        for bad in (False,"true",1,None):
            with self.assertRaises(PermissionError): self.approve(confirmed=bad)
        self.assertEqual(self.desktop.calls,[])
    def test_duration_and_target_identity(self):
        with self.assertRaises(ValueError): self.service.approve(self.plan["id"],1,str(self.log),901,confirmed=True,agy_ack=True)
        self.desktop.broker.backend.target["pid"] += 1
        with self.assertRaises(PermissionError): self.approve()
        self.assertEqual(self.desktop.calls,[])
    def test_single_consent_propagates_two_exact_identities(self):
        from tests.test_desktop_multiwindow import MultiBackend
        self.desktop.broker.backend=MultiBackend()
        self.plan=self.service.propose(TASK,{"id":"test","path":str(self.root)},"conversation",MODELS)
        self.service.approve(self.plan["id"],[1,2],str(self.log),60,confirmed=True,agy_ack=True)
        args,kwargs=self.desktop.calls[0]
        self.assertEqual(args[1],[1,2])
        self.assertEqual([w["handle"] for w in kwargs["expected_targets"]],[1,2])
    def test_second_selected_identity_change_blocks_entire_start(self):
        from tests.test_desktop_multiwindow import MultiBackend
        self.desktop.broker.backend=MultiBackend()
        self.plan=self.service.propose(TASK,{"id":"test","path":str(self.root)},"conversation",MODELS)
        self.desktop.broker.backend.items[2]["started"]+=1
        with self.assertRaises(PermissionError):self.service.approve(self.plan["id"],[1,2],str(self.log),60,confirmed=True,agy_ack=True)
        self.assertEqual(self.desktop.calls,[])
    def test_unknown_launch_id_cannot_expand_consent(self):
        with self.assertRaises(PermissionError):self.service.approve(self.plan["id"],1,str(self.log),60,confirmed=True,agy_ack=True,launch_ids=["unapproved"])
        self.assertEqual(self.desktop.calls,[])
    def test_existing_operator_blocks_second(self):
        self.desktop.active=True
        with self.assertRaises(RuntimeError): self.approve()
        self.assertEqual(self.desktop.calls,[])
    def test_real_squad_roundtrip_and_cleanup(self):
        self.approve()
        self.assertNotEqual(self.service._agent("codex"),"quartz-codex")
        self.wait_for(lambda: bool(self.service.notes))
        self.assertEqual(self.service.notes[0]["sender"],"antigravity")
        self.assertTrue(self.reader.calls[0][2]["tool_guard"])
        self.assertNotIn("desktop_connection",self.reader.calls[0][2])
        self.assertTrue((Path(self.reader.calls[0][1])/".agents/hooks.json").is_file())
        self.service.instruct("Yalnız test düğmesini incele.")
        self.desktop.run={"status":"completed","result":"Actual operator result."}
        self.wait_for(lambda:not self.service.status()["active"])
        self.wait_for(lambda:self.service.job.get("squad_closed"))
        self.assertEqual(self.service.job["status"],"completed")
        self.assertGreaterEqual(len(self.reader.calls),2)
        self.assertIn("Actual operator result.",self.reader.calls[-1][0])
        self.assertFalse(self.desktop.active); self.assertIsNone(self.service.temp)
        self.assertIsNone(self.desktop.broker.context_provider)
        self.assertTrue(any(event[1]=="codex" for event in self.events))
    def test_failed_operator_is_not_success(self):
        self.approve(); self.desktop.run={"status":"failed","result":"blocked"}
        self.wait_for(lambda:not self.service.status()["active"])
        self.assertEqual(self.service.job["status"],"failed")
    def test_reader_start_failure_cleans_resources(self):
        with patch.object(self.reader,"start",side_effect=RuntimeError("reader unavailable")):
            with self.assertRaises(RuntimeError): self.approve()
        self.assertIsNone(self.service.temp); self.assertFalse(self.desktop.active)
        self.assertTrue(self.service.job["squad_closed"])
    def test_observer_tool_attempt_stops_both(self):
        original=self.reader.start
        def command(*args,**kwargs):
            run=original(*args,**kwargs); self.reader.runs[run["id"]]["commands"]=["forbidden"]; return run
        with patch.object(self.reader,"start",side_effect=command): self.approve()
        self.wait_for(lambda:not self.service.status()["active"])
        self.assertEqual(self.service.job["status"],"failed"); self.assertFalse(self.desktop.active)
    def test_stop_revokes_and_preserves_log(self):
        before=self.log.read_bytes(); self.approve(); self.service.stop()
        self.assertEqual(self.service.job["status"],"cancelled")
        self.assertFalse(self.desktop.active); self.assertEqual(self.log.read_bytes(),before)
    def test_normal_chat_inbox_is_not_consumed(self):
        self.squad.join("quartz-codex"); self.squad.join("unrelated")
        self.squad.send("unrelated","quartz-codex","unrelated conversation")
        self.approve(); self.wait_for(lambda:bool(self.service.notes))
        unread=self.squad.receive("quartz-codex")
        self.assertEqual([m["content"] for m in unread],["unrelated conversation"])


if __name__ == "__main__": unittest.main()
