"""
core/tool_workbench/catalog.py
Tool Catalog and Capability Resolver for Quartz Tool Workbench.
Maps investigation capability requirements to manifest-backed tools.
"""

from __future__ import annotations

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
        platform=["win32", "windows", "win_amd64", "x86_64"],
        capabilities=["binary_string_search", "pattern_search", "symbol_scan", "text_search"],
        executable_subpath="ripgrep-14.1.1-x86_64-pc-windows-msvc/rg.exe",
        supported_operations={
            "search": {
                "description": "Search regex or literal pattern in target file or directory",
                "options": {
                    "pattern": {"type": "string", "required": True},
                    "case_sensitive": {"type": "boolean", "default": False},
                    "fixed_strings": {"type": "boolean", "default": False},
                    "max_count": {"type": "integer", "default": None},
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
    "pe_inspector": ToolManifest(
        tool_id="pe_inspector",
        name="PE Header & Binary Structure Inspector",
        version="1.0.0",
        source_url="https://github.com/quartz-assistant/pe-inspector/releases/download/v1.0.0/pe_inspector-1.0.0.zip",
        pinned_revision="1.0.0",
        package_digest="8f4b23c91d908bb945d7d9fa81fbfb7c2576b2512e9b0b4b2cb8ebdf596cb101",
        license="MIT",
        platform=["win32", "windows", "win_amd64", "x86_64", "any"],
        capabilities=["pe_header_analysis", "section_dump", "export_table", "import_table"],
        executable_subpath="pe_inspector.py",
        dependencies=["python>=3.10"],
        supported_operations={
            "headers": {
                "description": "Dump DOS, COFF and Optional PE headers as JSON",
                "options": {
                    "json_output": {"type": "boolean", "default": True},
                },
                "allowed_flags": ["--headers", "--json"],
            },
            "sections": {
                "description": "List sections with virtual addresses, raw sizes and entropy",
                "options": {
                    "json_output": {"type": "boolean", "default": True},
                },
                "allowed_flags": ["--sections", "--json"],
            },
            "imports": {
                "description": "List imported DLLs and imported function symbols",
                "options": {
                    "json_output": {"type": "boolean", "default": True},
                },
                "allowed_flags": ["--imports", "--json"],
            },
        },
        max_timeout_seconds=30.0,
        default_timeout_seconds=10.0,
    ),
    "rea_static": ToolManifest(
        tool_id="rea_static",
        name="REA Static Artifact Adapter",
        version="6.8.0",
        source_url="https://github.com/quartz-assistant/rea-agents/releases/download/v6.8.0/rea-agents-6.8.0.zip",
        pinned_revision="6.8.0",
        package_digest="7a9e014e21a8d05fc86bc052df120786cfba3a32cb1689255e3e2cf6f74a0bb2",
        license="Proprietary",
        platform=["win32", "windows", "win_amd64", "x86_64"],
        capabilities=["static_disassembly", "code_flow_analysis", "game_engine_fingerprint"],
        executable_subpath="node_modules/rea-agents/scripts/rea.mjs",
        dependencies=["node>=22.23.4"],
        supported_operations={
            "inspect-artifact": {
                "description": "Run REA static artifact inspection",
                "options": {
                    "detail": {"type": "string", "default": "summary"},
                    "json_output": {"type": "boolean", "default": True},
                },
                "allowed_flags": ["inspect-artifact", "--detail", "--json", "--evidence_output"],
            },
        },
        max_timeout_seconds=90.0,
        default_timeout_seconds=30.0,
    ),
}


class ToolCatalog:
    """Registry of verified tool manifests with capability matching."""

    def __init__(self, manifests: Optional[Dict[str, ToolManifest]] = None):
        self._manifests: Dict[str, ToolManifest] = dict(manifests or BUILTIN_MANIFESTS)

    def register(self, manifest: ToolManifest) -> None:
        """Register or update a tool manifest."""
        if not isinstance(manifest, ToolManifest):
            raise TypeError("Expected ToolManifest instance")
        self._manifests[manifest.tool_id] = manifest

    def get(self, tool_id: str) -> Optional[ToolManifest]:
        """Get manifest by tool ID."""
        return self._manifests.get(tool_id)

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
            if is_win and plat_lower in {"windows", "win32", "win_amd64", "x86_64"}:
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

        primary_req = req_list[0]
        desired_cap = primary_req.get("capability_id", "")
        desired_tool_id = primary_req.get("tool_id")
        target_format = primary_req.get("target_format", "")

        candidates: List[ToolManifest] = []

        if desired_tool_id and desired_tool_id in self._manifests:
            candidates.append(self._manifests[desired_tool_id])
        else:
            for manifest in self._manifests.values():
                if desired_cap and desired_cap in manifest.capabilities:
                    candidates.append(manifest)

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
            "manifest_object": selected,
            "capability_id": desired_cap,
            "license": selected.license,
            "pinned_revision": selected.pinned_revision,
            "package_digest": selected.package_digest,
            "limitations": [],
        }
