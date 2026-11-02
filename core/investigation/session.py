"""Synchronous evidence scope inside the existing diagnostics worker, not a new job engine."""
from copy import deepcopy
import hashlib
import json
import time

from .contracts import IDENTIFIER, InvestigationError, Target, bounded_json, guard, validate_finding
from .evidence import EvidenceRepository
from .memory import InvestigationMemory

DEFAULT_QUESTION = 'Seçilen uygulamanın doğrulanabilir statik dosya envanteri nedir?'
PIPELINE_REVISION = 'quartz-static-evidence-v1'


class InvestigationSession:
    def __init__(self, value, *, root, event, deadline, tool_identity, question=DEFAULT_QUESTION):
        self.event, self.deadline = event, deadline
        self.question = question
        self.target = Target.capture(value, event, deadline)
        self.tool_fingerprint = hashlib.sha256(json.dumps(
            [PIPELINE_REVISION, bounded_json(tool_identity)], sort_keys=True).encode()).hexdigest()
        self.memory = InvestigationMemory(root)
        self.previous = self.memory.lookup(self.target, question, self.tool_fingerprint, event, deadline)
        self.evidence = EvidenceRepository(root, self.target, event, deadline)
        self.findings = []
        self.raw_rea = None
        self.report = None
        self.prepared = None
        self.contributions = []

    def accept_analysis(self, report, *, executed_capabilities):
        """Claims must cite artifacts already captured by the host gateway."""
        guard(self.event,self.deadline)
        report=bounded_json(report,maximum=512*1024)
        if (not isinstance(report,dict) or report.get('schema_version')!=1
                or report.get('target',{}).get('sha256')!=self.target.sha256
                or not isinstance(report.get('findings'),list) or len(report['findings'])>96):
            raise InvestigationError('invalid-analysis-report')
        capabilities=report.get('capabilities_used',[])
        if (not isinstance(capabilities,list) or len(capabilities)>32
                or any(not isinstance(x,str) or not IDENTIFIER.fullmatch(x) for x in capabilities)
                or not set(capabilities)<=set(executed_capabilities)):
            raise InvestigationError('unobserved-analysis-capability')
        findings=[validate_finding(f,self.evidence.records) for f in report['findings']]
        existing={f['claim_id'] for r in self.contributions for f in r['findings']}
        if len({f['claim_id'] for f in findings})!=len(findings) or existing.intersection(f['claim_id'] for f in findings):
            raise InvestigationError('duplicate-analysis-claim')
        self.contributions.append({'findings':findings,'capabilities_used':capabilities})

    def capture_rea(self, source, *, source_root, expected_sha256):
        self.raw_rea = self.evidence.ingest_file(source, source_root=source_root,
            expected_sha256=expected_sha256, kind='rea-full-artifact', origin='rea-inspect-artifact')
        return {'evidence_id': self.raw_rea['evidence_id'], 'digest': self.raw_rea['digest']}

    def cached_inventory(self):
        record = self.previous
        if not record or 'static_inventory' not in record.get('coverage', []): return None
        result = record.get('reusable_inventory')
        if not isinstance(result, dict) or result.get('status') != 'PASS': return None
        # A valid prior summary must still reference a verified full REA artifact.
        metadata = result.get('evidence', {})
        if (not isinstance(metadata, dict) or metadata.get('artifact_sha256') != self.target.sha256
                or not any(x.get('kind') == 'rea-full-artifact' and x.get('digest') == metadata.get('source_evidence_sha256')
                           for x in record['evidence'].values())): return None
        result = deepcopy(result)
        result.update(used=False, knowledge_reused=True)
        result['message'] = 'Aynı dosya ve araç sürümü için önceki statik kanıt yeniden doğrulandı; yeni çalışma zamanı testi yapılmadı.'
        result['evidence'] = dict(result.get('evidence', {}), historical=True,
                                  observed_at=record['observed_at'])
        return result

    def finish(self, checks, inventory=None):
        guard(self.event, self.deadline)
        self.target.revalidate(self.event, self.deadline)
        checks = bounded_json(checks)
        host = self.evidence.add_json(checks, kind='host-static-checks', origin='host-static-parser')
        records = deepcopy(self.evidence.records)
        if inventory and inventory.get('knowledge_reused'):
            # Retain the actual reused artifact, not an ever-growing chain of
            # historical host summaries from every cache hit.
            for identity, item in self.previous['evidence'].items():
                if item.get('kind') == 'rea-full-artifact': records[identity] = deepcopy(item)
        for check in checks:
            if check.get('status') != 'PASS': continue
            identity = check.get('id')
            if identity not in {'artifact', 'pe', 'rea'}: continue
            claim = {'artifact': 'Seçilen dosyanın kimliği ve SHA-256 değeri doğrulandı.',
                     'pe': 'Seçilen dosyanın sınırlı Windows PE başlığı ayrıştırıldı.',
                     'rea': 'REA sınırlı statik envanteri doğruladı; kod semantiği ve çalışma davranışı çıkarılmadı.'}[identity]
            refs = [host['evidence_id']]
            if identity == 'rea' and self.raw_rea: refs.append(self.raw_rea['evidence_id'])
            elif identity == 'rea' and inventory and inventory.get('knowledge_reused'):
                refs.extend(key for key, item in records.items() if item.get('kind') == 'rea-full-artifact')
            item = {'claim_id': 'static.' + identity, 'claim': claim, 'claim_type':'observation',
                    'evidence_ids':refs, 'confidence_basis':'Kimliği doğrulanan dosya üzerinde yapılandırılmış statik kontrol.',
                    'counter_evidence_ids':[], 'reproducible':True,
                    'limitations':['Statik inceleme; uygulama çalıştırılmadı veya arayüz davranışı test edilmedi.']}
            self.findings.append(validate_finding(item, records))
        advanced=[]
        for contribution in self.contributions:
            self.findings.extend(contribution['findings'])
            advanced.extend(contribution['capabilities_used'])
        coverage = ['host_identity']
        if any(c.get('id') == 'pe' and c.get('status') == 'PASS' for c in checks): coverage.append('pe_header')
        reusable = None
        if inventory and inventory.get('status') == 'PASS' and (self.raw_rea or inventory.get('knowledge_reused')):
            coverage.append('static_inventory')
            reusable = {k:deepcopy(inventory[k]) for k in ('status','message','evidence') if k in inventory}
        self.evidence.finalize('completed')
        self.report = {'schema_version':1, 'investigation_id':self.evidence.id, 'status':'completed',
            'target':self.target.as_dict(), 'findings':self.findings, 'evidence':records, 'coverage':coverage,
            'reusable_inventory':reusable, 'capabilities_used':list(dict.fromkeys(
                (['bounded-pe-header', 'static-inventory'] if reusable else ['host-static-checks'])+advanced)),
            'unsupported':['Runtime/UI verification', 'Function semantics', 'Engine-specific modding'],
            'limitations':['Mevcut statik adaptör kapsamı; daha geniş analiz sağlayıcıları ayrıca yetenek ve kanıt ile bağlanmalıdır.'],
            'knowledge_reused':bool(inventory and inventory.get('knowledge_reused')), 'instruction_authority':False}
        return deepcopy(self.report)

    def prepare_publication(self):
        if self.report is None: raise InvestigationError('incomplete-investigation')
        self.prepared = self.memory.prepare(self.target, self.question, self.tool_fingerprint,
                                            self.report, self.event, self.deadline)

    def publish(self):
        if self.prepared is None: self.prepare_publication()
        return self.memory.commit(self.target, self.prepared, self.event, self.deadline)

    def close(self, *, cancelled=False):
        if self.evidence.state == 'running':
            self.evidence.finalize('cancelled' if cancelled else 'failed')

    def summary(self):
        return {'schema_version':1, 'investigation_id':self.evidence.id,
                'knowledge_reused':bool(self.report and self.report['knowledge_reused']),
                'findings_count':len(self.findings), 'evidence_count':len(self.report['evidence']) if self.report else len(self.evidence.records),
                'context':InvestigationMemory.context(self.previous), 'instruction_authority':False}
