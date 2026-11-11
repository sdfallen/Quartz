"""Latency regressions; mocked cloud, no live performance claims."""
import time
import unittest
from unittest.mock import patch

from core.notion_runtime import NotionRuntime
from tests import test_notion_runtime as runtime_tests
from tests.test_notion_runtime import session, event, wait
from tests.test_notion_main_chat_tools import Harness


class LatencyTests(unittest.TestCase):
    setUp = runtime_tests.NotionRuntimeTests.setUp
    reply = runtime_tests.NotionRuntimeTests.reply
    def test_filters_prior_turn_history_and_exposes_observed_timings(self):
        sid = '30000000-0000-0000-0000-000000000001'
        self.runtime._remember(sid, self.runtime.configuration())
        bodies = []
        def reply(path, body=None):
            if path.endswith('/events/query'):
                bodies.append(body)
                return {'results': [event(2, 'old')] if len(bodies) == 1 else [event(3, 'new')], 'has_more': False}
            return session()
        self.client.request.side_effect = reply
        run = wait(self.runtime, self.runtime.start('next', session_id=sid)['id'])
        self.assertEqual(bodies[1]['filter'], {'property': 'sequence', 'number': {'greater_than': 2}})
        self.assertEqual(run['result'], 'new')
        self.assertEqual(run['timings']['request_count'], 4)
        self.assertGreaterEqual(run['timings']['total_ms'], run['timings']['first_text_ms'])
        self.assertGreaterEqual(run['timings']['request_ms'], 0)
        self.assertNotIn('next', str(run['timings']))

    def test_actual_model_metadata_is_not_a_fake_selector(self):
        auto = NotionRuntime.model_capability({'model': {'mode': 'auto'}})
        pinned = NotionRuntime.model_capability({'model': {'mode': 'pinned', 'id': 'real-server-model'}})
        self.assertEqual(auto['label'], 'Otomatik (Notion)')
        self.assertEqual(pinned['id'], 'real-server-model')
        self.assertFalse(pinned['selection_supported'])
        self.assertEqual(NotionRuntime.model_capability()['mode'], 'unknown')

    def test_published_result_is_not_requeried_while_cloud_finishes(self):
        h = Harness(self).start()
        original_get = h.runtime.get
        waits = []
        def delayed_get(rid):
            result = original_get(rid)
            if len(h.cloud.messages) == 2 and len(waits) < 3:
                waits.append(rid)
                result['status'] = 'running'
            return result
        with patch.object(h.runtime, 'get', side_effect=delayed_get):
            h.tools.decide(h.pending(), 'c1', True, confirmed=True)
            status, _, _ = h.result()
        self.assertEqual(status, 'completed')
        self.assertEqual(len(waits), 3)
        self.assertEqual(len(h.queues[0].completed), 1)
        self.assertEqual(h.reads, 1)
