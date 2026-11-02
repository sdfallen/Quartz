"""
core/tool_workbench/errors.py
Explicit typed exceptions for Quartz Tool Workbench.
"""

from __future__ import annotations


class WorkbenchError(Exception):
    """Base exception for all Tool Workbench errors."""


class ResolutionError(WorkbenchError):
    """Raised when capability requirements cannot be resolved to a compatible tool."""


class IncompatiblePlatformError(ResolutionError):
    """Raised when a candidate tool does not support the host platform or OS."""


class AcquisitionError(WorkbenchError):
    """Base exception for tool acquisition and installation failures."""


class DigestMismatchError(AcquisitionError):
    """Raised when downloaded package checksum fails cryptographic verification."""


class SecurityViolationError(AcquisitionError):
    """Raised when an archive traversal, untrusted source, or unapproved script is detected."""


class DownloadError(AcquisitionError):
    """Raised when a network or HTTP error occurs during tool download."""


class CorruptedArchiveError(AcquisitionError):
    """Raised when an archive file is malformed, truncated, or invalid."""


class ExecutionError(WorkbenchError):
    """Base exception for tool execution failures."""


class SchemaValidationError(ExecutionError):
    """Raised when requested tool options or arguments fail schema validation."""


class TimeoutExpiredError(ExecutionError):
    """Raised when tool execution exceeds the monotonic deadline."""


class OutputLimitExceededError(ExecutionError):
    """Raised when tool stdout/stderr exceeds the maximum allowed output bytes."""


class CancellationError(ExecutionError):
    """Raised when tool execution is cancelled via cancel event or stop request."""
