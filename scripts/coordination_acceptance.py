"""Real provider/Squad/native-window coordination, isolated from user projects.

This is a product self-test, not a claim of packaged main-GUI acceptance.
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
    destination=ROOT/"labs"/("coordination-"+provider+"-"+time.strftime("%Y%m%d-%H%M%S"))
    destination.mkdir(parents=True)
    desktop=DesktopAgentService(); events=[]
    service=ChatCoordination(desktop,lambda *args:events.append(args))
    fixture=None; plan=None
    try:
        squad=SquadAdapter(destination); squad.initialize()
        fixture=subprocess.Popen([sys.executable,str(ROOT/"scripts/coordination_fixture.py")],cwd=ROOT,
            env={**os.environ,"QUARTZ_FIXTURE_DIR":str(destination)},creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        for _ in range(50):
            matches=[w for w in desktop.windows() if w["pid"]==fixture.pid and w["title"]=="Quartz Disposable Coordination Test"]
            if matches: break
            if fixture.poll() is not None: raise RuntimeError("Owned fixture exited")
            time.sleep(.2)
        if len(matches)!=1: raise RuntimeError("Owned disposable window not uniquely found")
        text=("Codex, bilgisayar kontrolünü al. Gemini, logları izle ve hataları analiz et."
              if provider=="codex" else "Gemini, bilgisayar kontrolünü al. Codex, logları izle ve hataları analiz et.")
        text += (" Operator task: focus ONCE, inspect the actual image. Click TEST BUTTON exactly ONCE with "
                 "desktop_act action=click and integer snapshot-relative coordinates, not UI invocation. "
                 "Read the resulting click count, then call desktop_observe once for current colleague_messages and report any actual log observation. "
                 "No typing, no other windows, no shell/file/browser tools. Stop on an error, do not retry focus.")
        models={"codex":{"model":"gpt-6-luna","effort":"low"},"antigravity":{"model":"gemini-3.8-flash-low","effort":"low"}}
        plan=service.propose(text,{"id":"disposable","path":str(destination)},"test-conversation",models)
        service.approve(plan["id"],matches[0]["handle"],str(destination/"events.jsonl"),120,confirmed=True,agy_ack=True)
        print("START",provider,"fixture",fixture.pid,flush=True)
        limit=time.monotonic()+130
        while service.status()["active"] and time.monotonic()<limit: time.sleep(.5)
        if service.status()["active"]: service.stop()
        if service.thread: service.thread.join(timeout=15)
        result={"status":service.status(),"events":events,"audit":desktop.broker.audit,
                "callback":json.loads((destination/"callback.json").read_text()) if (destination/"callback.json").is_file() else None,
                "squad_history":squad.history(),"observer_runs":service.observer_runtime.list() if service.observer_runtime else [],
                "operator_run":desktop._runtime.get(desktop._run_id) if desktop._runtime else None}
        (destination/"acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"directory":str(destination),"status":result["status"]["job"]["status"],"callback":result["callback"],
                          "analysis_rounds":result["status"]["job"]["analysis_rounds"],"events":len(events)},ensure_ascii=True),flush=True)
    except Exception as exc:
        (destination/"failure.json").write_text(json.dumps({"error":str(exc),"status":service.status(),"events":events},indent=2),encoding="utf-8")
        print("BLOCKED/FAILED",repr(exc),"evidence",destination,flush=True)
        return 1
    finally:
        service.stop(); desktop.close()
        if fixture is not None and fixture.poll() is None:
            fixture.terminate(); fixture.wait(timeout=10)
    return 0


if __name__=="__main__": raise SystemExit(main())
