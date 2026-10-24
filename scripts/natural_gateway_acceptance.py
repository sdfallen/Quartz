"""Real CLI/MCP/Squad transport check WITHOUT any native input or permission.

Not a substitute for packaged-chat / visual acceptance. Providers may exchange
only synthetic test notes in an isolated workspace; the backend has no windows.
"""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.desktop_broker import DesktopBroker
from core.natural_desktop import NaturalDesktopTask
from core.squad_adapter import SquadAdapter


class NoInputBackend:
    def windows(self):return []
    def identity(self,*a):raise PermissionError("Transport test has no desktop authority")


def main():
    destination=ROOT/"labs"/("natural-gateway-"+time.strftime("%Y%m%d-%H%M%S"))
    destination.mkdir()
    SquadAdapter(destination).initialize()
    backend=NoInputBackend();broker=DesktopBroker(backend)
    service=NaturalDesktopTask(SimpleNamespace(broker=broker,windows=backend.windows),lambda *a:None,evidence_root=destination/"evidence")
    models={"codex":{"model":"gpt-6-luna","effort":"low"},"antigravity":{"model":"gemini-3.8-flash-low","effort":"low"}}
    prompt=("Codex, bu yalnız CLI/MCP/Squad bağlantı testi. task_context çağır, task_message ile 'CODEX_TRANSPORT_OK' gönder, "
            "sonra sonlandır. Ekran/izin/dosya isteme, masaüstü testi yaptığını söyleme. "
            "Gemini, aynı bağlantı testinde task_context çağır, task_message ile 'GEMINI_TRANSPORT_OK' gönder. "
            "Codex notu ve bitiş durumu gelince kısa son yanıtını ver. Native backend bu testte boş; grafik kabul DEĞİL.")
    try:
        service.start(prompt,{"path":str(destination)},"transport-only",models)
        deadline=time.monotonic()+150
        while service.status()["active"] and time.monotonic()<deadline:time.sleep(.5)
        if service.status()["active"]:service.stop("transport test timeout")
        if service.thread:service.thread.join(5)
        runs={p:r.get(rid) for p,(r,rid) in service.runs.items()}
        notes=[e["content"] for e in service.job["events"]]
        verdict=(any("CODEX_TRANSPORT_OK" in t for t in notes) and any("GEMINI_TRANSPORT_OK" in t for t in notes)
                 and all(r["status"]=="completed" for r in runs.values()) and not broker.audit)
        compact={p:{k:r.get(k) for k in ("status","model","effort","started_at","finished_at","errors","result","progress_log")} for p,r in runs.items()}
        record={"coverage":"Real CLI/MCP/Squad transport only; synthetic task; no native input, GUI or approval acceptance",
                "passed":verdict,"runs":compact,"events":service.job["events"],"history":service.squad.history(),"broker_audit":broker.audit}
        (destination/"transport-result.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"directory":str(destination),"passed":verdict,"statuses":{p:r["status"] for p,r in runs.items()}},ensure_ascii=False))
        return 0 if verdict else 1
    finally:service.stop();broker.close()


if __name__=="__main__":raise SystemExit(main())
