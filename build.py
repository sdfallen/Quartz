"""Build into a unique staging folder; never delete dist or local user data.

Use --deploy only to replace a CLOSED local Quartz using the verified,
recoverable deployment script. No pip installs, icon invention or user-data upload.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import time
import os

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy",action="store_true")
    parser.add_argument("--require-brand",action="store_true",help="Refuse legacy icon fallback")
    args=parser.parse_args()
    if args.require_brand and not (ROOT/"assets/branding/quartz-q.ico").is_file():
        raise RuntimeError("Approved Q artwork missing; no substitute will be generated")
    for module in ("PyInstaller","webview","psutil","PIL"):
        __import__(module)
    package=Path.home()/".codex/backups"/("quartz-workspace-package-"+time.strftime("%Y%m%d-%H%M%S"))
    package.mkdir(parents=True,exist_ok=False)
    env = os.environ.copy()
    env['PYTHONPYCACHEPREFIX'] = str(package / 'fresh-bytecode')
    env['PYINSTALLER_CONFIG_DIR'] = str(package / 'isolated-pyinstaller-cache')
    def run(command): subprocess.run([sys.executable,'-B',*command],cwd=ROOT,check=True,env=env)
    run(["scripts/check_gui_javascript.py"])
    run(["scripts/run_safe_tests.py"])
    run(["-m","PyInstaller","--noconfirm","--onefile","--console","--name","QuartzDesktopMCP",
         "--distpath",str(ROOT/"build/desktop-helper"),"--workpath",str(package/"helper-work"),
         "--specpath",str(package/"helper-spec"),str(ROOT/"core/desktop_mcp.py")])
    run(["-m","PyInstaller","--noconfirm","--distpath",str(package/"dist"),
         "--workpath",str(package/"work"),str(ROOT/"Quartz.spec")])
    run(["scripts/verify_desktop_package.py",str(package/"dist/Quartz/Quartz.exe")])
    if args.deploy: run(["scripts/finalize_desktop_delivery.py",str(package)])
    print("Verified staged package:",package)
    if not args.deploy: print("Existing dist/user data untouched. Use the finalizer when Quartz is closed.")


if __name__=="__main__": main()
