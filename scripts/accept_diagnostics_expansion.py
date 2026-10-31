"""Real file/service acceptance on disposable copies; NOT packaged chat acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.package_repair import PackageRepair
from core.artifact_diagnostics import ArtifactDiagnosticsService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    result = {'scope': 'Real file IO and REA services on disposable copies; not GUI acceptance'}
    before = PackageRepair.digest(args.package/'Quartz.exe')
    with tempfile.TemporaryDirectory(prefix='quartz-repair-acceptance-') as folder:
        root = Path(folder)
        reference, target = root/'reference', root/'target'
        for location in (reference, target):
            location.mkdir()
            for name in ('Quartz.exe', *PackageRepair.ALLOWED):
                destination = location/name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(args.package/name, destination)
        files = {name: PackageRepair.digest(reference/name) for name in ('Quartz.exe', *PackageRepair.ALLOWED)}
        (reference/'release-manifest.json').write_text(json.dumps({'files': files}))
        css = target/PackageRepair.ALLOWED[0]
        css.write_bytes(b'/* Deliberately damaged disposable fixture, never deployed */')
        damaged = PackageRepair.digest(css)
        service = PackageRepair(target, args.evidence/'repair-backups')
        plan = service.prepare(reference)
        outcome = service.apply(plan['id'])
        assert outcome['state'] == 'verified'
        assert PackageRepair.digest(css) == files[PackageRepair.ALLOWED[0]]
        assert PackageRepair.digest(args.evidence/'repair-backups'/plan['id']/'0') == damaged
        duplicate_denied = False
        try:
            service.apply(plan['id'])
        except ValueError:
            duplicate_denied = True
        assert duplicate_denied
        result['repair'] = {'state': 'verified', 'backup_verified': True,
                            'duplicate_denied': True, 'exe_unchanged': PackageRepair.digest(target/'Quartz.exe') == before}
    original = PackageRepair.digest(args.artifact)
    service = ArtifactDiagnosticsService(args.artifact, reports=args.evidence/'reports')
    try:
        job = service.start()
        service.threads[job['id']].join(195)
        result['artifact'] = service.status()
        assert result['artifact']['state'] != 'running'
        assert PackageRepair.digest(args.artifact) == original
        result['artifact_unchanged'] = True
    finally:
        service.shutdown()
    assert PackageRepair.digest(args.package/'Quartz.exe') == before
    result['source_package_unchanged'] = True
    (args.evidence/'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'repair': result['repair'], 'artifact_state': result['artifact']['state'],
                      'artifact_verdict': result['artifact']['verdict'], 'unchanged': True}, indent=2))


if __name__ == '__main__':
    main()
