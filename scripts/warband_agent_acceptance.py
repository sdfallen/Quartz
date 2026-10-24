"""Real CLI/Squad + UM-owned game smoke. Host grants this explicit test scope.

This tests the source application service, not a human clicking a packaged
inline card. No campaign/save/load, gameplay patch, build, cheat or outcome.
"""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.desktop_agents import DesktopAgentService
from core.natural_desktop import NaturalDesktopTask
from core.warband_workspace import WarbandWorkspace,SAVES,PROJECT,GAME,CONFIG,digest


def main():
    preparation=Path(sys.argv[1]).resolve(strict=True)
    receipt=json.loads(preparation.read_text(encoding="utf-8"))
    before={p.name:digest(p) for p in sorted(SAVES.glob("sg*.sav"))}
    if before!=receipt["save_hashes"]: raise RuntimeError("Preparation save receipt is stale")
    for name,value in receipt["source_hashes"].items():
        if digest(PROJECT/name)!=value: raise RuntimeError("Preparation source receipt is stale: "+name)
    destination=ROOT/"labs"/("warband-agent-"+time.strftime("%Y%m%d-%H%M%S"))
    desktop=DesktopAgentService(); events=[]; holder={}
    def factory(evidence):
        w=WarbandWorkspace(evidence);w.prepared=receipt;holder["workspace"]=w;return w
    def emit(cid,sender,content,metadata):
        events.append({"sender":sender,"content":content,"metadata":metadata})
        print(sender,content[:260],flush=True)
    service=NaturalDesktopTask(desktop,emit,evidence_root=destination,warband_factory=factory)
    prompt=("Codex, bilgisayar kontrolünü al; ASTER Warband test araclarini kullanarak yalniz guvenli ana-menu smoke testi yap. "
        "Gemini, AGENTS.md ve CONTINUATION_NOTE.md kaynaklarini ve RGL kanitlarini incele, Squad ile raporla. "
        "Host daha once gercek UM source/module/save hazirligini tamamladi; warband_status prepared=true ve hashler yeniden dogrulandi. "
        "inspect ve play izni iste, prepare'i gereksiz tekrarlama. warband_run preflight tamamlaninca launch baslat. "
        "task_wait ve warband_status ile arka-plan sonucu bekle. Tamamlaninca warband_observe focus=true ile GERCEK resmi oku. "
        "Resim Native launcher ise ve launcher.can_start=true ise warband_start_game ile bir kez Play yap. Play custom-rendered ise GERCEK resimdeki 'Mount&Blade Oyna' merkezinin x,y client piksellerini ver; tahmin veya module combobox tiklamasi yok. "
        "Play sonrasi pencere degisimi/yukleme beklenir: task_wait ile 20 saniye bekle, sonra warband_observe. game_loading yaniti gelirse remaining_seconds bitene kadar task_wait ve observe ile bekle; gecici pencere yoklugunda hemen close yapma. "
        "Module kesin AI_Island_Test ise ve resim ana menuyse, Escape'e bir kez normal warband_act girdisi gonder, "
        "taze resmi incele; bir cikis onay diyaloğu acildiysa Escape ile iptal edip tekrar gozlemle. "
        "Kampanya, karakter olusturma, save/load, multiplayer, kaynak duzeltme, derleme veya hile YOK. "
        "Sonra warband_run close ile kendi oyununun normal kapanisini iste; lease_status verified_restored ve "
        "gercek save-preservation kaniti icin status oku. Goruntu gelmezse, Steam oturum ekrani veya yanlis modul varsa "
        "oyun girdisi gonderme; tam engeli raporla ve kendi oyunun icin normal close iste. "
        "SOURCE ve LIVE gozlemi ayri raporla; bu bir Gate B kabul testi degildir.")
    if "--campaign-readonly" in sys.argv[2:]:
        prompt=("Codex, bilgisayar kontrolünü al; ASTER / AI_Island_Test salt-okunur kampanya yukleme testini yap. "
            "Gemini, AGENTS.md ve CONTINUATION_NOTE.md ile gercek RGL/status kanitlarini incele ve Squad ile kisa raporla. "
            "UM source/module/save hazirligi host tarafindan tamamlandi, hashler taze kontrol edildi; prepared=true, prepare'i tekrarlama. "
            "inspect+play izni iste. preflight tamamlaninca launch, task_wait/status ile sonucu bekle. warband_observe focus=true ile GERCEK resmi oku. "
            "Native launcher AI_Island_Test secimini kontrol ile dogruluyorsa warband_start_game kullan. Play custom-rendered ise gercek resimden Mount&Blade Oyna merkez x,y ver. "
            "Pencere degisimi/yukleme icin task_wait ve observe kullan; game_loading surerken erken close yapma. "
            "Ana menu geldikten sonra Kayıtlı Oyunlar secenegini gercek resimde gorup tikla; listeyi gozlemle ve mevcut bir kaydi salt okunur yukle. "
            "Tercih SG07 (sg00'dan sayilan sekizinci slot); siralama kesin degilse secilen gorunen kayit adini/durumunu raporla, SG07 oldugunu uydurma. "
            "save_guard_active=true olmali. Kampanya gelince hareket veya unpause yapmadan resmi ve RGL'yi oku; aciksa Space ile normal pause yapabilirsin. "
            "Sonra Escape ile menuyu ac, GERCEK 'Kaydetmeden Çık' secenegini kullanip ana menuye don. Yalniz bu var olan kaydi READ-ONLY yuklemeye izin var. "
            "Save, Kaydet, Kaydet ve Çık, QuickSave, yeni oyun, multiplayer, kaynak degisikligi, build ve hile YASAK. "
            "Sonunda warband_run close, status ile verified_restored ve nine-save hash kanitini kontrol et. "
            "FG/user takeover olursa girdiyi durdur; sonucta gercek resimleri ve secilen slot belirsizligini kisa raporla. Bu Gate B mekanik kabul testi degildir.")
    models={"codex":{"model":"gpt-6-luna","effort":"low"},"antigravity":{"model":"gemini-3.8-flash-low","effort":"low"}}
    try:
        service.start(prompt,{"id":"aster-warband","path":str(PROJECT),"workflow":"warband","protected":True},"warband-smoke",models)
        until=time.monotonic()+480
        approved=set()
        play_approved=False
        while service.status()["active"] and time.monotonic()<until:
            pending=service.status().get("pending")
            if pending and pending["id"] not in approved:
                if pending.get("kind")!="warband" or not set(pending["capabilities"])<={"inspect","play"}:
                    service.deny(pending["id"]);raise RuntimeError("Test requested an unexpected scope")
                if play_approved and "play" in pending["capabilities"]:
                    service.deny(pending["id"]);raise RuntimeError("Input was revoked; the harness will not override a user takeover")
                service.approve(pending["id"],confirmed=True);approved.add(pending["id"])
                play_approved=play_approved or "play" in pending["capabilities"]
            time.sleep(.5)
        state=service.status()
        report={"level":"REAL source-service CLI/Squad/UM; not packaged main-chat card", "events":events,"state":state,
                "runs":{p:r.get(rid) for p,(r,rid) in service.runs.items()},"saves_before":before}
        w=holder["workspace"]
        report["game_observations"]=len(list(w.evidence.glob("game-*.png")))
        report["actual_game_actions"]=len(w.audit)
        report["saves_after"]={p.name:digest(p) for p in sorted(SAVES.glob("sg*.sav"))}
        report["save_diff0"]=report["saves_after"]==before
        (w.evidence/"agent-acceptance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"evidence":str(w.evidence),"observations":report["game_observations"],"actions":report["actual_game_actions"],"save_diff0":report["save_diff0"]}),flush=True)
    finally:
        # Only the exact game launched by this test. Normal WM_CLOSE only;
        # preserve a nonclosing game/watcher and report it rather than kill.
        w=holder.get("workspace")
        if w and w.owned:
            import psutil
            try:
                p=psutil.Process(w.owned["pid"])
                if p.create_time()==w.owned["started"] and p.exe()==w.owned["exe"]:
                    backend=desktop.broker.backend
                    windows=[v for v in backend.controller.windows()["windows"] if v["process_id"]==p.pid]
                    if len(windows)==1:
                        u=ctypes.windll.user32;u.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
                        u.PostMessageW(windows[0]["handle"],0x0010,0,0)
            except psutil.NoSuchProcess: pass
        service.stop("test ended");desktop.close()
        if w:
            for _ in range(40):
                status=w.context()
                if (status.get("lease_status") or {}).get("verified_restored"): break
                time.sleep(.5)
            (w.evidence/"closing-state.json").write_text(json.dumps({"status":w.context(),"save_diff0":before=={p.name:digest(p) for p in SAVES.glob("sg*.sav")}},indent=2),encoding="utf-8")

if __name__=="__main__":main()
