"""Claude in the interface: its lane, model picker, mode button and readiness."""
import re
import unittest
from pathlib import Path

from ui.js_chat import JAVASCRIPT as CHAT_JS
from ui.js_setup import JAVASCRIPT as SETUP_JS
from ui.shell import SHELL_MARKUP

ROOT = Path(__file__).resolve().parents[1]


class ClaudeMarkupTests(unittest.TestCase):
    def test_lane_picker_and_mode_button_are_shipped_once(self):
        for element_id in ("laneColClaude", "laneClaude", "laneClaudeState", "claudeModelPill",
                           "claudeModelSelect", "claudeEffortSelect", "laneClaudeStatus", "laneClaudeTrail"):
            self.assertEqual(SHELL_MARKUP.count(f'id="{element_id}"'), 1, element_id)
        self.assertEqual(SHELL_MARKUP.count('class="agent-seg-btn" data-agent="claude"'), 1)
        self.assertIn('<option value="claude">Claude</option>', SHELL_MARKUP)

    def test_model_and_effort_options_match_the_runtime(self):
        from core.claude_runtime import MODELS, ClaudeRuntime
        model_block = re.search(r'id="claudeModelSelect".*?</select>', SHELL_MARKUP, re.S).group(0)
        effort_block = re.search(r'id="claudeEffortSelect".*?</select>', SHELL_MARKUP, re.S).group(0)
        self.assertEqual(sorted(re.findall(r'value="([^"]+)"', model_block)), sorted(m for m, _ in MODELS))
        self.assertEqual(re.findall(r'value="([^"]+)"', effort_block), ClaudeRuntime.SUPPORTED_EFFORTS)

    def test_stage_gives_claude_its_own_grid_area(self):
        css = (ROOT / "assets" / "workspace.css").read_text(encoding="utf-8")
        self.assertIn('grid-template-areas: "codex stream agy" "claude stream agy"', css)
        self.assertIn(".lane-claude { grid-area: claude;", css)
        self.assertIn("#laneClaude, .lane-claude, .chat > .msg.sender-claude { --lane:", css)


class ClaudeScriptTests(unittest.TestCase):
    def test_lane_mode_and_model_saving_are_wired(self):
        self.assertIn("claude: {col: 'laneColClaude', card: 'laneClaude'", CHAT_JS)
        self.assertIn("'Yalnız Claude'", CHAT_JS)
        self.assertIn("saveAgentModelSelection('claude', true)", CHAT_JS)
        self.assertIn("['codex', 'antigravity', 'claude', 'collaboration'].includes(agent)", CHAT_JS)

    def test_birlikte_mode_does_not_pull_claude_in(self):
        self.assertIn("(focus === 'collaboration' && agent !== 'claude')", CHAT_JS)

    def test_mode_button_readiness_comes_from_claude_provider(self):
        self.assertIn("['codex','antigravity','claude','collaboration'].includes(agent)", SETUP_JS)
        self.assertIn("...(known?.claude ? [['claude', 'Claude', describe(known.claude), active === 'claude']] : [])", SETUP_JS)


class ClaudeReadinessTests(unittest.TestCase):
    def test_onboarding_reports_claude_from_auth_status(self):
        import tempfile
        from unittest.mock import patch
        from core import onboarding
        with tempfile.TemporaryDirectory() as folder:
            service = onboarding.OnboardingService.__new__(onboarding.OnboardingService)
            service.lock = __import__("threading").RLock()
            service.login_processes = {}
            service._cached, service._cached_at = None, 0
            service.job = {"state": "idle"}
            service.base = Path(folder)
            service.installer = type("I", (), {"status": lambda self: {
                "codex": {"installed": False, "executable": None},
                "gemini": {"installed": False, "executable": None}}})()
            service._load_connections = lambda: {"gemini": {"backend": "agy"}}
            for ready, message in ((True, "Claude hesabı bağlı"), (False, "/login")):
                with self.subTest(ready=ready), \
                        patch("core.antigravity_runtime.AntigravityRuntime.probe", return_value={"ready": False}), \
                        patch("core.claude_runtime.ClaudeRuntime.probe",
                              return_value={"installed": True, "ready": ready, "executable": "claude.exe"}):
                    claude = service.status(force=True)["providers"]["claude"]
                self.assertEqual(claude["ready"], ready)
                self.assertIn(message, claude["auth_message"])


if __name__ == "__main__":
    unittest.main()
