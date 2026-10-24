import os
import unittest
from unittest.mock import patch

import config


class ProviderSelectionTests(unittest.TestCase):
    def test_groq_does_not_fall_back_when_key_missing(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": ""}):
            provider = config.get_llm_provider()
        self.assertEqual(provider["name"], "groq")
        self.assertEqual(provider["api_key"], "")

    def test_groq_selection(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "test-key"}):
            provider = config.get_llm_provider()
        self.assertEqual(provider["base_url"], "https://api.groq.com/openai/v1")
        self.assertEqual(provider["model"], "openai/gpt-oss-120b")

    def test_explicit_github_provider_overrides_available_nvidia_key(self):
        values = {
            "LLM_PROVIDER": "github",
            "GITHUB_TOKEN": "github-test-token",
            "NVIDIA_API_KEY": "nvidia-test-key",
        }
        with patch.dict(os.environ, values, clear=False):
            provider = config.get_llm_provider()
        self.assertEqual(provider["name"], "github")
        self.assertEqual(provider["api_key"], "github-test-token")

    def test_explicit_nvidia_provider_is_supported(self):
        values = {
            "LLM_PROVIDER": "nvidia",
            "GITHUB_TOKEN": "github-test-token",
            "NVIDIA_API_KEY": "nvidia-test-key",
        }
        with patch.dict(os.environ, values, clear=False):
            provider = config.get_llm_provider()
        self.assertEqual(provider["name"], "nvidia")
        self.assertEqual(provider["model"], "openai/gpt-oss-20b")


if __name__ == "__main__":
    unittest.main()
