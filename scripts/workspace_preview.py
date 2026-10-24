"""Loopback-only UI preview with synthetic chat data; no native capabilities.

For visual/DOM QA only. It cannot prove real agents or packaged-window behavior.
"""
from http.server import BaseHTTPRequestHandler,HTTPServer
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
window.pywebview={api:new Proxy({},{get:(_,name)=>async(...args)=>{
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
