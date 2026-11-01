"""Notion Custom Agent local tool transport adapter.

Binds validated Notion tool requests to Codex's local execution router,
enforces replay/idempotency protection, deadline timeouts, cancellation checks,
session isolation, and payload size bounds.

Safety invariants:
- Never executes system/shell commands, Win32 calls, or disk modifications directly.
- Dispatches strictly to an injected local router (e.g. DesktopBroker / Checkpoint).
- Never parses arbitrary plain text or code blocks as executable tool commands.
- Model-supplied scope_ref is treated as untrusted metadata, verified only locally.
- Replayed requests with session/task mismatches are fail-closed rejected.
- Large binary/screenshot payloads are bounded to max_payload_bytes (5MB default).
- Never logs credentials, tokens, or raw binary payloads.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import threading
import time
from typing import Any, Callable
import uuid


SCHEMA_VERSION = 1
DEFAULT_MAX_PAYLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_MAX_HISTORY = 1000


class NotionTransportError(Exception):
    """Base exception for Notion tool transport errors."""
    pass


class ValidationError(NotionTransportError):
    """Raised when an incoming tool request fails structural validation."""
    pass


class SessionMismatchError(NotionTransportError):
    """Raised when a replayed request ID is paired with an inconsistent session or task."""
    pass


class ReplayError(NotionTransportError):
    """Raised when an in-flight or non-idempotent request is replayed illegally."""
    pass


class PayloadLimitError(NotionTransportError):
    """Raised when tool output exceeds allowed payload size limits."""
    pass


def _validate_uuid(val: Any, field_name: str) -> str:
    if not isinstance(val, str) or not val.strip():
        raise ValidationError(f"'{field_name}' must be a non-empty UUID string.")
    try:
        return str(uuid.UUID(val.strip()))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(f"'{field_name}' is not a valid UUID: {val!r}") from None


@dataclass(frozen=True)
class NotionToolRequest:
    """Validated structured request matching PLAN.md local contract."""
    schema_version: int
    task_id: str
    session_id: str
    request_id: str
    tool_name: str
    arguments: dict[str, Any]
    project_id: str
    scope_ref: str
    deadline: float

    @classmethod
    def from_dict(cls, data: Any) -> NotionToolRequest:
        if not isinstance(data, dict):
            raise ValidationError("Tool request must be a structured JSON dictionary.")

        schema_version = data.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ValidationError(f"Unsupported schema_version: {schema_version!r} (expected {SCHEMA_VERSION}).")

        task_id = _validate_uuid(data.get("task_id"), "task_id")
        session_id = _validate_uuid(data.get("session_id"), "session_id")

        raw_req_id = data.get("request_id")
        if not isinstance(raw_req_id, str) or not raw_req_id.strip():
            raise ValidationError("'request_id' must be a non-empty string.")
        request_id = raw_req_id.strip()

        raw_tool_name = data.get("tool_name")
        if not isinstance(raw_tool_name, str) or not raw_tool_name.strip():
            raise ValidationError("'tool_name' must be a non-empty string.")
        tool_name = raw_tool_name.strip()

        args = data.get("arguments")
        if not isinstance(args, dict):
            raise ValidationError(f"'arguments' for tool '{tool_name}' must be a dictionary, got {type(args).__name__}.")

        raw_project_id = data.get("project_id", "")
        if not isinstance(raw_project_id, str):
            raise ValidationError("'project_id' must be a string.")
        project_id = raw_project_id.strip()

        raw_scope_ref = data.get("scope_ref", "")
        if not isinstance(raw_scope_ref, str):
            raise ValidationError("'scope_ref' must be a string.")
        scope_ref = raw_scope_ref.strip()

        raw_deadline = data.get("deadline")
        if not isinstance(raw_deadline, (int, float)) or raw_deadline <= 0:
            raise ValidationError(f"'deadline' must be a positive float, got {raw_deadline!r}.")
        deadline = float(raw_deadline)

        return cls(
            schema_version=schema_version,
            task_id=task_id,
            session_id=session_id,
            request_id=request_id,
            tool_name=tool_name,
            arguments=dict(args),
            project_id=project_id,
            scope_ref=scope_ref,
            deadline=deadline,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NotionToolResult:
    """Structured result returned to caller and formatted for Notion session turn."""
    schema_version: int
    task_id: str
    session_id: str
    request_id: str
    status: str  # "completed", "failed", "rejected", "cancelled", "timeout"
    output: Any
    error: str
    duration_ms: float
    verification: str  # "none", "observed", "verified"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NotionToolTransport:
    """Dependency-injected transport adapter for Notion Custom Agent local tools."""

    def __init__(
        self,
        local_router: Callable[[NotionToolRequest], NotionToolResult] | None = None,
        *,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        max_history: int = DEFAULT_MAX_HISTORY,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._router = local_router
        self._max_payload_bytes = max_payload_bytes
        self._max_history = max_history
        self._clock = clock
        self._lock = threading.RLock()
        self._history: dict[str, NotionToolResult] = {}
        self._in_progress: dict[str, NotionToolRequest] = {}
        self._cancelled_requests: set[str] = set()
        self._cancelled_sessions: set[str] = set()

    def register_router(self, router: Callable[[NotionToolRequest], NotionToolResult]) -> None:
        """Inject the local execution router (provided by Codex/DesktopBroker)."""
        if not callable(router):
            raise TypeError("Local router must be a callable.")
        with self._lock:
            self._router = router

    def cancel_request(self, request_id: str) -> bool:
        """Flag an individual tool request as cancelled."""
        with self._lock:
            if not isinstance(request_id, str) or not request_id.strip():
                return False
            req_id = request_id.strip()
            self._cancelled_requests.add(req_id)
            return True

    def cancel_session(self, session_id: str) -> int:
        """Cancel all in-flight or subsequent requests bound to this session_id."""
        with self._lock:
            try:
                clean_id = _validate_uuid(session_id, "session_id")
            except ValidationError:
                return 0
            self._cancelled_sessions.add(clean_id)
            # Count in-flight requests for this session
            affected = sum(1 for req in self._in_progress.values() if req.session_id == clean_id)
            return affected

    def is_cancelled(self, request_id: str, session_id: str | None = None) -> bool:
        """Check if request or session has been marked cancelled."""
        with self._lock:
            if request_id in self._cancelled_requests:
                return True
            if session_id and session_id in self._cancelled_sessions:
                return True
            return False

    def get_result(self, request_id: str) -> NotionToolResult | None:
        """Retrieve completed cached result by request_id."""
        with self._lock:
            return self._history.get(request_id)

    def dispatch(self, raw_request: dict[str, Any] | NotionToolRequest) -> NotionToolResult:
        """Validate, check replay/cancellation/deadline, and dispatch to local router."""
        t_start = self._clock()

        # 1. Parse & validate request
        if isinstance(raw_request, NotionToolRequest):
            request = raw_request
        else:
            try:
                request = NotionToolRequest.from_dict(raw_request)
            except ValidationError as exc:
                t_end = self._clock()
                return NotionToolResult(
                    schema_version=SCHEMA_VERSION,
                    task_id=str(raw_request.get("task_id", "")) if isinstance(raw_request, dict) else "",
                    session_id=str(raw_request.get("session_id", "")) if isinstance(raw_request, dict) else "",
                    request_id=str(raw_request.get("request_id", "")) if isinstance(raw_request, dict) else "",
                    status="rejected",
                    output=None,
                    error=f"Validation failed: {exc}",
                    duration_ms=round((t_end - t_start) * 1000.0, 2),
                    verification="none",
                )

        req_id = request.request_id

        # 2. Check Replay, Idempotency & Session Consistency
        with self._lock:
            if req_id in self._in_progress:
                existing_req = self._in_progress[req_id]
                if existing_req.session_id != request.session_id or existing_req.task_id != request.task_id:
                    raise SessionMismatchError(
                        f"Request '{req_id}' replayed with mismatched session/task. Expected session {existing_req.session_id}."
                    )
                raise ReplayError(f"Request '{req_id}' is already executing in-flight.")

            if req_id in self._history:
                prior = self._history[req_id]
                if prior.session_id != request.session_id or prior.task_id != request.task_id:
                    raise SessionMismatchError(
                        f"Request '{req_id}' replayed with mismatched session/task binding."
                    )
                # Idempotent return of completed result
                return prior

            # Register as in-progress
            self._in_progress[req_id] = request

        try:
            # 3. Check Cancellation
            if self.is_cancelled(req_id, request.session_id):
                t_end = self._clock()
                res = NotionToolResult(
                    schema_version=SCHEMA_VERSION,
                    task_id=request.task_id,
                    session_id=request.session_id,
                    request_id=req_id,
                    status="cancelled",
                    output=None,
                    error="Operation cancelled by user or session stop.",
                    duration_ms=round((t_end - t_start) * 1000.0, 2),
                    verification="none",
                )
                self._record_history(req_id, res)
                return res

            # 4. Check Deadline before invocation
            now = self._clock()
            if now >= request.deadline:
                t_end = self._clock()
                res = NotionToolResult(
                    schema_version=SCHEMA_VERSION,
                    task_id=request.task_id,
                    session_id=request.session_id,
                    request_id=req_id,
                    status="timeout",
                    output=None,
                    error=f"Request deadline expired before execution ({now:.2f} >= {request.deadline:.2f}).",
                    duration_ms=round((t_end - t_start) * 1000.0, 2),
                    verification="none",
                )
                self._record_history(req_id, res)
                return res

            # 5. Check Router Registered
            with self._lock:
                router = self._router

            if router is None:
                t_end = self._clock()
                res = NotionToolResult(
                    schema_version=SCHEMA_VERSION,
                    task_id=request.task_id,
                    session_id=request.session_id,
                    request_id=req_id,
                    status="rejected",
                    output=None,
                    error="No local router registered to execute tool requests.",
                    duration_ms=round((t_end - t_start) * 1000.0, 2),
                    verification="none",
                )
                self._record_history(req_id, res)
                return res

            # 6. Execute via Local Router
            try:
                raw_result = router(request)
            except NotionTransportError:
                raise
            except Exception as exc:
                t_end = self._clock()
                res = NotionToolResult(
                    schema_version=SCHEMA_VERSION,
                    task_id=request.task_id,
                    session_id=request.session_id,
                    request_id=req_id,
                    status="failed",
                    output=None,
                    error=f"Local execution error: {exc}",
                    duration_ms=round((t_end - t_start) * 1000.0, 2),
                    verification="none",
                )
                self._record_history(req_id, res)
                return res

            # 7. Post-Execution Cancellation Check
            if self.is_cancelled(req_id, request.session_id):
                t_end = self._clock()
                res = NotionToolResult(
                    schema_version=SCHEMA_VERSION,
                    task_id=request.task_id,
                    session_id=request.session_id,
                    request_id=req_id,
                    status="cancelled",
                    output=None,
                    error="Operation cancelled while awaiting execution.",
                    duration_ms=round((t_end - t_start) * 1000.0, 2),
                    verification="none",
                )
                self._record_history(req_id, res)
                return res

            # 8. Normalize & Validate Result Object
            t_end = self._clock()
            total_duration_ms = round((t_end - t_start) * 1000.0, 2)

            if isinstance(raw_result, NotionToolResult):
                output_val = raw_result.output
                status_val = raw_result.status
                error_val = raw_result.error
                verification_val = raw_result.verification
            elif isinstance(raw_result, dict):
                output_val = raw_result.get("output")
                status_val = str(raw_result.get("status", "completed"))
                error_val = str(raw_result.get("error", ""))
                verification_val = str(raw_result.get("verification", "none"))
            else:
                output_val = raw_result
                status_val = "completed"
                error_val = ""
                verification_val = "none"

            # 9. Enforce Payload Size Limit
            output_val, payload_error = self._bound_payload(output_val)
            if payload_error:
                status_val = "failed"
                error_val = payload_error

            res = NotionToolResult(
                schema_version=SCHEMA_VERSION,
                task_id=request.task_id,
                session_id=request.session_id,
                request_id=req_id,
                status=status_val,
                output=output_val,
                error=error_val,
                duration_ms=total_duration_ms,
                verification=verification_val,
            )
            self._record_history(req_id, res)
            return res

        finally:
            with self._lock:
                self._in_progress.pop(req_id, None)

    def _bound_payload(self, output: Any) -> tuple[Any, str]:
        """Verify output payload does not exceed max_payload_bytes."""
        if output is None:
            return None, ""
        try:
            if isinstance(output, (bytes, bytearray)):
                byte_len = len(output)
                if byte_len > self._max_payload_bytes:
                    return None, f"PayloadLimitError: Binary payload size ({byte_len} bytes) exceeds limit ({self._max_payload_bytes} bytes)."
                return output, ""

            # Check JSON-serialized representation size
            serialized = json.dumps(output, ensure_ascii=False)
            encoded_len = len(serialized.encode("utf-8"))
            if encoded_len > self._max_payload_bytes:
                return None, f"PayloadLimitError: Tool output size ({encoded_len} bytes) exceeds limit ({self._max_payload_bytes} bytes)."
            return output, ""
        except (TypeError, ValueError) as exc:
            return None, f"Payload serialization error: {exc}"

    def _record_history(self, request_id: str, result: NotionToolResult) -> None:
        with self._lock:
            if len(self._history) >= self._max_history:
                # Evict oldest entry (FIFO)
                oldest_key = next(iter(self._history))
                self._history.pop(oldest_key, None)
            self._history[request_id] = result


def format_continuation_message(result: NotionToolResult) -> dict[str, Any]:
    """Format a verified NotionToolResult into a continuation payload for POST /v1/sessions."""
    clean_dict = result.to_dict()
    # Strip any potential binary buffers for safe JSON transmission
    if isinstance(clean_dict.get("output"), (bytes, bytearray)):
        clean_dict["output"] = f"<binary data: {len(clean_dict['output'])} bytes>"

    clean_output = clean_dict.get("output")
    formatted_content = (
        f"[Quartz Local Tool Result]\n"
        f"status: {result.status}\n"
        f"tool_request_id: {result.request_id}\n"
        f"verification: {result.verification}\n"
        f"duration_ms: {result.duration_ms}\n"
    )
    if result.error:
        formatted_content += f"error: {result.error}\n"
    if clean_output is not None:
        try:
            if isinstance(clean_output, str):
                formatted_content += f"output: {clean_output}\n"
            else:
                formatted_content += f"output: {json.dumps(clean_output, ensure_ascii=False, indent=2)}\n"
        except Exception:
            formatted_content += f"output: {str(clean_output)[:1000]}\n"

    return {
        "session_id": result.session_id,
        "message": formatted_content.strip(),
        "metadata": {
            "schema_version": result.schema_version,
            "task_id": result.task_id,
            "request_id": result.request_id,
            "verification": result.verification,
        },
    }
