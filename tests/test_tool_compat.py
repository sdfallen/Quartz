import unittest
from unittest.mock import patch

import advanced_controller
import assistant

from core.tool_compat import parse_text_tool_call


class TextToolCompatibilityTests(unittest.TestCase):
    ALLOWED = {"smart_open", "browser_open_url"}

    def test_parses_complete_quoted_call(self):
        self.assertEqual(
            parse_text_tool_call('smart_open("code")', self.ALLOWED),
            ("smart_open", ["code"], {}),
        )

    def test_accepts_simple_unquoted_app_name(self):
        self.assertEqual(
            parse_text_tool_call("smart_open(code)", self.ALLOWED),
            ("smart_open", ["code"], {}),
        )

    def test_does_not_execute_calls_embedded_in_explanation(self):
        self.assertIsNone(
            parse_text_tool_call(
                'İstersen smart_open("code") kullanabilirim.', self.ALLOWED
            )
        )

    def test_rejects_unknown_or_executable_arguments(self):
        self.assertIsNone(parse_text_tool_call('delete("x")', self.ALLOWED))
        self.assertIsNone(
            parse_text_tool_call(
                'smart_open(__import__("os").getcwd())', self.ALLOWED
            )
        )

    def test_smart_open_routes_youtube_to_signed_in_browser(self):
        with patch.object(advanced_controller, "_open_in_user_browser") as opener:
            result = advanced_controller.smart_open("YouTube")
        opener.assert_called_once_with("https://www.youtube.com")
        self.assertIn("youtube", result.lower())

    def test_turkish_open_request_selects_browser_tool(self):
        hint = assistant._intent_hint("YouTube'u açar mısın?")
        self.assertIn('browser_open_url("https://www.youtube.com")', hint)


if __name__ == "__main__":
    unittest.main()
