"""Real desktop + CLI/Squad through GUI-local prepare/status/stop APIs.

Disposable chat persistence is isolated. Host supplies a bounded test grant;
this is not a human clicking the packaged approval card.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import gui
from core.chat_coordination import ChatCoordination
from core.desktop_agents import DesktopAgentService
from core.squad_adapter import SquadAdapter


def main():
    uia="--uia" in sys.argv
    destination=ROOT/"labs"/("desktop-chat-"+time.strftime("%Y%m%d-%H%M%S"));destination.mkdir(parents=True)
    squad=SquadAdapter(destination);squad.initialize()
    desktop=DesktopAgentService();events=[];messages=[];children=[];states=[]
    service=ChatCoordination(desktop,lambda *a:events.append(a))
    api=gui.Api();api._coordination=service;api._desktop_agents=desktop
    exe=ROOT/"build/multiwindow-fixture/MultiWindowFixture.exe"
    models={"codex":{"model":"gpt-6-luna","effort":"low"},"antigravity":{"model":"gemini-3.8-flash-low","effort":"low"}}
    def ipc(action,data=None):
        if action=="chat_status":return {"status":"ok","data":{"active_conversation":{"id":"disposable-chat"},"active_turn":None,
            "projects":[{"id":"disposable","path":str(destination)}]}}
        if action=="chat_coordination_message":messages.append(data);return {"status":"ok"}
        raise AssertionError("Unexpected IPC request: "+action)
    try:
        windows={}
        for name in "ABC":
            child=subprocess.Popen([str(exe)],env={**os.environ,"QUARTZ_FIXTURE_DIR":str(destination),"QUARTZ_FIXTURE_NAME":name});children.append(child)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                matches=[w for w in desktop.windows() if w["pid"]==child.pid]
                if len(matches)==1:windows[name]=matches[0];break
                time.sleep(.2)
            if name not in windows:raise RuntimeError("Owned fixture absent: "+name)
        task=(f"A HWND {windows['A']['handle']} ve B HWND {windows['B']['handle']} test pencerelerini kullan. "
              f"C HWND {windows['C']['handle']} izin dışı. First desktop_windows, desktop_focus A. "+
              ("Inspect actual controls, invoke TEST BUTTON A exactly once using its fresh UIA ref; switch B and invoke TEST BUTTON B exactly once using its fresh ref. " if uia else
               "Inspect actual screenshot, click TEST BUTTON A exactly once, switch B, click TEST BUTTON B exactly once. ")+
              "Switch back A and verify Clicks:1. Attempt desktop_switch C once: denial expected, do not input C. "
              "Read colleague_messages, then report actual results and end. Only broker tools, no shell/files. "+
              ("desktop_act action=ui, ref is the actual TEST BUTTON ref, ui_action=invoke; x,y,text,key,seconds=null; copy EXACT latest top-level snapshot_id. " if uia else
               "desktop_act action is the flat string click, x/y integer screenshot pixels; copy EXACT latest top-level snapshot_id. Other nullable fields null. ")+
              "Stop on unexpected errors.")
        with patch("gui.ipc_send",side_effect=ipc):
            states.append(api.desktop_task_status())
            prepared=api.coordination_route(task,"disposable-chat","disposable",models)
            if prepared["status"]!="ok":raise RuntimeError(prepared)
            plan=prepared["data"]["plan"]
            assert plan["roles"]=={"operator":"codex","observer":"antigravity"}
            states.append(api.desktop_task_status())
            assert states[-1]["data"]["code"]=="pending" and not desktop.broker.status()["active"]
            result=api.coordination_approve(plan["id"],[windows[n]["handle"] for n in "AB"],str(destination/"events.jsonl"),180,True,True,[])
            if result["status"]!="ok":raise RuntimeError(result)
            states.append(api.desktop_task_status())
            assert states[-1]["data"]["control_active"]
            deadline=time.monotonic()+195;last=None
            while service.status()["active"] and time.monotonic()<deadline:
                state=api.desktop_task_status()
                if state["data"]["code"]!=last:states.append(state);last=state["data"]["code"]
                time.sleep(.5)
            if service.status()["active"]:api.desktop_task_stop("coord:"+plan["id"])
            if service.thread:service.thread.join(15)
            states.append(api.desktop_task_status())
        callbacks={n:json.loads((destination/("callback-"+n+".json")).read_text()) if (destination/("callback-"+n+".json")).exists() else None for n in "ABC"}
        result={"coverage":"real Native input and CLI/Squad through GUI APIs; isolated IPC, no actual approval-button click", "input_method":"UIA invoke" if uia else "pixel click",
                "states":states,"callbacks":callbacks,"status":service.status(),"audit":desktop.broker.audit,
                "events":events,"messages":messages,"squad_history":squad.history()}
        (destination/"acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"directory":str(destination),"callbacks":callbacks,"states":[s["data"]["code"] for s in states]}),flush=True)
        return 0 if callbacks["A"]=={"click_count":1} and callbacks["B"]=={"click_count":1} and callbacks["C"] is None else 1
    except Exception as exc:
        (destination/"failure.json").write_text(json.dumps({"error":repr(exc),"states":states,"status":service.status(),"audit":desktop.broker.audit},indent=2),encoding="utf-8")
        print("FAILED/BLOCKED",repr(exc),destination,flush=True);return 1
    finally:
        service.stop();desktop.close()
        for child in children:
            if child.poll() is None:child.terminate();child.wait(10)


if __name__=="__main__":raise SystemExit(main())
