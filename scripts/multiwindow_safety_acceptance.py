"""Owned real Windows lifecycle/launch acceptance through the packaged MCP.

This exercises product APIs, not packaged main-chat inline consent or visual QA.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.desktop_broker import DesktopBroker
from core.desktop_native import NativeDesktopBackend
from core.desktop_launch import describe_launch
from core.desktop_agents import connection_environment


def main():
    dest=ROOT/"labs"/("multiwindow-safety-"+time.strftime("%Y%m%d-%H%M%S"));dest.mkdir(parents=True)
    exe=ROOT/"build/multiwindow-fixture/MultiWindowFixture.exe"
    helper=ROOT/"build/desktop-helper/QuartzDesktopMCP.exe"
    backend=NativeDesktopBackend();broker=DesktopBroker(backend);children=[];results=[]
    old_dir=os.environ.get("QUARTZ_FIXTURE_DIR");old_name=os.environ.get("QUARTZ_FIXTURE_NAME")
    os.environ["QUARTZ_FIXTURE_DIR"]=str(dest);os.environ["QUARTZ_FIXTURE_NAME"]="LAUNCH"
    def start(name):
        child=subprocess.Popen([str(exe)],env={**os.environ,"QUARTZ_FIXTURE_NAME":name});children.append(child)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            match=[w for w in backend.windows() if w["pid"]==child.pid]
            if len(match)==1:return child,match[0]
            time.sleep(.15)
        raise RuntimeError("Fixture unavailable")
    def tool(connection,name,**args):
        request={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}}
        proc=subprocess.run([str(helper)],input=json.dumps(request)+"\n",capture_output=True,text=True,encoding="utf-8",
                            env=connection_environment(connection),timeout=30)
        response=json.loads(proc.stdout)["result"]
        data=json.loads(response["content"][0]["text"]) if not response["isError"] else response["content"][0]["text"]
        results.append({"tool":name,"arguments":args,"error":response["isError"],
                        "result":data if isinstance(data,str) else {k:v for k,v in data.items() if k!="observation"}})
        return response["isError"],data
    try:
        a,wa=start("A");b,wb=start("B");c,wc=start("C")
        app=describe_launch(exe)
        connection=broker.grant([wa["handle"],wb["handle"]],"codex",confirmed=True,launches=[app])
        assert not tool(connection,"desktop_focus")[0]
        second=DesktopBroker(backend)
        try:
            try:second.grant(wc["handle"],"antigravity",confirmed=True)
            except RuntimeError:results.append({"one_os_lease":"VERIFIED"})
            else:raise AssertionError("second lease acquired")
        finally:second.close()
        assert tool(connection,"desktop_switch",handle=wc["handle"])[0]
        assert not tool(connection,"desktop_switch",handle=wb["handle"])[0]
        assert not tool(connection,"desktop_switch",handle=wa["handle"])[0]
        error,launch=tool(connection,"desktop_launch",app_id=app["id"])
        assert not error
        import psutil
        launched=psutil.Process(launch["target"]["pid"])
        assert launched.exe().lower()==str(exe).lower()
        assert tool(connection,"desktop_launch",app_id=app["id"])[0]
        launched.terminate();launched.wait(10)
        assert tool(connection,"desktop_observe")[0]
        assert not broker.status()["active"]
        connection=broker.grant([wa["handle"],wb["handle"]],"codex",confirmed=True)
        assert not tool(connection,"desktop_focus")[0]
        backend.focus(wc)  # external test driver changes focus; no C input
        assert tool(connection,"desktop_observe")[0]
        assert not broker.status()["active"]
        connection=broker.grant(wa["handle"],"codex",confirmed=True)
        broker.stop("test Stop")
        assert tool(connection,"desktop_observe")[0]
        d,wd=start("NEW-HWND")
        connection=broker.grant(wa["handle"],"codex",confirmed=True)
        assert tool(connection,"desktop_switch",handle=wd["handle"])[0]
        broker.stop()
        (dest/"acceptance.json").write_text(json.dumps({"status":"VERIFIED","tests":results,"audit":broker.audit,
            "coverage":"real owned windows and packaged MCP, not main GUI approval","display":{"rect":wa["rect"]}},indent=2),encoding="utf-8")
        print("VERIFIED",dest,flush=True)
        return 0
    except Exception as exc:
        (dest/"failure.json").write_text(json.dumps({"error":repr(exc),"tests":results,"audit":broker.audit},indent=2),encoding="utf-8")
        print("FAILED/BLOCKED",repr(exc),dest,flush=True);return 1
    finally:
        broker.close()
        for child in children:
            if child.poll() is None:child.terminate();child.wait(10)
        for key,value in (("QUARTZ_FIXTURE_DIR",old_dir),("QUARTZ_FIXTURE_NAME",old_name)):
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


if __name__=="__main__":raise SystemExit(main())
