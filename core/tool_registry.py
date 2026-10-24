"""Central tool metadata, schema generation, validation and plugin registry."""

import inspect
import threading
import types
from dataclasses import dataclass
from typing import Callable, Union, get_args, get_origin


@dataclass(frozen=True)
class ToolSpec:
    name: str
    function: Callable
    risk: str = "read"
    source: str = "core"


def _json_type(annotation) -> dict:
    if annotation is inspect.Parameter.empty:
        return {"type": "string"}
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        choices = [item for item in get_args(annotation) if item is not type(None)]
        return _json_type(choices[0]) if choices else {"type": "string"}
    mapping = {
        str: "string", int: "integer", float: "number",
        bool: "boolean", list: "array", dict: "object",
    }
    return {"type": mapping.get(origin or annotation, "string")}


class ToolRegistry:
    def __init__(self):
        self._specs: dict[str, ToolSpec] = {}
        self._tools: dict[str, Callable] = {}
        self._source_enabled: dict[str, bool] = {"core": True}
        self._lock = threading.RLock()

    @property
    def tools(self) -> dict:
        # Intentionally mutable for compatibility with older plugins and tests.
        return self._tools

    def register(self, name: str, function: Callable, *, risk: str = "read",
                 source: str = "core") -> None:
        if risk not in {"read", "write", "destructive", "system"}:
            raise ValueError(f"Invalid tool risk: {risk}")
        if not callable(function):
            raise TypeError(f"Tool {name} is not callable")
        with self._lock:
            self._specs[name] = ToolSpec(name, function, risk, source)
            self._tools[name] = function
            self._source_enabled.setdefault(source, True)

    def unregister(self, name: str) -> None:
        with self._lock:
            self._specs.pop(name, None)
            self._tools.pop(name, None)

    def unregister_source(self, source: str) -> None:
        with self._lock:
            names = [name for name, spec in self._specs.items()
                     if spec.source == source]
            for name in names:
                self._specs.pop(name, None)
                self._tools.pop(name, None)

    def function(self, name: str):
        with self._lock:
            spec = self._specs.get(name)
            if spec and not self._source_enabled.get(spec.source, True):
                return None
            return self._tools.get(name)

    def risk(self, name: str) -> str:
        with self._lock:
            spec = self._specs.get(name)
            return spec.risk if spec else "read"

    def names(self):
        with self._lock:
            return tuple(self._tools)

    def schemas(self) -> list:
        with self._lock:
            specs = [
                ToolSpec(name, function, self.risk(name),
                         self._specs.get(name, ToolSpec(name, function)).source)
                for name, function in self._tools.items()
                if self._source_enabled.get(
                    self._specs.get(name, ToolSpec(name, function)).source, True)
            ]
        return [self._schema(spec) for spec in specs]

    def validate(self, name: str, args=(), kwargs=None):
        function = self.function(name)
        if function is None:
            raise ValueError(f"Unknown tool: {name}")
        signature = inspect.signature(function)
        bound = signature.bind(*args, **(kwargs or {}))
        bound.apply_defaults()
        for key, value in bound.arguments.items():
            annotation = signature.parameters[key].annotation
            expected = get_origin(annotation) or annotation
            if expected in (str, int, float, bool, list, dict):
                if expected is int and isinstance(value, bool):
                    raise ValueError(f"{key} must be an integer")
                if not isinstance(value, expected):
                    raise ValueError(f"{key} has the wrong type")
        return function, bound.args, bound.kwargs

    def set_source_enabled(self, source: str, enabled: bool) -> None:
        if source == "core":
            raise ValueError("Core tools cannot be disabled as a group")
        with self._lock:
            if source not in self._source_enabled:
                raise ValueError(f"Unknown tool source: {source}")
            self._source_enabled[source] = bool(enabled)

    def permissions(self) -> list[dict]:
        with self._lock:
            grouped = {}
            for spec in self._specs.values():
                entry = grouped.setdefault(spec.source, {
                    "source": spec.source,
                    "enabled": self._source_enabled.get(spec.source, True),
                    "tools": [],
                })
                entry["tools"].append({"name": spec.name, "risk": spec.risk})
            return list(grouped.values())

    @staticmethod
    def _schema(spec: ToolSpec) -> dict:
        signature = inspect.signature(spec.function)
        properties, required = {}, []
        for param in signature.parameters.values():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            properties[param.name] = _json_type(param.annotation)
            if param.default is inspect.Parameter.empty:
                required.append(param.name)
        description = inspect.getdoc(spec.function) or f"Run the {spec.name} tool."
        return {"type": "function", "function": {
            "name": spec.name,
            "description": description.splitlines()[0][:250],
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False},
        }}


_global_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _global_registry
