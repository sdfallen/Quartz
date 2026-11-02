"""Main-chat investigation binding: routing, permission continuation, tool gap, Stop.

Scenario letters refer to docs/rea-system/CLAUDE_CHAT_FINALIZATION_PROMPT.md.
These are SOURCE-level regressions with real local persistence where a store is
needed; no Quartz GUI, no packaged build and no real tool acquisition is implied.
"""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from core.application_services import ApplicationServices, ServicesClosed
from core.artifact_diagnostics import ArtifactDiagnosticsService
from core.investigation.chat_task import (
    ChatInvestigationTask, classify_investigation_request, reusable_procedures)
from core.investigation.contracts import InvestigationError
from core.investigation.planning import InvestigationPolicy

TASK_TEXT = ('Bu uygulamadaki ayar kaydetme hatasını incele ve düzelt; '
             'diğer ajan değişikliği kontrol etsin.')


def task(request=None, *, policy=None, max_rounds=8):
    return ChatInvestigationTask(request or classify_investigation_request(TASK_TEXT),
                                 task_id='chat.t1', conversation_id='c1',
                                 policy=policy, max_rounds=max_rounds)


class FakeOwner:
    scope = 'artifact'

    def __init__(self, target='/tmp/app.zip', identity=(1, 2, 3, 4)):
        self.target, self.identity = target, identity


class OrdinaryChatTests(unittest.TestCase):
    """A: ordinary conversation opens no analysis/installation/desktop work."""

    def test_ordinary_messages_are_not_investigation_requests(self):
        for text in ('Merhaba, nasılsın?', 'Python listesi nasıl sıralanır?',
                     'Bugün hava nasıl?', 'Teşekkürler, harika oldu',
                     'Quartz nedir ve neler yapabilir?', '', '   '):
            self.assertIsNone(classify_investigation_request(text), text)

    def test_discussion_and_no_tools_requests_never_authorize(self):
        # Quoted prose and an explicit "just chat" instruction stay text-only.
        self.assertIsNone(classify_investigation_request(
            'Sadece sohbet edelim; "uygulamadaki hatayı incele" demek istemiyorum'))
        self.assertIsNone(classify_investigation_request(
            'Araç kullanma, ama uygulamadaki kaydetme hatasını incele'))

    def test_feature_request_without_a_defect_is_not_an_investigation(self):
        self.assertIsNone(classify_investigation_request('Bu uygulamaya karanlık tema ekle'))
        self.assertIsNone(classify_investigation_request('Uygulamayı derle ve paketle'))

    def test_real_task_is_classified_without_granting_anything(self):
        request = classify_investigation_request(TASK_TEXT)
        self.assertEqual(request['kind'], 'application_investigation')
        self.assertTrue(request['diagnose_requested'] and request['fix_requested'])
        self.assertTrue(request['review_requested'] and request['problem_reported'])
        # Classification is not a grant and not a file path.
        self.assertTrue(request['needs_target'])
        self.assertFalse(request['instruction_authority'])
        self.assertEqual(task(request).granted_effects, frozenset())


class PermissionContinuationTests(unittest.TestCase):
    """B: new scope asks the existing card, then the SAME task continues."""

    def setUp(self):
        self.task = task()
        self.task.bind_owner(FakeOwner())

    def test_target_binding_requires_a_host_built_owner(self):
        fresh = task()
        self.assertEqual(fresh.state, 'awaiting_target')
        with self.assertRaises(InvestigationError):
            fresh.bind_owner(object())  # an arbitrary object is not a selection
        self.assertEqual(fresh.state, 'awaiting_target')
        fresh.bind_owner(FakeOwner())
        self.assertEqual(fresh.state, 'running')
        with self.assertRaises(InvestigationError):
            fresh.bind_owner(FakeOwner('/tmp/other.zip'))  # no silent retarget

    def test_permission_answer_resumes_the_same_task(self):
        pending = self.task.request_scope('read_target', 'Dosya kimliğini doğrulamak için')
        self.assertEqual(self.task.state, 'awaiting_permission')
        self.assertTrue(pending['continues_existing_task'])
        answer = self.task.grant_scope(request_id=pending['pending_permission']['request_id'],
                                       generation=pending['pending_permission']['generation'],
                                       effect='read_target', granted=True)
        self.assertTrue(answer['resumed_same_task'] and answer['granted'])
        self.assertEqual(self.task.state, 'running')
        self.assertEqual(answer['granted_effects'], ['read_target'])

    def test_stale_replayed_and_mismatched_answers_open_no_task(self):
        pending = self.task.request_scope('read_target', 'gerekçe')['pending_permission']
        self.task.grant_scope(request_id=pending['request_id'],
                              generation=pending['generation'], effect='read_target')
        for kwargs in ({'request_id': pending['request_id'], 'generation': pending['generation'],
                        'effect': 'read_target'},                      # replay
                       {'request_id': 'chat.t1.scope.99', 'generation': 99,
                        'effect': 'read_target'},                      # unknown id
                       ):
            with self.assertRaises(InvestigationError):
                self.task.grant_scope(**kwargs)
        self.assertEqual(self.task.granted_effects, frozenset({'read_target'}))

        second = self.task.request_scope('read_target', 'ikinci tur')['pending_permission']
        with self.assertRaises(InvestigationError):  # right id, wrong generation
            self.task.grant_scope(request_id=second['request_id'],
                                  generation=second['generation'] + 1, effect='read_target')
        with self.assertRaises(InvestigationError):  # answer for another effect
            self.task.grant_scope(request_id=second['request_id'],
                                  generation=second['generation'], effect='execute_tool')
        self.assertEqual(self.task.state, 'awaiting_permission')

    def test_task_cannot_ask_beyond_its_own_policy(self):
        with self.assertRaises(InvestigationError):
            self.task.request_scope('execute_target', 'hedefi çalıştır')

    def test_refusal_keeps_the_task_without_the_effect(self):
        pending = self.task.request_scope('read_target', 'gerekçe')['pending_permission']
        answer = self.task.grant_scope(request_id=pending['request_id'],
                                       generation=pending['generation'],
                                       effect='read_target', granted=False)
        self.assertFalse(answer['granted'])
        self.assertEqual(self.task.state, 'running')
        self.assertEqual(self.task.granted_effects, frozenset())


class ToolGapTests(unittest.TestCase):
    """D: a real capability gap plans a registered tool, or says unsupported."""

    def setUp(self):
        self.allowing = InvestigationPolicy(
            effects=frozenset({'read_target', 'write_workspace', 'execute_tool'}),
            allow_acquire=True)

    def grantable(self, policy):
        current = task(policy=policy)
        current.bind_owner(FakeOwner())
        pending = current.request_scope('execute_tool', 'Kayıtlı arama aracı gerekiyor')['pending_permission']
        current.grant_scope(request_id=pending['request_id'],
                            generation=pending['generation'], effect='execute_tool')
        return current

    def test_without_granted_scope_the_gap_is_unsupported(self):
        current = task(policy=self.allowing)
        current.bind_owner(FakeOwner())
        result = current.plan_external_tool(['binary_pattern_search'], Workbench())
        self.assertEqual((result['status'], result['reason']), ('unsupported', 'tool-scope-not-granted'))

    def test_without_policy_acquisition_the_gap_is_unsupported(self):
        policy = InvestigationPolicy(effects=frozenset({'read_target', 'execute_tool'}),
                                     allow_acquire=False)
        result = self.grantable(policy).plan_external_tool(['binary_pattern_search'], Workbench())
        self.assertEqual((result['status'], result['reason']), ('unsupported', 'acquisition-not-allowed'))

    def test_registered_candidate_is_planned_with_pinned_provenance(self):
        result = self.grantable(self.allowing).plan_external_tool(['binary_pattern_search'], Workbench())
        self.assertEqual(result['status'], 'planned')
        self.assertTrue(result['requires_managed_acquisition'])
        candidate = result['candidates'][0]
        self.assertEqual(candidate['tool_id'], 'ripgrep')
        self.assertEqual(candidate['package_digest'], 'a' * 64)
        self.assertTrue(candidate['pinned_revision'])

    def test_unknown_capability_and_catalog_failure_stay_unsupported(self):
        current = self.grantable(self.allowing)
        result = current.plan_external_tool(['no_such_capability'], Workbench())
        self.assertEqual((result['status'], result['reason']), ('unsupported', 'no-registered-tool'))
        self.assertEqual(result['missing'], ['no_such_capability'])
        crashing = self.grantable(self.allowing)
        broken = crashing.plan_external_tool(['binary_pattern_search'], Workbench(raise_on_resolve=True))
        self.assertEqual(broken['status'], 'unsupported')  # a catalog error is not a crash

    def test_no_workbench_is_reported_not_assumed(self):
        result = self.grantable(self.allowing).plan_external_tool(['binary_pattern_search'], None)
        self.assertEqual((result['status'], result['reason']), ('unsupported', 'no-tool-workbench'))


class Workbench:
    """Minimal stand-in for the separately owned ToolWorkbench catalog."""

    def __init__(self, raise_on_resolve=False):
        self.raise_on_resolve = raise_on_resolve

    def resolve(self, requirements):
        if self.raise_on_resolve:
            raise RuntimeError('catalog unavailable')
        if requirements.get('capability_id') != 'binary_pattern_search':
            return {'status': 'unresolved', 'tool_manifest': None}
        return {'status': 'resolved', 'tool_manifest': {
            'tool_id': 'ripgrep', 'source_url': 'https://example.invalid/rg.zip',
            'pinned_revision': '14.1.1', 'package_digest': 'a' * 64}}


class BoundedLoopTests(unittest.TestCase):
    """E: a wrong approach stops with a typed outcome instead of retrying."""

    def setUp(self):
        self.task = task(max_rounds=3)
        self.task.bind_owner(FakeOwner())

    def test_repeated_identical_outcome_makes_no_progress_and_stalls(self):
        first = self.task.record_round(action='static_scan', observation={'hits': 0}, status='failed')
        self.assertTrue(first['made_progress'])
        second = self.task.record_round(action='static_scan', observation={'hits': 0}, status='failed')
        self.assertFalse(second['made_progress'])
        self.assertFalse(self.task.stalled())  # one duplicate is not yet a stall
        self.task.record_round(action='static_scan', observation={'hits': 0}, status='failed')
        self.assertTrue(self.task.stalled())

    def test_round_budget_is_enforced_rather_than_looping(self):
        for index in range(3):
            self.task.record_round(action='probe', observation={'n': index}, status='failed')
        self.assertTrue(self.task.rounds_exhausted())
        with self.assertRaises(InvestigationError):
            self.task.record_round(action='probe', observation={'n': 99}, status='failed')

    def test_blocked_outcome_records_the_failed_method(self):
        self.task.record_failed_method('string_scan', 'Yalnız string araması; semantik kanıt vermedi')
        self.task.record_failed_method('string_scan', 'Yalnız string araması; semantik kanıt vermedi')
        outcome = self.task.conclude('blocked', summary='Desteklenen kanıt üretilemedi')
        self.assertEqual(len(outcome['failed_methods']), 1)  # deduplicated
        self.assertEqual(outcome['status'], 'blocked')
        self.assertIsNone(outcome['verified_by'])

    def test_a_model_claim_is_not_a_completed_fix(self):
        with self.assertRaises(InvestigationError):
            self.task.conclude('completed', summary='Düzelttim')
        with self.assertRaises(InvestigationError):
            self.task.conclude('completed', summary='Düzelttim', verified_by='model_says_so')
        outcome = self.task.conclude('completed', summary='Yeniden çalıştırma geçti',
                                     verified_by='rerun', evidence_ids=['e1'])
        self.assertEqual(outcome['verified_by'], 'rerun')


class KnowledgeReuseTests(unittest.TestCase):
    """F: a later task reuses verified knowledge; change invalidates it."""

    def record(self, sha='b' * 64):
        procedure = {'claim_id': 'procedure.settings_fix', 'claim': 'Ayar kaydetme düzeltmesi',
                     'claim_type': 'verified_procedure', 'evidence_ids': ['e1', 'e2'],
                     'counter_evidence_ids': [], 'reproducible': True,
                     'confidence_basis': 'İki bağımsız host doğrulaması',
                     'limitations': ['Aynı sürüm için geçerlidir.'],
                     'procedure': {'steps': [
                         {'operation': 'read_scoped_file',
                          'locator': {'relative_file': 'settings.json'}},
                         {'operation': 'compare_digest', 'expected': True}],
                                   'success_check': {'operation': 'compare_digest',
                                                     'locator': {'relative_file': 'settings.json'},
                                                     'expected': 'e' * 64},
                                   'preconditions': {'target_sha256': sha,
                                                     'required_grants': ['read_target']}}}
        evidence = {name: {'evidence_id': name, 'level': 'LIVE', 'origin': 'host-verification',
                           'kind': 'host-verification', 'digest': 'c' * 64, 'bytes': 10,
                           'target_fingerprint': sha} for name in ('e1', 'e2')}
        return {'target_sha256': sha, 'findings': [procedure], 'evidence': evidence}

    def test_verified_procedure_is_reusable_under_the_current_grant(self):
        found = reusable_procedures(self.record(), target_sha256='b' * 64,
                                    current_grants=['read_target'])
        self.assertEqual([f['claim_id'] for f in found], ['procedure.settings_fix'])
        self.assertTrue(found[0]['requires_current_grant'])
        self.assertFalse(found[0]['instruction_authority'])

    def test_changed_target_or_missing_grant_invalidates_reuse(self):
        self.assertEqual(reusable_procedures(self.record(), target_sha256='d' * 64,
                                             current_grants=['read_target']), [])
        self.assertEqual(reusable_procedures(self.record(), target_sha256='b' * 64,
                                             current_grants=[]), [])


class StopAndShutdownTests(unittest.TestCase):
    """H: Stop fences the task; pending work is never reported as confirmed."""

    def test_stop_during_pending_permission_cancels_without_resuming(self):
        current = task()
        current.bind_owner(FakeOwner())
        pending = current.request_scope('read_target', 'gerekçe')['pending_permission']
        outcome = current.cancel('kullanıcı durdurdu')
        self.assertEqual(outcome['status'], 'cancelled')
        self.assertIsNone(current.summary()['pending_permission'])
        with self.assertRaises(InvestigationError):
            current.grant_scope(request_id=pending['request_id'],
                                generation=pending['generation'], effect='read_target')
        self.assertEqual(current.state, 'cancelled')

    def test_cancel_is_idempotent_and_keeps_the_first_outcome(self):
        current = task()
        current.bind_owner(FakeOwner())
        first = current.cancel('ilk')
        self.assertEqual(current.cancel('ikinci')['summary'], first['summary'])

    def test_services_shutdown_cancels_open_chat_tasks_and_fences_new_ones(self):
        services = ApplicationServices()
        current = task()
        current.bind_owner(FakeOwner())
        services.register_chat_task(current)
        self.assertEqual(services.chat_task('chat.t1'), current)
        self.assertEqual(len(services.open_chat_tasks()), 1)
        services.shutdown()
        self.assertEqual(current.state, 'cancelled')
        self.assertEqual(services.open_chat_tasks(), [])
        with self.assertRaises(ServicesClosed):
            services.register_chat_task(task(max_rounds=2))

    def test_registry_is_bounded_and_drops_finished_records(self):
        services = ApplicationServices()
        for index in range(ApplicationServices.MAX_CHAT_TASKS):
            done = ChatInvestigationTask(classify_investigation_request(TASK_TEXT),
                                         task_id='chat.done%d' % index, conversation_id='c1')
            done.bind_owner(FakeOwner())
            done.conclude('blocked', summary='bitti')
            services.register_chat_task(done)
        services.register_chat_task(task())  # finished records are reclaimed
        self.assertEqual([t.task_id for t in services.open_chat_tasks()], ['chat.t1'])


class HostWorkbenchWiringTests(unittest.TestCase):
    """D (host): the diagnostics owner actually routes to the injected workbench."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'application.zip'
        with zipfile.ZipFile(self.target, 'w') as archive:
            archive.writestr('package.json', json.dumps({'name': 'fixture'}))

    def service(self, **kwargs):
        return ArtifactDiagnosticsService(self.target, reports=self.root / 'reports',
            investigation_root=self.root / 'investigations', knowledge=False, **kwargs)

    def test_default_host_keeps_the_builtin_only_gateway(self):
        service = self.service()
        self.addCleanup(service.shutdown)
        self.assertIsNone(service.workbench)
        self.assertEqual(service.tool_specs, {})
        self.assertEqual(service.tool_effects, frozenset())

    def test_tool_effects_require_a_workbench(self):
        with self.assertRaises(ValueError):
            self.service(tool_effects=('execute_tool',))
        with self.assertRaises(ValueError):
            self.service(workbench=object(), tool_effects=('attach_runtime',))

    def test_injected_workbench_is_stopped_with_the_investigation(self):
        calls = []

        class Recording:
            def execute(self, request, cancel_event=None):
                calls.append(('execute', request.get('request_id')))
                raise AssertionError('builtin analysis must not call the workbench')

            def stop(self, investigation_id=None):
                calls.append(('stop', investigation_id))
                return {'status': 'confirmed'}

        service = self.service(workbench=Recording(),
                               tool_specs={'ripgrep': {
                                   'package_digest': 'a' * 64, 'operations': ['search'],
                                   'effects': ['execute_tool'],
                                   'source_url': 'https://example.invalid/rg.zip',
                                   'pinned_revision': '14.1.1'}},
                               tool_effects=('execute_tool',))
        self.addCleanup(service.shutdown)
        job = service.start(include_rea=False)
        service.threads[job['id']].join(10)
        self.assertEqual(service.status(job['id'])['state'], 'completed')
        # The builtin parser never spends the external tool; closing the
        # investigation still asks the workbench to stop its own work.
        self.assertEqual([name for name, _ in calls], ['stop'])
        self.assertEqual(service.shutdown()['status'], 'confirmed')


class ChatBridgeRoutingTests(unittest.TestCase):
    """A/B at the bridge: routing, real binding and the permission answer."""

    def setUp(self):
        import gui
        self.gui = gui
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'application.zip'
        with zipfile.ZipFile(self.target, 'w') as archive:
            archive.writestr('settings.json', '{}')

    def api(self):
        return self.gui.Api()

    def test_ordinary_chat_opens_no_picker_and_no_investigation(self):
        from unittest.mock import patch
        api = self.api()
        for text in ('Merhaba dostum', 'Quartz hakkında ne düşünüyorsun?',
                     'Sadece sohbet edelim; uygulamadaki hatayı incele'):
            with self.subTest(text=text), \
                 patch.object(api, 'diagnostics_select_application',
                              side_effect=AssertionError('picker opened for ordinary chat')), \
                 patch.object(api, 'natural_start', return_value={'status': 'ok', 'data': {}}), \
                 patch('gui.ipc_send', return_value={'status': 'ok', 'data': {}}):
                api.coordination_route(text, 'c', 'p', {}, 'project')
        self.assertEqual(api._services.open_chat_tasks(), [])

    def test_application_task_routes_to_the_investigation_owner(self):
        from unittest.mock import patch
        api = self.api()
        with patch.object(api, 'diagnostics_select_application',
                          return_value={'status': 'ok', 'data': {'id': 'job1'},
                                        'chat_task': {'task_id': 'chat.job1'}}) as picker, \
             patch.object(api, 'natural_start',
                          side_effect=AssertionError('desktop operator started instead')):
            result = api.coordination_route(TASK_TEXT, 'conv1', 'p', {}, 'project')
        self.assertTrue(result['data']['diagnostics_started'])
        self.assertEqual(result['data']['investigation_task']['task_id'], 'chat.job1')
        self.assertEqual(picker.call_args.kwargs['question'], TASK_TEXT)
        self.assertEqual(picker.call_args.kwargs['conversation_id'], 'conv1')
        self.assertTrue(picker.call_args.kwargs['chat_request']['fix_requested'])

    def test_real_picker_selection_binds_and_registers_one_task(self):
        from unittest.mock import Mock, patch
        api = self.api()
        window = Mock()
        window.create_file_dialog.return_value = [str(self.target)]
        with patch.object(self.gui.webview, 'windows', [window]), \
             patch.object(api, 'natural_start',
                          side_effect=AssertionError('desktop operator started instead')):
            result = api.coordination_route(TASK_TEXT, 'conv1', 'p', {}, 'project')
            service = api._artifact_diagnostics
            self.addCleanup(service.shutdown)
            for thread in service.threads.values():
                thread.join(10)
        summary = result['data']['investigation_task']
        self.assertEqual(summary['conversation_id'], 'conv1')
        self.assertEqual(summary['state'], 'running')
        self.assertEqual(summary['question'], TASK_TEXT)
        self.assertEqual(summary['granted_effects'], [])  # binding is not a grant
        tasks = api._services.open_chat_tasks()
        self.assertEqual([t.task_id for t in tasks], [summary['task_id']])

    def test_cancelled_selection_opens_no_task(self):
        from unittest.mock import Mock, patch
        api = self.api()
        window = Mock()
        window.create_file_dialog.return_value = None
        with patch.object(self.gui.webview, 'windows', [window]), \
             patch.object(api, 'natural_start',
                          side_effect=AssertionError('desktop operator started instead')):
            result = api.coordination_route(TASK_TEXT, 'conv1', 'p', {}, 'project')
        self.assertTrue(result['data']['investigation_target_required'])
        self.assertEqual(api._services.open_chat_tasks(), [])

    def test_permission_answer_resumes_and_a_replay_is_refused(self):
        api = self.api()
        current = task()
        current.bind_owner(FakeOwner())
        api._services.register_chat_task(current)
        pending = current.request_scope('read_target', 'gerekçe')['pending_permission']
        granted = api.investigation_grant_scope('chat.t1', pending['request_id'],
                                                pending['generation'], 'read_target', True)
        self.assertEqual(granted['status'], 'ok')
        self.assertTrue(granted['data']['resumed_same_task'])
        replay = api.investigation_grant_scope('chat.t1', pending['request_id'],
                                               pending['generation'], 'read_target', True)
        self.assertEqual(replay['status'], 'error')
        self.assertEqual(len(api._services.open_chat_tasks()), 1)
        unknown = api.investigation_grant_scope('chat.missing', 'x', 1, 'read_target', True)
        self.assertEqual(unknown['status'], 'error')

    def test_status_is_read_only(self):
        api = self.api()
        current = task()
        current.bind_owner(FakeOwner())
        api._services.register_chat_task(current)
        state = api.investigation_task_status('chat.t1')
        self.assertEqual(state['data']['state'], 'running')
        self.assertFalse(state['data']['instruction_authority'])
        self.assertEqual(api.investigation_task_status('nope')['status'], 'error')


if __name__ == '__main__':
    unittest.main()
