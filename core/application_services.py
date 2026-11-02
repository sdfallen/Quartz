"""Ownership of the application services that live in the GUI process.

``gui.Api`` is the pywebview bridge and native picker/consent adapter. The
components it used to construct and own directly (desktop operator, natural
desktop task, chat coordination, artifact diagnostics, package repair,
onboarding and voice) are created, reused and shut down here instead.

Rules (docs/architecture/FINALIZATION_TEAM_20261102.md, shared contract):

* Construction is lazy and single-instance per slot, through injected
  factories. The defaults import their module only when first needed.
* After ``shutdown()`` starts, no component is constructed or adopted again
  (``ServicesClosed``). Existing instances stay readable for late status calls.
* Every owned component is closed independently: one failure never skips the
  others. Each close is verified against the component's own state; an
  unverifiable result is ``pending``, never ``confirmed``.
* ``shutdown()`` is idempotent: a confirmed component is not closed twice;
  only failed/pending ones are retried.
* This module does not import the GUI, ``webview`` or the IPC client. Backend
  shutdown stays in ``gui.Api.cleanup_before_exit`` (authenticated IPC).

Security-specific wiring stays explicit, not generic: the desktop operator
gets the writer-recovery admission guard before it is ever returned, and the
artifact diagnostics service is only built from a path the native picker gave.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from contextlib import contextmanager

CONFIRMED = "confirmed"
PENDING = "pending"
FAILED = "failed"
NOT_STARTED = "not_started"

# Close order matches the previous Api.cleanup_before_exit order. Tasks that
# use the desktop operator are stopped before the operator itself is closed.
CLOSE_ORDER = ("artifact_diagnostics", "natural", "coordination", "desktop",
               "voice", "repair", "onboarding")


class ServicesClosed(RuntimeError):
    def __init__(self):
        super().__init__("Quartz kapanıyor; yeni görev veya servis başlatılmadı.")


def _onboarding():
    from core.onboarding import OnboardingService
    return OnboardingService()


def _desktop():
    from core.desktop_agents import DesktopAgentService
    return DesktopAgentService()


def _coordination(desktop, emit):
    from core.chat_coordination import ChatCoordination
    return ChatCoordination(desktop, emit)


def _natural(desktop, emit):
    from core.natural_desktop import NaturalDesktopTask
    return NaturalDesktopTask(desktop, emit)


def _artifact_diagnostics(path, *, question=None):
    from core.artifact_diagnostics import ArtifactDiagnosticsService
    return ArtifactDiagnosticsService(path, question=question)


def _repair():
    from core.cli_installer import app_root
    from core.package_repair import PackageRepair
    backups = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Quartz/repair-backups"
    return PackageRepair(app_root(), backups)


def _voice():
    from voice_system import VoiceSystem
    return VoiceSystem()


@dataclass(frozen=True)
class ServiceFactories:
    onboarding: Callable = _onboarding
    desktop: Callable = _desktop
    coordination: Callable = _coordination
    natural: Callable = _natural
    artifact_diagnostics: Callable = _artifact_diagnostics
    repair: Callable = _repair
    voice: Callable = _voice


# ── Per-component close + verification ─────────────────────────────────────
# Each returns CONFIRMED only when the component's own state says it stopped.

def _close_artifact_diagnostics(service, _owner):
    service.shutdown()
    threads = list(getattr(service, "threads", {}).values())
    return PENDING if any(t.is_alive() for t in threads) else CONFIRMED


def _close_natural(task, _owner):
    task.stop()
    state = task.status()
    if state.get("active"):
        return PENDING
    thread = getattr(task, 'thread', None)
    if thread is not None and thread.is_alive(): return PENDING
    for runtime, rid in getattr(task, 'runs', {}).values():
        record = runtime.get(rid)
        if record.get('process_exit_confirmed') is not True:
            runtime.cancel(rid)
            return PENDING
    cleanup = (state.get("job") or {}).get("cleanup") or {}
    if cleanup.get("status") == "failed":
        return FAILED
    if state.get('job') and cleanup.get('status') != 'completed': return PENDING
    return CONFIRMED


def _close_coordination(service, _owner):
    service.stop()
    state = service.status()
    thread = getattr(service, 'thread', None)
    if state.get('active') or (thread is not None and thread.is_alive()): return PENDING
    runtime, rid = getattr(service, 'observer_runtime', None), getattr(service, 'observer_run', None)
    if runtime is not None and rid and runtime.get(rid).get('process_exit_confirmed') is not True:
        runtime.cancel(rid)
        return PENDING
    if (state.get('job') or {}).get('cleanup', {}).get('status') == 'failed': return FAILED
    return CONFIRMED


def _close_desktop(service, _owner):
    service.close()
    session = (service.status() or {}).get("session") or {}
    runtime, rid = getattr(service, '_runtime', None), getattr(service, '_run_id', None)
    if runtime is not None and rid and runtime.get(rid).get('process_exit_confirmed') is not True:
        return PENDING
    return PENDING if session.get("active") else CONFIRMED


def _close_voice(voice, _owner):
    voice.stop_wake_loop()
    voice.stop_speaking()
    return PENDING if getattr(voice, "wake_active", False) else CONFIRMED


def _close_repair(_plan, owner):
    # A repair apply runs under the diagnostics lock; do not drop a plan that
    # is being applied, and do not report it as stopped.
    if not owner.diagnostics_lock.acquire(timeout=2.0):
        return PENDING
    try:
        owner._release("repair")
        return CONFIRMED
    finally:
        owner.diagnostics_lock.release()


def _close_onboarding(service, _owner):
    # The GUI does not kill a user's login window or an install in progress;
    # it reports that work as still pending instead of claiming it stopped.
    with service.lock:
        running = service.job.get("state") == "running"
        logins = list(service.login_processes.values())
    if running or any(p.poll() is None for p in logins):
        return PENDING
    return CONFIRMED


_CLOSERS = {
    "artifact_diagnostics": _close_artifact_diagnostics,
    "natural": _close_natural,
    "coordination": _close_coordination,
    "desktop": _close_desktop,
    "voice": _close_voice,
    "repair": _close_repair,
    "onboarding": _close_onboarding,
}


def overall_status(components: dict) -> str:
    values = set(components.values())
    if FAILED in values:
        return FAILED
    if PENDING in values:
        return PENDING
    return CONFIRMED


class ApplicationServices:
    """Lazy owner of the GUI-process components. Not a task engine."""

    def __init__(self, factories: ServiceFactories | None = None):
        self.factories = factories or ServiceFactories()
        self._lock = threading.RLock()
        self._shutdown_lock = threading.Lock()
        # Held by the bridge around picker-driven diagnostics/repair steps.
        self.diagnostics_lock = threading.RLock()
        self._instances = dict.fromkeys(CLOSE_ORDER)
        self._closing = False
        self._components: dict[str, str] = {}
        self._activities = 0

    @contextmanager
    def activity(self):
        with self._lock:
            self.ensure_open()
            self._activities += 1
        try:
            yield
        finally:
            with self._lock: self._activities -= 1

    # ── state ──
    @property
    def closing(self) -> bool:
        return self._closing

    def ensure_open(self):
        if self._closing:
            raise ServicesClosed()

    def peek(self, name):
        """Current instance or None. Never constructs."""
        return self._instances[name]

    def adopt(self, name, instance):
        """Install a ready instance (compatibility/test injection)."""
        with self._lock:
            if name not in self._instances:
                raise KeyError(name)
            if self._closing and instance is not None:
                raise ServicesClosed()
            self._instances[name] = instance

    def _release(self, name):
        with self._lock:
            self._instances[name] = None

    def _get(self, name, build):
        with self._lock:
            self.ensure_open()
            if self._instances[name] is None:
                self._instances[name] = build()
            return self._instances[name]

    # ── lazily shared components ──
    def onboarding(self):
        return self._get("onboarding", self.factories.onboarding)

    def desktop(self, admission_guard: Callable):
        def build():
            service = self.factories.desktop()
            # The writer-recovery guard is installed before anyone can use
            # the operator; a desktop service without it is never exposed.
            service.broker.admission_guard = admission_guard
            return service
        return self._get("desktop", build)

    def coordination(self, desktop: Callable, emit: Callable):
        return self._get("coordination", lambda: self.factories.coordination(desktop(), emit))

    def voice(self):
        return self._get("voice", self.factories.voice)

    # ── per-request components (a new user action replaces the old one) ──
    def start_natural(self, desktop, emit):
        with self._lock:
            self.ensure_open()
            previous = self._instances['natural']
            if previous is not None:
                state = previous.status()
                thread = getattr(previous, 'thread', None)
                cleanup = (state.get('job') or {}).get('cleanup', {})
                if state.get('active') or (thread is not None and thread.is_alive()) or (
                        state.get('job') and cleanup.get('status') != 'completed'):
                    raise RuntimeError('Önceki görevin kapanışı henüz tamamlanmadı.')
                for runtime, rid in getattr(previous, 'runs', {}).values():
                    if runtime.get(rid).get('process_exit_confirmed') is not True:
                        raise RuntimeError('Önceki ajan sürecinin çıkışı henüz doğrulanmadı.')
            task = self.factories.natural(desktop, emit)
            self._instances["natural"] = task
            return task

    def replace_artifact_diagnostics(self, selected_path, *, question=None):
        """Build diagnostics for a path the native picker returned."""
        with self._lock:
            self.ensure_open()
            previous = self._instances["artifact_diagnostics"]
            if previous is not None:
                previous.shutdown()
                if any(t.is_alive() for t in getattr(previous, 'threads', {}).values()):
                    raise RuntimeError('Önceki incelemenin kapanışı henüz tamamlanmadı.')
            service = (self.factories.artifact_diagnostics(selected_path, question=question)
                       if question is not None else self.factories.artifact_diagnostics(selected_path))
            self._instances["artifact_diagnostics"] = service
            return service

    def new_repair(self):
        with self._lock:
            self.ensure_open()
            plan = self.factories.repair()
            self._instances["repair"] = plan
            return plan

    def discard_repair(self):
        self._release("repair")

    # ── shutdown ──
    def shutdown(self) -> dict:
        """Fence new construction, then close every owned component.

        Returns ``{"status", "components", "errors"}``; errors carry only a
        component name, a code and an exception type (no message text).
        """
        with self._shutdown_lock:
            with self._lock:
                self._closing = True
                targets = [(name, self._instances[name]) for name in CLOSE_ORDER]
                activities = self._activities
            desktop = self.peek('desktop')
            if activities:
                # No new grants or inputs survive a pending startup action.
                if desktop is not None and callable(getattr(desktop.broker, 'stop', None)):
                    desktop.broker.stop()
                return {'status':PENDING, 'components':{'inflight_gui':PENDING}, 'errors':[]}
            errors = []
            for name, instance in targets:
                if self._components.get(name) == CONFIRMED:
                    continue  # never close a confirmed component twice
                if instance is None:
                    self._components[name] = NOT_STARTED
                    continue
                try:
                    self._components[name] = _CLOSERS[name](instance, self)
                except Exception as exc:
                    self._components[name] = FAILED
                    errors.append({"component": name, "code": "close_failed",
                                   "type": type(exc).__name__})
            components = dict(self._components)
            return {"status": overall_status(components), "components": components,
                    "errors": errors}
