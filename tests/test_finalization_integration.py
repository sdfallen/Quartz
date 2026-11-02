"""Cross-delivery lifecycle races. Only disposable objects and local sockets."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.shutdown import ShutdownCoordinator
from core.application_services import ApplicationServices, ServiceFactories
from main import IPCServer


class FinalLifecycleTests(unittest.TestCase):
    def test_returned_pending_receipt_retains_chat_until_retry_confirms(self):
        server = IPCServer(coordinator=ShutdownCoordinator())
        chat = Mock()
        chat.close.side_effect = [{'status':'pending'}, {'status':'confirmed'}]
        server._agent_chat = chat
        with patch('main._mobile_gateway', None):
            self.assertEqual(server.stop()['status'], 'pending')
            self.assertIs(server._agent_chat, chat)
            self.assertEqual(server.stop()['status'], 'confirmed')
            self.assertIsNone(server._agent_chat)

    def test_concurrent_shutdown_has_one_worker_and_late_result_refreshes(self):
        entered, release = threading.Event(), threading.Event()
        coordinator = ShutdownCoordinator()
        def cleanup():
            entered.set()
            release.wait(3)
            return {'status':'confirmed'}
        cleanup = Mock(side_effect=cleanup)
        worker = threading.Thread(target=lambda: coordinator.execute_shutdown({'owner':cleanup}, .3))
        worker.start()
        self.assertTrue(entered.wait(1))
        try:
            self.assertEqual(coordinator.execute_shutdown({'owner':cleanup}, .01)['status'], 'pending')
            self.assertEqual(cleanup.call_count, 1)
        finally:
            release.set()
            worker.join(2)
        self.assertEqual(coordinator.get_receipt()['status'], 'confirmed')

    def test_timeout_preserves_owner_and_result_cannot_cross_component(self):
        release = threading.Event()
        coordinator = ShutdownCoordinator()
        slow = Mock(side_effect=lambda: (release.wait(2), {'status':'failed'})[1])
        fast = Mock(return_value={'status':'confirmed'})
        try:
            receipt = coordinator.execute_shutdown({'slow':slow, 'fast':fast}, .01)
            self.assertEqual(receipt['status'], 'pending')
            self.assertEqual(receipt['components']['fast']['status'], 'confirmed')
            owned = coordinator._operations['slow']['thread']
            self.assertFalse(owned.daemon)
        finally:
            release.set()
            owned.join(2)
        receipt = coordinator.get_receipt()
        self.assertEqual(receipt['components']['slow']['status'], 'failed')
        self.assertEqual(receipt['components']['fast']['status'], 'confirmed')
        self.assertEqual(slow.call_count, 1)
        self.assertEqual(fast.call_count, 1)

    def test_failed_owner_can_retry_without_repeating_confirmed_owner(self):
        coordinator = ShutdownCoordinator()
        failed = Mock(side_effect=[OSError('private path and token'), True])
        good = Mock(return_value=True)
        first = coordinator.execute_shutdown({'a':failed, 'b':good})
        self.assertEqual(first['status'], 'failed')
        self.assertNotIn('private path', str(first))
        self.assertEqual(coordinator.execute_shutdown({'a':failed, 'b':good})['status'], 'confirmed')
        self.assertEqual(good.call_count, 1)

    def test_constructor_started_before_fence_is_retained_and_closed(self):
        entered, release = threading.Event(), threading.Event()
        server = IPCServer(coordinator=ShutdownCoordinator())
        instance = Mock()
        instance.shutdown.return_value = None
        def construct():
            entered.set()
            release.wait(2)
            return instance
        observed = []
        with patch('main.GitHubAssistant', side_effect=construct), patch('main._mobile_gateway', None):
            creator = threading.Thread(target=lambda: observed.append(server._assistant))
            creator.start()
            self.assertTrue(entered.wait(1))
            try:
                self.assertEqual(server.stop()['status'], 'pending')
            finally:
                release.set()
                creator.join(2)
            self.assertEqual(observed, [None])
            self.assertEqual(server.stop()['status'], 'confirmed')
            instance.shutdown.assert_called_once()

    def test_inflight_dispatch_cannot_escape_service_cleanup(self):
        server = IPCServer(coordinator=ShutdownCoordinator())
        entered, release = threading.Event(), threading.Event()
        center = Mock()
        center.shutdown.return_value = None
        server._agent_center = center
        def dispatch(_):
            entered.set()
            release.wait(2)
            return {'status':'ok'}
        original = server._dispatch_action
        server._dispatch_action = dispatch
        with patch('main.authorized', return_value=True), patch('main._mobile_gateway', None):
            worker = threading.Thread(target=lambda: server._dispatch({'action':'fixture'}))
            worker.start()
            self.assertTrue(entered.wait(1))
            try:
                self.assertEqual(server.stop()['status'], 'pending')
                center.shutdown.assert_not_called()
            finally:
                release.set()
                worker.join(2)
            server._dispatch_action = original
            self.assertEqual(server.stop()['status'], 'confirmed')
            center.shutdown.assert_called_once()

    def test_gui_reads_actual_backend_receipt_envelope(self):
        from gui import Api
        with patch('gui.ipc_send', return_value={'status':'ok', 'data':'Shutting down', 'receipt':{'status':'confirmed'}}):
            self.assertEqual(Api._request_backend_shutdown(), ('confirmed', []))

    def test_synchronous_shutdown_return_does_not_hide_a_live_observer(self):
        server = IPCServer(coordinator=ShutdownCoordinator())
        observer = Mock()
        observer.is_alive.return_value = True
        diagnostics = Mock()
        diagnostics.threads = {'owned':observer}
        diagnostics.shutdown.return_value = None
        server._diagnostics = diagnostics
        with patch('main._mobile_gateway', None):
            self.assertEqual(server.stop()['status'], 'pending')
            self.assertIs(server._diagnostics, diagnostics)
            observer.is_alive.return_value = False
            self.assertEqual(server.stop()['status'], 'confirmed')

    def test_entry_waits_for_pending_owners_and_actual_backend_join(self):
        import quartz_entry
        thread = Mock()
        thread.is_alive.side_effect = [True, False]
        app = SimpleNamespace(_api=SimpleNamespace(_services=Mock()))
        app._api._services.shutdown.return_value = {'status':'confirmed'}
        with patch('main.stop_backend', side_effect=[{'status':'pending'}, {'status':'confirmed'}]), \
                patch('quartz_entry.log'), patch('quartz_entry.time.sleep'):
            result = quartz_entry.finish_backend(thread, app)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(thread.join.call_count, 2)

    def test_gui_cleanup_exception_cannot_skip_backend_shutdown(self):
        import quartz_entry
        thread = Mock()
        thread.is_alive.return_value = False
        app = SimpleNamespace(_api=SimpleNamespace(_services=Mock()))
        app._api._services.shutdown.side_effect = [OSError('private path'), {'status':'confirmed'}]
        with patch('main.stop_backend', return_value={'status':'confirmed'}) as backend, \
                patch('quartz_entry.log'), patch('quartz_entry.time.sleep'):
            result = quartz_entry.finish_backend(thread, app)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(backend.call_count, 2)

    def test_gui_startup_activity_fences_shutdown_without_losing_owner(self):
        owner = ApplicationServices()
        desktop = SimpleNamespace(broker=Mock(), close=Mock(), status=lambda:{'session':{'active':False}})
        owner.adopt('desktop', desktop)
        with owner.activity():
            result = owner.shutdown()
            self.assertEqual(result['status'], 'pending')
            desktop.broker.stop.assert_called_once()
            with self.assertRaises(RuntimeError):
                with owner.activity(): pass
        self.assertEqual(owner.shutdown()['status'], 'confirmed')

    def test_replacing_task_cannot_drop_its_unconfirmed_process(self):
        factory = Mock()
        owner = ApplicationServices(ServiceFactories(natural=factory))
        runtime = Mock()
        runtime.get.return_value = {'process_exit_confirmed':False}
        old = SimpleNamespace(status=lambda:{'active':False,'job':{'cleanup':{'status':'completed'}}},
                              runs={'codex':(runtime, 'actual-id')})
        owner.adopt('natural', old)
        with self.assertRaises(RuntimeError): owner.start_natural(None, None)
        self.assertIs(owner.peek('natural'), old)
        factory.assert_not_called()


class StopLegacyBoundaryTests(unittest.TestCase):
    def test_chat_cancel_compatibility_does_not_construct_unused_legacy_assistant(self):
        server = IPCServer(coordinator=ShutdownCoordinator())
        with patch('main.GitHubAssistant') as factory:
            result = server._dispatch_action({'action': 'cancel_request'})
        self.assertEqual(result['status'], 'ok')
        factory.assert_not_called()
        self.assertIsNone(server._assistant_instance)

    def test_legacy_request_still_cancelled_when_owner_already_exists(self):
        assistant = Mock()
        server = IPCServer(assistant=assistant, coordinator=ShutdownCoordinator())
        with patch('main.GitHubAssistant') as factory:
            result = server._dispatch_action({'action': 'cancel_request'})
        self.assertEqual(result['status'], 'ok')
        assistant.cancel_current.assert_called_once_with()
        factory.assert_not_called()
