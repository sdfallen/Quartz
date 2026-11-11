"""Nonblocking environment-health projection of existing chat diagnostics."""
import json
import threading
from core.async_snapshot import AsyncSnapshot


class ChatEnvironmentHealth:
    def __init__(self):
        self.snapshot = AsyncSnapshot(self._load, ttl=60)
        self.lock = threading.Lock()
        self.serial = 0

    @staticmethod
    def _load(key):
        from core.environment_health import check
        from core.cli_installer import cli_environment
        path, mode, raw_json, _ = key
        raw = json.loads(raw_json)
        source = cli_environment()
        env = {k: v for k, v in source.items() if k.upper() in {
            'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC'}}
        return check(path, mode=mode, agents=raw, squad=raw['squad'],
                     force=True, env=env)

    def read(self, project_path, mode, raw_status, force=False):
        # Probe only existing diagnostics; missing providers remain unknown, never
        # launch another Runtime.probe from the status poll.
        raw = {}
        fields = ('installed', 'authenticated', 'ready', 'checking', 'initialized', 'connected', 'mode', 'error')
        for provider in ('codex', 'antigravity', 'squad'):
            entry = raw_status.get(provider) or {}
            raw[provider] = {k: entry[k] for k in fields if k in entry} if isinstance(entry, dict) else {}
            if not raw[provider]:
                raw[provider] = {'checking': True}
        seed = {'status': 'warn', 'checks': [{'id': 'environment_health', 'status': 'unknown',
                'summary_tr': 'Ortam kontrol ediliyor.', 'fix_tr': '', 'detail': ''}]}
        if not isinstance(project_path, str) or not project_path:
            return seed
        with self.lock:
            if force is True:
                self.serial += 1
            key = (project_path, mode, json.dumps(raw, sort_keys=True, default=str), self.serial)
            result, state = self.snapshot.read(key, seed)
        result['diagnostics'] = state
        return result

    def close(self):
        self.snapshot.close()
