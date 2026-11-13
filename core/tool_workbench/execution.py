"""
core/tool_workbench/execution.py
Isolated and tracked process execution for SpeS Tool Workbench.
Enforces argv schema validation, secrets filtering, output overflow bounding,
process tree tracking, cancellation, and artifact generation.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import re
import math
import stat
import tempfile
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from core.process_tree import stop_process_tree
from core.tool_workbench.contracts import Target, ToolManifest, ToolReceipt, ToolRequest
from core.tool_workbench.errors import (
    CancellationError,
    ExecutionError,
    OutputLimitExceededError,
    SchemaValidationError,
    TimeoutExpiredError,
)

log = logging.getLogger("quartz.workbench.execution")

_DISALLOWED_SHELL_CHARS = re.compile(r"[\r\n;&|<>`$]")


class ToolExecutor:
    """Manages isolated subprocess lifecycles with process-tree tracking and resource bounds."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self._workspace_root = self._plain_path(Path(workspace_root) if workspace_root else Path(tempfile.gettempdir()) / "quartz_workbench_runs")
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._active_processes: Dict[str, Dict[str, Any]] = {}
        self._closed = False
        self._stopping_all = False
        self._stopped_investigations = set()
        self._condition = threading.Condition(self._lock)

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def _sanitize_environment(self, workspace_dir: Path) -> Dict[str, str]:
        """Produce an isolated environment stripping all secrets, keys, and credentials."""
        # SYSTEMDRIVE is required: without it Windows expands %SystemDrive% in shell
        # cache paths relative to the cwd and writes cversions.2.db into the run folder.
        safe_keys = {"SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "WINDIR", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"}
        env: Dict[str, str] = {}

        for k, v in os.environ.items():
            k_upper = k.upper()
            if any(secret in k_upper for secret in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH", "COOKIE", "PRIVATE")):
                continue
            if k_upper in safe_keys:
                env[k] = v
        if os.name == "nt" and not any(k.upper() == "SYSTEMDRIVE" for k in env):
            root = next((v for k, v in env.items() if k.upper() in ("SYSTEMROOT", "WINDIR")), "")
            env["SYSTEMDRIVE"] = Path(root).drive or "C:"

        # Set isolated temporary and user profile directories
        tmp_dir = workspace_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = workspace_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        env["TEMP"] = str(tmp_dir)
        env["TMP"] = str(tmp_dir)
        env["USERPROFILE"] = str(workspace_dir)
        env["XDG_CACHE_HOME"] = str(cache_dir)
        env["PYTHONUNBUFFERED"] = "1"

        return env

    def _validate_options(self, manifest: ToolManifest, operation: str, options: Dict[str, Any]) -> None:
        """Validate options against operation schema and reject shell injection."""
        op_spec = manifest.supported_operations.get(operation)
        if not op_spec:
            raise SchemaValidationError(f"Operation '{operation}' not supported by tool '{manifest.tool_id}'")

        allowed_options = op_spec.get("options", {})
        if not isinstance(options, dict) or len(options) > 32:
            raise SchemaValidationError("Options must be a bounded dictionary")
        kinds = {"string": str, "boolean": bool, "integer": int, "number": (int, float)}
        for key, value in options.items():
            if not isinstance(key, str) or key not in allowed_options:
                raise SchemaValidationError(f"Unrecognized option '{key}' for operation '{operation}'")
            spec = allowed_options[key]
            kind = spec.get("type")
            expected = kinds.get(kind)
            if expected is None or (kind == "number" and (type(value) not in expected or not math.isfinite(value))) or (kind != "number" and type(value) is not expected):
                raise SchemaValidationError(f"Invalid type for option '{key}'")
            if kind == "string" and (len(value) > spec.get("maxLength", 8192) or "\x00" in value or _DISALLOWED_SHELL_CHARS.search(value)):
                raise SchemaValidationError(f"Disallowed shell character or length in option '{key}'")
            if "enum" in spec and value not in spec["enum"]:
                raise SchemaValidationError(f"Invalid enum value for option '{key}'")
            if kind in {"integer", "number"} and (value < spec.get("minimum", 0) or value > spec.get("maximum", 1000000)):
                raise SchemaValidationError(f"Option '{key}' is outside its allowed range")
        for key, spec in allowed_options.items():
            if spec.get("required") and key not in options:
                raise SchemaValidationError(f"Missing required option '{key}' for operation '{operation}'")

    def _build_argv(
        self, manifest: ToolManifest, executable_path: str, request: ToolRequest
    ) -> List[str]:
        """Assemble a safe argv list without shell expansion."""
        exe_path = Path(executable_path).resolve()
        if not exe_path.is_file():
            raise ExecutionError(f"Tool executable not found: {executable_path}")

        argv: List[str] = []
        suffix = exe_path.suffix.lower()

        if suffix == ".py":
            if getattr(sys, "frozen", False):
                raise ExecutionError("Python script execution requires a verified managed interpreter in packaged SpeS")
            argv.extend([sys.executable, str(exe_path)])
        elif suffix in {".js", ".mjs"}:
            from core.cli_installer import node_command
            argv = node_command(str(exe_path), [])
        else:
            argv.append(str(exe_path))

        op = request.operation
        options = request.options

        # Operation-specific argument building
        if manifest.tool_id == "ripgrep":
            if op == "version":
                argv.append("--version")
            elif op in {"search", "strings"}:
                argv.extend(["--no-config", "--color", "never"])
                if op == "strings":
                    argv.append("-a")

                if options.get("case_sensitive") is True:
                    argv.append("-s")
                elif options.get("case_sensitive") is False:
                    argv.append("-i")

                if options.get("fixed_strings"):
                    argv.append("-F")

                if options.get("json_output"):
                    argv.append("--json")

                max_count = options.get("max_count")
                if max_count is not None:
                    argv.extend(["-m", str(int(max_count))])

                pattern = options.get("pattern", "")
                if pattern:
                    argv.extend(["-e", str(pattern)])
                elif op == "strings":
                    argv.extend(["-e", "[ -~]{4,}"])

                if request.target:
                    target_path = request.target.canonical_path if isinstance(request.target, Target) else str(request.target)
                    argv.append(str(Path(target_path).resolve()))

        elif manifest.tool_id == "pe_inspector":
            argv.append(f"--{op}")
            if options.get("json_output", True):
                argv.append("--json")
            if request.target:
                target_path = request.target.canonical_path if isinstance(request.target, Target) else str(request.target)
                argv.append(str(Path(target_path).resolve()))

        elif manifest.tool_id == "rea_static":
            argv.append(op)
            if request.target:
                target_path = request.target.canonical_path if isinstance(request.target, Target) else str(request.target)
                argv.append(str(Path(target_path).resolve()))
            if options.get("detail"):
                argv.extend(["--detail", str(options["detail"])])
            if options.get("json_output", True):
                argv.append("--json")

        else:
            # Generic operation handling from manifest schema
            argv.append(op)
            for k, v in sorted(options.items()):
                if isinstance(v, bool):
                    if v:
                        argv.append(f"--{k}")
                else:
                    argv.extend([f"--{k}", str(v)])
            if request.target:
                target_path = request.target.canonical_path if isinstance(request.target, Target) else str(request.target)
                argv.append(str(Path(target_path).resolve()))

        return argv

    MAX_OUTPUT_BYTES = 8 * 1024 * 1024
    MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
    MAX_ARTIFACTS = 32
    MAX_WORKSPACE_ENTRIES = 2048
    CLEANUP_SECONDS = 4.0

    @staticmethod
    def _plain_path(path: Path) -> Path:
        """Reject links/junctions before resolving; resolve alone loses that evidence."""
        absolute = path.absolute()
        for component in (absolute, *absolute.parents):
            try:
                info = component.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ExecutionError("Workspace/artifact links and reparse points are prohibited")
        return absolute.resolve()

    def _workspace(self, request):
        base = self._plain_path(Path(request.workspace)) if request.workspace else self._workspace_root
        if base != self._workspace_root and self._workspace_root not in base.parents:
            raise ExecutionError("Workspace is outside the approved executor root")
        base.mkdir(parents=True, exist_ok=True)
        # A fresh directory prevents old results and concurrent runs being attributed to this request.
        run = base / ("run_" + uuid.uuid4().hex)
        run.mkdir()
        return base, run

    def _check_admission(self, request, cancel_event, deadline, record=None):
        with self._lock:
            if self._closed:
                raise ExecutionError("Tool executor is closed")
            stopped = self._stopping_all or request.investigation_id in self._stopped_investigations
        if stopped or (cancel_event and cancel_event.is_set()) or (record and record["stop"].is_set()):
            raise CancellationError("Tool execution cancelled before spawn")
        if time.monotonic() >= deadline:
            raise TimeoutExpiredError("Tool deadline expired before spawn")

    def _spawn(self, argv, workspace, environment, record):
        """Reserve first, assign a suspended Windows process to a job, then resume it."""
        import psutil  # Required identity/supervision dependency; fail before spawning if absent.
        with self._lock:
            if self._closed or record["stop"].is_set():
                raise CancellationError("Tool spawn reservation was cancelled")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        job = _WindowsJob() if os.name == "nt" else None
        if job:
            flags |= 0x00000004  # CREATE_SUSPENDED: no tool code runs before job ownership.
        try:
            process = subprocess.Popen(argv, cwd=str(workspace), env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                creationflags=flags, start_new_session=os.name != "nt")
            with self._lock:
                record["process"] = process
                record["job"] = job
            if job:
                job.assign(process)
            try:
                identity = psutil.Process(process.pid)
                record["identity"] = identity.create_time()
            except psutil.NoSuchProcess:
                if process.poll() is None:
                    raise
                record["identity"] = None
            if job:
                identity.resume()
            return process
        except BaseException:
            # Assignment/resume failures never leave an unowned suspended executable.
            process = record.get("process")
            if process is not None:
                try:
                    if job and job.assigned:
                        job.terminate()
                    else:
                        process.kill()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if job and job.empty():
                job.close()
            raise

    @staticmethod
    def _observe_children(record):
        """POSIX fallback retains identity-bearing children; Windows uses the job kernel object."""
        if record.get("job") or record["process"].poll() is not None:
            return
        import psutil
        try:
            parent = psutil.Process(record["process"].pid)
            if parent.create_time() != record["identity"]:
                record["observation_failed"] = True
                return
            for child in parent.children(recursive=True):
                record["children"][(child.pid, child.create_time())] = child
        except psutil.NoSuchProcess:
            pass
        except psutil.Error:
            record["observation_failed"] = True

    def _tree_empty(self, record):
        process = record["process"]
        if process is None:
            return True
        if process.poll() is None:
            return False
        job = record.get("job")
        if job:
            return job.empty()
        if getattr(process, '_quartz_tree_discovery_incomplete', False) is True:
            return False
        import psutil
        for child in record["children"].values():
            try:
                if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                    return False
            except psutil.NoSuchProcess:
                pass
            except psutil.Error:
                return False
        # A dedicated process group catches children missed between parent spawn and exit.
        if os.name != "nt":
            try:
                os.killpg(process.pid, 0)
                return False
            except ProcessLookupError:
                pass
            except OSError:
                return False
        return not record.get("observation_failed", False)

    def _terminate(self, record):
        process = record["process"]
        if process is None:
            return
        job = record.get("job")
        if job:
            job.terminate()
        else:
            if os.name != "nt":
                import signal
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process._quartz_pending_children = list(record["children"].values())
            stop_process_tree(process, timeout=.1)

    def _release_when_clean(self, request_id, record):
        if not self._tree_empty(record) or any(t.is_alive() for t in record["drains"]):
            return False
        job = record.get("job")
        if job:
            job.close()
        with self._condition:
            if self._active_processes.get(request_id) is record:
                self._active_processes.pop(request_id)
            if not self._active_processes:
                self._stopping_all = False
            self._condition.notify_all()
        return True

    def _watch_pending(self, request_id, record):
        # Keep ownership after an uncertain timeout instead of declaring cleanup or forgetting a child.
        while True:
            try:
                self._terminate(record)
                if self._release_when_clean(request_id, record):
                    return
            except Exception:
                log.exception("Owned tool cleanup is still pending")
            time.sleep(.2)

    def _artifacts(self, run, base, output, limitations):
        artifacts = []
        total = 0
        hash_deadline = time.monotonic() + 2.0
        # Output is evidence even for stdout-only tools. New exclusive files cannot overwrite tool results.
        for stream, content in output.items():
            candidate = run / ("quartz-" + stream + "-" + uuid.uuid4().hex + ".bin")
            with candidate.open("xb") as handle:
                handle.write(content)
        entries = 0
        for root, directories, files in os.walk(run, followlinks=False):
            entries += len(directories) + len(files)
            if entries > self.MAX_WORKSPACE_ENTRIES:
                raise ExecutionError("Workspace entry limit exceeded")
            for directory in list(directories):
                path = Path(root) / directory
                self._plain_path(path)
                if path.parent == run and directory in {"tmp", "cache"}:
                    directories.remove(directory)
            for name in sorted(files):
                path = Path(root) / name
                self._plain_path(path)
                info = path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ExecutionError("Artifact must be a regular, unlinked file")
                if len(artifacts) >= self.MAX_ARTIFACTS or total + info.st_size > self.MAX_ARTIFACT_BYTES:
                    raise ExecutionError("Artifact count/byte limit exceeded")
                digest = hashlib.sha256()
                read_size = 0
                with path.open("rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise ExecutionError("Artifact changed during opening")
                    while True:
                        if time.monotonic() > hash_deadline:
                            raise ExecutionError("Artifact hashing deadline exceeded")
                        block = handle.read(65536)
                        if not block:
                            break
                        read_size += len(block)
                        if total + read_size > self.MAX_ARTIFACT_BYTES:
                            raise ExecutionError("Artifact byte limit exceeded while hashing")
                        digest.update(block)
                    final = os.fstat(handle.fileno())
                if (final.st_size, final.st_mtime_ns, read_size) != (info.st_size, info.st_mtime_ns, info.st_size):
                    raise ExecutionError("Artifact changed during hashing")
                total += read_size
                artifacts.append({"path": str(path.relative_to(base)), "absolute_path": str(path),
                    "size": read_size, "sha256": digest.hexdigest()})
        return artifacts

    def _validate_target(self, request, deadline, record=None, cancel_event=None):
        target = request.target
        if target is None:
            return
        if not isinstance(target, Target):
            raise SchemaValidationError("Target must carry immutable file identity")
        scope = target.approved_scope
        if scope != "read_only" and not (isinstance(scope, (list, tuple)) and "read_target" in scope):
            raise SchemaValidationError("Target read is outside the approved scope")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", target.sha256) or type(target.size) is not int or target.size < 0:
            raise SchemaValidationError("Invalid target digest/size")
        path = Path(target.canonical_path)
        if not path.is_absolute() or path.resolve() != path or not path.is_file():
            raise ExecutionError("Target must be one canonical regular file")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != target.size:
            raise ExecutionError("Target identity/size changed")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
                raise ExecutionError("Target changed while opening")
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutExpiredError("Target validation exceeded deadline")
                if (cancel_event and cancel_event.is_set()) or (record and record["stop"].is_set()):
                    raise CancellationError("Target validation cancelled")
                block = handle.read(65536)
                if not block:
                    break
                digest.update(block)
            final = os.fstat(handle.fileno())
        if (final.st_size, final.st_mtime_ns) != (info.st_size, info.st_mtime_ns) or digest.hexdigest() != target.sha256.lower():
            raise ExecutionError("Target digest/identity changed")

    def execute(self, manifest: ToolManifest, executable_path: str, request: ToolRequest,
                cancel_event: Optional[threading.Event] = None) -> ToolReceipt:
        self._validate_options(manifest, request.operation, request.options)
        if (type(request.max_output_bytes) is not int or not 1 <= request.max_output_bytes <= self.MAX_OUTPUT_BYTES
                or type(request.deadline_monotonic) not in {int, float}
                or not math.isfinite(request.deadline_monotonic)
                or not math.isfinite(manifest.max_timeout_seconds) or manifest.max_timeout_seconds <= 0):
            raise SchemaValidationError("Invalid output limit or finite execution deadline")
        started = time.monotonic()
        wall_start = time.time()
        deadline = min(request.deadline_monotonic, started + manifest.max_timeout_seconds)
        self._check_admission(request, cancel_event, deadline)
        record = {"process": None, "job": None, "children": {}, "drains": [],
                  "stop": threading.Event(), "investigation_id": request.investigation_id}
        with self._lock:
            self._check_admission(request, cancel_event, deadline)
            if request.request_id in self._active_processes:
                raise ExecutionError("Duplicate active tool request ID")
            self._active_processes[request.request_id] = record
        process = None
        output = {"stdout": bytearray(), "stderr": bytearray()}
        output_lock = threading.Lock()
        overflow = threading.Event()
        status, reason, limitations = "confirmed", None, []
        try:
            base, run = self._workspace(request)
            self._validate_target(request, deadline, record, cancel_event)
            argv = self._build_argv(manifest, executable_path, request)
            clean_env = self._sanitize_environment(run)
            self._check_admission(request, cancel_event, deadline, record)
            process = self._spawn(argv, run, clean_env, record)
            record["process"] = process

            def drain(name, stream):
                try:
                    read = getattr(stream, "read1", stream.read)
                    while True:
                        block = read(8192)
                        if not block:
                            break
                        with output_lock:
                            remaining = request.max_output_bytes - sum(map(len, output.values()))
                            if len(block) > remaining:
                                overflow.set()
                            output[name].extend(block[:max(0, remaining)])
                except (OSError, ValueError) as exc:
                    record["drain_error"] = str(exc)
                finally:
                    stream.close()

            for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
                thread = threading.Thread(target=drain, args=(name, stream), daemon=True)
                record["drains"].append(thread)
                thread.start()
            while True:
                self._observe_children(record)
                if record["stop"].is_set() or (cancel_event and cancel_event.is_set()):
                    status, reason = "cancelled", "cancelled"
                    break
                if overflow.is_set():
                    status, reason = "output_limit", "output_limit"
                    limitations.append(f"Output truncated at limit ({request.max_output_bytes} bytes)")
                    break
                if time.monotonic() >= deadline:
                    status, reason = "timeout", "timeout"
                    limitations.append("Execution exceeded deadline")
                    break
                if process.poll() is not None:
                    break
                record["stop"].wait(.01)
            # A tool's successful parent exit does not confer a lease to background children.
            if not self._tree_empty(record):
                self._terminate(record)
            cleanup_end = time.monotonic() + self.CLEANUP_SECONDS
            while time.monotonic() < cleanup_end:
                for thread in record["drains"]:
                    thread.join(timeout=.01)
                if self._tree_empty(record) and not any(t.is_alive() for t in record["drains"]):
                    break
                self._terminate(record)
                time.sleep(.01)
            clean = self._tree_empty(record) and not any(t.is_alive() for t in record["drains"])
            if not clean:
                status = "failed"
                limitations.append("Owned process tree/output drains remain pending")
            if overflow.is_set():
                status = "output_limit"
                if not any("Output truncated" in item for item in limitations):
                    limitations.append(f"Output truncated at limit ({request.max_output_bytes} bytes)")
            elif status == "confirmed" and (process.returncode != 0 or record.get("drain_error")):
                status = "failed"
            # Freeze drained bytes under lock; pending drains cannot mutate the returned snapshot.
            with output_lock:
                captured = {name: bytes(value) for name, value in output.items()}
            artifacts = []
            if clean:
                try:
                    if reason is None:
                        self._validate_target(request, deadline, record, cancel_event)
                    artifacts = self._artifacts(run, base if request.workspace else run, captured, limitations)
                except (OSError, ExecutionError) as exc:
                    status = "cancelled" if isinstance(exc, CancellationError) else "failed"
                    limitations.append(str(exc))
            if record["stop"].is_set() or (cancel_event and cancel_event.is_set()):
                status = "cancelled"
            argv_redacted = ["[REDACTED]" if re.search(r"(?i)(?:key|secret|token)=", arg) else arg for arg in argv]
            receipt = ToolReceipt(request_id=request.request_id, tool_id=manifest.tool_id,
                source_url=manifest.source_url, pinned_revision=manifest.pinned_revision,
                package_digest=manifest.package_digest, argv_redacted=argv_redacted,
                process_identity={"pid": process.pid, "created_at": record.get("identity"), "exit_code": process.returncode},
                timestamps={"started_at": wall_start, "finished_at": time.time(),
                    "duration_seconds": round(time.monotonic() - started, 4)},
                exit_code=process.returncode, status=status,
                cleanup_receipt={"status": "confirmed" if clean else "pending",
                    "process_exited": process.poll() is not None, "children_reaped": clean,
                    "drains_finished": not any(t.is_alive() for t in record["drains"])},
                artifacts=artifacts, limitations=limitations, stdout=captured["stdout"], stderr=captured["stderr"],
                error_message=("Terminated: " + reason) if reason else None)
            return receipt
        finally:
            if process is None:
                process = record.get("process")
            if process is None:
                with self._condition:
                    self._active_processes.pop(request.request_id, None)
                    if not self._active_processes:
                        self._stopping_all = False
                    self._condition.notify_all()
            else:
                try:
                    released = self._release_when_clean(request.request_id, record)
                except Exception:
                    released = False
                if not released:
                    record["stop"].set()
                    threading.Thread(target=self._watch_pending, args=(request.request_id, record), daemon=True).start()

    def stop_all(self, investigation_id: Optional[str] = None) -> Dict[str, Any]:
        with self._condition:
            if investigation_id is not None:
                self._stopped_investigations.add(investigation_id)
            else:
                self._stopping_all = True
            targets = [record for record in self._active_processes.values()
                       if investigation_id is None or record["investigation_id"] == investigation_id]
            for record in targets:
                self._stopped_investigations.add(record["investigation_id"])
                record["stop"].set()
            until = time.monotonic() + .5
            while any(any(current is record for current in self._active_processes.values()) for record in targets):
                remaining = until - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            pending = any(any(current is record for current in self._active_processes.values()) for record in targets)
            if investigation_id is None and not pending:
                self._stopping_all = False
        return {"status": "pending" if pending else "confirmed", "stopped_count": len(targets), "all_exited": not pending}

    def close(self):
        with self._lock:
            self._closed = True
        return self.stop_all()


class _WindowsJob:
    """Windows kernel ownership survives the parent exiting before descendants."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes as w
        self.ctypes = ctypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        self.kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        class Limits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", w.DWORD), ("min_working", ctypes.c_size_t), ("max_working", ctypes.c_size_t),
                ("process_limit", w.DWORD), ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("limits", Limits), ("io", IO), ("process_mem", ctypes.c_size_t),
                ("job_mem", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        self.assigned = False
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.kernel.CloseHandle(self.handle)
            raise error

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        self.assigned = True

    def empty(self):
        if not self.handle:
            return True
        c = self.ctypes
        from ctypes import wintypes as w
        class Accounting(c.Structure):
            _fields_ = [("user", c.c_int64), ("kernel", c.c_int64), ("period_user", c.c_int64),
                ("period_kernel", c.c_int64), ("faults", w.DWORD), ("total", w.DWORD),
                ("active", w.DWORD), ("terminated", w.DWORD)]
        info = Accounting()
        if not self.kernel.QueryInformationJobObject(self.handle, 1, c.byref(info), c.sizeof(info), None):
            return False
        return info.active == 0

    def terminate(self):
        if self.handle and not self.kernel.TerminateJobObject(self.handle, 1):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
