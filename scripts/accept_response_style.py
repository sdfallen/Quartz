"""Read-only live chat/Squad acceptance in a new disposable project.

No production conversation, model setting, user save or desktop input is used.
Full agent output and real Squad messages remain in the fixture evidence.
"""
import json
from pathlib import Path
import sys
import time
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.agent_chat import AgentChatService
from core.multi_agent_service import MultiAgentService
from core.squad_adapter import SquadAdapter


def main():
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    evidence = ROOT / "labs" / "chat-style-20261021" / time.strftime("%Y%m%d-%H%M%S")
    workspace = evidence / "workspace"
    workspace.mkdir(parents=True)
    service = MultiAgentService(projects=[{"id":"style-lab", "path":str(workspace), "name":"Style acceptance"}])
    SquadAdapter(workspace).initialize()
    chat = AgentChatService(service, evidence / "conversations.json")
    cases = [
        ("normal-question", "codex", "Quartz masaüstü kontrolü çalışıyor mu? Bağlam: kaynak testleri geçti ama paketli arayüz testi ekran okuma hatası yüzünden henüz doğrulanmadı. Araç kullanma."),
        ("technical-error", "antigravity", "Bir testte ElementFromPoint 0x80070057 hatası aldım. Bu ne demek, ne yapacağız? Bu yalnız örnek hata sorusudur; araç kullanma veya dosya değiştirme."),
        ("full-report", "codex", "Kapsamlı bir rapor istiyorum: görev bazlı masaüstü izni, tek operatör ve odak kaybında durdurmanın faydalarını, risklerini ve kabul testlerini açıkla. Araç kullanma; gerçek test yaptığını iddia etme."),
        ("group-discussion", "collaboration", "Codex ve Antigravity: kısa ve anlaşılır sohbet ile tam test kanıtlarını birlikte nasıl koruruz? Biriniz kısa kullanıcı mesajını, diğeriniz kanıt erişimini değerlendirsin. Birbirinizi tekrarlamadan yeni katkı sunun. Bu bir tartışma; araç veya komut çağırmayın."),
    ]
    results = []
    try:
        for name, agent, prompt in cases:
            selected = [sys.argv[i+1] for i, value in enumerate(sys.argv[:-1]) if value == "--case"]
            if selected and name not in selected: continue
            conv = chat.new_conversation(title=name, agent=agent, project_id="style-lab")
            cid = conv["id"]
            chat.set_agent_model(cid, "codex", "gpt-6-luna", "low")
            chat.set_agent_model(cid, "antigravity", "gemini-3.8-flash-low", "low")
            started = time.time()
            chat.send_message(prompt, agent=agent, conversation_id=cid)
            deadline = time.monotonic() + (300 if agent == "collaboration" else 180)
            while time.monotonic() < deadline:
                current = chat.poll_active()
                if not current.get("active"): break
                time.sleep(.5)
            else:
                chat.cancel_active()
                current = {"status":"cancelled", "reason":"acceptance deadline"}
            full = chat.store.get(cid)
            record = {"case":name, "provider":agent, "seconds":round(time.time()-started,2),
                      "turn_status":current.get("status"), "conversation":full,
                      "style_sha256": hashlib.sha256((ROOT/"core/response_style.py").read_bytes()).hexdigest()}
            results.append(record)
            (evidence / "results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps({"case":name,"status":current.get("status"),
                              "messages":[{"sender":m.get("sender"),"status":m.get("status"),"chars":len(m.get("content", "")),
                                           "squad_connected":m.get("metadata",{}).get("squad_connected")}
                                          for m in full["messages"] if m.get("role")!="user"]},ensure_ascii=False), flush=True)
        print("EVIDENCE", evidence, flush=True)
    finally:
        chat.cancel_active()
        service.shutdown()


if __name__ == "__main__": main()
