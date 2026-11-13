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
        return {"id": "c1", "title": "Teslim", "messages": list(self.messages)}


class FakeChat:
    def __init__(self):
        self.store = FakeStore()
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

    def test_device_key_is_never_read_from_the_address(self):
        self.assertNotIn("query.get('token')", mobile_server._HTML)
        self.assertNotIn("QUARTZ", mobile_server._HTML)


if __name__ == "__main__":
    unittest.main()
