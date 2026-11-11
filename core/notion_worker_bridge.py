"""Outbound-only, read-only disposable fixture bridge for a Notion Worker.

Not wired into normal chat, REA, terminal or Desktop Broker. No network listener.
The local manifest is created by the test owner, NEVER from remote queue rows.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

from core.notion_cli import NotionCli, identifier


def sign(kind, payload, key):
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(body.encode()) > 12000 or len(key) != 32:
        raise ValueError('Bridge payload or key invalid')
    mac = hmac.new(key, f'quartz-readonly/{kind}/v1\n{body}'.encode(), hashlib.sha256).hexdigest()
    return json.dumps(dict(v=1, kind=kind, body=body, mac=mac), ensure_ascii=False, separators=(',', ':'))


def verify(raw, kind, key):
    if not isinstance(raw, str) or len(raw.encode()) > 16000 or len(key) != 32:
        raise ValueError('Invalid bridge envelope')
    env = json.loads(raw)
    if (not isinstance(env, dict) or set(env) != {'v','kind','body','mac'} or
            type(env['v']) is not int or env['v'] != 1 or env['kind'] != kind or
            not isinstance(env['body'], str) or not isinstance(env['mac'], str)):
        raise ValueError('Invalid bridge envelope')
    expected = hmac.new(key, f"quartz-readonly/{kind}/v1\n{env['body']}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, env['mac']):
        raise PermissionError('Invalid bridge signature')
    data = json.loads(env['body'])
    if not isinstance(data, dict): raise ValueError('Invalid bridge payload')
    return data


def store_bridge_key(target, key):
    import win32cred
    if len(key) != 32: raise ValueError('Invalid bridge key')
    win32cred.CredWrite({'Type': win32cred.CRED_TYPE_GENERIC, 'TargetName': target,
        'UserName': 'Quartz Notion read-only bridge', 'CredentialBlob': key.hex(),
        'Persist': win32cred.CRED_PERSIST_LOCAL_MACHINE}, 0)


def load_bridge_key(target):
    import win32cred
    raw = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)['CredentialBlob']
    text = raw.decode('utf-16-le') if isinstance(raw, bytes) else raw
    if not isinstance(text, str) or not re.fullmatch(r'[a-f0-9]{64}', text): raise ValueError('Bridge key unavailable')
    key = bytes.fromhex(text)
    return key


def rich(text):
    return {'rich_text': [{'type':'text','text':{'content':text[i:i+1800]}} for i in range(0,len(text),1800)]}


def property_text(page, name):
    return ''.join(t.get('plain_text', t.get('text', {}).get('content', ''))
                   for t in page.get('properties', {}).get(name, {}).get('rich_text', []))


class NotionQueueApi(NotionCli):
    def __init__(self, workspace_id, queue_id, **kwargs):
        super().__init__(workspace_id, **kwargs)
        self.queue_id = identifier(queue_id)

    def page(self, page_id):
        page = self._send('v1/pages/' + identifier(page_id))
        if (page.get('archived') or page.get('in_trash') or
                page.get('parent', {}).get('data_source_id') != self.queue_id):
            raise PermissionError('Page outside private bridge queue')
        return page

    def create(self, name, properties):
        return self._send('v1/pages', {'parent': {'type':'data_source_id','data_source_id':self.queue_id},
            'properties': {'Name': {'title':[{'text': {'content':name}}]}, **properties}})

    def query(self, task_id, session_id):
        # Only one owner's current task. Do not scan other workspace pages.
        result = self._send(f'v1/data_sources/{self.queue_id}/query', {'page_size':100,
            'filter': {'and': [{'property':'Task ID','rich_text':{'equals':task_id}},
                               {'property':'Session ID','rich_text':{'equals':session_id}}]}})
        if result.get('has_more'): raise RuntimeError('Queue task exceeds safe page limit')
        return result.get('results', [])

    def complete(self, page_id, result, state):
        self.page(page_id)
        if state not in {'completed','blocked','failed','cancelled','expired'}:
            raise ValueError('Invalid queue completion state')
        return self._send('v1/pages/' + identifier(page_id),
            {'properties': {'State': {'select': {'name':state}}, 'Signed Result':rich(result)}}, method='PATCH')


class ReadOnlyWorkerBridge:
    def __init__(self, api, key, manifest, ledger_path, *, clock=time.time):
        self.api, self._key = api, key
        self.manifest, self.clock = deepcopy(manifest), clock
        self.root = Path(manifest['root']).resolve(strict=True)
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.ledger = Path(ledger_path)
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, result TEXT)')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.ledger, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def stop(self):
        self._stop.set()

    def _validate(self, request):
        m = self.manifest
        expected = {'schema_version','task_id','session_id','project_id','scope_ref','request_id','tool_name','arguments','expires_at'}
        if set(request) != expected or type(request['schema_version']) is not int or request['schema_version'] != 1:
            raise ValueError('Invalid read-only request')
        if any(request[k] != m[k] for k in ('task_id','session_id','project_id','scope_ref','request_id')):
            raise PermissionError('Request does not belong to this local task')
        if (request['tool_name'] != 'read_test_file' or request['arguments'] != {'relative_path':m['relative_path']} or
                request['expires_at'] != m['expires_at'] or self.clock() >= m['expires_at'] or self._stop.is_set()):
            raise PermissionError('Read-only scope expired or revoked')

    def process(self, page):
        if page.get('parent', {}).get('data_source_id') != self.api.queue_id:
            raise PermissionError('Foreign queue page')
        raw = property_text(page, 'Signed Request')
        if not raw: return None  # Signed grant rows are not tool requests.
        request = verify(raw, 'request', self._key)
        self._validate(request)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        rid = request['request_id']
        with self._lock, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT digest,state,result FROM requests WHERE id=?', (rid,)).fetchone()
            if old:
                if old[0] != digest: raise PermissionError('Request identity reused with different content')
                if old[1] != 'completed': raise RuntimeError('Previous outcome uncertain; automatic replay blocked')
                result = old[2]
            else:
                if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] >= 256:
                    raise RuntimeError('Read-only ledger limit reached')
                db.execute('INSERT INTO requests VALUES (?,?,?,NULL)', (rid,digest,'claimed'))
                result = None
        if result is None:
            base = {k:request[k] for k in ('task_id','session_id','project_id','request_id')}
            try:
                output = self._read_fixture()
                self._validate(request)
                payload = {**base,'status':'completed','verification':'observed','observed_at':self.clock(),'output':output}
            except Exception:
                payload = {**base,'status':'blocked','verification':'none',
                           'error':'Test dosyası, kapsam veya süre doğrulanamadı. İşlem tekrarlanmadı.'}
            result = sign('result', payload, self._key)
            with self._db() as db:
                db.execute('UPDATE requests SET state=?,result=? WHERE id=?', ('completed',result,rid))
        if self._stop.is_set(): return None  # No late success publication after Stop.
        self.api.complete(page['id'], result, verify(result, 'result', self._key)['status'])
        return verify(result, 'result', self._key)

    def _read_fixture(self):
        if self._stop.is_set(): raise PermissionError('Stopped')
        m = self.manifest
        name = m['relative_path']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}\.txt', name): raise PermissionError('Invalid fixture name')
        path = self.root / name
        if path.is_symlink() or path.resolve(strict=True).parent != self.root:
            raise PermissionError('Fixture path changed')
        # Verify the open file's identity BEFORE reading; a replaced path or
        # redirected file cannot expand the local manifest's approved scope.
        with path.open('rb') as stream:
            stat = os.fstat(stream.fileno())
            if [stat.st_dev,stat.st_ino,stat.st_size] != m['file_identity'] or stat.st_size > 4096:
                raise PermissionError('Fixture identity changed')
            if self._stop.is_set(): raise PermissionError('Stopped')
            data = stream.read(4097)
            after = os.fstat(stream.fileno())
            if after.st_mtime_ns != stat.st_mtime_ns or self._stop.is_set(): raise PermissionError('Fixture changed or stopped')
        digest = hashlib.sha256(data).hexdigest()
        if digest != m['sha256']: raise PermissionError('Fixture bytes changed')
        return {'relative_path':name,'text':data.decode('utf-8'),'sha256':digest,'bytes':len(data)}
