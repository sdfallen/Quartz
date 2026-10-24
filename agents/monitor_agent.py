"""
agents/monitor_agent.py  —  JARVIS System Monitor
Fixed:
  - Checks ALL disk partitions (not just C:\\)
  - Network anomaly detection added
  - cross-platform compatible
"""

import psutil
import time
from datetime import datetime
from agents.base_agent import BaseAgent
from logger import get_logger

log = get_logger(__name__)


class MonitorAgent(BaseAgent):

    def __init__(self, jarvis_tools: dict):
        super().__init__(
            "SystemMonitor", jarvis_tools)

        self.cpu_threshold  = 90
        self.ram_threshold  = 88
        self.disk_threshold = 93
        self.net_send_threshold_mbps = 10.0
        self.net_recv_threshold_mbps = 50.0
        self.check_interval = 30

        self._alert_cooldown: dict = {}
        self._cooldown_secs  = 300
        self._check_count    = 0
        self._net_samples:   list = []

    # ── Main loop ─────────────────────────────────────

    def run(self, goal: str = ""):
        self._log_step(
            f"System monitoring started. "
            f"Checking every "
            f"{self.check_interval}s.")

        while self.is_running:
            self._check_all()
            self._wait(self.check_interval)

        self._log_step(
            "System monitoring stopped.")

    # ── Checks ────────────────────────────────────────

    def _check_all(self):
        try:
            self._check_count += 1
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            net = psutil.net_io_counters()

            if not self.is_running:
                return

            self._check_cpu(cpu)
            self._check_ram(mem.percent)
            self._check_all_disks()
            self._check_network(net)

            if self._check_count % 10 == 0:
                self._log_step(
                    f"Health OK — "
                    f"CPU:{cpu:.0f}% "
                    f"RAM:{mem.percent:.0f}%")

        except Exception as exc:
            self._log_step(
                f"Check error: {exc}")

    def _check_cpu(self, cpu: float):
        if cpu > self.cpu_threshold:
            self._alert(
                "cpu",
                f"🔴 HIGH CPU: {cpu:.1f}%\n"
                f"   Threshold: "
                f"{self.cpu_threshold}%\n"
                f"   Consider closing heavy "
                f"applications.",
                level="warning")

    def _check_ram(self, ram: float):
        if ram > self.ram_threshold:
            try:
                procs = []
                for p in psutil.process_iter(
                    ["name", "memory_percent"]
                ):
                    try:
                        procs.append((
                            p.info["name"],
                            p.info.get(
                                "memory_percent",
                                0) or 0,
                        ))
                    except Exception:
                        pass
                procs.sort(
                    key=lambda x: x[1],
                    reverse=True)
                top_str = ", ".join(
                    f"{n}({v:.1f}%)"
                    for n, v in procs[:3])
            except Exception:
                top_str = "N/A"

            self._alert(
                "ram",
                f"🔴 HIGH RAM: {ram:.1f}%\n"
                f"   Top processes: {top_str}",
                level="warning")

    def _check_all_disks(self):
        """Check all mounted partitions."""
        try:
            for part in psutil.disk_partitions(
                    all=False):
                try:
                    usage = psutil.disk_usage(
                        part.mountpoint)
                    if (usage.percent
                            > self.disk_threshold):
                        self._alert(
                            f"disk_{part.mountpoint}",
                            f"🔴 DISK CRITICAL: "
                            f"{usage.percent:.1f}%"
                            f" on "
                            f"{part.mountpoint}\n"
                            f"   Disk almost full!\n"
                            f"   Free up space soon.",
                            level="warning")
                except PermissionError:
                    pass
                except Exception:
                    pass
        except Exception as exc:
            self._log_step(
                f"Disk check error: {exc}")

    def _check_network(
            self,
            net: psutil._common.snetio):
        """Detect unusual network activity."""
        try:
            current = {
                "sent": net.bytes_sent,
                "recv": net.bytes_recv,
                "ts":   time.time(),
            }

            if self._net_samples:
                prev = self._net_samples[-1]
                dt   = (current["ts"]
                        - prev["ts"])
                if dt > 0:
                    send_mbps = (
                        (current["sent"]
                         - prev["sent"])
                        / dt / 1e6)
                    recv_mbps = (
                        (current["recv"]
                         - prev["recv"])
                        / dt / 1e6)

                    if (send_mbps
                            > self.net_send_threshold_mbps):
                        self._alert(
                            "net_send",
                            f"🔴 HIGH UPLOAD: "
                            f"{send_mbps:.1f} MB/s\n"
                            f"   Possible data "
                            f"exfiltration?",
                            level="warning")

                    if (recv_mbps
                            > self.net_recv_threshold_mbps):
                        self._alert(
                            "net_recv",
                            f"⚠️ HIGH DOWNLOAD: "
                            f"{recv_mbps:.1f} MB/s",
                            level="info")

            self._net_samples.append(current)
            if len(self._net_samples) > 10:
                self._net_samples.pop(0)

        except Exception as exc:
            self._log_step(
                f"Network check error: {exc}")

    def _alert(self,
               alert_type: str,
               message: str,
               level: str = "warning"):
        now  = time.time()
        last = self._alert_cooldown.get(
            alert_type, 0)

        if now - last < self._cooldown_secs:
            return

        self._alert_cooldown[alert_type] = now
        ts       = datetime.now().strftime(
            "%H:%M:%S")
        full_msg = (
            f"⚠️ MONITOR ALERT [{ts}]\n"
            f"{message}")
        self._add_result(full_msg, level=level)
        self._log_step(
            f"ALERT: {alert_type}")

    # ── Configuration ─────────────────────────────────

    def set_threshold(self,
                      metric: str,
                      value: int) -> str:
        m = metric.lower()
        if m == "cpu":
            self.cpu_threshold = value
            return f"CPU threshold: {value}%"
        if m == "ram":
            self.ram_threshold = value
            return f"RAM threshold: {value}%"
        if m == "disk":
            self.disk_threshold = value
            return f"Disk threshold: {value}%"
        return f"Unknown metric: {metric}"

    def get_snapshot(self) -> str:
        try:
            cpu  = psutil.cpu_percent(interval=1)
            mem  = psutil.virtual_memory()
            net  = psutil.net_io_counters()
            boot = datetime.fromtimestamp(
                psutil.boot_time())
            uptime = datetime.now() - boot

            # Primary disk
            try:
                import platform
                disk_path = (
                    "C:\\" if
                    platform.system() == "Windows"
                    else "/")
                disk = psutil.disk_usage(
                    disk_path)
                disk_str = (
                    f"{disk.percent:.1f}% "
                    f"({disk.used/1e9:.1f}GB / "
                    f"{disk.total/1e9:.1f}GB)")
            except Exception:
                disk_str = "N/A"

            return (
                f"📊 System Snapshot\n"
                f"──────────────────\n"
                f"CPU    : {cpu:.1f}%\n"
                f"RAM    : "
                f"{mem.percent:.1f}% "
                f"({mem.used/1e9:.1f}GB / "
                f"{mem.total/1e9:.1f}GB)\n"
                f"DISK   : {disk_str}\n"
                f"NET↑   : "
                f"{net.bytes_sent/1e6:.0f}MB\n"
                f"NET↓   : "
                f"{net.bytes_recv/1e6:.0f}MB\n"
                f"Uptime : "
                f"{str(uptime).split('.')[0]}")

        except Exception as exc:
            return f"Snapshot error: {exc}"