import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from core.cli_installer import CliInstaller, node_command, resolve_cli


class CliInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"QUARTZ_CLI_ROOT": str(self.root)}, clear=True)
        self.env.start()
        self.which = patch('core.cli_installer.shutil.which', return_value=None)
        self.which.start()

    def tearDown(self):
        self.which.stop(); self.env.stop(); self.temp.cleanup()

    def test_clean_machine_requires_no_desktop_and_has_no_global_path_changes(self):
        before = dict(os.environ)
        with patch('core.cli_installer.app_root', return_value=self.root):
            result = CliInstaller(self.root).status()
        self.assertFalse(result['codex']['installed'])
        self.assertFalse(result['gemini']['installed'])
        self.assertEqual(before, dict(os.environ))

    def test_local_manifest_and_explicit_path_are_discovered(self):
        cli = self.root/'codex.js'; cli.write_text('')
        (self.root/'installed.json').write_text(json.dumps({'codex':{'executable':str(cli)}}))
        self.assertEqual(resolve_cli('codex'),str(cli.resolve()))
        self.assertEqual(resolve_cli('gemini',str(cli)),str(cli.resolve()))

    def test_existing_codex_cache_is_optional_when_launch_path_differs(self):
        executable=self.root/'OpenAI/Codex/bin/version/codex.exe'
        executable.parent.mkdir(parents=True);executable.touch()
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.root)}):
            self.assertEqual(resolve_cli('codex'),str(executable.resolve()))

    def test_node_invocation_never_interpolates_prompt_into_shell(self):
        node = self.root/'node/node.exe'; node.parent.mkdir();node.touch()
        cli = self.root/'packages/gemini/index.js';cli.parent.mkdir(parents=True);cli.touch()
        prompt = 'a & echo secret $(test)'
        self.assertEqual(node_command(cli,['-p',prompt]),[str(node),str(cli),'-p',prompt])
        unknown = self.root/'weird.cmd';unknown.touch()
        with self.assertRaises(RuntimeError):node_command(unknown,['-p',prompt])

    def test_checksum_failure_does_not_publish_runtime(self):
        def fetch(url):
            if url.endswith('index.json'):
                return json.dumps([{'lts':'Test','version':'v24.1.0','files':['win-x64-zip']}]).encode()
            if url.endswith('SHASUMS256.txt'):
                return ('0'*64+'  node-v24.1.0-win-x64.zip').encode()
            return b'corrupt'
        with patch('core.cli_installer.platform.system',return_value='Windows'), patch('core.cli_installer.platform.machine',return_value='AMD64'):
            with self.assertRaisesRegex(ValueError,'SHA256'):CliInstaller(self.root,fetch=fetch)._node()
        self.assertFalse((self.root/'node').exists())

    def test_safe_node_extract_and_traversal_rejection(self):
        for entry in ('node-v24.1.0-win-x64/node.exe','../outside.exe'):
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as archive:archive.writestr(entry,b'test')
            data=output.getvalue()
            def fetch(url):
                if url.endswith('index.json'):return b'[{"lts":"test","version":"v24.1.0","files":["win-x64-zip"]}]'
                if url.endswith('SHASUMS256.txt'):return (hashlib.sha256(data).hexdigest()+'  node-v24.1.0-win-x64.zip').encode()
                return data
            runtime_root=self.root/('bad' if entry.startswith('..') else 'good')
            with patch('core.cli_installer.platform.system',return_value='Windows'), patch('core.cli_installer.platform.machine',return_value='AMD64'):
                if entry.startswith('..'):
                    with self.assertRaises(ValueError):CliInstaller(runtime_root,fetch=fetch)._node()
                else:self.assertTrue(CliInstaller(runtime_root,fetch=fetch)._node()[0].is_file())

    def test_failed_npm_never_sets_installed_manifest(self):
        installer=CliInstaller(self.root,fetch=lambda _:b'{"version":"1.2.3"}',run=Mock(return_value=SimpleNamespace(returncode=1)))
        with patch.object(installer,'_node',return_value=(self.root/'node.exe',self.root/'npm.js')):
            with self.assertRaises(RuntimeError):installer.install('gemini')
        self.assertFalse((self.root/'installed.json').exists())

    def test_success_publishes_only_after_version_probe(self):
        calls=[]
        def run(command,**kwargs):
            calls.append(command)
            if 'install' in command:
                prefix=Path(command[command.index('--prefix')+1]);script=prefix/'node_modules/@google/gemini-cli/dist/index.js'
                script.parent.mkdir(parents=True);script.write_text('')
                (prefix/'node_modules/@google/gemini-cli/package.json').write_text(json.dumps({'name':'@google/gemini-cli','bin':{'gemini':'dist/index.js'}}))
            return SimpleNamespace(returncode=0,stdout='1.2.3',stderr='')
        installer=CliInstaller(self.root,fetch=lambda _:b'{"version":"1.2.3"}',run=run)
        with patch.object(installer,'_node',return_value=(self.root/'node.exe',self.root/'npm.js')):
            result=installer.install('gemini')
        self.assertTrue(Path(result['executable']).is_file())
        self.assertEqual(calls[-1][-1],'--version')
        self.assertIn('--ignore-scripts',calls[0])
        self.assertIn('gemini',json.loads((self.root/'installed.json').read_text()))


if __name__=='__main__':unittest.main()
