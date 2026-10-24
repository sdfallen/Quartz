"""Real project, read-only UM preparation/contracts/preservation acceptance.

Never launches the game, changes gameplay source, compiles the module or writes
a save. Checks actual UM checkpoint receipts and original save checksums.
"""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.warband_workspace import WarbandWorkspace,digest,SAVES,GAME


def main():
    destination=ROOT/"labs"/("warband-adapter-"+time.strftime("%Y%m%d-%H%M%S"))
    workspace=WarbandWorkspace(destination)
    before={p.name:digest(p) for p in sorted(SAVES.glob("sg*.sav"))}
    module=digest(GAME/"Modules/AI_Island_Test/scripts.txt")
    workspace.grant(["inspect"])
    results={}
    try:
        for operation in ("preflight","contracts","preservation","prepare"):
            workspace.run(operation)
            while workspace.job["status"]=="running": time.sleep(.25)
            results[operation]=dict(workspace.job)
            print(operation,workspace.job["status"],flush=True)
            if workspace.job["status"]!="completed": break
        after={p.name:digest(p) for p in sorted(SAVES.glob("sg*.sav"))}
        report={"level":"SOURCE/STATIC + ACTUAL UM BACKUP; NOT LIVE GAMEPLAY",
                "jobs":results,"saves_before":before,"saves_after":after,"save_diff0":before==after,
                "scripts_before":module,"scripts_after":digest(GAME/"Modules/AI_Island_Test/scripts.txt"),
                "status":"VERIFIED" if len(results)==4 and all(r["status"]=="completed" for r in results.values()) and before==after else "FAILED"}
        (workspace.evidence/"acceptance.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps({"status":report["status"],"save_diff0":report["save_diff0"],"evidence":str(workspace.evidence)},ensure_ascii=False),flush=True)
        return 0 if report["status"]=="VERIFIED" else 1
    finally: workspace.shutdown()

if __name__=="__main__": raise SystemExit(main())
