"""
upgrade_manager.py  —  Quartz Self-Upgrade System
True plug-and-play plugin loading.
Plugins register their own tools automatically.
No code changes needed after install.
"""

import sys
import os
import json
import shutil
import importlib
import importlib.util
import subprocess
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from logger import get_logger
from core.atomic_json import atomic_write_json, load_json
from core.tool_registry import get_tool_registry
from core.plugin_loader import register_plugin_tools, unregister_plugin_tools
from core.rollback_manager import RollbackManager, rmtree_safe

log = get_logger(__name__)

# ── Paths ─────────────────────────────────────────────
BASE_DIR      = Path(
    os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR   = BASE_DIR / "plugins" / "installed"
PENDING_DIR   = BASE_DIR / "plugins" / "pending"
DISABLED_DIR  = BASE_DIR / "plugins" / "disabled"
BACKUPS_DIR   = BASE_DIR / "upgrades" / "backups"
HISTORY_FILE  = (
    BASE_DIR / "upgrades" / "upgrade_history.json")
REGISTRY_FILE = (
    BASE_DIR / "upgrades" / "plugin_registry.json")

# ── Dangerous patterns ────────────────────────────────
_DANGEROUS_PATTERNS = [
    "os.system(",
    "eval(",
    "exec(",
    "__import__(",
    "pickle.loads(",
    "marshal.loads(",
    "compile(",
    "open(\"/etc",
    "open(\"C:\\\\Windows",
    "rmdir(",
    ":(){:|:&};:",
]

# ── GitHub URL pattern ────────────────────────────────
_GITHUB_URL_RE = re.compile(
    r'https?://github\.com/'
    r'[\w\-\.]+/[\w\-\.]+'
)


class UpgradeManager:

    def __init__(self):
        self._loaded_plugins: dict = {}
        self._dynamic_tools:  dict = {}
        self._dynamic_hints:  list = []
        self._lock = threading.RLock()
        self._rollback = RollbackManager()
        self._ensure_dirs()
        log.info("UpgradeManager ready")

    # ── Directory setup ───────────────────────────────

    def _ensure_dirs(self):
        for d in [
            PLUGINS_DIR, PENDING_DIR,
            DISABLED_DIR, BACKUPS_DIR,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        if not HISTORY_FILE.exists():
            atomic_write_json(HISTORY_FILE, [])

        if not REGISTRY_FILE.exists():
            atomic_write_json(
                REGISTRY_FILE, {"installed": {}, "disabled": {}})

    # ── Dynamic tool registry ─────────────────────────

    def get_dynamic_tools(self) -> dict:
        """
        Returns all tools registered by plugins.
        Called by assistant.py to merge into
        the main TOOLS dict.
        """
        with self._lock:
            return dict(self._dynamic_tools)

    def get_dynamic_prompt(self) -> str:
        """
        Returns extra prompt lines from plugins.
        Injected into SYSTEM_PROMPT automatically.
        """
        with self._lock:
            if not self._dynamic_hints:
                return ""
            lines = [
                "\nINSTALLED PLUGIN TOOLS:"]
            for hint in self._dynamic_hints:
                lines.append(hint)
            return "\n".join(lines)

    def _register_plugin_tools(
            self,
            plugin_name: str,
            module) -> None:
        """
        Read PLUGIN_INFO from the module and
        automatically register all its functions
        as Quartz tools.
        """
        info = getattr(
            module, "PLUGIN_INFO", {})
        commands = info.get("commands", [])
        description = info.get(
            "description", plugin_name)

        registered = []

        # The central registry owns runtime schemas, risk metadata and lookup.
        registered = register_plugin_tools(
            get_tool_registry(), plugin_name, module)

        with self._lock:
            for cmd in commands:
                func = getattr(module, cmd, None)
                if callable(func):
                    # Add to dynamic tools
                    self._dynamic_tools[cmd] = func
                    log.info(
                        "Registered tool: %s "
                        "from %s",
                        cmd, plugin_name)

            # Add to dynamic prompt
            if registered:
                cmds_str = "\n".join(
                    f'{cmd}("argument")'
                    for cmd in registered
                )
                hint = (
                    f"\n{description}:\n"
                    f"{cmds_str}"
                )
                # Remove old entry if updating
                self._dynamic_hints = [
                    h for h in
                    self._dynamic_hints
                    if plugin_name not in h
                ]
                self._dynamic_hints.append(hint)

        if registered:
            log.info(
                "Plugin '%s' registered "
                "%d tools: %s",
                plugin_name,
                len(registered),
                registered,
            )

    def _unregister_plugin_tools(
            self,
            plugin_name: str,
            module) -> None:
        """Remove plugin tools from registry."""
        unregister_plugin_tools(get_tool_registry(), plugin_name)
        info     = getattr(
            module, "PLUGIN_INFO", {})
        commands = info.get("commands", [])

        with self._lock:
            for cmd in commands:
                self._dynamic_tools.pop(
                    cmd, None)
            self._dynamic_hints = [
                h for h in self._dynamic_hints
                if plugin_name not in h
            ]

        log.info(
            "Unregistered tools for: %s",
            plugin_name)

    # ── Install ───────────────────────────────────────

    def install_from_github(
            self, url: str,
            auto_activate: bool = True) -> str:
        """
        Download and install a GitHub repo
        as a Quartz plugin.
        Tools register automatically.
        """
        url = url.strip().rstrip("/")

        if not _GITHUB_URL_RE.match(url):
            return (
                f"Invalid GitHub URL: {url}\n"
                "Expected: "
                "https://github.com/user/repo"
            )

        repo_name    = url.split("/")[-1]
        install_path = PLUGINS_DIR / repo_name
        pending_path = PENDING_DIR / repo_name

        if install_path.exists():
            return (
                f"Plugin '{repo_name}' is "
                f"already installed.\n"
                f"Use 'update plugin "
                f"{repo_name}' to upgrade."
            )

        if not self._git_available():
            return (
                "Git is not installed.\n"
                "Install from: "
                "https://git-scm.com"
            )

        try:
            log.info(
                "Installing: %s", repo_name)

            if pending_path.exists():
                rmtree_safe(pending_path)

            # Clone
            result = subprocess.run(
                ["git", "clone", url,
                 str(pending_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                return (
                    f"Git clone failed:\n"
                    f"{result.stderr}"
                )

            # Security scan
            scan = self._security_scan(
                pending_path)
            if not scan["safe"]:
                rmtree_safe(pending_path)
                return (
                    f"⚠️ SECURITY BLOCK\n"
                    f"Reason: {scan['reason']}\n"
                    f"Plugin NOT installed."
                )

            # Install requirements
            req_file = (
                pending_path / "requirements.txt")
            if req_file.exists():
                self._install_requirements(
                    req_file)

            # Move to installed
            shutil.move(
                str(pending_path),
                str(install_path))

            self._registry_add(
                repo_name, url)

            self._log_event({
                "action":    "install",
                "plugin":    repo_name,
                "url":       url,
                "timestamp": _now(),
                "status":    "success",
            })

            # Auto-activate and register tools
            if auto_activate:
                load_msg = self.load_plugin(
                    repo_name)
                return (
                    f"✅ '{repo_name}' installed"
                    f" and activated!\n"
                    f"{load_msg}"
                )

            return (
                f"✅ '{repo_name}' installed."
            )

        except subprocess.TimeoutExpired:
            if pending_path.exists():
                rmtree_safe(pending_path)
            return "Timeout: download too long."
        except Exception as exc:
            if pending_path.exists():
                rmtree_safe(pending_path)
            self._log_event({
                "action":    "install",
                "plugin":    repo_name,
                "url":       url,
                "timestamp": _now(),
                "status":    f"failed: {exc}",
            })
            log.exception("Install failed")
            return (
                f"❌ Installation failed: {exc}")

    # ── Load plugin ───────────────────────────────────

    def load_plugin(self,
                    plugin_name: str) -> str:
        """
        Dynamically load a plugin.
        Automatically registers its tools.
        No manual code changes needed.
        """
        plugin_path = PLUGINS_DIR / plugin_name

        if not plugin_path.exists():
            return (
                f"Plugin directory not found: "
                f"{plugin_name}"
            )

        for entry in [
            "quartz_plugin.py",
            "main.py",
            "__init__.py",
        ]:
            ep = plugin_path / entry
            if not ep.exists():
                continue

            try:
                spec = (
                    importlib.util
                    .spec_from_file_location(
                        plugin_name, ep))
                module = (
                    importlib.util
                    .module_from_spec(spec))
                sys.modules[
                    plugin_name] = module
                spec.loader.exec_module(module)

                # Call register()
                if hasattr(module, "register"):
                    try:
                        module.register()
                    except Exception as exc:
                        log.warning(
                            "register() error "
                            "%s: %s",
                            plugin_name, exc)

                with self._lock:
                    self._loaded_plugins[
                        plugin_name] = module

                # ── Auto-register tools ───────
                self._register_plugin_tools(
                    plugin_name, module)

                # ── Update assistant TOOLS ────
                self._inject_into_assistant(
                    plugin_name, module)

                log.info(
                    "Plugin loaded: %s",
                    plugin_name)

                # Get tool names for message
                info = getattr(
                    module,
                    "PLUGIN_INFO", {})
                cmds = info.get("commands", [])
                cmds_str = (
                    ", ".join(cmds)
                    if cmds
                    else "no commands listed"
                )

                return (
                    f"🟢 '{plugin_name}' active!"
                    f"\n   Tools: {cmds_str}\n"
                    f"   Ready to use "
                    f"immediately."
                )

            except Exception as exc:
                log.exception(
                    "Load error: %s",
                    plugin_name)
                return (
                    f"⚠️ Installed but failed "
                    f"to load: {exc}"
                )

        return (
            f"'{plugin_name}' installed but "
            f"no entry point found.\n"
            f"Expected: quartz_plugin.py, "
            f"main.py, or __init__.py"
        )

    def _inject_into_assistant(
            self,
            plugin_name: str,
            module) -> None:
        log.debug("Plugin %s is live through ToolRegistry", plugin_name)
        return

        """
        Inject plugin tools directly into
        the running assistant TOOLS dict.
        This is the key to plug-and-play —
        no restart needed!
        """
        try:
            import assistant as asst

            info     = getattr(
                module, "PLUGIN_INFO", {})
            commands = info.get("commands", [])

            injected = []
            for cmd in commands:
                func = getattr(
                    module, cmd, None)
                if callable(func):
                    asst.TOOLS[cmd] = func
                    injected.append(cmd)

            if injected:
                # Rebuild the tool regex
                asst._TOOL_RE = (
                    __import__("re").compile(
                        r"\b(?P<name>"
                        + "|".join(
                            __import__("re")
                            .escape(k)
                            for k in asst.TOOLS
                        )
                        + r")\s*\("
                        r"(?P<args>[^)]*)\)",
                        __import__("re").DOTALL,
                    )
                )

                # Add to system prompt
                desc = info.get(
                    "description",
                    plugin_name)
                prompt_addition = (
                    f"\n\nPLUGIN '{plugin_name}"
                    f"' TOOLS ({desc}):\n"
                )
                for cmd in injected:
                    prompt_addition += (
                        f'{cmd}("argument")\n')

                asst.SYSTEM_PROMPT += (
                    prompt_addition)

                log.info(
                    "Injected %d tools into "
                    "assistant: %s",
                    len(injected), injected)

        except Exception as exc:
            log.warning(
                "Assistant injection failed: "
                "%s", exc)

    # ── Update ────────────────────────────────────────

    def update_plugin(self,
                      plugin_name: str) -> str:
        install_path = PLUGINS_DIR / plugin_name

        if not install_path.exists():
            return (
                f"Plugin '{plugin_name}' "
                f"not found.")

        if not self._git_available():
            return "Git is not available."

        try:
            self._backup_plugin(plugin_name)

            result = subprocess.run(
                ["git", "-C",
                 str(install_path), "pull"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                self.rollback_plugin(plugin_name)
                return (
                    f"Update failed:\n"
                    f"{result.stderr}\n"
                    f"Rolled back."
                )

            if ("Already up to date"
                    in result.stdout):
                return (
                    f"✅ '{plugin_name}' "
                    f"already up to date."
                )

            # Reload with new tools
            if plugin_name in (
                    self._loaded_plugins):
                # Unregister old tools first
                old_mod = (
                    self._loaded_plugins[
                        plugin_name])
                self._unregister_plugin_tools(
                    plugin_name, old_mod)
                self.load_plugin(plugin_name)

            self._log_event({
                "action":    "update",
                "plugin":    plugin_name,
                "timestamp": _now(),
                "status":    "success",
            })

            return (
                f"✅ '{plugin_name}' updated "
                f"and reloaded."
            )

        except subprocess.TimeoutExpired:
            return "Update timed out."
        except Exception as exc:
            self.rollback_plugin(plugin_name)
            log.exception("Update failed")
            return (
                f"❌ Update failed: {exc}\n"
                f"Rolled back."
            )

    def update_all_plugins(self) -> str:
        if not any(
            PLUGINS_DIR.iterdir()
            if PLUGINS_DIR.exists()
            else []
        ):
            return "No plugins installed."

        results = []
        for plugin_dir in (
                PLUGINS_DIR.iterdir()):
            if plugin_dir.is_dir():
                result = self.update_plugin(
                    plugin_dir.name)
                results.append(
                    f"• {plugin_dir.name}: "
                    f"{result}")

        return "\n".join(results)

    # ── Remove ────────────────────────────────────────

    def remove_plugin(self,
                      plugin_name: str) -> str:
        install_path = PLUGINS_DIR / plugin_name

        if not install_path.exists():
            return (
                f"Plugin '{plugin_name}' "
                f"not found.")

        try:
            with self._lock:
                module = (
                    self._loaded_plugins
                    .get(plugin_name))
                if module:
                    # Unregister tools
                    self._unregister_plugin_tools(
                        plugin_name, module)

                    if hasattr(
                            module,
                            "unregister"):
                        try:
                            module.unregister()
                        except Exception:
                            pass

                    del self._loaded_plugins[
                        plugin_name]

                if plugin_name in sys.modules:
                    del sys.modules[
                        plugin_name]

            rmtree_safe(install_path)
            self._registry_remove(plugin_name)

            self._log_event({
                "action":    "remove",
                "plugin":    plugin_name,
                "timestamp": _now(),
                "status":    "success",
            })

            return (
                f"✅ '{plugin_name}' removed."
            )

        except Exception as exc:
            log.exception("Remove failed")
            return f"❌ Remove failed: {exc}"

    # ── Rollback ──────────────────────────────────────

    def rollback_plugin(self,
                        plugin_name: str) -> str:
        backup_path  = BACKUPS_DIR / plugin_name
        install_path = PLUGINS_DIR / plugin_name

        if not backup_path.exists():
            return (
                f"No backup found for "
                f"'{plugin_name}'.")

        try:
            self._rollback.restore(backup_path, install_path)

            if plugin_name in (
                    self._loaded_plugins):
                self.load_plugin(plugin_name)

            self._log_event({
                "action":    "rollback",
                "plugin":    plugin_name,
                "timestamp": _now(),
                "status":    "success",
            })

            return (
                f"✅ '{plugin_name}' "
                f"rolled back."
            )

        except Exception as exc:
            log.exception("Rollback failed")
            return (
                f"❌ Rollback failed: {exc}")

    # ── List ──────────────────────────────────────────

    def list_plugins(self) -> str:
        if not PLUGINS_DIR.exists():
            return "No plugins directory."

        plugins = [
            d for d in PLUGINS_DIR.iterdir()
            if d.is_dir()
        ]

        if not plugins:
            return (
                "No plugins installed.\n"
                "Install with:\n"
                "install_plugin("
                "\"https://github.com/"
                "user/repo\")"
            )

        lines = ["📦 Installed Plugins:\n"]
        for p in sorted(plugins):
            with self._lock:
                active = (
                    p.name in
                    self._loaded_plugins)
            status = (
                "🟢 Active"
                if active
                else "⚫ Inactive"
            )

            # Get tools list
            mod = self._loaded_plugins.get(
                p.name)
            if mod:
                info = getattr(
                    mod, "PLUGIN_INFO", {})
                cmds = info.get("commands", [])
                tools_str = (
                    f" → {', '.join(cmds)}"
                    if cmds else ""
                )
            else:
                tools_str = ""

            version = (
                self._get_plugin_version(p))
            ver_str = (
                f" v{version}"
                if version else "")

            lines.append(
                f"  {status}  "
                f"{p.name}{ver_str}"
                f"{tools_str}"
            )

        lines.append(
            f"\nTotal: {len(plugins)} "
            f"plugin(s)"
        )
        return "\n".join(lines)

    # ── Self upgrade ──────────────────────────────────

    def self_upgrade(self) -> str:
        if not self._git_available():
            return "Git is not available."

        try:
            git_dir = BASE_DIR / ".git"
            if not git_dir.exists():
                return (
                    "Quartz core is not a "
                    "Git repository.\n"
                    "Cannot self-upgrade."
                )

            result = subprocess.run(
                ["git", "-C",
                 str(BASE_DIR), "pull"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return (
                    f"Self-upgrade failed:\n"
                    f"{result.stderr}"
                )

            if ("Already up to date"
                    in result.stdout):
                return (
                    "✅ Quartz core is already "
                    "up to date."
                )

            self._log_event({
                "action":    "self_upgrade",
                "plugin":    "QUARTZ_CORE",
                "timestamp": _now(),
                "status":    "success",
            })

            return (
                "✅ Quartz core updated!\n"
                "Please restart to apply "
                "all changes."
            )

        except subprocess.TimeoutExpired:
            return "Self-upgrade timed out."
        except Exception as exc:
            log.exception(
                "Self-upgrade failed")
            return (
                f"❌ Self-upgrade failed: "
                f"{exc}"
            )

    # ── Security scan ─────────────────────────────────

    def _security_scan(self,
                       path: Path) -> dict:
        py_files = list(path.rglob("*.py"))

        if len(py_files) > 500:
            return {
                "safe":   False,
                "reason": (
                    f"Too many files "
                    f"({len(py_files)}). "
                    f"Suspicious."
                ),
            }

        for py_file in py_files:
            try:
                content = py_file.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            except Exception:
                continue

            for pattern in _DANGEROUS_PATTERNS:
                if pattern in content:
                    return {
                        "safe":   False,
                        "reason": (
                            f"Dangerous pattern "
                            f"'{pattern}' in "
                            f"{py_file.name}"
                        ),
                    }

        return {
            "safe":   True,
            "reason": "All checks passed",
        }

    # ── Requirements ──────────────────────────────────

    def _install_requirements(
            self, req_file: Path) -> dict:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip",
                 "install", "-r",
                 str(req_file), "--quiet"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return {"ok": True,
                        "msg": "OK"}
            return {
                "ok":  False,
                "msg": result.stderr[:200],
            }
        except Exception as exc:
            return {
                "ok": False, "msg": str(exc)}

    # ── Backup ────────────────────────────────────────

    def _backup_plugin(self,
                       plugin_name: str):
        source = PLUGINS_DIR / plugin_name
        backup = BACKUPS_DIR / plugin_name
        if not source.exists():
            return
        try:
            self._rollback.backup(source, backup)
        except Exception as exc:
            log.warning(
                "Backup failed: %s — %s",
                plugin_name, exc)

    # ── Registry ──────────────────────────────────────

    def _registry_add(self, name: str,
                      url: str):
        try:
            data = load_json(
                REGISTRY_FILE, {"installed": {}, "disabled": {}})
            data.setdefault(
                "installed", {})[name] = {
                "url":          url,
                "installed_at": _now(),
            }
            atomic_write_json(REGISTRY_FILE, data)
        except Exception as exc:
            log.warning(
                "Registry add failed: %s",
                exc)

    def _registry_remove(self, name: str):
        try:
            data = load_json(
                REGISTRY_FILE, {"installed": {}, "disabled": {}})
            data.get(
                "installed", {}).pop(name, None)
            atomic_write_json(REGISTRY_FILE, data)
        except Exception as exc:
            log.warning(
                "Registry remove failed: %s",
                exc)

    # ── History ───────────────────────────────────────

    def _log_event(self, entry: dict):
        try:
            history = load_json(HISTORY_FILE, [])
            history.append(entry)
            history = history[-200:]
            atomic_write_json(HISTORY_FILE, history)
        except Exception as exc:
            log.warning(
                "History log failed: %s", exc)

    # ── Version reader ────────────────────────────────

    def _get_plugin_version(
            self,
            plugin_path: Path) -> Optional[str]:
        for entry in [
            "quartz_plugin.py",
            "main.py",
            "__init__.py",
        ]:
            ep = plugin_path / entry
            if not ep.exists():
                continue
            try:
                content = ep.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
                match = re.search(
                    r'["\']version["\']\s*:\s*'
                    r'["\']([^"\']+)["\']',
                    content,
                )
                if match:
                    return match.group(1)
                match = re.search(
                    r'__version__\s*=\s*'
                    r'["\']([^"\']+)["\']',
                    content,
                )
                if match:
                    return match.group(1)
            except Exception:
                pass
        return None

    # ── Git check ─────────────────────────────────────

    @staticmethod
    def _git_available() -> bool:
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except Exception:
            return False


# ── Helper ────────────────────────────────────────────

def _now() -> str:
    return datetime.now().isoformat()
