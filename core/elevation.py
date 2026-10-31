"""Explicit per-application UAC handoff; never elevate Quartz or automate consent."""
import os
from pathlib import Path
import shutil
import subprocess


class ElevationRequired(OSError):
    def __init__(self, path):
        super().__init__(740, 'Bu uygulama Windows yönetici onayı istiyor')
        self.winerror = 740
        from core.desktop_launch import describe_launch
        resolved = str(path) if Path(path).is_absolute() else shutil.which(str(path))
        self.approval = describe_launch(resolved) if resolved else None


def launch_normal(path):
    try:
        return subprocess.Popen([str(path)], shell=False)
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 740:
            raise ElevationRequired(path) from exc
        raise


def request_uac(approval, *, cancelled=None):
    from core.desktop_launch import validate_launch
    validate_launch(approval)
    if cancelled is not None and cancelled():
        return {'state':'cancelled_before_launch','verified':False}
    if os.name != 'nt': raise OSError('Windows gerekir')
    try:
        os.startfile(approval['exe'], 'runas', cwd=str(Path(approval['exe']).parent))
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 1223:
            return {'state':'cancelled','verified':False,'winerror':1223}
        return {'state':'failed','verified':False,'winerror':getattr(exc,'winerror',None)}
    return {'state':'launch_requested','verified':False,
            'message':'Windows başlatma isteğini kabul etti; pencere ve işlem kimliği henüz doğrulanmadı.'}


def token_elevated(pid):
    if os.name != 'nt': return None
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    adv=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    adv.OpenProcessToken.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE)]
    adv.GetTokenInformation.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    proc=kernel.OpenProcess(0x1000,False,int(pid))
    if not proc:return None
    token=wintypes.HANDLE()
    try:
        if not adv.OpenProcessToken(proc,8,ctypes.byref(token)):return None
        value=wintypes.DWORD();needed=wintypes.DWORD()
        if not adv.GetTokenInformation(token,20,ctypes.byref(value),ctypes.sizeof(value),ctypes.byref(needed)):return None
        return bool(value.value)
    finally:
        if token:kernel.CloseHandle(token)
        kernel.CloseHandle(proc)


def require_input_integrity(target):
    current, other = token_integrity(os.getpid()), token_integrity(target['pid'])
    if current is None or other is None:
        raise PermissionError('İşlem yetki seviyesi doğrulanamadı; girdi gönderilmedi')
    if other > current:
        raise PermissionError('UIPI: Hedef yönetici yetkisinde, Quartz normal yetkide. Otomatik girdi gönderilmedi; manuel kontrol gerekiyor.')


def token_integrity(pid):
    if os.name != 'nt': return None
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    adv=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    adv.OpenProcessToken.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE)]
    adv.GetTokenInformation.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    adv.GetSidSubAuthorityCount.argtypes=[ctypes.c_void_p];adv.GetSidSubAuthorityCount.restype=ctypes.POINTER(ctypes.c_ubyte)
    adv.GetSidSubAuthority.argtypes=[ctypes.c_void_p,wintypes.DWORD];adv.GetSidSubAuthority.restype=ctypes.POINTER(wintypes.DWORD)
    proc=kernel.OpenProcess(0x1000,False,int(pid));token=wintypes.HANDLE()
    if not proc:return None
    try:
        if not adv.OpenProcessToken(proc,8,ctypes.byref(token)):return None
        needed=wintypes.DWORD();adv.GetTokenInformation(token,25,None,0,ctypes.byref(needed))
        if not 0<needed.value<=4096:return None
        buffer=ctypes.create_string_buffer(needed.value)
        if not adv.GetTokenInformation(token,25,buffer,len(buffer),ctypes.byref(needed)):return None
        sid=ctypes.cast(buffer,ctypes.POINTER(ctypes.c_void_p)).contents.value
        if not sid:return None
        count=adv.GetSidSubAuthorityCount(sid).contents.value
        if not 1<=count<=15:return None
        return adv.GetSidSubAuthority(sid,count-1).contents.value
    finally:
        if token:kernel.CloseHandle(token)
        kernel.CloseHandle(proc)
