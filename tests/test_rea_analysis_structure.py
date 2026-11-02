"""Real-file analysis and boundary regressions; no installed application edits."""
import hashlib
import base64
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from core.investigation.contracts import InvestigationError, Target
from core.investigation.gateway import InvestigationToolGateway
from core.investigation.planning import InvestigationPolicy
from core.investigation.session import InvestigationSession
from core.rea_analysis import AnalysisService
from core.rea_analysis.binary import FormatError, PE
from core.rea_analysis.managed import inspect_managed
from core.rea_analysis.packages import inspect_pck, inspect_pyinstaller, inspect_zip

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'labs' / 'rea-analysis'
CSC = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
NATIVE = Path(sys.base_prefix) / 'python.exe'


def make_pe():
    """SOURCE fixture: explicit handcrafted minimal PE, not a live executable."""
    raw = bytearray(1024)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', raw, 0x84, 0x8664, 1, 0, 0, 0, 240, 0x22)
    struct.pack_into('<H', raw, 0x98, 0x20b)
    struct.pack_into('<I', raw, 0x98 + 16, 0x1000)
    struct.pack_into('<Q', raw, 0x98 + 24, 0x140000000)
    struct.pack_into('<I', raw, 0x98 + 60, 512)
    struct.pack_into('<H', raw, 0x98 + 68, 3)
    struct.pack_into('<I', raw, 0x98 + 108, 16)
    struct.pack_into('<8sIIIIIIHHI', raw, 0x98 + 240, b'.text', 512, 0x1000, 512, 512, 0, 0, 0, 0, 0x60000020)
    return raw


class StructureTests(unittest.TestCase):
    def test_real_native_import_iat_unwind_relationships(self):
        if not NATIVE.is_file():
            self.skipTest('Windows CPython PE unavailable')
        pe = PE(NATIVE.read_bytes())
        result = pe.inspect()
        self.assertEqual(result['bits'], 64)
        self.assertTrue(result['imports'])
        self.assertTrue(any(symbol.get('name') for lib in result['imports'] for symbol in lib['symbols']))
        for lib in result['imports']:
            for symbol in lib['symbols']:
                pe.rva(symbol['iat_rva'], 8)
        self.assertTrue(result['runtime_functions'])
        self.assertTrue(all(x['begin_rva'] < x['end_rva'] for x in result['runtime_functions']))

    def test_malformed_rva_and_truncation_fail(self):
        for data in (b'MZ', make_pe()[:300]):
            with self.assertRaises(FormatError):
                PE(data).inspect()
        pe = PE(make_pe())
        with self.assertRaises(FormatError):
            pe.rva(0x2000)

    def test_import_directory_cannot_map_virtual_only_bytes(self):
        data = make_pe()
        struct.pack_into('<II', data, 0x98 + 112 + 8, 0x2000, 20)
        with self.assertRaises(FormatError):
            PE(data).inspect()

    def test_managed_magic_string_is_not_managed_metadata(self):
        data = make_pe()
        data[600:620] = b'UnityEngine BSJB .NET'
        self.assertIsNone(inspect_managed(PE(data)))

    def test_zip_manifest_dependency_is_structural(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('app/package.json', json.dumps({'name': 'source-fixture', 'version': '1.0', 'dependencies': {'electron': '30.0.0'}}))
            archive.writestr('app/mods/example.json', '{"fixture":true}')
        result = inspect_zip(stream.getvalue(), lambda: None)
        self.assertEqual(len(result['entries']), 2)
        self.assertEqual(result['manifests'][0]['dependencies']['dependencies']['electron'], '30.0.0')

    def test_zip_oversized_count_rejected_before_library(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w'):
            pass
        data = bytearray(stream.getvalue())
        struct.pack_into('<HH', data, 8, 65535, 65535)
        with self.assertRaises(FormatError):
            inspect_zip(data, lambda: None)

    def test_pyinstaller_cookie_toc_fixture(self):
        name = b'fixture_module\0'
        payload = b'fixture'
        stride = 18 + len(name)
        toc = struct.pack('!IIIIBB', stride, 0, len(payload), len(payload), 0, ord('s')) + name
        cookie = struct.pack('!8sIIII64s', b'MEI\x0c\x0b\x0a\x0b\x0e', len(payload) + len(toc) + 88, len(payload), len(toc), 313, b'python313.dll')
        result = inspect_pyinstaller(payload + toc + cookie, lambda: None)
        self.assertEqual(result['entries'][0]['name'], 'fixture_module')
        self.assertEqual(result['python_version'], 313)
        corrupt = bytearray(payload + toc + cookie)
        struct.pack_into('!I', corrupt, len(payload), 1)
        with self.assertRaises(FormatError):
            inspect_pyinstaller(corrupt, lambda: None)

    def test_pck_source_fixture_and_corrupt_payload(self):
        payload = b'{"fixture":true}'
        name = b'mods/value.json\0'
        header = struct.pack('<IIIIIIQQ', 0x43504447, 4, 4, 7, 1, 2, 128, 128 + len(payload)) + bytes(64)
        raw = header + bytes(128 - len(header)) + payload
        raw += struct.pack('<II', 1, len(name)) + name + struct.pack('<QQ', 0, len(payload)) + hashlib.md5(payload, usedforsecurity=False).digest() + struct.pack('<I', 0)
        result = inspect_pck(raw, lambda: None)
        self.assertEqual(result['entries'][0]['resource_path'], 'res://mods/value.json')
        self.assertTrue(result['entries'][0]['md5_verified'])
        corrupt = bytearray(raw)
        corrupt[128] ^= 1
        with self.assertRaisesRegex(FormatError, 'pck-member-digest-mismatch'):
            inspect_pck(corrupt, lambda: None)

    def test_actual_godot_471_generated_pack_fixture(self):
        # Exact224-byte output from actual Godot4.7.1 official PCKPacker,
        # lab godot-20261102T133550Z. This is BUILT fixture provenance, not
        # a new live engine run or a handcrafted success marker.
        data = base64.b64decode('R0RQQwQAAAAEAAAABwAAAAEAAAACAAAAgAAAAAAAAACgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB7InZhbHVlIjo3fQAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAUAAAAZGF0YS9zZXR0aW5ncy5qc29uAAAAAAAAAAAAAAsAAAAAAAAAHL9/Xa7IrXWnTsi18mdGvgAAAAA=')
        result = inspect_pck(data, lambda: None)
        self.assertEqual(result['pack_format_version'], 4)
        self.assertEqual(result['declared_engine_version'], '4.7.1')
        entry = result['entries'][0]
        self.assertEqual(entry['resource_path'], 'res://data/settings.json')
        self.assertEqual(entry['size'], 11)
        self.assertEqual(entry['sha256'], '9d709bba0358da8fdf5600bb3692fa32d0aa2a19a08152cf4307e0b4240e71ac')
        encrypted = bytearray(data)
        struct.pack_into('<I', encrypted, 20, 3)
        with self.assertRaisesRegex(FormatError, 'pck-version-encryption-or-sparse-unsupported'):
            inspect_pck(encrypted, lambda: None)

    def test_runtime_identity_changes_with_semantics_and_constants_without_file_reads(self):
        from core.rea_analysis import service, binary
        with patch.object(Path, 'open', side_effect=AssertionError('must not read source')):
            baseline = AnalysisService.runtime_identity()
        with patch.object(service, 'MAX_INPUT', service.MAX_INPUT + 1):
            self.assertNotEqual(baseline['code_sha256'], AnalysisService.runtime_identity()['code_sha256'])
        original = binary.PE.imports.__code__
        try:
            binary.PE.imports.__code__ = original.replace(co_filename='unrelated/path.py', co_firstlineno=9876)
            self.assertEqual(baseline, AnalysisService.runtime_identity())
            binary.PE.imports.__code__ = (lambda self: []).__code__
            self.assertNotEqual(baseline['code_sha256'], AnalysisService.runtime_identity()['code_sha256'])
        finally:
            binary.PE.imports.__code__ = original


class FacadeTests(unittest.TestCase):
    def setUp(self):
        LAB.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='test-', dir=LAB)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target_path = self.root / 'target.exe'
        self.target_path.write_bytes(make_pe())
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.event = threading.Event()
        self.deadline = time.monotonic() + 30
        self.session = InvestigationSession(self.target_path, root=self.root / 'evidence', event=self.event,
            deadline=self.deadline, tool_identity={'provider': 'quartz-structure-v1'})
        self.addCleanup(self.session.close)
        self.gateway = InvestigationToolGateway(self.session, None, workspace=self.workspace,
            policy=InvestigationPolicy(effects=frozenset({'read_target', 'write_workspace'})), tool_specs={})
        self.request = {'investigation_id': self.session.evidence.id, 'step_id': 'structural', 'operation': 'analyze',
            'tool_id': 'quartz-builtin-analysis', 'target': self.session.target.as_dict(), 'options': {},
            'workspace': str(self.workspace), 'deadline_monotonic': self.deadline, 'max_output_bytes': 512 * 1024}

    def test_actual_host_capture_and_acceptance_no_invented_evidence(self):
        result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertEqual(result['errors'], [])
        self.assertTrue(result['findings'])
        self.session.accept_analysis(result, executed_capabilities=result['capabilities_used'])
        for finding in result['findings']:
            for identity in finding['evidence_ids']:
                record = self.session.evidence.records[identity]
                self.assertEqual(record['level'], 'SOURCE')
                self.assertEqual(record['origin'], 'quartz-builtin-analysis')
        self.assertEqual(list(self.workspace.iterdir()), [])
        self.assertEqual(result['cleanup_receipt']['status'], 'confirmed')
        self.assertEqual(self.target_path.read_bytes(), make_pe())

    def test_missing_capture_blocks_findings(self):
        result = AnalysisService().analyze(self.request, object(), self.event)
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['errors'][0]['code'], 'analysis-evidence-capture-unavailable')
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_repeat_static_analysis_reuses_host_capture_identity(self):
        first = AnalysisService().analyze(self.request, self.gateway, self.event)
        second = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertEqual(first['errors'], [])
        self.assertEqual(second['errors'], [])
        self.assertEqual(first['findings'], second['findings'])
        self.assertEqual(len(self.session.evidence.records), 1)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_target_changes_are_rejected(self):
        self.target_path.write_bytes(b'changed')
        result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['errors'][0]['code'], 'target-changed')

    def test_precancelled_and_expired_do_not_write(self):
        self.event.set()
        result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertTrue(result['cancellation']['cancelled'])
        self.event.clear()
        self.request['deadline_monotonic'] = time.monotonic() - 1
        result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertEqual(result['errors'][0]['code'], 'deadline')
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_unknown_format_and_string_only_engine_do_not_become_findings(self):
        self.target_path.write_bytes(b'UnityEngine GodotSharp UnrealEngine')
        target = Target.capture(self.target_path, self.event, self.deadline)
        self.request['target'] = target.as_dict()
        result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertEqual(result['findings'], [])
        self.assertIn('Unrecognized format', result['unsupported'][-1])

    def test_missing_scope_cannot_write(self):
        gateway = InvestigationToolGateway(self.session, None, workspace=self.workspace,
            policy=InvestigationPolicy(), tool_specs={})
        result = AnalysisService().analyze(self.request, gateway, self.event)
        self.assertEqual(result['errors'][0]['code'], 'analysis-workspace-write-not-authorized')
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_output_limit_leaves_no_snapshot(self):
        self.request['max_output_bytes'] = 1024
        result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertEqual(result['errors'][0]['code'], 'analysis-report-output-limit')
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_cancellation_at_capture_fence_discards_findings(self):
        original = self.gateway.capture_analysis
        def cancel_after_capture(*args):
            result = original(*args)
            self.event.set()
            return result
        with patch.object(self.gateway, 'capture_analysis', side_effect=cancel_after_capture):
            result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertTrue(result['cancellation']['cancelled'])
        self.assertEqual(result['findings'], [])
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_external_unknown_outcome_does_not_claim_confirmed_cleanup(self):
        self.request['options'] = {'external_tool': {'tool_id': 'missing-tool', 'operation': 'disassemble', 'options': {}}}
        result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertTrue(result['errors'])
        self.assertEqual(result['cleanup_receipt']['status'], 'pending')
        self.assertEqual(result['findings'], [])

    def test_native_capabilities_do_not_pretend_managed_or_disassembly_available(self):
        caps = {x['capability_id']: x for x in AnalysisService().capabilities(self.session.target)}
        self.assertTrue(caps['pe-structure']['available'])
        self.assertFalse(caps['dotnet-metadata']['available'])
        self.assertFalse(caps['native-disassembly']['available'])
        self.assertIn('execute_tool', caps['native-disassembly']['effects'])
        self.assertIn('attach_runtime', caps['runtime-observation']['effects'])

    def test_builtin_cleanup_failure_is_reported(self):
        with patch.object(Path, 'unlink', side_effect=OSError('fixture cleanup denial')):
            result = AnalysisService().analyze(self.request, self.gateway, self.event)
        self.assertEqual(result['cleanup_receipt']['status'], 'failed')


class RealPackageTests(unittest.TestCase):
    def test_actual_installed_pyinstaller_writer_and_reader_agree(self):
        try:
            from PyInstaller.archive.writers import CArchiveWriter
            from PyInstaller.archive.readers import CArchiveReader
        except ImportError:
            self.skipTest('Local PyInstaller unavailable; no acquisition')
        LAB.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='package-test-', dir=LAB) as directory:
            root = Path(directory)
            source = root / 'settings.json'
            source.write_text('{"fixture":true}', encoding='utf-8')
            target = root / 'Fixture.pkg'
            CArchiveWriter(str(target), [('settings.json', str(source), True, 'x')], 'python313.dll')
            actual = CArchiveReader(str(target))
            ours = inspect_pyinstaller(target.read_bytes(), lambda: None)
            self.assertEqual(ours['entries'][0]['name'], next(iter(actual.toc)))
            self.assertEqual(ours['entries'][0]['compressed_size'], actual.toc['settings.json'][1])
            self.assertEqual(ours['entries'][0]['size'], actual.toc['settings.json'][2])
            self.assertEqual(actual.extract('settings.json'), source.read_bytes())


@unittest.skipUnless(CSC.is_file(), 'Local Microsoft C# compiler unavailable; no acquisition')
class RealManagedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LAB.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix='managed-test-', dir=LAB)
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'Fixture.cs'
        cls.target = cls.root / 'Fixture.dll'
        cls.source.write_text('''using System;
using System.Runtime.InteropServices;
namespace QuartzFixture {
 public class Counter {
  [DllImport("kernel32.dll")] public static extern uint GetTickCount();
  public static int Add(int left, int right) { return left + right; }
  public string Describe() { return "explicit built test fixture"; }
 }
}''', encoding='utf-8')
        result = subprocess.run([str(CSC), '/nologo', '/target:library', '/out:' + str(cls.target), str(cls.source)],
            cwd=cls.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError('Local fixture compilation failed: ' + result.stdout.decode('utf-8', 'replace'))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_compiled_assembly_types_methods_and_pinvoke(self):
        before = hashlib.sha256(self.target.read_bytes()).hexdigest()
        result = inspect_managed(PE(self.target.read_bytes()))
        self.assertEqual(result['assemblies'][0]['name'], 'Fixture')
        counter = next(t for t in result['types'] if t['name'] == 'Counter')
        methods = {m['token']: m['name'] for m in result['methods']}
        self.assertIn('Add', [methods[token] for token in counter['method_tokens']])
        self.assertIn('Describe', [methods[token] for token in counter['method_tokens']])
        self.assertEqual(result['pinvoke'][0]['import_name'], 'GetTickCount')
        self.assertEqual(result['pinvoke'][0]['module'], 'kernel32.dll')
        self.assertTrue(any(x['name'] == 'mscorlib' for x in result['assembly_references']))
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
