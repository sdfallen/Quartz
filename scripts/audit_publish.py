"""Read-only publication audit. Never prints secret values or changes Git state.

Scans the working publication set (or index with --staged), optionally the HEAD
ancestry. Other local branches/checkpoint refs are NOT publication targets.
This is a defense-in-depth check, not a comprehensive secret detector.
"""
import argparse
import fnmatch
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_NAMES = {
    '.env', 'chat_history.json', 'quartz_conversations.json', 'jarvis_memory.json',
    'quartz_memory.json', 'quartz_projects.json', 'quartz_operation.json',
    'quartz_tasks.json', 'quartz_workflows.json', 'quartz_agent_runs.json',
    'mobile_access.json', 'mcp_skills.json', 'credentials.json', 'token.json',
    'tokens.json', 'auth.json', 'auth-state.json',
    'oauth_creds.json', 'cookies', 'cookies-journal', 'login data', 'web data',
    'cli_connections.json', 'gemini-oauth-check.json',
}
PRIVATE_DIRS = {'labs', 'dist', 'build', 'vision_captures', '.squad', '.quartz', '.agents', '.venv', 'venv'}
PRIVATE_DIRS |= {'.codex', '.gemini', '.agy', 'quartz_deleted_chats', 'user data',
                 'local storage', 'session storage', 'network', 'webview2', 'ebwebview'}
TOKEN_PATTERNS = {
    'github-token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
    'provider-key': rb'\b(?:nvapi-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,}|AIza[A-Za-z0-9_-]{30,})\b',
    'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
}


def git(*args, data=None):
    return subprocess.run(['git', '-C', str(ROOT), *args], input=data,
                          capture_output=True, check=True).stdout


def _approved_bundled_binary(posix_path, content=None):
    if posix_path != 'assets/bin/squad.exe':
        return False
    license_file = ROOT / 'assets/bin/SQUAD-LICENSE.txt'
    prov_file = ROOT / 'assets/bin/SQUAD-PROVENANCE.json'
    if not license_file.is_file() or not prov_file.is_file():
        return False
    try:
        prov = json.loads(prov_file.read_text(encoding='utf-8'))
        expected_sha = str(prov.get('sha256') or '').strip().lower()
        if prov.get('license') != 'MIT' or len(expected_sha) != 64:
            return False
        if content is None:
            target = ROOT / 'assets/bin/squad.exe'
            if not target.is_file():
                return False
            content = target.read_bytes()
        return hashlib.sha256(content).hexdigest().lower() == expected_sha
    except Exception:
        return False


def forbidden_path(path, content=None):
    posix_path = PurePosixPath(path.replace('\\', '/')).as_posix()
    if _approved_bundled_binary(posix_path, content):
        return False
    parts = PurePosixPath(posix_path).parts
    name = parts[-1].lower() if parts else ''
    return (name in PRIVATE_NAMES or any(p.lower() in PRIVATE_DIRS for p in parts[:-1])
            or (name.startswith('.env.') and name != '.env.example')
            or any(fnmatch.fnmatch(name, pattern) for pattern in
                   ('*.log', '*.log.*', '*.log-*', '*.pem', '*.key', '*.pfx', '*.p12',
                    '*.db', '*.db-*', '*.sqlite*', '*.exe', '*.msi')))


def content_rules(content, local_secrets=()):
    rules = [name for name, pattern in TOKEN_PATTERNS.items() if re.search(pattern, content)]
    if any(secret and secret in content for secret in local_secrets):
        rules.append('local-env-secret-match')
    return rules


def audit_package(directory, local_secrets=()):
    """Scan a NEW-USER package, not the developer's preserved working dist.

    Root allowlist prevents accidental history/settings extras. Runtime trees
    may contain third-party executables but never browser profiles/credentials.
    """
    root = Path(directory).resolve(strict=True)
    findings, count = [], 0
    for file in root.rglob('*'):
        relative = file.relative_to(root).as_posix()
        parts = relative.lower().split('/')
        if file.is_symlink() or getattr(file, 'is_junction', lambda: False)():
            findings.append({'path': relative, 'rule': 'link-not-allowed'})
            continue
        if not file.is_file():
            continue
        count += 1
        name = parts[-1]
        content = file.read_bytes()
        public_ca = False
        ca_sources = {'_internal/certifi/cacert.pem': ('certifi', 'cacert.pem'),
                      '_internal/grpc/_cython/_credentials/roots.pem': ('grpc', '_cython/_credentials/roots.pem')}
        if relative in ca_sources:
            module, resource = ca_sources[relative]
            spec = importlib.util.find_spec(module)
            if spec and spec.origin:
                original = Path(spec.origin).parent / resource
                public_ca = (original.is_file() and b'-----BEGIN CERTIFICATE-----' in content
                             and original.read_bytes() == content)
        if (parts[0] not in {'quartz.exe', '_internal', 'readme.txt', 'release-manifest.json'}
                or (len(parts) > 1 and parts[0] != '_internal')
                or name in PRIVATE_NAMES or name in {'brand-manifest.json'} or name.startswith('.env')
                or any(part in PRIVATE_DIRS for part in parts)
                or any(fnmatch.fnmatch(name, pattern) for pattern in ('*.log*', '*.db*', '*.sqlite*', '*.key', '*.pfx', '*.p12'))
                or (name.endswith('.pem') and not public_ca)):
            findings.append({'path': relative, 'rule': 'personal-or-unexpected-package-path'})
        for rule in content_rules(content, local_secrets):
            findings.append({'path': relative, 'rule': rule})
    if not (root / 'Quartz.exe').is_file() or not (root / '_internal').is_dir():
        findings.append({'path': '.', 'rule': 'incomplete-package'})
    manifest_file = root / 'release-manifest.json'
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
            recorded = manifest['files']
            actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in root.rglob('*') if p.is_file() and p != manifest_file}
            if recorded != actual or manifest.get('personal_data_included') is not False:
                findings.append({'path': 'release-manifest.json', 'rule': 'release-manifest-mismatch'})
        except (OSError, ValueError, KeyError, TypeError):
            findings.append({'path': 'release-manifest.json', 'rule': 'invalid-release-manifest'})
    return {'status': 'FAIL' if findings else 'PASS', 'files': count,
            'findings': findings, 'secrets_printed': False}


def env_secrets():
    result = []
    for path in (ROOT / '.env', ROOT / 'dist/Quartz/.env'):
        if not path.is_file():
            continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            if sep and re.search(r'(?:KEY|TOKEN|SECRET|PASSWORD)', key, re.I):
                value = value.strip().strip('"\'')
                if len(value) >= 8:
                    result.append(value.encode('utf-8'))
    return result


def batch_blobs(objects):
    if not objects:
        return
    data = git('cat-file', '--batch', data=('\n'.join(objects) + '\n').encode('ascii'))
    offset = 0
    for requested in objects:
        end = data.index(b'\n', offset)
        fields = data[offset:end].split()
        if len(fields) != 3 or fields[1] != b'blob':
            raise RuntimeError('Expected a Git blob; publication audit incomplete')
        size = int(fields[2]); offset = end + 1
        yield requested, data[offset:offset + size]
        offset += size + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--package', type=Path, help='Audit a clean new-user distribution')
    args = parser.parse_args()
    secrets = env_secrets()
    if args.package:
        result = audit_package(args.package, secrets)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'PASS' else 1
    findings, counts = [], {'current_files': 0, 'history_blobs': 0}

    def inspect(scope, path, content):
        rules = content_rules(content, secrets)
        if forbidden_path(path, content):
            rules.append('private-or-runtime-path')
        if len(content) >= 90 * 1024 * 1024:
            rules.append('large-git-blob')
        for rule in rules:
            findings.append({'scope': scope, 'path': path, 'rule': rule})

    if args.staged:
        rows = git('ls-files', '--stage', '-z').decode('utf-8').split('\0')
        entries = {}
        for row in filter(None, rows):
            metadata, path = row.split('\t', 1)
            mode, oid, stage = metadata.split()
            if stage != '0' or mode in {'120000', '160000'}:
                raise RuntimeError('Unmerged/symlink/submodule index needs manual review')
            entries.setdefault(oid, []).append(path)
        for oid, content in batch_blobs(list(entries)):
            for path in entries[oid]:
                inspect('index', path, content); counts['current_files'] += 1
    else:
        paths = set(git('ls-files', '-c', '-o', '--exclude-standard', '-z').decode('utf-8').split('\0'))
        for path in sorted(filter(None, paths)):
            file = ROOT / path
            if file.is_symlink():
                raise RuntimeError('Symlink needs manual review')
            if file.is_file():
                inspect('working-tree', path, file.read_bytes()); counts['current_files'] += 1
    if args.history:
        entries = {}
        # Restrict to the intended branch ancestry. Never include backup refs.
        for row in git('rev-list', '--objects', 'HEAD').decode('utf-8').splitlines():
            oid, _, path = row.partition(' ')
            if path:
                entries[oid] = path
        types = git('cat-file', '--batch-check=%(objectname) %(objecttype)',
                    data=('\n'.join(entries) + '\n').encode('ascii')).decode('ascii')
        blobs = [line.split()[0] for line in types.splitlines() if line.endswith(' blob')]
        for oid, content in batch_blobs(blobs):
            inspect('HEAD-history', entries[oid], content); counts['history_blobs'] += 1
    print(json.dumps({'status': 'PASS' if not findings else 'FAIL', **counts,
                      'findings': findings, 'secrets_printed': False}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
