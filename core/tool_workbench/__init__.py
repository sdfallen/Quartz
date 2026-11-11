"""
core/tool_workbench
Quartz Tool Workbench package for capability resolution, isolated tool acquisition,
and supervised execution.
"""

from core.tool_workbench.acquisition import ToolAcquirer, get_default_managed_dir
from core.tool_workbench.catalog import BUILTIN_MANIFESTS, ToolCatalog
from core.tool_workbench.contracts import (
    AcquisitionPolicy,
    Capability,
    Target,
    ToolManifest,
    ToolReceipt,
    ToolRequest,
)
from core.tool_workbench.errors import (
    AcquisitionError,
    CancellationError,
    CorruptedArchiveError,
    DigestMismatchError,
    DownloadError,
    ExecutionError,
    IncompatiblePlatformError,
    OutputLimitExceededError,
    ResolutionError,
    SchemaValidationError,
    SecurityViolationError,
    TimeoutExpiredError,
    WorkbenchError,
)
from core.tool_workbench.execution import ToolExecutor
from core.tool_workbench.workbench import ToolWorkbench

__all__ = [
    "ToolWorkbench",
    "ToolCatalog",
    "ToolAcquirer",
    "ToolExecutor",
    "ToolRequest",
    "ToolReceipt",
    "ToolManifest",
    "Target",
    "Capability",
    "AcquisitionPolicy",
    "BUILTIN_MANIFESTS",
    "get_default_managed_dir",
    "WorkbenchError",
    "ResolutionError",
    "IncompatiblePlatformError",
    "AcquisitionError",
    "DigestMismatchError",
    "SecurityViolationError",
    "DownloadError",
    "CorruptedArchiveError",
    "ExecutionError",
    "SchemaValidationError",
    "TimeoutExpiredError",
    "OutputLimitExceededError",
    "CancellationError",
]
