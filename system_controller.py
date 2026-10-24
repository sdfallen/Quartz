"""
system_controller.py  —  Quartz
Low-level system operations.
All bugs fixed:
  - delete_file() now has path protection
  - disk_usage uses C:\\ on Windows
  - Protected path checks improved
"""

import os
import sys
import subprocess
import shutil
import platform
import shlex
import pyautogui
import pyperclip
import psutil
from pathlib import Path
from typing import Optional

from config import COMMAND_TIMEOUT, MAX_OUTPUT_CHARS
from logger import get_logger
from core.rollback_manager import rmtree_safe

log = get_logger(__name__)

# ── Disk path (Windows fix) ───────────────────────────────────────────────────
_DISK_PATH = "C:\\" if platform.system() == "Windows" else "/"

# ── Safety guards ─────────────────────────────────────────────────────────────
_PROTECTED_PATHS = {
    Path(os.path.expanduser("~")),
    Path("C:\\"),
    Path("C:\\Windows"),
    Path("C:\\Windows\\System32"),
    Path("C:\\Program Files"),
    Path("C:\\Program Files (x86)"),
    Path("/"),
}

_PROTECTED_KEYWORDS = [
    "system32", "windows", "program files",
    "appdata\\roaming\\microsoft",
    "boot", "recovery",
]

pyautogui.FAILSAFE = True


def _command_args(command) -> list[str]:
    """Convert a command to argv without invoking a command shell."""
    if isinstance(command, (list, tuple)):
        args = [str(part) for part in command]
    elif isinstance(command, str):
        args = shlex.split(command, posix=platform.system() != "Windows")
        if platform.system() == "Windows":
            args = [
                part[1:-1]
                if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'"
                else part
                for part in args
            ]
    else:
        raise TypeError("command must be a string or a list of arguments")
    if not args or not args[0].strip():
        raise ValueError("command cannot be empty")
    return args


# ── Shell execution ───────────────────────────────────────────────────────────

def run_command(command: str,
                working_dir: Optional[str] = None) -> str:
    """Execute a shell command and return its output."""
    log.info("run_command: %s", command)
    try:
        args = _command_args(command)
        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            cwd=working_dir or os.getcwd(),
        )
        output = result.stdout + result.stderr
        if len(output) > MAX_OUTPUT_CHARS:
            output = (
                output[:MAX_OUTPUT_CHARS]
                + "\n...[output truncated]"
            )
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return (
            f"Error: command timed out "
            f"after {COMMAND_TIMEOUT}s"
        )
    except Exception as exc:
        log.exception("run_command failed")
        return f"Error: {exc}"


def run_command_async(
        command: str,
        working_dir: Optional[str] = None) -> str:
    """Fire-and-forget — start a process without waiting."""
    log.info("run_command_async: %s", command)
    try:
        args = _command_args(command)
        if platform.system() == "Windows":
            subprocess.Popen(
                args,
                shell=False,
                cwd=working_dir or os.getcwd(),
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                ),
            )
        else:
            subprocess.Popen(
                args,
                shell=False,
                cwd=working_dir or os.getcwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return f"Started: {command}"
    except Exception as exc:
        log.exception("run_command_async failed")
        return f"Error: {exc}"


# ── File system ───────────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    log.info("read_file: %s", path)
    try:
        return Path(path).read_text(
            encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading file: {exc}"


def write_file(path: str, content: str) -> str:
    log.info("write_file: %s", path)
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return (
            f"Written {len(content)} "
            f"characters to {path}"
        )
    except Exception as exc:
        return f"Error writing file: {exc}"


def append_file(path: str, content: str) -> str:
    log.info("append_file: %s", path)
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(content)
        return f"Appended to {path}"
    except Exception as exc:
        return f"Error appending to file: {exc}"


def _is_protected(path: Path) -> bool:
    """
    Return True if the path is protected
    and should not be deleted.
    """
    try:
        resolved = path.resolve()
    except Exception:
        return True

    # Check exact protected paths
    for protected in _PROTECTED_PATHS:
        try:
            if resolved == protected.resolve():
                return True
            # Block if it's a direct child of home/root
            if (resolved.parent.resolve()
                    == protected.resolve()
                    and protected in {
                        Path("C:\\"),
                        Path("/"),
                    }):
                return True
        except Exception:
            continue

    # Check keyword patterns
    path_lower = str(resolved).lower()
    if any(kw in path_lower
           for kw in _PROTECTED_KEYWORDS):
        return True

    return False


def delete_file(path: str) -> str:
    log.info("delete_file: %s", path)
    try:
        p = Path(path)

        # ── Safety check ──────────────────────────────────
        if _is_protected(p):
            log.warning(
                "Blocked delete of protected path: %s",
                path)
            return (
                f"BLOCKED: Cannot delete protected "
                f"path: {path}"
            )

        if p.is_dir():
            rmtree_safe(p)
            return f"Deleted directory: {path}"
        try:
            p.unlink()
        except PermissionError:
            os.chmod(p, 0o777)
            p.unlink()
        return f"Deleted file: {path}"

    except Exception as exc:
        return f"Error deleting: {exc}"


def list_directory(path: str = ".") -> str:
    log.info("list_directory: %s", path)
    try:
        items = sorted(
            Path(path).iterdir(),
            key=lambda p: (p.is_file(), p.name),
        )
        lines = []
        for item in items:
            kind = "DIR " if item.is_dir() else "FILE"
            size = ""
            if item.is_file():
                size = (
                    f"  ({item.stat().st_size:,} bytes)"
                )
            lines.append(
                f"[{kind}] {item.name}{size}")
        return (
            "\n".join(lines)
            if lines
            else "(empty directory)"
        )
    except Exception as exc:
        return f"Error listing directory: {exc}"


def create_directory(path: str) -> str:
    log.info("create_directory: %s", path)
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return f"Directory created: {path}"
    except Exception as exc:
        return f"Error creating directory: {exc}"


def copy_item(src: str, dst: str) -> str:
    log.info("copy_item: %s -> %s", src, dst)
    try:
        s, d = Path(src), Path(dst)
        if s.is_dir():
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
        return f"Copied {src} → {dst}"
    except Exception as exc:
        return f"Error copying: {exc}"


def move_item(src: str, dst: str) -> str:
    log.info("move_item: %s -> %s", src, dst)
    try:
        shutil.move(src, dst)
        return f"Moved {src} → {dst}"
    except Exception as exc:
        return f"Error moving: {exc}"


# ── System info ───────────────────────────────────────────────────────────────

def get_system_info() -> str:
    log.info("get_system_info")
    cpu  = psutil.cpu_percent(interval=1)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage(_DISK_PATH)
    return (
        f"OS      : {platform.system()} "
        f"{platform.release()} "
        f"({platform.machine()})\n"
        f"CPU     : {cpu:.1f}%\n"
        f"RAM     : "
        f"{mem.used / 1e9:.1f} GB used / "
        f"{mem.total / 1e9:.1f} GB total\n"
        f"Disk    : "
        f"{disk.used / 1e9:.1f} GB used / "
        f"{disk.total / 1e9:.1f} GB total\n"
        f"Python  : {sys.version}"
    )


def list_processes() -> str:
    log.info("list_processes")
    try:
        procs = []
        for p in psutil.process_iter(
            ["pid", "name", "cpu_percent",
             "memory_info"]
        ):
            try:
                procs.append(p.info)
            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
            ):
                pass
        procs.sort(
            key=lambda x: x.get(
                "cpu_percent") or 0,
            reverse=True,
        )
        lines = ["PID      CPU%   MEM(MB)  NAME"]
        for p in procs[:30]:
            mem_mb = (
                (p.get("memory_info")
                 or type("", (), {"rss": 0})()
                 ).rss / 1e6
            )
            lines.append(
                f"{p['pid']:<8} "
                f"{p['cpu_percent'] or 0:>5.1f}  "
                f"{mem_mb:>7.1f}  {p['name']}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listing processes: {exc}"


def kill_process(pid_or_name: str) -> str:
    log.info("kill_process: %s", pid_or_name)
    killed = []
    try:
        if pid_or_name.isdigit():
            p = psutil.Process(int(pid_or_name))
            p.terminate()
            killed.append(str(p.pid))
        else:
            for p in psutil.process_iter(
                ["pid", "name"]
            ):
                if (p.info["name"]
                        and pid_or_name.lower()
                        in p.info["name"].lower()):
                    p.terminate()
                    killed.append(
                        f"{p.info['name']}"
                        f"({p.info['pid']})"
                    )
        return (
            f"Terminated: {', '.join(killed)}"
            if killed
            else "No matching process found"
        )
    except Exception as exc:
        return f"Error killing process: {exc}"


# ── Mouse & Keyboard ──────────────────────────────────────────────────────────

def mouse_click(x: int, y: int,
                button: str = "left",
                clicks: int = 1) -> str:
    log.info(
        "mouse_click: (%d,%d) button=%s "
        "clicks=%d", x, y, button, clicks)
    try:
        pyautogui.click(
            x, y, button=button, clicks=clicks)
        return f"Clicked {button} at ({x},{y})"
    except Exception as exc:
        return f"Error clicking: {exc}"


def mouse_move(x: int, y: int) -> str:
    log.info("mouse_move: (%d,%d)", x, y)
    try:
        pyautogui.moveTo(x, y, duration=0.3)
        return f"Mouse moved to ({x},{y})"
    except Exception as exc:
        return f"Error moving mouse: {exc}"


def type_text(text: str) -> str:
    log.info("type_text: %r", text[:50])
    try:
        pyautogui.write(text, interval=0.02)
        return f"Typed {len(text)} characters"
    except Exception as exc:
        return f"Error typing: {exc}"


def press_keys(*keys: str) -> str:
    """Press a key combo, e.g. press_keys('ctrl','c')."""
    log.info("press_keys: %s", keys)
    try:
        pyautogui.hotkey(*keys)
        return f"Pressed: {'+'.join(keys)}"
    except Exception as exc:
        return f"Error pressing keys: {exc}"


def take_screenshot(
        save_path: Optional[str] = None) -> str:
    log.info("take_screenshot: path=%s", save_path)
    try:
        img = pyautogui.screenshot()
        if save_path is None:
            save_path = os.path.join(
                os.path.expanduser("~"),
                "Desktop",
                "screenshot.png",
            )
        img.save(save_path)
        return f"Screenshot saved: {save_path}"
    except Exception as exc:
        return f"Error taking screenshot: {exc}"


# ── Clipboard ─────────────────────────────────────────────────────────────────

def get_clipboard() -> str:
    log.info("get_clipboard")
    try:
        return pyperclip.paste() or "(clipboard is empty)"
    except Exception as exc:
        return f"Error reading clipboard: {exc}"


def set_clipboard(text: str) -> str:
    log.info("set_clipboard")
    try:
        pyperclip.copy(text)
        return "Clipboard updated"
    except Exception as exc:
        return f"Error setting clipboard: {exc}"


# ── Applications ──────────────────────────────────────────────────────────────

def open_url(url: str) -> str:
    log.info("open_url: %s", url)
    import webbrowser
    try:
        webbrowser.open(url)
        return f"Opened URL: {url}"
    except Exception as exc:
        return f"Error opening URL: {exc}"


def open_file_explorer(path: str = ".") -> str:
    log.info("open_file_explorer: %s", path)
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return f"Opened file explorer at: {path}"
    except Exception as exc:
        return f"Error opening explorer: {exc}"
