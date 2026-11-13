"""The desktop/guard helper must stay small: Antigravity starts it for every tool call.

On 12 Nov an import of core.desktop_agents (numpy, PIL, Tk, pywin32) from the
project-read module grew the one-file helper from 7.8 MB to 34 MB; it then
needed 9-13 s to start, Antigravity's 5 s hook limit expired and every tool
call was refused.
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER_MODULES = {"core.desktop_mcp", "core.project_read_mcp", "core.helper_command"}


def imported_names(path):
    """Every module name imported anywhere in the file, function bodies included (PyInstaller follows them)."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            if node.module == "core":
                names.update("core." + alias.name for alias in node.names)
    return names


class HelperFootprintTests(unittest.TestCase):
    def test_helper_import_closure_is_standard_library_only(self):
        stdlib = set(sys.stdlib_module_names) | {"__future__"}
        seen, todo = set(), ["core.desktop_mcp"]
        while todo:
            module = todo.pop()
            if module in seen:
                continue
            seen.add(module)
            for name in imported_names(ROOT / (module.replace(".", "/") + ".py")):
                if name in HELPER_MODULES:
                    todo.append(name)
                elif name in {"project_read_mcp", "core"}:  # script/frozen fallback; bare namespace package
                    continue
                else:
                    with self.subTest(module=module, imports=name):
                        self.assertIn(name.split(".")[0], stdlib)
        self.assertEqual(seen, HELPER_MODULES)

    def test_every_guard_hook_has_the_same_generous_time_limit(self):
        from core.chat_coordination import write_observer_hooks, write_project_read_hooks
        from core.desktop_agents import write_operator_hooks
        from core.helper_command import HOOK_TIMEOUT_SECONDS
        self.assertGreaterEqual(HOOK_TIMEOUT_SECONDS, 20)
        with tempfile.TemporaryDirectory() as work:
            helper = Path(work) / "helper.exe"; helper.write_bytes(b"x")
            project = Path(work) / "project"; project.mkdir()
            for module, write, args in (("core.chat_coordination", write_observer_hooks, ()),
                                        ("core.chat_coordination", write_project_read_hooks, ([str(project)],)),
                                        ("core.desktop_agents", write_operator_hooks, ())):
                with self.subTest(writer=write.__name__), tempfile.TemporaryDirectory() as directory, \
                        patch(module + ".mcp_command", return_value=[str(helper)]):
                    hooks = write(directory, *args)
                    hooks = Path(hooks) if hooks else Path(directory) / ".agents/hooks.json"
                    entry = next(iter(json.loads(hooks.read_text(encoding="utf-8")).values()))
                    self.assertEqual(entry["PreToolUse"][0]["hooks"][0]["timeout"], HOOK_TIMEOUT_SECONDS)


    def test_observer_hook_switches_to_web_search_only_when_asked(self):
        from core.chat_coordination import write_observer_hooks
        with tempfile.TemporaryDirectory() as work:
            helper = Path(work) / "helper.exe"; helper.write_bytes(b"x")
            for web, flag in ((False, "--deny-tools"), (True, "--web-search-only")):
                with self.subTest(web=web), tempfile.TemporaryDirectory() as directory,                         patch("core.chat_coordination.mcp_command", return_value=[str(helper)]):
                    hooks = Path(write_observer_hooks(directory, web=web))
                    entry = next(iter(json.loads(hooks.read_text(encoding="utf-8")).values()))
                    command = entry["PreToolUse"][0]["hooks"][0]["command"]
                    self.assertTrue(command.endswith(flag), command)
                    self.assertEqual(entry["PreToolUse"][0]["matcher"], "*")


if __name__ == "__main__":
    unittest.main()
