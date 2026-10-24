"""Plugin metadata validation and central tool registration."""

from dataclasses import dataclass
from types import ModuleType

from core.tool_registry import ToolRegistry


@dataclass(frozen=True)
class PluginManifest:
    name: str
    description: str
    commands: tuple[str, ...]
    risks: dict


def read_manifest(module: ModuleType, fallback_name: str) -> PluginManifest:
    info = getattr(module, "PLUGIN_INFO", {})
    if not isinstance(info, dict):
        raise ValueError("PLUGIN_INFO must be a dictionary")
    commands = info.get("commands", [])
    if not isinstance(commands, (list, tuple)) or not all(
            isinstance(item, str) and item for item in commands):
        raise ValueError("PLUGIN_INFO.commands must contain tool names")
    risks = info.get("risks", {})
    if not isinstance(risks, dict):
        raise ValueError("PLUGIN_INFO.risks must be a dictionary")
    return PluginManifest(
        name=str(info.get("name") or fallback_name),
        description=str(info.get("description") or fallback_name),
        commands=tuple(commands), risks=risks,
    )


def register_plugin_tools(registry: ToolRegistry, plugin_name: str,
                          module: ModuleType) -> list[str]:
    manifest = read_manifest(module, plugin_name)
    registered = []
    for command in manifest.commands:
        function = getattr(module, command, None)
        if not callable(function):
            raise ValueError(f"Plugin tool is missing or not callable: {command}")
        registry.register(
            command, function,
            risk=str(manifest.risks.get(command, "read")),
            source=f"plugin:{plugin_name}",
        )
        registered.append(command)
    return registered


def unregister_plugin_tools(registry: ToolRegistry, plugin_name: str) -> None:
    registry.unregister_source(f"plugin:{plugin_name}")
