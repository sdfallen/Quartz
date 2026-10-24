import re
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import assistant as assistant_module
from core.task_engine import TaskEngine
from core.continuity_engine import ContinuityEngine
import tempfile
from pathlib import Path


class FakeMemory:
    def increment_messages(self): pass
    def get_ai_context(self): return "[TEST MEMORY]"
    def track_command(self, _name): pass
    def track_app_open(self, _name): pass
    def track_song_play(self, _name): pass
    def track_site_visit(self, _name): pass
    def get_preference(self, _key, default=None): return default
    def set_preference(self, _key, _value): pass


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        data = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ]
        return {key: value for key, value in data.items()
                if not exclude_none or value is not None}


def tool_call(name, arguments="{}", call_id="call-1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class FakeCompletions:
    def __init__(self, messages, delay=0):
        self.messages = list(messages)
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            message = self.messages.pop(0) if self.messages else FakeMessage("ok")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        finally:
            with self.lock:
                self.active -= 1


class FakeClient:
    def __init__(self, messages, delay=0):
        self.completions = FakeCompletions(messages, delay)
        self.chat = SimpleNamespace(completions=self.completions)


PROVIDER = {
    "name": "test", "model": "fake-model",
    "api_key": "unused", "base_url": "http://unused",
}


class AssistantFlowTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(assistant_module, "memory", FakeMemory()),
            patch.object(assistant_module, "_save_history", lambda _history: None),
            patch.object(assistant_module, "_get_upgrade_manager", lambda: None),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def make_assistant(self, messages, delay=0):
        client = FakeClient(messages, delay)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        instance = assistant_module.GitHubAssistant(
            client=client, provider=PROVIDER, history=[],
            task_engine=TaskEngine(root / "tasks.json"),
            continuity_engine=ContinuityEngine(
                root / "operation.json", root / "workflows.json"))
        return instance, client

    def test_plain_chat_uses_fake_llm(self):
        quartz, _ = self.make_assistant([FakeMessage("Merhaba dostum")])
        self.assertEqual(quartz.chat("selam"), "Merhaba dostum")

    def test_structured_safe_tool_runs_and_gets_followup(self):
        first = FakeMessage(tool_calls=[tool_call("get_volume")])
        quartz, _ = self.make_assistant([first, FakeMessage("Ses seviyesi okundu")])
        with patch.dict(assistant_module.TOOLS, {"get_volume": lambda: "50%"}):
            self.assertEqual(quartz.chat("ses kaç"), "Ses seviyesi okundu")

    def test_dangerous_text_tool_waits_for_valid_confirmation(self):
        quartz, _ = self.make_assistant([
            FakeMessage('write_file("safe.txt", "hello")')])
        calls = []
        with patch.dict(
            assistant_module.TOOLS,
            {"write_file": lambda path, content: calls.append((path, content)) or "ok"},
        ):
            response = quartz.chat("dosyaya yaz")
            self.assertEqual(calls, [])
            code = re.search(r"onayla ([A-F0-9]{6})", response).group(1)
            self.assertIn("Geçerli", quartz.chat("onayla 000000"))
            self.assertEqual(calls, [])
            self.assertIn("ok", quartz.chat(f"onayla {code}"))
            self.assertEqual(calls, [("safe.txt", "hello")])

    def test_chat_lock_serializes_parallel_requests(self):
        quartz, client = self.make_assistant(
            [FakeMessage("bir"), FakeMessage("iki")], delay=0.04)
        threads = [threading.Thread(target=quartz.chat, args=(str(i),)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(client.completions.max_active, 1)

    def test_safe_mode_blocks_side_effect_tool(self):
        quartz, _ = self.make_assistant([FakeMessage('smart_open("code")')])
        quartz.set_safe_mode(True)
        calls = []
        with patch.dict(
            assistant_module.TOOLS,
            {"smart_open": lambda app: calls.append(app) or "opened"},
        ):
            response = quartz.chat("code aç")
        self.assertIn("Güvenli Mod", response)
        self.assertEqual(calls, [])
        self.assertEqual(quartz.drain_ui_events()[0]["type"], "blocked")

    def test_confirmation_emits_structured_ui_event(self):
        quartz, _ = self.make_assistant([
            FakeMessage('write_file("safe.txt", "hello")')])
        with patch.dict(
            assistant_module.TOOLS,
            {"write_file": lambda path, content: "ok"},
        ):
            quartz.chat("dosyaya yaz")
        event = quartz.drain_ui_events()[0]
        self.assertEqual(event["type"], "confirmation")
        self.assertEqual(event["tool"], "write_file")
        self.assertRegex(event["code"], r"^[A-F0-9]{6}$")

    def test_multiple_tools_are_tracked_as_a_task(self):
        first = FakeMessage(tool_calls=[
            tool_call("get_volume", call_id="one"),
            tool_call("get_system_info", call_id="two"),
        ])
        with tempfile.TemporaryDirectory() as directory:
            engine = TaskEngine(Path(directory) / "tasks.json")
            client = FakeClient([first, FakeMessage("Görev tamamlandı")])
            quartz = assistant_module.GitHubAssistant(
                client=client, provider=PROVIDER, history=[], task_engine=engine,
                continuity_engine=ContinuityEngine(
                    Path(directory) / "operation.json",
                    Path(directory) / "workflows.json"))
            with patch.dict(assistant_module.TOOLS, {
                "get_volume": lambda: "50%",
                "get_system_info": lambda: "healthy",
            }):
                response = quartz.chat("sesi ve sistemi kontrol et")
            self.assertEqual(response, "Görev tamamlandı")
            task = engine.list()[0]
            self.assertEqual(task["status"], "completed")
            self.assertEqual([s["status"] for s in task["steps"]],
                             ["completed", "completed"])
            event_types = [event["type"] for event in quartz.drain_ui_events()]
            self.assertIn("task_created", event_types)
            self.assertIn("task_updated", event_types)

    def test_agent_keeps_calling_tools_until_final_result(self):
        messages = [
            FakeMessage(tool_calls=[tool_call(
                "smart_open", '{"target":"steam"}', "open")]),
            FakeMessage(tool_calls=[tool_call(
                "get_volume", "{}", "check")]),
            FakeMessage("Steam açıldı ve durum doğrulandı"),
        ]
        quartz, _ = self.make_assistant(messages)
        calls = []
        with patch.dict(assistant_module.TOOLS, {
            "smart_open": lambda target: calls.append(("open", target)) or "opened",
            "get_volume": lambda: calls.append(("volume", None)) or "50%",
        }):
            result = quartz.chat("Steam'i aç ve kontrol et")
        self.assertEqual(result, "Steam açıldı ve durum doğrulandı")
        self.assertEqual(calls, [("open", "steam"), ("volume", None)])
        self.assertEqual(len(quartz._continuity.active()["actions"]), 2)

    def test_next_message_receives_active_application_context(self):
        first = FakeMessage(tool_calls=[tool_call(
            "smart_open", '{"target":"steam"}', "open")])
        quartz, client = self.make_assistant([
            first, FakeMessage("Steam açıldı"), FakeMessage("Kütüphane açılıyor")])
        with patch.dict(assistant_module.TOOLS, {
            "smart_open": lambda target: "opened",
        }):
            quartz.chat("Steam'i aç")
            quartz.chat("Steam penceresinde ne görüyorsun?")
        second_request = client.completions.requests[-1]
        system = second_request["messages"][0]["content"]
        self.assertIn("ACTIVE OPERATION CONTEXT", system)
        self.assertIn("active_app: steam", system)
        self.assertIn("Steam penceresinde ne görüyorsun?", system)

    def test_approval_resumes_remaining_agent_plan(self):
        first = FakeMessage(tool_calls=[tool_call(
            "write_file", '{"path":"safe.txt","content":"ok"}', "write")])
        after_approval = FakeMessage(tool_calls=[tool_call(
            "get_volume", "{}", "verify")])
        quartz, _ = self.make_assistant([
            first, after_approval, FakeMessage("Plan tamamlandı")])
        calls = []
        with patch.dict(assistant_module.TOOLS, {
            "write_file": lambda path, content: calls.append("write") or "written",
            "get_volume": lambda: calls.append("verify") or "50%",
        }):
            pending = quartz.chat("dosyaya yaz ve doğrula")
            code = re.search(r"onayla ([A-F0-9]{6})", pending).group(1)
            result = quartz.chat(f"onayla {code}")
        self.assertEqual(result, "Plan tamamlandı")
        self.assertEqual(calls, ["write", "verify"])


    def test_steam_followup_uses_direct_install_tool_with_confirmation(self):
        quartz, _ = self.make_assistant([])
        quartz._continuity.record_tool(
            "Open Steam", "smart_open", {"args": ["steam"]}, "opened")
        installed = []
        with patch.dict(assistant_module.TOOLS, {
            "steam_install_game": lambda game_name: installed.append(game_name) or "dialog",
        }):
            pending = quartz.chat("Cyberpunk 2077'yi bul ve indirmeye koy")
            self.assertEqual(installed, [])
            code = re.search(r"onayla ([A-F0-9]{6})", pending).group(1)
            result = quartz.chat(f"onayla {code}")
        self.assertEqual(result, "[steam_install_game] dialog")
        self.assertEqual(installed, ["Cyberpunk 2077"])

    def test_steam_library_followup_bypasses_vision_clicking(self):
        quartz, _ = self.make_assistant([])
        quartz._continuity.record_tool(
            "Open Steam", "smart_open", {"args": ["steam"]}, "opened")
        calls = []
        with patch.dict(assistant_module.TOOLS, {
            "steam_open_library": lambda: calls.append("library") or "opened",
        }):
            result = quartz.chat("Şimdi kütüphaneme gir")
        self.assertEqual(result, "opened")
        self.assertEqual(calls, ["library"])


if __name__ == "__main__":
    unittest.main()
