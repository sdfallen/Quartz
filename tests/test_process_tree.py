import subprocess
import sys
import unittest

import psutil

from core.process_tree import stop_process_tree


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
