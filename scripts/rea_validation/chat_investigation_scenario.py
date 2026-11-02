"""STANDALONE FIXTURE: observe -> checkpoint -> scripted narrow repair -> re-run.

Runs entirely inside a disposable temporary project. It never reads the user's
projects, never touches an installed build and starts no GUI. The subject is a
tiny generated Python application with a real settings-persistence defect, so
observations below come from actual local child processes. The repair is a
predefined script replacement, not an agent discovering or applying a fix.

What this does and does not prove:

* It proves only the generated fixture's failure and subsequent repair re-run.
* It does not exercise ChatInvestigationTask, an agent, permission continuation,
  GUI, installed Quartz, or the integrated model-driven repair path.
* JSON always states quartz_integration_verified=false. Its separate
  fixture_fix_rerun_verified flag depends on successful actual child runs.

Usage:  python -X utf8 -B scripts/rea_validation/chat_investigation_scenario.py [--out DIR]
Use a fresh private --out directory to retain the report, fixture sources and
checkpoint. Without --out all generated evidence is temporary.
Exit code 0 only when the bounded experiment and actual repair re-run pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.workspace_checkpoint import create_checkpoint

# The defect: save() writes a temporary file and never replaces the real one,
# so a value looks saved in the same process but is lost on the next start.
DEFECTIVE_APP = '''"""Disposable settings fixture with a real persistence defect."""
import json, sys
from pathlib import Path

STORE = Path(__file__).resolve().parent / "settings.json"


def load():
    if not STORE.is_file():
        return {}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def save(key, value):
    data = load()
    data[key] = value
    staging = STORE.with_suffix(".json.tmp")
    staging.write_text(json.dumps(data), encoding="utf-8")
    # BUG: the staged file is never promoted to STORE.
    return True


def main(argv):
    if argv[:1] == ["set"]:
        save(argv[1], argv[2])
        print("saved")
    elif argv[:1] == ["get"]:
        print(json.dumps(load().get(argv[1])))
    else:
        print("usage: app.py set KEY VALUE | get KEY")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

FIXED_SAVE = '''    staging = STORE.with_suffix(".json.tmp")
    staging.write_text(json.dumps(data), encoding="utf-8")
    staging.replace(STORE)
    return True
'''

DEFECTIVE_SAVE = '''    staging = STORE.with_suffix(".json.tmp")
    staging.write_text(json.dumps(data), encoding="utf-8")
    # BUG: the staged file is never promoted to STORE.
    return True
'''


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def run_app(project: Path, *args: str) -> dict:
    """Run the fixture application as a real child process."""
    started = time.monotonic()
    completed = subprocess.run([sys.executable, '-I', '-B', str(project / 'app.py'), *args],
                               capture_output=True, text=True, timeout=60, check=False,
                               cwd=str(project))
    return {'argv': ['python', 'app.py', *args], 'exit_code': completed.returncode,
            'stdout': completed.stdout.strip()[:2000], 'stderr': completed.stderr.strip()[:2000],
            'seconds': round(time.monotonic() - started, 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description='Standalone generated-app repair experiment; no Quartz integration proof.')
    parser.add_argument('--out', default=None, help='fresh private evidence directory (default: temporary)')
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='standalone-repair-fixture-') as folder:
        workspace = Path(folder)
        project = workspace / 'settings-app'
        project.mkdir()
        destination = Path(options.out).resolve() if options.out else workspace / 'evidence'
        # Never overwrite another run's evidence.
        destination.mkdir(parents=True, exist_ok=False)
        app = project / 'app.py'
        app.write_text(DEFECTIVE_APP, encoding='utf-8')
        evidence = {'schema_version': 2, 'experiment': 'STANDALONE FIXTURE',
                    'subject': 'generated disposable settings app',
                    'repair_performed_by': 'predefined script replacement; no agent or model',
                    'quartz_integration_verified': False, 'fixture_fix_rerun_verified': False,
                    'fixture_defect_reproduced': False, 'checkpoint_verified': False,
                    'platform': sys.platform, 'python': sys.version.split()[0],
                    'script_sha256': digest(Path(__file__)), 'status': 'failed',
                    'limitations': ['No Quartz GUI or packaged acceptance.',
                                    'No model-driven investigation or repair acceptance.',
                                    'No permission, continuation, or user acceptance proof.'],
                    'steps': [], 'artifact_sha256': {}}

        def step(name, **payload):
            if len(evidence['steps']) >= 12:
                raise RuntimeError('standalone-observation-limit')
            evidence['steps'].append({'step': len(evidence['steps']) + 1, 'name': name, **payload})

        try:
            # Real independent processes demonstrate the baseline persistence failure.
            wrote = run_app(project, 'set', 'theme', 'dark')
            before_get = run_app(project, 'get', 'theme')
            reproduced = (wrote['exit_code'] == 0 and wrote['stdout'] == 'saved'
                          and before_get['exit_code'] == 0 and before_get['stdout'] == 'null'
                          and not (project / 'settings.json').exists()
                          and (project / 'settings.json.tmp').is_file())
            evidence['fixture_defect_reproduced'] = reproduced
            step('fixture_failure_before_repair', set_run=wrote, get_run=before_get,
                 defect_reproduced=reproduced, expected_get='"dark"')
            if not reproduced:
                raise RuntimeError('fixture-defect-not-reproduced')

            # A seeded fixture-only file tests the reader, rather than claiming
            # that a null result for a missing key proves the reader works.
            store = project / 'settings.json'
            store.write_text(json.dumps({'reader_probe': 'READ_PATH_WORKS'}), encoding='utf-8')
            reader_probe = run_app(project, 'get', 'reader_probe')
            reader_works = reader_probe['exit_code'] == 0 and reader_probe['stdout'] == '"READ_PATH_WORKS"'
            step('fixture_reader_probe', get_run=reader_probe, reader_verified_for_seed=reader_works,
                 seeded_file_sha256=digest(store))
            store.unlink()  # Only the file this experiment just created.
            if not reader_works:
                raise RuntimeError('fixture-reader-probe-failed')

            staged = project / 'settings.json.tmp'
            staged_payload = json.loads(staged.read_text(encoding='utf-8'))
            hypothesis_supported = staged_payload.get('theme') == 'dark'
            step('fixture_staged_value_evidence', staged_payload=staged_payload,
                 staged_sha256=digest(staged), store_present=store.exists(),
                 hypothesis='The save tail never promotes the staged file.', supported=hypothesis_supported)
            if not hypothesis_supported:
                raise RuntimeError('fixture-staged-evidence-missing')

            before_bytes = app.read_bytes()
            before_sha = digest(app)
            (destination / 'fixture-before.py').write_bytes(before_bytes)
            checkpoint = create_checkpoint(project, backup_root=destination / 'checkpoints')
            archive = Path(checkpoint['archive']) if checkpoint.get('archive') else None
            checkpoint_ok = (checkpoint.get('status') in {'git', 'snapshot'}
                             and checkpoint.get('complete') is True and archive is not None and archive.is_file())
            if checkpoint_ok:
                with zipfile.ZipFile(archive) as saved:
                    checkpoint_ok = (saved.testzip() is None and saved.read('files/app.py') == before_bytes
                                     and json.loads(saved.read('checkpoint-manifest.json'))['files']['app.py']['sha256'] == before_sha)
            evidence['checkpoint_verified'] = checkpoint_ok
            step('fixture_checkpoint', status=checkpoint.get('status'), verified=checkpoint_ok,
                 archive=str(archive) if archive else None, archive_sha256=digest(archive) if archive else None,
                 app_before_sha256=before_sha)
            if not checkpoint_ok:
                raise RuntimeError('fixture-checkpoint-unverified-write-refused')

            source = app.read_text(encoding='utf-8')
            if source.count(DEFECTIVE_SAVE) != 1:
                raise RuntimeError('fixture-defective-block-not-unique-write-refused')
            fixed = source.replace(DEFECTIVE_SAVE, FIXED_SAVE)
            app.write_text(fixed, encoding='utf-8')
            after_sha = digest(app)
            (destination / 'fixture-after.py').write_bytes(app.read_bytes())
            narrow_verified = app.read_text(encoding='utf-8') == fixed and before_sha != after_sha
            step('fixture_scripted_narrow_change', changed_file='app.py', replacement_count=1,
                 before_sha256=before_sha, after_sha256=after_sha,
                 verified_unique_replacement=narrow_verified)
            if not narrow_verified:
                raise RuntimeError('fixture-narrow-change-unverified')

            for name in ('settings.json', 'settings.json.tmp'):
                path = project / name
                if path.is_file():
                    path.unlink()  # Generated fixture state, never user data.
            rerun_set = run_app(project, 'set', 'theme', 'dark')
            rerun_get = run_app(project, 'get', 'theme')
            verified = (rerun_set['exit_code'] == 0 and rerun_set['stdout'] == 'saved'
                        and rerun_get['exit_code'] == 0 and rerun_get['stdout'] == '"dark"'
                        and store.is_file() and json.loads(store.read_text(encoding='utf-8')).get('theme') == 'dark'
                        and not (project / 'settings.json.tmp').exists())
            evidence['fixture_fix_rerun_verified'] = verified
            step('fixture_repair_rerun', set_run=rerun_set, get_run=rerun_get,
                 fixture_fix_rerun_verified=verified, settings_sha256=digest(store))
            if not verified:
                raise RuntimeError('fixture-repair-rerun-failed')
            evidence['status'] = 'passed'
        except Exception as exc:
            evidence['failure'] = {'type': type(exc).__name__, 'reason': str(exc)[:500]}
        for artifact in sorted(destination.rglob('*')):
            if artifact.is_file():
                evidence['artifact_sha256'][artifact.relative_to(destination).as_posix()] = digest(artifact)
        manifest = destination / 'standalone-fixture-repair.json'
        with manifest.open('x', encoding='utf-8') as stream:
            json.dump(evidence, stream, indent=2, ensure_ascii=False, allow_nan=False)
        print(json.dumps({'experiment': 'STANDALONE FIXTURE', 'status': evidence['status'],
                          'quartz_integration_verified': False,
                          'fixture_fix_rerun_verified': evidence['fixture_fix_rerun_verified'],
                          'manifest': str(manifest), 'manifest_sha256': digest(manifest),
                          'evidence_retained': options.out is not None}, indent=2, ensure_ascii=False))
        return 0 if evidence['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
