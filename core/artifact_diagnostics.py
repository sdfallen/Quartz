"""GUI-selected executable inspection. No directory scans or target execution."""
from pathlib import Path
import struct
import tempfile
import shutil

from core.self_diagnostics import SelfDiagnosticsService


def selected_executable(value):
    path = Path(value).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('Bağlantılı hedefler incelenmez')
    path = path.resolve(strict=True)
    if (path.suffix.lower() != '.exe' or not path.is_file()
            or path.stat().st_size > 512 * 1024 * 1024
            or any(p.casefold() in {'warbandisland', 'ai_island_test'} for p in path.parts)):
        raise ValueError('Bu dosya izinli uygulama incelemesi kapsamında değil')
    return path


def selected_artifact(value):
    """One native-picker selection; legacy EXE callers keep their strict API."""
    from core.investigation.contracts import safe_path
    path = safe_path(value)
    if (not path.is_file() or path.suffix.casefold() not in {'.exe','.dll','.pyd','.zip','.pkg','.pck'}
            or path.stat().st_size>512*1024*1024):
        raise ValueError('Bu dosya izinli uygulama veya oyun paketi incelemesi kapsamında değil')
    return path


def parse_pe_metadata(stream, file_size: int) -> dict | None:
    """Parse bounded MZ/COFF/OptionalHeader/SectionTable facts without reading code or strings."""
    stream.seek(0)
    header = stream.read(64)
    offset = struct.unpack_from('<I', header, 60)[0] if len(header) == 64 else -1
    if header[:2] != b'MZ' or not (64 <= offset <= min(file_size - 24, 1024 * 1024)):
        return None
    stream.seek(offset)
    coff = stream.read(24)
    if len(coff) != 24 or coff[:4] != b'PE\0\0':
        return None
    machine, sections, _ts, _sym_ptr, _sym_cnt, opt_size, characteristics = struct.unpack_from('<HHIIIHH', coff, 4)
    arch = {0x8664: 'x64', 0x014c: 'x86', 0xaa64: 'arm64'}.get(machine, 'unknown')
    meta = {
        'machine': int(machine),
        'sections': int(sections),
        'architecture': arch,
        'is_dll': bool(characteristics & 0x2000),
        'large_address_aware': bool(characteristics & 0x0020),
    }
    if 2 <= opt_size <= 4096 and offset + 24 + opt_size <= file_size:
        opt = stream.read(opt_size)
        if len(opt) == opt_size:
            magic = struct.unpack_from('<H', opt, 0)[0]
            meta['pe_format'] = {0x20b: 'PE32+', 0x10b: 'PE32'}.get(magic, 'unknown')
            if len(opt) >= 72 and magic in {0x10b, 0x20b}:
                subsystem_code, dll_chars = struct.unpack_from('<HH', opt, 68)
                meta['subsystem'] = {
                    1: 'native',
                    2: 'windows_gui',
                    3: 'windows_cui',
                    10: 'efi',
                    11: 'efi',
                    12: 'efi',
                    13: 'efi',
                }.get(subsystem_code, 'other')
                meta['dynamic_base'] = bool(dll_chars & 0x0040)
                meta['high_entropy_va'] = bool(dll_chars & 0x0020)
                meta['nx_compat'] = bool(dll_chars & 0x0100)
            if 0 < sections <= 96 and offset + 24 + opt_size + sections * 40 <= file_size:
                sec_table = stream.read(sections * 40)
                if len(sec_table) == sections * 40:
                    has_resources = False
                    max_raw_end = 0
                    for idx in range(sections):
                        entry = sec_table[idx * 40:(idx + 1) * 40]
                        raw_name = entry[:8].split(b'\0', 1)[0].decode('ascii', 'ignore').strip().lower()
                        if raw_name == '.rsrc':
                            has_resources = True
                        raw_size, raw_ptr = struct.unpack_from('<II', entry, 16)
                        if raw_ptr > 0 and raw_size > 0:
                            end = raw_ptr + raw_size
                            if end > max_raw_end:
                                max_raw_end = end
                    meta['has_resources'] = has_resources
                    if max_raw_end > 0:
                        overlay = max(0, file_size - max_raw_end)
                        meta['has_overlay'] = overlay > 0
                        meta['overlay_bytes'] = int(overlay)
    return meta


class ArtifactDiagnosticsService(SelfDiagnosticsService):
    SCOPE = 'artifact'

    def __init__(self, selected_path, *, knowledge=None, question=None, investigation_root=None,
                 investigation=True, analyzer=None, analysis_enabled=True,
                 workbench=None, tool_specs=None, tool_effects=(), registered_search=None,
                 workbench_factory=None, **kwargs):
        self.target = selected_artifact(selected_path)
        stat = self.target.stat()
        self.identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        super().__init__(**kwargs)
        from core.investigation.session import DEFAULT_QUESTION
        self.question = question or DEFAULT_QUESTION
        if not isinstance(self.question, str) or not 1 <= len(self.question.strip()) <= 2000:
            raise ValueError('İnceleme sorusu geçersiz')
        self.investigation_root = Path(investigation_root) if investigation_root is not None else self.reports.parent / 'investigations'
        self.investigation_enabled = bool(investigation)
        self._investigations = {}
        self._inventories = {}
        self.analyzer = analyzer
        self.analysis_enabled = bool(analysis_enabled)
        # External tool authority stays in ToolWorkbench. Without an injected
        # workbench the gateway keeps its previous behaviour (builtin parser
        # only); supplying one does not widen effects by itself.
        self.workbench = workbench
        self.tool_specs = dict(tool_specs) if tool_specs else {}
        effects = frozenset(tool_effects or ())
        if not effects <= {'read_target', 'write_workspace', 'execute_tool'}:
            raise ValueError('Desteklenmeyen inceleme aracı etkisi')
        if effects and workbench is None:
            raise ValueError('Araç etkisi için doğrulanmış bir workbench gerekir')
        self.tool_effects = effects
        if registered_search is not None:
            from core.investigation.contracts import bounded_json
            registered_search = bounded_json(registered_search, maximum=2048)
            if (not isinstance(registered_search,dict) or set(registered_search)!={'pattern'}
                    or not isinstance(registered_search['pattern'],str) or not 1<=len(registered_search['pattern'])<=512
                    or any(c in registered_search['pattern'] for c in ('\x00','\r','\n'))):
                raise ValueError('Geçersiz dize araması')
        self.registered_search = registered_search
        self._workbench_factory = workbench_factory
        self._owned_workbench = None
        self._tool_approvals = {}
        self._workspaces = {}
        self._gateways = {}
        self._gateway_cleanup = {}
        self._investigation_closed = False
        if knowledge is False:
            self.knowledge = None
        elif knowledge is not None:
            self.knowledge = knowledge
        else:
            from core.application_knowledge import ApplicationKnowledge
            reports_dir = kwargs.get('reports')
            knowledge_root = (Path(reports_dir).parent / 'application-knowledge') if reports_dir is not None else None
            self.knowledge = ApplicationKnowledge(knowledge_root)

    def _on_completed(self, identity, snapshot):
        if self.knowledge is not None:
            try:
                self.knowledge.save(self.target, snapshot)
                snapshot['knowledge_saved'] = True
            except Exception:
                snapshot['knowledge_saved'] = False
        session = self._investigations.get(identity)
        if session is not None:
            try:
                session.prepare_publication()
            except (OSError, ValueError) as exc:
                if str(exc) in {'target-changed', 'file-changed'}:
                    raise
                snapshot['investigation_knowledge_saved'] = False
            snapshot['investigation'] = session.summary()

    def start(self, include_rea=True):
        with self.lock:
            if self._investigation_closed:
                raise RuntimeError('İnceleme kapanmış; yeni iş başlatılmadı.')
            if any(x.get('status')!='confirmed' for x in self._gateway_cleanup.values()):
                raise RuntimeError('Önceki inceleme aracının kapanışı doğrulanmalı.')
            result=super().start(include_rea)
            self._tool_approvals.setdefault(result['id'], None)
            # The existing diagnostics inventory is bounded to five jobs. Drop
            # matching completed domain scopes too; retain unconfirmed owners.
            for old in set(self._investigations)-set(self.jobs):
                if self._gateway_cleanup.get(old,{}).get('status','confirmed')=='confirmed':
                    self._investigations.pop(old,None);self._inventories.pop(old,None)
                    self._gateways.pop(old,None);self._gateway_cleanup.pop(old,None)
                    self._tool_approvals.pop(old,None)
                    if not self._workspaces.get(old):self._workspaces.pop(old,None)
            return result

    def authorize_registered_tool(self, job_id, granted):
        """Only the validated, task-bound GUI approval adapter calls this."""
        with self.lock:
            if (type(granted) is not bool or self.registered_search is None or self._investigation_closed
                    or job_id != self.latest or job_id not in self.jobs
                    or self.jobs[job_id]['state'] != 'running' or self.events[job_id].is_set()
                    or self._tool_approvals.get(job_id) is not None):
                raise ValueError('Dize araması onayı güncel işe ait değil')
            self._tool_approvals[job_id] = granted

    def _commit_completed(self, identity, snapshot):
        session = self._investigations.get(identity)
        if session is not None and session.prepared is not None:
            try:
                record = session.publish()
                snapshot['investigation_knowledge_saved'] = True
                from core.investigation.memory import InvestigationMemory
                snapshot['investigation']['context'] = InvestigationMemory.context(record)
            except (OSError, ValueError):
                snapshot['investigation_knowledge_saved'] = False

    def _inspect(self, identity, event, deadline, include_rea):
        from core.investigation.contracts import Cancelled
        from core.investigation.session import InvestigationSession
        from core.self_diagnostics import InspectionCancelled
        from core.rea_adapter import ReaAdapter
        session = None
        try:
            if self.investigation_enabled:
                tool_identity = (ReaAdapter.runtime_identity() if include_rea and self.rea is None else
                                 {'provider':'injected-analyzer', 'type':type(self.rea).__name__})
                if self.analysis_enabled:
                    from core.rea_analysis import AnalysisService
                    from core.rea_analysis.service import PARSER_VERSION
                    analyzer = self.analyzer or AnalysisService()
                    version = getattr(analyzer, 'runtime_identity', None)
                    tool_identity = {'inventory':tool_identity,
                        'analysis':version() if callable(version) else PARSER_VERSION}
                session = InvestigationSession(self.target, root=self.investigation_root,
                    event=event, deadline=deadline, tool_identity=tool_identity, question=self.question)
                self._investigations[identity] = session
            self._inspect_static(identity, event, deadline, include_rea, session)
            if session is not None:
                if self.analysis_enabled:
                    self._inspect_structure(identity,event,deadline,session,analyzer)
                if self.registered_search is not None:
                    self._inspect_registered_tool(identity,event,deadline,session)
                session.finish(self.status(identity)['checks'], self._inventories.get(identity))
                self._update(identity, investigation=session.summary())
        except Cancelled as exc:
            raise InspectionCancelled() from exc
        except Exception as exc:
            if event.is_set():
                raise InspectionCancelled() from exc
            raise
        finally:
            if session is not None:
                session.close(cancelled=event.is_set())

    def _inspect_structure(self, identity, event, deadline, session, analyzer):
        from core.investigation.contracts import bounded_json, safe_path
        from core.investigation.gateway import InvestigationToolGateway
        from core.investigation.planning import InvestigationPolicy
        self._update(identity,phase='analysis',progress=80,message='Dosyanın yapı ve bağımlılık ilişkileri inceleniyor…')
        root=safe_path(self.investigation_root/'workspaces',exists=False);root.mkdir(parents=True,exist_ok=True)
        folder=tempfile.mkdtemp(prefix='analysis-',dir=root)
        self._workspaces.setdefault(identity,set()).add(folder)
        gateway=None
        try:
            gateway=InvestigationToolGateway(session,self.workbench,workspace=folder,
                policy=InvestigationPolicy(effects=frozenset({'read_target','write_workspace'})|self.tool_effects,max_output_bytes=4*1024*1024),
                tool_specs=self.tool_specs)
            self._gateways[identity]=gateway
            try:
                catalog=bounded_json(analyzer.capabilities(session.target.as_dict()))
                available={c['capability_id'] for c in catalog if isinstance(c,dict) and c.get('available') is True}
                request={'investigation_id':session.evidence.id,'step_id':'structure',
                    'operation':'analyze_structure','tool_id':'quartz-builtin-analysis',
                    'target':session.target.as_dict(),'workspace':folder,'options':{},
                    'deadline_monotonic':deadline,'max_output_bytes':4*1024*1024}
                report=bounded_json(analyzer.analyze(request,gateway,event),maximum=512*1024)
                self._guard(event,deadline)
                cleanup=report.get('cleanup_receipt') if isinstance(report,dict) else None
                if not isinstance(cleanup,dict) or cleanup.get('status')!='confirmed':
                    self._check(identity,'analysis','UNKNOWN','Yapı çözümlemesi','Analiz temizliği doğrulanmadı; sonuç kabul edilmedi.')
                    return
                if report.get('errors') or not report.get('findings'):
                    self._check(identity,'analysis','UNKNOWN','Yapı çözümlemesi',
                        'Desteklenen yapı ilişkileri doğrulanamadı; bu durum uygulamanın bozuk olduğunu kanıtlamaz.',
                        unsupported=report.get('unsupported',[])[:12])
                    return
                session.accept_analysis(report,executed_capabilities=available)
                self._check(identity,'analysis','PASS','Yapı ve bağımlılık çözümlemesi',
                    'Desteklenen dosya ilişkileri gerçek kaynak kanıtına bağlandı; çalışma davranışı test edilmedi.',
                    capabilities=report['capabilities_used'],findings=len(report['findings']),
                    unsupported=report.get('unsupported',[])[:12])
            finally:
                self._close_gateway(identity,gateway)
        finally:
            if gateway is None:self._close_gateway(identity,None)
            self._cleanup_workspaces(identity)

    def _cleanup_workspaces(self, identity):
        """Never delete a workspace while an owned tool/drain remains pending."""
        from core.investigation.contracts import safe_path
        if self._gateway_cleanup.get(identity,{}).get('status')!='confirmed': return
        paths=list(self._workspaces.get(identity,set()))
        if not paths:return
        root=safe_path(self.investigation_root/'workspaces',exists=False)
        for value in paths:
            path=safe_path(value,exists=False)
            if root not in path.parents or path.parent!=root:
                self._gateway_cleanup[identity]={'status':'failed','reason':'workspace-outside-owner'}
                return
            try:
                if path.exists():shutil.rmtree(path)
                self._workspaces[identity].discard(value)
            except OSError:
                self._gateway_cleanup[identity]={'status':'failed','reason':'workspace-cleanup-failed'}
                return

    def _close_gateway(self, identity, gateway):
        try:
            receipt=gateway.close() if gateway is not None else {'status':'confirmed'}
            if not isinstance(receipt,dict) or receipt.get('status') not in {'confirmed','pending','failed'}:
                receipt={'status':'failed','reason':'invalid-cleanup-receipt'}
        except Exception:
            receipt={'status':'failed','reason':'gateway-close-failed'}
        self._gateway_cleanup[identity]=receipt
        return receipt

    def _inspect_registered_tool(self, identity, event, deadline, session):
        from core.investigation.gateway import InvestigationToolGateway
        from core.investigation.planning import InvestigationPolicy
        from core.investigation.contracts import safe_path
        self._update(identity,phase='tool_permission',progress=85,
            message='Seçilen dosyada dize araması için araç onayı bekleniyor…')
        while True:
            self._guard(event,deadline)
            with self.lock: approved=self._tool_approvals.get(identity)
            if approved is not None:break
            event.wait(.1)
        if approved is False:
            self._check(identity,'registered_tool','NOT_TESTED','Kayıtlı araç araması',
                'Araç çalıştırma izni verilmedi; dize araması yapılmadı.')
            return
        if self._gateway_cleanup.get(identity,{}).get('status','confirmed')!='confirmed':
            self._check(identity,'registered_tool','UNKNOWN','Kayıtlı araç araması',
                'Önceki analiz temizliği doğrulanmadığı için araç başlatılmadı.')
            return
        session.target.revalidate(event,deadline)
        root=safe_path(self.investigation_root/'workspaces',exists=False);root.mkdir(parents=True,exist_ok=True)
        from core.tool_workbench import ToolWorkbench
        factory=self._workbench_factory or ToolWorkbench
        if self._owned_workbench is not None:
            previous=self._owned_workbench.close()
            if not isinstance(previous,dict) or previous.get('status')!='confirmed':
                raise RuntimeError('Önceki araç sahibi kapanmadan yenisi oluşturulamaz')
        self._guard(event,deadline)
        self._owned_workbench=factory(workspace_dir=root)
        resolution=self._owned_workbench.resolve({'capability_id':'binary_string_search'})
        manifest=resolution.get('manifest') if isinstance(resolution,dict) else None
        if (not isinstance(manifest,dict) or resolution.get('status')!='resolved'
                or manifest.get('tool_id')!='ripgrep'):
            self._check(identity,'registered_tool','NOT_TESTED','Kayıtlı araç araması',
                'Bu platform için doğrulanmış kayıtlı dize aracı bulunamadı.')
            return
        folder=tempfile.mkdtemp(prefix='tool-',dir=root)
        self._workspaces.setdefault(identity,set()).add(folder)
        gateway=InvestigationToolGateway(session,self._owned_workbench,workspace=folder,
            policy=InvestigationPolicy(effects=frozenset({'read_target','write_workspace','execute_tool'}),allow_acquire=True),
            tool_specs={'ripgrep':{'source_url':manifest['source_url'],'pinned_revision':manifest['pinned_revision'],
                'package_digest':manifest['package_digest'],'operations':['strings'],
                'effects':['read_target','write_workspace','execute_tool']}})
        self._gateways[identity]=gateway
        try:
            self._update(identity,phase='tool_acquire',progress=88,message='Kayıtlı araç sürümü ve dosyaları doğrulanıyor…')
            self._owned_workbench.acquire('ripgrep',cancel_event=event,deadline_monotonic=deadline)
            self._guard(event,deadline)
            receipt=gateway.execute({'investigation_id':session.evidence.id,'step_id':'registered-strings',
                'tool_id':'ripgrep','operation':'strings','target':session.target.as_dict(),
                'workspace':folder,'options':{'pattern':self.registered_search['pattern']},
                'max_output_bytes':512*1024},event)
            self._guard(event,deadline)
            no_match=(receipt.get('status')=='failed' and receipt.get('exit_code')==1 and receipt.get('stderr_bytes')==0
                and receipt.get('stdout_bytes')==0)
            passed=receipt.get('status')=='completed' or no_match
            self._check(identity,'registered_tool','PASS' if passed else 'UNKNOWN','Kayıtlı araç araması',
                ('Dize araması tamamlandı; eşleşme bulunmadı.' if no_match else
                 'Dize araması gerçek araçla tamamlandı; çıktı kalıcı kanıta bağlandı.') if passed else
                'Araç araması tamamlanamadı; uygulamanın hatalı olduğu sonucu çıkarılmadı.',
                tool_id='ripgrep',exit_code=receipt.get('exit_code'),evidence_ids=receipt.get('evidence_ids',[]),
                stdout_bytes=receipt.get('stdout_bytes'),stderr_bytes=receipt.get('stderr_bytes'))
            if passed:
                session.accept_analysis({'schema_version':1,'target':session.target.as_dict(),
                    'capabilities_used':['registered-string-search'],'findings':[{
                        'claim_id':'registered.strings','claim':('Kayıtlı araç seçilen dosyada eşleşme bulmadı.' if no_match else
                        'Kayıtlı araç seçilen dosyada dize araması yürüttü; çıktı bayt sayısı: '+str(receipt.get('stdout_bytes',0))),
                        'claim_type':'observation','evidence_ids':receipt['evidence_ids'],
                        'confidence_basis':'Hedef hash kontrolü, sabit araç kimliği ve gerçek süreç çıkış kaydı.',
                        'counter_evidence_ids':[],'reproducible':True,
                        'limitations':['Dize araması SOURCE kanıtıdır; fonksiyon semantiği, uygulama onarımı veya GUI doğrulaması değildir.']}]},
                    executed_capabilities=['registered-string-search'])
        finally:
            self._close_gateway(identity,gateway)
            self._update(identity,tool_cleanup=self._gateway_cleanup[identity])
            self._cleanup_workspaces(identity)

    def shutdown(self):
        with self.lock:self._investigation_closed=True
        super().shutdown()
        for identity,gateway in list(self._gateways.items()):
            self._close_gateway(identity,gateway)
            self._cleanup_workspaces(identity)
        bench_cleanup=self._owned_workbench.close() if self._owned_workbench is not None else {'status':'confirmed'}
        states=[x.get('status','pending') for x in self._gateway_cleanup.values()]
        states.append(bench_cleanup.get('status','pending'))
        for identity,receipt in list(self._gateway_cleanup.items()):
            if identity in self.jobs and 'tool_cleanup' in self.jobs[identity]:
                status=('failed' if 'failed' in {receipt.get('status'),bench_cleanup.get('status')} else
                        'pending' if {receipt.get('status'),bench_cleanup.get('status')} != {'confirmed'} else 'confirmed')
                self._update(identity,tool_cleanup={'status':status})
        status='pending' if any(t.is_alive() for t in self.threads.values()) or 'pending' in states else 'failed' if 'failed' in states else 'confirmed'
        return {'status':status,'components':{'analysis_gateways':dict(self._gateway_cleanup),'registered_workbench':bench_cleanup}}

    def _inspect_static(self, identity, event, deadline, include_rea, session=None):
        target = selected_artifact(self.target)
        stat = target.stat()
        if self.identity != (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns):
            raise ValueError('Seçilen dosya değişti; yeniden seçilmeli')
        self._update(identity, phase='scope', progress=10,
                     message='Seçilen uygulama çalıştırılmadan inceleniyor…',
                     limitations=['Yalnız seçilen dosya okunur; komşu dosyalar, hesaplar ve günlükler taranmaz.',
                                  'Statik dosya incelemesi; güvenlik, ekran davranışı veya hatasız çalışma garantisi değildir.'])
        digest = self._hash(target, event, deadline)
        self._check(identity, 'artifact', 'PASS', 'Seçilen dosya',
                    'Dosya kimliği ve SHA-256 kaydedildi; uygulama çalıştırılmadı.',
                    sha256=digest, bytes=stat.st_size)
        # Parse only a bounded PE header, never imports, code or embedded strings.
        with target.open('rb') as stream:
            pe_meta = parse_pe_metadata(stream, stat.st_size)
            if pe_meta is not None:
                self._check(identity, 'pe', 'PASS', 'Windows dosya başlığı',
                            'PE başlığı ve mimari yapısı okunabildi; bu bir çalıştırma testi değildir.',
                            **pe_meta)
            else:
                self._check(identity, 'pe', 'UNKNOWN', 'Windows dosya başlığı',
                            'Desteklenen PE başlığı doğrulanamadı.')
        self._guard(event, deadline)
        if include_rea:
            from core.rea_adapter import ReaAdapter
            result = session.cached_inventory() if session is not None else None
            if result is None:
                adapter = self.rea or ReaAdapter()
                options = {'event':event, 'deadline':deadline}
                if session is not None and getattr(adapter, 'supports_evidence_sink', False) is True:
                    options['evidence_sink'] = session.capture_rea
                result = adapter.inspect(target, **options)
            self._inventories[identity] = result
            self._guard(event, deadline)
            self._check(identity, 'rea', result['status'], 'REA statik incelemesi',
                        result['message'], **result.get('evidence', {}))
            self._update(identity, rea_used=bool(result.get('used')))
        else:
            self._check(identity, 'rea', 'NOT_TESTED', 'REA', 'REA kullanılmadı.')
        if self._hash(target, event, deadline) != digest:
            raise ValueError('İnceleme sırasında dosya değişti')
