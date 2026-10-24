import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import assistant
import config
import gui


class ProbeCompletions:
    def create(self, **_kwargs):
        return object()


class ProbeClient:
    def __init__(self, **_kwargs):
        self.chat = type("Chat", (), {"completions": ProbeCompletions()})()


class ApiOnboardingTests(unittest.TestCase):
    def test_api_key_is_saved_and_existing_settings_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("VOICE_LANGUAGE=tr-TR\n", encoding="utf-8")
            with patch.object(config, "BASE_DIR", directory):
                config.save_api_key("nvidia", "nvapi-test-secret-value")
            contents = env.read_text(encoding="utf-8")
            self.assertIn("VOICE_LANGUAGE=tr-TR", contents)
            self.assertIn("NVIDIA_API_KEY=nvapi-test-secret-value", contents)

    def test_provider_is_activated_only_after_successful_probe(self):
        provider = {"name": "test", "model": "fake", "api_key": "x",
                    "base_url": "http://unused"}
        quartz = assistant.GitHubAssistant(
            client=ProbeClient(), provider=provider, history=[])
        with patch.object(assistant, "OpenAI", ProbeClient), \
                patch.object(assistant, "save_api_key") as save:
            result = quartz.configure_api("nvidia", "nvapi-test-secret-value")
        self.assertTrue(result["configured"])
        self.assertTrue(quartz.health_status()["llm"]["configured"])
        save.assert_called_once_with("nvidia", "nvapi-test-secret-value")

    def test_first_run_panel_uses_password_input(self):
        self.assertIn('<option value="groq">', gui._HTML)
        self.assertIn('id="apiSetup"', gui._HTML)
        self.assertIn('id="apiKey" type="password"', gui._HTML)
        self.assertIn("checkApiSetup()", gui._HTML)
        self.assertIn('id="providerStatus"', gui._HTML)
        self.assertIn('id="btnProviderProbe"', gui._HTML)

    def test_groq_key_is_persisted_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(config, "BASE_DIR", directory):
                config.save_api_key("groq", "gsk-test-secret-value")
            content = (Path(directory) / ".env").read_text(encoding="utf-8")
            self.assertIn("GROQ_API_KEY=gsk-test-secret-value", content)
            self.assertIn("LLM_PROVIDER=groq", content)
            self.assertNotIn("GITHUB_TOKEN", content)


if __name__ == "__main__":
    unittest.main()
