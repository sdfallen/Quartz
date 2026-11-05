import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch
from tests import test_multi_agent_service as fixtures


class SquadIdleCacheTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.squad').mkdir()
        (self.root / '.squad/messages.db').write_bytes(b'fixture')
        self.project = {'id':'test', 'path':str(self.root)}
        self.service, _, _ = fixtures.MultiAgentServiceTests().make_service()
        self.squad = MagicMock()
        self.squad.status.return_value = {'installed':True, 'error':''}
        self.squad.agents.return_value = [{'id':'a'}]
        self.squad.tasks.return_value = []
        self.squad.history.return_value = []

    def read(self): return self.service._squad_snapshot(self.project, self.squad)

    def test_idle_reads_reuse_snapshot_and_return_copies(self):
        self.read()[1][0]['id'] = 'mutated'
        for _ in range(20): self.assertEqual(self.read()[1][0]['id'], 'a')
        self.assertEqual(self.squad.status.call_count, 1)

    def test_database_and_wal_changes_invalidate(self):
        self.read()
        (self.root / '.squad/messages.db-wal').write_bytes(b'new message')
        self.read()
        (self.root / '.squad/messages.db').write_bytes(b'new database')
        self.read()
        self.assertEqual(self.squad.tasks.call_count, 3)

    def test_active_run_bypasses_cache_and_next_idle_refreshes(self):
        self.read()
        self.service._links['r'] = {'project_id':'test', 'reported':False}
        self.read(); self.read()
        self.service._links['r']['reported'] = True
        self.read(); self.read()
        self.assertEqual(self.squad.tasks.call_count, 4)

    def test_errors_missing_database_and_ttl_do_not_freeze_readiness(self):
        self.squad.tasks.side_effect = RuntimeError('offline')
        self.assertTrue(self.read()[-1]); self.read()
        self.assertEqual(self.squad.tasks.call_count, 2)
        self.squad.tasks.side_effect = None
        with patch('core.multi_agent_service.time.monotonic', return_value=100): self.read()
        with patch('core.multi_agent_service.time.monotonic', return_value=401): self.read()
        self.assertEqual(self.squad.tasks.call_count, 4)
        (self.root / '.squad/messages.db').unlink()
        self.read(); self.read()
        self.assertEqual(self.squad.tasks.call_count, 6)

    def test_project_keys_are_isolated(self):
        self.read()
        other = self.root / 'other'; (other / '.squad').mkdir(parents=True)
        (other / '.squad/messages.db').write_bytes(b'other')
        self.service._squad_snapshot({'id':'other','path':str(other)}, self.squad)
        self.assertEqual(self.squad.tasks.call_count, 2)
