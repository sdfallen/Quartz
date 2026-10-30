"""Real local IPC + optional REA acceptance on an explicitly selected package.

Development harness only. The production IPC never accepts a target directory.
No target execution, model request, account use or public transmission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import statistics
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    parser.add_argument('evidence',type=Path)
    args=parser.parse_args()
    package=args.package.resolve(strict=True)
    args.evidence.mkdir(parents=True,exist_ok=True)
    exe=package/'Quartz.exe'
    before=hashlib.sha256(exe.read_bytes()).hexdigest()
    import main as backend
    from core.local_ipc import request_token
    from core.self_diagnostics import SelfDiagnosticsService
    backend.IPC_PORT=0  # Dedicated ephemeral socket; never interfere with an open app.
    server=backend.IPCServer()
    server._diagnostics=SelfDiagnosticsService(package,args.evidence/'reports')
    thread=threading.Thread(target=server.start,daemon=True)
    thread.start()
    end=time.monotonic()+10
    while (not server._server or not server._running) and time.monotonic()<end:time.sleep(.02)
    port=server._server.getsockname()[1]
    def send(action,data=None,authenticated=True):
        request={'action':action,'data':data or {}}
        if authenticated: request['auth']=request_token()
        start=time.monotonic()
        with socket.create_connection(('127.0.0.1',port),timeout=3) as connection:
            connection.sendall(json.dumps(request).encode()+b'\n'); connection.shutdown(socket.SHUT_WR)
            chunks=[]
            while chunk:=connection.recv(65536):chunks.append(chunk)
        return json.loads(b''.join(chunks)),(time.monotonic()-start)*1000
    try:
        denied,_=send('diagnostics_start',authenticated=False)
        assert denied['status']=='error'
        outside,_=send('diagnostics_start',{'target':'C:/not-approved'})
        assert outside['status']=='error'
        started,start_ms=send('diagnostics_start',{'include_rea':True})
        assert started['status']=='ok'
        identity=started['data']['id']
        duplicate,_=send('diagnostics_start',{'include_rea':True})
        assert duplicate['data']['id']==identity
        latencies=[]
        deadline=time.monotonic()+190
        while time.monotonic()<deadline:
            response,latency=send('diagnostics_status',{'job_id':identity})
            latencies.append(latency)
            state=response['data']
            if state['state']!='running':break
            time.sleep(.4)
        else:raise RuntimeError('Acceptance deadline exceeded')
        after=hashlib.sha256(exe.read_bytes()).hexdigest()
        assert after==before
        result={'scope':'Real backend IPC and static REA integration; not packaged GUI acceptance',
                'unauthorized_rejected':True,'outside_target_rejected':True,'duplicate_start_idempotent':True,
                'target_unchanged':True,'target_sha256':before,'start_response_ms':round(start_ms,3),
                'poll_samples':len(latencies),'poll_median_ms':round(statistics.median(latencies),3),
                'poll_max_ms':round(max(latencies),3),'job':state}
        (args.evidence/'acceptance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='job'},indent=2))
        print('Verdict:',state['verdict'],'State:',state['state'])
    finally:
        server.stop();thread.join(timeout=3)


if __name__=='__main__':main()
