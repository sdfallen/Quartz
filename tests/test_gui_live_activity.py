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

    def test_reveal_finishes_without_animation_frames_and_at_once_when_hidden(self):
        # Live 7 Nov: frames never came in a covered pane, so the text stayed hidden.
        self.run_js(r'''
global.requestAnimationFrame=()=>{throw new Error('frames are not available');};
global.window={matchMedia:()=>({matches:false})};
function textBody(text){const parent={insertBefore(){}};const node={nodeValue:text,parentNode:parent};
  const body=new El('div');body.isConnected=true;body.querySelectorAll=()=>[];body._node=node;return body;}
document.createTreeWalker=(body)=>{let done=false;return {nextNode:()=>{if(done)return null;done=true;return body._node;}};};
liveRevealArmed=true;
const visible=textBody('x'.repeat(300));revealMessage(new El('div'),visible,'v1');
assert.equal(visible._node.nodeValue,'');            // Starts empty, then types out.
setTimeout(()=>{const n=visible._node.nodeValue.length;assert.ok(n>0&&n<300,String(n));},500);
setTimeout(()=>{assert.equal(visible._node.nodeValue,'x'.repeat(300));assert.equal(revealedLength.get('v1'),300);
  document.hidden=true;
  const covered=textBody('gizli pencere metni '.repeat(20));revealMessage(new El('div'),covered,'v2');
  setTimeout(()=>assert.equal(covered._node.nodeValue,'gizli pencere metni '.repeat(20)),60);},2600);
''')

    def test_status_line_prefers_the_live_activity(self):
        result = _node("function agentProgressText(" + PROGRESS + r'''
const assert=require('node:assert/strict');
assert.equal(agentProgressText({codex:{status:'running',activity:'Komut çalıştırıyor: ls',step:'CODEX yanıtlıyor'}}),'Codex: çalışıyor — Komut çalıştırıyor: ls');
assert.equal(agentProgressText({codex:{status:'running',step:'CODEX yanıtlıyor'}}),'Codex: çalışıyor — CODEX yanıtlıyor');
''')
        self.assertEqual(result.returncode, 0, result.stderr)


CREW = "//" + gui._HTML.split("  // Crew band:", 1)[1].split("  if (btnContinueCollab) {", 1)[0]


class CrewBandTests(unittest.TestCase):
    def run_js(self, checks):
        harness = r'''
const assert=require('node:assert/strict');
const els={};
function el(id){const e={id,dataset:{},attrs:{},textContent:'',disabled:false,listeners:{},
  setAttribute(k,v){this.attrs[k]=String(v)},getAttribute(k){return this.attrs[k]},
  addEventListener(t,f){this.listeners[t]=f},click(){this.listeners.click&&this.listeners.click({currentTarget:this})}};els[id]=e;return e;}
['crew','laneCodex','laneCodexState','laneColCodex','laneAgy','laneAgyState','laneColAgy','crewCore','crewCoreLabel'].forEach(id=>el(id));
for(const id of ['laneCodexTrail','laneAgyTrail']){const t=el(id);t.children=[];t.replaceChildren=(...c)=>{t.children=c};t.closest=()=>({classList:{toggle(){}}});}els.laneCodex.dataset.agent='codex';els.laneAgy.dataset.agent='antigravity';els.crewCore.dataset.agent='collaboration';
const seg={};for(const a of ['codex','antigravity','collaboration'])seg[a]={disabled:false,clicks:0,_active:a==='antigravity',
  classList:{contains(c){return c==='active'&&seg[a]._active}},click(){this.clicks++;for(const b of Object.values(seg))b._active=false;this._active=true;}};
const stage={attrs:{},setAttribute(k,v){this.attrs[k]=v}};
const bodyClasses=new Set();
global.document={body:{classList:{contains:c=>bodyClasses.has(c)}},getElementById:id=>els[id]||null,
  createElement:t=>({tag:t,textContent:'',className:''}),
  querySelector:s=>{const m=s.match(/data-agent="(\w+)"/);if(m)return seg[m[1]]||null;if(s==='.chat-stage')return stage;return null;}};
const codexModelSelect={selectedOptions:[{textContent:'GPT-6.1-Sol'}],addEventListener(){}};
const agyModelSelect={selectedOptions:[{textContent:'Gemini 3.8 Flash (High)'}],addEventListener(){}};
let currentConvId='c1';
'''
        result = _node(harness + CREW + checks)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_lanes_follow_the_picker_and_show_models(self):
        self.run_js(r'''
assert.equal(els.crew.dataset.focus,'antigravity');
assert.equal(els.laneAgy.attrs['aria-pressed'],'true');assert.equal(els.laneCodex.attrs['aria-pressed'],'false');
assert.equal(els.laneCodex.dataset.included,'false');
assert.equal(els.laneColCodex.dataset.included,'false');
// Idle, the crystal names the selected mode instead of always saying "Birlikte" (live exam 9 Nov).
assert.equal(els.crewCoreLabel.textContent,'Yalnız Antigravity');assert.equal(els.crewCoreLabel.lang,'en');
assert.match(els.crewCore.attrs.title,/^Birlikte moduna geç/);
els.crewCore.click();
assert.equal(seg.collaboration.clicks,1);assert.equal(els.crew.dataset.focus,'collaboration');
assert.equal(els.crewCoreLabel.textContent,'Birlikte');assert.equal(els.crewCoreLabel.lang,'tr');assert.match(els.crewCore.attrs.title,/^Birlikte: /);
assert.equal(els.crewCore.attrs['aria-pressed'],'true');assert.equal(els.laneCodex.dataset.included,'true');
seg.codex.disabled=true;renderCrew();
assert.equal(els.laneCodex.disabled,true);assert.equal(els.laneCodexState.textContent,'Bağlı değil');
els.laneCodex.click();assert.equal(seg.codex.clicks,0);  // A disconnected agent is never chosen.
''')

    def test_working_agent_lights_its_lane_and_rail_and_clears_when_done(self):
        self.run_js(r'''
setCrewProgress({codex:{status:'running',activity:'Dosya okuyor: app.py'},notion:{status:'running',activity:'x'}});
assert.equal(els.laneCodex.dataset.state,'working');assert.equal(els.laneCodexState.textContent,'Dosya okuyor: app.py');
assert.equal(els.crew.dataset.flow,'codex');assert.equal(stage.attrs['data-flow'],'codex');
assert.equal(els.crewCoreLabel.textContent,'Yönlendiriyor');
setCrewProgress({codex:{status:'running',activity:'Komut çalıştırıyor: ls',activity_trail:['Düşünüyor…','Dosya okuyor: app.py','Komut çalıştırıyor: ls']}});
assert.deepEqual(els.laneCodexTrail.children.map(c=>c.textContent),['Düşünüyor…','Dosya okuyor: app.py','Komut çalıştırıyor: ls']);
assert.equal(els.laneCodexTrail.children[2].className,'now');assert.equal(els.laneColCodex.dataset.state,'working');
setCrewProgress(null);
assert.equal(els.laneCodexTrail.children.length,3);  // The last run's steps stay visible...
assert.equal(els.laneCodexTrail.children[2].className,'');  // ...but nothing is marked as happening now.
currentConvId='c2';renderCrew();
assert.equal(els.laneCodexTrail.children.length,0);  // another conversation starts with empty columns
assert.equal(els.laneCodex.dataset.state,'idle');assert.equal(els.crew.dataset.flow,'');assert.equal(els.crewCoreLabel.textContent,'Yalnız Antigravity');
''')

    def test_operator_column_shows_task_last_step_and_evidence_from_host_fields(self):
        # GPT UI review 8 Nov: the columns show the live task, last tool call,
        # verification and error instead of an empty placeholder.
        self.run_js(r'''
const node=t=>({tag:t,children:[],dataset:{},attrs:{},textContent:'',className:'',
  setAttribute(k,v){this.attrs[k]=v},append(...c){this.children.push(...c)}});
document.createElement=node;
const text=n=>n.textContent+(n.children||[]).map(text).join('');
for(const id of ['laneCodexStatus','laneAgyStatus']){const b=el(id);b.hidden=true;b.children=[];
  b.replaceChildren=(...c)=>{b.children=c};b.closest=()=>({classList:{toggle(){}}});}
const rows=id=>els[id].children.map(r=>[text(r.children[0]),text(r.children[1])]);
setCrewDesktop({active:true,job:{conversation_id:'c1',roles:{operator:'codex'},scope:'Hesap makinesinde 12x4',
  last_step:{tool:'desktop_act'},verification:{status:'NOT VERIFIED'},error:'Pencere kapandı'}});
assert.deepEqual(rows('laneCodexStatus'),[['Görev','Hesap makinesinde 12x4'],['Son adım','Girdi verdi'],
  ['Kanıt','Doğrulanmadı'],['Hata','Pencere kapandı']]);
assert.equal(els.laneCodexStatus.hidden,false);
assert.equal(els.laneAgyStatus.hidden,true);  // the reviewer has no task rows of its own
setCrewDesktop({active:true,job:{conversation_id:'c1',roles:{operator:'codex'},scope:'x',
  verification:{status:'OBSERVED UI CRITERION VERIFIED'}}});
assert.deepEqual(rows('laneCodexStatus'),[['Görev','x'],['Kanıt','Ekranda doğrulandı']]);
// Without a task the column keeps the latest host outcome of that agent's messages.
setCrewDesktop({active:false});
global.agentMessageView=(t,m)=>m.metadata.badge;
setCrewResults([{id:'1',sender:'antigravity',timestamp:1,metadata:{badge:{tone:'warn',label:'Kanıt yok',state:'s'}}},
  {id:'2',sender:'gemini',timestamp:2,metadata:{badge:{tone:'ok',label:'Doğrulandı',state:'s'}}},
  {id:'3',role:'user',sender:'user',timestamp:3,metadata:{badge:{tone:'fail',label:'Başarısız',state:'s'}}}],true);
assert.deepEqual(rows('laneAgyStatus'),[['Son sonuç','Doğrulandı']]);
assert.equal(els.laneCodexStatus.hidden,true);
currentConvId='c2';renderCrew();
assert.equal(els.laneAgyStatus.hidden,true);  // results belong to their own conversation
''')

    def test_desktop_task_marks_operator_and_reviewer_only_for_this_conversation(self):
        self.run_js(r'''
const task={active:true,job:{conversation_id:'c1',roles:{operator:'codex'}}};
bodyClasses.add('screen-control-active');setCrewDesktop(task);
assert.equal(els.laneCodex.dataset.state,'keyboard');assert.equal(els.laneCodexState.textContent,'Klavyede');
assert.equal(els.laneAgy.dataset.state,'review');assert.equal(els.crew.dataset.control,'true');
assert.equal(els.crewCoreLabel.textContent,'Kontrolde');
setCrewProgress({antigravity:{status:'running',activity:'Ekranı inceliyor'}});
assert.equal(els.laneAgyState.textContent,'İnceliyor · Ekranı inceliyor');
setCrewDesktop({...task,job:{...task.job,conversation_id:'other'}});
assert.equal(els.laneCodex.dataset.state,'idle');
setCrewDesktop({active:true,job:{conversation_id:'c1',roles:{operator:'notion'}}});
assert.equal(els.laneCodex.dataset.state,'idle');
''')


if __name__ == "__main__":
    unittest.main()
