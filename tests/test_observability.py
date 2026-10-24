import logging
import unittest
from logging.handlers import RotatingFileHandler

from logger import RequestIdFilter, get_logger, request_context
from main import IPCServer
from core.local_ipc import request_token


class FakeAssistant:
    def health_status(self):
        return {"llm": {"status": "configured"}, "mcp": {"status": "ok"}}

    def chat(self, message):
        return f"echo:{message}"


class ObservabilityTests(unittest.TestCase):
    def test_request_id_is_added_to_log_records(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "x", (), None)
        with request_context("req-test-123"):
            RequestIdFilter().filter(record)
        self.assertEqual(record.request_id, "req-test-123")

    def test_health_endpoint_contains_components_and_request_id(self):
        server = IPCServer(FakeAssistant())
        response = server._dispatch({"action": "health", "request_id": "health-1", "auth": request_token()})
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["request_id"], "health-1")
        self.assertEqual(response["data"]["backend"], "ok")
        self.assertIn("components", response["data"])

    def test_chat_response_carries_request_id(self):
        server = IPCServer(FakeAssistant())
        response = server._dispatch({
            "action": "chat", "data": "hello", "request_id": "chat-1", "auth": request_token()})
        self.assertEqual(response["data"], "echo:hello")
        self.assertEqual(response["request_id"], "chat-1")

    def test_file_logging_uses_rotation(self):
        quartz_logger = get_logger("test.rotation")
        handlers = [h for h in quartz_logger.handlers
                    if isinstance(h, RotatingFileHandler)]
        self.assertEqual(len(handlers), 1)
        self.assertGreater(handlers[0].maxBytes, 0)
        self.assertGreater(handlers[0].backupCount, 0)


if __name__ == "__main__":
    unittest.main()
