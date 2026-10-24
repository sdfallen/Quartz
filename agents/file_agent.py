"""
agents/file_agent.py  —  JARVIS File Agent
Fixed:
  - Dry-run mode ON by default (safe)
  - Skips recently modified files
  - Full undo log
  - Confirmation required to enable moves
"""

import shutil
import time
from pathlib import Path
from datetime import datetime
from agents.base_agent import BaseAgent
from logger import get_logger

log = get_logger(__name__)

FILE_CATEGORIES = {
    "Images": [
        ".jpg", ".jpeg", ".png", ".gif",
        ".bmp", ".svg", ".ico", ".webp",
        ".tiff",
    ],
    "Videos": [
        ".mp4", ".avi", ".mkv", ".mov",
        ".wmv", ".flv", ".webm", ".m4v",
    ],
    "Audio": [
        ".mp3", ".wav", ".flac", ".aac",
        ".ogg", ".wma", ".m4a",
    ],
    "Documents": [
        ".pdf", ".doc", ".docx", ".txt",
        ".xlsx", ".xls", ".pptx", ".ppt",
        ".odt", ".rtf", ".csv",
    ],
    "Code": [
        ".py", ".js", ".ts", ".html",
        ".css", ".java", ".cpp", ".c",
        ".json", ".xml", ".sql", ".php",
        ".go", ".rs", ".rb", ".sh",
    ],
    "Archives": [
        ".zip", ".rar", ".7z", ".tar",
        ".gz", ".bz2",
    ],
    "Executables": [
        ".exe", ".msi", ".bat", ".cmd",
    ],
}


class FileAgent(BaseAgent):

    def __init__(self, jarvis_tools: dict):
        super().__init__(
            "FileAgent", jarvis_tools)
        self._watch_folder  = str(
            Path.home() / "Downloads")
        self._target_folder = str(
            Path.home() / "Downloads"
            / "Organized")
        self._scan_interval = 60
        self._moved_count   = 0
        self._dry_run       = True   # SAFE default
        self._min_age_secs  = 300    # 5 min old
        self._move_log_path = (
            Path.home()
            / "Downloads"
            / ".jarvis_moves.log")

    # ── Main loop ─────────────────────────────────────

    def run(self, goal: str = ""):
        if goal and Path(goal).exists():
            self._watch_folder = goal

        mode_str = (
            "DRY-RUN" if self._dry_run
            else "LIVE")
        self._log_step(
            f"Watching: {self._watch_folder} "
            f"[{mode_str}] "
            f"every {self._scan_interval}s")

        while self.is_running:
            self._scan_and_organize()
            self._wait(self._scan_interval)

        self._log_step(
            f"File agent stopped. "
            f"Moved {self._moved_count} files.")

    # ── Organization ──────────────────────────────────

    def _scan_and_organize(self):
        try:
            watch = Path(self._watch_folder)
            if not watch.exists():
                self._log_step(
                    f"Watch folder missing: "
                    f"{self._watch_folder}")
                return

            moved   = []
            skipped = []
            now_ts  = time.time()

            for item in watch.iterdir():
                if not item.is_file():
                    continue
                if item.name.startswith("."):
                    continue

                # Skip recently touched files
                try:
                    age = (now_ts
                           - item.stat().st_mtime)
                    if age < self._min_age_secs:
                        skipped.append(item.name)
                        continue
                except Exception:
                    continue

                category = self._categorize(
                    item.suffix.lower())
                if not category:
                    continue

                dest_dir  = (
                    Path(self._target_folder)
                    / category)
                dest_file = dest_dir / item.name

                if dest_file.exists():
                    ts = datetime.now()\
                        .strftime("%H%M%S")
                    dest_file = (
                        dest_dir
                        / f"{item.stem}_{ts}"
                          f"{item.suffix}")

                if self._dry_run:
                    moved.append(
                        f"[DRY] {item.name} "
                        f"→ {category}/")
                else:
                    dest_dir.mkdir(
                        parents=True,
                        exist_ok=True)
                    shutil.move(
                        str(item),
                        str(dest_file))
                    self._log_move(
                        item, dest_file)
                    moved.append(
                        f"{item.name} "
                        f"→ {category}/")
                    self._moved_count += 1

            if skipped:
                self._log_step(
                    f"Skipped "
                    f"{len(skipped)} "
                    f"recent file(s)")

            if moved:
                mode = (
                    "DRY RUN"
                    if self._dry_run
                    else "MOVED")
                report = (
                    f"📁 [{mode}] "
                    f"{len(moved)} file(s):\n"
                    + "\n".join(
                        f"  {m}"
                        for m in moved))
                self._add_result(report)
                self._log_step(
                    f"Processed "
                    f"{len(moved)} files")

        except Exception as exc:
            self._log_step(
                f"Scan error: {exc}")

    def _categorize(self,
                    extension: str) -> str:
        for cat, exts in (
                FILE_CATEGORIES.items()):
            if extension in exts:
                return cat
        return ""

    def _log_move(self,
                  src: Path,
                  dst: Path) -> None:
        try:
            ts = datetime.now().isoformat()
            with open(
                self._move_log_path,
                "a",
                encoding="utf-8",
            ) as fh:
                fh.write(
                    f"{ts}|{src}|{dst}\n")
        except Exception:
            pass

    # ── Manual operations ─────────────────────────────

    def organize_now(self) -> str:
        self._scan_and_organize()
        mode = (
            "Dry-run preview"
            if self._dry_run
            else "Organization")
        return (
            f"{mode} complete. "
            f"Total moved: "
            f"{self._moved_count} files.")

    def enable_move(self) -> str:
        self._dry_run = False
        return (
            "⚠️ File moving ENABLED.\n"
            "Files will now be physically moved.")

    def enable_dry_run(self) -> str:
        self._dry_run = True
        return "Dry-run mode ENABLED (safe)."

    def undo_last_moves(self,
                        count: int = 10) -> str:
        try:
            if not self._move_log_path.exists():
                return "No move log found."

            lines = (
                self._move_log_path
                .read_text(encoding="utf-8")
                .strip()
                .splitlines())

            if not lines:
                return "Move log is empty."

            restored = []
            errors   = []
            for line in reversed(
                    lines[-count:]):
                parts = line.split("|")
                if len(parts) != 3:
                    continue
                _, src, dst = parts
                try:
                    if Path(dst).exists():
                        shutil.move(dst, src)
                        restored.append(
                            Path(dst).name)
                    else:
                        errors.append(
                            f"Missing: {dst}")
                except Exception as exc:
                    errors.append(str(exc))

            msg = ""
            if restored:
                msg += (
                    f"Restored "
                    f"{len(restored)} file(s):\n"
                    + "\n".join(
                        f"  ✅ {f}"
                        for f in restored))
            if errors:
                msg += (
                    "\nErrors:\n"
                    + "\n".join(
                        f"  ❌ {e}"
                        for e in errors))
            return msg or "Nothing to undo."

        except Exception as exc:
            return f"Undo error: {exc}"

    def set_watch_folder(self,
                         path: str) -> str:
        if Path(path).exists():
            self._watch_folder = path
            return f"Now watching: {path}"
        return f"Folder not found: {path}"

    def get_folder_stats(self) -> str:
        try:
            watch = Path(self._watch_folder)
            if not watch.exists():
                return (
                    f"Folder not found: "
                    f"{self._watch_folder}")

            counts     = {}
            total_size = 0
            file_count = 0

            for item in watch.iterdir():
                if not item.is_file():
                    continue
                file_count += 1
                ext = item.suffix.lower()
                cat = self._categorize(ext)
                if cat:
                    counts[cat] = (
                        counts.get(cat, 0) + 1)
                try:
                    total_size += (
                        item.stat().st_size)
                except Exception:
                    pass

            size_mb = total_size / 1e6
            lines   = [
                f"📁 Folder Stats: "
                f"{watch.name}\n"
                f"   Files    : {file_count}\n"
                f"   Size     : "
                f"{size_mb:.1f} MB"
            ]

            if counts:
                lines.append("   By type  :")
                for cat, cnt in sorted(
                    counts.items(),
                    key=lambda x: x[1],
                    reverse=True,
                ):
                    lines.append(
                        f"     {cat}: {cnt}")

            mode = (
                "DRY-RUN"
                if self._dry_run
                else "LIVE")
            lines.append(
                f"   Mode     : {mode}")

            return "\n".join(lines)

        except Exception as exc:
            return f"Stats error: {exc}"