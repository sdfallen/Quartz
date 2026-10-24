"""Reliability tests for empirical verification, evidence integrity, and user-facing messages.
Covers:
- F-07: Model self-assertion vs empirical validation (syntax parsing and test execution).
- F-10: Raw technical English stop reasons leaking into chat bubbles instead of localized user guidance.
"""
import ast
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from core.natural_desktop import NaturalDesktopTask
from core.desktop_broker import DesktopBroker
from tests.test_desktop_broker import FakeBackend


class VerificationAndEvidenceReliabilityTests(unittest.TestCase):
    """Tests verifying separation of model assertion from empirical evidence, and message formatting."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = FakeBackend()
        self.broker = DesktopBroker(self.backend)
        self.desktop = SimpleNamespace(broker=self.broker, windows=self.backend.windows)
        self.events = []
        self.task = NaturalDesktopTask(
            self.desktop,
            lambda *a: self.events.append(a),
            factories={},
            evidence_root=self.root,
        )

    def tearDown(self):
        self.task.stop("teardown")
        self.broker.close()
        self.temp.cleanup()

    def test_reproduce_f07_model_claim_does_not_guarantee_valid_syntax(self):
        """F-07 RISK DEMONSTRATION: Model claims success in prose, but modified code contains syntax errors.

        Without empirical verification (e.g. ast.parse or test run), accepting exit code 0 or model assertion
        allows invalid Python syntax to be reported as completed work.
        """
        model_claim = "Tüm sorunları düzelttim, dosya başarıyla güncellendi ve testler geçiyor."
        broken_code = "def calculate_total(items:\n    return sum(items)\n"  # SyntaxError: invalid syntax

        # Exit code from CLI might be 0 if the process terminated normally
        cli_exit_code = 0

        # Demonstrating that reliance on exit_code and prose claim alone is insufficient
        claim_believed = (cli_exit_code == 0) and ("düzelttim" in model_claim)
        self.assertTrue(claim_believed, "Blind claim accepted based purely on CLI exit code and prose")

        # Empirical verification step: ast.parse catches the syntax error immediately
        with self.assertRaises(SyntaxError):
            ast.parse(broken_code)

    def test_reproduce_f10_raw_technical_stop_reasons_in_chat_event(self):
        """F-10 PROVEN DEFECT: stop(reason) formats raw internal English status strings directly into chat event.

        In core/natural_desktop.py:623:
            self._event("quartz", "Görev yürütmesi sona erdi: " + reason + ". Kanıt sonucu: " + ...
        When reason is 'blocked: foreground changed (user takeover)', the raw English internal diagnostic
        is placed into the user-facing chat bubble without translation.
        """
        self.task.job = {
            "id": "job-10",
            "conversation_id": "conv-10",
            "project": {"path": str(self.root)},
            "roles": {"operator": "codex", "observer": "antigravity"},
            "verification": {"status": "NOT VERIFIED"},
            "task_id": "squad-10",
            "events": [],
        }
        self.task.evidence = self.root / "evidence"
        self.task.evidence.mkdir(parents=True, exist_ok=True)
        self.task.squad = Mock()

        # Stop with foreground takeover reason
        raw_reason = "blocked: foreground changed (user takeover)"
        self.task.stop(raw_reason)

        # Inspect chat event emitted to UI (signature: emit(cid, sender, content, metadata))
        quartz_events = [e for e in self.events if len(e) >= 3 and e[1] == "quartz"]
        self.assertTrue(quartz_events, "No quartz chat event was emitted")

        event_text = quartz_events[0][2]
        # DEFECT CONFIRMED: Raw English internal diagnostic was placed in user chat message
        self.assertIn(
            "blocked: foreground changed (user takeover)",
            event_text,
            "F-10 Defect confirmed: raw technical reason leaked into chat event",
        )

    @unittest.expectedFailure
    def test_contract_f10_stop_reason_should_be_localized_user_message(self):
        """CONTRACT TEST: stop(reason) must map internal stop reasons to friendly Turkish descriptions.

        Marked as expectedFailure until Codex applies localization dictionary mapping before emitting chat event.
        """
        self.task.job = {
            "id": "job-10b",
            "conversation_id": "conv-10b",
            "project": {"path": str(self.root)},
            "roles": {"operator": "codex", "observer": "antigravity"},
            "verification": {"status": "NOT VERIFIED"},
            "task_id": "squad-10b",
            "events": [],
        }
        self.task.evidence = self.root / "evidence-b"
        self.task.evidence.mkdir(parents=True, exist_ok=True)
        self.task.squad = Mock()

        raw_reason = "blocked: foreground changed (user takeover)"
        self.task.stop(raw_reason)

        quartz_events = [e for e in self.events if len(e) >= 3 and e[1] == "quartz"]
        event_text = quartz_events[-1][2]

        # In a localized, human-friendly architecture, raw English diagnostics must NOT be present
        self.assertNotIn("blocked: foreground changed (user takeover)", event_text)
        self.assertIn("kullanıcı müdahalesi" in event_text.lower() or "odak değişti" in event_text.lower(), True)


if __name__ == "__main__":
    unittest.main()
