"""
core/tool_workbench/workbench.py
Production Tool Workbench facade for Quartz REA system.
Implements catalog, resolve, acquire, execute, stop, and close lifecycle.
"""

from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Union

from core.tool_workbench.acquisition import ToolAcquirer, get_default_managed_dir
from core.tool_workbench.catalog import ToolCatalog
from core.tool_workbench.contracts import (
    AcquisitionPolicy,
    ToolManifest,
    ToolReceipt,
    ToolRequest,
)
from core.tool_workbench.errors import AcquisitionError, ExecutionError, ResolutionError
from core.tool_workbench.execution import ToolExecutor

log = logging.getLogger("quartz.workbench")


class ToolWorkbench:
    """
    Main Production Workbench Facade.
    Provides verified tool resolution, isolated managed acquisition, and supervised execution.
    """

    def __init__(
        self,
        managed_dir: Optional[Union[str, Path]] = None,
        workspace_dir: Optional[Union[str, Path]] = None,
        catalog: Optional[ToolCatalog] = None,
    ):
        self._managed_path = Path(managed_dir or get_default_managed_dir()).resolve()
        self._catalog = catalog or ToolCatalog()
        self._acquirer = ToolAcquirer(base_managed_dir=self._managed_path)
        self._executor = ToolExecutor(workspace_root=Path(workspace_dir).resolve() if workspace_dir else None)
        self._lock = threading.RLock()
        self._installed_cache: Dict[str, Dict[str, Any]] = {}  # tool_id -> acquisition dict

    @property
    def managed_dir(self) -> Path:
        return self._managed_path

    @property
    def catalog_service(self) -> ToolCatalog:
        return self._catalog

    def catalog(self, query: Optional[Union[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """List and search available tool manifests."""
        return self._catalog.catalog(query)

    def resolve(self, requirements: Union[List[Dict[str, Any]], Dict[str, Any], str]) -> Dict[str, Any]:
        """Resolve capability requirements to a compatible tool manifest."""
        return self._catalog.resolve(requirements)

    def acquire(
        self,
        selection: Union[Dict[str, Any], ToolManifest, str],
        policy: Optional[Union[AcquisitionPolicy, Dict[str, Any]]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """
        Acquire a tool into the managed directory according to security policy.
        Never executes README or install scripts. Verifies cryptographic digest.
        """
        if isinstance(selection, ToolManifest):
            manifest = selection
        elif isinstance(selection, str):
            manifest = self._catalog.get(selection)
            if not manifest:
                raise ResolutionError(f"Tool ID '{selection}' not found in catalog")
        elif isinstance(selection, dict):
            if "tool_id" in selection and "executable_subpath" in selection:
                manifest = ToolManifest.from_dict(selection)
            elif "tool_id" in selection:
                manifest = self._catalog.get(selection["tool_id"])
                if not manifest:
                    raise ResolutionError(f"Tool ID '{selection['tool_id']}' not found in catalog")
            else:
                raise ValueError("Invalid selection dictionary for tool acquisition")
        else:
            raise TypeError("Selection must be ToolManifest, tool_id string, or dict")

        acq_policy: AcquisitionPolicy
        if isinstance(policy, AcquisitionPolicy):
            acq_policy = policy
        elif isinstance(policy, dict):
            acq_policy = AcquisitionPolicy(**policy)
        else:
            acq_policy = AcquisitionPolicy(managed_dir=str(self._managed_path))

        result = self._acquirer.acquire(manifest, acq_policy, cancel_event)
        with self._lock:
            self._installed_cache[manifest.tool_id] = result
        return result

    def execute(
        self,
        request: Union[ToolRequest, Dict[str, Any]],
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolReceipt:
        """
        Execute an operation using an acquired managed tool in an isolated workspace.
        Enforces secrets stripping, output limits, monotonic timeouts, and process tracking.
        """
        req: ToolRequest
        if isinstance(request, ToolRequest):
            req = request
        elif isinstance(request, dict):
            req = ToolRequest.from_dict(request)
        else:
            raise TypeError("Request must be ToolRequest instance or dict")

        manifest = self._catalog.get(req.tool_id)
        if not manifest:
            raise ResolutionError(f"Tool '{req.tool_id}' is not registered in catalog")

        with self._lock:
            installed = self._installed_cache.get(req.tool_id)

        # If not in cache, verify if already present on disk
        if not installed:
            installed_path = self._managed_path / req.tool_id / manifest.pinned_revision
            cached = self._acquirer._verify_existing_installation(installed_path, manifest)
            if cached:
                installed = cached
                with self._lock:
                    self._installed_cache[req.tool_id] = installed

        if not installed:
            raise AcquisitionError(
                f"Tool '{req.tool_id}' is not acquired in managed directory. Call acquire() first."
            )

        exe_path = installed["executable_path"]
        receipt = self._executor.execute(manifest, exe_path, req, cancel_event)
        return receipt

    def stop(self, investigation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Stop active workbench tool processes. Confirmed only upon observed exit.
        """
        result = self._executor.stop_all(investigation_id)
        return {
            "status": result["status"],  # "confirmed" | "pending"
            "investigation_id": investigation_id,
            "stopped_count": result["stopped_count"],
            "all_exited": result["all_exited"],
            "timestamp": time.time(),
        }

    def close(self) -> Dict[str, Any]:
        """
        Cleanly terminate all active workbench tool executions and release resources.
        """
        stop_result = self.stop()
        return {
            "status": stop_result["status"],
            "stopped_count": stop_result["stopped_count"],
            "all_exited": stop_result["all_exited"],
            "timestamp": time.time(),
        }
