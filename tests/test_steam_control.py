import json
import unittest
from unittest.mock import patch

import advanced_controller as controller
import assistant


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._data


class SteamControlTests(unittest.TestCase):
    def test_store_search_resolves_best_title(self):
        payload = {"items": [
            {"id": 123, "name": "Cyberpunk Soundtrack"},
            {"id": 1091500, "name": "Cyberpunk 2077"},
        ]}
        with patch.object(controller.urllib.request, "urlopen",
                          return_value=FakeResponse(payload)):
            self.assertEqual(
                controller._steam_game_candidate("Cyberpunk 2077"),
                (1091500, "Cyberpunk 2077"))

    def test_install_opens_official_steam_uri(self):
        with patch.object(controller, "_steam_game_candidate",
                          return_value=(1091500, "Cyberpunk 2077")), \
                patch.object(controller.os, "startfile", create=True) as start:
            result = controller.steam_install_game("Cyberpunk 2077")
        start.assert_called_once_with("steam://install/1091500")
        self.assertIn("Cyberpunk 2077", result)

    def test_install_tool_remains_confirmation_protected(self):
        self.assertIn("steam_install_game", assistant.DANGEROUS_TOOLS)
        self.assertEqual(assistant.TOOL_RISK_LEVELS["steam_install_game"], "system")


if __name__ == "__main__":
    unittest.main()
