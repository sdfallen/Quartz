"""
mcp_tools.py  —  Quartz MCP Tool Wrappers
Connects MCP client to Quartz TOOLS dict.
"""

from mcp_client import (
    get_mcp_client,
    get_mcp_installer,
)
from logger import get_logger

log = get_logger(__name__)


def list_mcp_skills() -> str:
    """List all available MCP skills."""
    installer = get_mcp_installer()
    return installer.list_available()


def install_mcp_skill(
        skill_name: str,
        api_key: str = "") -> str:
    """Install an MCP skill."""
    installer = get_mcp_installer()
    return installer.install_skill(
        skill_name, api_key)


def activate_mcp_skill(
        skill_name: str) -> str:
    """
    Activate an installed MCP skill.
    Connects to its server and registers
    all its tools in Quartz automatically.
    """
    installer = get_mcp_installer()
    installed = installer.get_installed()

    if skill_name not in installed:
        return (
            f"Skill '{skill_name}' not "
            f"installed.\n"
            f"Use: install_mcp_skill("
            f"\"{skill_name}\")")

    config  = installed[skill_name]
    client  = get_mcp_client()

    result = client.connect_server(
        name    = skill_name,
        command = config["command"],
        args    = config["args"],
        env     = config.get("env", {}),
    )

    # Inject new tools into Quartz
    if "✅" in result:
        try:
            import assistant as asst
            new_tools = (
                client.get_tools_for_assistant())
            for tool_name, func in (
                    new_tools.items()):
                asst.TOOLS[tool_name] = func
                log.info(
                    "MCP tool injected: %s",
                    tool_name)

            # Rebuild regex
            import re
            asst._TOOL_RE = re.compile(
                r"\b(?P<name>"
                + "|".join(
                    re.escape(k)
                    for k in asst.TOOLS
                )
                + r")\s*\("
                r"(?P<args>[^)]*)\)",
                re.DOTALL,
            )

            result += (
                f"\n🔧 Tools injected "
                f"into Quartz!"
            )
        except Exception as exc:
            log.warning(
                "Tool injection failed: %s",
                exc)

    return result


def show_mcp_tools() -> str:
    """Show all connected MCP tools."""
    client = get_mcp_client()
    return client.list_skills()


def use_mcp_tool(
        tool_name: str,
        argument: str = "") -> str:
    """Call any MCP tool directly."""
    client = get_mcp_client()
    args   = {}
    if argument:
        # Try to parse as JSON first
        try:
            import json
            args = json.loads(argument)
        except Exception:
            # Use as plain string argument
            args = {"input": argument}
    return client.call_tool(tool_name, args)