"""
agents/scheduler_agent.py  —  JARVIS Scheduler
Fixed:
  - Race condition in task execution (atomic mark)
  - Better command routing via JARVIS tools
  - Proper time validation
"""

import re
import time
from datetime import datetime
from agents.base_agent import BaseAgent
from logger import get_logger

log = get_logger(__name__)


class SchedulerAgent(BaseAgent):

    def __init__(self, jarvis_tools: dict):
        super().__init__(
            "Scheduler", jarvis_tools)
        self._tasks:        list = []
        self._task_counter: int  = 0

    # ── Main loop ─────────────────────────────────────

    def run(self, goal: str = ""):
        self._log_step(
            "Scheduler running. "
            "Checking tasks every 30s.")

        while self.is_running:
            self._check_tasks()
            self._wait(30)

        self._log_step("Scheduler stopped.")

    # ── Task management ───────────────────────────────

    def add_task(self,
                 task_time: str,
                 command: str,
                 repeat: bool = False,
                 label: str = "") -> str:
        try:
            parts = task_time.split(":")
            if (len(parts) != 2
                    or not all(
                        p.isdigit()
                        for p in parts)):
                return (
                    "Invalid time format. "
                    "Use HH:MM (e.g. 09:30)")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23
                    and 0 <= m <= 59):
                return (
                    "Invalid time. "
                    "Hours: 0-23, "
                    "Minutes: 0-59")
        except Exception:
            return (
                "Invalid time format. "
                "Use HH:MM")

        self._task_counter += 1
        task = {
            "id":        self._task_counter,
            "time":      task_time,
            "command":   command,
            "label":     label or command[:30],
            "repeat":    repeat,
            "done":      False,
            "last_run":  None,
            "run_count": 0,
        }

        with self._lock:
            self._tasks.append(task)

        repeat_str = (
            "🔁 daily" if repeat
            else "1️⃣ once")
        return (
            f"✅ Task #{self._task_counter} "
            f"scheduled!\n"
            f"   Time   : {task_time}\n"
            f"   Command: {command[:50]}\n"
            f"   Repeat : {repeat_str}")

    def remove_task(self,
                    task_id: int) -> str:
        with self._lock:
            before = len(self._tasks)
            self._tasks = [
                t for t in self._tasks
                if t["id"] != task_id]
            after = len(self._tasks)

        if after < before:
            return f"✅ Task #{task_id} removed."
        return f"Task #{task_id} not found."

    def list_tasks(self) -> str:
        with self._lock:
            tasks = list(self._tasks)

        if not tasks:
            return (
                "No scheduled tasks.\n"
                "Add one with:\n"
                'schedule_task('
                '"09:00", "show weather")')

        lines = ["📅 Scheduled Tasks:\n"]
        for t in tasks:
            status = (
                "✅ done"
                if (t["done"]
                    and not t["repeat"])
                else "⏳ waiting")
            repeat = (
                "🔁 daily"
                if t["repeat"]
                else "1️⃣ once")
            last = (
                f" | last: {t['last_run']}"
                if t["last_run"] else "")
            lines.append(
                f"  #{t['id']} [{status}] "
                f"{repeat}\n"
                f"     ⏰ {t['time']} → "
                f"{t['label']}{last}")

        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────

    def _check_tasks(self):
        now = datetime.now().strftime("%H:%M")

        # Atomic: collect due tasks AND mark
        # last_run in one lock acquisition
        due_tasks = []
        with self._lock:
            for task in self._tasks:
                if task["time"] != now:
                    continue
                if (task["done"]
                        and not task["repeat"]):
                    continue
                if task.get("last_run") == now:
                    continue
                # Mark immediately to prevent
                # double execution
                task["last_run"] = now
                due_tasks.append(dict(task))

        # Execute outside lock
        for task in due_tasks:
            self._execute_task(task)
            # Update counters
            with self._lock:
                for t in self._tasks:
                    if t["id"] == task["id"]:
                        t["run_count"] += 1
                        if not t["repeat"]:
                            t["done"] = True

    def _execute_task(self, task: dict):
        cmd = task["command"]
        lbl = task["label"]
        self._log_step(f"Executing: {lbl}")

        result = self._route_command(cmd)

        ts = datetime.now().strftime("%H:%M:%S")
        self._add_result(
            f"✅ Task ran at {ts}: "
            f"{lbl}\n{result[:200]}",
            level="success")

    def _route_command(self, cmd: str) -> str:
        """
        Route scheduled command to the
        correct JARVIS tool intelligently.
        """
        cmd_lower = cmd.lower().strip()

        # Weather
        if any(w in cmd_lower for w in [
            "weather", "temperature",
            "forecast",
        ]):
            city = re.sub(
                r'\b(weather|temperature|'
                r'forecast|in|for|the|'
                r'show|get|check)\b',
                ' ', cmd_lower,
                flags=re.IGNORECASE,
            ).strip() or "Istanbul"
            return self._use_tool(
                "get_weather", city)

        # Screenshot
        if "screenshot" in cmd_lower:
            return self._use_tool(
                "take_screenshot")

        # System info
        if any(w in cmd_lower for w in [
            "system", "sysinfo",
            "cpu", "ram",
        ]):
            return self._use_tool(
                "get_system_info")

        # Volume
        if "volume" in cmd_lower:
            nums = re.findall(
                r'\d+', cmd_lower)
            if nums:
                return self._use_tool(
                    "set_volume",
                    int(nums[0]))
            return self._use_tool(
                "get_volume")

        # Notes
        if "note" in cmd_lower:
            content = re.sub(
                r'\b(add|note|save|a)\b',
                ' ', cmd_lower).strip()
            return self._use_tool(
                "add_note",
                content or cmd,
                "scheduled")

        # Lock screen
        if "lock" in cmd_lower:
            return self._use_tool("lock_screen")

        # Safe shell commands only
        safe_first = cmd_lower.split()[0]
        safe_cmds  = {
            "ipconfig", "date", "time",
            "dir", "whoami", "ping",
        }
        if safe_first in safe_cmds:
            return self._use_tool(
                "run_command", cmd)

        return (
            f"Command '{cmd}' not recognised "
            f"by scheduler router.")