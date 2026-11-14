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


_SEPARATORS = re.compile(r"(\|\||&&|;|\|)")
_ECHO_STATUS = re.compile(r"^\s*echo\b.*\$\?")
_PRINTED_STATUS = re.compile(r"(?:exit(?:[\s_-]*code)?\s*[=:]?\s*)(-?\d+)\s*$", re.IGNORECASE)


def _test_exit_code(record):
    """The test's own exit code, or None when the command hides it.

    Live 14 Nov: Fatum ran `node tests/validate.test.js; echo "exit=$?"`. The command's
    status is echo's, so a failing test would still look like a success. A test followed by
    `;`, `|` or `||` hides its status; `; echo ... $?` prints it, and that printed value is
    read from the output. `&&` after the test keeps it honest (a failure stops the chain).
    """
    command = str(record.get("command") or "")
    parts = _SEPARATORS.split(command)
    index = next((i for i in range(0, len(parts), 2) if is_test_command(parts[i])), None)
    status = record.get("exit_code")
    if not record.get("ok") or record.get("state") == "ERROR":
        status = status if status not in (None, 0) else 1
    tail = parts[index + 1:] if index is not None else []
    if not tail or all(sep == "&&" for sep in tail[0::2]):
        return status
    if tail[0] == ";" and len(tail) > 1 and _ECHO_STATUS.match(tail[1]):
        lines = [line for line in str(record.get("output") or "").strip().splitlines() if line.strip()]
        found = _PRINTED_STATUS.search(lines[-1]) if lines else None
        if found:
            return int(found.group(1))
        if lines and lines[-1].strip().lstrip("-").isdigit():
            return int(lines[-1].strip())
    return None


def agent_test_result(command_results) -> dict | None:
    """The outcome of the test commands an agent ran, or None when it ran none.

    The last test run decides: "fix, run again, pass" counts as passed. A run whose own
    exit status is hidden by the command line is "RAN": it ran, the result is unknown.
    """
    runs = [r for r in (command_results or []) if isinstance(r, dict) and is_test_command(r.get("command"))]
    if not runs:
        return None
    last = runs[-1]
    code = _test_exit_code(last)
    status = "RAN" if code is None else "PASSED" if code == 0 else "FAILED"
    return {"level": "AGENT RUN", "status": status, "exit_code": code,
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
    if tests == "RAN":
        return "warn", "Test çalıştı; sonucu ayırt edilemedi"
    if source == "VERIFIED":
        return "warn", "Sözdizimi doğrulandı; test kanıtı yok"
    return "warn", "Bağımsız kanıt yok"
