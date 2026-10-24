"""
agents/base_agent.py  —  JARVIS Base Agent
Fixed:
  - stop() now joins thread with timeout
  - Interruptible _wait()
  - Timestamped results
  - Thread-safe throughout
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from logger import get_logger

log = get_logger(__name__)


@dataclass
class AgentResult:
    message:    str
    timestamp:  datetime = field(
        default_factory=datetime.now)
    level:      str = "info"
    agent_name: str = ""

    def format(self) -> str:
        ts = self.timestamp.strftime(
            "%Y-%m-%d %H:%M:%S")
        icon = {
            "info":    "ℹ️",
            "warning": "⚠️",
            "error":   "❌",
            "success": "✅",
        }.get(self.level, "📌")
        return (
            f"{icon} [{ts}] "
            f"{self.agent_name}\n"
            f"{self.message}")


class BaseAgent:
    """
    Every JARVIS agent inherits this.
    Provides start/stop/pause/resume/status.
    """

    def __init__(self,
                 name: str,
                 jarvis_tools: dict):
        self.name        = name
        self.tools       = jarvis_tools
        self.is_running  = False
        self.is_paused   = False
        self._thread: threading.Thread = None
        self._results:  list = []
        self._status:   str  = "idle"
        self._start_time: datetime = None
        self._step_log: list = []
        self._lock      = threading.Lock()
        log.info("Agent created: %s", name)

    # ── Lifecycle ─────────────────────────────────────

    def start(self, goal: str = "") -> str:
        if self.is_running:
            return (
                f"Agent '{self.name}' "
                f"is already running.")

        self.is_running  = True
        self.is_paused   = False
        self._status     = "running"
        self._start_time = datetime.now()
        self._step_log   = []

        self._thread = threading.Thread(
            target=self._safe_run,
            args=(goal,),
            daemon=True,
        )
        self._thread.start()

        return (
            f"🤖 Agent '{self.name}' started."
            f"\nGoal: {goal or 'standby'}")

    def stop(self,
             timeout: float = 5.0) -> str:
        """
        Signal stop and wait for thread
        to finish (up to timeout seconds).
        """
        self.is_running = False
        self.is_paused  = False
        self._status    = "stopped"

        if (self._thread
                and self._thread.is_alive()):
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                log.warning(
                    "Agent %s did not stop "
                    "within %.1fs",
                    self.name, timeout)
                return (
                    f"⚠️ Agent '{self.name}' "
                    f"stop signal sent "
                    f"(still finishing task)")

        return (
            f"⏹️ Agent '{self.name}' stopped.")

    def pause(self) -> str:
        self.is_paused = True
        self._status   = "paused"
        return (
            f"⏸️ Agent '{self.name}' paused.")

    def resume(self) -> str:
        self.is_paused = False
        self._status   = "running"
        return (
            f"▶️ Agent '{self.name}' resumed.")

    def get_status(self) -> str:
        uptime = ""
        if self._start_time:
            delta = (
                datetime.now()
                - self._start_time)
            secs  = int(
                delta.total_seconds())
            h, r  = divmod(secs, 3600)
            m, s  = divmod(r, 60)
            uptime = (
                f"\n   Uptime   : "
                f"{h:02d}:{m:02d}:{s:02d}")

        with self._lock:
            recent = list(self._step_log[-3:])

        steps = ""
        if recent:
            steps = (
                "\n   Recent   :\n"
                + "\n".join(
                    f"   → {s}"
                    for s in recent))

        return (
            f"🤖 {self.name}\n"
            f"   Status   : {self._status}"
            f"{uptime}{steps}")

    def get_results(self) -> str:
        with self._lock:
            results = list(self._results)
        if not results:
            return (
                f"No results yet from "
                f"'{self.name}'.")
        return "\n\n".join(
            r.format()
            if isinstance(r, AgentResult)
            else str(r)
            for r in results)

    def clear_results(self) -> str:
        with self._lock:
            self._results.clear()
        return (
            f"Results cleared for "
            f"'{self.name}'.")

    # ── Internal helpers ──────────────────────────────

    def _safe_run(self, goal: str):
        try:
            self.run(goal)
        except Exception as exc:
            log.exception(
                "Agent %s crashed: %s",
                self.name, exc)
            self._status    = f"error: {exc}"
            self.is_running = False

    def run(self, goal: str):
        raise NotImplementedError(
            f"Agent '{self.name}' must "
            f"implement run()")

    def _use_tool(self,
                  tool_name: str,
                  *args,
                  **kwargs) -> str:
        func = self.tools.get(tool_name)
        if not func:
            msg = f"Tool not found: {tool_name}"
            self._log_step(msg)
            return msg
        try:
            result     = func(*args, **kwargs)
            result_str = str(result)
            self._log_step(
                f"{tool_name}() → "
                f"{result_str[:60]}")
            return result_str
        except Exception as exc:
            msg = (
                f"Tool error [{tool_name}]: "
                f"{exc}")
            self._log_step(msg)
            return msg

    def _log_step(self, message: str):
        ts    = datetime.now().strftime(
            "%H:%M:%S")
        entry = f"[{ts}] {message}"
        with self._lock:
            self._step_log.append(entry)
            if len(self._step_log) > 200:
                self._step_log = (
                    self._step_log[-100:])
        log.info(
            "Agent %s: %s",
            self.name, message)

    def _add_result(self,
                    result: str,
                    level: str = "info"):
        entry = AgentResult(
            message    = result,
            level      = level,
            agent_name = self.name,
        )
        with self._lock:
            self._results.append(entry)
            if len(self._results) > 50:
                self._results = (
                    self._results[-50:])

    def _wait(self, seconds: float):
        """
        Interruptible wait.
        Checks is_running every 100ms.
        """
        intervals = int(seconds * 10)
        for _ in range(max(1, intervals)):
            if not self.is_running:
                return
            while self.is_paused:
                if not self.is_running:
                    return
                time.sleep(0.1)
            time.sleep(0.1)