import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import mobile_server


class FakeAssistant:
    def health_status(self):
        return {"llm": {"provider": "test"}, "safe_mode": True}

    def list_tasks(self):
        return []

    def chat(self, message):
        return "yanıt: " + message

    def drain_ui_events(self):
        return []


class FakeStore:
    def __init__(self):
        self.messages = [
            {"id": "u1", "role": "user", "sender": "user", "sequence": 1, "content": "durum?"},
            {"id": "a1", "role": "assistant", "sender": "claude", "sequence": 2, "content": "Plan hazır.",
             "metadata": {"team": True, "team_step": 1}},
            {"id": "a2", "role": "assistant", "sender": "codex", "sequence": 3, "content": "Test kırıldı.",
             "metadata": {"status": "failed", "error": "boom"}},
        ]

    def get_active(self):
        return {"id": "c1", "title": "Teslim", "agent": "collaboration", "project_id": "p1",
                "messages": list(self.messages), "models": {"codex": {"model": "gpt-x", "effort": "low"}}}

    def list(self):
        return [{"id": "c0", "title": "Eski", "updated_at": 1}, {"id": "c1", "title": "Teslim", "updated_at": 5}]


class FakeProjects:
    def list(self):
        return [{"id": "p1", "name": "Teslim", "path": "C:/x"}]


class FakeService:
    projects = FakeProjects()


class FakeChat:
    def __init__(self):
        self.store = FakeStore()
        self.agent_service = FakeService()
        self.actions = []
        self.sent = []
        self.cancelled = 0
        self.active = False

    def poll_active(self):
        return {"active": self.active, "status": "running" if self.active else None}

    def send_message(self, text, **kwargs):
        self.sent.append((text, kwargs))
        return {"conversation_id": "c1"}

    def cancel_active(self):
        self.cancelled += 1
        return {"stopped": True}

    def status(self):
        conv = self.store.get_active()
        conv["messages"].append({"id": "e1", "role": "assistant", "sender": "claude", "sequence": 9, "content": "x",
                                 "metadata": {"host_evidence": {"files_changed": ["app.py"], "source_validation": {"status": "FAILED"}}}})
        conv["messages"].append({"id": "e2", "role": "assistant", "sender": "codex", "sequence": 10, "content": "y",
                                 "metadata": {"files_changed": ["claimed.py"]}})
        return {"active_conversation": conv,
                "models": {"codex": {"default_model": "gpt-x", "efforts": ["low", "high"], "models": [{"id": "gpt-x"}, {"id": "gpt-y"}]}},
                "environment_health": {"status": "warn", "checks": [{"id": "squad", "status": "warn", "summary_tr": "Squad bağlı değil", "fix_tr": "Yeniden dene"},
                                                                     {"id": "ok", "status": "ok", "summary_tr": "Tamam"}]}}

    def new_conversation(self, agent="antigravity", **_):
        self.actions.append(("new", agent)); return {"id": "c2"}

    def select_conversation(self, cid):
        self.actions.append(("select", cid)); return {"id": cid}

    def set_agent(self, cid, agent):
        self.actions.append(("mode", cid, agent))

    def set_agent_model(self, cid, agent, model=None, effort=None):
        self.actions.append(("model", cid, agent, model, effort)); return {"selection": {"model": model, "effort": effort}}

    def switch_project(self, pid):
        self.actions.append(("project", pid)); return {"id": "c3"}

    def memory_list(self):
        return [{"id": "m1", "text": "Benim adım Ali", "created_at": 1}]

    def memory_forget(self, item_id):
        self.actions.append(("forget", item_id)); return {"removed": True, "items": []}


class MobileGatewayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patch = patch.object(
            mobile_server, "ACCESS_FILE", Path(self.directory.name) / "access.json")
        self.patch.start()
        self.chat = FakeChat()
        self.gateway = mobile_server.MobileGateway(FakeAssistant(), port=0, agent_chat=lambda: self.chat)
        self.thread = threading.Thread(target=self.gateway.start, daemon=True)
        self.thread.start()
        deadline = time.time() + 3
        while self.gateway._server is None and time.time() < deadline:
            time.sleep(.01)
        self.port = self.gateway._server.server_address[1]

    def tearDown(self):
        self.gateway.stop()
        self.patch.stop()
        self.directory.cleanup()

    def request(self, path, *, token="", payload=None):
        headers = {"Authorization": "Bearer " + token}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        return urllib.request.urlopen(
            urllib.request.Request(
                f"http://127.0.0.1:{self.port}{path}",
                headers=headers, data=data), timeout=3)

    def test_rejects_request_without_device_token(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/health")
        self.assertEqual(error.exception.code, 401)
        error.exception.close()

    def test_authenticated_mobile_chat_reaches_assistant(self):
        with self.request(
            "/api/chat", token=self.gateway.token,
            payload={"message": "merhaba"}) as response:
            body = json.loads(response.read())
            self.assertEqual(body["data"], "yanıt: merhaba")

    def test_gateway_binds_to_loopback_only(self):
        self.assertEqual(self.gateway.host, "127.0.0.1")
        self.assertGreaterEqual(len(self.gateway.token), 32)

    def test_mobile_login_has_visible_connection_flow(self):
        with self.request("/") as response:
            page = response.read().decode("utf-8")
        self.assertIn("async function connect()", page)
        self.assertIn("button.textContent='BAĞLANIYOR…'", page)
        self.assertIn("$('loginError').textContent=e.message", page)
        self.assertIn("$('token').onkeydown", page)


    def test_team_state_needs_the_device_key_and_names_the_personas(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/state")
        self.assertEqual(error.exception.code, 401)
        error.exception.close()
        with self.request("/api/state", token=self.gateway.token) as response:
            body = json.loads(response.read())
        self.assertEqual(body["conversation"]["title"], "Teslim")
        self.assertEqual(body["last_seq"], 3)
        self.assertEqual([m["persona"] for m in body["messages"]], ["", "Fatum", "Fides"])
        self.assertEqual([m["failed"] for m in body["messages"]], [False, False, True])
        with self.request("/api/state?after=2", token=self.gateway.token) as response:
            self.assertEqual([m["id"] for m in json.loads(response.read())["messages"]], ["a2"])

    def test_long_poll_returns_when_a_new_message_arrives(self):
        def later():
            time.sleep(.5)
            self.chat.store.messages.append({"id": "a3", "role": "assistant", "sender": "antigravity",
                                             "sequence": 4, "content": "Risk yok."})
        threading.Thread(target=later, daemon=True).start()
        started = time.time()
        body = self.gateway.wait_snapshot(after=3, wait=5)
        self.assertLess(time.time() - started, 4)
        self.assertEqual([(m["id"], m["persona"]) for m in body["messages"]], [("a3", "Eos")])

    def test_phone_messages_are_read_only_and_stop_reaches_the_team(self):
        with self.request("/api/send", token=self.gateway.token, payload={"message": "özetle"}) as response:
            self.assertTrue(json.loads(response.read())["accepted"])
        text, kwargs = self.chat.sent[0]
        self.assertEqual(text, "özetle")
        for flag in ("write", "confirm_write", "full_access"):
            self.assertNotIn(flag, kwargs)
        with self.request("/api/stop", token=self.gateway.token, payload={}) as response:
            self.assertEqual(json.loads(response.read())["data"], {"stopped": True})
        self.assertEqual(self.chat.cancelled, 1)

    def test_pairing_code_is_single_use_and_dies_after_wrong_guesses(self):
        code, expires_in = self.gateway.pairing_code()
        self.assertEqual(len(code), 6)
        self.assertGreater(expires_in, 200)
        self.assertEqual(self.gateway.pairing_code()[0], code)  # stable while valid
        with self.request("/api/pair", payload={"code": code}) as response:
            self.assertEqual(json.loads(response.read())["token"], self.gateway.token)
        self.assertIsNone(self.gateway.redeem_pairing(code))  # used up
        fresh, _ = self.gateway.pairing_code()
        self.assertNotEqual(fresh, None)
        wrong = "000000" if fresh != "000000" else "111111"
        for _ in range(mobile_server.PAIR_MAX_FAILURES):
            self.assertIsNone(self.gateway.redeem_pairing(wrong))
        self.assertIsNone(self.gateway.redeem_pairing(fresh))  # burnt by the guesses

    def test_wrong_pairing_code_is_refused(self):
        self.gateway.pairing_code()
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/pair", payload={"code": "12345x"})
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_overview_lists_agents_health_and_only_host_evidence(self):
        with self.request("/api/overview", token=self.gateway.token) as response:
            body = json.loads(response.read())
        self.assertEqual(body["mode"], "collaboration")
        self.assertEqual(body["agents"]["codex"]["persona"], "Fides")
        self.assertEqual(body["agents"]["codex"]["models"], ["gpt-x", "gpt-y"])
        self.assertEqual(body["project"]["name"], "Teslim")
        self.assertEqual([w["title"] for w in body["health"]["warnings"]], ["Squad bağlı değil"])
        self.assertEqual([c["file"] for c in body["evidence"]["changes"]], ["app.py"])  # agent claims never listed
        self.assertEqual(body["evidence"]["checks"][0]["tone"], "fail")

    def test_conversations_newest_first_and_actions_reach_the_service(self):
        with self.request("/api/conversations", token=self.gateway.token) as response:
            body = json.loads(response.read())
        self.assertEqual([c["id"] for c in body["items"]], ["c1", "c0"])
        for path, payload in (("new", {"agent": "collaboration"}), ("select", {"conversation_id": "c0"}),
                              ("mode", {"agent": "claude"}), ("model", {"agent": "codex", "effort": "high"}),
                              ("project", {"project_id": "p1"})):
            with self.request("/api/act/" + path, token=self.gateway.token, payload=payload) as response:
                self.assertEqual(response.status, 200)
        self.assertEqual([a[0] for a in self.chat.actions], ["new", "select", "mode", "model", "project"])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/act/delete", token=self.gateway.token, payload={})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_memory_is_listed_and_forgettable_from_the_phone(self):
        with self.request("/api/memory", token=self.gateway.token) as response:
            self.assertEqual(json.loads(response.read())["items"][0]["text"], "Benim adım Ali")
        with self.request("/api/act/forget", token=self.gateway.token, payload={"id": "m1"}) as response:
            self.assertTrue(json.loads(response.read())["removed"])
        self.assertIn(("forget", "m1"), self.chat.actions)

    def test_voice_answers_fast_or_hands_the_question_to_the_team(self):
        class Front:
            def __init__(self, route): self.route, self.seen = route, None
            def answer(self, text, state):
                self.seen = state
                return {"route": "answered", "reply": "Fides'in testi başarısız."} if self.route == "answered" else {"route": "team", "reason": "team_only"}
        fast = Front("answered")
        result = self.gateway.voice("Ne oldu?", front=fast)
        self.assertEqual((result["route"], result["after"]), ("answered", 3))
        self.assertEqual(self.chat.sent, [])  # nothing reached the team
        result = self.gateway.voice("Güvenli mi?", front=Front("team"))
        self.assertEqual(result["route"], "team")
        self.assertEqual(self.chat.sent[0][0], "Güvenli mi?")
        for flag in ("write", "confirm_write", "full_access"):
            self.assertNotIn(flag, self.chat.sent[0][1])

    def test_device_key_is_never_read_from_the_address(self):
        self.assertNotIn("query.get('token')", mobile_server._HTML)
        self.assertNotIn("QUARTZ", mobile_server._HTML)


if __name__ == "__main__":
    unittest.main()
