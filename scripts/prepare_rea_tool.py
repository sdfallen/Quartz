"""Explicit optional REA setup. No agent registration, credentials or global npm/PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.atomic_json import atomic_write_json
from core.cli_installer import CliInstaller
from core.rea_adapter import ReaAdapter


def prepare(prefix, node=None):
    prefix = Path(prefix).absolute()
    if prefix.is_symlink() or getattr(prefix, 'is_junction', lambda: False)():
        raise ValueError('Bağlantılı araç klasörü kullanılmaz')
    prefix = prefix.resolve()
    prefix.mkdir(parents=True, exist_ok=True)
    if node is None:
        node, npm = CliInstaller(prefix/'runtime')._node(prefer_private=True)
    else:
        node = Path(node).resolve(strict=True)
        npm = node.parent/'node_modules/npm/bin/npm-cli.js'
    if not npm.is_file(): raise ValueError('Bu Node kurulumunda npm bulunamadı')
    env = {k:v for k,v in os.environ.items() if not any(t in k.upper() for t in ('TOKEN','SECRET','PASSWORD','API_KEY'))
           and not k.upper().startswith('NPM_CONFIG_') and k.upper() not in {'NODE_OPTIONS','NODE_PATH'}}
    env.update(PATH=str(node.parent)+os.pathsep+env.get('PATH',''), NPM_CONFIG_USERCONFIG=str(prefix/'empty.npmrc'),
               NPM_CONFIG_CACHE=str(prefix/'npm-cache'))
    def run(args, timeout):
        return subprocess.run([str(node),*map(str,args)], env=env, cwd=prefix, capture_output=True,
                              text=True, timeout=timeout, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    version = run(['--version'],15)
    if version.returncode or not ReaAdapter.node_supported(version.stdout):
        raise ValueError('Node sürümü REA koşullarını karşılamıyor; uyumlu özel runtime seçin')
    result = run([npm,'install','--prefix',prefix,'--registry=https://registry.npmjs.org','--ignore-scripts',
                  '--engine-strict','--no-audit','--no-fund','rea-agents@'+ReaAdapter.SUPPORTED_VERSION],600)
    if result.returncode: raise RuntimeError('İsteğe bağlı REA kurulumu tamamlanamadı; mevcut araç tanımı korunuyor')
    script=prefix/'node_modules/rea-agents/scripts/rea.mjs'
    check=run([script,'--version'],30)
    if check.returncode or check.stdout.strip()!=ReaAdapter.SUPPORTED_VERSION:
        raise RuntimeError('REA kuruldu ancak sürüm kontrolü geçmedi')
    receipt={'schema_version':1,'package':'rea-agents','version':ReaAdapter.SUPPORTED_VERSION,
             'node':str(node),'node_version':version.stdout.strip(),'script':str(script),
             'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),
             'source':'https://registry.npmjs.org/rea-agents','install_scripts':False}
    atomic_write_json(prefix/'tool.json',receipt)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix',type=Path,default=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'Quartz/tools/rea')
    parser.add_argument('--node',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.prefix,args.node),indent=2))
