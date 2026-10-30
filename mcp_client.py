"""
mcp_client.py  —  Quartz MCP Client
Connects Quartz to any MCP server.
Gives access to 1000s of agent skills.
"""

import asyncio
import json
import subprocess
import threading
import sys
import os
from pathlib import Path
from typing import Optional
from logger import get_logger

log = get_logger(__name__)

# ── Try importing MCP SDK ─────────────────────────────
try:
    import importlib.util as _mcp_spec
    if _mcp_spec.find_spec("mcp") is None:
        raise ImportError("mcp")
    def StdioServerParameters(*a, **kw):
        from mcp import StdioServerParameters as _S
        return _S(*a, **kw)
    def stdio_client(*a, **kw):
        from mcp.client.stdio import stdio_client as _c
        return _c(*a, **kw)
    def ClientSession(*a, **kw):
        from mcp import ClientSession as _C
        return _C(*a, **kw)
    MCP_AVAILABLE = True
    log.info("MCP SDK available")
except ImportError:
    MCP_AVAILABLE = False
    log.warning(
        "MCP SDK not installed.\n"
        "Run: pip install mcp")


class MCPSkillClient:
    """
    Connects Quartz to MCP servers.
    Each server provides a set of skills.
    """

    def __init__(self):
        self._servers    = {}
        self._tools      = {}
        self._lock       = threading.Lock()
        self._loop       = None
        self._thread     = None
        self._start_loop()
        log.info("MCPSkillClient ready")

    # ── Event loop in background thread ──────────────

    def _start_loop(self):
        """Start asyncio loop in background."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro):
        """Run async code from sync context."""
        future = asyncio.run_coroutine_threadsafe(
            coro, self._loop)
        return future.result(timeout=30)

    # ── Connect to MCP server ─────────────────────────

    def connect_server(
            self,
            name: str,
            command: str,
            args: list = None,
            env: dict = None) -> str:
        """
        Connect to an MCP server.
        command: executable to run
        args: arguments list
        env: environment variables
        """
        if not MCP_AVAILABLE:
            return (
                "MCP SDK not installed.\n"
                "Run: pip install mcp")

        try:
            result = self._run_async(
                self._connect_async(
                    name, command,
                    args or [], env or {}))
            return result
        except Exception as exc:
            log.exception(
                "MCP connect failed: %s", name)
            return f"Connection failed: {exc}"

    async def _connect_async(
            self, name: str,
            command: str,
            args: list,
            env: dict) -> str:
        """Async MCP server connection."""
        try:
            params = StdioServerParameters(
                command=command,
                args=args,
                env={
                    **os.environ,
                    **env,
                },
            )

            async with stdio_client(
                    params) as (read, write):
                async with ClientSession(
                        read, write) as session:

                    # Initialize session
                    await session.initialize()

                    # Get available tools
                    tools_result = (
                        await session.list_tools())
                    tools = tools_result.tools

                    # Register tools
                    tool_names = []
                    with self._lock:
                        self._servers[name] = {
                            "command": command,
                            "args":    args,
                            "env":     env,
                            "tools":   [
                                t.name
                                for t in tools],
                        }
                        for tool in tools:
                            self._tools[
                                tool.name] = {
                                "server":      name,
                                "description": (
                                    tool.description
                                    or ""),
                                "schema":      (
                                    tool.inputSchema
                                    or {}),
                            }
                            tool_names.append(
                                tool.name)

                    return (
                        f"✅ MCP Server "
                        f"'{name}' connected!\n"
                        f"   Tools: "
                        f"{', '.join(tool_names)}"
                    )

        except Exception as exc:
            return (
                f"MCP connection error: {exc}")

    # ── Call MCP tool ─────────────────────────────────

    def call_tool(
            self,
            tool_name: str,
            arguments: dict = None) -> str:
        """Call an MCP tool by name."""
        if not MCP_AVAILABLE:
            return "MCP SDK not installed."

        with self._lock:
            tool_info = self._tools.get(
                tool_name)

        if not tool_info:
            available = list(
                self._tools.keys())
            return (
                f"Tool '{tool_name}' not found."
                f"\nAvailable: "
                f"{', '.join(available[:5])}"
                if available
                else "No MCP tools loaded yet."
            )

        try:
            server_name = tool_info["server"]
            with self._lock:
                server = self._servers.get(
                    server_name, {})

            result = self._run_async(
                self._call_tool_async(
                    server_name,
                    server.get("command"),
                    server.get("args", []),
                    server.get("env", {}),
                    tool_name,
                    arguments or {},
                )
            )
            return result

        except Exception as exc:
            log.exception(
                "Tool call failed: %s",
                tool_name)
            return f"Tool error: {exc}"

    async def _call_tool_async(
            self,
            server_name: str,
            command: str,
            args: list,
            env: dict,
            tool_name: str,
            arguments: dict) -> str:
        """Async tool execution."""
        try:
            params = StdioServerParameters(
                command=command,
                args=args,
                env={**os.environ, **env},
            )

            async with stdio_client(
                    params) as (read, write):
                async with ClientSession(
                        read, write) as session:

                    await session.initialize()

                    result = (
                        await session.call_tool(
                            tool_name,
                            arguments,
                        )
                    )

                    # Extract text from result
                    if result.content:
                        parts = []
                        for c in result.content:
                            if hasattr(c, "text"):
                                parts.append(
                                    c.text)
                            else:
                                parts.append(
                                    str(c))
                        return "\n".join(parts)

                    return (
                        f"Tool '{tool_name}' "
                        f"completed.")

        except Exception as exc:
            return f"Execution error: {exc}"

    # ── List tools ────────────────────────────────────

    def list_skills(self) -> str:
        """List all available MCP skills."""
        with self._lock:
            servers = dict(self._servers)
            tools   = dict(self._tools)

        if not servers:
            return (
                "No MCP servers connected.\n\n"
                "Connect one with:\n"
                "connect_mcp_server("
                "\"name\", \"command\")\n\n"
                "Or install a skill:\n"
                "install_mcp_skill("
                "\"filesystem\")"
            )

        lines = [
            f"🔌 MCP Skills "
            f"({len(tools)} tools "
            f"from {len(servers)} servers)\n"
        ]

        for srv_name, srv in servers.items():
            srv_tools = srv.get("tools", [])
            lines.append(
                f"📦 {srv_name} "
                f"({len(srv_tools)} tools):"
            )
            for t in srv_tools[:8]:
                desc = tools.get(
                    t, {}).get(
                    "description", "")[:50]
                lines.append(
                    f"   • {t}"
                    + (f" — {desc}"
                       if desc else "")
                )
            if len(srv_tools) > 8:
                lines.append(
                    f"   ... and "
                    f"{len(srv_tools)-8} more"
                )
            lines.append("")

        return "\n".join(lines)

    def get_tools_for_assistant(
            self) -> dict:
        """
        Returns callable wrappers for
        all MCP tools. Injected into
        Quartz TOOLS dict automatically.
        """
        result = {}
        with self._lock:
            tools = dict(self._tools)

        for tool_name in tools:
            # Create closure for each tool
            def make_wrapper(tn):
                def wrapper(**kwargs) -> str:
                    return self.call_tool(
                        tn, kwargs)
                wrapper.__name__ = tn
                wrapper.__doc__  = (
                    tools[tn].get(
                        "description", ""))
                return wrapper
            result[tool_name] = (
                make_wrapper(tool_name))

        return result


# ── Built-in skill installers ─────────────────────────

class MCPSkillInstaller:
    """
    Installs and configures MCP skills
    without needing full GitHub repos.
    Just pip installs and configures.
    """

    SKILLS = {
        "filesystem": {
            "description": (
                "Read/write files and "
                "directories"),
            "package":  "mcp",
            "command":  "python",
            "args":     [
                "-m",
                "mcp.server.filesystem",
            ],
            "env":      {},
            "tools": [
                "read_file",
                "write_file",
                "list_directory",
                "create_directory",
                "move_file",
                "search_files",
                "get_file_info",
            ],
        },
        "fetch": {
            "description": (
                "Fetch web pages and "
                "extract content"),
            "package":  "mcp-server-fetch",
            "command":  "uvx",
            "args":     ["mcp-server-fetch"],
            "env":      {},
            "tools": [
                "fetch",
            ],
        },
        "memory": {
            "description": (
                "Persistent knowledge "
                "graph memory"),
            "package":  "mcp-memory",
            "command":  "npx",
            "args":     [
                "-y",
                "@modelcontextprotocol/"
                "server-memory",
            ],
            "env":      {},
            "tools": [
                "create_entities",
                "search_nodes",
                "add_observations",
                "delete_entities",
            ],
        },
        "brave_search": {
            "description": (
                "Web search via "
                "Brave Search API"),
            "package":  None,
            "command":  "npx",
            "args":     [
                "-y",
                "@modelcontextprotocol/"
                "server-brave-search",
            ],
            "env":      {
                "BRAVE_API_KEY": "YOUR_KEY",
            },
            "tools": [
                "brave_web_search",
                "brave_local_search",
            ],
        },
        "github": {
            "description": (
                "Full GitHub control — "
                "repos, issues, PRs"),
            "package":  None,
            "command":  "npx",
            "args":     [
                "-y",
                "@modelcontextprotocol/"
                "server-github",
            ],
            "env":      {
                "GITHUB_PERSONAL_ACCESS_TOKEN":
                    "YOUR_TOKEN",
            },
            "tools": [
                "create_repository",
                "create_issue",
                "create_pull_request",
                "search_repositories",
                "get_file_contents",
                "push_files",
                "list_commits",
            ],
        },
        "sqlite": {
            "description": (
                "SQLite database "
                "operations"),
            "package":  "mcp-server-sqlite",
            "command":  "uvx",
            "args":     [
                "mcp-server-sqlite",
                "--db-path",
                str(
                    Path.home()
                    / "quartz.db"),
            ],
            "env":      {},
            "tools": [
                "read_query",
                "write_query",
                "create_table",
                "list_tables",
                "describe_table",
            ],
        },
    }

    def __init__(self):
        self._installed = {}
        self._config_file = (
            Path(__file__).parent
            / "mcp_skills.json"
        )
        self._load_config()

    def _load_config(self):
        """Load saved skill configs."""
        if self._config_file.exists():
            try:
                self._installed = json.loads(
                    self._config_file
                    .read_text(
                        encoding="utf-8"))
            except Exception:
                self._installed = {}

    def _save_config(self):
        """Save skill configs."""
        try:
            self._config_file.write_text(
                json.dumps(
                    self._installed,
                    indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning(
                "Config save failed: %s",
                exc)

    def list_available(self) -> str:
        """List all available MCP skills."""
        lines = [
            "🔌 Available MCP Skills:\n"]

        for name, info in self.SKILLS.items():
            installed = (
                "✅ installed"
                if name in self._installed
                else "⬇️  available"
            )
            lines.append(
                f"  {installed}  "
                f"{name}\n"
                f"     {info['description']}\n"
                f"     Tools: "
                f"{', '.join(info['tools'][:3])}"
                + (
                    f" +{len(info['tools'])-3}"
                    f" more"
                    if len(info["tools"]) > 3
                    else ""
                )
            )

        lines.append(
            "\nInstall with:\n"
            "install_mcp_skill(\"name\")"
        )
        return "\n".join(lines)

    def install_skill(
            self,
            skill_name: str,
            api_key: str = "") -> str:
        """Install an MCP skill."""
        skill = self.SKILLS.get(skill_name)
        if not skill:
            available = list(
                self.SKILLS.keys())
            return (
                f"Skill '{skill_name}' "
                f"not found.\n"
                f"Available: "
                f"{', '.join(available)}"
            )

        results = []

        # Install Python package if needed
        pkg = skill.get("package")
        if pkg:
            results.append(
                f"Installing {pkg}...")
            try:
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-m", "pip",
                        "install", pkg,
                        "--quiet",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if proc.returncode == 0:
                    results.append(
                        f"✅ {pkg} installed")
                else:
                    results.append(
                        f"⚠️ {pkg}: "
                        f"{proc.stderr[:100]}")
            except Exception as exc:
                results.append(
                    f"Install error: {exc}")

        # Handle API key if needed
        env = dict(skill.get("env", {}))
        needs_key = any(
            "YOUR_" in v
            for v in env.values())

        if needs_key and api_key:
            for k in env:
                if "YOUR_" in env[k]:
                    env[k] = api_key

        elif needs_key and not api_key:
            key_names = [
                k for k, v in env.items()
                if "YOUR_" in v
            ]
            results.append(
                f"\n⚠️ API key required!\n"
                f"Provide key for: "
                f"{', '.join(key_names)}\n"
                f"Use: install_mcp_skill("
                f"\"{skill_name}\", "
                f"\"YOUR_API_KEY\")"
            )

        # Save configuration
        config = {
            "command": skill["command"],
            "args":    skill["args"],
            "env":     env,
            "tools":   skill["tools"],
        }
        self._installed[skill_name] = config
        self._save_config()

        results.append(
            f"\n✅ Skill '{skill_name}' "
            f"configured!\n"
            f"Tools: "
            f"{', '.join(skill['tools'])}\n"
            f"Activate with:\n"
            f"activate_mcp_skill("
            f"\"{skill_name}\")"
        )

        return "\n".join(results)

    def get_installed(self) -> dict:
        """Get all installed skill configs."""
        return dict(self._installed)


# ── Global instances ──────────────────────────────────
_mcp_client    = None
_mcp_installer = None


def get_mcp_client() -> MCPSkillClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPSkillClient()
    return _mcp_client


def get_mcp_installer() -> MCPSkillInstaller:
    global _mcp_installer
    if _mcp_installer is None:
        _mcp_installer = MCPSkillInstaller()
    return _mcp_installer