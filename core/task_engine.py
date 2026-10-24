"""Persistent multi-step task state for Quartz orchestration."""

import threading
import uuid
from datetime import datetime

from core.atomic_json import atomic_write_json, load_json


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskEngine:
    TERMINAL = {"completed", "failed", "cancelled"}

    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        value = load_json(path, [])
        self._tasks = value if isinstance(value, list) else []

    def create(self, title: str, steps: list[dict]) -> dict:
        if not steps:
            raise ValueError("A task requires at least one step")
        task = {
            "id": uuid.uuid4().hex[:10],
            "title": title.strip() or "Quartz task",
            "status": "pending",
            "created_at": _now(),
            "updated_at": _now(),
            "steps": [
                {
                    "index": index, "tool": step["tool"],
                    "arguments": step.get("arguments", {}),
                    "status": "pending", "result": None, "error": None,
                }
                for index, step in enumerate(steps)
            ],
        }
        with self._lock:
            self._tasks.append(task)
            self._tasks = self._tasks[-100:]
            self._save()
            return self._copy(task)

    def update_step(self, task_id: str, index: int, status: str,
                    *, result=None, error=None) -> dict:
        with self._lock:
            task = self._find(task_id)
            step = task["steps"][index]
            step.update({"status": status, "result": result, "error": error})
            task["updated_at"] = _now()
            states = {item["status"] for item in task["steps"]}
            if "failed" in states:
                task["status"] = "failed"
            elif "cancelled" in states:
                task["status"] = "cancelled"
            elif states == {"completed"}:
                task["status"] = "completed"
            elif "running" in states:
                task["status"] = "running"
            else:
                task["status"] = "pending"
            self._save()
            return self._copy(task)

    def cancel(self, task_id: str) -> dict:
        with self._lock:
            task = self._find(task_id)
            if task["status"] not in self.TERMINAL:
                task["status"] = "cancelled"
                task["updated_at"] = _now()
                for step in task["steps"]:
                    if step["status"] in {"pending", "running"}:
                        step["status"] = "cancelled"
                self._save()
            return self._copy(task)

    def list(self, limit: int = 20) -> list[dict]:
        with self._lock:
            return [self._copy(task) for task in self._tasks[-limit:]][::-1]

    def _find(self, task_id: str) -> dict:
        for task in self._tasks:
            if task["id"] == task_id:
                return task
        raise KeyError(f"Unknown task: {task_id}")

    def _save(self) -> None:
        atomic_write_json(self.path, self._tasks)

    @staticmethod
    def _copy(value):
        import copy
        return copy.deepcopy(value)
