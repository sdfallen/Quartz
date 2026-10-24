"""Scoped local Quartz shortcut branding; never executes script hosts or installers.

Only this checkout's EXE is eligible. Existing links are backed up first. No
registry, pinned-taskbar items, startup choice, or unrelated shortcut is changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.branding import APP_ID


def shell_link(path=None, *, writable=False):
    import pythoncom
    from win32com.shell import shell
    link=pythoncom.CoCreateInstance(shell.CLSID_ShellLink,None,pythoncom.CLSCTX_INPROC_SERVER,shell.IID_IShellLink)
    if path: link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path),2 if writable else 0)
    return link


def read_link(path):
    from win32com.propsys import propsys,pscon
    link=shell_link(path)
    value=link.QueryInterface(propsys.IID_IPropertyStore).GetValue(pscon.PKEY_AppUserModel_ID)
    return {'path':str(path),'target':link.GetPath(0)[0],'icon':link.GetIconLocation(),
            'app_id':value.GetValue() if hasattr(value,'GetValue') else value}


def deliver_link(path,backup,exe,icon):
    import pythoncom
    from win32com.propsys import propsys,pscon
    if path.is_symlink(): raise PermissionError('Refuse shortcut symlink')
    before=read_link(path) if path.exists() else None
    if before and Path(before['target']).resolve()!=exe:
        return {'status':'SKIPPED_UNRELATED','before':before}
    path.parent.mkdir(parents=True,exist_ok=True)
    saved=None
    if before:
        saved=backup/(uuid.uuid4().hex+'-'+path.name)
        shutil.copy2(path,saved)
        if saved.read_bytes()!=path.read_bytes(): raise RuntimeError('Shortcut backup mismatch')
    link=shell_link(path if before else None)
    if not before:
        link.SetPath(str(exe));link.SetWorkingDirectory(str(exe.parent))
        link.SetDescription('Quartz multi-agent workspace')
    link.SetIconLocation(str(icon),0)
    temporary=path.with_name('.quartz-brand-'+uuid.uuid4().hex+'.lnk')
    try:
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(temporary),0)
        # Commit properties on a writable TEMPORARY copy, never the original.
        link=shell_link(temporary,writable=True)
        store=link.QueryInterface(propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID,propsys.PROPVARIANTType(APP_ID));store.Commit()
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(temporary),0)
        del store,link
        readback=read_link(temporary)
        if (Path(readback['target']).resolve()!=exe or Path(readback['icon'][0]).resolve()!=icon
                or readback['app_id']!=APP_ID): raise RuntimeError('Shortcut readback mismatch')
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()  # only our exact newly-created temporary file
    return {'status':'UPDATED' if before else 'CREATED','before':before,'after':read_link(path),
            'backup':str(saved) if saved else None,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backup-dir',type=Path,required=True)
    args=parser.parse_args()
    import pythoncom
    from win32com.shell import shell,shellcon
    pythoncom.CoInitialize()
    try:
        exe=(ROOT/'dist/Quartz/Quartz.exe').resolve(strict=True)
        icon=(ROOT/'assets/branding/quartz-q.ico').resolve(strict=True)
        desktop=Path(shell.SHGetFolderPath(0,shellcon.CSIDL_DESKTOPDIRECTORY,0,0))
        programs=Path(shell.SHGetFolderPath(0,shellcon.CSIDL_PROGRAMS,0,0))
        backup=args.backup_dir.resolve();backup.mkdir(parents=True,exist_ok=False)
        matches=[p for p in desktop.glob('*Quartz*.lnk') if Path(read_link(p)['target']).resolve()==exe]
        paths=matches or [desktop/'Quartz.lnk']
        paths.append(programs/'Quartz/Quartz.lnk')
        result=[deliver_link(path,backup,exe,icon) for path in paths]
        (backup/'shortcut-receipt.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(result,indent=2,ensure_ascii=True))
    finally: pythoncom.CoUninitialize()


if __name__=='__main__': main()
