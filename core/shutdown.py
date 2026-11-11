"""Owned, single-flight backend cleanup and truthful retryable receipts."""
from copy import deepcopy
from dataclasses import dataclass, field
import threading
import time


@dataclass
class ShutdownReceipt:
    status: str
    components: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        return deepcopy(vars(self))


class ShutdownCoordinator:
    def __init__(self):
        self._lock = threading.RLock()
        self._pass_lock = threading.Lock()
        self._admission_closed = False
        self._operations = {}
        self._receipt = None
        self._started = False
        self._requests = 0

    def enter_request(self):
        with self._lock:
            if self._admission_closed: return False
            self._requests += 1
            return True

    def leave_request(self):
        with self._lock:
            self._requests -= 1

    def requests_pending(self):
        with self._lock:
            return self._requests > 0

    def is_admission_closed(self):
        with self._lock:
            return self._admission_closed

    def close_admission(self):
        with self._lock:
            self._admission_closed = True

    def _snapshot(self):
        # Called under _lock. An operation's actual thread is retained even
        # after a bounded join expires. Late results cannot cross owners.
        components, errors = {}, []
        for name, op in self._operations.items():
            worker = op.get('thread')
            if worker is None or worker.is_alive():
                value = {'status':'pending'}
                if op.get('timed_out'): value['error'] = 'TimeoutExpired'
            else:
                value = deepcopy(op['result'])
            components[name] = value
            if value.get('error'): errors.append(value['error'])
        states = [value['status'] for value in components.values()]
        status = 'pending' if 'pending' in states else 'failed' if 'failed' in states else 'confirmed'
        if self._receipt is None or (self._receipt.status, self._receipt.components, self._receipt.errors) != (status, components, errors):
            self._receipt = ShutdownReceipt(status, components, errors)
        return self._receipt.to_dict()

    def get_receipt(self):
        with self._lock:
            return self._snapshot() if self._started else None

    @staticmethod
    def _interpret(value):
        if value is False:
            return {'status':'skipped', 'detail':'not_instantiated'}
        if value is None or value is True:
            return {'status':'confirmed'}  # synchronous verified-owner callback
        if isinstance(value, dict) and value.get('status') in {'confirmed','pending','failed'}:
            result = {'status':value['status']}
            for key in ('process_exit_confirmed','worker_pending','writer_pending','unresolved_dispatch'):
                if key in value: result[key] = deepcopy(value[key])
            return result
        return {'status':'pending', 'error':'UnverifiedReceipt'}

    def _perform(self, callback, operation):
        try:
            result = self._interpret(callback())
        except BaseException as exc:
            result = {'status':'failed', 'error':type(exc).__name__}
        with self._lock:
            operation['result'] = result
            operation['timed_out'] = False

    def execute_shutdown(self, components, timeout_per_component=3.0):
        if not isinstance(timeout_per_component, (int,float)) or timeout_per_component <= 0:
            raise ValueError('Positive cleanup join timeout required')
        self.close_admission()
        # Register all owners before anyone can read or race this pass.
        with self._lock:
            self._started = True
            for name in components:
                self._operations.setdefault(name, {'thread':None, 'result':{'status':'pending'}})
        if not self._pass_lock.acquire(blocking=False):
            return self.get_receipt()
        try:
            for name, callback in components.items():
                with self._lock:
                    operation = self._operations[name]
                    worker = operation['thread']
                    if worker is not None and not worker.is_alive() and operation['result']['status'] in {'confirmed','skipped'}:
                        continue
                    if worker is None or not worker.is_alive():
                        if callback is None:
                            operation['result'] = {'status':'skipped', 'detail':'not_registered'}
                            callback = lambda: False
                        operation['result'] = {'status':'pending'}
                        worker = threading.Thread(target=self._perform, args=(callback, operation),
                            name='quartz-stop-'+name, daemon=False)
                        operation['thread'] = worker
                        try: worker.start()
                        except Exception as exc:
                            operation['result'] = {'status':'failed', 'error':type(exc).__name__}
                            continue
                worker.join(timeout=timeout_per_component)
                with self._lock:
                    operation['timed_out'] = worker.is_alive()
            return self.get_receipt()
        finally:
            self._pass_lock.release()

    def reset(self):
        with self._lock:
            if any(op.get('thread') and op['thread'].is_alive() for op in self._operations.values()):
                raise RuntimeError('Cannot abandon an owned cleanup worker')
            self._admission_closed = False
            self._operations.clear()
            self._receipt = None
            self._started = False
            self._requests = 0


_global_coordinator = None
_coordinator_lock = threading.Lock()


def get_shutdown_coordinator():
    global _global_coordinator
    with _coordinator_lock:
        if _global_coordinator is None: _global_coordinator = ShutdownCoordinator()
        return _global_coordinator


def reset_shutdown_coordinator():
    global _global_coordinator
    with _coordinator_lock:
        if _global_coordinator is not None: _global_coordinator.reset()
        _global_coordinator = None
