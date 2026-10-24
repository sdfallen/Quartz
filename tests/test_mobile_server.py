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


class MobileGatewayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patch = patch.object(
            mobile_server, "ACCESS_FILE", Path(self.directory.name) / "access.json")
        self.patch.start()
        self.gateway = mobile_server.MobileGateway(FakeAssistant(), port=0)
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


if __name__ == "__main__":
    unittest.main()
