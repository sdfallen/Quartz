"""Isolated actual Godot4.7.1 PCK/loading experiment, outside AnalysisService.

Reads only the engine tool explicitly supplied with --engine. All copies,
generated project/resources, logs and outputs live beside this script.
Never reads an existing project's source/assets or runs from its directory.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.rea_analysis import AnalysisService
from core.investigation.gateway import InvestigationToolGateway
from core.investigation.planning import InvestigationPolicy
from core.investigation.session import InvestigationSession




def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True, help="Approved Godot engine executable")
    approved_engine = parser.parse_args().engine.resolve(strict=True)
    run = Path(__file__).resolve().parent / ('godot-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    run.mkdir(exist_ok=False)
    before = sha(approved_engine)
    tools = run / 'tools'
    tools.mkdir()
    engine = tools / approved_engine.name
    shutil.copyfile(approved_engine, engine)
    assert sha(engine) == before
    project = run / 'project'
    project.mkdir()
    (project / 'project.godot').write_text('''config_version=5
[application]
config/name="Quartz isolated PCK experiment"
[debug]
file_logging/enable_file_logging=false
[rendering]
renderer/rendering_method="gl_compatibility"
''', encoding='utf-8')
    payload = project / 'payload'
    payload.mkdir()
    (payload / 'base.json').write_text('{"value":7}', encoding='utf-8')
    (payload / 'mod.json').write_text('{"value":42}', encoding='utf-8')
    gd = project / 'experiment.gd'
    gd.write_text('''extends SceneTree

func _initialize():
    var folder = ProjectSettings.globalize_path("res://")
    for name in ["base", "mod"]:
        var packer = PCKPacker.new()
        if packer.pck_start(folder.path_join(name + ".pck")) != OK:
            quit(2)
            return
        if packer.add_file("res://data/settings.json", folder.path_join("payload/" + name + ".json")) != OK:
            quit(3)
            return
        if packer.flush() != OK:
            quit(4)
            return
    var base_ok = ProjectSettings.load_resource_pack(folder.path_join("base.pck"), true)
    var initial = JSON.parse_string(FileAccess.get_file_as_string("res://data/settings.json"))
    var retain_ok = ProjectSettings.load_resource_pack(folder.path_join("mod.pck"), false)
    var retained = JSON.parse_string(FileAccess.get_file_as_string("res://data/settings.json"))
    var replace_ok = ProjectSettings.load_resource_pack(folder.path_join("mod.pck"), true)
    var replaced = JSON.parse_string(FileAccess.get_file_as_string("res://data/settings.json"))
    print("REA_GODOT_RESULT:" + JSON.stringify({"engine":Engine.get_version_info(), "base_loaded":base_ok,
        "retain_loaded":retain_ok,"replace_loaded":replace_ok,"initial":initial,"retained":retained,"replaced":replaced}))
    quit(0 if base_ok and retain_ok and replace_ok and initial.value == 7 and retained.value == 7 and replaced.value == 42 else 5)
''', encoding='utf-8')
    setup_hashes = {str(p.relative_to(project)): sha(p) for p in (gd, project / 'project.godot', payload / 'base.json', payload / 'mod.json')}
    environment = {k: v for k, v in os.environ.items() if not any(secret in k.upper() for secret in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY'))}
    for key, relative in [('APPDATA', 'profile/roaming'), ('LOCALAPPDATA', 'profile/local'), ('TEMP', 'temp'), ('TMP', 'temp')]:
        path = run / relative
        path.mkdir(parents=True, exist_ok=True)
        environment[key] = str(path)
    command = [str(engine), '--headless', '--path', str(project), '--script', 'res://experiment.gd', '--log-file', str(run / 'engine.log')]
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=project, env=environment, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (run / 'engine.stdout').write_bytes(completed.stdout)
    (run / 'engine.stderr').write_bytes(completed.stderr)
    lines = completed.stdout.decode('utf-8', 'replace').splitlines()
    actual = next((json.loads(line.split(':', 1)[1]) for line in lines if line.startswith('REA_GODOT_RESULT:')), None)
    process = {'argv': command, 'exit_code': completed.returncode, 'wall_seconds': time.perf_counter() - started,
               'process_cleanup': 'subprocess completed and reaped', 'actual_result': actual}
    save(run / 'process.json', process)
    if completed.returncode or not actual:
        raise AssertionError('Engine experiment failed: inspect ' + str(run / 'process.json'))
    assert actual['initial']['value'] == 7 and actual['retained']['value'] == 7 and actual['replaced']['value'] == 42
    assert setup_hashes == {str(p.relative_to(project)): sha(p) for p in (gd, project / 'project.godot', payload / 'base.json', payload / 'mod.json')}
    reports = []
    for name in ('base', 'mod'):
        target = project / (name + '.pck')
        event = threading.Event()
        deadline = time.monotonic() + 30
        session = InvestigationSession(target, root=run / 'host-store', event=event, deadline=deadline,
            tool_identity=AnalysisService.runtime_identity())
        workspace = run / 'workspaces' / name
        workspace.mkdir(parents=True)
        gateway = InvestigationToolGateway(session, None, workspace=workspace,
            policy=InvestigationPolicy(effects=frozenset({'read_target', 'write_workspace'})), tool_specs={})
        request = {'investigation_id': session.evidence.id, 'step_id': 'godot-' + name,
            'operation': 'analyze', 'tool_id': 'quartz-builtin-analysis', 'target': session.target.as_dict(), 'options': {},
            'workspace': str(workspace), 'deadline_monotonic': deadline, 'max_output_bytes': 512 * 1024}
        report = AnalysisService().analyze(request, gateway, event)
        save(run / (name + '-analysis.json'), report)
        assert not report['errors'], report['errors']
        assert set(report['capabilities_used']) == {'package-inventory', 'engine-signatures'}
        session.accept_analysis(report, executed_capabilities={'package-inventory', 'engine-signatures'})
        session.evidence.finalize('completed')
        assert not list(workspace.iterdir())
        reports.append({'pack': str(target.relative_to(run)), 'sha256': sha(target), 'findings': len(report['findings']),
                        'evidence': session.evidence.records, 'static_evidence_level': 'SOURCE'})
    assert sha(approved_engine) == before and sha(engine) == before
    save(run / 'manifest.json', {'schema_version': 1, 'engine_source_tool': str(approved_engine),
        'engine_sha256': before, 'engine_size': engine.stat().st_size, 'engine_source_unchanged': True,
        'analysis_identity': AnalysisService.runtime_identity(), 'fixture_hashes': setup_hashes, 'process': process,
        'reports': reports, 'scope': 'Actual headless Godot4.7.1 resource-pack experiment in new isolated project; static facade never executes target. No Quartz/UI/game acceptance.',
        'native_engine_binary_analysis': 'Unavailable: actual178997256-byte engine exceeds bounded128MiB reader; PCKs analyzed instead.'})
    print(str(run / 'manifest.json'))


if __name__ == '__main__':
    main()
