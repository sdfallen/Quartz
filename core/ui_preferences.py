"""Appearance preferences for the desktop window. No task, permission or account data."""
import os
import threading
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json

DEFAULTS = {"theme": "dark", "crystal": "citrine"}
_SAVE_LOCK = threading.Lock()  # pywebview runs each API call on its own thread.
ALLOWED = {"theme": ("dark", "light", "system"), "crystal": ("rose", "citrine", "amethyst", "smoky")}


def preferences_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Quartz" / "ui-preferences.json"  # folder name kept: holds saved preferences


def load_ui_preferences(path=None) -> dict:
    stored = load_json(path or preferences_path(), {})
    stored = stored if isinstance(stored, dict) else {}
    return {key: stored.get(key) if stored.get(key) in ALLOWED[key] else DEFAULTS[key] for key in DEFAULTS}


def save_ui_preference(key: str, value: str, path=None) -> dict:
    if key not in ALLOWED or value not in ALLOWED[key]:
        raise ValueError("Bilinmeyen görünüm tercihi")
    target = Path(path or preferences_path())
    with _SAVE_LOCK:
        current = load_ui_preferences(target)
        current[key] = value
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(target, current)
    return current


def apply_to_document(html: str, path=None) -> str:
    """Set the theme before first paint so the window never flashes the wrong colours."""
    prefs = load_ui_preferences(path)
    return html.replace('<html lang="tr">', f'<html lang="tr" data-theme="{prefs["theme"]}" data-crystal="{prefs["crystal"]}">', 1)


def window_background(path=None) -> str:
    return "#f5f6f3" if load_ui_preferences(path)["theme"] == "light" else "#121416"
