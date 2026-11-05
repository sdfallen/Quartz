import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from scripts.exam_process import ExamProcess


@unittest.skipUnless(os.name=='nt','Windows kernel job containment')
class ExamProcessTests(unittest.TestCase):
    def test_exited_root_with_living_child_is_not_verified(self):
        import psutil
        with tempfile.TemporaryDirectory() as directory:
            pidfile=Path(directory)/'child.pid'
            child='import time; time.sleep(60)'
            parent=f'import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c",{child!r}]); Path({str(pidfile)!r}).write_text(str(p.pid)); time.sleep(.4)'
            owner=ExamProcess()
            try:
                p=owner.launch([sys.executable,'-c',parent],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                until=time.monotonic()+8
                while not pidfile.exists() and time.monotonic()<until:time.sleep(.02)
                self.assertTrue(pidfile.exists())
                identity=psutil.Process(int(pidfile.read_text()))
                p.wait(timeout=8)
                self.assertFalse(owner.cleanup())
                self.assertFalse(owner.cleanup())  # Closing the job cannot turn uncertainty into success.
                # Windows can retain a terminated PID while query handles live.
                # Waiting on the creation-bound process proves actual exit.
                self.assertIsNotNone(identity.wait(timeout=3))
            finally:owner.cleanup(force=True)

    def test_normal_process_empty_job_confirms(self):
        owner=ExamProcess()
        try:
            p=owner.launch([sys.executable,'-c','pass'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            p.wait(timeout=8)
            self.assertTrue(owner.cleanup())
        finally:owner.cleanup(force=True)
