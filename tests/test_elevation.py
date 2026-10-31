import unittest
from unittest.mock import Mock,patch
from core.elevation import launch_normal,ElevationRequired,request_uac,require_input_integrity
from tests import test_natural_desktop as fixtures


def windows_error(number):
    error=OSError('fixture Windows error');error.winerror=number;return error


class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.NaturalTaskTests('test_metadata_and_model_request_never_grant_input')
        self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.task=self.fixture.task
        self.file=self.fixture.root/'app.exe';self.file.write_bytes(b'MZ fixture')
        self.adv=Mock();self.task._controllers=lambda:(Mock(),self.adv)
        self.task._learn_approved_applications=Mock()

    def queue(self):
        self.adv.smart_open.side_effect=ElevationRequired(self.file)
        return self.task.call('op',{'name':'jarvis_open_app','arguments':{'target':'Example'}})

    def test_740_becomes_pending_and_does_not_loop_or_auto_elevate_full(self):
        self.task.job['requested_permission_level']='full'
        with patch('core.elevation.os.startfile') as shell:
            first=self.queue();self.assertEqual(first['kind'],'elevation')
            again=self.queue();self.assertEqual(again['status'],'blocked_elevation')
            self.assertEqual(self.adv.smart_open.call_count,1);shell.assert_not_called()
        self.assertEqual(self.task.job['verification']['status'],'NOT VERIFIED')

    def test_failed_new_control_cannot_reuse_previous_success(self):
        self.task.job['verification']={'status':'OBSERVED UI CRITERION VERIFIED'}
        self.task.latest={'snapshot_id':'old','image_sha256':'old'}
        self.adv.smart_open.side_effect=PermissionError('UIPI blocked fixture')
        with self.assertRaises(PermissionError):
            self.task.call('op',{'name':'jarvis_open_app','arguments':{'target':'Example'}})
        self.assertIsNone(self.task.latest)
        self.assertEqual(self.task.job['verification']['status'],'NOT VERIFIED')

    def test_collaborator_cannot_invalidate_operator_verification(self):
        self.task.job['verification']={'status':'OBSERVED UI CRITERION VERIFIED'}
        self.task.latest={'snapshot_id':'operator-snapshot'}
        with self.assertRaises(PermissionError):
            self.task.call('review',{'name':'jarvis_open_app','arguments':{'target':'Example'}})
        self.assertEqual(self.task.latest['snapshot_id'],'operator-snapshot')

    def test_explicit_confirmation_and_double_click_only_start_one_worker(self):
        self.queue();identity=self.task.pending['id']
        with self.assertRaises(PermissionError):self.task.approve(identity)
        with patch('core.natural_desktop.threading.Thread') as worker:
            self.task.approve(identity,confirmed=True)
            self.task.approve(identity,confirmed=True)
            worker.assert_called_once()
        self.task._inflight_calls=0

    def test_uac_cancellation_is_not_success_and_not_retried(self):
        self.queue();pending=dict(self.task.pending);self.task._inflight_calls=1
        with patch('core.elevation.request_uac',return_value={'state':'cancelled','verified':False,'winerror':1223}):
            self.task._elevation_worker(self.task.job,pending)
        self.assertIsNone(self.task.pending)
        self.assertFalse(self.task.job['elevation_outcomes'][0]['verified'])
        self.assertEqual(self.queue()['status'],'blocked_elevation')

    def test_changed_executable_rejected_before_uac(self):
        self.queue();identity=self.task.pending['id'];self.file.write_bytes(b'MZ changed')
        with patch('core.elevation.os.startfile') as shell,self.assertRaises(PermissionError):
            self.task.approve(identity,confirmed=True)
        shell.assert_not_called()

    def test_stop_during_prompt_never_restarts_or_adopts(self):
        self.queue();pending=dict(self.task.pending);job=self.task.job
        self.task._inflight_calls=1
        def during_prompt(*args,**kwargs):
            self.task.stop();return {'state':'launch_requested','verified':False}
        with patch('core.elevation.request_uac',side_effect=during_prompt), \
                patch.object(self.task,'_launch_provider') as restart:
            self.task._elevation_worker(job,pending)
        restart.assert_not_called();self.assertIsNone(self.task.connection)

    def test_stop_before_worker_prevents_windows_request(self):
        self.queue();pending=dict(self.task.pending);self.task._inflight_calls=1;self.task.stop()
        with patch('core.elevation.request_uac') as shell:
            self.task._elevation_worker(self.task.job,pending)
        shell.assert_not_called()
        self.assertEqual(self.task._inflight_calls,0)

    def test_cancel_during_file_validation_prevents_uac(self):
        approval=ElevationRequired(self.file).approval
        with patch('core.desktop_launch.validate_launch'),patch('core.elevation.os.startfile') as shell:
            self.assertEqual(request_uac(approval,cancelled=lambda:True)['state'],'cancelled_before_launch')
        shell.assert_not_called()

    def test_normal_launch_classifies_only_740_and_uac_rejects_1223(self):
        with patch('core.elevation.subprocess.Popen',side_effect=windows_error(740)),self.assertRaises(ElevationRequired):
            launch_normal(self.file)
        with patch('core.elevation.subprocess.Popen',side_effect=windows_error(5)),self.assertRaises(OSError) as ctx:
            launch_normal(self.file)
        self.assertNotIsInstance(ctx.exception,ElevationRequired)
        approval=ElevationRequired(self.file).approval
        with patch('core.elevation.os.startfile',side_effect=windows_error(1223)):
            self.assertEqual(request_uac(approval)['state'],'cancelled')

    def test_uac_launch_uses_only_exact_file_and_own_working_directory(self):
        approval=ElevationRequired(self.file).approval
        with patch('core.elevation.os.startfile') as shell:
            result=request_uac(approval)
        self.assertFalse(result['verified'])
        self.assertEqual(result['state'],'launch_requested')
        resolved = self.file.resolve()
        shell.assert_called_once_with(str(resolved),'runas',cwd=str(resolved.parent))

    def test_uipi_blocks_higher_or_unknown_target_without_input(self):
        for levels in ([0x2000,0x3000],[0x2000,None]):
            with patch('core.elevation.token_integrity',side_effect=levels),self.assertRaises(PermissionError):
                require_input_integrity({'pid':123})
        with patch('core.elevation.token_integrity',side_effect=[0x2000,0x2000]):
            require_input_integrity({'pid':123})
