"""
core/tool_workbench/contracts.py
Typed data contracts and schemas for Quartz Tool Workbench (schema_version=1).
Fully compliant with docs/rea-system/TEAM_CONTRACT.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Union
import uuid


@dataclass
class Target:
    """Target application or binary under investigation."""
    target_id: str
    canonical_path: str
    sha256: str
    size: int
    format: str  # "pe", "dotnet", "native", "archive", "json", "unknown"
    version_fingerprint: str = ""
    approved_scope: Union[str, List[str]] = "read_only"

    @classmethod
    def from_file(cls, path: Union[str, Path], approved_scope: Union[str, List[str]] = "read_only") -> Target:
        p = Path(path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Target file not found: {p}")
        st = p.stat()
        hasher = hashlib.sha256()
        with p.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        digest = hasher.hexdigest()

        # Simple format detector
        suffix = p.suffix.lower()
        if suffix in {".exe", ".dll", ".sys"}:
            fmt = "pe"
        elif suffix in {".zip", ".tar", ".gz", ".7z"}:
            fmt = "archive"
        elif suffix in {".json", ".jsonl"}:
            fmt = "json"
        else:
            fmt = "native"

        return cls(
            target_id=f"target-{digest[:12]}",
            canonical_path=str(p),
            sha256=digest,
            size=st.st_size,
            format=fmt,
            version_fingerprint=f"mtime:{int(st.st_mtime)}",
            approved_scope=approved_scope,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "canonical_path": self.canonical_path,
            "sha256": self.sha256,
            "size": self.size,
            "format": self.format,
            "version_fingerprint": self.version_fingerprint,
            "approved_scope": self.approved_scope,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Target:
        if (not isinstance(data, dict) or type(data.get('size')) is not int
                or any(not isinstance(data.get(k), str) for k in ('target_id','canonical_path','sha256','format'))):
            raise ValueError('Invalid target field types')
        return cls(
            target_id=str(data.get("target_id", "")),
            canonical_path=str(data.get("canonical_path", "")),
            sha256=str(data.get("sha256", "")),
            size=int(data.get("size", 0)),
            format=str(data.get("format", "unknown")),
            version_fingerprint=str(data.get("version_fingerprint", "")),
            approved_scope=data.get("approved_scope", "read_only"),
        )


@dataclass
class Capability:
    """Tool capability declaration."""
    capability_id: str
    provider: str
    supported_formats: List[str] = field(default_factory=list)
    effects: List[str] = field(default_factory=lambda: ["read_target", "write_workspace", "execute_tool"])
    required_tools: List[str] = field(default_factory=list)
    available: bool = True
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "provider": self.provider,
            "supported_formats": list(self.supported_formats),
            "effects": list(self.effects),
            "required_tools": list(self.required_tools),
            "available": self.available,
            "limitations": list(self.limitations),
        }


@dataclass
class ToolManifest:
    """Manifest describing a resolvable and acquirable GitHub tool."""
    tool_id: str
    name: str
    version: str
    source_url: str
    pinned_revision: str
    package_digest: str  # Cryptographic SHA-256
    license: str
    platform: List[str]
    capabilities: List[str]
    executable_subpath: str
    supported_operations: Dict[str, Dict[str, Any]]
    dependencies: List[str] = field(default_factory=list)
    max_timeout_seconds: float = 60.0
    default_timeout_seconds: float = 15.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "version": self.version,
            "source_url": self.source_url,
            "pinned_revision": self.pinned_revision,
            "package_digest": self.package_digest,
            "license": self.license,
            "platform": list(self.platform),
            "capabilities": list(self.capabilities),
            "executable_subpath": self.executable_subpath,
            "supported_operations": dict(self.supported_operations),
            "dependencies": list(self.dependencies),
            "max_timeout_seconds": self.max_timeout_seconds,
            "default_timeout_seconds": self.default_timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolManifest:
        return cls(
            tool_id=str(data["tool_id"]),
            name=str(data.get("name", data["tool_id"])),
            version=str(data["version"]),
            source_url=str(data["source_url"]),
            pinned_revision=str(data["pinned_revision"]),
            package_digest=str(data["package_digest"]),
            license=str(data.get("license", "Unknown")),
            platform=list(data.get("platform", ["windows", "win32"])),
            capabilities=list(data.get("capabilities", [])),
            executable_subpath=str(data["executable_subpath"]),
            supported_operations=dict(data.get("supported_operations", {})),
            dependencies=list(data.get("dependencies", [])),
            max_timeout_seconds=float(data.get("max_timeout_seconds", 60.0)),
            default_timeout_seconds=float(data.get("default_timeout_seconds", 15.0)),
        )


@dataclass
class AcquisitionPolicy:
    """Security policy for managed tool downloads and installation."""
    allow_network: bool = True
    allowed_sources: List[str] = field(
        default_factory=lambda: [
            "https://github.com/",
            "https://raw.githubusercontent.com/",
        ]
    )
    managed_dir: Optional[str] = None
    verify_digest: bool = True
    max_download_bytes: int = 50 * 1024 * 1024  # 50 MB max
    max_uncompressed_bytes: int = 200 * 1024 * 1024  # 200 MB max uncompressed
    max_archive_entries: int = 2000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allow_network": self.allow_network,
            "allowed_sources": list(self.allowed_sources),
            "managed_dir": self.managed_dir,
            "verify_digest": self.verify_digest,
            "max_download_bytes": self.max_download_bytes,
            "max_uncompressed_bytes": self.max_uncompressed_bytes,
            "max_archive_entries": self.max_archive_entries,
        }


@dataclass
class ToolRequest:
    """Request to execute an operation with a managed or cataloged tool."""
    investigation_id: str
    step_id: str
    operation: str
    tool_id: str
    target: Optional[Union[Target, Dict[str, Any], str]] = None
    options: Dict[str, Any] = field(default_factory=dict)
    workspace: Optional[str] = None
    deadline_monotonic: float = 0.0
    max_output_bytes: int = 2 * 1024 * 1024  # 2 MB default
    request_id: str = field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}")

    def __post_init__(self):
        if not self.deadline_monotonic:
            self.deadline_monotonic = time.monotonic() + 30.0
        if isinstance(self.target, dict):
            self.target = Target.from_dict(self.target)
        elif isinstance(self.target, (str, Path)):
            self.target = Target.from_file(self.target)

    def to_dict(self) -> Dict[str, Any]:
        target_dict = None
        if isinstance(self.target, Target):
            target_dict = self.target.to_dict()
        elif isinstance(self.target, dict):
            target_dict = self.target
        elif self.target:
            target_dict = {"path": str(self.target)}

        return {
            "schema_version": 1,
            "request_id": self.request_id,
            "investigation_id": self.investigation_id,
            "step_id": self.step_id,
            "operation": self.operation,
            "tool_id": self.tool_id,
            "target": target_dict,
            "options": dict(self.options),
            "workspace": self.workspace,
            "deadline_monotonic": self.deadline_monotonic,
            "max_output_bytes": self.max_output_bytes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolRequest:
        if not isinstance(data, dict) or data.get('schema_version', 1) != 1:
            raise ValueError('Invalid tool request schema')
        for name in ('investigation_id','step_id','tool_id','operation','request_id'):
            if name in data and (not isinstance(data[name], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', data[name])):
                raise ValueError('Invalid tool request identity')
        limit = data.get('max_output_bytes', 2 * 1024 * 1024)
        deadline = data.get('deadline_monotonic', 0.0)
        if (type(limit) is not int or not 1 <= limit <= 8 * 1024 * 1024
                or type(deadline) not in (int, float) or not math.isfinite(deadline)):
            raise ValueError('Invalid tool request resource types')
        options = data.get('options', {})
        if not isinstance(options, dict) or len(json.dumps(options, allow_nan=False)) > 128 * 1024:
            raise ValueError('Invalid tool request options')
        if data.get('workspace') is not None and not isinstance(data['workspace'], str):
            raise ValueError('Invalid tool workspace')
        target = data.get("target")
        if isinstance(target, dict):
            target = Target.from_dict(target)
        return cls(
            request_id=str(data.get("request_id") or f"req-{uuid.uuid4().hex[:12]}"),
            investigation_id=str(data.get("investigation_id", "inv-default")),
            step_id=str(data.get("step_id", "step-0")),
            operation=str(data["operation"]),
            tool_id=str(data["tool_id"]),
            target=target,
            options=json.loads(json.dumps(options, allow_nan=False)),
            workspace=data.get("workspace"),
            deadline_monotonic=deadline,
            max_output_bytes=limit,
        )


@dataclass
class ToolReceipt:
    """Verifiable execution receipt returned upon tool completion or termination."""
    request_id: str
    tool_id: str
    source_url: str
    pinned_revision: str
    package_digest: str
    argv_redacted: List[str]
    process_identity: Dict[str, Any]
    timestamps: Dict[str, float]
    exit_code: Optional[int]
    status: str  # "confirmed" | "failed" | "timeout" | "cancelled" | "output_limit"
    cleanup_receipt: Dict[str, Any]
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    stdout: bytes = b""
    stderr: bytes = b""
    error_message: Optional[str] = None
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "tool_id": self.tool_id,
            "source_url": self.source_url,
            "pinned_revision": self.pinned_revision,
            "package_digest": self.package_digest,
            "argv_redacted": list(self.argv_redacted),
            "process_identity": dict(self.process_identity),
            "timestamps": dict(self.timestamps),
            "exit_code": self.exit_code,
            "status": self.status,
            "cleanup_receipt": dict(self.cleanup_receipt),
            "artifacts": list(self.artifacts),
            "limitations": list(self.limitations),
            "stdout_bytes": len(self.stdout),
            "stderr_bytes": len(self.stderr),
            "error_message": self.error_message,
        }
