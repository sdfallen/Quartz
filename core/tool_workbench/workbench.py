"""Registered tools only, with owned acquisition/execution and JSON receipts.

This is supervision, not an OS security sandbox. Catalog registration is a
trusted host operation; a repository README or tool output cannot register code.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import threading
import time
import uuid

from .acquisition import ToolAcquirer, get_default_managed_dir
from .catalog import ToolCatalog
from .contracts import AcquisitionPolicy, ToolManifest, ToolRequest
from .errors import AcquisitionError, ExecutionError, ResolutionError
from .execution import ToolExecutor


class _Cancellation:
    def __init__(self, *events): self.events = [e for e in events if e is not None]
    def is_set(self): return any(e.is_set() for e in self.events)
    def wait(self, timeout=None):
        until = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            if until is not None and time.monotonic() >= until: return False
            time.sleep(.02)
        return True


class ToolWorkbench:
    def __init__(self, managed_dir=None, workspace_dir=None, catalog=None):
        self._managed_path = Path(managed_dir or get_default_managed_dir()).resolve()
        self._catalog = catalog if catalog is not None else ToolCatalog()
        self._acquirer = ToolAcquirer(base_managed_dir=self._managed_path)
        self._executor = ToolExecutor(workspace_root=Path(workspace_dir) if workspace_dir else None)
        self._lock = threading.RLock()
        self._closed = False
        self._operations = {}

    @property
    def managed_dir(self): return self._managed_path
    @property
    def catalog_service(self): return self._catalog
    def catalog(self, query=None): return self._catalog.catalog(query)
    def resolve(self, requirements): return self._catalog.resolve(requirements)

    def _begin(self, investigation_id, external):
        with self._lock:
            if self._closed: raise ExecutionError("Workbench is closed")
            token, event = uuid.uuid4().hex, threading.Event()
            self._operations[token] = (investigation_id, event)
            return token, _Cancellation(event, external)

    def _end(self, token):
        with self._lock: self._operations.pop(token, None)

    def _manifest(self, selection):
        if isinstance(selection, ToolManifest): supplied, identity = selection, selection.tool_id
        elif isinstance(selection, str): supplied, identity = None, selection
        elif isinstance(selection, dict):
            identity = selection.get('tool_id')
            supplied = ToolManifest.from_dict(selection) if 'executable_subpath' in selection else None
        else: raise ResolutionError("Invalid tool selection")
        registered = self._catalog.get(identity)
        if registered is None: raise ResolutionError("Tool is not registered")
        if supplied is not None and supplied.to_dict() != registered.to_dict():
            raise ResolutionError("Selection does not match registered manifest")
        # Detach nested mutable fields from concurrent catalog callers.
        return ToolManifest.from_dict(deepcopy(registered.to_dict()))

    def acquire(self, selection, policy=None, cancel_event=None):
        manifest = self._manifest(selection)
        if isinstance(policy, dict): policy = AcquisitionPolicy(**policy)
        policy = policy or AcquisitionPolicy(managed_dir=str(self._managed_path))
        token, event = self._begin(None, cancel_event)
        try:
            if event.is_set(): raise AcquisitionError("Acquisition cancelled")
            result = self._acquirer.acquire(manifest, policy, event)
            with self._lock:
                if self._closed or event.is_set(): raise AcquisitionError("Acquisition cancelled before publication")
            return result
        finally: self._end(token)

    def execute(self, request, cancel_event=None):
        """JSON in/out for gateways; retain typed receipts for Python callers."""
        json_request = isinstance(request, dict)
        req = ToolRequest.from_dict(request) if json_request else request
        if not isinstance(req, ToolRequest): raise TypeError("Invalid tool request")
        manifest = self._manifest(req.tool_id)
        token, event = self._begin(req.investigation_id, cancel_event)
        try:
            if event.is_set(): raise ExecutionError("Execution cancelled")
            # Rehash the installed files on EVERY execution. Cached metadata or
            # a matching ID alone cannot attest to current executable bytes.
            installed = self._acquirer.validate_installation(manifest,
                self._managed_path / manifest.tool_id / manifest.pinned_revision,
                cancel_event=event)
            receipt = self._executor.execute(manifest, installed['executable_path'], req, event)
            if not json_request: return receipt
            value = receipt.to_dict()
            value['status'] = {'confirmed':'completed', 'failed':'failed',
                'cancelled':'cancelled', 'timeout':'blocked', 'output_limit':'blocked'}.get(receipt.status, 'blocked')
            return value
        finally: self._end(token)

    def _stop(self, investigation_id=None, *, closing=False):
        with self._lock:
            if closing: self._closed = True
            for owner, event in self._operations.values():
                if owner is None or investigation_id is None or owner == investigation_id: event.set()
        executor = self._executor.close() if closing else self._executor.stop_all(investigation_id)
        acquirer = self._acquirer.close() if closing else self._acquirer.stop()
        with self._lock:
            pending = sum(1 for owner, _ in self._operations.values()
                if owner is None or investigation_id is None or owner == investigation_id)
        confirmed = not pending and executor.get('status') == 'confirmed' and acquirer.get('status') == 'confirmed'
        return {'status':'confirmed' if confirmed else 'pending',
            'all_exited':confirmed, 'stopped_count':executor.get('stopped_count',0),
            'pending_operations':pending, 'investigation_id':investigation_id,
            'components':{'executor':executor, 'acquirer':acquirer}, 'timestamp':time.time()}

    def stop(self, investigation_id=None): return self._stop(investigation_id)
    def close(self): return self._stop(closing=True)
