import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from core.onboarding import OnboardingService
from core.gemini_runtime import GeminiRuntime,google_runtime


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.installer=Mock()
        self.installer.status.return_value={'codex':{'installed':False,'executable':None},'gemini':{'installed':True,'executable':'gemini.exe'}}
        self.service=OnboardingService(self.root,self.installer,validate=Mock())

    def tearDown(self):self.temp.cleanup()

    def test_invalid_key_does_not_install_or_save(self):
        self.service.validate.side_effect=ValueError('Anahtar kabul edilmedi')
        self.service._work('key','gemini','secret-test-value')
        self.assertEqual(self.service.job['state'],'error')
        self.installer.install.assert_not_called()
        self.assertFalse((self.root/'.env').exists())

    def test_one_key_saves_atomically_without_overwriting_preferences_or_exposing_secret(self):
        (self.root/'.env').write_text('VOICE_LANGUAGE=tr-TR\n')
        (self.root/'quartz_memory.json').write_text('{"preferences":{"theme":"dark"}}')
        with patch('core.onboarding.resolve_cli',return_value='gemini.exe'):
            self.service._work('key','gemini','test-secret-value')
        self.assertEqual(self.service.job['state'],'done')
        env=(self.root/'.env').read_text(); memory=(self.root/'quartz_memory.json').read_text()
        self.assertIn('VOICE_LANGUAGE=tr-TR',env);self.assertIn('GEMINI_API_KEY=',env)
        self.assertNotIn('test-secret-value',memory)
        self.assertNotIn('test-secret-value',json.dumps(self.service.job))
        self.assertEqual(json.loads(memory)['preferences']['theme'],'dark')

    def test_single_provider_is_ready_without_other_provider(self):
        self.service._save('gemini','test-secret-value')
        with patch.dict(os.environ,{},clear=True),patch('core.onboarding.Path.home',return_value=self.root):
            state=self.service.status()
        self.assertFalse(state['needs_setup']);self.assertTrue(state['providers']['gemini']['ready'])
        self.assertFalse(state['providers']['codex']['ready'])

    def test_busy_setup_does_not_start_second_worker(self):
        self.service.job={'state':'running'}
        with self.assertRaises(RuntimeError):self.service.begin('install','codex')

    def test_failed_metadata_commit_restores_original_env(self):
        (self.root/'.env').write_text('VOICE_LANGUAGE=tr-TR\n')
        with patch('core.onboarding.atomic_write_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.service._save('gemini','test-secret-value')
        self.assertEqual((self.root/'.env').read_text(),'VOICE_LANGUAGE=tr-TR\n')

    def test_key_never_enters_codex_command_arguments(self):
        key='test-secret-value'
        with patch('core.onboarding.resolve_cli',return_value='codex.exe'),patch('core.onboarding.subprocess.run',return_value=SimpleNamespace(returncode=0)) as run:
            self.service._work('key','codex',key)
        self.assertNotIn(key,str(run.call_args.args))
        self.assertEqual(run.call_args.kwargs['input'],key+'\n')

    def test_account_login_is_explicit_and_does_not_store_key(self):
        with patch('core.onboarding.resolve_cli',return_value='gemini.exe'),patch('core.onboarding.subprocess.Popen') as launch:
            self.service._work('account','gemini','')
        launch.assert_called_once()
        self.assertFalse((self.root/'.env').exists())


class GeminiAdapterTests(unittest.TestCase):
    def test_stream_mapping_preserves_session_text_and_result(self):
        runtime=object.__new__(GeminiRuntime)
        self.assertEqual(runtime._normalize_event({'type':'init','session_id':'abc'})['conversation_id'],'gemini:abc')
        self.assertEqual(runtime._normalize_event({'type':'message','role':'assistant','content':'Merhaba'})['step_update']['text_delta'],'Merhaba')
        self.assertEqual(runtime._normalize_event({'type':'result','status':'success'})['result']['status'],'SUCCESS')

    def test_gemini_arguments_are_not_agy_arguments(self):
        runtime=object.__new__(GeminiRuntime);runtime.executable='gemini.exe'
        command=runtime._command(['-p','hello','--output-format','stream-json','--print-timeout','2m','--mode','accept-edits','--dangerously-skip-permissions','--effort','high'])
        self.assertIn('yolo',command);self.assertNotIn('--effort',command);self.assertNotIn('--print-timeout',command)

    def test_factory_works_without_antigravity_desktop(self):
        with patch('core.gemini_runtime.cli_environment',return_value={}),patch('core.gemini_runtime._gemini_connection_meta',return_value={}),patch('core.gemini_runtime.GeminiRuntime') as gemini:
            google_runtime(legacy_factory=Mock(side_effect=FileNotFoundError()))
            gemini.assert_called_once()

    def test_existing_account_runtime_is_preserved(self):
        existing=Mock()
        with patch('core.gemini_runtime.cli_environment',return_value={}),patch('core.gemini_runtime._gemini_connection_meta',return_value={}),patch.dict(os.environ,{},clear=True):
            self.assertIs(google_runtime(legacy_factory=Mock(return_value=existing)),existing)

    def test_desktop_config_does_not_persist_bearer_token(self):
        runtime=object.__new__(GeminiRuntime)
        with patch('core.gemini_runtime.cli_environment',return_value={}),patch('core.desktop_agents.mcp_command',return_value=['helper.exe']):
            options=runtime._process_options({'env':{'QUARTZ_DESKTOP_TOKEN':'secret-token','QUARTZ_DESKTOP_URL':'http://localhost/tool'}},Path('.'),{'token':'secret-token','url':'http://localhost/tool'},False)
        path=Path(options['env']['GEMINI_CLI_SYSTEM_SETTINGS_PATH'])
        try:
            text=path.read_text();self.assertNotIn('secret-token',text)
            allowed=json.loads(text)['tools']['core']
            self.assertTrue(allowed)
            self.assertTrue(all(name.startswith('mcp_quartz-desktop_') for name in allowed))
        finally:path.unlink();path.parent.rmdir()


if __name__=='__main__':unittest.main()
