"""Real CLI hook-protocol probe with a fake read-only window list, not UI QA."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.desktop_agents import write_operator_hooks,mcp_command,ensure_antigravity_tool_grants
from core.desktop_broker import DesktopBroker
from core.antigravity_runtime import AntigravityRuntime
from tests.test_desktop_broker import FakeBackend

dest=ROOT/"labs"/("operator-hook-"+time.strftime("%Y%m%d-%H%M%S"));dest.mkdir(parents=True)
runtime=AntigravityRuntime();broker=DesktopBroker(FakeBackend())
try:
    connection=broker.grant(1,"antigravity",confirmed=True)
    write_operator_hooks(dest)
    subprocess.run([runtime.executable,"mcp","add","quartz-desktop",*mcp_command()],capture_output=True,check=True)
    ensure_antigravity_tool_grants()
    run=runtime.start("Hook protocol test. Call ONLY quartz-desktop desktop_windows once using call_mcp_tool. "
        "Report exact result or denial. No other tool, do not retry or bypass.",dest,
        model="gemini-3.8-flash-low",effort="low",desktop_connection=connection,timeout="1m")
    deadline=time.monotonic()+75
    while runtime.get(run["id"])["status"] not in runtime.TERMINAL and time.monotonic()<deadline:time.sleep(.3)
    runtime.shutdown();result=runtime.get(run["id"])
    (dest/"acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(result["result"],dest,flush=True)
finally:runtime.shutdown();broker.close()
