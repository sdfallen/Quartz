"""Test runs observed in an agent's command stream (freelance trial, 14 Nov 2026).

The Kafe Lavanta job passed 18/18 Node tests, yet SpeS showed "Kanıt yok": it only
looked at its own Python syntax check. The CLI runtimes already record every shell
command with its exit status from the tool events (not from the model's text). This
module picks the test commands out of that record.

Evidence level: AGENT RUN, observed. SpeS did not run the tests itself, so the UI
says so; a passing run is stronger than a claim, weaker than a host re-run.
"""
from __future__ import annotations

import re

_TEST_COMMAND = re.compile(
    r"(?:^|[\s;&|(\"'])(?:"
    r"node\s+(?:--test\b|\S*(?:test|spec)\S*\.(?:c|m)?js\b)"
    r"|(?:npm|pnpm|yarn)\s+(?:run\s+)?test\b|npx\s+(?:jest|vitest|mocha)\b|(?:jest|vitest|mocha)\b"
    r"|(?:python3?|py)(?:\s+-\S+)*\s+-m\s+(?:pytest|unittest)\b|pytest\b"
    r"|(?:python3?|py)(?:\s+-\S+)*\s+\S*(?:run_safe_tests|test_\w+|\w+_test)\.py\b"
    r"|go\s+test\b|cargo\s+test\b|dotnet\s+test\b|mvn\s+(?:-\S+\s+)*test\b|gradlew?\s+test\b"
    r")", re.IGNORECASE)


def is_test_command(command: str) -> bool:
    return bool(_TEST_COMMAND.search(str(command or "")))


def agent_test_result(command_results) -> dict | None:
    """The outcome of the test commands an agent ran, or None when it ran none.

    The last test run decides: "fix, run again, pass" counts as passed.
    """
    runs = [r for r in (command_results or []) if isinstance(r, dict) and is_test_command(r.get("command"))]
    if not runs:
        return None
    last = runs[-1]
    passed = bool(last.get("ok")) and last.get("exit_code") in (0, None) and last.get("state") != "ERROR"
    return {"level": "AGENT RUN", "status": "PASSED" if passed else "FAILED",
            "command": str(last.get("command") or "")[:200], "runs": len(runs)}


def evidence_label(host_evidence, outcome=None):
    """(tone, short label) for a finished write turn; the desktop badge mirrors this in JS."""
    ev = host_evidence if isinstance(host_evidence, dict) else {}
    verdict = (outcome or {}).get("goal_verdict")
    source = (ev.get("source_validation") or {}).get("status")
    tests = (ev.get("agent_tests") or {}).get("status")
    if verdict == "VERIFIED":
        return "ok", "Hedef doğrulandı"
    if source == "FAILED":
        return "fail", "Kontrol başarısız"
    if tests == "FAILED":
        return "fail", "Test başarısız"
    if tests == "PASSED":
        return "ok", "Testler geçti (ajan çalıştırdı)"
    if source == "VERIFIED":
        return "warn", "Sözdizimi doğrulandı; test kanıtı yok"
    return "warn", "Bağımsız kanıt yok"
