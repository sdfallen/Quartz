"""
tests/test_cooperative_shutdown.py
Unit and integration tests for cooperative shutdown, dispatch admission,
component cleanup isolation, and structured receipt verification.
"""

import json
import socket
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.shutdown import ShutdownCoordinator, ShutdownReceipt, get_shutdown_coordinator, reset_shutdown_coordinator
from main import IPCServer


class TestCooperativeShutdown(unittest.TestCase):

    def setUp(self):
        reset_shutdown_coordinator()
        self.coordinator = ShutdownCoordinator()

    def tearDown(self):
        reset_shutdown_coordinator()

    def test_lazy_services_not_instantiated_on_shutdown(self):
        """stop() must not instantiate services that were not already created."""
        server = IPCServer(assistant=None, coordinator=self.coordinator)
        self.assertIsNone(getattr(server, "_diagnostics", None))
        self.assertIsNone(server._agent_chat)
        self.assertIsNone(server._agent_center)
        self.assertIsNone(server._assistant_instance)

        receipt = server.stop()

        self.assertEqual(receipt["status"], "confirmed")
        self.assertEqual(receipt["components"]["diagnostics"]["status"], "skipped")
        self.assertEqual(receipt["components"]["agent_chat"]["status"], "skipped")
        self.assertEqual(receipt["components"]["agent_center"]["status"], "skipped")
        self.assertEqual(receipt["components"]["assistant"]["status"], "skipped")
        self.assertEqual(receipt["components"]["mobile_gateway"]["status"], "skipped")

        # Verify nothing was instantiated as a side-effect
        self.assertIsNone(getattr(server, "_diagnostics", None))
        self.assertIsNone(server._agent_chat)
        self.assertIsNone(server._agent_center)
        self.assertIsNone(server._assistant_instance)

    def test_getter_refuses_instantiation_once_admission_closed(self):
        """Lazy getters must return None and not instantiate when admission is closed."""
        server = IPCServer(assistant=None, coordinator=self.coordinator)
        self.coordinator.close_admission()
        self.assertTrue(self.coordinator.is_admission_closed())

        # Attempting to access lazy properties should return None without instantiating
        self.assertIsNone(server._get_diagnostics())
        self.assertIsNone(server._assistant)
        self.assertIsNone(server._get_agent_center())
        self.assertIsNone(server._get_agent_chat())

        self.assertIsNone(getattr(server, "_diagnostics", None))
        self.assertIsNone(server._agent_chat)
        self.assertIsNone(server._agent_center)
        self.assertIsNone(server._assistant_instance)

    def test_getter_race_during_and_after_shutdown(self):
        """Concurrent calls to service getters while admission is closed or shutting down must not create singletons."""
        server = IPCServer(assistant=None, coordinator=self.coordinator)
        self.coordinator.close_admission()
        results = []

        def worker():
            for _ in range(50):
                res = server._assistant
                results.append(res)
                time.sleep(0.001)

        t = threading.Thread(target=worker)
        t.start()
        time.sleep(0.005)
        server.stop()
        t.join()

        self.assertIsNone(server._assistant_instance)
        self.assertTrue(all(r is None for r in results))

    def test_component_cleanup_isolation_on_error(self):
        """A failure in one component must not prevent other components from cleaning up."""
        server = IPCServer(assistant=None, coordinator=self.coordinator)

        mock_diag = MagicMock()
        mock_diag.shutdown.side_effect = RuntimeError("Diagnostics database locked")
        server._diagnostics = mock_diag

        mock_center = MagicMock()
        mock_center.shutdown.return_value = None
        server._agent_center = mock_center

        mock_ast = MagicMock()
        mock_ast.shutdown.return_value = None
        server._assistant_instance = mock_ast

        mock_socket = MagicMock()
        server._server = mock_socket

        receipt = server.stop()

        # Diagnostics failed
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["components"]["diagnostics"]["status"], "failed")
        self.assertIn("RuntimeError", receipt["components"]["diagnostics"]["error"])

        # But agent_center, assistant, and socket were STILL properly cleaned up!
        self.assertEqual(receipt["components"]["agent_center"]["status"], "confirmed")
        mock_center.shutdown.assert_called_once()

        self.assertEqual(receipt["components"]["assistant"]["status"], "confirmed")
        mock_ast.shutdown.assert_called_once()

        self.assertEqual(receipt["components"]["ipc_socket"]["status"], "confirmed")
        mock_socket.close.assert_called_once()

        # Cleaned references reset to None
        self.assertIsNone(server._diagnostics)
        self.assertIsNone(server._agent_center)
        self.assertIsNone(server._assistant_instance)
        self.assertIsNone(server._server)

    def test_stuck_component_times_out_without_freezing(self):
        """A hanging component must be bounded by timeout and reported as pending without hanging indefinitely."""
        coord = ShutdownCoordinator()

        def hanging_component():
            time.sleep(5.0)

        components = {
            "fast_component": lambda: True,
            "stuck_component": hanging_component,
        }

        start = time.monotonic()
        receipt = coord.execute_shutdown(components, timeout_per_component=0.2)
        elapsed = time.monotonic() - start

        # Must have completed in ~0.2s, not 5.0s
        self.assertLess(elapsed, 1.5)
        self.assertEqual(receipt["status"], "pending")
        self.assertEqual(receipt["components"]["fast_component"]["status"], "confirmed")
        self.assertEqual(receipt["components"]["stuck_component"]["status"], "pending")
        self.assertIn("TimeoutExpired", receipt["components"]["stuck_component"]["error"])

    def test_idempotent_shutdown_returns_cached_receipt(self):
        """Calling stop() repeatedly must return the identical receipt without repeated execution."""
        server = IPCServer(assistant=None, coordinator=self.coordinator)
        mock_center = MagicMock()
        server._agent_center = mock_center

        receipt1 = server.stop()
        receipt2 = server.stop()

        self.assertEqual(receipt1, receipt2)
        self.assertEqual(mock_center.shutdown.call_count, 1)

    def test_dispatch_admission_closed_rejects_new_requests(self):
        """New dispatches are rejected once admission is closed, but shutdown action is accepted."""
        server = IPCServer(assistant=None, coordinator=self.coordinator)

        with patch("main.authorized", return_value=True):
            # Normal dispatch works when open
            with patch.object(server, "_dispatch_action", return_value={"status": "ok", "data": "pong"}):
                resp = server._dispatch({"action": "ping", "auth": "test"})
                self.assertEqual(resp["status"], "ok")

            # Close admission
            self.coordinator.close_admission()

            # Normal dispatch rejected
            resp2 = server._dispatch({"action": "ping", "auth": "test"})
            self.assertEqual(resp2["status"], "error")
            self.assertEqual(resp2["error_code"], "SHUTDOWN_IN_PROGRESS")
            self.assertIn("shutting down", resp2["data"])

            # Shutdown action is still handled cleanly
            resp_shutdown = server._dispatch({"action": "shutdown", "auth": "test"})
            self.assertEqual(resp_shutdown["status"], "ok")
            self.assertIn("receipt", resp_shutdown)
            self.assertEqual(resp_shutdown["receipt"]["status"], "confirmed")

    def test_ipc_socket_shutdown_and_exit(self):
        """An actual socket connection sending shutdown receives receipt and listener stops without SIGTERM."""
        # Find a free port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        with patch("main.IPC_PORT", port), patch("main.authorized", return_value=True):
            server = IPCServer(assistant=None, coordinator=self.coordinator)

            # Start server in thread
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            time.sleep(0.1)

            # Connect and send shutdown request
            client = socket.create_connection(("127.0.0.1", port), timeout=5)
            client.sendall(json.dumps({"action": "shutdown", "auth": "test"}).encode() + b"\n")

            raw = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                raw += chunk
                if raw.endswith(b"\n"):
                    break
            client.close()

            response = json.loads(raw.decode().strip())
            self.assertEqual(response["status"], "ok")
            self.assertEqual(response["data"], "Shutting down")
            self.assertIn("receipt", response)
            self.assertEqual(response["receipt"]["status"], "confirmed")

            # Server thread must terminate cleanly because socket was closed
            server_thread.join(timeout=3.0)
            self.assertFalse(server_thread.is_alive())

    def test_mobile_gateway_and_legacy_assistant_cleaned_if_present(self):
        """Instantiated MobileGateway and GitHubAssistant are stopped properly."""
        server = IPCServer(assistant=None, coordinator=self.coordinator)
        mock_ast = MagicMock()
        server._assistant_instance = mock_ast

        mock_mg = MagicMock()
        with patch("main._mobile_gateway", mock_mg):
            receipt = server.stop()
            self.assertEqual(receipt["status"], "confirmed")
            self.assertEqual(receipt["components"]["assistant"]["status"], "confirmed")
            self.assertEqual(receipt["components"]["mobile_gateway"]["status"], "confirmed")
            mock_ast.shutdown.assert_called_once()
            mock_mg.stop.assert_called_once()

    def test_runtime_unconfirmed_cleanup_fails_receipt(self):
        """If a runtime reports unconfirmed cleanup, the overall receipt is failed."""
        server = IPCServer(assistant=None, coordinator=self.coordinator)
        mock_center = MagicMock()
        mock_center.shutdown.side_effect = RuntimeError("Owned runtime cleanup is not confirmed")
        server._agent_center = mock_center

        receipt = server.stop()
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["components"]["agent_center"]["status"], "failed")
        self.assertIn("Owned runtime cleanup is not confirmed", receipt["errors"][0])


if __name__ == "__main__":
    unittest.main()
