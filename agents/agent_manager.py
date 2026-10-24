"""
agent_manager.py  —  JARVIS Agent Manager
Fixed:
  - None checks on all agent accesses
  - Circuit breaker for failed agents
  - Research agent thread leak fixed
  - stop_all() properly joins threads
"""

import threading
from datetime import datetime
from enum import Enum
from agents.monitor_agent   import MonitorAgent
from agents.research_agent  import ResearchAgent
from agents.scheduler_agent import SchedulerAgent
from agents.file_agent      import FileAgent
from logger import get_logger

log = get_logger(__name__)


class AgentState(Enum):
    HEALTHY  = "healthy"
    FAILED   = "failed"


class AgentManager:
    """Central hub for all JARVIS agents."""

    def __init__(self, tools: dict):
        self.tools         = tools
        self._agents:      dict = {}
        self._agent_state: dict = {}
        self._fail_counts: dict = {}
        self._lock         = threading.Lock()
        log.info("AgentManager initialized")

    # ── Agent factory ─────────────────────────────────

    def _create_agent(self, name: str):
        factories = {
            "monitor":   lambda: MonitorAgent(
                self.tools),
            "research":  lambda: ResearchAgent(
                self.tools),
            "scheduler": lambda: SchedulerAgent(
                self.tools),
            "files":     lambda: FileAgent(
                self.tools),
        }
        factory = factories.get(name)
        if not factory:
            raise ValueError(
                f"Unknown agent: {name}")
        return factory()

    def _get(self, name: str):
        """Get or create agent with circuit breaker."""
        state = self._agent_state.get(
            name, AgentState.HEALTHY)

        if state == AgentState.FAILED:
            if self._fail_counts.get(name, 0) >= 3:
                log.warning(
                    "Agent %s circuit open "
                    "(3 failures)", name)
                return None

        with self._lock:
            if name not in self._agents:
                try:
                    self._agents[name] = (
                        self._create_agent(name))
                    self._agent_state[name] = (
                        AgentState.HEALTHY)
                    self._fail_counts[name] = 0
                except Exception as exc:
                    log.exception(
                        "Agent creation failed: "
                        "%s — %s", name, exc)
                    self._fail_counts[name] = (
                        self._fail_counts.get(
                            name, 0) + 1)
                    self._agent_state[name] = (
                        AgentState.FAILED)
                    return None

        return self._agents.get(name)

    # ── Monitor Agent ─────────────────────────────────

    def start_monitor(self) -> str:
        agent = self._get("monitor")
        if agent is None:
            return (
                "Monitor agent unavailable. "
                "Check logs.")
        if agent.is_running:
            return (
                "Monitor already running.\n"
                + agent.get_status())
        return agent.start(
            "Monitor system health 24/7")

    def stop_monitor(self) -> str:
        with self._lock:
            agent = self._agents.get("monitor")
        if not agent:
            return "Monitor was not running."
        return agent.stop()

    def monitor_status(self) -> str:
        with self._lock:
            agent = self._agents.get("monitor")
        if not agent:
            return (
                "Monitor not started.\n"
                "Say 'start monitor' to begin.")

        status  = agent.get_status()
        results = agent.get_results()
        snap    = agent.get_snapshot()

        output = f"{status}\n\n{snap}"
        if (results and
                "No results yet" not in results):
            output += (
                f"\n\n⚠️ Recent Alerts:\n"
                f"{results}")
        return output

    def monitor_alerts(self) -> str:
        with self._lock:
            agent = self._agents.get("monitor")
        if not agent:
            return "Monitor not running."
        results = agent.get_results()
        if "No results yet" in results:
            return "✅ No alerts. System is healthy!"
        return results

    def set_monitor_threshold(self,
                              metric: str,
                              value: int) -> str:
        agent = self._get("monitor")
        if agent is None:
            return "Monitor unavailable."
        return agent.set_threshold(metric, value)

    # ── Research Agent ────────────────────────────────

    def start_research(self,
                       topic: str) -> str:
        """Always creates a fresh research agent."""
        # Stop and clean up old agent first
        with self._lock:
            old = self._agents.get("research")

        if old and old.is_running:
            try:
                old.stop(timeout=3.0)
            except Exception:
                pass

        with self._lock:
            self._agents["research"] = (
                ResearchAgent(self.tools))
            agent = self._agents["research"]

        return agent.start(topic)

    def get_research(self) -> str:
        with self._lock:
            agent = self._agents.get("research")
        if not agent:
            return (
                "No research running.\n"
                "Say 'research [topic]' "
                "to start.")
        status  = agent.get_status()
        results = agent.get_results()
        return f"{status}\n\n{results}"

    # ── Scheduler Agent ───────────────────────────────

    def schedule_task(self,
                      task_time: str,
                      command: str,
                      repeat: bool = False) -> str:
        agent = self._get("scheduler")
        if agent is None:
            return "Scheduler unavailable."
        if not agent.is_running:
            agent.start("Running scheduler")
        return agent.add_task(
            task_time, command, repeat)

    def remove_scheduled_task(self,
                              task_id: int) -> str:
        with self._lock:
            agent = self._agents.get("scheduler")
        if not agent:
            return "Scheduler not running."
        return agent.remove_task(task_id)

    def list_scheduled(self) -> str:
        with self._lock:
            agent = self._agents.get("scheduler")
        if not agent:
            return (
                "No tasks scheduled.\n"
                "Add one with:\n"
                "'schedule task at 09:00 "
                "show weather'")
        return agent.list_tasks()

    # ── File Agent ────────────────────────────────────

    def start_file_agent(self,
                         folder: str = "") -> str:
        agent = self._get("files")
        if agent is None:
            return "File agent unavailable."
        if agent.is_running:
            return (
                "File agent already running.\n"
                + agent.get_status())
        return agent.start(folder)

    def stop_file_agent(self) -> str:
        with self._lock:
            agent = self._agents.get("files")
        if not agent:
            return "File agent not running."
        return agent.stop()

    def organize_files_now(self) -> str:
        agent = self._get("files")
        if agent is None:
            return "File agent unavailable."
        return agent.organize_now()

    def file_agent_stats(self) -> str:
        agent = self._get("files")
        if agent is None:
            return "File agent unavailable."
        return agent.get_folder_stats()

    def set_watch_folder(self,
                         path: str) -> str:
        agent = self._get("files")
        if agent is None:
            return "File agent unavailable."
        return agent.set_watch_folder(path)

    def file_agent_undo(self,
                        count: int = 10) -> str:
        agent = self._get("files")
        if agent is None:
            return "File agent unavailable."
        return agent.undo_last_moves(count)

    def file_agent_enable_move(self) -> str:
        agent = self._get("files")
        if agent is None:
            return "File agent unavailable."
        return agent.enable_move()

    # ── All agents ────────────────────────────────────

    def all_status(self) -> str:
        with self._lock:
            agents = dict(self._agents)

        if not agents:
            return (
                "🤖 No agents running.\n\n"
                "Available agents:\n"
                "  start_monitor()\n"
                '  start_research("topic")\n'
                '  schedule_task("09:00",'
                ' "weather")\n'
                "  start_file_agent()")

        lines = [
            f"🤖 Active Agents "
            f"({len(agents)} total)\n"]
        for name, agent in agents.items():
            lines.append(agent.get_status())
            lines.append("─" * 30)

        return "\n".join(lines)

    def stop_all(self) -> str:
        with self._lock:
            agents = dict(self._agents)

        stopped = []
        for name, agent in agents.items():
            if agent.is_running:
                agent.stop(timeout=3.0)
                stopped.append(name)

        if stopped:
            return (
                f"⏹️ Stopped: "
                f"{', '.join(stopped)}")
        return "No agents were running."