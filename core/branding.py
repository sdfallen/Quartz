"""One icon source for the native window and build; no automatic logo generation."""
from pathlib import Path
import sys

APP_ID = "AliMehdi.Quartz.Workspace"


def asset_root():
    return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[1]))


def application_icon():
    root=asset_root()
    chosen=root/"assets/branding/quartz-q.ico"
    return chosen if chosen.is_file() else root/"quartz.ico"


def set_windows_app_id():
    if sys.platform=="win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
