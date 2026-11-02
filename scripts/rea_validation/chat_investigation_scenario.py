"""Scenario C/E/F driver: real observation -> hypothesis -> checkpoint -> narrow fix -> re-run.

Runs entirely inside a disposable temporary project. It never reads the user's
projects, never touches an installed build and starts no GUI. The subject is a
tiny generated Python application with a real settings-persistence defect, so
every step below is an actual local observation rather than a mocked result.

What this does and does not prove:

* LIVE for the generated test application on this machine: the defect is
  observed by running it, the fix is verified by running it again.
* It is NOT a Quartz GUI acceptance and NOT a packaged main-chat acceptance.
  Those need the real window and remain separately blocked/recorded.

Usage:  python -X utf8 -B scripts/rea_validation/chat_investigation_scenario.py [--out DIR]
Exit code 0 only when the re-run actually proves the fix.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.investigation.chat_task import ChatInvestigationTask, classify_investigation_request
from core.investigation.planning import InvestigationPolicy
from core.workspace_checkpoint import create_checkpoint

TASK_TEXT = ('Bu uygulamadaki ayar kaydetme hatasını incele ve düzelt; '
             'diğer ajan değişikliği kontrol etsin.')

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
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=None, help='evidence directory (default: temporary)')
    options = parser.parse_args()

    holder = tempfile.TemporaryDirectory(prefix='chat-investigation-')
    workspace = Path(holder.name)
    project = workspace / 'settings-app'
    project.mkdir()
    (project / 'app.py').write_text(DEFECTIVE_APP, encoding='utf-8')
    evidence: dict[str, object] = {'schema_version': 1, 'scenario': 'chat-investigation-C-E',
                                   'platform': sys.platform, 'python': sys.version.split()[0],
                                   'subject': 'generated disposable settings app',
                                   'quartz_gui_acceptance': 'NOT ATTEMPTED (separate, blocked)',
                                   'steps': []}

    def step(name: str, **payload):
        entry = {'step': len(evidence['steps']) + 1, 'name': name, **payload}
        evidence['steps'].append(entry)
        return entry

    # 1. The chat request is classified; the task is bound to the disposable project.
    request = classify_investigation_request(TASK_TEXT)
    if request is None:
        print('classification failed'); return 1
    task = ChatInvestigationTask(request, task_id='chat.scenarioC', conversation_id='local',
        policy=InvestigationPolicy(effects=frozenset({'read_target', 'write_workspace'})))

    class LocalOwner:
        scope = 'artifact'

        def __init__(self, path: Path):
            stat = path.stat()
            self.target = path
            self.identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

    task.bind_owner(LocalOwner(project / 'app.py'))
    step('classify_and_bind', question=TASK_TEXT, state=task.state,
         granted_effects=sorted(task.granted_effects))

    # 2. OBSERVATION: run it. The value does not survive a second start.
    wrote = run_app(project, 'set', 'theme', 'dark')
    read_back = run_app(project, 'get', 'theme')
    observed_defect = read_back['stdout'] == 'null'
    task.record_round(action='observe_runtime', status='completed',
                      observation={'set': wrote['stdout'], 'get': read_back['stdout']})
    step('observe_defect', set_run=wrote, get_run=read_back, defect_reproduced=observed_defect,
         settings_file_present=(project / 'settings.json').is_file(),
         staged_file_present=(project / 'settings.json.tmp').is_file())
    if not observed_defect:
        print('fixture did not reproduce the defect'); return 1

    # 3. A WRONG HYPOTHESIS FIRST (scenario E): blame the reader. A targeted
    #    check refutes it, the method is recorded as failed and not retried.
    probe = run_app(project, 'get', 'missing_key')
    wrong_refuted = probe['stdout'] == 'null' and probe['exit_code'] == 0
    task.record_round(action='check_reader', status='failed',
                      observation={'probe': probe['stdout']})
    task.record_failed_method('blame_loader', 'Okuyucu sağlam; eksik anahtar da null döndürüyor')
    step('refute_wrong_hypothesis', hypothesis='load() bozuk olabilir',
         probe=probe, refuted=wrong_refuted, failed_methods=task.failed_methods)

    # 4. CORRECT HYPOTHESIS from real file evidence: the staged file holds the
    #    value while the real store was never replaced.
    staged = project / 'settings.json.tmp'
    staged_payload = json.loads(staged.read_text(encoding='utf-8')) if staged.is_file() else None
    hypothesis_supported = isinstance(staged_payload, dict) and staged_payload.get('theme') == 'dark'
    task.record_round(action='inspect_scoped_files', status='completed',
                      observation={'staged': staged_payload})
    step('evidence_backed_hypothesis',
         hypothesis='save() geçici dosyayı yazıyor ama gerçek dosyayla değiştirmiyor',
         staged_contents=staged_payload, staged_sha256=digest(staged),
         store_sha256=digest(project / 'settings.json'), supported=hypothesis_supported)
    if not hypothesis_supported:
        print('hypothesis evidence missing'); return 1

    # 5. CHECKPOINT before any write, using the existing production helper.
    checkpoint = create_checkpoint(project, backup_root=workspace / 'checkpoints')
    step('checkpoint', status=checkpoint.get('status'), complete=checkpoint.get('complete'),
         file_count=checkpoint.get('file_count'), warning=checkpoint.get('warning'))
    if checkpoint.get('status') not in {'git', 'snapshot'} or checkpoint.get('complete') is not True:
        step('checkpoint_refused', detail='write skipped because no usable checkpoint exists')
        print('no usable checkpoint; refusing to write'); return 1

    # 6. NARROW FIX: replace only the defective save tail.
    source = (project / 'app.py').read_text(encoding='utf-8')
    before_sha = digest(project / 'app.py')
    if source.count(DEFECTIVE_SAVE) != 1:
        print('defective block not uniquely found'); return 1
    (project / 'app.py').write_text(source.replace(DEFECTIVE_SAVE, FIXED_SAVE), encoding='utf-8')
    after_sha = digest(project / 'app.py')
    changed_lines = sum(1 for a, b in zip(source.splitlines(),
                        (project / 'app.py').read_text(encoding='utf-8').splitlines()) if a != b)
    step('narrow_fix', before_sha256=before_sha, after_sha256=after_sha,
         changed_line_count=changed_lines)

    # 7. RE-RUN is the verification. A claim of success is not accepted.
    for stale in (project / 'settings.json', project / 'settings.json.tmp'):
        if stale.is_file():
            stale.unlink()
    rerun_set = run_app(project, 'set', 'theme', 'dark')
    rerun_get = run_app(project, 'get', 'theme')
    verified = rerun_get['stdout'] == '"dark"' and rerun_get['exit_code'] == 0
    task.record_round(action='rerun_verify', status='completed' if verified else 'failed',
                      observation={'get': rerun_get['stdout']})
    step('rerun_verification', set_run=rerun_set, get_run=rerun_get, verified=verified,
         settings_sha256=digest(project / 'settings.json'))

    # 8. Conclusion: only a real re-run may close this as completed.
    if verified:
        outcome = task.conclude('completed', summary='Ayar kaydetme hatası düzeltildi ve '
                                'yeniden çalıştırma ile doğrulandı.', verified_by='rerun')
    else:
        outcome = task.conclude('blocked', summary='Düzeltme yeniden çalıştırmada doğrulanamadı.')
    evidence['outcome'] = outcome
    evidence['rounds'] = task.summary()['rounds']
    evidence['unverified_completion_rejected'] = True
    try:
        task.conclude('completed', summary='model öyle diyor', verified_by='model_claim')
        evidence['unverified_completion_rejected'] = False
    except Exception:
        pass

    destination = Path(options.out).resolve() if options.out else workspace / 'evidence'
    destination.mkdir(parents=True, exist_ok=True)
    manifest = destination / 'chat-investigation-scenario.json'
    manifest.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'verified': verified, 'outcome': outcome['status'],
                      'rounds': evidence['rounds'], 'manifest': str(manifest),
                      'manifest_sha256': digest(manifest)}, indent=2, ensure_ascii=False))
    if options.out is None:
        holder.cleanup()
    return 0 if verified and outcome['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
