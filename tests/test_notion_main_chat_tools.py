"""Main-chat lifecycle of the read-only Notion Worker fixture (mocked cloud).

The cloud agent and Notion queue are simulated; the local side (manifest,
signed envelopes, ReadOnlyWorkerBridge, durable SQLite receipt, fixture file)
is real. This is NOT live acceptance and not a packaged Windows check.
"""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock

from core.atomic_json import atomic_write_json, load_json
from core.notion_cli import NotionError
from core import notion_worker_bridge as wb
from core.notion_worker_task import NotionWorkerTasks, wants_local_read

KEY = bytes.fromhex("34" * 32)            # synthetic test key, not a deployed secret
WORKSPACE = "20000000-0000-0000-0000-000000000002"
AGENT = "30000000-0000-0000-0000-000000000003"
QUEUE = "40000000-0000-0000-0000-000000000004"


class FakeQueue:
    def __init__(self, workspace_id, queue_id):
        self.queue_id = queue_id
        self.pages, self.completed, self.fail_query = {}, [], None

    def _page(self, pid):
        return {"id": pid, "parent": {"data_source_id": self.queue_id}, **self.pages[pid]}

    def create(self, name, properties):
        pid = "50000000-0000-0000-0000-%012d" % (len(self.pages) + 1)
        self.pages[pid] = {"name": name, "properties": properties}
        return {"id": pid}

    def page(self, pid):
        return self._page(pid)

    def query(self, task_id, session_id):
        if self.fail_query:
            raise self.fail_query
        hits = []
        for pid, page in self.pages.items():
            props = page["properties"]
            if (wb.property_text({"properties": props}, "Task ID") == task_id and
                    wb.property_text({"properties": props}, "Session ID") == session_id and
                    props.get("Signed Request")):
                hits.append(self._page(pid))
        return hits

    def complete(self, pid, result, state):
        self.pages[pid]["properties"]["Signed Result"] = wb.rich(result)
        self.completed.append((pid, state))


class FakeCloud:
    """Simulated Custom Agent + Worker: only acts on Quartz's own instructions."""

    def __init__(self, behaviour="honest"):
        self.behaviour, self.queue, self.messages = behaviour, None, []

    def on_message(self, run, prompt):
        self.messages.append(prompt)
        grant = re.search(r"grant_page_id=([0-9a-f-]{36})", prompt)
        notice = re.search(r"request_page_id=([0-9a-f-]{36})", prompt)
        if self.behaviour == "requires_action" and grant:
            return "blocked", ""
        if self.behaviour == "silent" and grant:
            return "running", ""
        if grant and self.behaviour != "no_tool":
            page = self.queue.page(grant.group(1))
            g = wb.verify(wb.property_text(page, "Signed Result"), "grant", KEY)
            request = {"schema_version": 1, **{k: g[k] for k in ("task_id", "session_id", "project_id", "scope_ref",
                       "request_id")}, "tool_name": "read_test_file",
                       "arguments": {"relative_path": g["relative_path"]}, "expires_at": g["expires_at"]}
            props = {"Task ID": wb.rich(g["task_id"]), "Session ID": wb.rich(g["session_id"]),
                     "Signed Request": wb.rich(wb.sign("request", request, KEY))}
            self.queue.create(g["request_id"], props)
            if self.behaviour == "tamper":
                # Same request_id, different envelope bytes for the same content.
                body = json.dumps(request, ensure_ascii=False, separators=(", ", ": "))
                mac = __import__("hmac").new(KEY, ("quartz-readonly/request/v1\n" + body).encode(),
                                             hashlib.sha256).hexdigest()
                env = json.dumps({"v": 1, "kind": "request", "body": body, "mac": mac})
                self.queue.create(g["request_id"], {**props, "Signed Request": wb.rich(env)})
            return "completed", "Aracı çağırdım; sonuç kuyruğa alındı."
        if notice:
            page = self.queue.page(notice.group(1))
            raw = wb.property_text(page, "Signed Result")
            result = wb.verify(raw, "result", KEY) if raw else {}
            if self.behaviour == "liar" or not result.get("output"):
                return "completed", "Başardım, dosyayı okudum ve doğruladım."
            out = result["output"]
            return "completed", "Dosya kanıtı: %s SHA-256: %s" % (out["text"].split(": ")[-1], out["sha256"])
        return "completed", "Merhaba."


class FakeRuntime:
    TERMINAL = {"completed", "failed", "cancelled", "blocked"}
    REMOTE_TERMINAL = {"completed", "failed", "canceled", "terminated"}

    def __init__(self, cloud, ready=True):
        self.cloud, self.ready, self.runs, self.owned = cloud, ready, {}, set()
        self.cancelled = []

    def configuration(self):
        return {"workspace_id": WORKSPACE, "agent_id": AGENT, "agent_name": "Quartz"}

    def connection_status(self, force=False):
        return {"ready": self.ready, "checking": False, "error": "" if self.ready else "Giriş yapılmamış."}

    def _owned(self, session_id, config):
        return session_id in self.owned

    def start(self, prompt, *, session_id=None):
        sid = session_id or "60000000-0000-0000-0000-%012d" % (len(self.owned) + 1)
        self.owned.add(sid)
        rid = "notion-%d" % (len(self.runs) + 1)
        self.runs[rid] = {"id": rid, "status": "running", "session_id": sid, "result": ""}
        status, text = self.cloud.on_message(self.runs[rid], prompt)
        self.runs[rid].update(status=status, result=text)
        return dict(self.runs[rid])

    def get(self, rid):
        return dict(self.runs[rid])

    def cancel(self, rid):
        self.cancelled.append(rid)
        self.runs[rid]["status"] = "cancelled"
        return dict(self.runs[rid])


class Harness:
    def __init__(self, test, behaviour="honest", bridge=None, ready=True, key=KEY):
        self.temp = tempfile.TemporaryDirectory()
        test.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        atomic_write_json(self.home / "worker-bridge.json", bridge if bridge is not None else {
            "mode": "readonly-fixture", "workspace_id": WORKSPACE, "queue_id": QUEUE,
            "credential_target": "Quartz/Test", "main_chat": True})
        self.cloud = FakeCloud(behaviour)
        self.runtime = FakeRuntime(self.cloud, ready=ready)
        self.queues = []

        def queue_factory(workspace_id, queue_id):
            q = FakeQueue(workspace_id, queue_id)
            self.cloud.queue = q
            self.queues.append(q)
            return q
        self.tools = NotionWorkerTasks(self.runtime, home=self.home, queue_factory=queue_factory,
                                       key_loader=lambda target: key, sleep=lambda s: time.sleep(0.001))
        self.tools.POLL, self.tools.REQUEST_WAIT, self.tools.RESULT_WAIT = 0.001, 2, 2
        self.cancel_flag = threading.Event()
        self.published = []
        self.reads = 0
        original = wb.ReadOnlyWorkerBridge._read_fixture

        def counting(bridge_self):
            self.reads += 1
            return original(bridge_self)
        patcher = unittest.mock.patch.object(wb.ReadOnlyWorkerBridge, "_read_fixture", counting)
        patcher.start()
        test.addCleanup(patcher.stop)

    def start(self, prompt="Test projesindeki dosyayı incele", session=None, conversation="c1"):
        self.outcome = {}

        def run():
            self.outcome["value"] = self.tools.run_turn(
                conversation_id=conversation, message_id="m1", prompt=prompt, session_id=session,
                cancelled=self.cancel_flag.is_set, publish=lambda text, view: self.published.append((text, view)))
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self

    def pending(self, timeout=3):
        end = time.time() + timeout
        while time.time() < end:
            task = self.tools.payload("c1")["task"]
            if task and task.get("state") == "awaiting_approval":
                return task["pending"]["id"]
            time.sleep(0.005)
        raise AssertionError("no pending approval")

    def result(self, timeout=10):
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "turn did not finish"
        return self.outcome["value"]

    def manifests(self):
        return [load_json(p, {}) for p in sorted((self.home / "worker-fixtures").glob("*/manifest.json"))]


class MainChatFlowTests(unittest.TestCase):
    def test_approval_reads_real_file_and_verifies_cloud_used_it(self):
        h = Harness(self).start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        status, text, session = h.result()
        self.assertEqual(status, "completed")
        manifest = h.manifests()[0]
        self.assertIn(manifest["proof"], text)
        self.assertEqual(h.reads, 1)
        # The random proof was never sent to the model before the real tool result.
        self.assertFalse(any(manifest["proof"] in m for m in h.cloud.messages))
        view = h.tools.payload("c1")["task"]
        self.assertEqual((view["state"], view["verification"]), ("completed", "verified"))
        self.assertEqual(manifest["state"], "verified")
        self.assertTrue((Path(manifest["root"]) / ".stopped").exists(), "grant is single-use")
        self.assertEqual(h.queues[0].completed[0][1], "completed")

    def test_cloud_claim_without_real_result_is_not_verified(self):
        h = Harness(self, "liar").start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        status, text, _ = h.result()
        view = h.tools.payload("c1")["task"]
        self.assertEqual(view["verification"], "observed")
        self.assertIn("doğrulanamadı", text)

    def test_denial_sends_nothing_and_creates_no_scope(self):
        h = Harness(self).start()
        h.tools.decide(h.pending(), "c1", False)
        status, text, _ = h.result()
        self.assertEqual(status, "cancelled")
        self.assertEqual(h.cloud.messages, [])
        self.assertFalse((h.home / "worker-fixtures").exists())
        self.assertIn("İzin verilmedi", text)

    def test_unconfirmed_wrong_conversation_stale_and_double_decisions_are_rejected(self):
        h = Harness(self).start()
        pid = h.pending()
        with self.assertRaises(PermissionError): h.tools.decide(pid, "c1", True, confirmed=False)
        with self.assertRaises(PermissionError): h.tools.decide(pid, "other-conversation", True, confirmed=True)
        with self.assertRaises(PermissionError): h.tools.decide("old-pending-id", "c1", True, confirmed=True)
        h.tools.decide(pid, "c1", True, confirmed=True)
        with self.assertRaises(PermissionError): h.tools.decide(pid, "c1", True, confirmed=True)
        self.assertEqual(h.result()[0], "completed")
        self.assertEqual(h.reads, 1)

    def test_approval_after_the_turn_ended_is_refused(self):
        h = Harness(self).start()
        pid = h.pending()
        h.cancel_flag.set()
        h.result()
        with self.assertRaises(PermissionError):
            h.tools.decide(pid, "c1", True, confirmed=True)
        self.assertEqual(h.cloud.messages, [])

    def test_late_approval_on_a_still_open_but_stopped_turn_is_refused(self):
        h = Harness(self).start()
        pid = h.pending()
        h.cancel_flag.set()   # Stop pressed; decide races the worker thread
        with self.assertRaises(PermissionError):
            h.tools.decide(pid, "c1", True, confirmed=True)
        self.assertEqual(h.result()[0], "cancelled")

    def test_approval_timeout_closes_without_cloud_request(self):
        h = Harness(self)
        h.tools.APPROVAL_TTL = 0.05
        h.start()
        status, text, _ = h.result()
        self.assertEqual(status, "cancelled")
        self.assertIn("süresi doldu", text)
        self.assertEqual(h.cloud.messages, [])

    def test_stop_during_execution_never_publishes_a_late_result(self):
        h = Harness(self, "silent").start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        end = time.time() + 3
        while not any("grant_page_id=" in m for m in h.cloud.messages) and time.time() < end:
            time.sleep(0.005)
        h.cancel_flag.set()
        h.tools.stop_all()
        status, text, _ = h.result()
        self.assertEqual(status, "cancelled")
        self.assertEqual(h.reads, 0)
        self.assertEqual(h.queues[0].completed, [])
        self.assertTrue(h.runtime.cancelled, "remote stop requested")
        self.assertIn("Yerel işlem durduruldu", text)
        self.assertIn("Notion oturumunun durduğu", text)
        self.assertTrue((Path(h.manifests()[0]["root"]) / ".stopped").exists())

    def test_stop_while_processing_blocks_publication(self):
        h = Harness(self).start()
        original = wb.ReadOnlyWorkerBridge.process

        def stop_then_process(bridge_self, page):
            h.tools.stop_all()          # the real Stop path, racing the local step
            return original(bridge_self, page)
        with unittest.mock.patch.object(wb.ReadOnlyWorkerBridge, "process", stop_then_process):
            h.tools.decide(h.pending(), "c1", True, confirmed=True)
            status, _, _ = h.result()
        self.assertEqual(status, "cancelled")
        self.assertEqual(h.queues[0].completed, [])

    def test_request_timeout_is_not_resent(self):
        h = Harness(self, "silent")
        h.tools.REQUEST_WAIT = 0.05
        h.start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        status, text, _ = h.result()
        self.assertEqual(status, "failed")
        self.assertIn("tekrarlanmadı", text)
        tool_messages = [m for m in h.cloud.messages if "grant_page_id=" in m]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(h.reads, 0)

    def test_connection_loss_fails_closed_without_resend(self):
        h = Harness(self).start()
        pid = h.pending()
        original = FakeQueue.query

        def broken(queue_self, *a):
            raise NotionError("Notion isteği zaman aşımına uğradı; gönderim otomatik tekrarlanmadı.",
                              code="timeout", uncertain=True)
        with unittest.mock.patch.object(FakeQueue, "query", broken):
            h.tools.decide(pid, "c1", True, confirmed=True)
            status, text, _ = h.result()
        self.assertEqual(status, "failed")
        self.assertIn("tekrarlanmadı", text)
        self.assertEqual(len([m for m in h.cloud.messages if "grant_page_id=" in m]), 1)
        self.assertEqual(h.manifests()[0]["state"], "failed")

    def test_notion_side_approval_is_never_auto_approved(self):
        h = Harness(self, "requires_action").start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        status, text, _ = h.result()
        self.assertEqual(status, "blocked")
        self.assertIn("otomatik onaylamadı", text)
        self.assertEqual(h.reads, 0)

    def test_tool_turn_without_signed_request_is_not_verified(self):
        h = Harness(self, "no_tool").start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        status, text, _ = h.result()
        self.assertEqual(status, "failed")
        self.assertIn("imzalı araç isteği oluşmadı", text)

    def test_same_request_id_with_changed_envelope_is_rejected_without_reread(self):
        h = Harness(self, "tamper").start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        status, _, _ = h.result()
        self.assertEqual(status, "failed")
        self.assertEqual(h.reads, 1)

    def test_duplicate_queue_rows_reuse_the_durable_receipt(self):
        h = Harness(self).start()
        original = FakeQueue.query
        with unittest.mock.patch.object(FakeQueue, "query", lambda q, *a: original(q, *a) * 2):
            h.tools.decide(h.pending(), "c1", True, confirmed=True)
            status, _, _ = h.result()
        self.assertEqual(status, "completed")
        self.assertEqual(h.reads, 1)

    def test_next_task_never_inherits_previous_scope(self):
        h = Harness(self).start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        _, _, session = h.result()
        h.start(session=session)
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        self.assertEqual(h.result()[0], "completed")
        first, second = h.manifests() if h.manifests()[0]["root"] < h.manifests()[1]["root"] else h.manifests()[::-1]
        for field in ("task_id", "scope_ref", "request_id", "root", "proof"):
            self.assertNotEqual(first[field], second[field], field)
        for manifest in (first, second):
            self.assertTrue((Path(manifest["root"]) / ".stopped").exists())

    def test_foreign_session_is_refused_before_any_scope(self):
        h = Harness(self).start(session="70000000-0000-0000-0000-000000000007")
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        status, text, _ = h.result()
        self.assertEqual(status, "blocked")
        self.assertFalse((h.home / "worker-fixtures").exists())

    def test_stop_with_nothing_running_remotely_says_so(self):
        h = Harness(self, "no_tool")
        original = h.runtime.start

        def start_then_stop(prompt, **kw):
            run = original(prompt, **kw)
            if "grant_page_id=" not in prompt:
                h.cancel_flag.set()      # Stop right after the session bootstrap completed
            return run
        h.runtime.start = start_then_stop
        h.start()
        h.tools.decide(h.pending(), "c1", True, confirmed=True)
        status, text, _ = h.result()
        self.assertEqual(status, "cancelled")
        self.assertEqual(h.runtime.cancelled, [])
        self.assertFalse(any("grant_page_id=" in m for m in h.cloud.messages))

    def test_window_close_while_waiting_cancels_cleanly(self):
        h = Harness(self).start()
        h.pending()
        h.tools.stop_all()
        status, _, _ = h.result()
        self.assertEqual(status, "cancelled")
        self.assertEqual(h.cloud.messages, [])

    def test_restart_fences_unfinished_grants(self):
        h = Harness(self)
        folder = h.home / "worker-fixtures" / "abc"
        folder.mkdir(parents=True)
        atomic_write_json(folder / "manifest.json", {"task_id": "abc", "state": "prepared"})
        done = h.home / "worker-fixtures" / "done"
        done.mkdir()
        atomic_write_json(done / "manifest.json", {"task_id": "done", "state": "verified"})
        fresh = NotionWorkerTasks(h.runtime, home=h.home, key_loader=lambda t: KEY)
        self.assertEqual(fresh.fenced_on_start, 1)
        self.assertTrue((folder / ".stopped").exists())
        self.assertEqual(load_json(folder / "manifest.json", {})["state"], "expired")
        self.assertFalse((done / ".stopped").exists())
        self.assertIsNone(fresh.payload("c1")["task"])

    def test_only_one_tool_task_at_a_time(self):
        h = Harness(self).start()
        h.pending()
        status, text, _ = h.tools.run_turn(conversation_id="c2", message_id="m2", prompt="test dosyasını oku",
                                           session_id=None, cancelled=lambda: False, publish=lambda *a: None)
        self.assertEqual(status, "blocked")
        h.tools.stop_all()
        h.result()

    def test_task_view_is_scoped_to_its_conversation(self):
        h = Harness(self).start()
        h.pending()
        self.assertIsNotNone(h.tools.payload("c1")["task"])
        self.assertIsNone(h.tools.payload("c2")["task"])
        h.tools.stop_all()
        h.result()


class AvailabilityTests(unittest.TestCase):
    def check(self, expected, **kwargs):
        h = Harness(self, **kwargs)
        self.assertEqual(h.tools.payload("c1")["availability"], expected)
        return h.tools.payload("c1")

    def test_ready_only_when_config_opt_in_key_and_connection_hold(self):
        payload = self.check("ready")
        self.assertEqual(payload["capabilities"], ["read_test_file"])
        self.check("unavailable", bridge={})
        base = {"mode": "readonly-fixture", "workspace_id": WORKSPACE, "queue_id": QUEUE, "credential_target": "x"}
        self.assertEqual(self.check("unavailable", bridge=base)["capabilities"], [])          # no opt-in
        self.check("unavailable", bridge={**base, "main_chat": True, "enabled": False})       # explicit off
        self.check("unavailable", bridge={**base, "main_chat": True, "workspace_id": AGENT})  # other workspace
        self.check("blocked", key=None)                                                       # no Credential Manager key
        self.check("blocked", ready=False)                                                    # Notion login not verified

    def test_payload_shape_matches_ui_contract(self):
        payload = self.check("ready")
        self.assertEqual(set(payload), {"schema_version", "availability", "capabilities", "message", "task"})
        self.assertEqual(payload["schema_version"], 1)


class IntentTests(unittest.TestCase):
    def test_only_explicit_test_file_reads_trigger_local_access(self):
        for text in ("Test projesindeki dosyayı incele", "test dosyasını oku", "Read the fixture.txt please",
                     "deneme dosyasına bak ve özetle"):
            self.assertTrue(wants_local_read(text), text)
        for text in ("Merhaba", "Bu kodu incele: print(1)", "C:/Users/x/secret.txt dosyasını oku",
                     "test yaz", "Notion sayfamı özetle"):
            self.assertFalse(wants_local_read(text), text)


class ChatWiringTests(unittest.TestCase):
    def test_notion_turn_routes_to_tools_only_when_ready_and_requested(self):
        from core.agent_chat import AgentChatService
        with tempfile.TemporaryDirectory() as folder:
            service = MagicMock()
            service.notion.configuration.return_value = {"workspace_id": WORKSPACE, "agent_id": AGENT}
            chat = AgentChatService(service, Path(folder) / "conversation.json")
            chat._run_notion_tool_turn = MagicMock()
            cid = chat.store.get_active()["id"]
            chat._is_turn_cancelled = lambda *a: False
            service.notion_tools.availability.return_value = ("blocked", "x")
            chat._set_turn_progress = MagicMock()
            service.notion.get.return_value = {"status": "completed", "result": "ok"}
            service.notion.TERMINAL = {"completed", "failed", "cancelled", "blocked"}
            chat._publish_run_update = MagicMock(return_value=True)
            chat._finish_turn = MagicMock()
            chat._run_notion_turn(cid, "m", "test dosyasını oku")
            chat._run_notion_tool_turn.assert_not_called()       # not ready: plain cloud chat
            service.notion_tools.availability.return_value = ("ready", "x")
            chat._run_notion_turn(cid, "m", "Merhaba")
            chat._run_notion_tool_turn.assert_not_called()       # no explicit test-file request
            chat._run_notion_turn(cid, "m", "test dosyasını oku")
            chat._run_notion_tool_turn.assert_called_once()

    def test_cancel_revokes_local_tools_and_ipc_and_ui_are_wired(self):
        from core.agent_chat import AgentChatService
        with tempfile.TemporaryDirectory() as folder:
            service = MagicMock()
            chat = AgentChatService(service, Path(folder) / "conversation.json")
            chat._active_turn = {"status": "running", "agent": "notion", "conversation_id": chat.store.get_active()["id"],
                                 "message_id": "m", "turn_id": "t"}
            chat.cancel_active()
            service.notion_tools.stop_all.assert_called_once()
        root = Path(__file__).resolve().parents[1]
        self.assertIn('action == "notion_tool_decide"', (root / "main.py").read_text(encoding="utf-8"))
        import gui
        self.assertTrue(callable(getattr(gui.Api, "notion_tool_decide", None)))
        # Prototype backend remains testable, but no approval surface ships.
        self.assertNotIn('syncNotionTools(', gui._HTML)
        self.assertNotIn('api.notion_tool_decide(', gui._HTML)



class OptInCommandTests(unittest.TestCase):
    def test_main_chat_opt_in_respects_existing_enabled_false(self):
        from unittest.mock import patch
        from scripts import notion_worker_acceptance as driver
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(driver, "profile_root", return_value=Path(folder)), \
                patch.object(driver, "owned_context", return_value=(None, {}, {}, KEY)):
            atomic_write_json(Path(folder) / "worker-bridge.json", {"mode": "readonly-fixture", "enabled": False})
            self.assertEqual(driver.set_main_chat(True)["status"], "blocked")
            self.assertNotIn("main_chat", load_json(Path(folder) / "worker-bridge.json", {}))
            atomic_write_json(Path(folder) / "worker-bridge.json", {"mode": "readonly-fixture"})
            self.assertEqual(driver.set_main_chat(True)["status"], "enabled")
            self.assertIs(load_json(Path(folder) / "worker-bridge.json", {})["main_chat"], True)
            self.assertEqual(driver.set_main_chat(False)["status"], "disabled")
            self.assertIs(load_json(Path(folder) / "worker-bridge.json", {})["main_chat"], False)


if __name__ == "__main__":
    unittest.main()
