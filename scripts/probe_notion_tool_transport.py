"""Diagnostic probe for Notion tool transport protocol and local adapter readiness.

Defaults to safe read-only contract verification. Does not execute side-effecting
system tasks or connect to active model sessions unless --allow-active-task is explicitly set.
Never logs credentials, auth tokens, or raw binary payloads.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.notion_cli import profile_root, resolve_ntn
from core.notion_tool_transport import (
    DEFAULT_MAX_PAYLOAD_BYTES,
    NotionToolRequest,
    NotionToolResult,
    NotionToolTransport,
    SCHEMA_VERSION,
    format_continuation_message,
)


def probe_local_environment() -> dict[str, Any]:
    """Check whether official Notion CLI and workspace configuration exist locally."""
    try:
        ntn_path = resolve_ntn()
        cli_installed = True
    except FileNotFoundError:
        ntn_path = None
        cli_installed = False

    config_path = profile_root() / "connection.json"
    configured = False
    workspace_id = None
    agent_id = None
    agent_name = None

    if config_path.is_file():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            workspace_id = cfg.get("workspace_id")
            agent_id = cfg.get("agent_id")
            agent_name = cfg.get("agent_name")
            configured = bool(workspace_id and agent_id)
        except Exception:
            pass

    return {
        "cli_installed": cli_installed,
        "ntn_executable": ntn_path,
        "configured": configured,
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "config_file": str(config_path),
    }


def probe_transport_contract() -> dict[str, Any]:
    """Run simulated read-only contract checks across NotionToolTransport."""
    execution_log = []

    def simulated_read_only_router(req: NotionToolRequest) -> dict:
        execution_log.append(req.request_id)
        if req.tool_name == "probe_read_only":
            return {
                "status": "completed",
                "output": {"result": "probe_ok", "tool": req.tool_name, "args": req.arguments},
                "verification": "observed",
            }
        return {"status": "rejected", "error": "Unknown tool in read-only probe"}

    transport = NotionToolTransport(simulated_read_only_router)

    task_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    request_id = f"probe-{uuid.uuid4().hex[:8]}"

    valid_req = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "session_id": session_id,
        "request_id": request_id,
        "tool_name": "probe_read_only",
        "arguments": {"test_key": "test_val"},
        "project_id": "probe-project",
        "scope_ref": "read_only_scope",
        "deadline": time.monotonic() + 10.0,
    }

    # 1. Dispatch
    t0 = time.perf_counter()
    res1 = transport.dispatch(valid_req)
    t_dispatch_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Idempotent replay
    res2 = transport.dispatch(valid_req)
    idempotent_ok = (res2.request_id == res1.request_id) and (len(execution_log) == 1)

    # 3. Format continuation turn message
    turn_msg = format_continuation_message(res1)
    continuation_ok = bool(turn_msg.get("session_id") == session_id and turn_msg.get("message"))

    # 4. Check cancellation
    cancel_req_id = f"probe-cancel-{uuid.uuid4().hex[:8]}"
    transport.cancel_request(cancel_req_id)
    res_cancel = transport.dispatch({
        **valid_req,
        "request_id": cancel_req_id,
    })
    cancellation_ok = (res_cancel.status == "cancelled")

    # 5. Check deadline timeout
    res_timeout = transport.dispatch({
        **valid_req,
        "request_id": f"probe-timeout-{uuid.uuid4().hex[:8]}",
        "deadline": time.monotonic() - 1.0,
    })
    timeout_ok = (res_timeout.status == "timeout")

    return {
        "status": "PASS" if (res1.status == "completed" and idempotent_ok and continuation_ok and cancellation_ok and timeout_ok) else "FAIL",
        "dispatch_latency_ms": round(t_dispatch_ms, 2),
        "idempotent_replay_verified": idempotent_ok,
        "continuation_format_verified": continuation_ok,
        "cancellation_verified": cancellation_ok,
        "deadline_timeout_verified": timeout_ok,
        "schema_version": SCHEMA_VERSION,
        "max_payload_bytes": DEFAULT_MAX_PAYLOAD_BYTES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Notion tool transport adapter and connection readiness.")
    parser.add_argument("--allow-active-task", action="store_true", default=False,
                        help="Allow active tasks (defaults to false for safe read-only diagnostics).")
    parser.add_argument("--json", action="store_true", default=False,
                        help="Output report in machine-readable JSON format.")
    args = parser.parse_args()

    env_info = probe_local_environment()
    contract_info = probe_transport_contract()

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "active" if args.allow_active_task else "read-only",
        "feasibility": {
            "direct_cloud_to_stdio_mcp": "BLOCKED (Cloud Custom Agent cannot reach local stdio without hosted relay)",
            "supported_path": "Client-Orchestrated Continuation (Quartz local execution + session turn continuation)",
            "zero_cloud_cost": True,
            "offline_safe": True,
        },
        "environment": env_info,
        "contract_probe": contract_info,
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=== Quartz Notion Tool Transport Probe ===")
        print(f"Mode: {report['mode']}")
        print(f"Direct cloud-to-stdio: {report['feasibility']['direct_cloud_to_stdio_mcp']}")
        print(f"Supported Architecture: {report['feasibility']['supported_path']}")
        print(f"CLI Installed: {env_info['cli_installed']} ({env_info['ntn_executable'] or 'not found'})")
        print(f"Configured: {env_info['configured']} (agent: {env_info['agent_name'] or 'none'})")
        print(f"Transport Contract: {contract_info['status']} (dispatch: {contract_info['dispatch_latency_ms']}ms)")
        print(f"  - Idempotent replay: {'OK' if contract_info['idempotent_replay_verified'] else 'FAIL'}")
        print(f"  - Cancellation: {'OK' if contract_info['cancellation_verified'] else 'FAIL'}")
        print(f"  - Deadline timeout: {'OK' if contract_info['deadline_timeout_verified'] else 'FAIL'}")
        print(f"  - Continuation turn formatting: {'OK' if contract_info['continuation_format_verified'] else 'FAIL'}")

    return 0 if contract_info["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
