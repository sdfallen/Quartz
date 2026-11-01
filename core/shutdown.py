"""
core/shutdown.py
Cooperative shutdown coordinator and structured shutdown receipt for Quartz.
Enforces admission closing, component-isolated cleanups, and verifiable receipts.
"""

from dataclasses import dataclass, field
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("quartz.shutdown")


@dataclass
class ShutdownReceipt:
    status: str  # "confirmed" | "pending" | "failed"
    components: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "components": dict(self.components),
            "errors": list(self.errors),
            "timestamp": self.timestamp,
        }


class ShutdownCoordinator:
    """
    Coordinates orderly cooperative shutdown across Quartz backend components.
    Guarantees:
      1. Dispatch admission closing before component teardown.
      2. No new singletons or services instantiated during/after shutdown.
      3. Component cleanup isolation (one failure does not abort others).
      4. Idempotent execution and cached receipt.
      5. Bounded timeouts to prevent indefinite UI or entry freeze.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._admission_closed = False
        self._shutdown_started = False
        self._shutdown_completed = False
        self._receipt: Optional[ShutdownReceipt] = None

    def is_admission_closed(self) -> bool:
        with self._lock:
            return self._admission_closed

    def close_admission(self) -> None:
        with self._lock:
            if not self._admission_closed:
                log.info("Shutdown admission closed: rejecting new dispatches and instantiations")
                self._admission_closed = True

    def get_receipt(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._receipt.to_dict() if self._receipt else None

    def execute_shutdown(
        self,
        components: Dict[str, Callable[[], Any]],
        timeout_per_component: float = 3.0,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._shutdown_completed and self._receipt:
                return self._receipt.to_dict()
            if self._shutdown_started:
                if self._receipt:
                    return self._receipt.to_dict()

            self._shutdown_started = True
            self._admission_closed = True

        component_results: Dict[str, Dict[str, Any]] = {}
        errors: List[str] = []
        has_pending = False
        has_failed = False

        for name, cleanup_func in components.items():
            if cleanup_func is None:
                component_results[name] = {"status": "skipped", "detail": "not_registered"}
                continue

            result_holder = {}
            error_holder = []

            def _worker():
                try:
                    res = cleanup_func()
                    result_holder["result"] = res
                except Exception as exc:
                    error_holder.append(exc)

            worker_thread = threading.Thread(
                target=_worker,
                name=f"quartz-stop-{name}",
                daemon=True,
            )
            worker_thread.start()
            worker_thread.join(timeout=timeout_per_component)

            if worker_thread.is_alive():
                has_pending = True
                msg = f"TimeoutExpired: {name} cleanup exceeded {timeout_per_component}s"
                component_results[name] = {"status": "pending", "error": msg}
                errors.append(msg)
                log.warning("Shutdown pending for component %s: exceeded timeout", name)
            elif error_holder:
                has_failed = True
                exc = error_holder[0]
                msg = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}".strip()
                component_results[name] = {"status": "failed", "error": msg}
                errors.append(msg)
                log.error("Shutdown failure in component %s: %s", name, msg)
            else:
                res = result_holder.get("result")
                if res is False:
                    component_results[name] = {"status": "skipped", "detail": "not_instantiated"}
                else:
                    component_results[name] = {"status": "confirmed"}
                log.debug("Shutdown confirmed for component %s", name)

        if has_pending:
            overall_status = "pending"
        elif has_failed:
            overall_status = "failed"
        else:
            overall_status = "confirmed"

        receipt = ShutdownReceipt(
            status=overall_status,
            components=component_results,
            errors=errors,
            timestamp=time.time(),
        )

        with self._lock:
            self._receipt = receipt
            self._shutdown_completed = True

        return receipt.to_dict()

    def reset(self) -> None:
        """Reset coordinator state. Intended for unit testing."""
        with self._lock:
            self._admission_closed = False
            self._shutdown_started = False
            self._shutdown_completed = False
            self._receipt = None


_global_coordinator: Optional[ShutdownCoordinator] = None
_coordinator_lock = threading.Lock()


def get_shutdown_coordinator() -> ShutdownCoordinator:
    global _global_coordinator
    if _global_coordinator is None:
        with _coordinator_lock:
            if _global_coordinator is None:
                _global_coordinator = ShutdownCoordinator()
    return _global_coordinator


def reset_shutdown_coordinator() -> None:
    global _global_coordinator
    with _coordinator_lock:
        if _global_coordinator is not None:
            _global_coordinator.reset()
        _global_coordinator = None
