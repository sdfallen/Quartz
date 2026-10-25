"""Fresh-process offline acceptance. No model, GUI, permission or user store.

Uses a disposable task history and source receipt. This is process/disk evidence,
not an assertion that desktop automation or a project runtime has been verified.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def child(folder):
    from core.agent_chat import AgentChatService
    from core.run_evidence_store import RunEvidenceStore
    root = Path(folder)
    # Constructing the service can only recover local data; no provider exists.
    chat = AgentChatService(SimpleNamespace(status=lambda *_: {}), root/'chat.json')
    try:
        conv = chat.store.get_active()
        receipt = RunEvidenceStore(root/'receipts.json').get('fixture-source-check')
        result = {
            'recovery':chat.recovery,
            'message_states':[m['status'] for m in conv['messages']],
            'partial_text':conv['messages'][0]['content'],
            'session_cleared':conv['sessions']['codex'] is None,
            'selected_model':conv['models']['codex']['model'],
            'receipt':receipt,
            'active_turn':chat._active_turn,
        }
        print(json.dumps(result, ensure_ascii=True))
    finally:
        chat.close()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--journal-producer':
        from core.writer_journal import WriterJournal
        root=Path(sys.argv[2]); journal=WriterJournal(root/'writers.json')
        key=journal.reserve(str(root/'project'),False,'codex')
        worker=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(12)'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        journal.update(key,stage='active',run_id='owned-sleep-fixture',pid=worker.pid)
        print(json.dumps({'claim':key,'worker_pid':worker.pid}),flush=True)
        return 0  # Deliberately leave ONLY this authored sleep child to exit naturally.
    if '--journal' in sys.argv[1:]: return journal_probe()
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        child(sys.argv[2]); return 0
    from core.conversation_store import ConversationStore
    from core.run_evidence_store import RunEvidenceStore
    from core.source_verification import verify_changed_python
    destination = ROOT/'labs'/('recovery-process-' + time.strftime('%Y%m%d-%H%M%S'))
    destination.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='quartz-recovery-probe-') as folder:
        root=Path(folder); store=ConversationStore(root/'chat.json'); cid=store.get_active()['id']
        store.update_agent_model(cid, 'codex', model='preserved-model', effort='high')
        store.set_agent_session(cid, 'codex', 'must-not-replay')
        store.append_message(cid, 'assistant', 'Real persisted partial text', sender='codex', metadata={'status':'running'})
        store.append_message(cid, 'assistant', 'Completed history', metadata={'status':'completed'})
        store.append_message(cid, 'assistant', 'Desktop task started', sender='quartz', metadata={
            'status':'completed', 'natural_task':'fixture-desktop-task', 'task_status':'running'})
        before=json.loads((root/'chat.json').read_text(encoding='utf-8'))
        source=root/'sample.py'; source.write_text('raise RuntimeError("must never execute")\n', encoding='utf-8')
        validation=verify_changed_python(root, [str(source)])
        RunEvidenceStore(root/'receipts.json').put('fixture-source-check', {'source_validation':validation})
        process=subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--child', str(root)],
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        if process.returncode: raise RuntimeError('Recovery child failed: ' + process.stderr[-1000:])
        result=json.loads(process.stdout)
        backup=json.loads(Path(result['recovery']['backup']).read_text(encoding='utf-8'))
        checks={
            'separate_process_exit_zero':process.returncode==0,
            'only_abandoned_states_changed':result['message_states']==['interrupted','completed','interrupted'],
            'partial_text_preserved':result['partial_text']=='Real persisted partial text',
            'original_backup_equal':backup==before,
            'model_preserved':result['selected_model']=='preserved-model',
            'no_active_turn_or_implicit_replay':result['active_turn'] is None and result['session_cleared'] and not result['recovery']['automatic_replay'],
            'durable_source_receipt':result['receipt']['historical'] and result['receipt']['source_validation']['status']=='VERIFIED',
            'not_runtime_or_goal_acceptance':not result['receipt']['source_validation']['tests_executed'] and not result['receipt']['source_validation']['goal_accepted'],
        }
    report={'scope':'FRESH PROCESS / OFFLINE; disposable fixture; no providers or GUI',
            'status':'VERIFIED' if all(checks.values()) else 'FAILED', 'checks':checks}
    (destination/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({**report, 'evidence':str(destination/'result.json')}, indent=2))
    return 0 if report['status']=='VERIFIED' else 1


def journal_probe():
    from core.writer_journal import WriterJournal
    destination=ROOT/'labs'/('runtime-journal-'+time.strftime('%Y%m%d-%H%M%S'))
    destination.mkdir(parents=True,exist_ok=False)
    report={'scope':'Real separate producer and owned sleep process; no GUI, model or user task; no process killed'}
    with tempfile.TemporaryDirectory(prefix='quartz-journal-probe-') as folder:
        root=Path(folder); (root/'project').mkdir()
        try:
            producer=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--journal-producer',folder],
                capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if producer.returncode: raise RuntimeError(producer.stderr[-500:])
            data=json.loads(producer.stdout); journal=WriterJournal(root/'writers.json')
            before=journal.inspect(data['claim'])
            reserve_blocked=False; ack_blocked=False
            try: journal.reserve(str(root/'project'),False,'codex')
            except RuntimeError: reserve_blocked=True
            try: journal.acknowledge(data['claim'],confirmed=True,external_review=True)
            except RuntimeError: ack_blocked=True
            deadline=time.monotonic()+25
            while journal.inspect(data['claim'])['process_state']=='live':
                if time.monotonic()>deadline: raise TimeoutError('Owned sleep fixture did not naturally exit')
                time.sleep(.25)
            after=journal.inspect(data['claim'])
            unconfirmed_blocked=False
            try: journal.acknowledge(data['claim'])
            except PermissionError: unconfirmed_blocked=True
            acknowledged=journal.acknowledge(data['claim'],confirmed=True,external_review=True)
            replacement=journal.reserve(str(root/'project'),False,'codex')
            journal.finish(replacement)
            checks={'producer_exited':producer.returncode==0,
                'host_gone_writer_live':before['owner_state'] in {'gone','replaced'} and before['process_state']=='live',
                'new_writer_blocked':reserve_blocked,'live_writer_not_overridden_by_confirmation':ack_blocked,
                'natural_worker_exit':after['process_state'] in {'gone','replaced'},
                'explicit_review_required':unconfirmed_blocked,
                'no_authority_or_replay_restored':not acknowledged['permissions_restored'] and not acknowledged['automatic_replay'],
                'review_archived':Path(acknowledged['archive']).is_file(),
                'no_claim_left':not WriterJournal(root/'writers.json').recovery_status()['claims']}
            report.update(status='VERIFIED' if all(checks.values()) else 'FAILED',checks=checks,
                original_worker_pid=data['worker_pid'],before=before,after=after)
        except Exception as exc: report.update(status='BLOCKED',error=str(exc))
    (destination/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'before','after'}},indent=2))
    print('Evidence:',destination/'result.json')
    return 0 if report['status']=='VERIFIED' else 1


if __name__ == '__main__': raise SystemExit(main())
