"""Claude Code as Quartz's third agent: locked-down command, proven profile, record contract."""
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core import claude_runtime
from core.claude_runtime import ClaudeRuntime


def runtime():
    rt = ClaudeRuntime.__new__(ClaudeRuntime)
    ClaudeRuntime.__init__(rt, executable=None)
    rt.executable = r"C:\fake\claude.exe"
    return rt


def record_for(rt, sandbox="danger-full-access", project=r"C:\proj"):
    rec = {"id": "r1", "status": "running", "project": project, "sandbox": sandbox,
           "first_event_at": None, "first_text_at": None, "thread_id": None, "result": "",
           "errors": [], "events": [], "usage": None, "cost_usd": None, "commands": [],
           "command_results": [], "command_exit_codes": [], "files_changed": [],
           "scratch_files_changed": [], "file_changes": [], "unauthorized_write_detected": False,
           "unauthorized_files_changed": [], "error_events": [], "tools_verified": False,
           "_oracle_seq": 0, "_expected_tools": sorted(rt.tools_for(sandbox)), "_pending_tools": {}}
    rt._runs["r1"] = rec
    return rec


def feed(rt, *events):
    lines = [json.dumps(e) + "\n" for e in events]
    process = SimpleNamespace(stdout=iter(lines))
    with patch.object(claude_runtime, "stop_process_tree") as stop:
        rt._read_stdout("r1", process)
    return stop


def init(rt, sandbox, **extra):
    event = {"type": "system", "subtype": "init", "session_id": "sess-1", "model": "claude-sonnet-5-5",
             "tools": list(rt.tools_for(sandbox)), "mcp_servers": [], "permissionMode": "dontAsk"}
    event.update(extra)
    return event


class CommandTests(unittest.TestCase):
    def test_every_run_is_locked_down(self):
        rt = runtime()
        for sandbox in ("none", "read-only", "workspace-write", "danger-full-access"):
            with self.subTest(sandbox=sandbox):
                args = rt.build_args(sandbox, model="sonnet", effort="high", session_id="s")
                for flag in ("-p", "--strict-mcp-config", "--verbose"):
                    self.assertIn(flag, args)
                self.assertEqual(args[args.index("--output-format") + 1], "stream-json")
                self.assertEqual(json.loads(args[args.index("--mcp-config") + 1]), {"mcpServers": {}})
                self.assertEqual(args[args.index("--setting-sources") + 1], "")
                self.assertEqual(args[args.index("--permission-mode") + 1], "dontAsk")
                self.assertEqual(args[args.index("--tools") + 1], ",".join(rt.tools_for(sandbox)))
                for forbidden in ("--bare", "--dangerously-skip-permissions",
                                  "--allow-dangerously-skip-permissions", "bypassPermissions"):
                    self.assertNotIn(forbidden, args)

    def test_tool_sets_grow_only_with_permission(self):
        rt = runtime()
        self.assertEqual(rt.tools_for("none"), ())
        self.assertEqual(set(rt.tools_for("read-only")), {"Read", "Grep", "Glob"})
        self.assertNotIn("Bash", rt.tools_for("workspace-write"))
        self.assertIn("Bash", rt.tools_for("danger-full-access"))
        for sandbox in claude_runtime.TOOLS_BY_SANDBOX:
            for risky in ("SendMessage", "WebFetch", "WebSearch", "CronCreate", "Task", "Artifact", "Skill"):
                self.assertNotIn(risky, rt.tools_for(sandbox))
        with self.assertRaises(ValueError):
            rt.tools_for("anything")

    def test_read_and_write_permissions_stay_inside_the_project(self):
        rt = runtime()

        def allowed(sandbox):
            args = rt.build_args(sandbox)
            return args[args.index("--allowedTools") + 1] if "--allowedTools" in args else None
        # No blanket "Read" rule: outside-project reads must hit dontAsk and be refused.
        self.assertIsNone(allowed("read-only"))
        self.assertEqual(allowed("workspace-write"), "Edit(./**)")
        self.assertEqual(allowed("danger-full-access").split(","), list(rt.tools_for("danger-full-access")))

    def test_tool_less_chat_has_no_allow_list_and_resume_uses_resume(self):
        rt = runtime()
        args = rt.build_args("none")
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertNotIn("--allowedTools", args)
        args = rt.build_args("read-only", session_id="new", resume_id="old")
        self.assertEqual(args[args.index("--resume") + 1], "old")
        self.assertNotIn("--session-id", args)

    def test_child_does_not_inherit_parent_claude_session(self):
        with patch("core.cli_installer.cli_environment",
                   return_value={"PATH": "x", "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "claude-desktop"}):
            env = ClaudeRuntime.child_environment()
        self.assertEqual(env, {"PATH": "x"})

    def test_unwired_profiles_are_refused_before_any_record(self):
        rt = runtime()
        with tempfile.TemporaryDirectory() as folder:
            for kwargs in ({"desktop_connection": object()}, {"tool_guard": True}, {"project_read": folder}):
                with self.subTest(kwargs=list(kwargs)):
                    with self.assertRaises(PermissionError):
                        rt.start("x", folder, **kwargs)
            self.assertEqual(rt._runs, {})
            with self.assertRaises(ValueError):
                rt.start("x", folder, effort="ultra")
            self.assertEqual(rt._runs, {})


class StreamTests(unittest.TestCase):
    def test_verified_run_records_session_files_commands_and_result(self):
        rt = runtime()
        rec = record_for(rt)
        stop = feed(rt, init(rt, "danger-full-access"),
                    {"type": "assistant", "message": {"content": [
                        {"type": "text", "text": "Yazıyorum"},
                        {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": r"C:\proj\app.py"}},
                        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "pytest -q"}}]}},
                    {"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
                        {"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": "3 passed"}]}]}},
                    {"type": "result", "subtype": "success", "is_error": False, "result": "Bitti",
                     "usage": {"output_tokens": 5}, "total_cost_usd": 0.01})
        stop.assert_not_called()
        self.assertTrue(rec["tools_verified"])
        self.assertEqual(rec["thread_id"], "sess-1")
        self.assertEqual(rec["files_changed"], [r"C:\proj\app.py"])
        self.assertEqual(rec["commands"][0]["command"], "pytest -q")
        self.assertTrue(rec["command_results"][0]["ok"])
        self.assertEqual(rec["result"], "Bitti")
        self.assertEqual(rec["errors"], [])
        self.assertIsNotNone(rec["first_text_at"])

    def test_unexpected_tools_or_mcp_stop_the_process_at_init(self):
        for extra in ({"tools": ["Read", "Grep", "Glob", "SendMessage"]},
                      {"mcp_servers": [{"name": "evil", "status": "connected"}]},
                      {"permissionMode": "bypassPermissions"}):
            with self.subTest(extra=extra):
                rt = runtime()
                rec = record_for(rt, "read-only")
                stop = feed(rt, init(rt, "read-only", **extra),
                            {"type": "result", "subtype": "success", "is_error": False, "result": "x"})
                stop.assert_called_once()
                self.assertFalse(rec["tools_verified"])
                self.assertEqual(rec["result"], "")
                self.assertEqual(rec["error_events"][0]["kind"], "profile_mismatch")

    def test_activity_before_init_is_refused(self):
        rt = runtime()
        rec = record_for(rt)
        stop = feed(rt, {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}})
        stop.assert_called_once()
        self.assertEqual(rec["error_events"][0]["kind"], "unverified_profile")

    def test_is_error_decides_failure_even_when_subtype_says_success(self):
        rt = runtime()
        rec = record_for(rt, "none")
        feed(rt, init(rt, "none"), {"type": "result", "subtype": "success", "is_error": True,
                                    "result": "Failed to authenticate: OAuth session expired"})
        self.assertEqual(rec["result"], "")
        self.assertIn("OAuth", rec["errors"][0])

    def test_auth_failure_forgets_cached_readiness(self):
        rt = runtime()
        rt._probe_cache = (10**9, {"ready": True})
        record_for(rt, "none")
        feed(rt, init(rt, "none"), {"type": "result", "subtype": "success", "is_error": True,
                                    "result": "Failed to authenticate: OAuth session expired"})
        self.assertEqual(rt._probe_cache, (0.0, {}))

    def test_read_only_write_is_flagged_as_unauthorized(self):
        rt = runtime()
        rec = record_for(rt, "read-only")
        feed(rt, init(rt, "read-only"),
             {"type": "assistant", "message": {"content": [
                 {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": r"C:\proj\a.py"}}]}},
             {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})
        self.assertTrue(rec["unauthorized_write_detected"])
        self.assertEqual(rec["unauthorized_files_changed"], [r"C:\proj\a.py"])

    def test_failed_tool_results_are_not_counted_as_changes(self):
        rt = runtime()
        rec = record_for(rt)
        feed(rt, init(rt, "danger-full-access"),
             {"type": "assistant", "message": {"content": [
                 {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": r"C:\proj\a.py"}},
                 {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "exit 1"}}]}},
             {"type": "user", "message": {"content": [
                 {"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "denied"},
                 {"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": "boom"}]}})
        self.assertEqual(rec["files_changed"], [])
        self.assertEqual(rec["file_changes"][0]["state"], "ERROR")
        self.assertFalse(rec["command_results"][0]["ok"])


class ProbeTests(unittest.TestCase):
    def test_probe_reads_auth_status_json(self):
        rt = runtime()
        replies = {"--version": {"returncode": 0, "stdout": "2.1.318 (Claude Code)\n", "stderr": ""},
                   "auth": {"returncode": 0, "stdout": json.dumps({"loggedIn": True, "authMethod": "claude.ai"}), "stderr": ""}}
        with patch.object(rt, "_probe", side_effect=lambda args: replies[args[0]]):
            result = rt.probe(force=True)
        self.assertTrue(result["ready"])
        self.assertEqual(result["authentication"], "claude.ai")

    def test_expired_login_is_not_ready_and_explains_how_to_fix(self):
        rt = runtime()
        replies = {"--version": {"returncode": 0, "stdout": "2.1.318", "stderr": ""},
                   "auth": {"returncode": 0, "stdout": json.dumps({"loggedIn": False}), "stderr": ""}}
        with patch.object(rt, "_probe", side_effect=lambda args: replies[args[0]]):
            result = rt.probe(force=True)
        self.assertFalse(result["ready"])
        self.assertIn("/login", result["error"])


class ServiceTests(unittest.TestCase):
    def service(self, folder):
        from core.multi_agent_service import MultiAgentService
        svc = MultiAgentService.__new__(MultiAgentService)
        import threading
        svc._lock = threading.RLock()
        svc._links = {}
        svc.claude = MagicMock()
        svc.claude.probe.return_value = {"ready": True, "error": ""}
        svc.claude.start.return_value = {"id": "run-1"}
        svc.codex = MagicMock()
        svc.antigravity = MagicMock()
        svc.projects = MagicMock()
        svc.projects.get.return_value = {"id": "p", "path": folder}
        svc.check_squad_connection = MagicMock(return_value={"connected": False})
        svc._start_writer = MagicMock(return_value={"id": "run-w"})
        return svc

    def test_runtime_lookup_and_dispatch_route_to_claude(self):
        with tempfile.TemporaryDirectory() as folder:
            svc = self.service(folder)
            self.assertIs(svc._runtime_for("claude"), svc.claude)
            self.assertIs(svc._runtime_for("codex"), svc.codex)
            self.assertIs(svc._runtime_for("agy"), svc.antigravity)
            svc.dispatch("claude", "x", project_id="p", chat_mode=True, model="sonnet", effort="medium")
            kwargs = svc.claude.start.call_args.kwargs
            self.assertEqual(kwargs["sandbox"], "read-only")
            self.assertEqual(svc._links["run-1"]["provider"], "claude")

    def test_write_needs_confirmation_and_uses_the_writer_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            svc = self.service(folder)
            with self.assertRaises(PermissionError):
                svc.dispatch_claude("x", project_id="p", chat_mode=True, full_access=True)
            svc.dispatch_claude("x", project_id="p", chat_mode=True, full_access=True, confirm_write=True)
            args = svc._start_writer.call_args
            self.assertEqual(args.args[0], "claude")
            self.assertEqual(args.kwargs["sandbox"], "danger-full-access")
            svc.claude.start.assert_not_called()

    def test_squad_task_path_and_unready_cli_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            svc = self.service(folder)
            with self.assertRaises(PermissionError):
                svc.dispatch_claude("x", project_id="p")
            svc.claude.probe.return_value = {"ready": False, "error": "login"}
            with self.assertRaisesRegex(RuntimeError, "login"):
                svc.dispatch_claude("x", project_id="p", chat_mode=True)

    def test_model_selection_accepts_claude_efforts(self):
        from core.multi_agent_service import MultiAgentService
        ok = MultiAgentService.validate_model_selections({"claude": {"model": "opus", "effort": "max"}}, agents=("claude",))
        self.assertEqual(ok["claude"], {"model": "opus", "effort": "max"})
        with self.assertRaises(ValueError):
            MultiAgentService.validate_model_selections({"claude": {"model": "opus", "effort": "ultra"}}, agents=("claude",))


if __name__ == "__main__":
    unittest.main()
