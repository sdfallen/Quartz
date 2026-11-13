"""Read-only project inspection for questions answered by the selected project's files."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.agent_chat import AgentChatService
from core.antigravity_runtime import AntigravityRuntime
from core.codex_runtime import CodexRuntime
from core.desktop_mcp import project_read_tool_allowed
from core.message_intent import message_intent, project_question
from core.project_read_mcp import ProjectReader, handle
from tests import test_antigravity_runtime as agy_tests
from tests import test_codex_runtime as codex_tests
from tests import test_multi_agent_service as service_tests

NAMES = ("SpeS", "Jarvis config")


def mcp_listing(*names, returncode=0):
    """A fake `codex mcp list --json` result with the given servers enabled."""
    from types import SimpleNamespace
    body = json.dumps([{"name": n, "enabled": True} for n in names])
    return SimpleNamespace(returncode=returncode, stdout=body, stderr="")


class ProjectQuestionTests(unittest.TestCase):
    def test_questions_about_project_files_are_project_reads(self):
        for text in ("agent_chat.py neden bu kadar büyük?", "Bu projede hangi testler yavaş?",
                     "Son committe ne değişti?", "repair_review.py içindeki hata nerede olabilir?",
                     "dosyaları listele", "README dosyasında ne yazıyor?", "Hangi dalda çalışıyoruz?",
                     "requirements.txt içinde hangi paketler var?", "Bu kodu nasıl hızlandırabiliriz?",
                     "agent_chat.py içindeki pencere seçimi nasıl çalışıyor?", "requirements.txt nedir?"):
            with self.subTest(text=text):
                self.assertEqual(message_intent(text), "conversation")
                self.assertTrue(project_question(text, NAMES))

    def test_project_name_needs_a_question_about_it(self):
        self.assertFalse(project_question("SpeS ajanlara hangi süreleri koyuyor?"))
        self.assertTrue(project_question("SpeS ajanlara hangi süreleri koyuyor?", NAMES))
        for text in ("SpeS, nasılsın?", "Merhaba SpeS"):
            with self.subTest(text=text):
                self.assertFalse(project_question(text, NAMES))

    def test_concepts_small_talk_live_state_and_no_look_stay_plain_conversation(self):
        for text in ("Merhaba", "Nasılsın?", "Python nedir?", "Fonksiyon nedir?", "Git branch nedir?",
                     "Python test piramidi nedir?", "Notepad açık mı?", "Masaüstümde kaç dosya var?",
                     "Ekranda ne var, kodu nerede?", "sadece sohbet edelim, kod hakkında konuşalım",
                     "araç kullanmadan README dosyasını anlat", "Bu kodu dosyalara bakmadan açıkla.",
                     "README dosyasında ne yazıyor? Araçlara başvurma.", "README dosyasını anlat, ama vazgeçtim",
                     "README.md dosyasını okumadan ne işe yaradığını açıkla.",
                     "İndirilenler klasöründe ne var?", "example.com/index.html neden açılmıyor?"):
            with self.subTest(text=text):
                self.assertFalse(project_question(text, NAMES))

    def test_quoted_text_does_not_count(self):
        self.assertFalse(project_question('Şu cümle ne demek: "README dosyasını oku"'))


class ProjectReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".codex" / "worktrees" / "repo"  # project under a dot folder
        (self.root / "core").mkdir(parents=True)
        (self.root / "core" / "a.py").write_text("def main():\n    return 'needle'\n", encoding="utf-8")
        (self.root / ".env").write_text("TOKEN=needle-secret\n", encoding="utf-8")
        (self.root / "keys").mkdir()
        (self.root / "keys" / "server.pem").write_text("needle-pem\n", encoding="utf-8")
        (self.root / "blob.bin").write_bytes(b"\0needle")
        (Path(self.tmp.name) / "outside.txt").write_text("needle-outside\n", encoding="utf-8")
        self.reader = ProjectReader(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_read_and_search_inside_the_project(self):
        listing = self.reader.list("")
        self.assertIn("core/", listing); self.assertNotIn(".env", listing)
        self.assertIn("2:     return 'needle'", self.reader.read("core/a.py"))
        hits = self.reader.search("needle")
        self.assertIn("core/a.py:2:", hits)
        for leaked in ("needle-secret", "needle-pem", "needle-outside", "blob.bin"):
            self.assertNotIn(leaked, hits)

    def test_escape_absolute_secret_and_stream_paths_are_refused(self):
        for path in ("../../../../outside.txt", "C:/Windows/win.ini", "/etc/passwd", "~/x", ".env",
                     "keys/server.pem", "core/a.py:hidden", "core/../../repo/.env"):
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                self.reader.read(path)

    @unittest.skipUnless(os.name == "nt", "Windows junction")
    def test_junction_inside_project_is_not_followed(self):
        link = self.root / "link"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), self.tmp.name],
                              capture_output=True, text=True)
        if made.returncode != 0:
            self.skipTest("junction creation unavailable")
        with self.assertRaises(ValueError):
            self.reader.read("link/outside.txt")
        self.assertNotIn("needle-outside", self.reader.search("needle"))

    def test_opened_object_is_verified_not_just_the_checked_name(self):
        # Simulate a swap between check and open: the opened handle resolves outside the root.
        outside = Path(self.tmp.name) / "outside.txt"
        with patch("core.project_read_mcp._final_path", return_value=str(outside)):
            with self.assertRaises(ValueError):
                self.reader.read("core/a.py")
            self.assertNotIn("needle", self.reader.search("needle"))

    def test_listing_is_verified_on_the_held_folder(self):
        outside = str(Path(self.tmp.name))
        with patch("core.project_read_mcp._handle_path", return_value=outside):
            with self.assertRaises(ValueError):
                self.reader.list("core")
            self.assertEqual(self.reader.search("needle"), "(no matches)")

    @unittest.skipUnless(os.name == "nt", "Windows handle sharing")
    def test_listing_comes_from_the_verified_handle_even_if_the_name_is_swapped(self):
        from core.project_read_mcp import _DirHandle
        holder = _DirHandle(self.root / "core")
        with holder:
            os.rename(self.root / "core", self.root / "moved")       # swap after verification
            (self.root / "core").mkdir()
            (self.root / "core" / "planted.txt").write_text("x", encoding="utf-8")
            names = [name for name, _, _ in holder.entries()]
        self.assertIn("a.py", names)
        self.assertNotIn("planted.txt", names)

    @unittest.skipUnless(os.name == "nt", "Windows junction")
    def test_link_inside_project_pointing_inside_is_also_not_followed(self):
        link = self.root / "alias"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.root / "core")],
                              capture_output=True, text=True)
        if made.returncode != 0:
            self.skipTest("junction creation unavailable")
        with self.assertRaises(ValueError):
            self.reader.read("alias/a.py")

    def test_mcp_protocol_reports_errors_without_raising(self):
        tools = handle(self.reader, {"method": "tools/list"})["tools"]
        self.assertEqual([t["name"] for t in tools], ["project_list", "project_read", "project_search"])
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
        bad = handle(self.reader, {"method": "tools/call", "params": {"name": "project_read", "arguments": {"path": ".env"}}})
        self.assertTrue(bad["isError"])
        unknown = handle(self.reader, {"method": "tools/call", "params": {"name": "write_file", "arguments": {}}})
        self.assertTrue(unknown["isError"])


class ReadGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        (self.root / "core").mkdir(parents=True)
        (self.root / "core" / "a.py").write_text("x = 1\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def allowed(self, name, args, *, native=True):
        payload = ({"toolCall": {"name": name, "args": args}} if native
                   else {"tool_name": name, "tool_input": json.dumps(args)})
        return project_read_tool_allowed(payload, [str(self.root)], cwd=self.root)

    def test_explicit_path_reads_inside_project_are_allowed(self):
        self.assertTrue(self.allowed("read_file", {"Path": str(self.root / "core" / "a.py")}))  # live payload shape
        self.assertTrue(self.allowed("view_file", {"AbsolutePath": str(self.root / "core" / "a.py")}))
        self.assertTrue(self.allowed("list_dir", {"DirectoryPath": str(self.root)}, native=False))

    def test_search_writes_commands_and_unknown_tools_are_denied(self):
        target = str(self.root / "core" / "a.py")
        for name in ("grep_search", "codebase_search", "find_by_name", "write_to_file", "replace_file_content",
                     "run_command", "search_web", "read_url_content", "call_mcp_tool", "invoke_subagent", ""):
            with self.subTest(name=name):
                self.assertFalse(self.allowed(name, {"SearchPath": target, "Path": target, "Query": "x"}))

    def test_scope_is_mandatory(self):
        self.assertFalse(self.allowed("list_dir", {}))
        self.assertFalse(self.allowed("read_file", {"StartLine": 1}))

    def test_the_tools_own_target_field_is_required(self):
        inside = str(self.root / "core")
        self.assertFalse(self.allowed("read_file", {"DirectoryPath": inside}))  # no Path
        self.assertFalse(self.allowed("read_file", {"Path": 42}))
        self.assertFalse(self.allowed("read_file", {"Path": inside, "AbsolutePath": inside}))  # ambiguous
        self.assertFalse(self.allowed("list_dir", {"SearchPath": inside}))

    def test_paths_outside_project_escape_and_secrets_are_denied(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        for args in ({"Path": str(outside)}, {"Path": str(self.root / ".." / "outside.txt")},
                     {"Path": "core/../../outside.txt"}, {"Path": str(self.root / ".env")},
                     {"Path": str(self.root / "keys" / "server.pem")}, {"Path": str(self.root / "core" / "a.py") + ":hidden"},
                     {"Path": "~/.ssh/id_rsa"}, {"nested": {"Uri": str(outside)}}):
            with self.subTest(args=args):
                self.assertFalse(self.allowed("read_file", args))

    def test_malformed_payloads_fail_closed(self):
        self.assertFalse(project_read_tool_allowed(None, [str(self.root)]))
        self.assertFalse(project_read_tool_allowed({"toolCall": {"name": "read_file", "args": "{not json"}}, [str(self.root)]))
        self.assertFalse(project_read_tool_allowed({"toolCall": {"name": "read_file", "args": ["x"]}}, [str(self.root)]))
        self.assertFalse(project_read_tool_allowed({"toolCall": {"name": "read_file", "args": {"Path": "a"}}}, []))


class RuntimeProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exe = self.root / "tool.exe"
        self.exe.touch()
        self.project = self.root / "project"
        self.project.mkdir()
        self.work = self.root / "work"
        self.work.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def wait(self, runtime, run_id):
        for _ in range(200):
            if runtime.get(run_id)["status"] in runtime.TERMINAL:
                return
            time.sleep(0.01)

    def test_codex_project_read_has_no_builtin_tools_and_only_quartz_mcp(self):
        runtime = CodexRuntime(self.exe)
        stream = ('{"type":"thread.started","thread_id":"t-1"}\n'
                  '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n')
        listings = [mcp_listing("quartz_project", "node_repl"), mcp_listing("quartz_project")]
        with patch("core.codex_runtime.subprocess.run", side_effect=listings) as probe, \
                patch("core.codex_runtime.subprocess.Popen", return_value=codex_tests.FakeProcess(stream)) as popen:
            run = runtime.start("README ne diyor?", self.work, project_read=self.project)
            self.wait(runtime, run["id"])
        self.assertEqual(probe.call_count, 2)
        self.assertIn("mcp", probe.call_args.args[0]); self.assertIn("--json", probe.call_args.args[0])
        command = popen.call_args.args[0]
        joined = " ".join(command)
        self.assertEqual(command[-1], "app-server")  # same-session verification path
        self.assertEqual(Path(popen.call_args.kwargs["cwd"]).resolve(), self.work.resolve())
        self.assertIn("mcp_servers.node_repl.enabled=false", joined)
        self.assertIn("features.hooks=false", joined)
        for blocked in ("shell_tool", "unified_exec", "view_image", "apps", "plugins", "multi_agent",
                        "computer_use", "browser_use", "memories", "image_generation"):
            self.assertIn(f"features.{blocked}=false", joined)
        self.assertIn('web_search="disabled"', joined)
        override = next(arg for arg in command if arg.startswith("mcp_servers.quartz_project="))
        self.assertIn("--project-read-server", override)
        self.assertIn(json.dumps(str(self.project.resolve()))[1:-1].replace("\\\\", "\\"),
                      override.replace("\\\\", "\\"))
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        with self.assertRaises(PermissionError):
            runtime.resume(run["id"], "devam")

    def test_codex_effective_mcp_set_is_proven_or_start_refused(self):
        runtime = CodexRuntime(self.exe)
        failing = [
            [mcp_listing("quartz_project", "node_repl"), mcp_listing("quartz_project", "node_repl")],  # stays on
            [mcp_listing("node_repl")],                                                               # ours missing
            [mcp_listing("quartz_project", returncode=1)],                                             # cannot verify
            [mcp_listing("quartz_project", "bad name!")],                                              # unsafe name
        ]
        for listings in failing:
            with self.subTest(listings=[l.stdout for l in listings]), \
                    patch("core.codex_runtime.subprocess.run", side_effect=listings), \
                    patch("core.codex_runtime.subprocess.Popen") as popen:
                with self.assertRaises(RuntimeError):
                    runtime.start("x", self.work, project_read=self.project)
                popen.assert_not_called()
        self.assertEqual(runtime._runs, {}); self.assertEqual(runtime._writers, {})

    def test_listing_rows_of_unknown_state_are_refused(self):
        from types import SimpleNamespace
        runtime = CodexRuntime(self.exe)
        rows = SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
            [{"name": "quartz_project", "enabled": True}, {"name": "mystery"}]))
        with patch("core.codex_runtime.subprocess.run", return_value=rows), \
                patch("core.codex_runtime.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError):
                runtime.start("x", self.work, project_read=self.project)
            popen.assert_not_called()

    def test_stop_during_project_read_checks_starts_no_process(self):
        runtime = CodexRuntime(self.exe)
        # Stopped before the first probe.
        with patch("core.codex_runtime.subprocess.run") as probe, \
                patch("core.codex_runtime.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError):
                runtime.start("x", self.work, project_read=self.project, should_abort=lambda: True)
            probe.assert_not_called(); popen.assert_not_called()
        self.assertEqual(runtime._runs, {})
        # Stopped after the checks passed but before the process: run is cancelled, nothing spawned.
        calls = iter([False, True])
        with patch("core.codex_runtime.subprocess.run", return_value=mcp_listing("quartz_project")), \
                patch("core.codex_runtime.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError):
                runtime.start("x", self.work, project_read=self.project, should_abort=lambda: next(calls, True))
            popen.assert_not_called()
        self.assertEqual([r["status"] for r in runtime._runs.values()], ["cancelled"])
        self.assertEqual(runtime._writers, {})

    def test_codex_rejected_profiles_leave_no_run_or_writer_lock(self):
        runtime = CodexRuntime(self.exe)
        cases = [dict(project_read=self.project, **o) for o in (
            {"sandbox": "workspace-write", "approval": "on-request"}, {"sandbox": "danger-full-access"},
            {"resume_thread_id": "old"}, {"tool_guard": True}, {"approval": "on-request"},
            {"desktop_connection": {"url": "u", "token": "t"}})]
        cases.append({"tool_guard": True, "sandbox": "workspace-write", "approval": "on-request"})
        for options in cases:
            with self.subTest(options=options), patch("core.codex_runtime.subprocess.Popen") as popen:
                with self.assertRaises(ValueError):
                    runtime.start("x", self.work, **options)
                popen.assert_not_called()
        self.assertEqual(runtime._runs, {}); self.assertEqual(runtime._writers, {})

    def test_failed_reader_start_does_not_release_another_writers_lock(self):
        runtime = CodexRuntime(self.exe)
        key = os.path.normcase(str(self.work.resolve()))
        runtime._writers[key] = "writer-run"
        with patch("core.codex_runtime.subprocess.Popen", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                runtime.start("x", self.work)  # read-only run on the same folder
        self.assertEqual(runtime._writers.get(key), "writer-run")

    def make_guard(self, roots=None, hooks=None):
        from core.chat_coordination import write_project_read_hooks
        helper = self.root / "QuartzDesktopMCP.exe"
        helper.write_bytes(b"MZ")
        with patch("core.chat_coordination.mcp_command", return_value=[str(helper)]):
            write_project_read_hooks(self.work, roots or [self.project])
        if hooks is not None:
            (self.work / ".agents" / "hooks.json").write_text(hooks, encoding="utf-8")

    def test_antigravity_read_dirs_need_the_exact_guard(self):
        runtime = AntigravityRuntime(self.exe)
        with patch("core.antigravity_runtime.subprocess.Popen") as popen:
            with self.assertRaises(PermissionError):
                runtime.start("x", self.work, read_dirs=[self.project])  # no guard at all
            self.make_guard(hooks="{}")
            with self.assertRaises(PermissionError):
                runtime.start("x", self.work, read_dirs=[self.project])  # wrong hook content
            other = self.root / "other"; other.mkdir()
            self.make_guard(roots=[other])
            with self.assertRaises(PermissionError):
                runtime.start("x", self.work, read_dirs=[self.project])  # roots differ
            self.make_guard()
            with self.assertRaises(PermissionError):
                runtime.start("x", self.work, read_dirs=[self.project], write=True, full_access=True)
            popen.assert_not_called()
        hooks = json.loads((self.work / ".agents" / "hooks.json").read_text(encoding="utf-8"))
        command = hooks["quartz-project-read"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertNotIn('"', command)  # no quoted paths through cmd.exe
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=agy_tests.FakeProcess("")) as popen:
            run = runtime.start("x", self.work, read_dirs=[self.project])
            self.wait(runtime, run["id"])
        command = popen.call_args.args[0]
        self.assertEqual(Path(command[command.index("--add-dir") + 1]).resolve(), self.project.resolve())
        self.assertIn("--sandbox", command)
        self.assertNotIn("--dangerously-skip-permissions", command)


class ServiceRoutingTests(unittest.TestCase):
    def test_codex_project_read_runs_in_scratch_with_project_root(self):
        service, runtime, _ = service_tests.MultiAgentServiceTests().make_service()
        runtime.get.return_value = {"status": "completed"}
        with patch.object(service, "_start_writer") as writer, patch.object(service, "_squad") as squad:
            result = service.dispatch_codex("README ne diyor?", project_id="test", chat_mode=True,
                                            conversation_only=True, project_read=True, resume_thread_id="old")
        args, opts = runtime.start.call_args.args, runtime.start.call_args.kwargs
        self.assertNotEqual(Path(args[1]).resolve(), Path(".").resolve())
        self.assertEqual(Path(opts["project_read"]).resolve(), Path(".").resolve())
        self.assertEqual(opts["sandbox"], "read-only")
        self.assertNotIn("tool_guard", opts); self.assertNotIn("resume_thread_id", opts)
        self.assertIn("YALNIZ OKUYABİLİRSİN", args[0]); self.assertIn("project_read", args[0])
        writer.assert_not_called(); squad.assert_not_called()
        self.assertTrue(result["run"]["project_read"])

    def test_protected_and_warband_projects_fall_back_to_blind_conversation(self):
        for flag in ({"protected": True}, {"workflow": "warband"}):
            with self.subTest(flag=flag):
                service, runtime, _ = service_tests.MultiAgentServiceTests().make_service()
                service.projects._projects["test"].update(flag)
                runtime.get.return_value = {"status": "completed"}
                service.dispatch_codex("README ne diyor?", project_id="test", chat_mode=True,
                                       conversation_only=True, project_read=True)
                opts = runtime.start.call_args.kwargs
                self.assertTrue(opts["tool_guard"]); self.assertNotIn("project_read", opts)

    def test_gemini_cli_backend_never_gets_project_read(self):
        service, _, agy = service_tests.MultiAgentServiceTests().make_service()
        service.antigravity = agy  # independent of the machine's Google backend selection
        agy.backend = "gemini"
        agy.get.return_value = {"status": "completed"}
        with patch("core.chat_coordination.write_project_read_hooks") as hooks, \
                patch("core.chat_coordination.write_observer_hooks"):
            service.dispatch_antigravity("README ne diyor?", project_id="test", chat_mode=True,
                                         conversation_only=True, project_read=True)
        hooks.assert_not_called()
        opts = agy.start.call_args.kwargs
        self.assertTrue(opts["tool_guard"]); self.assertNotIn("read_dirs", opts)

    def test_antigravity_runtime_refuses_read_dirs_on_gemini_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "agy.exe"; exe.touch()
            runtime = AntigravityRuntime(exe)
            runtime.backend = "gemini"
            with patch("core.antigravity_runtime.subprocess.Popen") as popen, self.assertRaises(PermissionError):
                runtime.start("x", tmp, read_dirs=[tmp])
            popen.assert_not_called()

    def test_antigravity_project_read_uses_scratch_guard_and_read_dir(self):
        service, _, agy = service_tests.MultiAgentServiceTests().make_service()
        service.antigravity = agy  # independent of the machine's Google backend selection
        agy.backend = "agy"
        agy.get.return_value = {"status": "completed"}
        with patch("core.chat_coordination.write_project_read_hooks") as hooks:
            service.dispatch_antigravity("README ne diyor?", project_id="test", chat_mode=True,
                                         conversation_only=True, project_read=True)
        args, opts = agy.start.call_args.args, agy.start.call_args.kwargs
        hooks.assert_called_once()
        self.assertEqual(os.path.normcase(str(hooks.call_args.args[0])), os.path.normcase(str(args[1])))
        self.assertNotEqual(Path(args[1]).resolve(), Path(".").resolve())  # never writes into the project
        self.assertEqual([Path(p).resolve() for p in opts["read_dirs"]], [Path(".").resolve()])
        self.assertFalse(opts["write"]); self.assertNotIn("tool_guard", opts)

    def test_stop_while_antigravity_guard_is_prepared_starts_nothing(self):
        service, _, agy = service_tests.MultiAgentServiceTests().make_service()
        service.antigravity = agy
        agy.backend = "agy"
        with patch("core.chat_coordination.write_project_read_hooks"):
            with self.assertRaises(RuntimeError):
                service.dispatch_antigravity("README ne diyor?", project_id="test", chat_mode=True,
                                             conversation_only=True, project_read=True, should_abort=lambda: True)
        agy.start.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows handle")
    def test_folder_handle_is_closed_when_its_path_cannot_be_verified(self):
        from core import project_read_mcp
        closed = []
        real_k32 = project_read_mcp._kernel32()

        class K32:
            def __getattr__(self, name):
                return getattr(real_k32, name)

            def CloseHandle(self, handle):
                closed.append(handle)
                return real_k32.CloseHandle(handle)

        with tempfile.TemporaryDirectory() as folder, \
                patch("core.project_read_mcp._kernel32", return_value=K32()), \
                patch("core.project_read_mcp._handle_path", side_effect=OSError("verify failed")):
            with self.assertRaises(OSError):
                with project_read_mcp._DirHandle(folder):
                    pass
        self.assertEqual(len(closed), 1)

    def test_plain_conversation_prompt_is_truthful(self):
        service, runtime, _ = service_tests.MultiAgentServiceTests().make_service()
        runtime.get.return_value = {"status": "completed"}
        service.dispatch_codex("Merhaba", project_id="test", chat_mode=True, conversation_only=True)
        prompt = runtime.start.call_args.args[0]
        self.assertNotIn("yetkim yok", prompt)
        self.assertIn("araç kullanmıyorsun", prompt)


class ChatTurnTests(unittest.TestCase):
    def make_chat(self, directory, project):
        agents = MagicMock()
        agents.projects.get.return_value = project
        chat = AgentChatService(agents, Path(directory) / "chats.json")
        chat.set_project(chat.store.get_active()["id"], "p1")
        return chat

    def send(self, chat, text, agent="codex"):
        conv = chat.store.get_active()
        self.assertEqual(conv.get("project_id"), "p1")
        with patch("core.agent_chat.threading.Thread"):
            chat.send_message(text, agent=agent, conversation_id=conv["id"])
        return chat._active_turn

    def test_project_question_marks_turn_project_read(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = self.make_chat(directory, {"id": "p1", "name": "SpeS", "path": directory})
            self.assertTrue(self.send(chat, "README dosyasında ne yazıyor?")["project_read"])

    def test_small_talk_tasks_protected_and_group_are_not_project_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            for project, text, agent in (({"id": "p1", "path": directory}, "Merhaba", "codex"),
                                         ({"id": "p1", "path": directory, "protected": True}, "README ne diyor?", "codex"),
                                         ({"id": "p1", "path": directory, "workflow": "warband"}, "README ne diyor?", "codex"),
                                         ({"id": "p1", "path": directory}, "README ne diyor?", "collaboration")):
                with self.subTest(project=project, text=text, agent=agent), \
                        tempfile.TemporaryDirectory() as store_dir:
                    chat = self.make_chat(store_dir, project)
                    self.assertFalse(self.send(chat, text, agent)["project_read"])

    def test_single_chat_prompts_no_longer_forbid_admitting_missing_access(self):
        prompt = AgentChatService._build_single_chat_prompt("codex", "Merhaba", [], set(), write=False)
        self.assertNotIn("yetkim yok", prompt)


if __name__ == "__main__":
    unittest.main()
