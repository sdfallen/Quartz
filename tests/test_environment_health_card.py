"""Environment health card (docs/INTEGRATION_REQUEST_ENVIRONMENT_HEALTH_20261109.md).

Runs the shipped card code in Node with a minimal DOM. The host decides ok/warn/blocked;
the card only shows it and offers a forced re-check.
"""
import subprocess
import unittest
from unittest.mock import patch

import gui

START = "  // Environment health card."
END = "  function renderWriterRecovery(data) {"
CARD = gui._HTML[gui._HTML.index(START):gui._HTML.index(END)]

HARNESS = r'''
const assert=require('node:assert/strict');
const node=(id)=>({id,hidden:true,dataset:{},attrs:{},textContent:'',disabled:false,children:[],listeners:{},
  setAttribute(k,v){this.attrs[k]=String(v)},append(...c){this.children.push(...c)},
  replaceChildren(...c){this.children=c},addEventListener(t,f){this.listeners[t]=f}});
const els={};for(const id of ['envHealth','envHealthList','envHealthToggle','envHealthRecheck','envHealthBadge','envHealthTitle'])els[id]=node(id);
const document={getElementById:id=>els[id]||null,createElement:t=>({tag:t,dataset:{},className:'',textContent:'',children:[],
  append(...c){this.children.push(...c)}})};
const logs=[];const logLine=m=>logs.push(m);
let calls=[];let reply={status:'ok',data:{status:'ok',checks:[]}};
const window={pywebview:{api:{environment_health:async f=>{calls.push(f);return reply;}}}};
const text=n=>(n.textContent||'')+(n.children||[]).map(text).join('');
'''


def run(checks):
    result = subprocess.run(["node", "-"], input=HARNESS + CARD + checks, capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    return result


class EnvironmentHealthCardTests(unittest.TestCase):
    def assertJs(self, checks):
        result = run(checks)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ok_or_missing_result_shows_nothing(self):
        self.assertJs(r'''
renderEnvironmentHealth({status:'ok',checks:[{id:'python',status:'ok',summary_tr:'Python hazır.'}]});
assert.equal(els.envHealth.hidden,true);
renderEnvironmentHealth(null);assert.equal(els.envHealth.hidden,true);
''')

    def test_warning_is_collapsed_and_lists_only_problems(self):
        self.assertJs(r'''
renderEnvironmentHealth({status:'warn',checks:[
  {id:'python',status:'warn',summary_tr:'Python Store takma adı.',fix_tr:'python.org Python kurun.',detail:'WindowsApps'},
  {id:'git',status:'ok',summary_tr:'Git hazır.'}]});
assert.equal(els.envHealth.hidden,false);assert.equal(els.envHealth.dataset.status,'warn');
assert.equal(els.envHealthBadge.dataset.tone,'warn');assert.equal(els.envHealthTitle.textContent,'Ortamda 1 uyarı var');
assert.equal(els.envHealthList.hidden,true);assert.equal(els.envHealthToggle.attrs['aria-expanded'],'false');
assert.equal(els.envHealthList.children.length,1);
const item=text(els.envHealthList.children[0]);
assert.match(item,/Python Store takma adı\./);assert.match(item,/python\.org Python kurun\./);assert.match(item,/Teknik ayrıntılar/);
assert.doesNotMatch(item,/Git hazır/);
els.envHealthToggle.listeners.click();assert.equal(els.envHealthList.hidden,false);assert.equal(els.envHealthToggle.textContent,'Gizle');
''')

    def test_blocked_explains_itself_without_a_click(self):
        self.assertJs(r'''
renderEnvironmentHealth({status:'blocked',checks:[
  {id:'squad',status:'blocked',summary_tr:'Squad bağlı değil.',fix_tr:'squad init'},
  {id:'python',status:'warn',summary_tr:'Store takma adı.'},
  {id:'codex_cli',status:'unknown',summary_tr:'Kontrol ediliyor.'}]});
assert.equal(els.envHealth.dataset.status,'blocked');assert.equal(els.envHealthBadge.dataset.tone,'fail');
assert.equal(els.envHealthTitle.textContent,'Görev başlatılamaz: 1 engel, 2 uyarı');
assert.equal(els.envHealthList.hidden,false);assert.equal(els.envHealthList.children[0].dataset.status,'blocked');
''')

    def test_host_text_is_never_html(self):
        self.assertJs(r'''
renderEnvironmentHealth({status:'warn',checks:[{id:'x',status:'warn',summary_tr:'<img src=x onerror=alert(1)>'}]});
assert.equal(els.envHealthList.children[0].children[0].textContent,'<img src=x onerror=alert(1)>');
''')
        self.assertNotIn("innerHTML", CARD)

    def test_recheck_forces_a_fresh_check_and_is_disabled_while_running(self):
        self.assertJs(r'''
(async()=>{
renderEnvironmentHealth({status:'warn',checks:[{id:'python',status:'warn',summary_tr:'Store.'}]});
reply={status:'ok',data:{status:'ok',checks:[]}};
const pending=els.envHealthRecheck.listeners.click();
assert.equal(els.envHealthRecheck.disabled,true);assert.equal(els.envHealthRecheck.textContent,'Kontrol ediliyor…');
await pending;
assert.deepEqual(calls,[true]);assert.equal(els.envHealth.hidden,true);
assert.equal(els.envHealthRecheck.disabled,false);assert.equal(els.envHealthRecheck.textContent,'Yeniden kontrol et');
reply={status:'error',data:'backend yok'};await els.envHealthRecheck.listeners.click();
assert.match(logs.pop(),/backend yok/);
})().catch(e=>{console.error(e);process.exitCode=1;});
''')

    def test_shell_and_bridge(self):
        self.assertIn('id="envHealth"', gui._HTML)
        self.assertIn('aria-controls="envHealthList"', gui._HTML)
        self.assertIn("if ('environment_health' in data) renderEnvironmentHealth(data.environment_health);", gui._HTML)
        api = gui.Api()
        with patch.object(gui, "ipc_send", return_value={"status": "ok", "data": {}}) as send:
            api.environment_health(True)
            api.environment_health("yes")  # only a real True forces
        self.assertEqual(send.call_args_list[0].args, ("environment_health", {"force": True}))
        self.assertEqual(send.call_args_list[1].args, ("environment_health", {"force": False}))
        with patch.object(gui, "ipc_send", side_effect=RuntimeError("down")):
            self.assertEqual(api.environment_health(True)["status"], "error")


if __name__ == "__main__":
    unittest.main()
