"""
memory_system.py  —  Quartz Persistent Memory
Fixed:
  - Debounced writes (no disk write every call)
  - Thread-safe with lock
  - Graceful shutdown flush
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from logger import get_logger
from core.atomic_json import atomic_write_json, load_json

log = get_logger(__name__)

BASE_DIR      = Path(__file__).parent
MEMORY_FILE   = BASE_DIR / "quartz_memory.json"
_OLD_MEMORY_FILE = BASE_DIR / "jarvis_memory.json"  # pre-rename fallback


def _default_memory() -> dict:
    return {
        "user": {
            "name":       None,
            "language":   "english",
            "timezone":   None,
            "city":       "Istanbul",
            "created_at": datetime.now().isoformat(),
        },
        "preferences": {
            "default_browser":   "chrome",
            "default_music_app": "youtube",
            "default_editor":    "vscode",
            "volume_level":      50,
            "theme":             "dark",
        },
        "habits": {
            "most_opened_apps":   {},
            "most_played_songs":  {},
            "most_visited_sites": {},
            "most_used_commands": {},
        },
        "notes":           [],
        "reminders":       [],
        "facts":           {},
        "last_session": {
            "date":     None,
            "messages": 0,
        },
        "history_summary": [],
    }


class MemorySystem:

    def __init__(self):
        self._memory      = self._load()
        self._dirty       = False
        self._lock        = threading.Lock()
        self._save_timer: Optional[threading.Timer] = None
        self._update_session()
        log.info("MemorySystem initialized")

    # ── Load / Save ───────────────────────────────────

    def _load(self) -> dict:
        try:
            if MEMORY_FILE.exists():
                data = load_json(MEMORY_FILE, {})
                return self._deep_merge(
                    _default_memory(), data)

            # One-time migration from the old
            # pre-rename (JARVIS) memory file.
            if _OLD_MEMORY_FILE.exists():
                data = load_json(_OLD_MEMORY_FILE, {})
                merged = self._deep_merge(
                    _default_memory(), data)
                log.info(
                    "Migrated memory from %s -> %s",
                    _OLD_MEMORY_FILE.name,
                    MEMORY_FILE.name)
                return merged
        except Exception as exc:
            log.warning(
                "Memory load failed: %s", exc)
        return _default_memory()

    def _deep_merge(self,
                    base: dict,
                    override: dict) -> dict:
        result = base.copy()
        for key, val in override.items():
            if (key in result
                    and isinstance(result[key], dict)
                    and isinstance(val, dict)):
                result[key] = self._deep_merge(
                    result[key], val)
            else:
                result[key] = val
        return result

    def _mark_dirty(self) -> None:
        """Schedule a deferred disk write."""
        self._dirty = True
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(
            2.0, self._flush)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _flush(self) -> None:
        """Write to disk only if dirty."""
        if not self._dirty:
            return
        with self._lock:
            try:
                atomic_write_json(MEMORY_FILE, self._memory)
                self._dirty = False
                log.debug("Memory flushed to disk")
            except Exception as exc:
                log.warning(
                    "Memory flush failed: %s", exc)

    def shutdown(self) -> None:
        """Force save on Quartz exit."""
        if self._save_timer:
            self._save_timer.cancel()
        self._dirty = True
        self._flush()
        log.info("MemorySystem shutdown complete")

    def _update_session(self) -> None:
        self._memory["last_session"]["date"] = (
            datetime.now().isoformat())
        self._mark_dirty()

    # ── User info ─────────────────────────────────────

    def set_user_name(self, name: str) -> None:
        with self._lock:
            self._memory["user"]["name"] = name
        self._mark_dirty()

    def get_user_name(self) -> Optional[str]:
        return self._memory["user"].get("name")

    def set_language(self, lang: str) -> None:
        with self._lock:
            self._memory["user"]["language"] = lang
        self._mark_dirty()

    def get_language(self) -> str:
        return self._memory["user"].get(
            "language", "english")

    def get_user_city(self) -> str:
        return self._memory["user"].get(
            "city", "Istanbul")

    def set_user_city(self, city: str) -> None:
        with self._lock:
            self._memory["user"]["city"] = city
        self._mark_dirty()

    # ── Preferences ───────────────────────────────────

    def set_preference(self,
                       key: str,
                       value) -> None:
        with self._lock:
            self._memory["preferences"][key] = value
        self._mark_dirty()

    def get_preference(self,
                       key: str,
                       default=None):
        return self._memory["preferences"].get(
            key, default)

    def get_all_preferences(self) -> dict:
        return dict(self._memory["preferences"])

    # ── Habits ────────────────────────────────────────

    def track_app_open(self, app: str) -> None:
        with self._lock:
            apps = self._memory["habits"][
                "most_opened_apps"]
            apps[app] = apps.get(app, 0) + 1
        self._mark_dirty()

    def track_song_play(self, song: str) -> None:
        with self._lock:
            songs = self._memory["habits"][
                "most_played_songs"]
            songs[song] = songs.get(song, 0) + 1
        self._mark_dirty()

    def track_site_visit(self, url: str) -> None:
        with self._lock:
            sites = self._memory["habits"][
                "most_visited_sites"]
            sites[url] = sites.get(url, 0) + 1
        self._mark_dirty()

    def track_command(self, cmd: str) -> None:
        with self._lock:
            cmds = self._memory["habits"][
                "most_used_commands"]
            cmds[cmd] = cmds.get(cmd, 0) + 1
        self._mark_dirty()

    def get_top_apps(self, n: int = 5) -> list:
        apps = self._memory["habits"][
            "most_opened_apps"]
        return sorted(
            apps.items(),
            key=lambda x: x[1],
            reverse=True)[:n]

    def get_top_songs(self, n: int = 5) -> list:
        songs = self._memory["habits"][
            "most_played_songs"]
        return sorted(
            songs.items(),
            key=lambda x: x[1],
            reverse=True)[:n]

    def get_top_sites(self, n: int = 5) -> list:
        sites = self._memory["habits"][
            "most_visited_sites"]
        return sorted(
            sites.items(),
            key=lambda x: x[1],
            reverse=True)[:n]

    # ── Notes ─────────────────────────────────────────

    def add_note(self,
                 content: str,
                 tag: str = "general") -> str:
        with self._lock:
            note = {
                "id":         len(
                    self._memory["notes"]) + 1,
                "content":    content,
                "tag":        tag,
                "created_at": datetime.now()
                              .isoformat(),
            }
            self._memory["notes"].append(note)
        self._mark_dirty()
        return f"Note saved: {content[:50]}"

    def get_notes(self,
                  tag: str = None,
                  limit: int = 10) -> list:
        notes = self._memory["notes"]
        if tag:
            notes = [n for n in notes
                     if n.get("tag") == tag]
        return notes[-limit:]

    def get_notes_text(self,
                       tag: str = None,
                       limit: int = 10) -> str:
        notes = self.get_notes(tag, limit)
        if not notes:
            return "No notes found."
        lines = []
        for n in notes:
            ts = n.get("created_at", "")[:10]
            lines.append(
                f"[{n['id']}] ({ts}) "
                f"{n['content']}")
        return "\n".join(lines)

    def delete_note(self, note_id: int) -> str:
        with self._lock:
            before = len(self._memory["notes"])
            self._memory["notes"] = [
                n for n in self._memory["notes"]
                if n.get("id") != note_id]
        self._mark_dirty()
        after = len(self._memory["notes"])
        if after < before:
            return f"Note {note_id} deleted"
        return f"Note {note_id} not found"

    # ── Facts ─────────────────────────────────────────

    def remember_fact(self,
                      key: str,
                      value: str) -> str:
        with self._lock:
            self._memory["facts"][key] = {
                "value":      value,
                "learned_at": datetime.now()
                              .isoformat(),
            }
        self._mark_dirty()
        return f"I will remember: {key} = {value}"

    def recall_fact(self,
                    key: str) -> Optional[str]:
        fact = self._memory["facts"].get(key)
        return fact.get("value") if fact else None

    def get_all_facts(self) -> str:
        facts = self._memory["facts"]
        if not facts:
            return "No facts stored."
        return "\n".join(
            f"  {k}: {v.get('value','')}"
            for k, v in facts.items())

    def forget_fact(self, key: str) -> str:
        with self._lock:
            if key in self._memory["facts"]:
                del self._memory["facts"][key]
                self._mark_dirty()
                return f"Forgotten: {key}"
        return f"Fact not found: {key}"

    # ── Session ───────────────────────────────────────

    def increment_messages(self) -> None:
        with self._lock:
            self._memory["last_session"][
                "messages"] = (
                self._memory["last_session"]
                .get("messages", 0) + 1)
        self._mark_dirty()

    def get_session_info(self) -> str:
        sess = self._memory["last_session"]
        return (
            f"Last session: "
            f"{sess.get('date', 'N/A')}\n"
            f"Messages: "
            f"{sess.get('messages', 0)}")

    # ── Summaries ─────────────────────────────────────

    def add_summary(self, summary: str) -> None:
        with self._lock:
            self._memory["history_summary"].append({
                "summary":    summary,
                "created_at": datetime.now()
                              .isoformat(),
            })
            self._memory["history_summary"] = (
                self._memory[
                    "history_summary"][-20:])
        self._mark_dirty()

    def get_summaries(self, n: int = 5) -> str:
        summaries = (
            self._memory["history_summary"][-n:])
        if not summaries:
            return "No summaries yet."
        return "\n".join(
            s.get("summary", "")
            for s in summaries)

    # ── Reports ───────────────────────────────────────

    def get_full_report(self) -> str:
        name      = self.get_user_name() or "Unknown"
        top_apps  = self.get_top_apps(3)
        top_songs = self.get_top_songs(3)
        top_sites = self.get_top_sites(3)
        facts     = self.get_all_facts()
        notes     = self.get_notes_text(limit=5)
        prefs     = self.get_all_preferences()

        apps_str  = ", ".join(
            f"{a}({c})" for a, c in top_apps
        ) or "None"
        songs_str = ", ".join(
            f"{s}({c})" for s, c in top_songs
        ) or "None"
        sites_str = ", ".join(
            f"{s}({c})" for s, c in top_sites
        ) or "None"

        return (
            f"USER: {name}\n"
            f"LANGUAGE: {self.get_language()}\n"
            f"CITY: {self.get_user_city()}\n"
            f"TOP APPS: {apps_str}\n"
            f"TOP SONGS: {songs_str}\n"
            f"TOP SITES: {sites_str}\n"
            f"PREFERENCES: "
            f"{json.dumps(prefs)}\n"
            f"FACTS:\n{facts}\n"
            f"RECENT NOTES:\n{notes}\n")

    def get_ai_context(self) -> str:
        """Compact context injected into AI prompt."""
        name      = self.get_user_name()
        lang      = self.get_language()
        city      = self.get_user_city()
        facts     = self._memory.get("facts", {})
        prefs     = self._memory.get(
            "preferences", {})
        top_apps  = self.get_top_apps(3)
        top_songs = self.get_top_songs(3)
        notes     = self.get_notes(limit=3)

        lines = ["[QUARTZ MEMORY]"]

        if name:
            lines.append(f"User name: {name}")
        lines.append(f"Language: {lang}")
        lines.append(f"City: {city}")

        if facts:
            lines.append("Known facts:")
            for key, data in list(
                    facts.items())[:5]:
                lines.append(
                    f"  {key}: "
                    f"{data.get('value','')}")

        if top_apps:
            lines.append(
                "Favorite apps: "
                + ", ".join(
                    a for a, _ in top_apps))

        if top_songs:
            lines.append(
                "Favorite songs: "
                + ", ".join(
                    s for s, _ in top_songs))

        vol = prefs.get("volume_level")
        if vol is not None:
            lines.append(
                f"Preferred volume: {vol}%")

        if notes:
            lines.append("Recent notes:")
            for n in notes:
                lines.append(
                    f"  - "
                    f"{n.get('content','')[:60]}")

        lines.append("[END MEMORY]")
        return "\n".join(lines)
