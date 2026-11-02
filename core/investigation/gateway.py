"""Question/target-bound bridge to the separately owned ToolWorkbench facade.

Policy validation is not an OS sandbox. No subprocess, installation or UI input
is implemented here; the workbench and current Broker retain that authority.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import threading

from .contracts import IDENTIFIER, SHA256, InvestigationError, bounded_json, guard, safe_path
from .planning import InvestigationPolicy, ProgressLedger

_PRIVATE_KEYS = re.compile(r'(token|password|secret|cookie|authorization|api_key|credentials)',re.I)
_SECRET_VALUE = re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,})\b')


def _redacted(value):
    if isinstance(value,dict): return {k:('[gizli]' if _PRIVATE_KEYS.search(k) else _redacted(v)) for k,v in value.items()}
    if isinstance(value,list): return [_redacted(x) for x in value]
    if isinstance(value,str):return _SECRET_VALUE.sub('[gizli]',value)
    return value


def _validate_options(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key.casefold() in {'argv','command','shell','script','env','cwd','executable'} or _PRIVATE_KEYS.search(key):
                raise InvestigationError('unsafe-tool-options')
            _validate_options(item)
    elif isinstance(value,list):
        for item in value:_validate_options(item)


class InvestigationToolGateway:
    def __init__(self, session, workbench, *, workspace, policy, tool_specs):
        if not isinstance(policy,InvestigationPolicy):raise InvestigationError('missing-policy')
        self.session, self.workbench, self.policy = session, workbench, policy
        self.workspace = safe_path(workspace)
        if self.workspace == Path(self.session.target.canonical_path).parent:
            raise InvestigationError('tool-workspace-is-target-directory')
        self.tool_specs=bounded_json(tool_specs)
        if not isinstance(self.tool_specs,dict) or len(self.tool_specs)>128:raise InvestigationError('invalid-tool-specs')
        for key,spec in self.tool_specs.items():
            if (not isinstance(key,str) or not IDENTIFIER.fullmatch(key) or not isinstance(spec,dict)
                    or not isinstance(spec.get('package_digest'),str) or not SHA256.fullmatch(spec['package_digest'])
                    or not isinstance(spec.get('operations'),list) or not isinstance(spec.get('effects'),list)
                    or any(not isinstance(x,str) for x in spec['operations']+spec['effects'])
                    or not isinstance(spec.get('source_url'),str) or not 1<=len(spec['source_url'])<=2048
                    or not isinstance(spec.get('pinned_revision'),str) or not 1<=len(spec['pinned_revision'])<=200):
                raise InvestigationError('invalid-tool-spec')
        self.ledger=ProgressLedger(policy.max_steps)
        self._lock=threading.Lock()
        self._closed=False
        self._receipts={}

    def execute(self, request, cancel_event=None):
        # No parallel calls to a target from one investigator. A second caller
        # gets a clear busy result; this is not another task queue/writer lock.
        if not self._lock.acquire(blocking=False):raise InvestigationError('tool-call-in-progress')
        try:
            guard(self.session.event,self.session.deadline)
            if self._closed:raise InvestigationError('gateway-closed')
            if cancel_event is not None and cancel_event is not self.session.event:
                raise InvestigationError('wrong-cancellation-owner')
            request=bounded_json(request,maximum=128*1024)
            if not isinstance(request,dict):raise InvestigationError('invalid-tool-request')
            if request.get('investigation_id')!=self.session.evidence.id:raise InvestigationError('wrong-investigation')
            step=request.get('step_id')
            tool=request.get('tool_id');operation=request.get('operation')
            if (not isinstance(step,str) or not IDENTIFIER.fullmatch(step) or not isinstance(tool,str) or tool not in self.tool_specs
                    or not isinstance(operation,str) or not IDENTIFIER.fullmatch(operation)):
                raise InvestigationError('invalid-tool-step')
            spec=self.tool_specs[tool]
            if operation not in spec['operations'] or not set(spec['effects'])<=self.policy.effects:
                raise InvestigationError('tool-effect-not-authorized')
            if request.get('target')!=self.session.target.as_dict():raise InvestigationError('wrong-target')
            if safe_path(request.get('workspace',''))!=self.workspace:raise InvestigationError('wrong-workspace')
            options=request.get('options',{})
            if not isinstance(options,dict):raise InvestigationError('invalid-tool-options')
            _validate_options(options)
            request['deadline_monotonic']=self.session.deadline
            requested_limit=request.get('max_output_bytes',self.policy.max_output_bytes)
            if type(requested_limit) is not int or requested_limit<1:raise InvestigationError('invalid-output-limit')
            request['max_output_bytes']=min(self.policy.max_output_bytes,requested_limit)
            request['request_id']=self.session.evidence.id+'.'+step
            digest=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
            if step in self._receipts:
                previous=self._receipts[step]
                if previous['digest']!=digest:raise InvestigationError('conflicting-step-id')
                return deepcopy(previous['result']) | {'replayed_receipt':True}
            if len(self._receipts)>=self.policy.max_steps:raise InvestigationError('step-budget')
            self.session.target.revalidate(self.session.event,self.session.deadline)
            # Claim before crossing the side-effect boundary. An exception,
            # malformed receipt or late cancellation cannot make a resend safe.
            self._receipts[step]={'digest':digest,'result':{
                'status':'blocked','reason':'tool-call-outcome-unconfirmed',
                'request_id':request['request_id'],'instruction_authority':False}}
            receipt=self.workbench.execute(request,self.session.event)
            guard(self.session.event,self.session.deadline)
            self.session.target.revalidate(self.session.event,self.session.deadline)
            receipt=bounded_json(receipt,maximum=self.policy.max_output_bytes)
            if (not isinstance(receipt,dict) or receipt.get('request_id')!=request['request_id']
                    or receipt.get('tool_id')!=tool or receipt.get('status') not in {'completed','failed','cancelled','blocked'}):
                raise InvestigationError('invalid-tool-receipt')
            if any(receipt.get(k)!=spec[k] for k in ('source_url','pinned_revision','package_digest')):
                raise InvestigationError('tool-provenance-mismatch')
            cleanup=receipt.get('cleanup_receipt',{})
            if not isinstance(cleanup,dict) or cleanup.get('status')!='confirmed':
                raise InvestigationError('tool-cleanup-unconfirmed')
            records=[]
            artifacts=receipt.get('artifacts',[])
            if not isinstance(artifacts,list) or len(artifacts)>32:raise InvestigationError('invalid-tool-artifacts')
            if receipt['status']=='completed':
                if receipt.get('exit_code')!=0:raise InvestigationError('contradictory-tool-result')
                for item in artifacts:
                    if not isinstance(item,dict) or not isinstance(item.get('path'),str):raise InvestigationError('invalid-tool-artifact')
                    source=self.workspace/item['path']
                    record=self.session.evidence.ingest_file(source,source_root=self.workspace,
                        expected_sha256=item.get('sha256'),kind='tool-artifact',origin=tool)
                    records.append(record['evidence_id'])
            source=self.session.evidence.add_json(_redacted(receipt),kind='tool-receipt',origin=tool)
            records.append(source['evidence_id'])
            result=_redacted(receipt) | {'evidence_ids':records,
                'made_progress':self.ledger.record(request,receipt,evidence_ids=records), 'instruction_authority':False}
            self._receipts[step]={'digest':digest,'result':deepcopy(result)}
            return result
        finally:self._lock.release()

    def close(self):
        self._closed=True
        # The existing host owner decides when to cancel; a receipt never kills
        # a process or restores authority by itself.
        return self.workbench.stop(self.session.evidence.id) if self.workbench is not None else {'status':'confirmed'}

    def capture_analysis(self, artifact_path, expected_sha256, request, cancel_event):
        """Capture the builtin parser's snapshot; never promotes it to LIVE."""
        if not self._lock.acquire(blocking=False):raise InvestigationError('tool-call-in-progress')
        try:
            guard(self.session.event,self.session.deadline)
            if self._closed or cancel_event is not self.session.event:raise InvestigationError('wrong-capture-owner')
            request=bounded_json(request,maximum=128*1024)
            if (not isinstance(request,dict) or request.get('investigation_id')!=self.session.evidence.id
                    or request.get('target')!=self.session.target.as_dict()
                    or request.get('operation')!='builtin-analysis-snapshot'
                    or request.get('tool_id')!='quartz-builtin-analysis'
                    or safe_path(request.get('workspace',''))!=self.workspace
                    or not {'read_target','write_workspace'}<=self.policy.effects):
                raise InvestigationError('invalid-analysis-capture')
            step=request.get('step_id')
            if not isinstance(step,str) or not IDENTIFIER.fullmatch(step):raise InvestigationError('invalid-tool-step')
            if not isinstance(expected_sha256,str) or not SHA256.fullmatch(expected_sha256):raise InvestigationError('invalid-artifact-digest')
            source=safe_path(artifact_path)
            if self.workspace not in source.parents or source.stat().st_size>self.policy.max_output_bytes:
                raise InvestigationError('analysis-snapshot-outside-workspace')
            key=hashlib.sha256(json.dumps([request,expected_sha256],sort_keys=True).encode()).hexdigest()
            if step in self._receipts:
                previous=self._receipts[step]
                if previous['digest']!=key:raise InvestigationError('conflicting-step-id')
                return deepcopy(previous['result'])|{'replayed_receipt':True}
            if len(self._receipts)>=self.policy.max_steps:raise InvestigationError('step-budget')
            self.session.target.revalidate(self.session.event,self.session.deadline)
            payload=json.loads(source.read_text(encoding='utf-8'))
            if not isinstance(payload,dict):raise InvestigationError('invalid-analysis-snapshot')
            subject=payload.get('target')
            actual=payload.get('target_sha256') or (subject.get('sha256') if isinstance(subject,dict) else None)
            if actual!=self.session.target.sha256:raise InvestigationError('analysis-snapshot-wrong-target')
            record=self.session.evidence.ingest_file(source,source_root=self.workspace,
                expected_sha256=expected_sha256,kind='analysis-snapshot',origin='quartz-builtin-analysis')
            self.session.target.revalidate(self.session.event,self.session.deadline)
            result={'evidence_ids':[record['evidence_id']],'status':'completed',
                    'level':'SOURCE','instruction_authority':False}
            self._receipts[step]={'digest':key,'result':deepcopy(result)}
            return result
        finally:self._lock.release()
