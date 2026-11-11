import tempfile
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from tests import test_multi_agent_service as fixtures


class SquadConnectionCacheTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.squad_dir = self.root / ".squad"
        self.squad_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.squad_dir / "messages.db"
        self.db_path.write_bytes(b"fixture")

        self.service, _, _ = fixtures.MultiAgentServiceTests().make_service()
        self.project = {"id": "test-proj", "name": "TestProj", "path": str(self.root), "protected": False}
        self.service.projects.add(str(self.root), "TestProj")
        # Ensure project id is consistent
        self.project = self.service.projects.list()[-1]

        self.squad = MagicMock()
        self.squad.status.return_value = {
            "installed": True,
            "initialized": True,
            "database": str(self.db_path),
            "version": "1.0.0",
            "error": "",
        }

    def test_connected_cache_hit_when_database_exists(self):
        with patch.object(self.service, "_squad", return_value=self.squad) as mock_squad, \
             patch.object(self.service, "_ensure_agent"):
            first = self.service.check_squad_connection(self.project["id"], force=True)
            self.assertTrue(first["connected"])
            self.assertEqual(mock_squad.call_count, 1)

            # Within 30 seconds with db present -> cached result reused, _squad not called again
            second = self.service.check_squad_connection(self.project["id"])
            self.assertTrue(second["connected"])
            self.assertEqual(mock_squad.call_count, 1)

    def test_connected_cache_bypassed_when_database_missing(self):
        with patch.object(self.service, "_squad", return_value=self.squad) as mock_squad, \
             patch.object(self.service, "_ensure_agent"):
            first = self.service.check_squad_connection(self.project["id"], force=True)
            self.assertTrue(first["connected"])
            self.assertEqual(mock_squad.call_count, 1)

            # Delete messages.db
            self.db_path.unlink()
            self.assertFalse(self.db_path.exists())

            # Configure squad mock for when workspace is uninitialized / missing db
            self.squad.status.return_value = {
                "installed": True,
                "initialized": False,
                "database": "",
                "error": "Squad çalışma alanı hazır değil.",
            }
            # Next call must bypass cache and re-check squad
            second = self.service.check_squad_connection(self.project["id"])
            self.assertEqual(mock_squad.call_count, 2)
            self.assertFalse(second["connected"])

    def test_disconnected_cache_not_affected_by_database_check(self):
        with patch.object(self.service, "_squad", return_value=self.squad) as mock_squad, \
             patch.object(self.service, "_ensure_agent"):
            self.squad.status.return_value = {
                "installed": False,
                "initialized": False,
                "database": "",
                "error": "Squad kurulu değil.",
            }
            first = self.service.check_squad_connection(self.project["id"], force=True)
            self.assertFalse(first["connected"])
            self.assertEqual(mock_squad.call_count, 1)

            # Cached disconnected status is returned without re-querying squad
            second = self.service.check_squad_connection(self.project["id"])
            self.assertFalse(second["connected"])
            self.assertEqual(mock_squad.call_count, 1)
