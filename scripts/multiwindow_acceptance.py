"""Real native broker + actual CLI/Squad multiwindow product self-test.

Not packaged-main-chat consent acceptance. Uses owned A/B/C fixtures. The
software-test harness supplies the explicit grant, never bypasses broker input.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.chat_coordination import ChatCoordination
from core.desktop_agents import DesktopAgentService
from core.squad_adapter import SquadAdapter


def main():
    provider=sys.argv[1] if len(sys.argv)>1 else "codex"
    uia="--uia" in sys.argv[2:]
    dest=ROOT/"labs"/("multiwindow-"+provider+"-"+time.strftime("%Y%m%d-%H%M%S"))
    dest.mkdir(parents=True)
    exe=ROOT/"build/multiwindow-fixture/MultiWindowFixture.exe"
    exe.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run([r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe","/nologo","/target:winexe",
                    "/out:"+str(exe),str(ROOT/"scripts/MultiWindowFixture.cs")],check=True)
    desktop=DesktopAgentService();events=[];children=[]
    service=ChatCoordination(desktop,lambda *a:events.append(a))
    try:
        squad=SquadAdapter(dest);squad.initialize()
        windows={}
        for name in "ABC":
            child=subprocess.Popen([str(exe)],env={**os.environ,"QUARTZ_FIXTURE_DIR":str(dest),"QUARTZ_FIXTURE_NAME":name})
            children.append(child)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                matches=[w for w in desktop.windows() if w["pid"]==child.pid and w["title"]=="Quartz Multiwindow Fixture "+name]
                if len(matches)==1: windows[name]=matches[0];break
                time.sleep(.2)
            if name not in windows: raise RuntimeError("Owned fixture window absent: "+name)
        task=("Codex bilgisayar kontrolünü al. Gemini logları izle ve analiz et." if provider=="codex" else
              "Gemini bilgisayar kontrolünü al. Codex logları izle ve analiz et.")
        task+=(f"\nDisposable test: A HWND={windows['A']['handle']}, B HWND={windows['B']['handle']}, C HWND={windows['C']['handle']}. "
               "Only A and B approved. desktop_windows then desktop_focus (A). Inspect actual image. "+
               ("Activate TEST BUTTON A ONCE using actual current UIA ref, action=ui, ui_action=invoke. desktop_switch B; invoke TEST BUTTON B ONCE using its fresh ref. " if uia else
                "Click the visual CENTER of TEST BUTTON A ONCE using screenshot-relative pixels, not its border. desktop_switch B; inspect then click the visual CENTER of TEST BUTTON B ONCE. ")+
               "desktop_switch A and verify Clicks:1. Attempt desktop_switch C ONCE; denial expected, do NOT input into C. "
               "Read colleague_messages via desktop_observe after returning A. Report actual observed counts and colleague note. "
               "No typing, shell, filesystem, browser, extra focus or other tools. Stop on unexpected errors. "+
               ("desktop_act Arguments are FLAT: snapshot_id is the EXACT latest top-level value; action=ui, ref is the observed TEST BUTTON ref, ui_action=invoke, x,y,text,key,seconds=null. " if uia else
                "desktop_act Arguments are FLAT: snapshot_id is the EXACT latest top-level value; action is the literal STRING click, x,y are screenshot-derived INTEGER pixels. Set text,key,seconds,ref,ui_action to null. ")+
               "Do not use a nested action object or wrap desktop_act Arguments in another Arguments object.")
        models={"codex":{"model":"gpt-6-luna","effort":"low"},"antigravity":{"model":"gemini-3.8-flash-medium" if uia else "gemini-4-argon-low" if provider=="antigravity" else "gemini-3.8-flash-low","effort":"medium" if uia else "low"}}
        plan=service.propose(task,{"id":"disposable","path":str(dest)},"fixture-chat",models)
        service.approve(plan["id"],[windows[n]["handle"] for n in "AB"],str(dest/"events.jsonl"),180,confirmed=True,agy_ack=True)
        print("START",provider,dest,flush=True)
        deadline=time.monotonic()+195
        while service.status()["active"] and time.monotonic()<deadline: time.sleep(.5)
        if service.status()["active"]:service.stop()
        if service.thread:service.thread.join(15)
        callbacks={n:json.loads((dest/("callback-"+n+".json")).read_text()) if (dest/("callback-"+n+".json")).exists() else None for n in "ABC"}
        log_errors={n:(dest/("log-error-"+n+".txt")).read_text() if (dest/("log-error-"+n+".txt")).exists() else None for n in "ABC"}
        result={"status":service.status(),"input_method":"UIA invoke" if uia else "pixel click","callbacks":callbacks,"windows":windows,"audit":desktop.broker.audit,
                "events":events,"squad_history":squad.history(),"log_errors":log_errors,
                "operator":desktop._runtime.get(desktop._run_id) if desktop._runtime else None}
        (dest/"acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"directory":str(dest),"callbacks":callbacks,"status":result["status"]["job"]["status"],
                          "analysis_rounds":result["status"]["job"]["analysis_rounds"]}),flush=True)
        return 0 if (callbacks["A"]=={"click_count":1} and callbacks["B"]=={"click_count":1}
                     and callbacks["C"] is None and not any(log_errors.values())) else 1
    except Exception as exc:
        (dest/"failure.json").write_text(json.dumps({"error":repr(exc),"status":service.status(),"events":events,"audit":desktop.broker.audit},indent=2),encoding="utf-8")
        print("FAILED/BLOCKED",repr(exc),dest,flush=True);return 1
    finally:
        service.stop();desktop.close()
        for child in children:
            if child.poll() is None:
                # Only exact test children created above, never unrelated windows.
                child.terminate();child.wait(10)


if __name__=="__main__":raise SystemExit(main())
