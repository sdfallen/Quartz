"""
core/tool_workbench/catalog.py
Tool Catalog and Capability Resolver for SpeS Tool Workbench.
Maps investigation capability requirements to manifest-backed tools.
"""

from __future__ import annotations

from copy import deepcopy
import logging
import platform
import sys
from typing import Any, Dict, List, Optional, Union

from core.tool_workbench.contracts import Capability, ToolManifest
from core.tool_workbench.errors import IncompatiblePlatformError, ResolutionError

log = logging.getLogger("quartz.workbench.catalog")

# Official Pinned Tool Manifests
BUILTIN_MANIFESTS: Dict[str, ToolManifest] = {
    "ripgrep": ToolManifest(
        tool_id="ripgrep",
        name="ripgrep (fast binary and text pattern search)",
        version="14.1.1",
        source_url="https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-pc-windows-msvc.zip",
        pinned_revision="14.1.1",
        package_digest="d0f534024c42afd6cb4d38907c25cd2b249b79bbe6cc1dbee8e3e37c2b6e25a1",
        license="MIT OR Unlicense",
        platform=["win_amd64"],
        capabilities=["binary_string_search", "pattern_search", "text_search"],
        executable_subpath="ripgrep-14.1.1-x86_64-pc-windows-msvc/rg.exe",
        supported_operations={
            "search": {
                "description": "Search regex or literal pattern in target file or directory",
                "options": {
                    "pattern": {"type": "string", "required": True},
                    "case_sensitive": {"type": "boolean", "default": False},
                    "fixed_strings": {"type": "boolean", "default": False},
                    "max_count": {"type": "integer", "minimum": 1, "maximum": 100000, "default": None},
                    "json_output": {"type": "boolean", "default": False},
                },
                "allowed_flags": ["-i", "-F", "-m", "--json", "-a", "--color", "--no-config"],
            },
            "strings": {
                "description": "Extract and match strings in binary/PE targets",
                "options": {
                    "pattern": {"type": "string", "required": False, "default": "[ -~]{4,}"},
                    "case_sensitive": {"type": "boolean", "default": True},
                    "json_output": {"type": "boolean", "default": False},
                },
                "allowed_flags": ["-a", "-i", "--json", "--color", "--no-config"],
            },
            "version": {
                "description": "Query ripgrep version",
                "options": {},
                "allowed_flags": ["--version"],
            },
        },
        max_timeout_seconds=60.0,
        default_timeout_seconds=15.0,
    ),

}


class ToolCatalog:
    """Registry of verified tool manifests with capability matching."""

    def __init__(self, manifests: Optional[Dict[str, ToolManifest]] = None):
        self._manifests: Dict[str, ToolManifest] = deepcopy(BUILTIN_MANIFESTS if manifests is None else manifests)

    def register(self, manifest: ToolManifest) -> None:
        """Register or update a tool manifest."""
        if not isinstance(manifest, ToolManifest):
            raise TypeError("Expected ToolManifest instance")
        self._manifests[manifest.tool_id] = deepcopy(manifest)

    def get(self, tool_id: str) -> Optional[ToolManifest]:
        """Get manifest by tool ID."""
        return deepcopy(self._manifests.get(tool_id))

    def catalog(self, query: Optional[Union[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """List registered tools matching an optional query string or capability dictionary."""
        results: List[Dict[str, Any]] = []

        q_str = ""
        q_cap = ""
        if isinstance(query, str):
            q_str = query.strip().lower()
        elif isinstance(query, dict):
            q_str = str(query.get("query", "")).strip().lower()
            q_cap = str(query.get("capability", "")).strip().lower()

        for manifest in self._manifests.values():
            if q_cap and q_cap not in [c.lower() for c in manifest.capabilities]:
                continue
            if q_str:
                match_id = q_str in manifest.tool_id.lower()
                match_name = q_str in manifest.name.lower()
                match_cap = any(q_str in c.lower() for c in manifest.capabilities)
                if not (match_id or match_name or match_cap):
                    continue

            results.append(manifest.to_dict())

        return results

    def is_platform_compatible(self, manifest: ToolManifest) -> bool:
        """Check if manifest is compatible with current OS and architecture."""
        host_sys = sys.platform.lower()
        host_arch = platform.machine().lower()

        is_win = host_sys.startswith("win")
        for plat in manifest.platform:
            plat_lower = plat.lower()
            if plat_lower in {"any", "all"}:
                return True
            if is_win and (plat_lower in {"windows", "win32"} or
                           plat_lower in {"win_amd64", "x86_64"} and host_arch in {"amd64", "x86_64"}):
                return True
        return False

    def resolve(self, requirements: Union[List[Dict[str, Any]], Dict[str, Any], str]) -> Dict[str, Any]:
        """
        Resolve capability requirements to a candidate tool manifest.
        Returns a dictionary with status, tool_manifest, and compatibility details.
        """
        if isinstance(requirements, str):
            req_list = [{"capability_id": requirements}]
        elif isinstance(requirements, dict):
            if "capability_id" in requirements:
                req_list = [requirements]
            elif "requirements" in requirements and isinstance(requirements["requirements"], list):
                req_list = requirements["requirements"]
            else:
                req_list = [requirements]
        elif isinstance(requirements, list):
            req_list = requirements
        else:
            raise ValueError("Requirements must be a capability string, dict, or list of dicts")

        if not req_list:
            raise ResolutionError("No capability requirements provided for resolution")

        if any(not isinstance(r, dict) for r in req_list):
            raise ResolutionError("Invalid capability requirement")
        primary_req = req_list[0]
        desired_cap = primary_req.get("capability_id", "")
        desired_tool_id = primary_req.get("tool_id")
        def matches(manifest):
            for requirement in req_list:
                capability = requirement.get("capability_id")
                identity = requirement.get("tool_id")
                fmt = requirement.get("target_format")
                if identity and identity != manifest.tool_id: return False
                if capability and capability not in manifest.capabilities: return False
                if not identity and not capability: return False
                # Registered search adapter reads one approved file; unsupported
                # format declarations must not silently resolve to weaker tools.
                formats = {"pe", "dotnet", "native", "archive", "json", "text", "unknown"} if manifest.tool_id == "ripgrep" else set()
                if fmt and fmt not in formats: return False
            return True
        candidates = [m for m in self._manifests.values() if matches(m)]

        if not candidates:
            return {
                "status": "unsupported",
                "resolved": False,
                "tool_id": None,
                "manifest": None,
                "reason": f"No tool provides requested capability: {desired_cap or desired_tool_id}",
                "limitations": [f"Capability {desired_cap} is not covered by catalog manifests"],
            }

        compatible: List[ToolManifest] = []
        for cand in candidates:
            if not self.is_platform_compatible(cand):
                continue
            compatible.append(cand)

        if not compatible:
            return {
                "status": "unsupported",
                "resolved": False,
                "tool_id": candidates[0].tool_id,
                "manifest": None,
                "reason": f"Candidate tool '{candidates[0].tool_id}' is incompatible with platform {sys.platform}",
                "limitations": ["Platform architecture mismatch"],
            }

        selected = compatible[0]
        return {
            "status": "resolved",
            "resolved": True,
            "tool_id": selected.tool_id,
            "manifest": selected.to_dict(),
            "capability_id": desired_cap,
            "license": selected.license,
            "pinned_revision": selected.pinned_revision,
            "package_digest": selected.package_digest,
            "limitations": [],
        }
