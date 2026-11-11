"""JSON v1 analysis facade. Static facts are host-captured SOURCE evidence.

The host supplies workspace ownership, scope, cancellation and evidence capture.
External tools always cross its injected execute boundary; there is no downloader,
subprocess launcher, target writer or global evidence store in this package.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading
import time
import types
import uuid

from core.investigation.contracts import (Cancelled, IDENTIFIER, InvestigationError, Target,
    bounded_json, fingerprint, guard, safe_path)
from .binary import FormatError, PE
from .managed import inspect_managed
from .packages import inspect_pck, inspect_pyinstaller, inspect_zip

PARSER_VERSION = 'quartz-structure-v1'
MAX_INPUT = 128 * 1024 * 1024
MAX_REPORT = 512 * 1024


def _semantic_value(value):
    """Canonical loaded code/data, without source paths or debug line tables."""
    if isinstance(value, types.CodeType):
        fields = ('co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals',
                  'co_stacksize', 'co_flags', 'co_code', 'co_consts', 'co_names',
                  'co_varnames', 'co_freevars', 'co_cellvars', 'co_exceptiontable')
        return {'code': {key: _semantic_value(getattr(value, key)) for key in fields}}
    if isinstance(value, types.FunctionType):
        return {'function': _semantic_value(value.__code__), 'defaults': _semantic_value(value.__defaults__),
                'kwdefaults': _semantic_value(value.__kwdefaults__)}
    if isinstance(value, bytes):
        return {'bytes': value.hex()}
    if isinstance(value, (tuple, list)):
        return [_semantic_value(x) for x in value]
    if isinstance(value, (set, frozenset)):
        return {'set': sorted((_semantic_value(x) for x in value), key=lambda x: json.dumps(x, sort_keys=True))}
    if isinstance(value, dict):
        return {str(k): _semantic_value(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if value is Ellipsis:
        return {'ellipsis': True}
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError('unsupported-runtime-identity-value')


def _target(value):
    if isinstance(value, Target):
        return value
    if not isinstance(value, dict) or set(value) != set(Target.__dataclass_fields__):
        raise InvestigationError('invalid-analysis-target')
    try:
        target = Target(**dict(value, version_fingerprint=tuple(value['version_fingerprint']), approved_scope=tuple(value['approved_scope'])))
    except (TypeError, ValueError):
        raise InvestigationError('invalid-analysis-target') from None
    if ('read_target' not in target.approved_scope or not isinstance(target.sha256, str)
            or len(target.sha256) != 64 or type(target.size) is not int or not 0 <= target.size <= MAX_INPUT):
        raise InvestigationError('invalid-analysis-target')
    return target


class AnalysisService:
    """Reads one already-approved file; capabilities() does not execute tools."""

    @staticmethod
    def runtime_identity():
        # Use already loaded objects. No file/loader reads, subprocess or source
        # availability requirement, including in a PyInstaller frozen process.
        import sys
        from . import binary, managed, packages
        modules = [binary, managed, packages, sys.modules[__name__]]
        identity = {}
        for module in modules:
            contents = {}
            for name, value in vars(module).items():
                if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
                    contents[name] = _semantic_value(value)
                elif isinstance(value, type) and value.__module__ == module.__name__:
                    members = {'__bases__': [base.__module__ + '.' + base.__qualname__ for base in value.__bases__]}
                    for member_name, member in vars(value).items():
                        descriptor = type(member).__name__
                        if isinstance(member, (staticmethod, classmethod)):
                            member = member.__func__
                        if isinstance(member, types.FunctionType) or (member_name.isupper() and type(member) in (str, int, float, bool, list, tuple, dict)):
                            members[member_name] = {'descriptor': descriptor, 'value': _semantic_value(member)}
                    contents[name] = members
                elif name.isupper() and type(value) in (str, int, float, bool, list, tuple, dict):
                    contents[name] = _semantic_value(value)
            identity[module.__name__] = contents
        raw = json.dumps(identity, sort_keys=True, ensure_ascii=True, allow_nan=False).encode('ascii')
        return {'provider': 'quartz-builtin-analysis', 'parser_version': PARSER_VERSION, 'schema_version': 1,
                'code_sha256': hashlib.sha256(raw).hexdigest(), 'python_bytecode': sys.implementation.cache_tag,
                'python_version': list(sys.version_info[:3]),
                'identity_basis': 'loaded-functions-and-parser-constants', 'available': True}

    def capabilities(self, target):
        try:
            value = _target(target)
            path = safe_path(value.canonical_path)
            available = path.is_file() and path.stat().st_size <= MAX_INPUT and fingerprint(path) == value.version_fingerprint
            with path.open('rb') as stream:
                header = stream.read(64)
                is_pe = header[:2] == b'MZ'
                is_managed = False
                if is_pe and len(header) >= 64:
                    stream.seek(int.from_bytes(header[60:64], 'little'))
                    coff = stream.read(24)
                    if coff[:4] == b'PE\0\0' and len(coff) == 24:
                        optional = stream.read(int.from_bytes(coff[20:22], 'little'))
                        start = 112 if optional[:2] == b'\x0b\x02' else 96
                        is_managed = (len(optional) >= start + 15 * 8
                            and int.from_bytes(optional[start - 4:start], 'little') >= 15
                            and int.from_bytes(optional[start + 14 * 8:start + 14 * 8 + 4], 'little') != 0)
                    else:
                        is_pe = False
                stream.seek(max(0, value.size - 8 * 1024 * 1024))
                tail = stream.read(8 * 1024 * 1024)
                is_package = header[:2] == b'PK' or header[:4] == b'GDPC' or b'MEI\x0c\x0b\x0a\x0b\x0e' in tail
        except (InvestigationError, OSError, TypeError):
            available = False
            is_pe = is_package = is_managed = False
        definitions = [
            ('pe-structure', ['pe'], [], ['No disassembly, call graph, runtime observation or signature trust.']),
            ('dotnet-metadata', ['pe'], [], ['ECMA-335 table metadata; no IL semantics; pointer tables unsupported.']),
            ('package-inventory', ['zip', 'pyinstaller', 'pe', 'godot-pck'], [], ['Inventory only; no extraction, execution or bytecode decompilation.']),
            ('engine-signatures', ['pe', 'zip', 'pyinstaller', 'godot-pck'], [], ['Structural dependencies identify references; strings alone remain hypotheses.']),
            ('native-disassembly', ['pe'], ['external-disassembler'], ['An injected, pinned external provider is required; none is bundled.']),
            ('runtime-observation', ['pe'], ['host-runtime-provider'], ['Unavailable in this read-only facade.']),
        ]
        result = []
        for key, formats, required, limits in definitions:
            applicable = {'pe-structure': is_pe, 'dotnet-metadata': is_managed,
                          'package-inventory': is_package, 'engine-signatures': is_pe or is_package}.get(key, False)
            effects = ['read_target', 'write_workspace']
            if key == 'runtime-observation':
                effects += ['attach_runtime', 'execute_target']
            elif required:
                effects += ['execute_tool']
            result.append({'capability_id': key, 'provider': PARSER_VERSION, 'supported_formats': formats,
                 'effects': effects, 'required_tools': required,
                'available': available and applicable and not required,
                'limitations': limits + ['128 MiB input maximum; availability is a structural header probe, revalidated before analysis.']})
        return result

    def analyze(self, request, tool_executor, cancel_event=None):
        event = cancel_event if cancel_event is not None else threading.Event()
        report = {'schema_version': 1, 'target': {}, 'capabilities_used': [], 'findings': [], 'artifacts': [],
                  'unsupported': ['Runtime/UI behavior and target execution', 'Instruction disassembly and code xrefs'],
                  'errors': [], 'cancellation': {'cancelled': False},
                  'cleanup_receipt': {'status': 'confirmed', 'scope': 'builtin-parser', 'processes_started': 0, 'target_write_performed': False}}
        created = None
        try:
            request = bounded_json(request, maximum=128 * 1024)
            if not isinstance(request, dict):
                raise InvestigationError('invalid-analysis-request')
            target = _target(request.get('target'))
            report['target'] = target.as_dict()
            for key in ('investigation_id', 'step_id'):
                if not isinstance(request.get(key), str) or not IDENTIFIER.fullmatch(request[key]):
                    raise InvestigationError('invalid-analysis-request')
            deadline = request.get('deadline_monotonic')
            if not isinstance(deadline, (int, float)) or isinstance(deadline, bool):
                raise InvestigationError('invalid-analysis-deadline')
            guard(event, deadline)
            options = request.get('options', {})
            if not isinstance(options, dict) or set(options) - {'external_tool'}:
                raise InvestigationError('invalid-analysis-options')
            limit = request.get('max_output_bytes', MAX_REPORT)
            if type(limit) is not int or not 1024 <= limit <= 16 * 1024 * 1024:
                raise InvestigationError('invalid-analysis-output-limit')
            workspace = safe_path(request.get('workspace', ''))
            source = safe_path(target.canonical_path)
            if workspace == source.parent or workspace == source or not workspace.is_dir():
                raise InvestigationError('invalid-analysis-workspace')
            policy = getattr(tool_executor, 'policy', None)
            if policy is not None and not {'read_target', 'write_workspace'} <= policy.effects:
                raise InvestigationError('analysis-workspace-write-not-authorized')
            capture = getattr(tool_executor, 'capture_analysis', None)
            if not callable(capture):
                raise InvestigationError('analysis-evidence-capture-unavailable')
            target.revalidate(event, deadline)
            before = fingerprint(source)
            data = bytearray()
            with source.open('rb') as stream:
                while block := stream.read(256 * 1024):
                    guard(event, deadline)
                    data.extend(block)
                    if len(data) > MAX_INPUT or len(data) > target.size:
                        raise InvestigationError('analysis-file-limit')
            if len(data) != target.size or fingerprint(source) != before or hashlib.sha256(data).hexdigest() != target.sha256:
                raise InvestigationError('target-changed')
            data = bytes(data)
            check = lambda: guard(event, deadline)
            snapshot = {'schema_version': 1, 'parser': PARSER_VERSION, 'target_sha256': target.sha256,
                        'evidence_level': 'SOURCE', 'runtime_observed': False, 'observations': {}}
            observations = snapshot['observations']
            capabilities = []
            if data.startswith(b'MZ'):
                pe = PE(data, check)
                observations['pe'] = pe.inspect()
                capabilities.append('pe-structure')
                managed = inspect_managed(pe)
                if managed is not None:
                    observations['managed'] = managed
                    capabilities.append('dotnet-metadata')
            if data.startswith(b'GDPC'):
                package = inspect_pck(data, check)
            elif data.startswith(b'PK\x03\x04') or data.startswith(b'PK\x05\x06'):
                package = inspect_zip(data, check)
            else:
                package = inspect_pyinstaller(data, check)
            if package:
                observations['package'] = package
                capabilities.append('package-inventory')
            if not observations:
                report['unsupported'].append('Unrecognized format; supported: PE/CLI, classic ZIP, PyInstaller 2.1+ CArchive, unencrypted Godot PCK v2/v3/v4')
                return report
            drafts = self._findings(observations)
            if any(x['claim_id'].startswith('analysis.engine.') for x in drafts):
                capabilities.append('engine-signatures')
            raw = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf-8')
            if len(raw) > min(limit, 4 * 1024 * 1024):
                raise InvestigationError('analysis-snapshot-output-limit')
            guard(event, deadline)
            created = workspace / ('analysis-' + uuid.uuid4().hex + '.json')
            with created.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            target.revalidate(event, deadline)
            capture_request = dict(request, operation='builtin-analysis-snapshot', tool_id='quartz-builtin-analysis')
            receipt = capture(str(created), hashlib.sha256(raw).hexdigest(), capture_request, event)
            guard(event, deadline)
            receipt = bounded_json(receipt)
            refs = receipt.get('evidence_ids') if isinstance(receipt, dict) else None
            if (not isinstance(refs, list) or not 1 <= len(refs) <= 32
                    or any(not isinstance(x, str) or not IDENTIFIER.fullmatch(x) for x in refs)
                    or receipt.get('instruction_authority') is not False):
                raise InvestigationError('invalid-analysis-capture-receipt')
            for draft in drafts:
                draft['evidence_ids'] = list(refs)
            report['findings'] = drafts
            report['capabilities_used'] = capabilities
            report['artifacts'] = [{'snapshot_name': created.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'evidence_ids': refs,
                                    'kind': 'structural-snapshot', 'level': 'SOURCE'}]
            if options.get('external_tool') is not None:
                self._external(options['external_tool'], request, tool_executor, event, report)
            target.revalidate(event, deadline)
            if len(json.dumps(report, ensure_ascii=False, allow_nan=False).encode('utf-8')) > min(limit, MAX_REPORT):
                raise InvestigationError('analysis-report-output-limit')
            report = bounded_json(report, maximum=MAX_REPORT)
        except Cancelled:
            report['cancellation'] = {'cancelled': True, 'reason': 'cancelled'}
            # Partial results are not presented as accepted findings.
            report['findings'], report['capabilities_used'] = [], []
        except (InvestigationError, FormatError, OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            code = str(exc) if isinstance(exc, (InvestigationError, FormatError)) else 'analysis-io-or-format-error'
            report['errors'].append({'code': code[:160]})
            report['findings'], report['capabilities_used'] = [], []
        finally:
            if created is not None:
                try:
                    created.unlink(missing_ok=True)
                except OSError:
                    report['cleanup_receipt'] = {'status': 'failed', 'scope': 'builtin-parser', 'processes_started': 0, 'target_write_performed': False,
                                                  'reason': 'snapshot-cleanup-failed'}
        return report

    @staticmethod
    def _findings(observations):
        result = []
        def add(key, claim, basis, *, hypothesis=False, limitations=None):
            result.append({'claim_id': 'analysis.' + key, 'claim': claim, 'claim_type': 'hypothesis' if hypothesis else 'observation',
                'confidence_basis': basis, 'evidence_ids': [], 'counter_evidence_ids': [], 'reproducible': True,
                'limitations': limitations or ['Static SOURCE evidence; no application behavior or mod compatibility was tested.']})
        pe = observations.get('pe')
        if pe:
            libraries = [x['library'] for x in pe['imports']]
            add('pe', f"PE{pe['bits']} machine={pe['machine']}; {len(pe['sections'])} sections; entry RVA={hex(pe['entry_point_rva'])}.", 'Validated PE/COFF headers and file-backed section mappings.')
            add('native.dependencies', f"Import table declares {len(libraries)} libraries and {sum(len(x['symbols']) for x in pe['imports'])} symbols: {', '.join(libraries)[:2400]}.", 'DLL descriptors and Import Lookup Table entries map named/ordinal symbols to IAT RVAs; these are linkage dependencies, not observed calls.')
            if pe['exports']:
                add('native.exports', f"Export Address Table contains {len(pe['exports'])} nonzero addresses with ordinal/name/RVA and forwarder relationships in the snapshot.", 'Validated export directory, name/ordinal arrays and address table.', limitations=['An exported function is not automatically a supported mod API; no signature or ABI compatibility tested.'])
            if pe['runtime_functions']:
                add('native.ranges', f"x64 exception directory declares {len(pe['runtime_functions'])} begin/end/unwind function relationships.", 'Parsed IMAGE_RUNTIME_FUNCTION_ENTRY records; ranges have file backing.', limitations=['Unwind ranges are structural boundaries; no instructions, call graph or function semantics decoded.'])
            if any(x.casefold() == 'unityplayer.dll' for x in libraries):
                add('engine.unity', 'The PE structurally imports UnityPlayer.dll; this is a Unity player linkage indicator.', 'Actual import descriptor names UnityPlayer.dll.', limitations=['Engine version and successful loading are unverified.'])
            loading = [s['name'] for lib in pe['imports'] for s in lib['symbols'] if s.get('name') in ('LoadLibraryA', 'LoadLibraryW', 'LoadLibraryExA', 'LoadLibraryExW', 'GetProcAddress')]
            if loading:
                add('modding.loader', 'Declared dynamic-library loading boundary: ' + ', '.join(sorted(set(loading))) + '.', 'Named symbols in actual PE import thunks.', limitations=['This is a declared loader dependency, not evidence of plugin discovery, mod support or exercised calls.'])
        managed = observations.get('managed')
        if managed:
            refs = [r['name'] for r in managed['assembly_references']]
            add('managed.metadata', f"CLI metadata {managed['runtime_metadata_version']}: {len(managed['types'])} types, {len(managed['methods'])} MethodDefs; assemblies " + ', '.join(x['name'] + ' ' + x['version'] for x in managed['assemblies'])[:1500] + '.', 'Validated CLI header, BSJB streams and ECMA-335 metadata table layouts; TypeDef.MethodList defines actual method ownership.')
            add('managed.dependencies', 'AssemblyRef dependencies: ' + (', '.join(refs)[:2500] or '(none)') + '.', 'AssemblyRef rows carry assembly identity/version; references do not prove runtime resolution.')
            public_tokens = {token for kind in managed['types'] if kind['flags'] & 7 == 1 for token in kind['method_tokens']}
            public_methods = [m for m in managed['methods'] if m['token'] in public_tokens and m['flags'] & 7 == 6]
            if public_methods:
                add('managed.surface', f"Metadata declares {len(public_methods)} public methods on top-level public types; owner tokens and signature blob indexes are recorded.", 'TypeAttributes visibility, MethodAttributes.MemberAccessMask and TypeDef.MethodList relationships.', limitations=['Declared CLR API surface only; nested-type accessibility, supported extension API, ABI signatures and runtime invocation are unverified.'])
            if managed['pinvoke']:
                add('managed.pinvoke', f"ImplMap contains {len(managed['pinvoke'])} managed-to-native import relationships.", 'ImplMap rows map MemberForwarded tokens to ModuleRef and import names.')
            for dependency, engine in [('UnityEngine', 'unity'), ('GodotSharp', 'godot')]:
                if any(x == dependency or x.startswith(dependency + '.') for x in refs):
                    add('engine.' + engine, f'AssemblyRef structurally references {dependency}; a {engine} managed API dependency is present.', 'Typed AssemblyRef records, not arbitrary text matches.', limitations=['Engine executable version, runtime availability and mod compatibility unverified.'])
        package = observations.get('package')
        if package:
            add('package.inventory', f"{package['format']} structure declares {len(package['entries'])} members; names, sizes and compression/type metadata are in the snapshot.", 'Bounded archive central directory or CArchive cookie/TOC parsing.', limitations=['No member extraction or execution; ZIP CRC values are declared, not independently rehashed.'])
            if package['format'] == 'pyinstaller':
                add('package.runtime', f"CArchive cookie declares Python version {package['python_version']} and library {package['python_library']}.", 'PyInstaller cookie version/library fields and member TOC.', limitations=['Cookie declarations do not prove an installed Python runtime or executable behavior.'])
            if package['format'] == 'godot-pck':
                add('engine.godot-pck', f"Godot PCK v{package['pack_format_version']} structure declares writer engine version {package['declared_engine_version']}.", 'Validated standalone PCK header, version/flags, directory offsets and every unencrypted member MD5; not a text-marker guess.', limitations=['Header version identifies the declared writer; installed engine version and application runtime are not inferred.'])
                add('modding.resources', f"PCK defines {len(package['entries'])} unencrypted resource paths under res:// with byte ranges and verified content hashes.", 'Actual resource-directory path/offset/size/MD5 records map to file-backed payloads.', limitations=['Static resource-loading boundary only; this report does not execute or test loading/replacement or claim the target game exposes mod support.'])
            for manifest in package.get('manifests', []):
                deps = manifest['dependencies']
                if any('electron' in group for group in deps.values()):
                    add('engine.electron', 'A package.json manifest declares an electron dependency.', 'Parsed JSON dependency field inside the archive.', limitations=['Dependency declaration alone does not prove bundled runtime presence or a working Electron app.'])
                    break
        return result

    @staticmethod
    def _external(selection, request, executor, event, report):
        if (not isinstance(selection, dict) or set(selection) != {'tool_id', 'operation', 'options'}
                or not isinstance(selection['options'], dict)
                or any(not isinstance(selection[k], str) or not IDENTIFIER.fullmatch(selection[k]) for k in ('tool_id', 'operation'))):
            raise InvestigationError('invalid-external-analysis-selection')
        execute = getattr(executor, 'execute', None)
        if not callable(execute):
            report['unsupported'].append('External analysis executor unavailable')
            return
        external = dict(request, tool_id=selection['tool_id'], operation=selection['operation'],
                        options=selection['options'], step_id=request['step_id'] + '.external')
        if not IDENTIFIER.fullmatch(external['step_id']):
            raise InvestigationError('external-step-id-limit')
        report['cleanup_receipt'] = {'status': 'pending', 'scope': 'builtin-parser-and-external',
            'target_write_performed': False, 'reason': 'external-tool-outcome-unconfirmed'}
        receipt = bounded_json(execute(external, event), maximum=MAX_REPORT)
        cleanup = receipt.get('cleanup_receipt') if isinstance(receipt, dict) else None
        if isinstance(cleanup, dict) and cleanup.get('status') in ('confirmed', 'pending', 'failed'):
            report['cleanup_receipt'] = {'status': cleanup['status'], 'scope': 'builtin-parser-and-external',
                'target_write_performed': False, 'external': cleanup}
        # Tools need a separately verified domain adapter before their arbitrary
        # output can be interpreted as disassembly or semantic findings.
        if isinstance(receipt, dict):
            report['external_receipt'] = {k: receipt[k] for k in ('status', 'evidence_ids', 'tool_id', 'cleanup_receipt', 'limitations') if k in receipt}
        report['unsupported'].append('External receipt captured; domain disassembly adapter is not implemented')
