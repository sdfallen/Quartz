"""Thread-safe bounded conversation history persistence."""

import threading
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json


class HistoryStore:
    def __init__(self, path, max_messages: int):
        self.path = Path(path)
        self.max_messages = max_messages
        self._lock = threading.RLock()

    def load(self) -> list:
        with self._lock:
            value = load_json(self.path, [])
            return value if isinstance(value, list) else []

    def save(self, history: list) -> None:
        with self._lock:
            atomic_write_json(self.path, history[-self.max_messages:])

