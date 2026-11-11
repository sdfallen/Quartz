"""
scripts/tool_workbench_acquire_demo.py
Demonstration script for Quartz Tool Workbench.
Resolves, acquires, and executes ripgrep from GitHub against a test target.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.tool_workbench.contracts import AcquisitionPolicy, Target, ToolRequest
from core.tool_workbench.workbench import ToolWorkbench


def main():
    print("=" * 60)
    print("  Quartz Tool Workbench — Acquisition & Execution Demo")
    print("=" * 60)

    with tempfile.TemporaryDirectory(prefix="quartz_demo_") as temp_dir:
        managed_dir = Path(temp_dir) / "managed"
        workspace_dir = Path(temp_dir) / "workspaces"
        target_path = Path(temp_dir) / "sample_binary.bin"

        # Write sample binary data with identifiable strings
        target_path.write_bytes(
            b"PE_HEADER_SIMULATION\x00\x00\x00\x00"
            b"SECTION_TEXT_START\x00"
            b"STRING_FLAG_DISCOVERED=TRUE\x00"
            b"INTERNAL_FUNCTION_InitGraphics\x00"
            b"PE_HEADER_SIMULATION_END\x00"
        )
        target = Target.from_file(target_path)

        workbench = ToolWorkbench(managed_dir=managed_dir, workspace_dir=workspace_dir)

        try:
            # 1. Catalog & Resolve
            print("\n1. Resolving tool for 'binary_string_search'...")
            res = workbench.resolve("binary_string_search")
            print(f"   Tool: {res['tool_id']}")
            print(f"   Pinned revision: {res['pinned_revision']}")
            print(f"   Expected SHA-256: {res['package_digest']}")

            manifest = workbench.catalog_service.get(res["tool_id"])

            # 2. Acquire
            print(f"\n2. Acquiring '{manifest.name}' from {manifest.source_url}...")
            policy = AcquisitionPolicy(
                allow_network=True,
                managed_dir=str(managed_dir),
                verify_digest=True,
            )
            acq_res = workbench.acquire(manifest, policy=policy)
            print(f"   Status: {acq_res['status']}")
            print(f"   Executable: {acq_res['executable_path']}")
            print(f"   Verified Package Digest: {acq_res['package_digest']}")

            # 3. Execute
            print(f"\n3. Executing string extraction on target {target.canonical_path}...")
            req = ToolRequest(
                investigation_id="demo-inv",
                step_id="step-demo-1",
                operation="strings",
                tool_id=manifest.tool_id,
                target=target,
                options={"pattern": "STRING_FLAG_.*"},
            )
            receipt = workbench.execute(req)

            print(f"   Receipt Status: {receipt.status}")
            print(f"   Exit Code: {receipt.exit_code}")
            print(f"   Execution Duration: {receipt.timestamps.get('duration_seconds')}s")
            print(f"   Captured Output:\n   ---")
            for line in receipt.stdout.decode("utf-8", "replace").splitlines():
                print(f"   {line}")
            print(f"   ---")
            print(f"   Process Exit Confirmed: {receipt.cleanup_receipt.get('process_exited')}")

            print("\n4. Closing workbench...")
            close_receipt = workbench.close()
            print(f"   Workbench Close Status: {close_receipt['status']}")

            print("\nDemo completed successfully.")

        finally:
            workbench.close()


if __name__ == "__main__":
    main()
