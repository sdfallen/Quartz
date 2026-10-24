# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\LENAVO\\Desktop\\Jarvis config\\jarvis_entry.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\LENAVO\\Desktop\\Jarvis config\\.env', '.'), ('C:\\Users\\LENAVO\\Desktop\\Jarvis config\\jarvis_memory.json', '.'), ('C:\\Users\\LENAVO\\Desktop\\Jarvis config\\chat_history.json', '.')],
    hiddenimports=['PIL._tkinter_finder', 'pystray._win32', 'google.generativeai', 'openai', 'psutil', 'pyautogui', 'mss', 'pyperclip', 'dotenv'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='JARVIS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='NONE',
)
