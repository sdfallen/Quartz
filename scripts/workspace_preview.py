"""Loopback-only UI preview with synthetic chat data; no native capabilities.

For visual/DOM QA only. It cannot prove real agents or packaged-window behavior.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer as HTTPServer
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from gui import _HTML

MOCK="""<script>
const previewPlan={id:'preview-only',scope:'A ve B test pencerelerinde sonucu kontrol et.',roles:{operator:'codex',observer:'antigravity'}};
const previewWindows=[{handle:1,pid:101,exe:'Fixture-A.exe',title:'Disposable preview A (not connected)'},{handle:2,pid:102,exe:'Fixture-B.exe',title:'Disposable preview B (not connected)'}];
let previewDesktop={code:'normal',label:'Normal sohbet',detail:'PREVIEW ONLY — gerçek masaüstü izni yok.',control_active:false,stop_ref:null,pending_id:null};
const sampleConversation={id:'preview',title:'Quartz çalışma alanı',agent:'collaboration',project_id:'preview-project',models:{codex:{model:'gpt-6-luna',effort:'low'},antigravity:{model:'gemini-3.8-flash-low',effort:'low'}},messages:[
{id:'one',role:'user',sender:'user',content:'Codex test penceresini kontrol etsin; Gemini gerçek logları incelesin.',metadata:{}},
{id:'two',role:'assistant',sender:'quartz',content:'Önce pencere, kapsam ve süre için onay isteyeceğim. Aynı anda yalnız bir ajan klavye ve fareyi kullanabilir.',metadata:{status:'completed'}},
{id:'three',role:'assistant',sender:'codex',content:'Test sonucunu gerçek pencere ve log kanıtıyla değerlendireceğim.\\n\\n---TEKNIK_AYRINTILAR---\\nBu sayfa yalnız görsel test verisidir; gerçek görevi başlatmaz.',metadata:{status:'completed'}}]};
// Synthetic live turn (preview only): activity lines change, then the answer streams in.
let liveTurn=null;
const LIVE_STEPS=['Düşünüyor…','Dosya okuyor: agent_chat.py','Kodda arıyor: describe_activity','Komut çalıştırıyor: python -m unittest tests.test_ag…','Sonucu doğruluyor','Yanıt yazıyor…'];
const LIVE_ANSWER='Bence **önce ölçelim**. Etkinlik satırı Codex ve Gemini\\'nin gerçek olaylarından geliyor; model metni değil.\\n\\n- Komutlar kısaltılıyor, dosya yolunun yalnız son kısmı görünüyor.\\n- Satır yalnız bellekte; kanıt sayılmıyor.\\n\\nAçık soru: bu hız düşük donanımda yeterli mi? `low-spec` modunda animasyon kapanıyor.';
function liveState(){
 if(!liveTurn)return null;
 const e=(Date.now()-liveTurn.t0)/1000, step=Math.min(LIVE_STEPS.length-1,Math.floor(e/1.6));
 const streaming=e>8, done=e>13;
 const content=streaming?LIVE_ANSWER.slice(0,Math.floor((e-8)/4*LIVE_ANSWER.length)):'';
 const msg={id:'live-a',role:'assistant',sender:'antigravity',content:done?LIVE_ANSWER:content,status:done?'completed':'running',metadata:{status:done?'completed':'running',model:'gemini-3.8-flash-high',effort:'high'}};
 return {done,msg,progress:{antigravity:{message_id:'live-a',status:done?'completed':'running',activity:LIVE_STEPS[step],activity_trail:LIVE_STEPS.slice(0,step+1)}}};
}
window.pywebview={api:new Proxy({},{get:(_,name)=>async(...args)=>{
if(name==='chat_send'){liveTurn={t0:Date.now()};sampleConversation.messages.push({id:'live-u',role:'user',sender:'user',content:String(args[0]||''),metadata:{}});
 return {status:'ok',data:{conversation_id:'preview',user_message:{id:'live-u'},assistant_message:{id:'live-a',sender:'antigravity',metadata:{status:'starting'}}}};}
if(name==='chat_poll'){const s=liveState();if(!s)return {status:'ok',data:{active:false,messages:[]}};
 const msgs=sampleConversation.messages.filter(m=>m.id!=='live-a').concat([s.msg]);if(s.done){sampleConversation.messages=msgs;liveTurn=null;}
 return {status:'ok',data:{active:!s.done,messages:msgs,metadata:s.msg.metadata,agent_progress:s.progress,single_writer:{}}};}
if(name==='coordination_route'&&!/erişim|yetki|pencere|masaüstü/i.test(String(args[0]||'')))return {status:'ok',data:{handled:false,intent:'conversation'}};
if(name==='chat_status')return {status:'ok',data:{preferences:{response_detail:'short'},active_conversation:sampleConversation,conversations:[sampleConversation,{id:'older',title:'Önceki test notları'}],projects:[{id:'preview-project',name:'Geçici test projesi',path:'Preview only'}],agents:{},models:{},single_writer:{}}};
if(name==='ping')return {status:'ok',data:'Preview only'};
if(name==='get_stats')return {cpu:0,mem:0,disk:0};
if(name==='ui_events')return {status:'ok',data:[]};
if(name==='desktop_task_status')return {status:'ok',data:previewDesktop};
if(name==='coordination_status')return {status:'ok',data:{active:false}};
if(name==='coordination_prepare'||name==='coordination_route'){
if(name==='coordination_route'&&/erişim|yetki/.test(args[0]))return {status:'ok',data:{handled:true,desktop_help:'PREVIEW: normal sohbet masaüstü izni değildir. Bilgisayar görevi başlat düğmesini kullanın.'}};
previewPlan.scope=args[0];previewDesktop={code:'pending',label:'Onay bekliyor',detail:'PREVIEW ONLY — hiçbir gerçek izin verilmez.',control_active:false,stop_ref:null,pending_id:previewPlan.id};
return {status:'ok',data:{handled:true,plan:previewPlan,windows:previewWindows}};
}
if(name==='coordination_cancel_plan'){previewDesktop={code:'normal',label:'Normal sohbet',detail:'PREVIEW ONLY — istek iptal edildi.',control_active:false,stop_ref:null,pending_id:null};return {status:'ok',data:true};}
if(name==='coordination_pick_log')return {status:'ok',data:'Preview-only/events.log'};
if(name==='coordination_approve')return {status:'error',data:'PREVIEW ONLY: no real desktop permission can be granted.'};
return {status:'ok',data:[]};
}})};
window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));
// #light / #live (headless QA): pick the light theme, or run one live turn without clicks.
window.addEventListener('load',()=>{if(location.hash.includes('light'))setTimeout(()=>{document.documentElement.dataset.theme='light';},300);});
window.addEventListener('load',()=>{if(!location.hash.includes('live'))return;setTimeout(()=>{
 const input=document.getElementById('msgInput');if(!input)return;input.value='Bu etkinlik satırı fikrini değerlendir';
 document.getElementById('btnSend')?.click();},900);});
</script>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!='/': self.send_error(404);return
        import importlib,gui
        body=importlib.reload(gui)._HTML.replace('<head>','<head>'+MOCK).encode('utf-8')
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


if __name__=='__main__':
    print('Preview only http://127.0.0.1:8898',flush=True)
    HTTPServer(('127.0.0.1',8898),Handler).serve_forever()
