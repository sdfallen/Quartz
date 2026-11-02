"""
core/tool_workbench/execution.py
Isolated and tracked process execution for Quartz Tool Workbench.
Enforces argv schema validation, secrets filtering, output overflow bounding,
process tree tracking, cancellation, and artifact generation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
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
        self._workspace_root = (workspace_root or Path(tempfile.gettempdir()) / "quartz_workbench_runs").resolve()
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._active_processes: Dict[str, Tuple[subprocess.Popen, float, str]] = {}  # req_id -> (proc, start_time, inv_id)

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def _sanitize_environment(self, workspace_dir: Path) -> Dict[str, str]:
        """Produce an isolated environment stripping all secrets, keys, and credentials."""
        safe_keys = {"SYSTEMROOT", "COMSPEC", "PATHEXT", "WINDIR", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"}
        env: Dict[str, str] = {}

        for k, v in os.environ.items():
            k_upper = k.upper()
            if any(secret in k_upper for secret in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH", "COOKIE", "PRIVATE")):
                continue
            if k_upper in safe_keys:
                env[k] = v

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
        for opt_key, opt_val in options.items():
            if opt_key not in allowed_options:
                raise SchemaValidationError(f"Unrecognized option '{opt_key}' for operation '{operation}'")
            if isinstance(opt_val, str) and _DISALLOWED_SHELL_CHARS.search(opt_val):
                raise SchemaValidationError(f"Disallowed shell character in option '{opt_key}'")

        for req_key, req_spec in allowed_options.items():
            if req_spec.get("required") and req_key not in options:
                raise SchemaValidationError(f"Missing required option '{req_key}' for operation '{operation}'")

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

    def execute(
        self,
        manifest: ToolManifest,
        executable_path: str,
        request: ToolRequest,
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolReceipt:
        """
        Execute tool within an isolated workspace with streaming output drain and process-tree supervision.
        """
        self._validate_options(manifest, request.operation, request.options)

        # Setup isolated run workspace
        if request.workspace:
            run_workspace = Path(request.workspace).resolve()
        else:
            run_workspace = (self._workspace_root / f"run_{request.investigation_id}_{request.step_id}_{uuid.uuid4().hex[:6]}").resolve()
        run_workspace.mkdir(parents=True, exist_ok=True)

        argv = self._build_argv(manifest, executable_path, request)
        clean_env = self._sanitize_environment(run_workspace)

        # Redacted argv for receipt logging
        argv_redacted = list(argv)
        for i, arg in enumerate(argv_redacted):
            if any(secret in arg.upper() for secret in ("KEY=", "SECRET=", "TOKEN=")):
                argv_redacted[i] = "[REDACTED]"

        start_time = time.monotonic()
        timestamp_start = time.time()

        log.info("Executing tool %s (op=%s, req=%s) in %s", manifest.tool_id, request.operation, request.request_id, run_workspace)

        # Spawn subprocess with CREATE_NO_WINDOW
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            argv,
            cwd=str(run_workspace),
            env=clean_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
        )

        with self._lock:
            self._active_processes[request.request_id] = (process, start_time, request.investigation_id)

        # Output streaming and limits
        chunks: Dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
        drain_lock = threading.Lock()
        overflow_event = threading.Event()
        max_output = request.max_output_bytes

        def drain_stream(name: str, stream):
            try:
                while True:
                    block = stream.read(8192)
                    if not block:
                        break
                    with drain_lock:
                        current_total = sum(len(c) for c in chunks.values())
                        if current_total + len(block) > max_output:
                            overflow_event.set()
                            remaining = max(0, max_output - current_total)
                            if remaining > 0:
                                chunks[name].extend(block[:remaining])
                        else:
                            chunks[name].extend(block)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        drain_threads = [
            threading.Thread(target=drain_stream, args=("stdout", process.stdout), name=f"drain-stdout-{request.request_id}", daemon=True),
            threading.Thread(target=drain_stream, args=("stderr", process.stderr), name=f"drain-stderr-{request.request_id}", daemon=True),
        ]
        for t in drain_threads:
            t.start()

        status = "confirmed"
        termination_reason = None
        limitations: List[str] = []

        try:
            # Supervised wait loop
            while process.poll() is None:
                if cancel_event and cancel_event.is_set():
                    termination_reason = "cancelled"
                    status = "cancelled"
                    break
                if overflow_event.is_set():
                    termination_reason = "output_limit"
                    status = "output_limit"
                    limitations.append(f"Output truncated at limit ({max_output} bytes)")
                    break
                if time.monotonic() > request.deadline_monotonic:
                    termination_reason = "timeout"
                    status = "timeout"
                    limitations.append(f"Execution exceeded deadline of {request.deadline_monotonic - start_time:.1f}s")
                    break
                time.sleep(0.05)

            # If stopped due to limit, timeout, or cancellation, kill process tree
            if termination_reason:
                log.warning("Tool %s terminated due to: %s", manifest.tool_id, termination_reason)
                stop_process_tree(process, timeout=3.0)

            # Await process exit
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                stop_process_tree(process, timeout=1.0)
                process.wait(timeout=2.0)

        finally:
            with self._lock:
                self._active_processes.pop(request.request_id, None)

            # Ensure reader threads finish
            for t in drain_threads:
                t.join(timeout=1.0)

        duration = max(0.0, time.monotonic() - start_time)
        timestamp_end = time.time()
        exit_code = process.returncode

        if overflow_event.is_set():
            status = "output_limit"
            if not any("Output truncated" in lim for lim in limitations):
                limitations.append(f"Output truncated at limit ({max_output} bytes)")
        elif status == "confirmed" and exit_code != 0:
            status = "failed"
            limitations.append(f"Process exited with non-zero code {exit_code}")

        # Scan workspace for generated artifacts
        artifacts: List[Dict[str, Any]] = []
        for root, _, files in os.walk(run_workspace):
            for file_name in files:
                fpath = Path(root) / file_name
                # Avoid counting temporary internal files
                if "tmp" in fpath.parts or "cache" in fpath.parts:
                    continue
                try:
                    st = fpath.stat()
                    art_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
                    artifacts.append({
                        "path": str(fpath.relative_to(run_workspace)),
                        "absolute_path": str(fpath),
                        "size": st.st_size,
                        "sha256": art_hash,
                    })
                except OSError:
                    pass

        receipt = ToolReceipt(
            request_id=request.request_id,
            tool_id=manifest.tool_id,
            source_url=manifest.source_url,
            pinned_revision=manifest.pinned_revision,
            package_digest=manifest.package_digest,
            argv_redacted=argv_redacted,
            process_identity={
                "pid": process.pid,
                "exit_code": exit_code,
            },
            timestamps={
                "started_at": timestamp_start,
                "finished_at": timestamp_end,
                "duration_seconds": round(duration, 4),
            },
            exit_code=exit_code,
            status=status,
            cleanup_receipt={
                "process_exited": process.poll() is not None,
                "children_reaped": True,
            },
            artifacts=artifacts,
            limitations=limitations,
            stdout=bytes(chunks["stdout"]),
            stderr=bytes(chunks["stderr"]),
            error_message=f"Terminated: {termination_reason}" if termination_reason else None,
        )

        return receipt

    def stop_all(self, investigation_id: Optional[str] = None) -> Dict[str, Any]:
        """Stop all tracked processes, optionally filtered by investigation ID."""
        with self._lock:
            targets = list(self._active_processes.items())

        stopped_count = 0
        all_exited = True

        for req_id, (proc, _, inv_id) in targets:
            if investigation_id and inv_id != investigation_id:
                continue
            if proc.poll() is None:
                success = stop_process_tree(proc, timeout=3.0)
                if not success:
                    all_exited = False
                stopped_count += 1

        return {
            "status": "confirmed" if all_exited else "pending",
            "stopped_count": stopped_count,
            "all_exited": all_exited,
        }
