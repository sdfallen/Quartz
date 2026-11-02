"""Reproducible isolated BUILT fixtures + actual host-captured SOURCE analysis.

Run from repository: python -B labs/rea-analysis/validate.py
Only writes beneath this directory. Does not launch analyzed artifacts.
Uses already installed Microsoft csc and PyInstaller; downloads nothing.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import tracemalloc
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.investigation.gateway import InvestigationToolGateway
from core.investigation.planning import InvestigationPolicy
from core.investigation.session import InvestigationSession
from core.rea_analysis import AnalysisService


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def main():
    run = Path(__file__).resolve().parent / ('validation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    run.mkdir(exist_ok=False)
    fixtures = run / 'fixtures'
    fixtures.mkdir()
    csc = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not csc.is_file():
        raise RuntimeError('Local Microsoft csc unavailable; not acquired')
    source = fixtures / 'Fixture.cs'
    source.write_text('''using System;
using System.Runtime.InteropServices;
[assembly:System.Reflection.AssemblyVersion("1.2.3.4")]
namespace QuartzFixture {
 public interface IValue { int Value { get; } }
 [Serializable] public class Counter : IValue {
  [DllImport("kernel32.dll")] public static extern uint GetTickCount();
  public int Value { get { return 7; } }
  public static int Add(int left, int right) { return left + right; }
  public string Describe() { return "explicit BUILT fixture; never a live engine"; }
 }
 public class Holder<T> where T:class { public T Echo<U>(T value, U extra) where U:struct { return value; } }
}''', encoding='utf-8')
    managed = fixtures / 'Fixture.dll'
    command = [str(csc), '/nologo', '/target:library', '/out:' + str(managed), str(source)]
    started = time.perf_counter()
    compiled = subprocess.run(command, cwd=fixtures, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (run / 'compiler.stdout').write_bytes(compiled.stdout)
    (run / 'compiler.stderr').write_bytes(compiled.stderr)
    if compiled.returncode:
        raise RuntimeError('Fixture compiler failed; inspect compiler.stdout')
    compiler = {'tool': str(csc), 'tool_sha256': sha(csc), 'exit_code': compiled.returncode,
                'wall_seconds': time.perf_counter() - started, 'source_sha256': sha(source), 'artifact_sha256': sha(managed)}
    native = fixtures / 'CPython-native.exe'
    extension = fixtures / '_socket.pyd'
    shutil.copyfile(Path(sys.base_prefix) / 'python.exe', native)
    shutil.copyfile(Path(sys.base_prefix) / 'DLLs/_socket.pyd', extension)
    settings = fixtures / 'settings.json'
    settings.write_text('{"fixture":true,"value":7}', encoding='utf-8')
    from PyInstaller.archive.writers import CArchiveWriter
    from PyInstaller.archive.readers import CArchiveReader
    import PyInstaller
    package = fixtures / 'Fixture.pkg'
    CArchiveWriter(str(package), [('settings.json', str(settings), True, 'x'),
                                 ('Fixture.dll', str(managed), False, 'b')], 'python313.dll')
    package_reference = CArchiveReader(str(package))
    save(run / 'pyinstaller-reference.json', {'version': PyInstaller.__version__,
        'entries': package_reference.toc, 'settings_payload_matches': package_reference.extract('settings.json') == settings.read_bytes()})
    zipped = fixtures / 'Fixture.zip'
    with zipfile.ZipFile(zipped, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(managed, 'bin/Fixture.dll')
        archive.write(settings, 'data/settings.json')
        archive.writestr('package.json', json.dumps({'name': 'quartz-explicit-built-fixture', 'version': '1.2.3', 'dependencies': {}}))
    unknown = fixtures / 'unsupported.bin'
    unknown.write_bytes(b'UnityEngine UnrealEngine GodotSharp -- strings are not engine proof')
    source_paths = list((ROOT / 'core/rea_analysis').glob('*.py')) + [Path(__file__), Path(__file__).with_name('godot_experiment.py'), ROOT / 'core/investigation/gateway.py', ROOT / 'tests/test_rea_analysis_structure.py']
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    cases = [('native', native, 'Installed CPython binary copy'),
             ('native-exports', extension, 'Installed CPython extension copy'),
             ('managed', managed, 'BUILT Microsoft csc fixture'),
             ('pyinstaller', package, 'BUILT installed PyInstaller CArchiveWriter fixture'),
             ('zip', zipped, 'BUILT ZIP packaging fixture'),
             ('unsupported', unknown, 'SOURCE negative string fixture')]
    godot_runs = sorted(Path(__file__).resolve().parent.glob('godot-*/manifest.json'))
    engine_experiment = 'Unavailable: no completed isolated engine fixture in this lab.'
    if godot_runs:
        observed = godot_runs[-1]
        previous = json.loads(observed.read_text(encoding='utf-8'))
        assert previous['process']['exit_code'] == 0
        actual = previous['process']['actual_result']
        assert actual['initial']['value'] == 7 and actual['retained']['value'] == 7 and actual['replaced']['value'] == 42
        for label in ('base', 'mod'):
            original = observed.parent / 'project' / (label + '.pck')
            copy = fixtures / ('godot-' + label + '.pck')
            shutil.copyfile(original, copy)
            assert sha(original) == sha(copy)
            cases.append(('godot-' + label, copy, 'Actual Godot4.7.1 PCKPacker output copied from isolated engine experiment'))
        engine_experiment = {'original_manifest': str(observed.relative_to(ROOT)), 'manifest_sha256': sha(observed),
                             'engine_version': actual['engine'], 'runtime_result': actual,
                             'scope': 'Earlier actual isolated engine run; this validation reanalyzes its real PCK files with current frozen parser, without rerunning engine.'}
    results = []
    for name, path, kind in cases:
        event = threading.Event()
        deadline = time.monotonic() + 45
        session = InvestigationSession(path, root=run / 'host-store', event=event, deadline=deadline,
            tool_identity={'analysis': AnalysisService.runtime_identity(), 'source_hashes': hashes})
        workspace = run / 'workspaces' / name
        workspace.mkdir(parents=True)
        gateway = InvestigationToolGateway(session, None, workspace=workspace,
            policy=InvestigationPolicy(effects=frozenset({'read_target', 'write_workspace'})), tool_specs={})
        request = {'investigation_id': session.evidence.id, 'step_id': name, 'operation': 'analyze',
            'tool_id': 'quartz-builtin-analysis', 'target': session.target.as_dict(), 'options': {},
            'workspace': str(workspace), 'deadline_monotonic': deadline, 'max_output_bytes': 2 * 1024 * 1024}
        before = sha(path)
        started, cpu = time.perf_counter(), time.process_time()
        tracemalloc.start()
        report = AnalysisService().analyze(request, gateway, event)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        metrics = {'wall_seconds': time.perf_counter() - started, 'parser_process_cpu_seconds': time.process_time() - cpu,
                   'python_traced_peak_bytes': peak, 'target_size': path.stat().st_size}
        if report['errors']:
            save(run / (name + '-failed.json'), report)
            raise AssertionError((name, report['errors']))
        expected_capabilities = {'pe-structure', 'dotnet-metadata', 'package-inventory', 'engine-signatures'}
        session.accept_analysis(report, executed_capabilities=expected_capabilities)
        assert sha(path) == before
        assert not list(workspace.iterdir())
        assert all(r['level'] == 'SOURCE' for r in session.evidence.records.values())
        session.evidence.finalize('completed')
        snapshots = []
        for item in session.evidence.records.values():
            artifact = run / 'host-store' / item['artifact_relative_path']
            assert artifact.is_file() and sha(artifact) == item['digest']
            snapshots.append({'path': str(artifact.relative_to(run)), 'sha256': item['digest'], 'evidence_id': item['evidence_id']})
        save(run / (name + '-report.json'), report)
        results.append({'case': name, 'fixture_provenance': kind, 'target_sha256': before,
            'target_unchanged': True, 'findings': len(report['findings']), 'capabilities': report['capabilities_used'],
            'evidence': snapshots, 'metrics': metrics, 'cleanup_receipt': report['cleanup_receipt'],
            'runtime_or_ui_tested': False, 'unsupported': report['unsupported']})
    assert hashes == {str(p.relative_to(ROOT)): sha(p) for p in source_paths}, 'Analysis source changed during validation'
    save(run / 'manifest.json', {'schema_version': 1, 'source_baseline': 'e476c2fbd42c19f050d1a1e896959fe2e3ccd19d',
        'environment': {'python': sys.version, 'platform': platform.platform()},
        'source_hashes': hashes, 'compiler': compiler, 'pyinstaller_version': PyInstaller.__version__, 'results': results,
        'scope': 'Actual isolated static SOURCE analysis of native copies and BUILT fixtures; no analyzed target execution, no LIVE Quartz acceptance.',
        'analysis_identity': AnalysisService.runtime_identity(), 'engine_experiment': engine_experiment})
    print(str(run / 'manifest.json'))


if __name__ == '__main__':
    main()
