"""Real isolated install acceptance; no credentials, user config or Desktop apps."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.cli_installer import CliInstaller, node_command, resolve_cli


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--providers', nargs='+', choices=['codex','gemini','agy'], default=['codex','gemini'])
    args=parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    empty = root / 'empty-app'; empty.mkdir(exist_ok=True)
    environment = {k:v for k,v in os.environ.items() if not any(t in k.upper() for t in ('API_KEY','TOKEN','SECRET','PASSWORD'))}
    environment.update(QUARTZ_CLI_ROOT=str(root/'bin'), PATH=os.path.join(os.environ.get('SystemRoot',r'C:\Windows'),'System32'),
                       LOCALAPPDATA=str(root/'LocalAppData'), CODEX_HOME=str(root/'empty-codex-home'),
                       NPM_CONFIG_USERCONFIG=str(root/'empty.npmrc'), NPM_CONFIG_CACHE=str(root/'npm-cache'))
    for name in ('QUARTZ_CODEX_PATH','QUARTZ_GEMINI_PATH','QUARTZ_ANTIGRAVITY_PATH'):
        environment.pop(name,None)
    evidence = {'scope':'Real Node/npm install and CLI --version; no authentication or model request', 'providers':{}}
    with patch.dict(os.environ,environment,clear=True), patch('core.cli_installer.app_root',return_value=empty), patch('core.cli_installer.shutil.which',return_value=None):
        installer=CliInstaller(root/'bin')
        evidence['initial']=installer.status()
        for provider in args.providers:
            result=installer.install(provider)
            version=subprocess.run(node_command(result['executable'],['--version']),capture_output=True,text=True,timeout=60,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            evidence['providers'][provider]={**result,'version_stdout':version.stdout.strip(),'exit_code':version.returncode}
            (root/'acceptance.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
            if version.returncode:raise RuntimeError(provider+' version failed')
        evidence['final']={provider: resolve_cli(provider,root=root/'bin') for provider in args.providers}
        evidence['passed']=all(p['exit_code']==0 for p in evidence['providers'].values())
    (root/'acceptance.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':main()
