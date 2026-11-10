import threading
import unittest
from core.repair_cycle import RepairCycle, TestObservation


class RepairCycleTests(unittest.TestCase):
    def run_cycle(self, observations, **overrides):
        self.writes, self.saves = [], []
        def checkpoint():
            self.saves.append(True)
            return {'complete': True, 'status': 'snapshot', 'archive': 'fixture-checkpoint'}
        def repair(writer, output, stop):
            self.writes.append((writer, output))
        args = {'stop': threading.Event(), 'test': lambda stop: next(observations),
                'checkpoint': checkpoint, 'repair': repair}
        args.update(overrides)
        return RepairCycle(task_id='task', writer_id='original-writer').run(**args)

    def test_failure_is_returned_to_same_writer_then_retested(self):
        result = self.run_cycle(iter([TestObservation(1, 3, 'assertion failed'), TestObservation(0, 3)]))
        self.assertEqual(result['status'], 'tests_passed')
        self.assertEqual(self.writes, [('original-writer', 'assertion failed')])
        self.assertEqual(len(self.saves), 1)
        self.assertFalse(result['user_accepted'])

    def test_zero_tests_never_pass_or_trigger_repair(self):
        self.assertEqual(self.run_cycle(iter([TestObservation(0, 0)]))['status'], 'blocked')
        self.assertEqual(self.writes, [])

    def test_budget_exhaustion(self):
        result = self.run_cycle(iter([TestObservation(1, 2)] * 3))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(len(self.writes), 2)

    def test_checkpoint_failure_prevents_write(self):
        result = self.run_cycle(iter([TestObservation(1, 1)]), checkpoint=lambda: {'complete': False})
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(self.writes, [])

    def test_stop_during_test_prevents_repair(self):
        stop = threading.Event()
        def test(event):
            event.set()
            return TestObservation(1, 3)
        self.assertEqual(self.run_cycle(iter([]), stop=stop, test=test)['status'], 'cancelled')
        self.assertEqual(self.writes, [])

    def test_stop_after_checkpoint_prevents_repair(self):
        stop = threading.Event()
        def checkpoint():
            stop.set()
            return {'complete': True, 'status': 'git', 'ref': 'fixture-ref'}
        self.assertEqual(self.run_cycle(iter([TestObservation(1, 1)]), stop=stop, checkpoint=checkpoint)['status'], 'cancelled')
        self.assertEqual(self.writes, [])

    def test_cycle_is_single_use(self):
        cycle = RepairCycle(task_id='t', writer_id='w')
        args = dict(stop=threading.Event(), test=lambda _: TestObservation(0, 1), checkpoint=lambda: {}, repair=lambda *_: None)
        cycle.run(**args)
        with self.assertRaises(RuntimeError):
            cycle.run(**args)

    def test_deleted_tests_cannot_pass(self):
        result = self.run_cycle(iter([TestObservation(1, 8), TestObservation(0, 1)]))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['reason'], 'Host test count decreased')

    def test_manifest_change_cannot_pass(self):
        result = self.run_cycle(iter([TestObservation(1, 8, test_manifest=(('test.py', 'old'),)),
                                      TestObservation(0, 8, test_manifest=(('test.py', 'new'),))]))
        self.assertEqual(result['status'], 'blocked')

    def test_stop_exception_is_cancelled_in_both_callbacks(self):
        for phase in ('test', 'repair'):
            with self.subTest(phase=phase):
                stop = threading.Event()
                def interrupted(*args):
                    stop.set()
                    raise RuntimeError('cancelled owned process')
                result = self.run_cycle(iter([TestObservation(1, 2)]), stop=stop, **{phase: interrupted})
                self.assertEqual(result['status'], 'cancelled')
