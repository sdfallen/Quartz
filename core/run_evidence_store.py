"""Bounded durable source receipts. Data only: never restores task authority."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import time

from core.atomic_json import atomic_write_json


class RunEvidenceStore:
    LIMIT = 200
    MAX_BYTES = 4 * 1024 * 1024

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.lock = threading.RLock()
        self.records = {}
        self.error = ''
        if self.path is not None:
            try:
                if self.path.exists():
                    if self.path.stat().st_size > self.MAX_BYTES:
                        raise ValueError('Evidence store size limit exceeded')
                    raw = json.loads(self.path.read_text(encoding='utf-8'))
                    if not isinstance(raw, dict) or raw.get('version') != 1 or not isinstance(raw.get('runs'), dict):
                        raise ValueError('Unsupported evidence store schema')
                    if len(raw['runs']) > self.LIMIT or any(not isinstance(v, dict) for v in raw['runs'].values()):
                        raise ValueError('Invalid evidence receipt inventory')
                    self.records = raw['runs']
            except (OSError, ValueError) as exc:
                self.error = str(exc)  # Do not overwrite malformed historical evidence.

    def put(self, run_id, receipt):
        with self.lock:
            if self.error:
                raise OSError(self.error)
            candidate = deepcopy(self.records)
            candidate.pop(run_id, None)
            candidate[run_id] = {**deepcopy(receipt), 'recorded_at':time.time()}
            candidate = dict(list(candidate.items())[-self.LIMIT:])
            payload = {'version':1, 'scope':'Historical source receipts; no runtime or permission restoration', 'runs':candidate}
            if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > self.MAX_BYTES:
                raise ValueError('Evidence store size limit exceeded')
            if self.path is not None:
                atomic_write_json(self.path, payload)
            self.records = candidate

    def get(self, run_id):
        with self.lock:
            receipt = deepcopy(self.records.get(run_id, {}))
            if receipt:
                receipt['historical'] = True
            return receipt
