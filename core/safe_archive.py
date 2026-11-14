"""Extract a zip a person or a skill author handed to SpeS, safely (14 Nov 2026).

Used by chat attachments and the skill shelf. Nothing inside is ever executed: this
only copies bytes. Refused: absolute paths, ``..`` escapes, drive letters, links,
device names, too many files, too large a total, and suspicious compression ratios
(zip bombs). Secret-looking names (``.env``, keys) are skipped, not extracted.
"""
from __future__ import annotations

import stat
import zipfile
from pathlib import Path, PurePosixPath

from core.project_read_mcp import SECRET_NAME

MAX_FILES = 2000
MAX_TOTAL_BYTES = 200 * 1024 * 1024
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_RATIO = 200          # uncompressed / compressed for one member
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class ArchiveError(ValueError):
    """The archive is not one SpeS will open."""


def _safe_parts(name: str) -> list[str]:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or not path.parts:
        raise ArchiveError(f"Arşivde mutlak yol var: {name}")
    parts = []
    for part in path.parts:
        if part in ("", ".", ".."):
            raise ArchiveError(f"Arşivde klasör dışına çıkan yol var: {name}")
        if ":" in part or part.split(".")[0].lower() in _RESERVED or part.endswith((" ", ".")):
            raise ArchiveError(f"Arşivde geçersiz Windows adı var: {name}")
        parts.append(part)
    return parts


def extract_zip(archive: Path, target: Path) -> dict:
    """Extract ``archive`` into the empty or new folder ``target``. Returns a summary."""
    archive, target = Path(archive), Path(target)
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve(strict=True)
    if any(root.iterdir()):
        raise ArchiveError("Hedef klasör boş değil")
    try:
        bundle = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise ArchiveError("Geçerli bir zip dosyası değil") from exc
    files, skipped, total = [], [], 0
    with bundle:
        members = bundle.infolist()
        if len(members) > MAX_FILES:
            raise ArchiveError(f"Arşivde çok fazla dosya var (en çok {MAX_FILES})")
        for info in members:
            parts = _safe_parts(info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ArchiveError(f"Arşivde bağlantı (symlink) var: {info.filename}")
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise ArchiveError("Şifreli zip açılmaz")
            if any(SECRET_NAME.match(part) for part in parts):
                skipped.append(info.filename)
                continue
            if info.file_size > MAX_FILE_BYTES:
                raise ArchiveError(f"Arşivdeki bir dosya çok büyük: {info.filename}")
            if info.compress_size and info.file_size / info.compress_size > MAX_RATIO and info.file_size > 1024 * 1024:
                raise ArchiveError("Arşiv sıkıştırma oranı şüpheli (zip bombası olabilir)")
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ArchiveError("Arşivin açılmış boyutu çok büyük")
            destination = root.joinpath(*parts)
            if root not in destination.resolve().parents:
                raise ArchiveError(f"Arşivde klasör dışına çıkan yol var: {info.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with bundle.open(info) as source, open(destination, "xb") as sink:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > info.file_size or written > MAX_FILE_BYTES:
                        raise ArchiveError("Arşivdeki dosya beyan edilenden büyük")
                    sink.write(chunk)
            files.append("/".join(parts))
    return {"files": files, "skipped_secret": skipped, "bytes": total}
