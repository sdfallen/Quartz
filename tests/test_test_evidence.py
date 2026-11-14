"""Agent-run tests as evidence (freelance trial 14 Nov: 18/18 passed, badge said "Kanıt yok")."""
import unittest

from core.finish_report import collect_facts
from core.test_evidence import agent_test_result, evidence_label, is_test_command
from mobile_server import MobileGateway


def run(command, ok=True, exit_code=0):
    return {"command": command, "ok": ok, "exit_code": exit_code if ok else (exit_code or 1),
            "state": "DONE" if ok else "ERROR"}


class TestCommandTests(unittest.TestCase):
    def test_common_test_runners_are_recognised(self):
        for command in ("node tests/validate.test.js", "node --test tests/", "npm test", "npm run test",
                        "pnpm test", "npx vitest run", "python -m pytest -q", "py -3 -m unittest discover",
                        "pytest tests/test_app.py", "python -B scripts/run_safe_tests.py", "go test ./...",
                        "cargo test", "dotnet test", "cd app && npm test"):
            self.assertTrue(is_test_command(command), command)
        for command in ("node server.js", "npm install", "python app.py", "git status", "echo test",
                        "cat tests/validate.test.js", "ls tests"):
            self.assertFalse(is_test_command(command), command)

    def test_the_last_test_run_decides(self):
        self.assertIsNone(agent_test_result([run("npm install"), run("node app.js")]))
        fixed = agent_test_result([run("node --test", ok=False), run("git diff"), run("node --test")])
        self.assertEqual((fixed["status"], fixed["runs"], fixed["level"]), ("PASSED", 2, "AGENT RUN"))
        broke = agent_test_result([run("pytest -q"), run("pytest -q", ok=False)])
        self.assertEqual(broke["status"], "FAILED")
        self.assertEqual(agent_test_result([run("pytest -q", ok=True, exit_code=2)])["status"], "FAILED")

    def test_a_hidden_exit_status_is_read_or_reported_as_unknown(self):
        # Live 14 Nov: `node tests/validate.test.js; echo "exit=$?"` always exits 0.
        echo = 'node tests/validate.test.js; echo "exit=$?"'
        self.assertEqual(agent_test_result([{**run(echo), "output": "41 geçti\nexit=0"}])["status"], "PASSED")
        self.assertEqual(agent_test_result([{**run(echo), "output": "3 başarısız\nexit=1"}])["status"], "FAILED")
        self.assertEqual(agent_test_result([{**run("pytest -q; echo $?"), "output": "1 failed\n1"}])["status"], "FAILED")
        for hidden in ("npm test | tail -5", "pytest -q || true", "node --test; ls", echo):
            with self.subTest(hidden=hidden):
                self.assertEqual(agent_test_result([{**run(hidden), "output": "ok"}])["status"], "RAN")
        self.assertEqual(agent_test_result([run("cd app && npm test")])["status"], "PASSED")
        self.assertEqual(agent_test_result([run("npm test && echo done")])["status"], "PASSED")
        self.assertEqual(evidence_label({"agent_tests": {"status": "RAN"}}), ("warn", "Test çalıştı; sonucu ayırt edilemedi"))

    def test_label_precedence(self):
        self.assertEqual(evidence_label({"agent_tests": {"status": "PASSED"}}), ("ok", "Testler geçti (ajan çalıştırdı)"))
        self.assertEqual(evidence_label({"agent_tests": {"status": "FAILED"}, "source_validation": {"status": "VERIFIED"}}),
                         ("fail", "Test başarısız"))
        self.assertEqual(evidence_label({"agent_tests": {"status": "PASSED"}, "source_validation": {"status": "FAILED"}}),
                         ("fail", "Kontrol başarısız"))
        self.assertEqual(evidence_label({}, {"goal_verdict": "VERIFIED"}), ("ok", "Hedef doğrulandı"))
        self.assertEqual(evidence_label({}), ("warn", "Bağımsız kanıt yok"))

    def test_phone_and_finish_report_read_the_test_evidence(self):
        messages = [
            {"id": "u", "role": "user", "content": "Siteyi yap, bitince haber ver"},
            {"id": "a", "role": "assistant", "sender": "claude", "content": "Yazdım.",
             "metadata": {"sender": "claude", "host_evidence": {"files_changed": ["index.html"],
                                                                "agent_tests": {"status": "PASSED", "runs": 1}}}}]
        checks = MobileGateway._evidence(messages)["checks"]
        self.assertEqual((checks[0]["tone"], checks[0]["label"]), ("ok", "Testler geçti (ajan çalıştırdı)"))
        self.assertIn("testler geçti, ajan çalıştırdı (Fatum)", collect_facts(messages, "u", "completed")["checks"])


if __name__ == "__main__":
    unittest.main()
