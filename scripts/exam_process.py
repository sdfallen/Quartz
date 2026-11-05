"""Creation-time kernel ownership for exam children, including orphan descendants."""
import os
import signal
import subprocess
import threading
import time
from contextlib import contextmanager


@contextmanager
def deferred_interrupt():
    pending = [False]
    main = threading.current_thread() is threading.main_thread()
    old = signal.getsignal(signal.SIGINT) if main else None
    if main: signal.signal(signal.SIGINT, lambda *_: pending.__setitem__(0, True))
    try: yield pending
    finally:
        if main: signal.signal(signal.SIGINT, old)


class ExamProcess:
    def __init__(self):
        self.process = None
        self.job = None
        self.receipt = None
        self.interrupted = False

    def launch(self, command, **kwargs):
        if os.name != 'nt':
            raise PermissionError('Exam execution needs reviewed kernel containment on this platform')
        import psutil
        from core.tool_workbench.execution import _WindowsJob
        self.job = _WindowsJob()
        try:
            with deferred_interrupt() as pending:
                self.process = subprocess.Popen(command, creationflags=0x08000000 | 0x4, **kwargs)
                self.job.assign(self.process)
                psutil.Process(self.process.pid).resume()
            if pending[0]: raise KeyboardInterrupt
            return self.process
        except BaseException:
            self.cleanup(force=True)
            raise

    def cleanup(self, *, force=False):
        """Do not certify an exited root while the kernel still owns descendants."""
        if self.receipt is not None: return self.receipt
        try:
            with deferred_interrupt() as pending:
                self.receipt = self._cleanup(force=force)
            self.interrupted = self.interrupted or pending[0]
        except (OSError, subprocess.TimeoutExpired):
            if self.job: self.job.close()
            self.receipt = False
        return self.receipt

    def _cleanup(self, *, force):
        if not self.process:
            if self.job: self.job.close()
            return True
        if not self.job or not self.job.assigned:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=3)
            if self.job: self.job.close()
            return False  # No descendant-coverage proof.
        if force or self.process.poll() is None:
            self.job.terminate()
        until = time.monotonic() + 2
        while not self.job.empty() and time.monotonic() < until: time.sleep(.02)
        empty = self.job.empty()
        if not empty:
            self.job.terminate()
            until = time.monotonic() + 2
            while not self.job.empty() and time.monotonic() < until: time.sleep(.02)
        confirmed = self.job.empty()
        self.job.close()  # KILL_ON_JOB_CLOSE is a final fail-safe, not proof.
        self.process.wait(timeout=3)
        return confirmed and (empty or force)
