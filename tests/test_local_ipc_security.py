import json
import socket
import threading
import unittest
from unittest.mock import MagicMock, patch

import gui
from main import IPCServer
from core.local_ipc import request_token, authorized


class LocalIPCSecurityTests(unittest.TestCase):
    def test_capability_validation_and_no_desktop_route(self):
        assistant = MagicMock()
        server = IPCServer(assistant)
        for token in (None, True, "wrong", "şifre", ""):
            for action in ("chat", "chat_send", "agent_center_dispatch", "safe_mode", "set_tool_source", "shutdown"):
                with self.subTest(token=token, action=action):
                    response = server._dispatch({"action": action, "auth": token,
                                                 "data": {"permission_level":"full", "confirm_write":True}})
                    self.assertEqual(response["status"], "error")
        assistant.chat.assert_not_called()
        assistant.set_safe_mode.assert_not_called()
        self.assertTrue(authorized(request_token()))
        for name in ("desktop_operator_start", "desktop_focus", "desktop_act", "desktop_observe"):
            response = server._dispatch({"action": name, "auth": request_token(),
                                         "data": {"confirmed": True, "handle": 1}})
            self.assertEqual(response["status"], "error")
        self.assertIsNone(server._agent_center)

    def test_gui_socket_path_authenticates_and_external_client_is_denied(self):
        assistant = MagicMock()
        assistant.chat.return_value = "sade yanıt"
        assistant.drain_ui_events.return_value = []
        server = IPCServer(assistant)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0)); listener.listen(2); listener.settimeout(10)
        def serve():
            for _ in range(2):
                conn, addr = listener.accept()
                server._handle(conn, addr)
        worker = threading.Thread(target=serve, daemon=True); worker.start()
        try:
            with patch.object(gui, "IPC_PORT", listener.getsockname()[1]):
                response = gui.ipc_send("chat", "merhaba")
                self.assertEqual(response["data"], "sade yanıt")
            with socket.create_connection(listener.getsockname(), timeout=10) as client:
                client.sendall(b'{"action":"chat","data":"unauthorized command"}\n')
                response = json.loads(client.recv(65536))
                self.assertEqual(response["status"], "error")
                self.assertNotIn(request_token(), json.dumps(response))
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
            assistant.chat.assert_called_once_with("merhaba")
        finally:
            listener.close()
