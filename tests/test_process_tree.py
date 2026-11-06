import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import psutil

from core.process_tree import CREATE_SUSPENDED, bind_kill_on_close_job, stop_process_tree


class ProcessTreeTests(unittest.TestCase):
    def test_cancel_stops_owned_child(self):
        child_code = "import time; time.sleep(60)"
        parent_code = (
            "import subprocess,sys,time; "
            f"p=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
            "print(p.pid,flush=True); time.sleep(60)"
        )
        parent = subprocess.Popen([sys.executable, "-c", parent_code],
                                  stdout=subprocess.PIPE, text=True,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        child_pid = int(parent.stdout.readline().strip())
        try:
            stop_process_tree(parent, timeout=3)
            self.assertIsNotNone(parent.poll())
            self.assertFalse(psutil.pid_exists(child_pid))
        finally:
            if parent.poll() is None:
                parent.kill()
            if psutil.pid_exists(child_pid):
                psutil.Process(child_pid).kill()
            parent.wait(timeout=3)
            parent.stdout.close()

    @unittest.skipUnless(os.name == "nt", "Windows Job Object crash cleanup")
    def test_abrupt_parent_crash_reaps_child_and_grandchild_via_job_object(self):
        repo_root = str(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory(prefix="quartz-job-crash-") as tmp:
            root = Path(tmp)
            pid_file = root / "grandchild.pid"
            child_script = root / "child.py"
            child_script.write_text(
                "import subprocess, sys, time, pathlib\n"
                "gc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                "pathlib.Path(sys.argv[1]).write_text(str(gc.pid), encoding='utf-8')\n"
                "time.sleep(60)\n",
                encoding="utf-8",
            )
            parent_code = (
                f"import subprocess, sys, time; sys.path.insert(0, {repo_root!r}); "
                "from core.process_tree import CREATE_SUSPENDED, bind_kill_on_close_job; "
                f"p = subprocess.Popen([sys.executable, {str(child_script)!r}, {str(pid_file)!r}], "
                "creationflags=CREATE_SUSPENDED); "
                "ok = bind_kill_on_close_job(p, resume=True); "
                "print(f'{p.pid}:{int(ok)}:{int(getattr(p, \"_quartz_resumed\", False))}', flush=True); "
                "time.sleep(60)"
            )
            quartz_sim = subprocess.Popen(
                [sys.executable, "-c", parent_code],
                stdout=subprocess.PIPE,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                line = quartz_sim.stdout.readline().strip()
                child_pid_str, bound_str, resumed_str = line.split(":")
                child_pid = int(child_pid_str)
                self.assertEqual(bound_str, "1")
                self.assertEqual(resumed_str, "1")
                for _ in range(50):
                    if pid_file.is_file() and pid_file.read_text(encoding="utf-8").strip():
                        break
                    time.sleep(0.05)
                grandchild_pid = int(pid_file.read_text(encoding="utf-8").strip())
                self.assertTrue(psutil.pid_exists(child_pid))
                self.assertTrue(psutil.pid_exists(grandchild_pid))

                # Abruptly kill quartz_sim (TerminateProcess) without any Python shutdown/finally running
                quartz_sim.kill()
                quartz_sim.wait(timeout=5)
                for _ in range(40):
                    if not psutil.pid_exists(child_pid) and not psutil.pid_exists(grandchild_pid):
                        break
                    time.sleep(0.05)
                self.assertFalse(psutil.pid_exists(child_pid))
                self.assertFalse(psutil.pid_exists(grandchild_pid))
            finally:
                if quartz_sim.poll() is None:
                    quartz_sim.kill()
                quartz_sim.stdout.close()

    @unittest.skipUnless(os.name == "nt", "Windows CREATE_SUSPENDED + Job Object failure handling")
    def test_r3_job_assignment_failure_logs_error_and_resumes_suspended_process(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('resumed-ok', flush=True)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | CREATE_SUSPENDED,
        )
        errors: list[str] = []
        try:
            with patch("core.process_tree.ctypes.windll.kernel32.AssignProcessToJobObject", return_value=0):
                with self.assertLogs("core.process_tree", level="WARNING") as captured_logs:
                    ok = bind_kill_on_close_job(proc, resume=True, error_sink=errors.append)
            self.assertFalse(ok)
            self.assertEqual(len(errors), 1)
            self.assertIn("AssignProcessToJobObject failed", errors[0])
            self.assertIn("AssignProcessToJobObject failed", getattr(proc, "_quartz_job_error", ""))
            self.assertTrue(any("AssignProcessToJobObject failed" in msg for msg in captured_logs.output))
            self.assertTrue(getattr(proc, "_quartz_resumed", False))
            out, _ = proc.communicate(timeout=5)
            self.assertEqual(out.strip(), "resumed-ok")
            self.assertEqual(proc.returncode, 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
