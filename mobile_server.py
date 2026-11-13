"""Authenticated mobile gateway, exposed only through Tailscale Serve.

Serves the small web page and the JSON API that the SpeS Android app uses:
team state with long polling, read-only messages and Stop. The device key
travels only in the Authorization header, never in a URL. Work started from
the phone is always read-only; writing to a project still needs the desktop.
"""

import json
import secrets
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import BASE_DIR
from core.atomic_json import atomic_write_json, load_json
from logger import get_logger

log = get_logger(__name__)
MOBILE_PORT = 8765
MAX_MESSAGES = 40
PAIR_TTL = 300          # a pairing code lives five minutes
PAIR_MAX_FAILURES = 5  # and dies after five wrong guesses
PERSONA = {"claude": "Fatum", "codex": "Fides", "antigravity": "Eos", "gemini": "Eos"}
ACCESS_FILE = Path(BASE_DIR) / "mobile_access.json"


_HTML = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#030608"><title>SpeS Mobile</title>
<style>
:root{--cyan:#34eaff;--text:#eaf6ff;--dim:#6d8ea3;--glass:rgba(12,27,37,.78)}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 50% -10%,#0b1a24,#020405 62%);color:var(--text);font:14px Inter,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:2;display:flex;align-items:center;gap:10px;padding:14px 16px;background:rgba(3,8,12,.88);border-bottom:1px solid rgba(52,234,255,.14);backdrop-filter:blur(16px)}
.orb{width:23px;height:23px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#8ff6ff,#17b7d6 48%,#063a47);box-shadow:0 0 18px rgba(52,234,255,.55)}
.brand{font-weight:750;letter-spacing:.18em}.status{margin-left:auto;color:var(--dim);font-size:11px}.status.on{color:#34ffc0}
main{max-width:720px;margin:auto;padding:13px 13px 104px}.card{background:var(--glass);border:1px solid rgba(52,234,255,.12);border-radius:15px;padding:13px;margin-bottom:11px;backdrop-filter:blur(14px)}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.metric{text-align:center}.metric b{display:block;color:var(--cyan);font-size:16px}.metric span{color:var(--dim);font-size:10px}
#chat{display:flex;flex-direction:column;gap:9px;min-height:48vh}.msg{max-width:88%;padding:10px 12px;border-radius:13px;white-space:pre-wrap;line-height:1.45}.user{align-self:flex-end;background:rgba(52,234,255,.11);border:1px solid rgba(52,234,255,.2)}.bot{align-self:flex-start;background:rgba(20,38,50,.65);border-left:2px solid var(--cyan)}
.confirm{border:1px solid rgba(255,180,84,.5);background:rgba(70,45,12,.5)}button{border:0;border-radius:10px;padding:10px 13px;background:var(--cyan);color:#032028;font-weight:700}.danger{background:#ff5c72}.row{display:flex;gap:8px;margin-top:9px}
.composer{position:fixed;left:0;right:0;bottom:0;padding:10px max(12px,env(safe-area-inset-right)) calc(10px + env(safe-area-inset-bottom));background:rgba(3,8,12,.94);border-top:1px solid rgba(52,234,255,.14)}.composer>div{max-width:720px;margin:auto;display:flex;gap:8px}input{flex:1;min-width:0;border:1px solid rgba(52,234,255,.18);border-radius:22px;background:#0b171f;color:var(--text);padding:12px 15px;outline:none}
#login{position:fixed;inset:0;z-index:9;display:flex;align-items:center;padding:22px;background:#020405}#login .card{width:min(420px,100%);margin:auto}label{display:block;color:var(--dim);font-size:11px;margin:12px 0 6px}#login input{width:100%}.hidden{display:none!important}.error{color:#ffc2ca;font-size:11px;margin-top:8px}
</style></head><body>
<div id="login"><div class="card"><div class="brand">SpeS MOBİL</div><p style="color:var(--dim)">Bilgisayarındaki SpeS cihaz anahtarını gir.</p><label>CİHAZ ANAHTARI</label><input id="token" type="password" autocomplete="off"><button id="connect" type="button" style="width:100%;margin-top:12px">BAĞLAN</button><div id="loginError" class="error"></div></div></div>
<header><div class="orb"></div><div class="brand">SpeS</div><div id="status" class="status">BAĞLANIYOR</div></header>
<main><div class="card metrics"><div class="metric"><b id="provider">—</b><span>MODEL</span></div><div class="metric"><b id="safe">—</b><span>GÜVENLİ MOD</span></div><div class="metric"><b id="tasks">—</b><span>GÖREV</span></div></div><div id="chat"></div></main>
<div class="composer"><div><input id="message" placeholder="SpeS'e bir şey söyle..."><button id="send">➤</button></div></div>
<script>
let key=localStorage.getItem('quartz_mobile_token')||'',refreshTimer=null;const $=id=>document.getElementById(id);
if(location.search)history.replaceState({},'',location.pathname);
async function api(path,options={}){const headers={'Authorization':'Bearer '+key,'Content-Type':'application/json',...(options.headers||{})};const r=await fetch('/api/'+path,{...options,headers,cache:'no-store'});let data={};try{data=await r.json()}catch(_e){}if(r.status===401){$('login').classList.remove('hidden');throw Error('Cihaz anahtarı geçersiz')}if(!r.ok)throw Error(data.error||'İstek başarısız');return data}
function msg(text,kind='bot'){const d=document.createElement('div');d.className='msg '+kind;d.textContent=text;$('chat').appendChild(d);scrollTo(0,document.body.scrollHeight)}
function events(items=[]){for(const e of items){if(e.type==='confirmation'){const d=document.createElement('div');d.className='card confirm';d.textContent='Onay gerekli: '+(e.tools||[e.tool]).join(', ');const row=document.createElement('div');row.className='row';const yes=document.createElement('button');yes.textContent='Onayla';yes.onclick=()=>sendText('onayla '+e.code);const no=document.createElement('button');no.className='danger';no.textContent='İptal';no.onclick=()=>sendText('iptal');row.append(yes,no);d.append(row);$('chat').append(d)}else if(e.type==='screen_advice')msg('Ekran Rehberi: '+e.text)}}
async function refresh(){clearTimeout(refreshTimer);try{const h=await api('health');$('login').classList.add('hidden');$('loginError').textContent='';$('status').textContent='ÇEVRİMİÇİ';$('status').className='status on';const components=h.components||{};const llm=components.llm||{};$('provider').textContent=String(llm.provider||'—').toUpperCase();$('safe').textContent=components.safe_mode?'AÇIK':'KAPALI';try{const t=await api('tasks');$('tasks').textContent=Array.isArray(t)?t.length:'—'}catch(_e){$('tasks').textContent='—'}}catch(e){$('status').textContent='ÇEVRİMDIŞI';$('status').className='status';throw e}finally{refreshTimer=setTimeout(()=>refresh().catch(()=>{}),5000)}}
async function connect(){const button=$('connect');const candidate=$('token').value.trim();$('loginError').textContent='';if(!candidate){$('loginError').textContent='Cihaz anahtarını gir.';return}key=candidate;button.disabled=true;button.textContent='BAĞLANIYOR…';try{await api('health');localStorage.setItem('quartz_mobile_token',key);await refresh()}catch(e){localStorage.removeItem('quartz_mobile_token');$('loginError').textContent=e.message||'Bağlantı kurulamadı'}finally{button.disabled=false;button.textContent='BAĞLAN'}}
async function sendText(text){if(!text)return;msg(text,'user');$('message').value='';$('send').disabled=true;try{const r=await api('chat',{method:'POST',body:JSON.stringify({message:text})});events(r.ui_events);msg(r.data)}catch(e){msg(e.message,'bot')}finally{$('send').disabled=false}}
$('send').onclick=()=>sendText($('message').value.trim());$('message').onkeydown=e=>{if(e.key==='Enter')$('send').click()};$('connect').onclick=connect;$('token').onkeydown=e=>{if(e.key==='Enter')connect()};
if(key){$('token').value=key;refresh().catch(e=>{$('loginError').textContent=e.message})}else $('login').classList.remove('hidden');
</script></body></html>"""


class MobileGateway:
    def __init__(self, assistant, host="127.0.0.1", port=MOBILE_PORT, agent_chat=None):
        self.assistant = assistant
        # Callable returning the AgentChat service (the team conversation), or None.
        self._agent_chat = agent_chat
        self._pair = None  # [code, expires_at, failures]; one at a time, single use
        self._pair_lock = threading.Lock()
        self.host, self.port = host, port
        self._server = None
        self._attempts = defaultdict(deque)
        saved = load_json(ACCESS_FILE, {})
        self.token = str(saved.get("token", "")) if isinstance(saved, dict) else ""
        if len(self.token) < 32:
            self.token = secrets.token_urlsafe(32)
            atomic_write_json(ACCESS_FILE, {"token": self.token, "created_at": time.time()})

    # -- team API for the Android app ------------------------------------
    def _chat(self):
        chat = self._agent_chat() if callable(self._agent_chat) else None
        if chat is None:
            raise LookupError("Ekip sohbeti henüz hazır değil")
        return chat

    def snapshot(self, after=0):
        """Active conversation, busy flag and the messages newer than ``after`` (a sequence number)."""
        chat = self._chat()
        conv = chat.store.get_active() or {}
        turn = chat.poll_active() or {}
        messages = conv.get("messages") or []
        last_seq = 0
        rows = []
        for index, message in enumerate(messages):
            meta = message.get("metadata") or {}
            seq = int(message.get("sequence") or meta.get("sequence") or index + 1)
            last_seq = max(last_seq, seq)
            if after > 0 and seq <= after:
                continue
            sender = str(meta.get("sender") or message.get("sender") or message.get("role") or "")
            outcome = meta.get("outcome") or {}
            rows.append({
                "id": message.get("id"), "seq": seq, "role": message.get("role"), "sender": sender,
                "persona": PERSONA.get(sender.lower(), "SpeS" if sender.lower() in {"quartz", "bot", "assistant"} else ""),
                "step": meta.get("team_step"), "text": str(message.get("content") or "")[:4000],
                "failed": meta.get("status") == "failed" or bool(meta.get("error")) or outcome.get("goal_verdict") == "FAILED",
            })
        if after <= 0:
            rows = rows[-MAX_MESSAGES:]
        return {"conversation": {"id": conv.get("id"), "title": conv.get("title") or "Sohbet"},
                "busy": bool(turn.get("active")), "status": turn.get("status") or "idle",
                "progress": str((turn.get("metadata") or {}).get("progress_step") or ""),
                "last_seq": last_seq, "messages": rows}

    def wait_snapshot(self, after=0, wait=0.0):
        """Long poll: return as soon as a newer message arrives or the busy flag changes."""
        first = self.snapshot(after)
        deadline = time.time() + max(0.0, min(float(wait), 25.0))
        while time.time() < deadline and not first["messages"]:
            time.sleep(.8)
            current = self.snapshot(after)
            if current["messages"] or current["busy"] != first["busy"]:
                return current
        return first

    def send(self, message, conversation_id=None):
        # Read-only by construction: no write flag is ever passed on the phone path.
        result = self._chat().send_message(message, conversation_id=conversation_id or None)
        return {"conversation_id": (result or {}).get("conversation_id"), "accepted": True}

    def stop_work(self):
        return self._chat().cancel_active()

    def pairing_code(self):
        """Current six-digit pairing code; a new one once the old is used or expired."""
        with self._pair_lock:
            if not self._pair or self._pair[1] <= time.time():
                self._pair = [f"{secrets.randbelow(10 ** 6):06d}", time.time() + PAIR_TTL, 0]
            return self._pair[0], max(0, int(self._pair[1] - time.time()))

    def redeem_pairing(self, code):
        """Trade a valid pairing code for the device key exactly once."""
        code = str(code or "").strip()
        with self._pair_lock:
            if not self._pair or self._pair[1] <= time.time():
                self._pair = None
                return None
            if len(code) == 6 and secrets.compare_digest(code, self._pair[0]):
                self._pair = None
                return self.token
            self._pair[2] += 1
            if self._pair[2] >= PAIR_MAX_FAILURES:
                self._pair = None
            return None

    def access_info(self):
        code, expires_in = self.pairing_code()
        return {"local_url": f"http://{self.host}:{self.port}", "token": self.token,
                "pairing_code": code, "pairing_expires_in": expires_in,
                "tailscale_command": f"tailscale serve --bg http://127.0.0.1:{self.port}"}

    def start(self):
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "SpeSMobile/2"
            def log_message(self, _format, *_args):
                return
            def _json(self, status, value):
                raw = json.dumps(value, ensure_ascii=False).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(raw)
            def _authorized(self):
                address = self.client_address[0]; now = time.time(); attempts = gateway._attempts[address]
                while attempts and attempts[0] < now - 60: attempts.popleft()
                supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
                valid = secrets.compare_digest(supplied, gateway.token)
                if not valid: attempts.append(now)
                return valid and len(attempts) < 12
            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/":
                    raw = _HTML.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(raw); return
                if not self._authorized(): self._json(401, {"error": "Yetkisiz erişim"}); return
                if path == "/api/health": self._json(200, {"components": gateway.assistant.health_status()}); return
                if path == "/api/tasks": self._json(200, gateway.assistant.list_tasks()); return
                if path == "/api/ping": self._json(200, {"app": "SpeS", "api": 2}); return
                if path == "/api/state":
                    query = parse_qs(urlparse(self.path).query)
                    try:
                        after = int((query.get("after") or ["0"])[0]); wait = float((query.get("wait") or ["0"])[0])
                        self._json(200, gateway.wait_snapshot(after, wait))
                    except ValueError: self._json(400, {"error": "Geçersiz sorgu"})
                    except LookupError as exc: self._json(503, {"error": str(exc)})
                    except Exception: log.exception("Mobile state failed"); self._json(500, {"error": "Durum okunamadı"})
                    return
                self._json(404, {"error": "Bulunamadı"})
            def do_POST(self):
                if urlparse(self.path).path == "/api/pair":
                    address = self.client_address[0]; now = time.time(); attempts = gateway._attempts[address]
                    while attempts and attempts[0] < now - 60: attempts.popleft()
                    if len(attempts) >= 12: self._json(429, {"error": "Çok fazla deneme; bir dakika bekleyin"}); return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if length < 1 or length > 1024: raise ValueError
                        token = gateway.redeem_pairing(json.loads(self.rfile.read(length)).get("code"))
                    except (ValueError, AttributeError): token = None
                    if not token:
                        attempts.append(now); self._json(403, {"error": "Kod geçersiz veya süresi doldu"}); return
                    self._json(200, {"token": token, "app": "SpeS", "api": 2}); return
                if not self._authorized(): self._json(401, {"error": "Yetkisiz erişim"}); return
                path = urlparse(self.path).path
                if path == "/api/stop":
                    try: self._json(200, {"data": gateway.stop_work()})
                    except LookupError as exc: self._json(503, {"error": str(exc)})
                    except Exception: log.exception("Mobile stop failed"); self._json(500, {"error": "Durdurma iletilemedi"})
                    return
                if path == "/api/send":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if length < 1 or length > 65536: raise ValueError("Geçersiz istek boyutu")
                        body = json.loads(self.rfile.read(length))
                        message = str(body.get("message", "")).strip()
                        if not message: raise ValueError("Mesaj boş")
                        self._json(200, gateway.send(message, body.get("conversation_id")))
                    except ValueError as exc: self._json(400, {"error": str(exc)})
                    except PermissionError as exc: self._json(403, {"error": str(exc)})
                    except LookupError as exc: self._json(503, {"error": str(exc)})
                    except RuntimeError as exc: self._json(409, {"error": str(exc)})
                    except Exception: log.exception("Mobile send failed"); self._json(500, {"error": "Mesaj iletilemedi"})
                    return
                if path != "/api/chat": self._json(404, {"error": "Bulunamadı"}); return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 1 or length > 65536: raise ValueError("Geçersiz istek boyutu")
                    message = str(json.loads(self.rfile.read(length)).get("message", "")).strip()
                    if not message: raise ValueError("Mesaj boş")
                    answer = gateway.assistant.chat(message)
                    self._json(200, {"data": answer, "ui_events": gateway.assistant.drain_ui_events()})
                except ValueError as exc: self._json(400, {"error": str(exc)})
                except Exception: log.exception("Mobile request failed"); self._json(500, {"error": "SpeS isteği tamamlayamadı"})

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        log.info("Mobile gateway listening locally on %s:%d", self.host, self.port)
        self._server.serve_forever(poll_interval=.5)

    def stop(self):
        if self._server:
            try:
                self._server.shutdown()
            finally:
                try:
                    self._server.server_close()
                except Exception:
                    pass
