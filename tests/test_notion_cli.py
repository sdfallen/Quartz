import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from core.notion_cli import API_VERSION, NotionCli, NotionError, VERSION, install_ntn

WORKSPACE = "10000000-0000-0000-0000-000000000001"


class NotionCliTests(unittest.TestCase):
    def test_prompt_is_stdin_not_command_and_environment_does_not_leak_keys(self):
        calls = []
        def run(args, **kw):
            calls.append((args, kw))
            return subprocess.CompletedProcess(args, 0, '{"object":"session"}', '')
        cli = NotionCli(WORKSPACE, executable="ntn.exe", run=run)
        prompt = "özetle `$(anything)` & whoami"
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only", "NOTION_API_TOKEN": "test-only", "NOTION_KEYRING": "0",
                                    "NOTION_API_BASE_URL": "https://attacker.invalid", "NOTION_ENV": "dev"}):
            cli.request("v1/sessions", {"message": prompt})
        args, kw = calls[0]
        self.assertNotIn(prompt, args)
        self.assertEqual(json.loads(kw["input"])["message"], prompt)
        self.assertEqual(kw["env"]["NOTION_WORKSPACE_ID"], WORKSPACE)
        self.assertNotIn("NOTION_API_TOKEN", kw["env"])
        self.assertEqual(kw["env"]["NOTION_KEYRING"], "1")
        self.assertNotIn("OPENAI_API_KEY", kw["env"])
        self.assertEqual(kw["env"]["NOTION_API_BASE_URL"], "https://api.notion.com")
        self.assertEqual(kw["env"]["NOTION_ENV"], "prod")
        self.assertNotIn("shell", kw)
        self.assertIn(API_VERSION, args)

    def test_arbitrary_write_path_is_rejected_before_execution(self):
        cli = NotionCli(WORKSPACE, executable="ntn.exe", run=lambda *a, **k: self.fail("ran"))
        for path in ("https://attacker.invalid/", "v1/pages", "v1/sessions/../../delete"):
            with self.assertRaises(ValueError):
                cli.request(path, {})

    def test_real_cli_no_login_exit_is_not_misreported_as_bad_json(self):
        cli = NotionCli(WORKSPACE, executable="ntn.exe", run=lambda *a, **kw:
                        subprocess.CompletedProcess(a, 4, "", "error: No auth token found for the current workspace.\n"))
        with self.assertRaises(NotionError) as error:
            cli.agents()
        self.assertEqual(error.exception.code, "unauthorized")
        self.assertFalse(error.exception.uncertain)

    def test_timeout_is_ambiguous_and_never_retried(self):
        calls = []
        def run(args, **kw):
            calls.append(args)
            raise subprocess.TimeoutExpired(args, 30, output="private-user-data")
        cli = NotionCli(WORKSPACE, executable="ntn.exe", run=run)
        with self.assertRaises(NotionError) as error:
            cli.request("v1/sessions", {"message": "test"})
        self.assertTrue(error.exception.uncertain)
        self.assertNotIn("private-user-data", str(error.exception))
        self.assertEqual(len(calls), 1)

    def test_api_error_is_sanitized(self):
        def run(*args, **kw):
            return subprocess.CompletedProcess(args, 1, json.dumps({"object": "error", "code": "restricted_resource", "message": "private-token"}), "private-token")
        cli = NotionCli(WORKSPACE, executable="ntn.exe", run=run)
        with self.assertRaises(NotionError) as error:
            cli.request("v1/agents/query", {})
        self.assertEqual(error.exception.code, "restricted_resource")
        self.assertNotIn("private-token", str(error.exception))

    def test_malformed_success_does_not_expose_stdout(self):
        cli = NotionCli(WORKSPACE, executable="ntn.exe", run=lambda *a, **kw: subprocess.CompletedProcess(a, 0, "private-stderr", "private-stderr"))
        with self.assertRaises(NotionError) as error:
            cli.request("v1/users/me")
        self.assertNotIn("private-stderr", str(error.exception))

    def test_agent_pagination_does_not_silently_truncate(self):
        cli = NotionCli(WORKSPACE)
        with patch.object(cli, "request", side_effect=[
            {"results": [{"id": "a"}], "has_more": True, "next_cursor": "cursor"},
            {"results": [{"id": "b"}], "has_more": False},
        ]) as request:
            self.assertEqual([a["id"] for a in cli.agents()], ["a", "b"])
            self.assertEqual(request.call_args.args[1]["start_cursor"], "cursor")
        with patch.object(cli, "request", return_value={"results": [], "has_more": True, "next_cursor": "same"}):
            with self.assertRaises(NotionError):
                cli.agents()

    def test_install_only_extracts_expected_binary_without_npm_hooks(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as tar:
            for name, content in (("package/dist/ntn-win32-x64/ntn.exe", b"MZ-test-only"),
                                  ("../../unwanted", b"no"), ("package/install.cjs", b"must-not-run")):
                item = tarfile.TarInfo(name)
                item.size = len(content)
                tar.addfile(item, io.BytesIO(content))
        archive = data.getvalue()
        integrity = base64.b64encode(hashlib.sha512(archive).digest()).decode()
        calls = []
        def run(args, **kw):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, VERSION, "")
        with tempfile.TemporaryDirectory() as directory, patch("core.notion_cli.platform.system", return_value="Windows"), \
                patch("core.notion_cli.platform.machine", return_value="AMD64"), patch("core.notion_cli.INTEGRITY", integrity):
            result = install_ntn(directory, fetch=lambda u: archive, run=run)
            self.assertEqual(Path(result["executable"]).read_bytes(), b"MZ-test-only")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][-1], "--version")
            self.assertFalse((Path(directory).parent / "unwanted").exists())
            self.assertTrue(install_ntn(directory, fetch=lambda u: self.fail("re-downloaded"), run=run)["reused"])
            Path(result["executable"]).write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                install_ntn(directory, run=run)

    def test_bad_checksum_is_not_executed(self):
        with tempfile.TemporaryDirectory() as directory, patch("core.notion_cli.platform.system", return_value="Windows"), \
                patch("core.notion_cli.platform.machine", return_value="AMD64"):
            with self.assertRaises(ValueError):
                install_ntn(directory, fetch=lambda u: b"invalid", run=lambda *a, **k: self.fail("ran"))


if __name__ == "__main__":
    unittest.main()
