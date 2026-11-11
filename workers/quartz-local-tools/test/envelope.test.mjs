import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
import {sign,verify,requestFromGrant} from '../dist/envelope.js';

const key = '12'.repeat(32); // synthetic test key, never deployed
const grant = {tool_name:'read_test_file',relative_path:'fixture.txt',task_id:'t1',session_id:'s1',project_id:'p1',scope_ref:'scope',request_id:'r1',expires_at:100};
test('roundtrip preserves Turkish data and separates envelope domains',()=>{
  const env = sign('grant', {...grant,note:'Türkçe'},key);
  assert.equal(verify(JSON.stringify(env),'grant',key).note,'Türkçe');
  assert.throws(()=>verify(JSON.stringify(env),'request',key));
});
test('tampered body, wrong key and invalid MAC are rejected',()=>{
  const env = sign('grant',grant,key);
  assert.throws(()=>verify(JSON.stringify({...env,body:env.body+' '}),'grant',key));
  assert.throws(()=>verify(JSON.stringify(env),'grant','34'.repeat(32)));
  assert.throws(()=>verify(JSON.stringify({...env,mac:'invalid'}),'grant',key));
});
test('grant limits task, request, path, TTL and tool',()=>{
  assert.equal(requestFromGrant(grant,'r1','fixture.txt',1).tool_name,'read_test_file');
  for(const g of [{...grant,expires_at:0},{...grant,expires_at:Infinity},{...grant,expires_at:2000},
    {...grant,tool_name:'shell'}, {...grant,session_id:' '}, {...grant,relative_path:'../secret.txt'}])
      assert.throws(()=>requestFromGrant(g,'r1',g.relative_path,1));
  assert.throws(()=>requestFromGrant(grant,'r2','fixture.txt',1));
  assert.throws(()=>requestFromGrant(grant,'r1','other.txt',1));
});
test('oversized payload and unavailable key fail closed',()=>{
  assert.throws(()=>sign('request',{text:'a'.repeat(13000)},key));
  assert.throws(()=>sign('request',grant,''));
  assert.throws(()=>verify('a'.repeat(16001),'request',key));
});
test('Python and Worker verify each others UTF-8 envelopes',()=>{
  const input = JSON.stringify(sign('request',{note:'Türkçe kanıt'},key));
  const script = `import sys,json\nfrom core.notion_worker_bridge import verify,sign\nk=bytes.fromhex('12'*32)\np=verify(sys.stdin.read(),'request',k)\nprint(sign('result',p,k))`;
  const p = spawnSync('python',['-B','-c',script], {cwd:resolve('../..'),input,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'}});
  assert.equal(p.status,0,p.stderr);
  assert.equal(verify(p.stdout.trim(),'result',key).note,'Türkçe kanıt');
});
