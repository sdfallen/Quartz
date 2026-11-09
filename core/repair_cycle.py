"""Bounded host-owned repair policy; callbacks retain existing writer/process authority.

Not exposed as an agent tool. Chat must supply a reviewed test plan, existing writer
claim, checkpoint function and Stop-aware execution callbacks before using this.
"""
from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class TestObservation:
    exit_code: int
    tests_run: int
    output: str = ''

    @property
    def passed(self):
        return type(self.exit_code) is int and self.exit_code == 0 and type(self.tests_run) is int and self.tests_run > 0


class RepairCycle:
    def __init__(self, *, task_id, writer_id, max_repairs=2):
        if not task_id or not writer_id or type(max_repairs) is not int or not 0 <= max_repairs <= 5:
            raise ValueError('Task, writer and bounded repair count required')
        self.task_id, self.writer_id, self.max_repairs = task_id, writer_id, max_repairs
        self._lock = threading.Lock()
        self._used = False

    def run(self, *, stop: threading.Event, test, checkpoint, repair):
        """test(stop)->TestObservation; repair(writer_id, output, stop)->None.

        The owner must ensure both callbacks cancel their owned process tree when
        Stop is set. This policy never launches a process or expands permissions.
        """
        with self._lock:
            if self._used:
                raise RuntimeError('Repair cycle cannot be replayed')
            self._used = True
        history = []

        def result(status, reason):
            return {'task_id': self.task_id, 'writer_id': self.writer_id,
                    'status': status, 'reason': reason, 'attempts': history,
                    'level': 'HOST TEST RESULT', 'user_accepted': False}

        for attempt in range(self.max_repairs + 1):
            if stop.is_set():
                return result('cancelled', 'Stop requested')
            started = time.monotonic()
            try:
                observed = test(stop)
            except Exception as exc:
                return result('blocked', f'Test infrastructure: {type(exc).__name__}')
            if stop.is_set():
                return result('cancelled', 'Stop requested during test')
            if not isinstance(observed, TestObservation) or type(observed.tests_run) is not int or observed.tests_run <= 0:
                return result('blocked', 'No host-observed tests ran')
            if type(observed.exit_code) is not int:
                return result('blocked', 'Missing host exit code')
            history.append({'attempt': attempt, 'exit_code': observed.exit_code,
                            'tests_run': observed.tests_run, 'elapsed_seconds': time.monotonic() - started})
            if observed.passed:
                return result('tests_passed', 'Reviewed tests passed; whole goal acceptance remains separate')
            if attempt == self.max_repairs:
                return result('failed', 'Repair budget exhausted')
            try:
                saved = checkpoint()
                if (not isinstance(saved, dict) or saved.get('complete') is not True
                        or saved.get('status') not in {'git', 'snapshot'}
                        or not (saved.get('ref') or saved.get('archive'))):
                    return result('blocked', 'Checkpoint not confirmed')
                history[-1]['checkpoint'] = saved.get('ref') or saved.get('archive')
                if stop.is_set():
                    return result('cancelled', 'Stop requested before repair')
                repair(self.writer_id, observed.output[-16000:], stop)
            except Exception as exc:
                return result('blocked', f'Repair infrastructure: {type(exc).__name__}')
        raise AssertionError('Unreachable')
