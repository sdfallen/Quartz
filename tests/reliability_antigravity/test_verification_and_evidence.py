"""Reliability tests for empirical verification, evidence integrity, and user-facing messages.
Covers:
- F-07: Model self-assertion vs empirical validation (syntax parsing and test execution).
- F-10 (FIXED): Internal English stop reasons are localized into clear Turkish user messages.
"""
import ast
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from core.natural_desktop import NaturalDesktopTask
from core.desktop_broker import DesktopBroker
from tests.test_desktop_broker import FakeBackend


class VerificationAndEvidenceReliabilityTests(unittest.TestCase):
    """Tests verifying separation of model assertion from empirical evidence, and localized message formatting."""

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
        """F-07 RISK DEMONSTRATION: Model claims success in prose, but modified code contains syntax errors."""
        model_claim = "Tüm sorunları düzelttim, dosya başarıyla güncellendi ve testler geçiyor."
        broken_code = "def calculate_total(items:\n    return sum(items)\n"
        cli_exit_code = 0
        claim_believed = (cli_exit_code == 0) and ("düzelttim" in model_claim)
        self.assertTrue(claim_believed)
        with self.assertRaises(SyntaxError):
            ast.parse(broken_code)

    def test_f10_verified_no_raw_english_stop_reasons_in_chat_event(self):
        """F-10 VERIFIED FIX: stop(reason) emits localized Turkish explanation without raw English status strings."""
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

        raw_reason = "blocked: foreground changed (user takeover)"
        self.task.stop(raw_reason)

        quartz_events = [e for e in self.events if len(e) >= 3 and e[1] == "quartz"]
        self.assertTrue(quartz_events, "No quartz chat event was emitted")
        event_text = quartz_events[-1][2]
        self.assertNotIn("blocked: foreground changed (user takeover)", event_text)
        self.assertIn("Pencere odağı değiştiği", event_text)

    def test_contract_f10_stop_reason_should_be_localized_user_message(self):
        """CONTRACT TEST (F-10): stop(reason) maps internal stop reasons to friendly Turkish descriptions."""
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

        self.assertNotIn("blocked: foreground changed (user takeover)", event_text)
        self.assertTrue(
            "kullanıcı müdahalesi" in event_text.lower() or "odak değişti" in event_text.lower()
        )


if __name__ == "__main__":
    unittest.main()
