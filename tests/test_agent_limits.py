"""Limit indicator data: Codex session logs, Claude stream events, honest unknowns."""
import json
import tempfile
import unittest
from pathlib import Path

from core import agent_limits


class CodexLimitTests(unittest.TestCase):
    def test_latest_rate_limits_are_read_from_the_session_tail(self):
        with tempfile.TemporaryDirectory() as home:
            day = Path(home) / "sessions" / "2026" / "11" / "13"
            day.mkdir(parents=True)
            old = {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {
                "primary": {"used_percent": 5.0, "resets_at": 1}, "secondary": {"used_percent": 60.0}}}}
            new = {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {
                "primary": {"used_percent": 82.0, "resets_at": 99}, "secondary": {"used_percent": 66.0}}}}
            (day / "rollout-x.jsonl").write_text(
                "\n".join([json.dumps(old), '{"type":"message","text":"hi"}', json.dumps(new)]), encoding="utf-8")
            entry = agent_limits.codex_limits(home)
        self.assertEqual((entry["five_hour"], entry["week"], entry["resets_at"]), (82.0, 66.0, 99))
        self.assertEqual(entry["state"], "warn")

    def test_no_sessions_is_unknown(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(agent_limits.codex_limits(home)["state"], "unknown")


class ClaudeLimitTests(unittest.TestCase):
    def test_stream_event_is_stored_and_read_back(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "limits.json"
            event = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": {
                "five_hour": {"utilization": 0.21, "resetsAt": 123}, "seven_day": {"utilization": 0.33}}}}
            agent_limits.record_claude_event(event, store)
            entry = agent_limits.claude_limits(store)
            self.assertEqual((entry["five_hour"], entry["week"], entry["resets_at"], entry["state"]), (21.0, 33.0, 123, "ok"))
            agent_limits.record_claude_event({"rate_limit_info": {"status": "rejected", "unifiedWindows": {}}}, store)
            self.assertEqual(agent_limits.claude_limits(store)["state"], "full")

    def test_snapshot_reports_antigravity_as_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            data = agent_limits.snapshot(directory, Path(directory) / "none.json")
        self.assertEqual(set(data), {"codex", "claude", "antigravity"})
        self.assertEqual(data["antigravity"]["state"], "unknown")
        self.assertEqual(data["antigravity"]["source"], "unavailable")


if __name__ == "__main__":
    unittest.main()
