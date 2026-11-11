"""Actual disposable owner jobs and catalog resolution; no UI, model or network."""
from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from core.artifact_diagnostics import ArtifactDiagnosticsService
from core.application_services import ApplicationServices
from core.investigation.chat_task import ChatInvestigationTask, classify_investigation_request
from core.investigation.contracts import InvestigationError
from core.investigation.planning import InvestigationPolicy
from core.tool_workbench import ToolWorkbench, ToolManifest
from core.tool_workbench.catalog import ToolCatalog


class ChatTaskOwnerReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = self.root / 'application.zip'
        with zipfile.ZipFile(self.target, 'w') as archive:
            archive.writestr('settings.json', '{}')
        self.owners, self.gates = [], []

    def tearDown(self):
        for release in self.gates:
            release.set()
        for owner in self.owners:
            owner.shutdown()
        self.temp.cleanup()

    def make_owner(self):
        owner = ArtifactDiagnosticsService(self.target, knowledge=False, investigation=False,
            analysis_enabled=False, reports=self.root / 'reports', investigation_root=self.root / 'investigations')
        self.owners.append(owner)
        return owner

    def make_task(self, owner=None, *, text='Bu uygulamanın yapısını incele.', policy=None):
        task = ChatInvestigationTask(classify_investigation_request(text), task_id='chat.t1',
                                     conversation_id='conversation1', policy=policy)
        if owner is not None:
            task.bind_owner(owner)
        return task

    def start(self, *, blocked=False, text='Bu uygulamanın yapısını incele.', policy=None, check=None):
        owner = self.make_owner()
        task = self.make_task(owner, text=text, policy=policy)
        entered, release = threading.Event(), threading.Event()
        self.gates.append(release)
        original = owner._inspect

        def inspect(identity, event, deadline, include_rea):
            entered.set()
            if blocked:
                if not release.wait(3):
                    raise RuntimeError('fixture gate timeout')
            original(identity, event, deadline, include_rea)
            if check:
                owner._check(identity, 'registered_tool', check, 'Registered tool', 'Fixture check')

        owner._inspect = inspect
        job = owner.start(include_rea=False)
        self.assertTrue(entered.wait(2))
        task.attach_job(job['id'])
        return task, owner, job['id'], release

    def finish(self, owner, identity):
        owner.threads[identity].join(3)
        self.assertFalse(owner.threads[identity].is_alive())

    def test_real_job_is_attached_before_static_completion_is_reported(self):
        owner = self.make_owner()
        task = self.make_task(owner)
        self.assertEqual(task.summary()['state'], 'awaiting_job')
        self.assertEqual(owner.jobs, {})  # binding does not start work
        job = owner.start(include_rea=False)
        self.finish(owner, job['id'])
        task.attach_job(job['id'])
        result = task.summary()
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['verification'], 'SOURCE')
        self.assertFalse(result['fix_verified'])
        self.assertEqual(task.job_id, job['id'])
        self.assertIs(task.owner, owner)
        with self.assertRaises(AttributeError):
            task.job_id = 'other'

    def test_registry_retains_terminal_record_until_cleanup_is_confirmed(self):
        task, owner, identity, _ = self.start()
        self.finish(owner, identity)
        owner._gateway_cleanup[identity] = {'status': 'pending'}
        services = ApplicationServices()
        services.register_chat_task(task)
        self.assertEqual(task.summary()['state'], 'blocked')
        self.assertEqual(services.open_chat_tasks(), [task])
        another = ChatInvestigationTask(task.request, task_id='chat.t2', conversation_id='conversation1')
        services.register_chat_task(another)
        self.assertIs(services.chat_task(task.task_id), task)
        owner._gateway_cleanup[identity] = {'status': 'confirmed'}
        self.assertEqual(task.summary()['state'], 'completed')
        services.register_chat_task(ChatInvestigationTask(task.request, task_id='chat.t3', conversation_id='conversation1'))
        self.assertIsNone(services.chat_task(task.task_id))

    def test_registry_rejects_identity_collision_without_replacing_owner(self):
        services = ApplicationServices()
        task = self.make_task()
        services.register_chat_task(task)
        with self.assertRaisesRegex(RuntimeError, 'duplicate-chat-task'):
            services.register_chat_task(self.make_task())
        self.assertIs(services.chat_task(task.task_id), task)

    def test_shutdown_reports_cancel_failure_instead_of_confirmed_stop(self):
        services = ApplicationServices()
        task = self.make_task()
        services.register_chat_task(task)
        with patch.object(task, 'cancel', side_effect=RuntimeError('fixture cancel failure')):
            result = services.shutdown()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['components']['chat_tasks'], 'failed')
        self.assertTrue(any(item['code'] == 'cancel_failed' for item in result['errors']))

    def test_target_shaped_objects_are_not_host_owners(self):
        class Shaped:
            target = 'fake.zip'
            identity = (1, 2, 3, 4)
        with self.assertRaises(InvestigationError):
            self.make_task().bind_owner(Shaped())

    def test_job_cannot_be_retargeted_or_invented(self):
        task, owner, identity, _ = self.start(blocked=True)
        self.assertEqual(task.attach_job(identity)['job_id'], identity)
        with self.assertRaises(InvestigationError):
            task.attach_job('unowned-job')
        self.assertEqual(task.job_id, identity)

    def test_stop_calls_exact_owner_job_and_waits_for_actual_worker_exit(self):
        task, owner, identity, release = self.start(blocked=True)
        with patch.object(owner, 'cancel', wraps=owner.cancel) as cancel:
            first = task.cancel('first stop')
            self.assertEqual(first['status'], 'cancelling')
            self.assertFalse(first['stop_confirmed'])
            self.assertTrue(owner.events[identity].is_set())
            self.assertTrue(owner.threads[identity].is_alive())
            task.cancel('duplicate stop')
            cancel.assert_called_once_with(identity)
            release.set()
            self.finish(owner, identity)
            final = task.summary()
            self.assertEqual(final['state'], 'cancelled')
            self.assertTrue(final['outcome']['stop_confirmed'])
            self.assertEqual(final['outcome']['summary'], 'first stop')

    def test_stop_before_job_attachment_cancels_the_late_attached_job(self):
        owner = self.make_owner()
        task = self.make_task(owner)
        self.assertEqual(task.cancel()['status'], 'cancelling')
        entered, release = threading.Event(), threading.Event()
        self.gates.append(release)
        original = owner._inspect
        def inspect(*args):
            entered.set()
            release.wait(3)
            return original(*args)
        owner._inspect = inspect
        job = owner.start(include_rea=False)
        self.assertTrue(entered.wait(2))
        task.attach_job(job['id'])
        self.assertTrue(owner.events[job['id']].is_set())
        release.set()
        self.finish(owner, job['id'])
        self.assertEqual(task.summary()['state'], 'cancelled')

    def test_actual_owner_completion_invalidates_a_pending_permission(self):
        task, owner, identity, release = self.start(blocked=True)
        pending = task.request_scope('read_target', 'Read selected file')['pending_permission']
        release.set()
        self.finish(owner, identity)
        with self.assertRaises(InvestigationError):
            task.grant_scope(request_id=pending['request_id'], generation=pending['generation'], effect='read_target')
        self.assertEqual(task.summary()['state'], 'completed')
        self.assertEqual(task.granted_effects, frozenset())

    def test_duplicate_scope_request_keeps_one_generation(self):
        task, _, _, _ = self.start(blocked=True)
        first = task.request_scope('read_target', 'Read selected file')
        self.assertEqual(task.request_scope('read_target', 'Read selected file'), first)
        second = task.request_scope('read_target', 'Another reason')
        self.assertNotEqual(second['pending_permission']['request_id'], first['pending_permission']['request_id'])

    def test_failed_owner_job_is_not_inferred_to_be_a_completed_scan(self):
        owner = self.make_owner()
        task = self.make_task(owner)
        owner._inspect = lambda *args: (_ for _ in ()).throw(ValueError('fixture failure'))
        job = owner.start(include_rea=False)['id']
        self.finish(owner, job)
        task.attach_job(job)
        result = task.summary()
        self.assertEqual(result['state'], 'failed')
        self.assertTrue(result['stop_confirmed'])
        self.assertFalse(result['fix_verified'])

    def test_pending_tool_cleanup_keeps_stop_unconfirmed_after_worker_exit(self):
        task, owner, identity, release = self.start(blocked=True)
        task.cancel()
        release.set(); self.finish(owner, identity)
        owner._gateway_cleanup[identity] = {'status':'pending'}
        self.assertEqual(task.summary()['state'], 'cancelling')
        self.assertFalse(task.summary()['stop_confirmed'])
        owner._gateway_cleanup[identity] = {'status':'confirmed'}
        self.assertEqual(task.summary()['state'], 'cancelled')
        self.assertTrue(task.summary()['stop_confirmed'])

    def test_completed_static_job_is_not_rewritten_as_cancelled_by_owner_shutdown(self):
        task, owner, identity, _ = self.start()
        self.finish(owner, identity)
        first = task.summary()
        self.assertTrue(first['stop_confirmed'])
        owner.shutdown()  # sets its event even for already-completed jobs
        self.assertEqual(task.summary()['state'], 'completed')
        self.assertEqual(task.cancel()['status'], 'completed')
        with self.assertRaises(InvestigationError):
            task.conclude('completed', summary='a live fix', verified_by='rerun')

    def test_cancellation_error_can_be_retried_without_publishing_success(self):
        task, owner, identity, release = self.start(blocked=True)
        with patch.object(owner, 'cancel', side_effect=OSError('fixture error')):
            self.assertEqual(task.cancel()['status'], 'cancelling')
        self.assertFalse(owner.events[identity].is_set())
        self.assertEqual(task.cancel()['status'], 'cancelling')
        self.assertTrue(owner.events[identity].is_set())
        release.set(); self.finish(owner, identity)
        self.assertTrue(task.summary()['stop_confirmed'])

    def test_raw_permission_types_are_not_coerced(self):
        task, _, _, _ = self.start(blocked=True)
        pending = task.request_scope('read_target', 'Read selected file')['pending_permission']
        good = dict(request_id=pending['request_id'], generation=pending['generation'], effect='read_target', granted=True)
        for change in ({'generation':True}, {'generation':'1'}, {'request_id':1},
                       {'effect':['read_target']}, {'granted':1}, {'granted':'true'}, {'granted':None}):
            with self.subTest(change=change), self.assertRaises(InvestigationError):
                task.grant_scope(**dict(good, **change))
        self.assertEqual(task.summary()['pending_permission'], pending)
        for effect in (None, [], True):
            with self.assertRaises(InvestigationError): task.request_scope(effect, 'reason')

    def test_simultaneous_duplicate_grants_are_consumed_once(self):
        task, _, _, _ = self.start(blocked=True)
        pending = task.request_scope('read_target', 'Read selected file')['pending_permission']
        barrier = threading.Barrier(2)
        answers = []
        def grant():
            barrier.wait(2)
            try:
                task.grant_scope(request_id=pending['request_id'], generation=pending['generation'], effect='read_target')
                answers.append('granted')
            except InvestigationError:
                answers.append('stale')
        workers = [threading.Thread(target=grant) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertCountEqual(answers, ['granted', 'stale'])

    def test_free_verification_tag_does_not_complete_a_running_job_or_fix(self):
        task, owner, identity, release = self.start(blocked=True,
            text='Bu uygulamadaki hatayı incele ve düzelt.')
        with self.assertRaises(InvestigationError):
            task.conclude('completed', summary='fixed', verified_by='fresh_observation', evidence_ids=[])
        release.set()
        self.finish(owner, identity)
        self.assertEqual(task.summary()['state'], 'blocked')
        self.assertFalse(task.summary()['fix_verified'])
        with self.assertRaises(InvestigationError):
            task.conclude('completed', summary='fixed', verified_by='rerun', evidence_ids=['invented'])

    def test_missing_or_unknown_registered_search_is_not_completed(self):
        for check in (None, 'UNKNOWN', 'NOT_TESTED'):
            task, owner, identity, _ = self.start(text='Bu uygulamanın stringlerini incele.', check=check)
            self.finish(owner, identity)
            result = task.summary()
            self.assertEqual(result['state'], 'blocked')
            self.assertEqual(result['verification'], 'SOURCE')
        task, owner, identity, _ = self.start(text='Bu uygulamanın stringlerini incele.', check='PASS')
        self.finish(owner, identity)
        self.assertEqual(task.summary()['state'], 'completed')
        self.assertFalse(task.summary()['fix_verified'])

    def test_summary_and_stop_never_use_latest_unrelated_job(self):
        task, owner, identity, _ = self.start()
        self.finish(owner, identity)
        entered, release = threading.Event(), threading.Event()
        self.gates.append(release)
        original = owner._inspect
        def inspect(*args):
            entered.set(); release.wait(3); return original(*args)
        owner._inspect = inspect
        second = owner.start(include_rea=False)['id']
        self.assertTrue(entered.wait(2))
        self.assertNotEqual(identity, second)
        self.assertEqual(task.summary()['job_id'], identity)
        self.assertEqual(task.summary()['state'], 'completed')
        task.cancel()
        self.assertFalse(owner.events[second].is_set())

    def test_owner_read_error_never_confirms_stop(self):
        task, owner, _, _ = self.start(blocked=True)
        task.cancel()
        with patch.object(owner, 'status', side_effect=OSError('fixture private detail')):
            result = task.summary()
        self.assertEqual(result['state'], 'cancelling')
        self.assertFalse(result['outcome']['stop_confirmed'])
        self.assertEqual(result['owner_error_type'], 'OSError')

    def test_cancelled_task_cannot_be_reopened_by_conclude(self):
        task, owner, identity, release = self.start(blocked=True)
        task.cancel()
        release.set(); self.finish(owner, identity)
        with self.assertRaises(InvestigationError):
            task.conclude('completed', summary='late result', verified_by='rerun')
        self.assertEqual(task.summary()['state'], 'cancelled')

    def test_real_catalog_resolution_plans_only_registered_immutable_manifest(self):
        policy = InvestigationPolicy(effects=frozenset({'read_target', 'execute_tool'}), allow_acquire=True)
        task, _, _, _ = self.start(blocked=True, policy=policy)
        pending = task.request_scope('execute_tool', 'Search selected file')['pending_permission']
        task.grant_scope(request_id=pending['request_id'], generation=pending['generation'], effect='execute_tool')
        manifest = ToolManifest('local-search', 'Local test tool', '1',
            'https://github.com/quartz-tests/fixture/archive.zip', 'fixture-1', 'a' * 64,
            'test', ['any'], ['pattern_search'], 'scan.py', {'search': {'options': {}}})
        workbench = ToolWorkbench(managed_dir=self.root / 'managed', workspace_dir=self.root / 'work',
                                  catalog=ToolCatalog({manifest.tool_id: manifest}))
        self.addCleanup(workbench.close)
        with patch.object(workbench, 'acquire', side_effect=AssertionError('No network/acquisition')):
            result = task.plan_external_tool(['pattern_search'], workbench)
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(result['candidates'][0]['manifest'], manifest.to_dict())
        actual = workbench.resolve({'capability_id':'pattern_search'})
        for field in ('source_url', 'pinned_revision', 'package_digest'):
            changed = deepcopy(actual)
            changed['manifest'][field] = 'untrusted-value'
            with patch.object(workbench, 'resolve', return_value=changed):
                self.assertEqual(task.plan_external_tool(['pattern_search'], workbench)['status'], 'unsupported')
        with patch.object(workbench, 'resolve', return_value={'status':'resolved', 'tool_manifest':manifest.to_dict()}):
            self.assertEqual(task.plan_external_tool(['pattern_search'], workbench)['status'], 'unsupported')


class SearchClassificationReviewTests(unittest.TestCase):
    def test_explicit_literal_and_generic_strings_have_bounded_patterns(self):
        request = classify_investigation_request('Bu uygulamada "SAVE.ERROR[1]" ifadesini ara.')
        self.assertTrue(request['search_requested'])
        self.assertEqual(request['search_literal'], 'SAVE.ERROR[1]')
        self.assertEqual(request['search_pattern'], r'SAVE\.ERROR\[1\]')
        request = classify_investigation_request('Bu uygulamada SAVE_ERROR ifadesini ara.')
        self.assertEqual(request['search_pattern'], 'SAVE_ERROR')
        self.assertEqual(classify_investigation_request('Bu uygulamanın dizelerini incele.')['search_pattern'], '[ -~]{4,}')

    def test_quoted_commands_code_and_discussion_are_not_search_authority(self):
        for text in ('"Bu uygulamanın stringlerini ara"', "'Bu uygulamanın dizelerini incele'",
                     '```Bu uygulamanın stringlerini ara```', 'Sadece sohbet edelim; uygulamanın stringlerini ara',
                     'Uygulamada ara ne işe yarıyor?', 'Uygulamanın stringleri hakkında ne düşünüyorsun?'):
            with self.subTest(text=text):
                self.assertIsNone(classify_investigation_request(text))

    def test_quoted_application_or_question_name_does_not_request_a_search_tool(self):
        for text in ('"Foo.exe" uygulamasını incele.',
                     'Bu uygulamadaki "kayıt hatası" sorununu incele.',
                     'Bu paketteki "ayar" ifadesini incele.'):
            with self.subTest(text=text):
                request = classify_investigation_request(text)
                self.assertIsNotNone(request)
                self.assertFalse(request['search_requested'])
                self.assertIsNone(request['search_pattern'])


if __name__ == '__main__':
    unittest.main()
