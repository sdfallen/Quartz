"""Preserve the closed desktop distribution, deploy and record validation.

Never starts the GUI or a native input session. Refuses a running Quartz EXE.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.home() / ".codex/backups/quartz-desktop-package-20261020-200000"


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    import psutil
    def ensure_quartz_closed():
        for proc in psutil.process_iter(["name"]):
            if (proc.info["name"] or "").lower() == "quartz.exe":
                raise RuntimeError("Quartz is running; no deployment performed")
    ensure_quartz_closed()
    user_files = [ROOT / name for name in (".env", "quartz_memory.json", "quartz_conversations.json")]
    baseline = {str(path): digest(path) for path in user_files}
    tests = subprocess.run([sys.executable, str(ROOT / "scripts/run_safe_tests.py")], cwd=ROOT, capture_output=True)
    (PACKAGE / "regression-final.log").write_bytes(tests.stdout + tests.stderr)
    if tests.returncode: raise RuntimeError("Regression failed; old distribution untouched")
    check = subprocess.run([sys.executable, str(ROOT / "scripts/verify_desktop_package.py"),
                            str(PACKAGE / "dist/Quartz/Quartz.exe")], cwd=ROOT, capture_output=True)
    (PACKAGE / "package-verification.json").write_bytes(check.stdout)
    if check.returncode: raise RuntimeError("Package code mismatch; old distribution untouched")
    helper = PACKAGE / "dist/Quartz/_internal/operator/QuartzDesktopMCP.exe"
    env = os.environ.copy()
    env.pop("QUARTZ_DESKTOP_TOKEN", None); env.pop("QUARTZ_DESKTOP_URL", None)
    requests = [{"jsonrpc": "2.0", "id": "işlem-漢字", "method": "initialize"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "desktop_observe"}}]
    response = subprocess.run([str(helper)], input="".join(json.dumps(r)+"\n" for r in requests),
                              capture_output=True, text=True, encoding="utf-8", timeout=30, env=env)
    protocol = [json.loads(line) for line in response.stdout.splitlines() if line.strip()]
    if (response.returncode or len(protocol) != 3 or protocol[0].get("id") != "işlem-漢字"
            or not protocol[-1].get("result", {}).get("isError")):
        raise RuntimeError("Packaged helper fail-closed acceptance failed")
    old = ROOT / "dist/Quartz"
    old_backup = Path.home() / (".codex/backups/quartz-before-desktop-bridge-" + time.strftime("%Y%m%d-%H%M%S"))
    stage = PACKAGE / "dist/Quartz"
    if not old.is_dir() or not stage.is_dir() or old_backup.exists(): raise RuntimeError("Unexpected deployment paths")
    preserved = {}
    ensure_quartz_closed()
    # Preserve top-level local data/logs; never copy stale binary internals over new code.
    for item in old.iterdir():
        if item.name == "_internal" or item.suffix.lower() in {".exe", ".dll"}: continue
        target = stage / item.name
        if target.exists(): raise RuntimeError("Refuse to overwrite an unexpected staged data file")
        if item.is_dir(): shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
            if digest(item) != digest(target): raise RuntimeError("Data copy differs")
            preserved[item.name] = digest(item)
    # Exact, validated, recoverable directory moves; no deletion or broad cleanup.
    ensure_quartz_closed()
    if old.anchor != old_backup.anchor or old.anchor != stage.anchor:
        raise RuntimeError("Deployment must use same-volume atomic directory renames")
    os.rename(old, old_backup)
    try:
        os.rename(stage, old)
    except Exception:
        os.rename(old_backup, old)
        raise
    final = {str(path): digest(path) for path in user_files}
    if final != baseline: raise RuntimeError("Source user-data changed during validation")
    receipt = {"exe": str(old / "Quartz.exe"), "sha256": digest(old / "Quartz.exe"),
               "old_distribution": str(old_backup), "preserved_data": preserved,
               "all_preserved_data_equal": all(digest(old / name) == value for name, value in preserved.items()),
               "source_user_data_before": baseline, "source_user_data_after": final,
               "helper_protocol": protocol, "native_input": "See docs/QUARTZ_ACCEPTANCE_AND_CHAT_STYLE_20261021.md and earlier desktop evidence; this receipt verifies packaging/data only, not GUI acceptance",
               "warband_control": "Task-scoped Universal Modder adapter packaged; see docs/QUARTZ_WARBAND_WORKFLOW.md for actual acceptance scope", "gui_started": False}
    (PACKAGE / "deployment-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("exe", "sha256", "old_distribution", "all_preserved_data_equal", "gui_started")}, indent=2))


if __name__ == "__main__": main()
