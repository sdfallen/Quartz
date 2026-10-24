# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
root = Path(SPECPATH)
brand_icon = root/'assets/branding/quartz-q.ico'
if not brand_icon.is_file(): brand_icon = root/'quartz.ico'

datas = [(str(root/'build/desktop-helper/QuartzDesktopMCP.exe'), 'operator'), (str(root/'assets'), 'assets'), (str(root/'quartz.ico'), '.')]
binaries = []
hiddenimports = ['openai', 'psutil', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont', 'pyautogui', 'pywinauto', 'pywinauto.controls.uia_controls', 'pywinauto.controls.win32_controls', 'dotenv', 'mss', 'pyperclip', 'pynput', 'tkinter', 'webview', 'clr', 'webview.platforms.edgechromium', 'webview.platforms.winforms', 'speech_recognition', 'pyaudio', 'pyttsx3', 'pyttsx3.drivers', 'pyttsx3.drivers.sapi5', 'voice_system', 'screen_vision', 'memory_system', 'advanced_controller', 'system_controller', 'assistant', 'mobile_server', 'config', 'logger', 'main', 'gui', 'core.agent_chat', 'core.conversation_store', 'core.multi_agent_service', 'core.antigravity_runtime', 'core.codex_runtime', 'core.atomic_json', 'core.project_registry', 'core.process_tree', 'core.workspace_checkpoint']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [str(root/'quartz_entry.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pandas', 'pyarrow', 'numpy', 'selenium', 'tensorflow', 'pygame', 'matplotlib', 'IPython', 'notebook', 'jupyter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Quartz',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(root/'version_info.txt'),
    icon=[str(brand_icon)],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Quartz',
)
