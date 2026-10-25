import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from core.writer_journal import WriterJournal, identity_state
from core.agent_chat import AgentChatService


def identity(pid):
    return {'state':'observed','pid':pid,'created':10.0,'exe':'fixture.exe'}


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.path=self.root/'state/writers.json'
        self.journal=WriterJournal(self.path,probe=identity)
        self.journal.owner=identity(9876)

    def restarted(self, live=False):
        def probe(pid):
            return identity(pid) if live and pid==1234 else {'state':'gone'}
        return WriterJournal(self.path,probe=probe)

    def claim(self):
        key=self.journal.reserve(str(self.root/'project'),False,'codex')
        self.journal.update(key,stage='active',run_id='r',pid=1234)
        return key

    def test_restart_blocks_overlapping_and_nested_projects_but_not_unrelated(self):
        self.claim(); after=self.restarted()
        for project, exclusive in ((self.root/'project',False),(self.root/'project/child',False),(self.root,False),(self.root/'other',True)):
            with self.subTest(project=project), self.assertRaises(RuntimeError):
                after.reserve(str(project),exclusive,'codex')
        self.assertIsNotNone(after.reserve(str(self.root/'other'),False,'codex'))

    def test_process_identity_uses_creation_time_and_executable_not_just_pid(self):
        old=identity(1234)
        self.assertEqual(identity_state(old,lambda _: {**old,'created':11.0}),'replaced')
        self.assertEqual(identity_state(old,lambda _: {**old,'exe':'other.exe'}),'replaced')
        self.assertEqual(identity_state(old,identity),'live')

    def test_live_runtime_is_never_released_even_after_confirmation(self):
        key=self.claim(); after=self.restarted(live=True)
        with self.assertRaises(RuntimeError): after.acknowledge(key,confirmed=True,external_review=True)
        self.assertEqual(after.inspect(key)['process_state'],'live')
        self.assertIn(key,after.claims)

    def test_absent_root_requires_explicit_external_review_and_archives_claim(self):
        key=self.claim(); after=self.restarted()
        for kwargs in ({},{'confirmed':True},{'confirmed':'true','external_review':True}):
            with self.assertRaises(PermissionError): after.acknowledge(key,**kwargs)
        result=after.acknowledge(key,confirmed=True,external_review=True)
        self.assertFalse(result['permissions_restored']); self.assertFalse(result['automatic_replay'])
        self.assertEqual(json.loads(Path(result['archive']).read_text(encoding='utf-8'))['claim']['id'],key)
        self.assertNotIn(key,WriterJournal(self.path).claims)

    def test_unknown_process_readback_is_not_treated_as_gone(self):
        key=self.claim(); after=WriterJournal(self.path,probe=lambda _: {'state':'unknown'})
        with self.assertRaises(RuntimeError): after.acknowledge(key,confirmed=True,external_review=True)

    def test_pending_start_without_pid_is_not_silently_dropped(self):
        key=self.journal.reserve(str(self.root/'project'),False,'codex')
        self.journal.update(key,stage='starting')
        after=self.restarted()
        self.assertEqual(after.inspect(key)['process_state'],'unknown')
        self.assertTrue(after.recovery_status()['blocked'])

    def test_corrupt_journal_preserved_and_blocks_new_writers(self):
        self.path.parent.mkdir(parents=True); self.path.write_text('{ broken',encoding='utf-8')
        after=self.restarted(); original=self.path.read_bytes()
        self.assertTrue(after.recovery_status()['error'])
        with self.assertRaises(OSError): after.reserve(str(self.root/'p'),False,'codex')
        self.assertEqual(self.path.read_bytes(),original)

    def test_journal_commit_failure_does_not_publish_reservation(self):
        with patch('core.writer_journal.atomic_write_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.journal.reserve(str(self.root/'p'),False,'codex')
        self.assertEqual(self.journal.claims,{})

    def test_os_lock_prevents_second_facade_reserving_against_stale_inventory(self):
        other=self.restarted()
        with self.journal._transaction():
            with self.assertRaises(OSError): other.reserve(str(self.root/'p'),False,'codex')

    def test_authority_refresh_observes_external_claim_without_rewriting_file(self):
        other=self.restarted()
        self.assertFalse(other.recovery_status()['blocked'])
        key=self.claim(); before=self.path.read_bytes()
        other.refresh()
        self.assertEqual(other.recovery_status()['claims'][0]['id'],key)
        self.assertEqual(self.path.read_bytes(),before)

    def test_finish_cannot_remove_another_sessions_claim(self):
        key=self.claim(); after=self.restarted()
        with self.assertRaises(PermissionError): after.finish(key)
        self.journal.finish(key)
        self.assertFalse(self.restarted().recovery_status()['blocked'])

    def test_terminal_label_does_not_release_a_still_live_process(self):
        key=self.claim()
        with self.assertRaises(RuntimeError): self.journal.finish(key,verify_process=True)
        self.assertIn(key,self.journal.claims)


class IntegrationTests(unittest.TestCase):
    def test_broker_admission_guard_cannot_grant_authority_when_backend_is_blocked(self):
        from core.desktop_broker import DesktopBroker
        broker=DesktopBroker(Mock())
        broker.admission_guard=Mock(side_effect=PermissionError('unresolved writer'))
        with self.assertRaises(PermissionError): broker.grant(42,'codex',confirmed=True)
        self.assertFalse(broker.status()['active'])
        broker.backend.identity.assert_not_called()

    def test_failed_start_keeps_durable_uncertainty_and_blocks_replay(self):
        from core.multi_agent_service import MultiAgentService
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); project=root/'project'; project.mkdir()
            with patch('core.multi_agent_service.CodexRuntime'),patch('core.multi_agent_service.AntigravityRuntime'):
                service=MultiAgentService(projects=[{'id':'p','path':str(project)}],journal_store=root/'writers.json')
            starter=Mock(side_effect=RuntimeError('start result unknown'))
            checkpoint={'status':'snapshot','complete':True,'archive':'fixture.zip'}
            with patch('core.multi_agent_service.create_checkpoint',return_value=checkpoint):
                with self.assertRaises(RuntimeError): service._start_writer('codex',{'path':str(project)},starter)
            self.assertTrue(service._writer_status(str(project))['recovery_required'])
            self.assertEqual(service.writer_recovery_status()['claims'][0]['stage'],'starting')
            with self.assertRaises(RuntimeError): service._start_writer('codex',{'path':str(project)},starter)
            self.assertEqual(starter.call_count,1)

    def test_checkpoint_failure_clears_only_never_started_claim(self):
        from core.multi_agent_service import MultiAgentService
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); project=root/'project'; project.mkdir()
            with patch('core.multi_agent_service.CodexRuntime'),patch('core.multi_agent_service.AntigravityRuntime'):
                service=MultiAgentService(projects=[{'id':'p','path':str(project)}],journal_store=root/'writers.json')
            starter=Mock()
            with patch('core.multi_agent_service.create_checkpoint',return_value={'status':'error','warning':'failure'}):
                with self.assertRaises(RuntimeError): service._start_writer('codex',{'path':str(project)},starter)
            self.assertFalse(service._writer_status(str(project))['locked']); starter.assert_not_called()

    def test_observation_failure_keeps_unresolved_claim(self):
        from core.multi_agent_service import MultiAgentService
        with tempfile.TemporaryDirectory() as folder:
            with patch('core.multi_agent_service.CodexRuntime'),patch('core.multi_agent_service.AntigravityRuntime'):
                service=MultiAgentService(projects=[{'id':'p','path':folder}],journal_store=Path(folder)/'writers.json')
            key=os.path.normcase(str(Path(folder).resolve())); claim=service._writer_journal.reserve(key,False,'codex')
            service._writers[key]={'owner':'r','journal_claim':claim}
            runtime=Mock(); runtime.get.side_effect=KeyError('unknown run')
            service._watch_writer(key,'r',runtime,folder,{},claim)
            self.assertTrue(service._writer_status(folder)['recovery_required'])


class ResumeAndProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.service=Mock(); self.chat=AgentChatService(self.service,Path(self.tmp.name)/'chat.json')
        self.addCleanup(self.chat.close)

    def test_resume_prepares_draft_without_dispatch_or_old_authority(self):
        cid=self.chat.store.get_active()['id']
        self.chat.store.append_message(cid,'user','Review the fixture')
        msg=self.chat.store.append_message(cid,'assistant','partial',sender='codex',metadata={'status':'interrupted','permission_level':'full'})
        before=self.chat.store.path.read_bytes()
        result=self.chat.prepare_resume(cid,msg['id'])
        self.assertEqual(result['draft'],'Review the fixture')
        self.assertEqual(result['permission_level'],'read-only')
        self.assertFalse(result['automatic_replay']); self.assertFalse(result['permissions_restored'])
        self.assertEqual(self.chat.store.path.read_bytes(),before)
        self.service.dispatch_codex.assert_not_called()

    def test_resume_refuses_active_or_noninterrupted_message(self):
        cid=self.chat.store.get_active()['id']; msg=self.chat.store.append_message(cid,'assistant','done',metadata={'status':'completed'})
        with self.assertRaises(ValueError): self.chat.prepare_resume(cid,msg['id'])
        self.chat._active_turn={'status':'cancelling'}
        with self.assertRaises(RuntimeError): self.chat.prepare_resume(cid,msg['id'])
        self.chat._active_turn=None

    def test_agent_progress_is_independent_and_late_old_bubble_does_not_steal_it(self):
        cid=self.chat.store.get_active()['id']
        self.chat._active_turn={'status':'running','message_ids':['owner'],'conversation_id':cid,'message_id':'owner'}
        for agent,mid in [('codex','c'),('antigravity','a')]:
            self.chat._set_turn_progress(agent,current_msg_id=mid,owner_msg_id='owner',agent=agent)
        self.chat._set_turn_progress('new codex',current_msg_id='c2',owner_msg_id='owner',agent='codex')
        self.chat._publish_run_update(cid,'c','late',{'agent':'codex','status':'completed'})
        progress=self.chat._active_turn['agent_progress']
        self.assertEqual(progress['codex']['message_id'],'c2')
        self.assertEqual(progress['antigravity']['message_id'],'a')
        self.chat._active_turn=None

    def test_stale_turn_cannot_register_progress_and_terminal_state_is_monotonic(self):
        self.chat._active_turn={'status':'running','message_ids':['owner']}
        self.assertFalse(self.chat._set_turn_progress('old',current_msg_id='old',agent='codex'))
        self.chat._set_turn_progress('work',current_msg_id='owner',agent='codex')
        self.chat._finish_turn('owner','completed')
        self.assertFalse(self.chat._set_turn_progress('late',current_msg_id='owner',agent='codex'))
        self.assertEqual(self.chat._active_turn['agent_progress']['codex']['status'],'completed')
        self.chat._active_turn=None


if __name__ == '__main__': unittest.main()
