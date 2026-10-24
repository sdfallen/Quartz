"""Persistent multi-turn operation context and reusable Quartz workflows."""

import copy
import json
import re
import threading
import uuid
from datetime import datetime

from core.atomic_json import atomic_write_json, load_json


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_value(value):
    """Persist operational arguments while redacting obvious secrets."""
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if re.search(
                r"token|password|secret|api.?key", str(key), re.I)
                else _safe_value(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    text = str(value)
    return text[:1000]


class ContinuityEngine:
    """Keeps an operation coherent across separate chat messages and restarts."""

    def __init__(self, context_path, workflows_path):
        self.context_path = context_path
        self.workflows_path = workflows_path
        self._lock = threading.RLock()
        value = load_json(context_path, {})
        self._active = value.get("active") if isinstance(value, dict) else None
        workflows = load_json(workflows_path, [])
        self._workflows = workflows if isinstance(workflows, list) else []

    def active(self):
        with self._lock:
            return copy.deepcopy(self._active)

    def ensure(self, goal: str) -> dict:
        with self._lock:
            if not self._active or self._active.get("status") != "active":
                self._active = {
                    "id": uuid.uuid4().hex[:10],
                    "root_goal": goal.strip(),
                    "current_request": goal.strip(),
                    "status": "active",
                    "app_context": None,
                    "created_at": _now(),
                    "updated_at": _now(),
                    "messages": [],
                    "actions": [],
                    "observations": [],
                }
            self.add_message(goal)
            return copy.deepcopy(self._active)

    def add_message(self, message: str) -> None:
        with self._lock:
            if not self._active:
                return
            clean = message.strip()
            if (self._active.get("messages") and
                    self._active["messages"][-1].get("content") == clean):
                return
            self._active["current_request"] = clean
            self._active.setdefault("messages", []).append({
                "content": clean, "at": _now()})
            self._active["messages"] = self._active["messages"][-20:]
            self._active["updated_at"] = _now()
            self._save_context()

    def record_tool(self, goal: str, name: str, arguments, result: str,
                    *, error: str = None) -> dict:
        with self._lock:
            if name == "smart_open" and self._active:
                args = arguments.get("args", []) if isinstance(arguments, dict) else []
                next_app = str(args[0]).casefold().strip() if args else ""
                current_app = str(self._active.get("app_context") or "").casefold()
                if next_app and current_app and next_app != current_app:
                    self.complete("A different application task started")
            self.ensure(goal)
            action = {
                "tool": name,
                "arguments": _safe_value(arguments),
                "result": str(result)[:1500],
                "error": str(error)[:500] if error else None,
                "status": "failed" if error else "completed",
                "at": _now(),
            }
            self._active.setdefault("actions", []).append(action)
            self._active["actions"] = self._active["actions"][-30:]
            if name == "smart_open":
                args = arguments.get("args", []) if isinstance(arguments, dict) else []
                if args:
                    self._active["app_context"] = str(args[0])
            if name in {"desktop_inspect", "desktop_action"} and not error:
                try:
                    observed = json.loads(str(result))
                    observed = observed.get("after", observed)
                    if observed.get("handle"):
                        self._active["window_handle"] = observed["handle"]
                        self._active["app_context"] = observed.get("title", "")
                except (ValueError, TypeError, AttributeError):
                    pass
            self._active["updated_at"] = _now()
            self._save_context()
            return copy.deepcopy(self._active)

    def record_observation(self, text: str) -> None:
        with self._lock:
            if not self._active:
                return
            self._active.setdefault("observations", []).append({
                "content": str(text)[:2000], "at": _now()})
            self._active["observations"] = self._active["observations"][-8:]
            self._active["updated_at"] = _now()
            self._save_context()

    def complete(self, note: str = "") -> dict | None:
        with self._lock:
            if not self._active:
                return None
            self._active["status"] = "completed"
            self._active["completion_note"] = note[:1000]
            self._active["updated_at"] = _now()
            finished = copy.deepcopy(self._active)
            self._active = None
            self._save_context()
            return finished

    def learn_active(self, name: str = "") -> dict:
        with self._lock:
            if not self._active or not self._active.get("actions"):
                raise ValueError("Öğrenilecek aktif bir görev akışı yok.")
            workflow = {
                "id": uuid.uuid4().hex[:10],
                "name": name.strip() or self._active["root_goal"][:80],
                "root_goal": self._active["root_goal"],
                "app_context": self._active.get("app_context"),
                "steps": [
                    {"tool": item["tool"], "arguments": item["arguments"]}
                    for item in self._active["actions"]
                    if item.get("status") == "completed"
                ],
                "learned_at": _now(),
                "uses": 0,
            }
            self._workflows.append(workflow)
            self._workflows = self._workflows[-100:]
            atomic_write_json(self.workflows_path, self._workflows)
            return copy.deepcopy(workflow)

    def workflow_hint(self, message: str) -> str:
        words = set(re.findall(r"[\wçğıöşü]+", message.casefold()))
        if len(words) < 2:
            return ""
        scored = []
        with self._lock:
            for workflow in self._workflows:
                target = set(re.findall(
                    r"[\wçğıöşü]+",
                    (workflow.get("name", "") + " " +
                     workflow.get("root_goal", "")).casefold()))
                score = len(words & target)
                if score >= 2:
                    scored.append((score, workflow))
        if not scored:
            return ""
        workflow = max(scored, key=lambda item: item[0])[1]
        steps = ", ".join(step["tool"] for step in workflow.get("steps", []))
        return (f"LEARNED WORKFLOW MATCH: {workflow['name']} | "
                f"previous successful tools: {steps}. Adapt it to the current screen; "
                "do not blindly replay coordinates.")

    def prompt(self, current_message: str) -> str:
        with self._lock:
            if not self._active:
                return self.workflow_hint(current_message)
            self.add_message(current_message)
            recent = self._active.get("actions", [])[-8:]
            actions = "\n".join(
                f"- {item['tool']}({item.get('arguments')}) -> "
                f"{item.get('result', '')[:300]}"
                for item in recent) or "- none yet"
            observations = self._active.get("observations", [])[-2:]
            observed = "\n".join(
                f"- {item['content'][:500]}" for item in observations) or "- none"
            return (
                "ACTIVE OPERATION CONTEXT (continue this unless the user explicitly "
                "starts a new task):\n"
                f"operation_id: {self._active['id']}\n"
                f"root_goal: {self._active['root_goal']}\n"
                f"current_request: {current_message}\n"
                f"active_app: {self._active.get('app_context') or 'unknown'}\n"
                f"window_handle: {self._active.get('window_handle') or 'unknown'}\n"
                f"recent_actions:\n{actions}\n"
                f"recent_screen_observations:\n{observed}\n"
                "Resolve references such as 'orada', 'sonra', 'kütüphaneme gir', "
                "'onu indir' using this context. Continue acting with tools until the "
                "requested state is verified. Never claim success without a tool result "
                "or screen observation.")

    def summary(self) -> dict:
        with self._lock:
            active = copy.deepcopy(self._active)
            return {
                "active": active,
                "workflow_count": len(self._workflows),
            }

    def _save_context(self) -> None:
        atomic_write_json(self.context_path, {"active": self._active})
