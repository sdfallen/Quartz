"""Live agent activity line and typing reveal (user request, 7 Nov 2026)."""
import subprocess
import unittest

import gui

SOURCE = "//" + gui._HTML.split("  // Typing reveal for agent text", 1)[1].split("  function renderMessageBody(", 1)[0]
PROGRESS = gui._HTML.split("  function agentProgressText(", 1)[1].split("  async function loadActiveConversation()", 1)[0]

FAKE_DOM = r'''
const assert=require('node:assert/strict');
class El{constructor(tag){this.tag=tag;this.children=[];this.parentNode=null;this.dataset={};this.attrs={};this._text='';this.className='';
  this.classList={_s:new Set(),add:(c)=>this.classList._s.add(c),remove:(c)=>this.classList._s.delete(c),contains:(c)=>this.classList._s.has(c),toggle:(c,on)=>on?this.classList._s.add(c):this.classList._s.delete(c)};}
 get textContent(){return this._text+this.children.map(c=>c.textContent).join('');} set textContent(v){this._text=String(v);this.children=[];}
 setAttribute(k,v){this.attrs[k]=v} append(...c){for(const x of c){x.parentNode=this;this.children.push(x);}}
 after(x){const p=this.parentNode;x.parentNode=p;p.children.splice(p.children.indexOf(this)+1,0,x);}
 replaceWith(x){const p=this.parentNode;x.parentNode=p;p.children[p.children.indexOf(this)]=x;}
 replaceChildren(...c){this.children=[];this.append(...c);} remove(){if(this.parentNode){const k=this.parentNode.children;k.splice(k.indexOf(this),1);this.parentNode=null;}}
 querySelector(sel){return this.querySelectorAll(sel)[0]||null;}
 querySelectorAll(sel){const out=[];const scoped=sel.startsWith(':scope > ');const s=sel.replace(':scope > ','');
  const hit=c=>s.startsWith('.')?(c.className||'').split(' ').includes(s.slice(1)):c.tag===s;
  const walk=n=>{for(const c of n.children){if(hit(c))out.push(c);if(!scoped)walk(c);}};walk(this);return out;}}
const document={body:new El('body'),createElement:t=>new El(t)};
'''


def _node(code):
    return subprocess.run(["node", "-e", code], capture_output=True, text=True, encoding="utf-8", timeout=20)


class LiveActivityTests(unittest.TestCase):
    def run_js(self, checks):
        harness = FAKE_DOM + r'''
const bubbles={};
const chatEl={querySelector:(sel)=>{const id=(sel.match(/data-msg-id="([^"]+)"/)||[])[1];return bubbles[id]||null;},
  querySelectorAll:(sel)=>Object.values(bubbles).flatMap(b=>b.parentNode.querySelectorAll('.agent-live'))};
function bubbleFor(id){const wrap=new El('div');const b=new El('div');b.className='bubble';wrap.append(b);bubbles[id]=b;return b;}
let userPinnedToBottom=false;function scrollToBottom(){}
'''
        result = _node(harness + SOURCE + checks)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_activity_card_follows_the_running_agent_and_disappears_when_done(self):
        self.run_js(r'''
const b=bubbleFor('m1');
renderAgentLive({antigravity:{message_id:'m1',status:'running',activity:'Dosya okuyor: app.py',activity_trail:['Düşünüyor…','Dosya okuyor: app.py']}});
const live=b.parentNode.querySelector('.agent-live');
assert.ok(live);assert.equal(live.dataset.agent,'antigravity');
assert.equal(live.querySelector('.agent-live-now').children[1].textContent,'Dosya okuyor: app.py');
assert.deepEqual(live.querySelector('.agent-live-trail').children.map(c=>c.textContent),['Düşünüyor…']);
renderAgentLive({antigravity:{message_id:'m1',status:'running',activity:'Kodda arıyor: x',activity_trail:['Düşünüyor…','Dosya okuyor: app.py','Kodda arıyor: x']}});
assert.equal(b.parentNode.querySelectorAll('.agent-live').length,1);
assert.equal(live.querySelector('.agent-live-now').children[1].textContent,'Kodda arıyor: x');
renderAgentLive({antigravity:{message_id:'m1',status:'completed',activity:'Kodda arıyor: x'}});
assert.equal(b.parentNode.querySelectorAll('.agent-live').length,0);
''')

    def test_unknown_agents_bad_ids_and_missing_activity_show_nothing(self):
        self.run_js(r'''
const b=bubbleFor('m2');
renderAgentLive({notion:{message_id:'m2',status:'running',activity:'x'},codex:{message_id:'m2"] .x',status:'running',activity:'x'},antigravity:{message_id:'m2',status:'running'}});
assert.equal(b.parentNode.querySelectorAll('.agent-live').length,0);
renderAgentLive(null);
''')

    def test_reveal_never_animates_history_or_reduced_motion(self):
        self.run_js(r'''
document.createTreeWalker=()=>({nextNode:()=>null});
revealMessage(new El('div'),new El('div'),'h1');  // not armed yet: history is shown at once
assert.equal(revealedLength.get('h1'),0);
liveRevealArmed=true;global.window={matchMedia:()=>({matches:true})};
revealMessage(new El('div'),new El('div'),'h2');
assert.equal(revealedLength.get('h2'),0);
''')

    def test_status_line_prefers_the_live_activity(self):
        result = _node("function agentProgressText(" + PROGRESS + r'''
const assert=require('node:assert/strict');
assert.equal(agentProgressText({codex:{status:'running',activity:'Komut çalıştırıyor: ls',step:'CODEX yanıtlıyor'}}),'Codex: çalışıyor — Komut çalıştırıyor: ls');
assert.equal(agentProgressText({codex:{status:'running',step:'CODEX yanıtlıyor'}}),'Codex: çalışıyor — CODEX yanıtlıyor');
''')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
