import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from core.confirmation_manager import ConfirmationManager
from core.history_manager import HistoryStore
from core.plugin_loader import register_plugin_tools, unregister_plugin_tools
from core.rollback_manager import RollbackManager
from core.sandbox import PathSandbox, SandboxViolation
from core.tool_registry import ToolRegistry
from core.task_engine import TaskEngine


class CoreArchitectureTests(unittest.TestCase):
    def test_registry_validates_and_builds_schema(self):
        registry = ToolRegistry()
        registry.register("echo", lambda value: value, risk="read")
        function, args, kwargs = registry.validate("echo", ["hello"])
        self.assertEqual(function(*args, **kwargs), "hello")
        self.assertEqual(registry.schemas()[0]["function"]["name"], "echo")

    def test_plugin_tools_register_and_unregister_by_source(self):
        module = ModuleType("demo")
        module.PLUGIN_INFO = {
            "name": "Demo", "commands": ["hello"],
            "risks": {"hello": "read"},
        }
        module.hello = lambda name="world": f"hello {name}"
        registry = ToolRegistry()
        self.assertEqual(register_plugin_tools(registry, "demo", module), ["hello"])
        self.assertEqual(registry.function("hello")(), "hello world")
        unregister_plugin_tools(registry, "demo")
        self.assertIsNone(registry.function("hello"))

    def test_plugin_source_can_be_disabled(self):
        module = ModuleType("switchable")
        module.PLUGIN_INFO = {"commands": ["hello"]}
        module.hello = lambda: "hello"
        registry = ToolRegistry()
        register_plugin_tools(registry, "switchable", module)
        registry.set_source_enabled("plugin:switchable", False)
        self.assertIsNone(registry.function("hello"))
        permission = registry.permissions()[0]
        self.assertFalse(permission["enabled"])

    def test_confirmation_codes_are_single_use(self):
        manager = ConfirmationManager()
        code = manager.create(["operation"])
        self.assertIsNone(manager.consume("000000"))
        self.assertEqual(manager.consume(code), ["operation"])
        self.assertIsNone(manager.consume(code))

    def test_history_store_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / "history.json", 2)
            store.save([1, 2, 3])
            self.assertEqual(store.load(), [2, 3])

    def test_sandbox_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "allowed"
            root.mkdir()
            sandbox = PathSandbox([root])
            self.assertTrue(sandbox.allows(root / "file.txt"))
            with self.assertRaises(SandboxViolation):
                sandbox.resolve(root / ".." / "outside.txt")

    def test_rollback_ignores_repository_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            backup = base / "backup"
            restored = base / "restored"
            (source / ".git").mkdir(parents=True)
            (source / ".git" / "index").write_text("x", encoding="utf-8")
            (source / "plugin.py").write_text("ok", encoding="utf-8")
            manager = RollbackManager()
            manager.backup(source, backup)
            manager.restore(backup, restored)
            self.assertTrue((restored / "plugin.py").exists())
            self.assertFalse((restored / ".git").exists())

    def test_task_engine_tracks_steps_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            engine = TaskEngine(path)
            task = engine.create("Demo", [
                {"tool": "one", "arguments": {}},
                {"tool": "two", "arguments": {"value": 2}},
            ])
            engine.update_step(task["id"], 0, "running")
            engine.update_step(task["id"], 0, "completed", result="ok")
            engine.update_step(task["id"], 1, "completed", result="ok")
            restored = TaskEngine(path).list()[0]
            self.assertEqual(restored["status"], "completed")
            self.assertEqual(len(restored["steps"]), 2)


if __name__ == "__main__":
    unittest.main()
