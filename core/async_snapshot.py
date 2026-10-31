"""A bounded, single-flight read model. Polling never waits for external probes.

No task authority lives here. A cached result is diagnostic data, not permission
or proof that the next operation will succeed. One worker serves the latest key;
results from a superseded project generation cannot overwrite the current view.
"""
from copy import deepcopy
import threading
import time


class AsyncSnapshot:
    def __init__(self, loader, *, ttl=15, clock=time.monotonic):
        self.loader, self.ttl, self.clock = loader, ttl, clock
        self.lock = threading.RLock()
        self.key = None
        self.generation = 0
        self.value = None
        self._cached_value = None
        self._cached_generation = 0
        self.error = ''
        self.updated = None
        self.attempted = None
        self.worker = None
        self.closed = False

    def read(self, key, seed=None):
        with self.lock:
            now = self.clock()
            if key != self.key:
                self.key = key
                self.generation += 1
                self.value = None
                self._cached_value = None
                self.error = ''
                self.updated = self.attempted = None

            # Watchdog: if a background worker has hung for > max(2*ttl, 30s), fence it
            if self.worker is not None and self.attempted is not None:
                worker_age = now - self.attempted
                if worker_age >= max(float(self.ttl) * 2.0, 30.0):
                    self.error = 'Status probe timed out'
                    self.worker = None

            due = self.attempted is None or now - self.attempted >= self.ttl
            if not self.closed and self.worker is None and due:
                self.attempted = now
                self.worker = threading.Thread(target=self._refresh,
                    args=(self.generation, key), daemon=True, name='quartz-status-refresh')
                self.worker.start()
            state = {'refreshing': self.worker is not None, 'error': self.error,
                     'stale': self.updated is None or now - self.updated >= self.ttl,
                     'age_seconds': None if self.updated is None else max(0, now - self.updated)}

            if self.value is not None:
                if self._cached_value is None or self._cached_generation != self.generation:
                    self._cached_value = deepcopy(self.value)
                    self._cached_generation = self.generation
                res_val = deepcopy(self._cached_value)
            else:
                res_val = deepcopy(seed or {})
            return res_val, state

    def _refresh(self, generation, key):
        try:
            value = self.loader(key)
            if not isinstance(value, dict):
                raise TypeError('Status source must return a dictionary')
            error = ''
        except Exception as exc:
            value, error = None, str(exc)
        with self.lock:
            if not self.closed and generation == self.generation:
                if value is not None:
                    self.value = deepcopy(value)
                    self.updated = self.clock()
                    self._cached_value = deepcopy(self.value)
                    self._cached_generation = self.generation
                self.error = error
                self.worker = None
            elif self.worker is threading.current_thread():
                self.worker = None

    def close(self, timeout: float | None = None):
        # Do not block shutdown on an external CLI/network probe. Its late
        # result is fenced; the daemon owns no permission or input capability.
        with self.lock:
            self.closed = True
            self.generation += 1
            worker = self.worker
        if timeout is not None and worker is not None and worker.is_alive():
            worker.join(timeout=timeout)
