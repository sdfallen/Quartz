"""Normal runtime selection and OAuth verification, with no real accounts."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from core.gemini_runtime import GeminiRuntime, google_runtime
from core.onboarding import OnboardingService


class GeminiAuthSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.meta = {"backend": "gemini", "method": "account"}
        self.write_meta()
        self.env = {"GEMINI_CLI_HOME": str(self.root)}
        self.account_check = patch("core.gemini_auth.verify_google_account", return_value=False)
        from core.gemini_auth import verify_google_account
        self.original_verify_account = verify_google_account
        self.verify_account = self.account_check.start()
        self.addCleanup(self.account_check.stop)

    def tearDown(self):
        self.temp.cleanup()

    def write_meta(self):
        (self.root / "quartz_memory.json").write_text(json.dumps({"cli_connections": {"gemini": self.meta}}), encoding="utf-8")

    def write_oauth(self, **fields):
        folder = self.root / ".gemini"
        folder.mkdir(exist_ok=True)
        path = folder / "oauth_creds.json"
        path.write_text(json.dumps(fields), encoding="utf-8")
        return path

    def state(self):
        installer = Mock()
        installer.status.return_value = {"codex": {"installed": False, "executable": None}, "gemini": {"installed": True, "executable": "fake.exe"}}
        with patch.dict(os.environ, self.env, clear=True):
            return OnboardingService(self.root, installer=installer).status()["providers"]["gemini"]

    def test_normal_factory_reads_saved_backend_without_base_argument(self):
        with patch("core.gemini_runtime.app_root", return_value=self.root), patch("core.gemini_runtime.cli_environment", return_value=self.env), patch.dict(os.environ, {}, clear=True), patch("core.gemini_runtime.GeminiRuntime") as gemini:
            legacy = Mock()
            google_runtime(legacy_factory=legacy)
        gemini.assert_called_once()
        legacy.assert_not_called()

    def test_explicit_agy_account_selection_is_not_overridden_by_api_key(self):
        self.meta["backend"] = "agy"
        self.write_meta()
        expected = Mock()
        with patch("core.gemini_runtime.app_root", return_value=self.root), patch("core.gemini_runtime.cli_environment", return_value={"GEMINI_API_KEY": "placeholder"}), patch("core.gemini_runtime.GeminiRuntime") as gemini:
            self.assertIs(google_runtime(legacy_factory=Mock(return_value=expected)), expected)
        gemini.assert_not_called()

    def test_connect_existing_agy_account_does_not_install_gemini_or_launch_login(self):
        service = OnboardingService(self.root, installer=Mock())
        service.installer.status.return_value = {"codex": {"installed": False, "executable": None}, "gemini": {"installed": True, "executable": "fake.exe"}}
        runtime = Mock(executable="agy.exe")
        runtime.probe.return_value = {"installed": True, "ready": True, "executable": "agy.exe"}
        with patch("core.antigravity_runtime.AntigravityRuntime", return_value=runtime), patch("core.onboarding.subprocess.Popen") as launch:
            service._work("account_agy", "gemini", "")
            state = service.status()["providers"]["gemini"]
        self.assertEqual(service.job["state"], "done")
        service.installer.install.assert_not_called()
        launch.assert_not_called()
        self.assertTrue(state["ready"])
        self.assertEqual(state["backend"], "agy")
        self.assertFalse((self.root / ".env").exists())

    def test_refresh_after_restart_removes_gemini_auto_model_without_erasing_chat(self):
        from types import SimpleNamespace
        from main import IPCServer
        server = object.__new__(IPCServer)
        store = Mock()
        store.get_active.return_value = {"id": "chat", "sessions": {}, "models": {"antigravity": {"model": "auto"}}}
        chat = SimpleNamespace(agent_service=SimpleNamespace(antigravity=SimpleNamespace(backend="agy")),
                               status=lambda: {"active_turn": None}, store=store)
        server._get_agent_chat = lambda: chat
        with patch("core.codex_runtime.CodexRuntime"), patch("core.gemini_runtime.google_runtime", return_value=SimpleNamespace(backend="agy")):
            response = server._dispatch_action({"action": "onboarding_refresh"})
        self.assertEqual(response["status"], "ok")
        store.set_agent_session.assert_called_once_with("chat", "antigravity", None)
        store.update_agent_model.assert_called_once_with("chat", "antigravity", model="gemini-4-argon-medium", effort="medium")

    def test_account_task_uses_google_account_despite_inherited_api_key(self):
        runtime = object.__new__(GeminiRuntime)
        env = {**self.env, "GEMINI_API_KEY": "placeholder", "GOOGLE_API_KEY": "placeholder", "GOOGLE_GENAI_USE_VERTEXAI": "true", "KEEP_SETTING": "yes"}
        settings_dir = self.root / "settings"
        settings_dir.mkdir()
        with patch("core.gemini_runtime.app_root", return_value=self.root), patch("core.gemini_runtime.cli_environment", return_value=env), patch("core.gemini_runtime.tempfile.mkdtemp", return_value=str(settings_dir)):
            options = runtime._process_options({"env": {"GEMINI_API_KEY": "late-placeholder"}}, self.root, None, False)
        settings = json.loads((settings_dir / "settings.json").read_text())
        self.assertNotIn("GEMINI_API_KEY", options["env"])
        self.assertNotIn("GOOGLE_API_KEY", options["env"])
        self.assertNotIn("GOOGLE_GENAI_USE_VERTEXAI", options["env"])
        self.assertEqual(options["env"]["KEEP_SETTING"], "yes")
        self.assertEqual(settings["security"]["auth"]["selectedType"], "oauth-personal")
        self.assertEqual(env["GEMINI_API_KEY"], "placeholder")

    @unittest.skipUnless(os.name == "nt", "Windows CLI module resolution")
    def test_windows_acl_modules_are_preferred_without_changing_parent(self):
        from core.gemini_auth import task_environment
        modules = self.root / "System32/WindowsPowerShell/v1.0/Modules"
        modules.mkdir(parents=True)
        original = {"SystemRoot": str(self.root), "PSModulePath": "inherited-modules"}
        child = task_environment(original, {"method": "api-key"})
        self.assertEqual(original["PSModulePath"], "inherited-modules")
        self.assertEqual(child["PSModulePath"], str(modules) + os.pathsep + "inherited-modules")

    def test_expired_oauth_does_not_mean_verified_or_ready(self):
        self.write_oauth(access_token="placeholder", expiry_date=1)
        state = self.state()
        self.assertTrue(state["configured"])
        self.assertFalse(state["auth_verified"])
        self.assertFalse(state["ready"])

    def test_unchecked_future_oauth_does_not_mean_verified(self):
        self.write_oauth(access_token="placeholder", expiry_date=4102444800000)
        self.assertFalse(self.state()["auth_verified"])

    def test_existing_valid_cli_login_is_verified_automatically(self):
        self.write_oauth(access_token="placeholder", expiry_date=(time.time() + 3600) * 1000)
        self.verify_account.return_value = True
        self.assertTrue(self.state()["ready"])
        self.verify_account.assert_called_once_with("placeholder")

    def test_login_polling_does_not_keep_old_missing_credentials_cache(self):
        installer = Mock()
        installer.status.return_value = {"codex": {"installed": False, "executable": None}, "gemini": {"installed": True, "executable": "fake.exe"}}
        service = OnboardingService(self.root, installer=installer)
        service.login_processes["gemini"] = Mock(poll=Mock(return_value=None))
        with patch.dict(os.environ, self.env, clear=True):
            first = service.status()
            self.assertTrue(first["providers"]["gemini"]["login_pending"])
            self.write_oauth(access_token="placeholder", expiry_date=(time.time() + 3600) * 1000)
            self.verify_account.return_value = True
            second = service.status()
        self.assertTrue(second["providers"]["gemini"]["ready"])
        self.assertFalse(second["providers"]["gemini"]["login_pending"])

    def test_selected_account_cannot_be_verified_by_an_old_api_key(self):
        import hashlib
        self.meta.update(validated_at=12345, key_sha256=hashlib.sha256(b"placeholder").hexdigest())
        self.write_meta()
        self.env["GEMINI_API_KEY"] = "placeholder"
        state = self.state()
        self.assertFalse(state["auth_verified"])
        self.assertFalse(state["ready"])

    def test_explicit_account_verification_is_cached_without_credentials_or_identity(self):
        from core.gemini_auth import oauth_status
        path = self.write_oauth(access_token="placeholder-token", expiry_date=(time.time() + 3600) * 1000)
        before = path.read_bytes()
        validator = Mock(return_value=True)
        checked = oauth_status(self.env, self.root, verify=True, validator=validator)
        self.assertTrue(checked["auth_verified"])
        validator.assert_called_once_with("placeholder-token")
        cache = (self.root / ".quartz/gemini-oauth-check.json").read_text()
        self.assertNotIn("placeholder-token", cache)
        self.assertNotIn("access_token", cache)
        self.assertEqual(path.read_bytes(), before)
        validator.reset_mock()
        self.assertTrue(oauth_status(self.env, self.root, validator=validator)["auth_verified"])
        validator.assert_not_called()

    def test_failed_or_expired_account_is_not_verified_even_with_refresh_token(self):
        from core.gemini_auth import oauth_status
        self.write_oauth(access_token="placeholder", refresh_token="placeholder-refresh", expiry_date=1)
        validator = Mock(return_value=True)
        self.assertFalse(oauth_status(self.env, self.root, verify=True, validator=validator)["auth_verified"])
        validator.assert_not_called()
        self.write_oauth(access_token="placeholder", expiry_date=(time.time() + 3600) * 1000)
        self.assertFalse(oauth_status(self.env, self.root, verify=True, validator=Mock(return_value=False))["auth_verified"])

    def test_token_rotation_rechecks_and_does_not_reuse_prior_success(self):
        from core.gemini_auth import oauth_status
        self.write_oauth(access_token="first-placeholder", expiry_date=(time.time() + 3600) * 1000)
        oauth_status(self.env, self.root, verify=True, validator=Mock(return_value=True))
        self.write_oauth(access_token="second-placeholder", expiry_date=(time.time() + 3600) * 1000)
        validator = Mock(return_value=False)
        self.assertFalse(oauth_status(self.env, self.root, validator=validator)["auth_verified"])
        validator.assert_called_once_with("second-placeholder")

    def test_explicit_status_and_runtime_probe_agree_on_verified_account(self):
        self.write_oauth(access_token="placeholder", expiry_date=(time.time() + 3600) * 1000)
        installer = Mock()
        installer.status.return_value = {"codex": {"installed": False, "executable": None}, "gemini": {"installed": True, "executable": "fake.exe"}}
        with patch.dict(os.environ, self.env, clear=True), patch("core.gemini_auth.verify_google_account", return_value=True) as verify:
            state = OnboardingService(self.root, installer=installer).status(force=True)["providers"]["gemini"]
        self.assertTrue(state["ready"])
        verify.assert_called_once()
        runtime = object.__new__(GeminiRuntime)
        runtime.executable = "fake.exe"
        runtime._probe_cache, runtime._probe_cache_at = None, 0.0
        runtime._probe = Mock(return_value={"returncode": 0, "stdout": "test-version"})
        with patch("core.gemini_runtime.app_root", return_value=self.root), patch("core.gemini_runtime.cli_environment", return_value=self.env):
            self.assertTrue(runtime.probe()["ready"])
            self.write_oauth(access_token="placeholder", expiry_date=1)
            self.assertFalse(runtime.probe()["ready"])

    def test_api_key_selection_is_preserved_without_using_cached_oauth(self):
        import hashlib
        self.meta.update(method="api-key", validated_at=time.time(), key_sha256=hashlib.sha256(b"placeholder").hexdigest())
        self.write_meta()
        self.env["GEMINI_API_KEY"] = "placeholder"
        self.write_oauth(access_token="old-placeholder", expiry_date=1)
        self.assertTrue(self.state()["ready"])

    def test_interactive_account_login_overrides_old_api_settings_only_in_child(self):
        captured = {}
        env = {**self.env, "GEMINI_API_KEY": "placeholder", "GOOGLE_API_KEY": "placeholder", "GOOGLE_GENAI_USE_VERTEXAI": "true"}
        def launch(*args, **kwargs):
            captured["env"] = kwargs["env"]
            captured["settings"] = json.loads(Path(kwargs["env"]["GEMINI_CLI_SYSTEM_SETTINGS_PATH"]).read_text())
            return Mock()
        service = OnboardingService(self.root, installer=Mock())
        with patch("core.onboarding.resolve_cli", return_value="fake.exe"), patch("core.onboarding.cli_environment", return_value=env), patch("core.onboarding.subprocess.Popen", side_effect=launch):
            service._work("account", "gemini", "")
        self.assertEqual(service.job["state"], "done")
        self.assertEqual(captured["settings"]["security"]["auth"]["selectedType"], "oauth-personal")
        self.assertTrue(captured["settings"]["advanced"]["ignoreLocalEnv"])
        self.assertNotIn("GOOGLE_API_KEY", captured["env"])
        self.assertNotIn("GEMINI_API_KEY", captured["env"])
        self.assertNotIn("GOOGLE_GENAI_USE_VERTEXAI", captured["env"])
        self.assertIn("GEMINI_API_KEY", env)

    def test_google_validation_uses_fixed_https_endpoint_and_no_model_request(self):
        verify_google_account = self.original_verify_account
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"sub":"placeholder-subject"}'
        opener = Mock()
        opener.open.return_value = response
        with patch("core.gemini_auth.urllib.request.build_opener", return_value=opener):
            self.assertTrue(verify_google_account("placeholder-token"))
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://openidconnect.googleapis.com/v1/userinfo")
        self.assertNotIn("placeholder-token", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer placeholder-token")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 5)


if __name__ == "__main__":
    unittest.main()
