"""Single-use confirmation challenges for risky operations."""

import secrets
import threading


class ConfirmationManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._pending = None

    @property
    def pending(self) -> bool:
        with self._lock:
            return self._pending is not None

    def create(self, calls) -> str:
        with self._lock:
            code = secrets.token_hex(3).upper()
            self._pending = {"code": code, "calls": list(calls)}
            return code

    def consume(self, code: str):
        with self._lock:
            if not self._pending:
                return None
            if not secrets.compare_digest(self._pending["code"], code):
                return None
            calls = self._pending["calls"]
            self._pending = None
            return calls

    def cancel(self) -> None:
        with self._lock:
            self._pending = None

