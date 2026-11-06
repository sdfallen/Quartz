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
from core.task_outcome import stop_summary
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

    def test_task_without_deadline_stays_callable_and_gets_a_continuous_session(self):
        self.task.job["expires_at"] = None
        self.assertEqual(self.task._provider("op"), "codex")
        self.request()
        self.assertGreater(self.task.pending["expires_at"], time.time())
        self.task.approve(self.task.pending["id"], confirmed=True)
        self.assertTrue(self.broker._session["continuous"])
        self.assertTrue(self.broker._session["persistent_control"])

    def test_legacy_game_window_keeps_the_bounded_session(self):
        self.task.job["expires_at"] = None
        self.task.warband = Mock()
        self.backend.target["exe"] = "mb_warband.exe"
        self.request()
        self.task.approve(self.task.pending["id"], confirmed=True)
        self.assertFalse(self.broker._session["continuous"])
        self.assertFalse(self.broker._session["persistent_control"])
        self.task.warband = None

    def test_running_task_outlives_every_old_limit_until_stop(self):
        now = [0]
        self.broker.clock = lambda: now[0]
        self.task.job["expires_at"] = None
        self.request()
        self.task.approve(self.task.pending["id"], confirmed=True)
        runtime = SimpleNamespace(TERMINAL={"completed", "failed"}, get=lambda _: {"status": "running"}, cancel=lambda _: None)
        self.task.runs = {"codex": (runtime, "r1")}
        watcher = threading.Thread(target=self.task._watch, args=(self.task.job, self.task.stopped), daemon=True)
        self.task.thread = watcher
        watcher.start()
        for _ in range(4):  # Far past the old 15 and 30 minute limits.
            time.sleep(.5)
            now[0] += 1200
        time.sleep(.5)
        self.assertTrue(watcher.is_alive())
        self.assertEqual(self.task.job["status"], "running")
        self.assertTrue(self.broker.status()["active"])
        self.assertEqual(self.broker._session["token"], self.task.connection["token"])
        self.task.stop("cancelled")
        self.assertEqual(self.task.job["status"], "cancelled")
        self.assertFalse(self.broker.status()["active"])

    def test_provider_turn_is_not_cut_at_fifteen_minutes(self):
        started = {}
        class Runtime:
            backend = "gemini"
            TERMINAL = {"completed"}
            def start(self, _prompt, _workspace, **options):
                started.update(options)
                return {"id": "r"}
        self.task.factories = {"antigravity": Runtime}
        self.task.job.update(models={"antigravity": {"model": "auto", "effort": "medium"}},
                             roles={"operator": "antigravity", "observer": "codex", "assignments": {"antigravity": "", "codex": ""}})
        self.task.server = SimpleNamespace(server_port=1, shutdown=lambda: None, server_close=lambda: None)
        self.task.tokens["antigravity"] = "op"
        self.task._launch_provider("antigravity")
        self.assertEqual(started["timeout"], "1440m")
        self.task.runs = {}

    def test_identical_jarvis_input_is_refused_then_marks_the_task_stalled(self):
        job = self.task.job
        for _ in range(40):
            self.task._note_jarvis_input(job, "jarvis_input", {"action": "click"})
        for _ in range(4):
            with self.assertRaises(PermissionError):
                self.task._note_jarvis_input(job, "jarvis_input", {"action": "click"})
        self.assertNotIn("stalled", job)
        with self.assertRaises(PermissionError):
            self.task._note_jarvis_input(job, "jarvis_input", {"action": "click"})
        self.assertTrue(job["stalled"])

    def test_varied_jarvis_input_is_never_a_repeat_and_text_is_not_stored(self):
        job = self.task.job
        for number in range(200):
            self.task._note_jarvis_input(job, "jarvis_input", {"action": "type", "text": "gizli" + str(number % 2)})
        self.assertNotIn("stalled", job)
        self.assertNotIn("gizli", json.dumps(job["input_repeat"]))

    def test_stall_has_its_own_honest_summary(self):
        summary = stop_summary("blocked: stalled: repeated action", {"status": "NOT VERIFIED"})
        self.assertIn("tekrarladığı", summary)
        self.assertIn("tamamlanmış sayılmadı", summary)

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

    def test_context_names_both_task_ids_and_delivers_only_this_tasks_messages(self):
        # Live 6 Nov: Codex saw task_id from task_context and another id in message
        # receipts and concluded routing was broken.
        self.task.squad.receive.return_value=[{"task_id":"squad-task","content":"operator report"},
                                              {"task_id":"other-task","content":"stale"}]
        context=self.call("task_context",token="review")
        self.assertEqual((context["task_id"],context["squad_task_id"]),("test","squad-task"))
        self.assertEqual([m["content"] for m in context["colleague_messages"]],["operator report"])
        self.task.squad.receive.assert_called_with("g-task")
        self.call("task_message",{"text":"Not Defteri'ne yazdım; gözlemde 'deneme' görünüyor."})
        self.task.squad.send.assert_called_with("c-task","g-task","Not Defteri'ne yazdım; gözlemde 'deneme' görünüyor.",task_id="squad-task")

    def test_operator_is_asked_to_report_its_step_to_the_collaborator(self):
        from core.natural_desktop import INSTRUCTIONS
        self.assertIn("send one short task_message with what you did",INSTRUCTIONS)
        self.assertIn("squad_task_id",INSTRUCTIONS)

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

    def test_duplicate_approval_does_not_revoke_existing_grant(self):
        self.request()
        identity = self.task.pending['id']
        self.task.approve(identity, confirmed=True)
        grant = dict(self.task.connection)
        with self.assertRaises(PermissionError):
            self.task.approve(identity, confirmed=True)
        self.assertFalse(self.task.stopped.is_set())
        self.assertEqual(self.task.connection, grant)
        self.assertTrue(self.broker.status()['active'])
        self.assertEqual(self.task.tokens['codex'], 'op')
        self.task.squad.complete_task.assert_not_called()

    def test_invalid_confirmation_does_not_cancel_an_active_scope(self):
        self.approve()
        (self.root / 'extra.log').write_text('fixture', encoding='utf-8')
        self.call('task_read_log', {'path': 'extra.log'}, 'review')
        pending = dict(self.task.pending)
        grant = self.task.connection
        self.assertIsNone(grant)  # A manual card now pauses even the old scope.
        with self.assertRaises(PermissionError):
            self.task.approve(pending['id'], confirmed='true')
        self.assertFalse(self.task.stopped.is_set())
        self.assertEqual(self.task.pending, pending)
        self.assertEqual(self.task.connection, grant)
        self.task.approve(pending['id'], confirmed=True)
        self.assertIn('extra.log', self.task.approved_logs)

    def test_superseded_card_does_not_cancel_live_input_or_new_request(self):
        self.approve()
        for name in ('first.log', 'second.log'):
            (self.root / name).write_text('fixture', encoding='utf-8')
        self.call('task_read_log', {'path': 'first.log'}, 'review')
        old = self.task.pending['id']
        self.call('task_read_log', {'path': 'second.log'}, 'review')
        latest = self.task.pending['id']
        with self.assertRaises(PermissionError):
            self.task.approve(old, confirmed=True)
        self.assertFalse(self.task.stopped.is_set())
        self.assertEqual(self.task.pending['id'], latest)
        self.assertFalse(self.broker.status()['active'])
        self.task.approve(latest, confirmed=True)
        self.assertEqual(set(self.task.approved_logs), {'first.log', 'second.log'})

    def test_valid_approval_failure_still_revokes_the_current_scope(self):
        self.approve()
        (self.root / 'extra.log').write_text('fixture', encoding='utf-8')
        self.call('task_read_log', {'path': 'extra.log'}, 'review')
        identity = self.task.pending['id']
        self.backend.target['pid'] += 1
        with self.assertRaises(PermissionError):
            self.task.approve(identity, confirmed=True)
        self.assertTrue(self.task.stopped.is_set())
        self.assertIsNone(self.task.connection)
        self.assertFalse(self.broker.status()['active'])
        self.assertEqual(self.task.tokens, {})

    def test_concurrent_duplicate_approvals_apply_the_grant_only_once(self):
        self.request()
        identity = self.task.pending['id']
        barrier = threading.Barrier(2)
        outcomes = []

        def approve():
            barrier.wait(timeout=2)
            try:
                self.task.approve(identity, confirmed=True)
                outcomes.append('applied')
            except PermissionError:
                outcomes.append('stale')

        with patch.object(self.broker, 'grant', wraps=self.broker.grant) as grant:
            threads = [threading.Thread(target=approve) for _ in range(2)]
            for worker in threads:
                worker.start()
            for worker in threads:
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive())
            self.assertCountEqual(outcomes, ['applied', 'stale'])
            grant.assert_called_once()
        self.assertFalse(self.task.stopped.is_set())
        self.assertTrue(self.broker.status()['active'])
        self.assertEqual(self.backend.actions, [])

    def test_late_approval_failure_cannot_stop_a_new_task_generation(self):
        self.approve()
        (self.root / 'extra.log').write_text('fixture', encoding='utf-8')
        self.call('task_read_log', {'path': 'extra.log'}, 'review')
        identity = self.task.pending['id']
        original = self.task.job
        stop = self.task.stop

        def replace_generation_then_stop(reason, **kwargs):
            # Deterministic interleaving at the error-cleanup boundary, with no
            # real app/process/input. The grant stands in for the new task's.
            self.task.job = {**original, 'id': 'new-generation'}
            self.task.tokens = {'codex': 'new-token'}
            self.task.connection = self.broker.grant([1], 'codex', confirmed=True)
            return stop(reason, **kwargs)

        self.backend.target['pid'] += 1
        with patch.object(self.task, 'stop', side_effect=replace_generation_then_stop), \
                patch('core.natural_desktop.overlay_manager.hide') as hide:
            with self.assertRaises(PermissionError):
                self.task.approve(identity, confirmed=True)
        self.assertFalse(self.task.stopped.is_set())
        self.assertEqual(self.task.job['id'], 'new-generation')
        self.assertEqual(self.task.tokens, {'codex': 'new-token'})
        self.assertTrue(self.broker.status()['active'])
        hide.assert_not_called()

    def test_repeated_stop_does_not_repeat_resource_release(self):
        self.approve()
        learning = Mock()
        self.task.application_learning = learning
        with patch('core.natural_desktop.overlay_manager.hide') as hide:
            self.task.stop()
            self.task.stop()
        hide.assert_called_once()
        learning.stop.assert_called_once()
        self.task.squad.complete_task.assert_called_once()

    def test_learning_release_error_does_not_prevent_authority_revocation(self):
        self.approve()
        learning = Mock()
        learning.stop.side_effect = RuntimeError('fixture release failure')
        self.task.application_learning = learning
        self.task.stop()
        self.assertTrue(self.task.stopped.is_set())
        self.assertEqual(self.task.tokens, {})
        self.assertFalse(self.broker.status()['active'])
        self.assertEqual(self.task.job['cleanup']['status'], 'failed')
        self.task.squad.complete_task.assert_called_once()

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

    def notepad(self, value):
        image=base64.b64encode(b"fixture-image").decode()
        self.backend.observe=lambda _: {"ui":{"elements":[{"name":"Metin Düzenleyici","type":"Edit","visible":True,"value":value}]},"image_base64":image}

    def test_quoted_text_from_the_user_is_checked_by_quartz_after_input(self):
        # Live 6 Nov: Gemini typed 'deneme' but never called desktop_verify; 217 s were spent afterwards.
        from core.natural_desktop import requested_literals, HOST_TEXT_SOURCE
        self.task.job["requested_text"]=requested_literals("Gemini, Not Defteri’ni aç ve ‘deneme’ yaz")
        self.assertEqual(self.task.job["requested_text"],["deneme"])
        self.approve(); self.notepad("")
        observed=self.call("desktop_focus")
        self.assertNotIn("host_verification",observed)
        self.notepad("deneme")
        observed=self.call("desktop_act",{"snapshot_id":observed["snapshot_id"],"action":"text","text":"deneme"})
        self.assertEqual(self.task.job["verification"]["source"],HOST_TEXT_SOURCE)
        self.assertEqual(self.task.job["verification"]["status"],"OBSERVED UI CRITERION VERIFIED")
        self.assertIn("end your turn",observed["host_verification"]["next"])
        self.assertIn("'deneme'",stop_summary("completed",self.task.job["verification"]))
        self.notepad("başka")  # A later observation without the text withdraws the check.
        observed=self.call("desktop_observe")
        self.assertEqual(self.task.job["verification"]["status"],"NOT VERIFIED")
        self.assertNotIn("host_verification",observed)

    def test_host_check_ignores_text_that_was_visible_before_any_input(self):
        from core.natural_desktop import requested_literals
        self.task.job["requested_text"]=requested_literals("Not Defteri'ne 'deneme' yaz")
        self.approve(); self.notepad("deneme")
        observed=self.call("desktop_focus")
        observed=self.call("desktop_act",{"snapshot_id":observed["snapshot_id"],"action":"key","key":"end"})
        self.assertEqual(self.task.job["verification"]["status"],"NOT VERIFIED")
        self.assertNotIn("host_verification",observed)

    def test_model_chosen_text_never_becomes_a_host_check(self):
        self.task.job["requested_text"]=[]  # The user quoted nothing.
        self.approve(); self.notepad("")
        observed=self.call("desktop_focus")
        self.notepad("Metin Düzenleyici deneme")
        observed=self.call("desktop_act",{"snapshot_id":observed["snapshot_id"],"action":"text","text":"deneme"})
        self.assertNotIn("source",self.task.job["verification"])
        self.assertNotIn("host_verification",observed)
        self.assertIn("tüm hedefin doğrulandığı anlamına gelmez",stop_summary("completed",self.task.job["verification"]))

    def test_typed_text_is_verified_from_the_edit_value_not_only_names(self):
        # Live 6 Nov: Notepad's Edit is named "Metin Düzenleyici"; "deneme" exists only as its value.
        self.approve()
        image=base64.b64encode(b"fixture-image").decode()
        self.backend.observe=lambda _: {"ui":{"elements":[{"name":"Metin Düzenleyici","type":"Edit","visible":True,"value":"deneme"}]},"image_base64":image}
        observed=self.call("desktop_focus")
        args={"snapshot_id":observed["snapshot_id"],"expected_text":"deneme"}
        self.assertEqual(self.call("desktop_verify",args)["status"],"NOT VERIFIED")  # No input yet.
        observed=self.call("desktop_act",{"snapshot_id":observed["snapshot_id"],"action":"text","text":"deneme"})
        args["snapshot_id"]=observed["snapshot_id"]
        self.assertEqual(self.call("desktop_verify",args)["status"],"OBSERVED UI CRITERION VERIFIED")
        args["expected_text"]="başka metin"
        self.assertEqual(self.call("desktop_verify",args)["status"],"NOT VERIFIED")
        self.backend.observe=lambda _: {"ui":{"elements":[{"name":"Metin Düzenleyici","type":"Edit","visible":False,"value":"deneme"}]},"image_base64":image}
        observed=self.call("desktop_observe")
        self.assertEqual(self.call("desktop_verify",{"snapshot_id":observed["snapshot_id"],"expected_text":"deneme"})["status"],"NOT VERIFIED")

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

    def test_focus_loss_never_stops_the_task_in_warband_profile(self):
        self.task.warband = Mock()
        self.approve();self.call("desktop_focus");self.backend.foreground=False
        session = self.broker.status()["id"]
        self.assertEqual(self.task.status()["operator"]["session"]["id"], session)
        self.assertTrue(self.call("desktop_observe")["focus_recovered"])
        self.assertEqual(session, self.broker.status()["id"])
        self.assertEqual(self.backend.actions, [])

    def test_warband_game_window_still_revokes_on_focus_loss(self):
        self.task.warband = Mock()
        self.backend.target["exe"] = r"C:\\Game\\mb_warband.exe"
        self.approve();self.call("desktop_focus");self.backend.foreground=False
        self.assertFalse(self.broker.status()["active"])
        self.assertIn("user takeover", self.broker.stop_reason)

    def test_agents_are_told_to_continue_until_stop(self):
        from core.natural_desktop import INSTRUCTIONS
        self.assertIn("keep working until the user presses Stop", INSTRUCTIONS)

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

    def test_shelved_aster_project_gets_an_ordinary_isolated_desktop_task(self):
        # Live 4-7 Nov: every desktop task in the ASTER chat ran the Universal Modder profile.
        from tests.test_chat_coordination import MODELS
        class Runtime:
            TERMINAL={"completed","failed","cancelled"}
            executable="test-runtime.exe"
            def __init__(self):self.started=[]
            def start(self,prompt,workspace,**opts):
                self.started.append(prompt);return {"id":"run"+str(len(self.started)),"status":"running"}
            def get(self,rid):return {"id":rid,"status":"running"}
            def cancel(self,rid):pass
        aster=self.root/"WarbandIsland";aster.mkdir()
        codex,gemini=Runtime(),Runtime()
        squad=Mock();squad.initialized=True;squad.create_task.return_value={"id":"task"};squad.receive.return_value=[]
        squad.status.return_value={"installed":True,"initialized":True}
        roots=[]
        def squad_factory(path):roots.append(path);return squad
        warband=Mock()
        task=NaturalDesktopTask(self.desktop,lambda *a:None,factories={"codex":lambda:codex,"antigravity":lambda:gemini},
            squad_factory=squad_factory,evidence_root=self.root/"aster-evidence",warband_factory=warband)
        try:
            with patch("core.warband_workspace.PROJECT",aster), \
                 patch("core.natural_desktop.subprocess.run",return_value=SimpleNamespace(returncode=0)), \
                 patch("core.natural_desktop.ensure_antigravity_tool_grants"),patch("core.natural_desktop.write_operator_hooks"):
                task.start("Gemini, Not Defteri'ni aç ve 'deneme' yaz",{"id":"aster-warband","path":str(aster),"workflow":"warband"},"chat",MODELS)
            warband.assert_not_called()
            self.assertIsNone(task.warband)
            self.assertEqual(roots,[str(task.evidence)])  # Squad lives in the task folder, not in the ASTER tree.
            self.assertFalse((aster/".squad").exists())
            self.assertEqual(task.squad_info["mode"],"task-isolated")
            self.assertTrue(all("Universal Modder workspace" not in prompt for prompt in codex.started+gemini.started))
            with self.assertRaises(PermissionError):  # Other ASTER paths stay refused.
                other=aster/"Modules";other.mkdir()
                NaturalDesktopTask(self.desktop,lambda *a:None,factories={},evidence_root=self.root/"x").start(
                    "x",{"path":str(other)},"chat",MODELS)
        finally:task.stop()

    def test_early_approval_waits_for_pause_drain_and_late_old_exit_cannot_complete_new_run(self):
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
                with self.assertRaises(PermissionError):
                    task.approve(task.pending["id"],confirmed=True)
                task._drain_pause(task.job)
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
