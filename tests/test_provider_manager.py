import unittest
from types import SimpleNamespace

from core.provider_manager import ProviderManager, classify_provider_error


class ProviderManagerTests(unittest.TestCase):
    def test_probe_lists_model_without_generating_text(self):
        calls = []
        client = SimpleNamespace(models=SimpleNamespace(list=lambda: (
            calls.append("models") or SimpleNamespace(
                data=[SimpleNamespace(id="openai/gpt-oss-20b")]))))
        manager = ProviderManager("nvidia", "openai/gpt-oss-20b", True)
        result = manager.probe(client)
        self.assertEqual(calls, ["models"])
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["automatic_failover"])

    def test_missing_model_is_reported_without_secret_or_raw_error(self):
        client = SimpleNamespace(models=SimpleNamespace(list=lambda: SimpleNamespace(
            data=[SimpleNamespace(id="another-model")])))
        result = ProviderManager("nvidia", "removed-model", True).probe(client)
        self.assertEqual(result["last_error_code"], "model_missing")
        self.assertNotIn("removed-model", result["last_error"])

    def test_runtime_usage_is_accumulated(self):
        manager = ProviderManager("nvidia", "model", True)
        manager.record_success(.25, SimpleNamespace(prompt_tokens=12, completion_tokens=3))
        state = manager.snapshot()
        self.assertEqual(state["latency_ms"], 250)
        self.assertEqual(state["input_tokens"], 12)
        self.assertEqual(state["output_tokens"], 3)

    def test_errors_have_user_facing_categories(self):
        self.assertEqual(classify_provider_error(RuntimeError("403 forbidden"))[0], "permission")
        self.assertEqual(classify_provider_error(RuntimeError("429 rate limit"))[0], "rate_limit")
        self.assertEqual(classify_provider_error(RuntimeError("request timed out"))[0], "timeout")


if __name__ == "__main__":
    unittest.main()
