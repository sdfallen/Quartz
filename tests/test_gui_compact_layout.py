"""The compact chat (390 px) keeps every control inside the window (user report 26 Nov:
"mini chat bozuk" — the window controls and Send fell off the right edge)."""
import re
import unittest
from pathlib import Path

CSS = re.sub(r"/\*.*?\*/", "", (Path(__file__).resolve().parents[1] / "assets" / "workspace.css")
             .read_text(encoding="utf-8"), flags=re.S)


def compact_rules(selector: str) -> str:
    """Every declaration block of a body.compact rule that names the selector."""
    found = []
    for match in re.finditer(r"([^{}]+)\{([^}]*)\}", CSS):
        selectors, body = match.group(1), match.group(2)
        if any(part.strip().startswith("body.compact") and selector in part for part in selectors.split(",")):
            found.append(body)
    return " ".join(found)


class CompactLayoutTests(unittest.TestCase):
    def test_maximize_and_the_text_tool_buttons_leave_the_compact_bar(self):
        for selector in ("#btnWinMaximize", "#btnRepairPlan", "#btnContinueCollab"):
            self.assertIn("display: none", compact_rules(selector), selector)

    def test_the_wide_rows_may_shrink(self):
        self.assertIn("min-width: 0", compact_rules(".agent-seg-group"))
        self.assertIn("min-width: 0", compact_rules(".chat-title-group"))
        self.assertIn("min-width: 64px", compact_rules(".space-tab"))
        self.assertIn("width: 32px", compact_rules(".win-btn"))


if __name__ == "__main__":
    unittest.main()
