"""Execute the shipped JS loops: syntax checks cannot catch missing globals."""
import json
import subprocess
import unittest

import gui


class ConnectionPollingTests(unittest.TestCase):
    def test_account_login_keeps_polling_until_connected(self):
        source = gui._HTML
        function = source[source.index('  function renderCliStatus(data)'):source.index('  async function refreshCliStatus(')]
        harness = r'''
const assert=require('node:assert/strict');
let cliState=null, cliPollTimer=null; const timers=[];
const elements=new Map();
function node(){const n={textContent:'',disabled:false,dataset:{},attrs:{},children:[],classList:{contains:()=>true},
 setAttribute(k,v){this.attrs[k]=v},append(...c){this.children.push(...c)},replaceChildren(){this.children=[]}};return n;}
function el(id){if(!elements.has(id))elements.set(id,node());return elements.get(id);}
const document={getElementById:el,querySelectorAll:()=>[],createElement:node};
function clearTimeout(){} function setTimeout(fn,ms){timers.push({fn,ms});return timers.length;}
function refreshCliStatus(){}
'''
        checks = r'''
renderCliStatus({job:{state:'done'},providers:{gemini:{installed:true,ready:false,login_pending:true}}});
assert.equal(timers.length,1);assert.equal(timers[0].ms,1500);
assert.equal(el('cliContinue').disabled,true);
renderCliStatus({job:{state:'done'},providers:{gemini:{installed:true,ready:true,backend:'agy',login_pending:false}}});
assert.equal(timers.length,1);assert.equal(el('cliContinue').disabled,false);
assert.match(el('cliProviderState').textContent,/Antigravity CLI/);
const rows=el('agentConnections').children;
assert.deepEqual(rows.map(r=>[r.dataset.agentId,r.dataset.state]),[['codex','missing'],['antigravity','ready'],['notion','missing']]);
assert.equal(rows[2].children[2].textContent,'Bağlı değil');
'''
        result=subprocess.run(['node','-e',harness+function+checks],capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_connection_and_event_loops_execute_and_rearm(self):
        source = gui._HTML
        connection = source[source.index('  let lastUserActivityAt ='):source.index('  function fillClass(')]
        events = source[source.index('  let uiEventsPollBusy ='):source.index("  window.addEventListener('pywebviewready'")]
        harness = r'''
const assert = require('node:assert/strict');
let pingCalls=0, eventCalls=0, desktopReads=0, fail=false;
const timers=[];
const elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{textContent:'CONNECTING',style:{},classList:{toggle(){},add(){},remove(){}}});return elements.get(id);}
const document={hidden:false,visibilityState:'visible',body:el('body'),addEventListener(){},getElementById:el};
const window={addEventListener(){},pywebview:{api:{
 ping:async()=>{pingCalls++;if(fail)throw Error('offline');return {online:true};},
 ui_events:async()=>{eventCalls++;return {status:'ok',data:[]};}
}}};
function setTimeout(fn,ms){timers.push({fn,ms});}
let thinking=false,chatPollInterval=null,desktopView={code:'normal',stop_ref:null};
let conversationLoaded=true,currentConvId='c';
const statusPill=el('pill'),statusText=el('status');
async function loadActiveConversation(){}
async function refreshDesktopTaskState(){desktopReads++;}
function renderUiEvents(){}
async function pollNaturalTask(){}
'''
        checks = r'''
(async()=>{
 await pollPing();
 assert.equal(pingCalls,1);
 assert.equal(statusText.textContent,'ÇEVRİMİÇİ');
 assert.equal(timers.at(-1).fn,pollPing);
 fail=true;await pollPing();
 assert.equal(statusText.textContent,'ÇEVRİMDIŞI');
 assert.equal(timers.at(-1).fn,pollPing);
 assert.equal(timers.at(-1).ms,600);
 thinking=false;chatPollInterval=null;lastUserActivityAt=0;
 assert.equal(isUiIdle(),true);
 desktopView={code:'preparing',stop_ref:'natural:t'};
 assert.equal(isUiIdle(),false);
 chatPollInterval=1;await pollUiEvents();
 assert.equal(eventCalls,1);assert.equal(desktopReads,1);
 assert.equal(timers.at(-1).fn,pollUiEvents);
 console.log(JSON.stringify({pingCalls,eventCalls,desktopReads}));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run(['node','-e',harness+connection+events+checks],capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['pingCalls'],2)


if __name__ == '__main__':unittest.main()
