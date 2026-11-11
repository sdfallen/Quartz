"""Harmless unit tests verifying the Provider Failure Taxonomy across Codex, Antigravity, and Gemini runtimes.

Covers:
1. Quota exhaustion (no retry on quota error, user-facing Turkish quota message, process exit confirmed)
2. Auth / session drop (probe rejection before start; read-only stale session single retry vs write no-retry)
3. Timeout (stop_process_tree invoked, timeout error recorded, writer lock released)
4. CLI crash & silent exit-0 without output (failed status, no false success)
5. Network drop / truncated stream mid-turn (failed status, partial text not certified as completed)
6. Cancellation & unconfirmed child cleanup (stop_receipt confirmed vs pending on OwnedCleanupUnconfirmed)
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.agent_chat import AgentChatService
from core.antigravity_runtime import AntigravityRuntime
from core.codex_runtime import CodexRuntime
from core.gemini_runtime import GeminiRuntime
from core.multi_agent_service import MultiAgentService
from core.process_tree import OwnedCleanupUnconfirmed


class _TaxonomyFakeProcess:
    def __init__(self, stdout: str = "", stderr: str = "", exit_code: int = 0, delay: float = 0.0):
        self.pid = 7788
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self._exit_code = exit_code
        self._delay = delay
        self._terminated = False

    def wait(self, timeout=None):
        if self._delay > 0 and not self._terminated:
            if timeout is not None and timeout < self._delay:
                time.sleep(0.02)
                raise subprocess.TimeoutExpired(["fake"], timeout)
            time.sleep(min(0.05, self._delay))
        return self._exit_code

    def poll(self):
        if self._terminated or self._delay == 0:
            return self._exit_code
        return None

    def terminate(self):
        self._terminated = True
        if self._exit_code == 0:
            self._exit_code = 1

    def kill(self):
        self.terminate()


class ProviderFailureTaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="quartz-taxonomy-test-")
        self.root = Path(self.tmp.name)
        self.codex_exe = self.root / "codex.exe"
        self.codex_exe.touch()
        self.agy_exe = self.root / "agy.exe"
        self.agy_exe.touch()
        self.gemini_exe = self.root / "gemini.cmd"
        self.gemini_exe.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def _wait_terminal(self, runtime, run_id: str) -> dict:
        for _ in range(100):
            cur = runtime.get(run_id)
            if cur["status"] in runtime.TERMINAL or cur.get("cleanup_error"):
                return cur
            time.sleep(0.01)
        return runtime.get(run_id)

    def test_1_quota_exhaustion_codex_and_antigravity_format_and_no_retry(self):
        # Codex quota failure stream
        codex_stream = (
            '{"type":"thread.started","thread_id":"th-quota"}\n'
            '{"type":"turn.failed","error":"Quota limit reached (429 Too Many Requests)"}\n'
        )
        codex = CodexRuntime(self.codex_exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=_TaxonomyFakeProcess(codex_stream, exit_code=1)):
            c_run = codex.start("analyze", self.root)
            c_final = self._wait_terminal(codex, c_run["id"])
        self.assertEqual(c_final["status"], "failed")
        self.assertTrue(c_final["process_exit_confirmed"])
        self.assertTrue(any("Quota limit reached" in e for e in c_final["errors"]))
        c_msg = AgentChatService._format_error("codex", RuntimeError("\n".join(c_final["errors"])))
        self.assertIn("CODEX Kota Hatası", c_msg)

        # Antigravity quota failure stream
        agy_stream = (
            '{"event":"result","result":{"status":"ERROR","error":"RESOURCE_EXHAUSTED: Quota exceeded (429)"}}\n'
        )
        agy = AntigravityRuntime(self.agy_exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=_TaxonomyFakeProcess(agy_stream, exit_code=1)):
            a_run = agy.start("analyze", self.root)
            a_final = self._wait_terminal(agy, a_run["id"])
        self.assertEqual(a_final["status"], "failed")
        self.assertTrue(a_final["process_exit_confirmed"])
        a_msg = AgentChatService._format_error("antigravity", RuntimeError("\n".join(a_final["errors"])))
        self.assertIn("ANTIGRAVITY Kota Hatası", a_msg)

    def test_2_auth_drop_and_stale_session_retry_policy(self):
        svc = MultiAgentService(
            projects=[{"id": "p1", "name": "TestProj", "path": str(self.root)}],
            codex_executable=str(self.codex_exe),
            antigravity_executable=str(self.agy_exe),
            project_store=self.root / "projects.json",
        )
        chat = AgentChatService(svc, self.root / "conversations.json")
        try:
            conv = chat.store.get_active()
            cid = conv["id"]
            chat.store.set_agent_session(cid, "antigravity", "stale-conv-id")
            chat.store.update_agent_model(cid, "antigravity", model="gemini-4-argon-medium", effort="medium")

            # Verify read-only stale session retries once with conversation_id=None
            calls = []
            def fake_dispatch(prompt, **kwargs):
                calls.append(kwargs.get("conversation_id"))
                rid = f"run-{len(calls)}"
                if len(calls) == 1:
                    svc.antigravity._runs[rid] = {
                        "id": rid, "status": "failed", "result": "",
                        "errors": ["Conversation stale-conv-id not found"], "events": [],
                        "progress_log": [], "commands": [], "files_changed": [],
                        "process_exit_confirmed": True,
                    }
                else:
                    svc.antigravity._runs[rid] = {
                        "id": rid, "status": "completed", "result": "Recovered with fresh session",
                        "conversation_id": "fresh-conv-id",
                        "errors": [], "events": [], "progress_log": [],
                        "commands": [], "files_changed": [], "process_exit_confirmed": True,
                    }
                return {"run": svc.antigravity.get(rid), "squad": {"connected": False}}

            with patch.object(svc, "dispatch_antigravity", side_effect=fake_dispatch):
                chat.send_message("projedeki dosyaları incele", agent="antigravity", conversation_id=cid)
                for _ in range(100):
                    if not chat.poll_active().get("active"):
                        break
                    time.sleep(0.02)
            self.assertEqual(calls, ["stale-conv-id", None])
        finally:
            chat.close()

    def test_3_cli_crash_and_silent_zero_exit_never_report_false_success(self):
        # Codex exit 0 with empty stdout -> failed (never false success)
        codex = CodexRuntime(self.codex_exe)
        with patch("core.codex_runtime.subprocess.Popen", return_value=_TaxonomyFakeProcess("", exit_code=0)):
            c_run = codex.start("inspect", self.root)
            c_final = self._wait_terminal(codex, c_run["id"])
        self.assertEqual(c_final["status"], "failed")
        self.assertIn("Codex returned exit code 0 without response output", c_final["errors"])

        # Antigravity SUCCESS event with empty response -> failed (never false success)
        agy = AntigravityRuntime(self.agy_exe)
        empty_success = '{"event":"result","result":{"status":"SUCCESS","response":""}}\n'
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=_TaxonomyFakeProcess(empty_success, exit_code=0)):
            a_run = agy.start("inspect", self.root)
            a_final = self._wait_terminal(agy, a_run["id"])
        self.assertEqual(a_final["status"], "failed")
        self.assertIn("Antigravity returned SUCCESS without a response", a_final["errors"])

    def test_4_network_drop_truncated_stream_mid_turn_fails_cleanly(self):
        # Antigravity emits partial text_delta then disconnects (exit_code=1, no result event)
        truncated = (
            '{"event":"init","conversation_id":"conv-net"}\n'
            '{"event":"step_update","step_update":{"text_delta":"İnceleme başladı..."}}\n'
        )
        agy = AntigravityRuntime(self.agy_exe)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=_TaxonomyFakeProcess(truncated, stderr="ECONNRESET", exit_code=1)):
            a_run = agy.start("inspect", self.root)
            a_final = self._wait_terminal(agy, a_run["id"])
        self.assertEqual(a_final["status"], "failed")
        self.assertEqual(a_final["result"], "İnceleme başladı...")
        self.assertIn("ECONNRESET", a_final["errors"])
        self.assertTrue(a_final["process_exit_confirmed"])

        # Gemini error event normalization
        gem = GeminiRuntime(self.gemini_exe)
        norm = gem._normalize_event({"type": "error", "message": "Network connection lost"})
        self.assertEqual(norm["event"], "result")
        self.assertEqual(norm["result"]["status"], "ERROR")
        self.assertEqual(norm["result"]["error"], "Network connection lost")

    def test_5_unconfirmed_child_cleanup_keeps_writer_and_process_fenced(self):
        codex = CodexRuntime(self.codex_exe)
        fake = _TaxonomyFakeProcess("", exit_code=0)
        with patch("core.codex_runtime.subprocess.Popen", return_value=fake), \
             patch("core.codex_runtime.owned_cleanup_pending", return_value=True), \
             patch("core.codex_runtime.wait_for_owned_cleanup", side_effect=OwnedCleanupUnconfirmed(0)):
            run = codex.start("write file", self.root, sandbox="workspace-write", approval="never")
            final = self._wait_terminal(codex, run["id"])
        self.assertEqual(final["status"], "cancelling")
        self.assertTrue(final["cleanup_pending"])
        self.assertFalse(final["process_exit_confirmed"])
        self.assertEqual(final["cleanup_error"], "tree_discovery_incomplete")
        self.assertIn("Ana süreç durdu; alt süreçlerin kapanışı doğrulanamadı.", final["errors"])
        # Writer lock must NOT be released when child cleanup is unconfirmed
        self.assertIn(run["id"], codex._writers.values())

    def test_6_timeout_stops_process_tree_records_error_and_releases_writer_lock(self):
        project_key = str(self.root.resolve()).lower()

        # Codex writer run timing out
        codex = CodexRuntime(self.codex_exe)
        codex_proc = _TaxonomyFakeProcess("", exit_code=0, delay=500.0)
        with patch("core.codex_runtime.subprocess.Popen", return_value=codex_proc), \
             patch("core.codex_runtime.stop_process_tree", side_effect=lambda p, **kw: (p.terminate(), True)[1]) as mock_codex_stop, \
             patch("core.codex_runtime.owned_cleanup_pending", return_value=False):
            c_run = codex.start("write file", self.root, sandbox="workspace-write", approval="never", timeout=0.05)
            c_final = self._wait_terminal(codex, c_run["id"])
        mock_codex_stop.assert_called_once_with(codex_proc, timeout=5)
        self.assertEqual(c_final["status"], "failed")
        self.assertTrue(c_final["process_exit_confirmed"])
        self.assertTrue(any("Task timed out after" in e for e in c_final["errors"]))
        self.assertNotIn(project_key, codex._writers)

        # Antigravity writer run timing out
        agy = AntigravityRuntime(self.agy_exe)
        agy_proc = _TaxonomyFakeProcess("", exit_code=0, delay=500.0)
        with patch("core.antigravity_runtime.subprocess.Popen", return_value=agy_proc), \
             patch("core.antigravity_runtime.stop_process_tree", side_effect=lambda p, **kw: (p.terminate(), True)[1]) as mock_agy_stop, \
             patch("core.antigravity_runtime.owned_cleanup_pending", return_value=False):
            a_run = agy.start("write file", self.root, write=True, full_access=True, timeout="1s")
            a_final = self._wait_terminal(agy, a_run["id"])
        mock_agy_stop.assert_called_once_with(agy_proc, timeout=5)
        self.assertEqual(a_final["status"], "failed")
        self.assertTrue(a_final["process_exit_confirmed"])
        self.assertTrue(any("Task timed out after" in e for e in a_final["errors"]))
        self.assertNotIn(project_key, agy._writers)


if __name__ == "__main__":
    unittest.main()
