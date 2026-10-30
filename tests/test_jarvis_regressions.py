"""Real adapter signatures, target correctness and stop fences; no native input."""
import ast
import copy
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import gui
from core.desktop_native import NativeDesktopBackend
from core.message_intent import message_intent
from core.desktop_task_ui import desktop_intent
from tests.reliability_antigravity import test_task_lifecycle_reliability as lifecycle


def controller_functions(mouse, clipboard):
    """Compile actual function bodies without importing OS/controller modules."""
    tree=ast.parse((Path(__file__).resolve().parents[1]/'advanced_controller.py').read_text(encoding='utf-8'))
    selected=[copy.deepcopy(n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'type_and_enter','hotkey'}]
    namespace={'pyautogui':mouse,'pyperclip':clipboard,'PYAUTOGUI_OK':True,'time':SimpleNamespace(sleep=lambda _:None)}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'<actual-controller-functions>','exec'),namespace)
    return SimpleNamespace(type_and_enter=namespace['type_and_enter'],hotkey=namespace['hotkey'])


class JarvisRegressionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=lifecycle.NaturalTaskLifecycleReliabilityTests('test_stop_idempotency')
        self.fixture.setUp();self.fixture._setup_active_approved_task()
        self.addCleanup(self.fixture.tearDown)
        self.task=self.fixture.task;self.backend=self.fixture.backend
        self.backend._before_input=lambda target:NativeDesktopBackend._before_input(self.backend,target)
        self.backend.foreground_identity=lambda:{'handle':1}
        self.mouse=Mock();self.mouse.position.return_value=(20,20)
        self.clipboard=Mock();self.adv=controller_functions(self.mouse,self.clipboard)
        self.task._controllers=lambda:(Mock(),self.adv)
        self.module=patch.dict(sys.modules,{'pyautogui':self.mouse});self.module.start();self.addCleanup(self.module.stop)

    def call(self,action,**args):
        return self.task.call('token-op',{'name':'jarvis_input','arguments':{'action':action,**args}})

    def test_missing_or_ambiguous_target_never_clicks_or_focuses(self):
        with self.assertRaises(ValueError):self.call('click',target_window='ABSENT',x=5,y=5)
        self.mouse.click.assert_not_called()
        with patch.object(self.task.desktop,'windows',return_value=[dict(self.backend.target),{**self.backend.target,'handle':2}]):
            with self.assertRaises(ValueError):self.call('click',target_window='Test',x=5,y=5)
        self.mouse.click.assert_not_called()

    def test_click_must_stay_inside_current_target(self):
        with self.assertRaises(ValueError):self.call('click',target_window=1,x=900,y=5)
        self.mouse.click.assert_not_called()
        self.call('click',target_window=1,x=5,y=5)
        self.mouse.click.assert_called_once_with(5,5)
        self.assertEqual(self.task.job['verification']['status'],'NOT VERIFIED')

    def test_real_typing_adapter_preserves_unicode_and_optional_enter(self):
        self.call('type_text',target_window=1,text='Şimdi Türkçe',press_enter=False)
        self.clipboard.copy.assert_called_once_with('Şimdi Türkçe')
        self.mouse.hotkey.assert_called_once_with('ctrl','v');self.mouse.press.assert_not_called()
        self.call('type_text',target_window=1,text='Gönder',press_enter=True)
        self.mouse.press.assert_called_once_with('enter')

    def test_real_hotkey_signature_and_cancellation_guard(self):
        self.call('hotkey',target_window=1,keys='ctrl+c')
        self.mouse.hotkey.assert_called_once_with('ctrl','c')
        self.mouse.hotkey.reset_mock()
        def revoked():raise PermissionError('revoked before input')
        with self.assertRaises(PermissionError):self.adv.hotkey('ctrl+v',input_guard=revoked)
        self.mouse.hotkey.assert_not_called()

    def test_unimplemented_profiles_do_not_call_power_plan_controller(self):
        power=Mock();self.adv.quartz_mode=power
        with self.assertRaisesRegex(ValueError,'uygulanmış değil'):
            self.task.call('token-op',{'name':'jarvis_media_web','arguments':{'action':'quartz_mode','query':'coding'}})
        power.assert_not_called()
        from core.desktop_mcp import TOOLS
        tool=next(t for t in TOOLS if t['name']=='jarvis_media_web')
        self.assertNotIn('quartz_mode',tool['inputSchema']['properties']['action']['enum'])

    def test_stale_inflight_call_cannot_overlap_or_certify_next_task(self):
        entered=threading.Event();release=threading.Event();errors=[]
        def slow(_):entered.set();release.wait(4);return 'OLD_RESULT'
        self.adv.smart_open=slow
        def invoke():
            try:self.task.call('token-op',{'name':'jarvis_open_app','arguments':{'target':'notepad'}})
            except Exception as exc:errors.append(exc)
        worker=threading.Thread(target=invoke);worker.start()
        self.addCleanup(lambda:(release.set(),worker.join(3)))
        self.assertTrue(entered.wait(1));old_job=self.task.job
        self.task.stop('cancelled')
        self.assertTrue(self.task.status()['stopping']);self.assertTrue(self.task.status()['active'])
        with self.assertRaisesRegex(RuntimeError,'çağrıları'):
            self.task.start('Second',self.fixture.project,'second',self.fixture.models)
        release.set();worker.join(2)
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],PermissionError)
        self.assertNotIn('jarvis_actions',old_job)
        self.assertEqual(old_job['interrupted_calls'][0]['result'],'OLD_RESULT')
        with patch('core.natural_desktop.subprocess.run',return_value=SimpleNamespace(returncode=0)), \
             patch('core.natural_desktop.ensure_antigravity_tool_grants'),patch('core.natural_desktop.write_operator_hooks'):
            self.task.start('Second',self.fixture.project,'second',self.fixture.models,requested_permission_level='full')
        self.assertNotEqual(self.task.job['id'],old_job['id'])
        self.assertNotIn('jarvis_actions',self.task.job)
        old_thread=self.task.thread;self.task.stop();self.assertFalse(old_thread.is_alive())

    def test_target_identity_change_prevents_keyboard_input(self):
        with patch.object(self.backend,'identity',return_value={**self.backend.target,'pid':999}):
            with self.assertRaises(PermissionError):self.call('press_key',target_window=1,keys='enter')
        self.mouse.press.assert_not_called()


class RoutingRegressionTests(unittest.TestCase):
    def test_explanations_remain_chat_but_explicit_following_actions_run(self):
        for text in ("Spotify'daki oynat tuşu ne işe yarıyor?",'Set theory hakkında ne düşünüyorsun?',
                     'Bunu yap demek kolay mı?', 'Kopyala komutu ne demek?'):
            with self.subTest(text=text):self.assertEqual(message_intent(text),'conversation')
        for text in ("Chrome'u aç; Spotify oynat tuşu ne işe yarıyor?",'Oynat tuşuna bas',
                     'Codex sesi kıs ve sonucu kontrol et', 'Set the volume to 20'):
            with self.subTest(text=text):self.assertEqual(message_intent(text),'task')

    def test_orphan_continue_is_host_reply_without_new_model_or_permission(self):
        api=gui.Api();state={'status':'ok','data':{'active_conversation':{'id':'c'},'active_turn':None}}
        with patch('gui.ipc_send',side_effect=lambda action,*_:state if action=='chat_status' else {'status':'ok'}) as ipc, \
             patch.object(api,'natural_start') as start:
            result=api.coordination_route('Devam et','c','p',{},'full')
        start.assert_not_called();self.assertIn('devam eden bir görev yok',result['data']['continuation_status'])
        self.assertTrue(result['data']['handled']);self.assertEqual(ipc.call_count,3)


if __name__=='__main__':unittest.main()
