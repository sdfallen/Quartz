"""New-machine install gates. No user keys, accounts, desktop or registry writes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch

from core.cli_installer import CliInstaller, resolve_cli
from core.install_security import checked_url, download, verify_publisher
from core.onboarding import OnboardingService
from core.windows_prerequisites import webview2_status, install_webview2
from scripts.audit_publish import audit_package
from scripts.prepare_distribution import prepare


class NewMachineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_no_credentials_or_desktop_needed_to_install_agy(self):
        data = b'publisher-signed-test-binary'
        release = {'version': '1.4.10', 'url': 'https://storage.googleapis.com/antigravity-public/antigravity-cli/x.exe',
                   'sha512': hashlib.sha512(data).hexdigest()}
        def fetch(url, path, **kwargs):
            path.write_bytes(json.dumps(release).encode() if url.endswith('.json') else data)
            return path
        run = Mock(return_value=SimpleNamespace(returncode=0, stdout='Antigravity CLI 1.4.10'))
        before = dict(os.environ)
        with patch('core.cli_installer.resolve_cli', side_effect=FileNotFoundError), patch('core.cli_installer.platform.system', return_value='Windows'), \
                patch('core.install_security.download', side_effect=fetch), patch('core.install_security.verify_publisher', return_value={'status':'Valid','publisher':'Google LLC'}) as signed:
            result = CliInstaller(self.root, run=run).install('agy')
        self.assertTrue(Path(result['executable']).is_file())
        self.assertEqual(result['sha512'], release['sha512'])
        self.assertEqual(json.loads((self.root/'installed.json').read_text())['agy']['executable'],result['executable'])
        signed.assert_called_once()
        self.assertEqual(run.call_args.args[0][-1], '--version')
        self.assertEqual(dict(os.environ), before)

    def test_agy_checksum_failure_never_executes_or_publishes(self):
        release = {'version':'1.4.10','url':'https://storage.googleapis.com/antigravity-public/antigravity-cli/x.exe','sha512':'0'*128}
        def fetch(url, path, **kwargs):
            path.write_bytes(json.dumps(release).encode() if url.endswith('.json') else b'wrong')
            return path
        run = Mock()
        with patch('core.cli_installer.resolve_cli', side_effect=FileNotFoundError), patch('core.cli_installer.platform.system',return_value='Windows'), \
                patch('core.install_security.download',side_effect=fetch), patch('core.install_security.verify_publisher') as signed:
            with self.assertRaisesRegex(ValueError,'SHA512'): CliInstaller(self.root,run=run).install('agy')
        run.assert_not_called(); signed.assert_not_called()
        self.assertFalse((self.root/'installed.json').exists())

    def test_managed_agy_is_discoverable_without_path(self):
        exe=self.root/'agy.exe';exe.touch()
        (self.root/'installed.json').write_text(json.dumps({'agy':{'executable':str(exe)}}))
        with patch('core.cli_installer.shutil.which',return_value=None):
            self.assertEqual(resolve_cli('agy',root=self.root),str(exe.resolve()))

    def test_missing_agy_one_click_installs_then_launches_official_login(self):
        installer=Mock()
        service=OnboardingService(self.root,installer=installer)
        runtime=Mock(executable='agy.exe')
        runtime.probe.return_value={'installed':True,'ready':False}
        with patch('core.antigravity_runtime.AntigravityRuntime',side_effect=[FileNotFoundError(),runtime]), \
                patch('core.onboarding.subprocess.Popen') as launch:
            service._work('account_agy','gemini','')
        installer.install.assert_called_once_with('agy')
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[0],['agy.exe'])
        self.assertNotIn('GEMINI_API_KEY',launch.call_args.kwargs['env'])
        self.assertEqual(service.job['state'],'done')
        self.assertFalse((self.root/'.env').exists())
        self.assertEqual(json.loads((self.root/'quartz_memory.json').read_text())['cli_connections']['gemini']['backend'],'agy')

    def test_install_failure_does_not_launch_login_or_write_connection(self):
        installer=Mock();installer.install.side_effect=ValueError('İmza doğrulanamadı')
        service=OnboardingService(self.root,installer=installer)
        with patch('core.antigravity_runtime.AntigravityRuntime',side_effect=FileNotFoundError),patch('core.onboarding.subprocess.Popen') as launch:
            service._work('account_agy','gemini','')
        launch.assert_not_called()
        self.assertEqual(service.job['state'],'error')
        self.assertFalse((self.root/'quartz_memory.json').exists())

    def test_pending_login_cannot_launch_duplicate_process(self):
        service=OnboardingService(self.root,installer=Mock())
        service.login_processes['codex']=Mock(poll=Mock(return_value=None))
        with self.assertRaisesRegex(RuntimeError,'giriş penceresini'):service.begin('account','codex')

    def test_official_urls_reject_host_confusion_http_userinfo_and_wrong_bucket(self):
        allowed=[('storage.googleapis.com','/antigravity-public/antigravity-cli/')]
        self.assertTrue(checked_url('https://storage.googleapis.com/antigravity-public/antigravity-cli/ok.exe',allowed))
        for url in ('http://storage.googleapis.com/antigravity-public/antigravity-cli/a',
                    'https://storage.googleapis.com.evil.test/antigravity-public/antigravity-cli/a',
                    'https://storage.googleapis.com/unrelated/a','https://user@storage.googleapis.com/antigravity-public/antigravity-cli/a'):
            with self.subTest(url=url),self.assertRaises(ValueError):checked_url(url,allowed)

    def test_signature_requires_valid_expected_organization(self):
        exe=self.root/'test.exe';exe.touch()
        for status,subject,ok in [('Valid','CN=Google LLC, O=Google LLC, C=US',True),
                                  ('NotSigned','O=Google LLC',False),('Valid','O=Evil Google LLC',False)]:
            result=SimpleNamespace(returncode=0,stdout=json.dumps({'status':status,'subject':subject}))
            with self.subTest(status=status,subject=subject),patch('core.install_security.subprocess.run',return_value=result):
                if ok:self.assertEqual(verify_publisher(exe,'Google LLC')['status'],'Valid')
                else:
                    with self.assertRaises(ValueError):verify_publisher(exe,'Google LLC')

    def test_download_size_bound_removes_partial_but_never_existing_file(self):
        response=Mock();response.geturl.return_value='https://example.com/file'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.side_effect=[b'12345',b'']
        opener=Mock();opener.open.return_value=response
        dest=self.root/'download.exe'
        with patch('core.install_security.urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ValueError):download('https://example.com/file',dest,allowed=[('example.com','/')],limit=2)
            self.assertFalse(dest.exists())
            dest.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):download('https://example.com/file',dest,allowed=[('example.com','/')],limit=2)
            self.assertEqual(dest.read_bytes(),b'keep')

    def test_webview_zero_version_is_missing_and_both_registry_scopes_checked(self):
        registry=MagicMock(HKEY_CURRENT_USER=1,HKEY_LOCAL_MACHINE=2,KEY_WOW64_32KEY=32,KEY_WOW64_64KEY=64,KEY_READ=128)
        registry.QueryValueEx.return_value=('0.0.0.0',1)
        self.assertFalse(webview2_status(registry)['installed'])
        self.assertEqual(registry.OpenKey.call_count,4)
        registry.QueryValueEx.return_value=('140.0.1234.5',1)
        self.assertTrue(webview2_status(registry)['installed'])

    def test_webview_existing_install_does_not_download_or_execute(self):
        with patch('core.windows_prerequisites.webview2_status',return_value={'installed':True}), \
                patch('core.install_security.download') as fetch,patch('core.windows_prerequisites.subprocess.run') as run:
            self.assertTrue(install_webview2()['reused'])
        fetch.assert_not_called();run.assert_not_called()

    def test_webview_requires_microsoft_signature_and_post_install_detection(self):
        def fetch(url,path,**kwargs):path.touch();return path
        with patch('core.windows_prerequisites.webview2_status',side_effect=[{'installed':False},{'installed':False}]), \
                patch('core.install_security.download',side_effect=fetch),patch('core.install_security.verify_publisher') as signed, \
                patch('core.windows_prerequisites.subprocess.run',return_value=SimpleNamespace(returncode=0)) as run:
            with self.assertRaises(RuntimeError):install_webview2()
        self.assertEqual(signed.call_args.args[1],'Microsoft Corporation')
        self.assertEqual(run.call_args.args[0][1:],['/silent','/install'])

    def test_distribution_rejects_private_data_including_nested_browser_profiles(self):
        source=self.root/'source';source.mkdir();(source/'Quartz.exe').write_bytes(b'exe');(source/'_internal').mkdir()
        for name in ('.env','quartz_conversations.json','_internal/EBWebView/Default/Cookies'):
            private=source/name;private.parent.mkdir(parents=True,exist_ok=True);private.write_text('private')
            self.assertEqual(audit_package(source)['status'],'FAIL')
            with self.assertRaises(ValueError):prepare(source,self.root/'release')
            private.unlink()
        # Remove now-empty profile directories for an actually clean input.
        import shutil
        shutil.rmtree(source/'_internal/EBWebView')
        (source/'_internal/library.dll').write_bytes(b'dependency')
        with patch('scripts.prepare_distribution.env_secrets',return_value=[]):
            self.assertEqual(prepare(source,self.root/'release')['status'],'PASS')
        self.assertFalse((self.root/'release/.env').exists())
        self.assertTrue((self.root/'release/release-manifest.json').is_file())

    def test_package_secret_detection_reports_rule_never_value(self):
        source=self.root/'source';source.mkdir();(source/'Quartz.exe').write_bytes(b'test');(source/'_internal').mkdir()
        secret=b'private-fixture-value'
        (source/'_internal/resource.txt').write_bytes(secret)
        result=audit_package(source,[secret])
        self.assertEqual(result['status'],'FAIL')
        self.assertNotIn(secret.decode(),json.dumps(result))

    def test_release_manifest_detects_added_or_changed_runtime(self):
        source=self.root/'source';source.mkdir();(source/'Quartz.exe').write_bytes(b'test');(source/'_internal').mkdir()
        with patch('scripts.prepare_distribution.env_secrets',return_value=[]):prepare(source,self.root/'release')
        exe=self.root/'release/Quartz.exe';exe.write_bytes(b'changed')
        self.assertEqual(audit_package(self.root/'release')['status'],'FAIL')

    def test_pem_exception_requires_exact_bundled_public_ca_bytes(self):
        import certifi
        source=self.root/'source';source.mkdir();(source/'Quartz.exe').write_bytes(b'test')
        ca=source/'_internal/certifi/cacert.pem';ca.parent.mkdir(parents=True)
        ca.write_bytes(Path(certifi.where()).read_bytes())
        self.assertEqual(audit_package(source)['status'],'PASS')
        ca.write_bytes(b'-----BEGIN CERTIFICATE----- changed')
        self.assertEqual(audit_package(source)['status'],'FAIL')


if __name__=='__main__':unittest.main()
