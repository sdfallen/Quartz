"""Read-only project inspection for questions answered by the selected project's files."""
import json
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
from tests import test_antigravity_runtime as agy_tests
from tests import test_codex_runtime as codex_tests
from tests import test_multi_agent_service as service_tests


class ProjectQuestionTests(unittest.TestCase):
    def test_questions_about_project_files_are_project_reads(self):
        for text in ("agent_chat.py neden bu kadar büyük?", "Bu projede hangi testler yavaş?",
                     "Son committe ne değişti?", "repair_review.py içindeki hata nerede olabilir?",
                     "dosyaları listele", "README dosyasında ne yazıyor?", "Hangi dalda çalışıyoruz?",
                     "requirements.txt içinde hangi paketler var?", "Bu kodu nasıl hızlandırabiliriz?"):
            with self.subTest(text=text):
                self.assertEqual(message_intent(text), "conversation")
                self.assertTrue(project_question(text))

    def test_project_name_counts(self):
        self.assertFalse(project_question("Quartz ajanlara hangi süreleri koyuyor?"))
        self.assertTrue(project_question("Quartz ajanlara hangi süreleri koyuyor?", ("Quartz", "Jarvis config")))
        self.assertFalse(project_question("Merhaba", ("Quartz",)))

    def test_small_talk_live_state_and_no_tools_stay_plain_conversation(self):
        for text in ("Merhaba", "Nasılsın?", "Python nedir?", "Notepad açık mı?",
                     "Masaüstümde kaç dosya var?", "Ekranda ne var, kodu nerede?",
                     "sadece sohbet edelim, kod hakkında konuşalım",
                     "araç kullanmadan README dosyasını anlat", "README dosyasını anlat, ama vazgeçtim"):
            with self.subTest(text=text):
                self.assertFalse(project_question(text))

    def test_quoted_text_does_not_count(self):
        self.assertFalse(project_question('Şu cümle ne demek: "README dosyasını oku"'))


class ReadGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        (self.root / "core").mkdir(parents=True)
        (self.root / "core" / "a.py").write_text("x = 1\n", encoding="utf-8")
        self.work = Path(self.tmp.name) / "work"
        self.work.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def allowed(self, name, args, *, native=True):
        payload = ({"toolCall": {"name": name, "args": args}} if native
                   else {"tool_name": name, "tool_input": json.dumps(args)})
        return project_read_tool_allowed(payload, [str(self.root), str(self.work)], cwd=self.work)

    def test_read_tools_inside_project_are_allowed(self):
        self.assertTrue(self.allowed("view_file", {"AbsolutePath": str(self.root / "core" / "a.py")}))
        self.assertTrue(self.allowed("list_dir", {"DirectoryPath": str(self.root)}))
        self.assertTrue(self.allowed("grep_search", {"SearchPath": str(self.root), "Query": "x = 1"}))
        self.assertTrue(self.allowed("find_by_name", {"SearchDirectory": str(self.root), "Pattern": "*.py"}, native=False))
        self.assertTrue(self.allowed("grep_search", {"Query": "def main"}))

    def test_writes_commands_and_unknown_tools_are_denied(self):
        target = str(self.root / "core" / "a.py")
        for name in ("write_to_file", "replace_file_content", "multi_replace_file_content", "run_command",
                     "run_shell_command", "search_web", "read_url_content", "call_mcp_tool", "invoke_subagent", ""):
            with self.subTest(name=name):
                self.assertFalse(self.allowed(name, {"TargetFile": target, "AbsolutePath": target}))

    def test_paths_outside_project_escape_and_secrets_are_denied(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        (self.root / ".env").write_text("TOKEN=1", encoding="utf-8")
        for args in ({"AbsolutePath": str(outside)},
                     {"AbsolutePath": str(self.root / ".." / "outside.txt")},
                     {"AbsolutePath": "core/../../outside.txt"},
                     {"AbsolutePath": str(self.root / ".env")},
                     {"AbsolutePath": str(self.root / "keys" / "server.pem")},
                     {"AbsolutePath": str(self.root / "core" / "a.py") + ":hidden"},
                     {"AbsolutePath": "~/.ssh/id_rsa"},
                     {"SearchPath": "C:\\Windows\\System32", "Query": "x"},
                     {"nested": {"Uri": str(outside)}}):
            with self.subTest(args=args):
                self.assertFalse(self.allowed("view_file", args))

    def test_project_under_a_dot_folder_is_readable_but_its_secrets_are_not(self):
        nested = Path(self.tmp.name) / ".codex" / "worktrees" / "repo"
        nested.mkdir(parents=True)
        payload = lambda path: {"toolCall": {"name": "view_file", "args": {"AbsolutePath": str(path)}}}
        self.assertTrue(project_read_tool_allowed(payload(nested / "README.md"), [str(nested)]))
        self.assertFalse(project_read_tool_allowed(payload(nested / ".env"), [str(nested)]))
        self.assertFalse(project_read_tool_allowed(payload(nested / ".codex" / "auth.json"), [str(nested)]))

    def test_malformed_payloads_fail_closed(self):
        self.assertFalse(project_read_tool_allowed(None, [str(self.root)]))
        self.assertFalse(project_read_tool_allowed({"toolCall": {"name": "view_file", "args": "{not json"}}, [str(self.root)]))
        self.assertFalse(project_read_tool_allowed({"toolCall": {"name": "view_file", "args": ["x"]}}, [str(self.root)]))
        self.assertFalse(project_read_tool_allowed({"toolCall": {"name": "view_file", "args": {}}}, []))


class RuntimeProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exe = self.root / "tool.exe"
        self.exe.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def wait(self, runtime, run_id):
        for _ in range(200):
            if runtime.get(run_id)["status"] in runtime.TERMINAL:
                return
            time.sleep(0.01)

    def test_codex_project_read_keeps_read_tools_and_disables_reach(self):
        runtime = CodexRuntime(self.exe)
        stream = '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
        with patch("core.codex_runtime.subprocess.Popen", return_value=codex_tests.FakeProcess(stream)) as popen:
            run = runtime.start("README ne diyor?", self.root, project_read=True)
            self.wait(runtime, run["id"])
        command = popen.call_args.args[0]
        joined = " ".join(command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(Path(command[command.index("--cd") + 1]).resolve(), self.root.resolve())
        for kept in ("shell_tool", "unified_exec", "view_image"):
            self.assertNotIn(f"features.{kept}=false", joined)
        for blocked in ("apps", "plugins", "multi_agent", "computer_use", "browser_use", "memories", "image_generation"):
            self.assertIn(f"features.{blocked}=false", joined)
        self.assertIn('web_search="disabled"', joined)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_codex_project_read_rejects_write_resume_desktop_and_guard(self):
        runtime = CodexRuntime(self.exe)
        for options in ({"sandbox": "workspace-write", "approval": "on-request"},
                        {"sandbox": "danger-full-access"}, {"resume_thread_id": "old"},
                        {"tool_guard": True}, {"desktop_connection": {"url": "u", "token": "t"}},
                        {"approval": "on-request"}):
            with self.subTest(options=options), patch("core.codex_runtime.subprocess.Popen") as popen:
                with self.assertRaises(ValueError):
                    runtime.start("x", self.root, project_read=True, **options)
                popen.assert_not_called()

    def test_antigravity_read_dirs_need_hook_and_read_only(self):
        runtime = AntigravityRuntime(self.exe)
        project = self.root / "project"
        project.mkdir()
        work = self.root / "work"
        work.mkdir()
        with patch("core.antigravity_runtime.subprocess.Popen") as popen:
            with self.assertRaises(PermissionError):
                runtime.start("x", work, read_dirs=[project])  # no hook in workspace
            (work / ".agents").mkdir()
            (work / ".agents" / "hooks.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(PermissionError):
                runtime.start("x", work, read_dirs=[project], write=True, full_access=True)
            popen.assert_not_called()
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=agy_tests.FakeProcess("")) as popen:
            run = runtime.start("x", work, read_dirs=[project])
            self.wait(runtime, run["id"])
        command = popen.call_args.args[0]
        self.assertEqual(Path(command[command.index("--add-dir") + 1]).resolve(), project.resolve())
        self.assertEqual(command[command.index("--mode") + 1], "auto")
        self.assertIn("--sandbox", command)
        self.assertNotIn("--dangerously-skip-permissions", command)


class ServiceRoutingTests(unittest.TestCase):
    def test_codex_project_read_runs_in_project_read_only(self):
        service, runtime, _ = service_tests.MultiAgentServiceTests().make_service()
        runtime.get.return_value = {"status": "completed"}
        with patch.object(service, "_start_writer") as writer, patch.object(service, "_squad") as squad:
            result = service.dispatch_codex("README ne diyor?", project_id="test", chat_mode=True,
                                            conversation_only=True, project_read=True, resume_thread_id="old")
        args, opts = runtime.start.call_args.args, runtime.start.call_args.kwargs
        self.assertEqual(Path(args[1]).resolve(), Path(".").resolve())
        self.assertTrue(opts["project_read"]); self.assertEqual(opts["sandbox"], "read-only")
        self.assertNotIn("tool_guard", opts); self.assertNotIn("resume_thread_id", opts)
        self.assertIn("YALNIZ OKUYABİLİRSİN", args[0])
        writer.assert_not_called(); squad.assert_not_called()
        self.assertTrue(result["run"]["project_read"])

    def test_protected_project_falls_back_to_blind_conversation(self):
        service, runtime, _ = service_tests.MultiAgentServiceTests().make_service()
        service.projects._projects["test"]["protected"] = True
        runtime.get.return_value = {"status": "completed"}
        service.dispatch_codex("README ne diyor?", project_id="test", chat_mode=True,
                               conversation_only=True, project_read=True)
        args, opts = runtime.start.call_args.args, runtime.start.call_args.kwargs
        self.assertTrue(opts["tool_guard"]); self.assertNotIn("project_read", opts)
        self.assertNotEqual(Path(args[1]).resolve(), Path(".").resolve())

    def test_antigravity_project_read_uses_scratch_hook_and_read_dir(self):
        service, _, agy = service_tests.MultiAgentServiceTests().make_service()
        agy.get.return_value = {"status": "completed"}
        with patch("core.chat_coordination.write_project_read_hooks") as hooks:
            service.dispatch_antigravity("README ne diyor?", project_id="test", chat_mode=True,
                                         conversation_only=True, project_read=True)
        args, opts = agy.start.call_args.args, agy.start.call_args.kwargs
        hooks.assert_called_once()
        self.assertEqual(Path(hooks.call_args.args[0]).resolve(), Path(args[1]).resolve())
        self.assertNotEqual(Path(args[1]).resolve(), Path(".").resolve())  # never writes into the project
        self.assertEqual([Path(p).resolve() for p in opts["read_dirs"]], [Path(".").resolve()])
        self.assertFalse(opts["write"]); self.assertNotIn("tool_guard", opts)

    def test_plain_conversation_prompt_is_truthful(self):
        service, runtime, _ = service_tests.MultiAgentServiceTests().make_service()
        runtime.get.return_value = {"status": "completed"}
        service.dispatch_codex("Merhaba", project_id="test", chat_mode=True, conversation_only=True)
        prompt = runtime.start.call_args.args[0]
        self.assertNotIn("ASLA 'yetkim yok'", prompt)
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
            chat = self.make_chat(directory, {"id": "p1", "name": "Quartz", "path": directory})
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


if __name__ == "__main__":
    unittest.main()
