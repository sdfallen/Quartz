"""Bounded package acquisition; downloaded files are never executed here.

The installation receipt binds the entire manifest and each extracted file.
Its trust boundary is the local account: an attacker who rewrites both the
receipt and installed files is outside this integrity check's guarantee.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import threading
import time
from typing import Any, Dict, Optional
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

from core.tool_workbench.contracts import AcquisitionPolicy, ToolManifest
from core.tool_workbench.errors import (CancellationError, CorruptedArchiveError,
    DigestMismatchError, DownloadError, SecurityViolationError)

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DIGEST = re.compile(r"[a-fA-F0-9]{64}\Z")
_RECEIPT = "tool_receipt.json"
_CHUNK = 64 * 1024


def get_default_managed_dir() -> Path:
    root = os.environ.get("QUARTZ_MANAGED_TOOLS_ROOT")
    return Path(root) if root else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Quartz" / "tools" / "workbench"


def _no_links(path: Path) -> Path:
    """Inspect lexical components before resolve (including Windows junctions)."""
    absolute = Path(os.path.abspath(path))
    for component in (absolute, *absolute.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SecurityViolationError("Links/reparse points are prohibited in managed tool paths")
    return absolute


def _relative(value: str) -> Path:
    if not isinstance(value, str) or not value or len(value) > 1024 or "\x00" in value:
        raise SecurityViolationError("Invalid package path")
    text = value.replace("\\", "/")
    pure = PurePosixPath(text)
    if pure.is_absolute() or PureWindowsPath(value).is_absolute() or PureWindowsPath(value).drive:
        raise SecurityViolationError("Absolute path in tool package")
    if any(part in {"", ".", ".."} or ":" in part or part.rstrip(" .") != part
           or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
           for part in text.rstrip("/").split("/")):
        raise SecurityViolationError("Malicious package path detected (traversal or reserved name)")
    return Path(*pure.parts)


def manifest_fingerprint(manifest: ToolManifest) -> str:
    try:
        body = json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SecurityViolationError("Invalid tool manifest") from exc
    if len(body) > 128 * 1024:
        raise SecurityViolationError("Tool manifest exceeds size limit")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _source_allowed(url: str, allowed) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password or parsed.fragment or parsed.scheme not in {"http", "https"}:
            return False
        if not parsed.hostname:
            return False
        port = parsed.port
        for prefix in allowed:
            if not isinstance(prefix, str):
                continue
            candidate = urllib.parse.urlsplit(prefix)
            if candidate.scheme != parsed.scheme or candidate.hostname != parsed.hostname:
                continue
            try:
                wanted_port = candidate.port
            except ValueError:
                wanted_port = None
            if (wanted_port or (443 if candidate.scheme == 'https' else 80)) != (port or (443 if parsed.scheme == 'https' else 80)):
                continue
            if parsed.path.startswith(candidate.path):
                return True
    except (TypeError, ValueError):
        return False
    return False


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed, original):
        self.allowed = allowed
        self.github = urllib.parse.urlsplit(original).hostname == "github.com"

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        official_asset = (self.github and parsed.scheme == "https" and
                          parsed.hostname == "release-assets.githubusercontent.com" and
                          not parsed.username and not parsed.password and parsed.port in {None, 443})
        if not _source_allowed(newurl, self.allowed) and not official_asset:
            raise SecurityViolationError("Untrusted tool redirect rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ToolAcquirer:
    MAX_ACQUIRE_SECONDS = 120.0
    MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
    MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
    MAX_ENTRIES = 10000

    def __init__(self, base_managed_dir: Optional[Path] = None):
        self._base_dir = _no_links(Path(base_managed_dir or get_default_managed_dir()))
        self._lock = threading.RLock()
        self._closed = False
        self._active = {}
        self._cleanup_errors = 0

    @property
    def base_dir(self):
        return self._base_dir

    def _paths(self, manifest, policy):
        for value in (manifest.tool_id, manifest.pinned_revision):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) or value in {".", ".."}:
                raise SecurityViolationError("Invalid tool/revision identifier")
        executable = _relative(manifest.executable_subpath)
        root = _no_links(Path(policy.managed_dir or self._base_dir))
        if root != self._base_dir:
            raise SecurityViolationError("Acquisition policy cannot change configured managed root")
        target = _no_links(root / manifest.tool_id / manifest.pinned_revision)
        target.relative_to(root)
        _no_links(target / executable)
        return root, target

    def _check(self, own_event, caller_event, deadline):
        if own_event.is_set() or (caller_event is not None and caller_event.is_set()):
            raise CancellationError("Tool acquisition cancelled")
        if time.monotonic() >= deadline:
            raise CancellationError("Tool acquisition deadline exceeded")

    def _inventory(self, folder, check=lambda: None):
        folder = _no_links(folder)
        result = {}
        total = 0
        for current, directories, files in os.walk(folder, followlinks=False):
            check()
            for directory in directories:
                _no_links(Path(current) / directory)
            for name in files:
                path = _no_links(Path(current) / name)
                relative = path.relative_to(folder).as_posix()
                if relative == _RECEIPT:
                    continue
                if len(result) >= self.MAX_ENTRIES or not path.is_file():
                    raise SecurityViolationError("Invalid or excessive installed files")
                size = path.stat().st_size
                total += size
                if total > self.MAX_UNCOMPRESSED_BYTES:
                    raise SecurityViolationError("Installed package exceeds size limit")
                hasher = hashlib.sha256()
                observed = 0
                with path.open("rb") as stream:
                    while True:
                        check()
                        block = stream.read(_CHUNK)
                        if not block:
                            break
                        observed += len(block)
                        if observed > size:
                            raise SecurityViolationError("Installed file changed during verification")
                        hasher.update(block)
                if observed != size:
                    raise SecurityViolationError("Installed file changed during verification")
                result[relative] = {"sha256": hasher.hexdigest(), "bytes": size}
        return result

    def _verify_existing_installation(self, install_dir, manifest, cancel_event=None, check=None):
        try:
            expected = self._base_dir / manifest.tool_id / manifest.pinned_revision
            self._paths(manifest, AcquisitionPolicy(managed_dir=str(self._base_dir)))
            if _no_links(Path(install_dir)) != expected:
                return None
            receipt = _no_links(expected / _RECEIPT)
            if not receipt.is_file() or receipt.stat().st_size > 2 * 1024 * 1024:
                return None
            data = json.loads(receipt.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("manifest_fingerprint") != manifest_fingerprint(manifest):
                return None
            if data.get("package_digest") != manifest.package_digest.lower():
                return None
            verification_deadline = time.monotonic() + 30
            check = check or (lambda: self._check(threading.Event(), cancel_event, verification_deadline))
            actual = self._inventory(expected, check)
            if not actual or actual != data.get("files"):
                return None
            exe = _no_links(expected / _relative(manifest.executable_subpath))
            if not exe.is_file() or exe.relative_to(expected).as_posix() not in actual:
                return None
            return {"status": "cached", "tool_id": manifest.tool_id, "version": manifest.version,
                    "pinned_revision": manifest.pinned_revision, "package_digest": manifest.package_digest.lower(),
                    "manifest_fingerprint": data["manifest_fingerprint"], "files": actual,
                    "install_dir": str(expected), "executable_path": str(exe),
                    "acquired_at": data.get("acquired_at"), "receipt_file": str(receipt)}
        except (OSError, ValueError, TypeError, KeyError, SecurityViolationError):
            return None

    def validate_installation(self, manifest, receipt_or_dir, cancel_event=None):
        folder = receipt_or_dir.get("install_dir") if isinstance(receipt_or_dir, dict) else receipt_or_dir
        found = self._verify_existing_installation(Path(folder), manifest, cancel_event)
        if found is None:
            raise SecurityViolationError("Managed tool installation integrity check failed")
        return found

    @contextmanager
    def _publication(self, root, manifest, check):
        # OS-held lock is shared by separate ToolAcquirer instances/processes.
        lock = _no_links(root / (".acquire-" + manifest.tool_id + "-" + manifest.pinned_revision + ".lock"))
        with lock.open("a+b") as stream:
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0"); stream.flush()
            while True:
                check()
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    time.sleep(.03)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def acquire(self, manifest, policy=None, cancel_event=None, deadline_monotonic=None):
        pol = policy or AcquisitionPolicy(managed_dir=str(self._base_dir))
        root, target = self._paths(manifest, pol)  # Validate before any mutation.
        if not isinstance(manifest.source_url, str) or not isinstance(pol.allowed_sources, (list, tuple)) or len(pol.allowed_sources) > 32:
            raise SecurityViolationError("Invalid source policy")
        source = manifest.source_url.strip()
        if not _source_allowed(source, pol.allowed_sources):
            raise SecurityViolationError("Untrusted tool source URL rejected")
        if not pol.verify_digest or not isinstance(manifest.package_digest, str) or not _DIGEST.fullmatch(manifest.package_digest):
            raise SecurityViolationError("Pinned SHA-256 digest verification is mandatory")
        for value, ceiling in ((pol.max_download_bytes, self.MAX_DOWNLOAD_BYTES),
                               (pol.max_uncompressed_bytes, self.MAX_UNCOMPRESSED_BYTES),
                               (pol.max_archive_entries, self.MAX_ENTRIES)):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= ceiling:
                raise SecurityViolationError("Invalid acquisition resource limit")
        now = time.monotonic()
        deadline = deadline_monotonic if deadline_monotonic is not None else now + self.MAX_ACQUIRE_SECONDS
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
            raise SecurityViolationError("Invalid acquisition deadline")
        deadline = min(deadline, now + self.MAX_ACQUIRE_SECONDS)
        own = threading.Event()
        token = uuid.uuid4().hex
        with self._lock:
            if self._closed:
                raise CancellationError("Tool acquirer is closed")
            self._check(own, cancel_event, deadline)
            self._active[token] = own
        check = lambda: self._check(own, cancel_event, deadline)
        staging = None
        try:
            cached = self._verify_existing_installation(target, manifest, cancel_event=own, check=check)
            check()
            if cached:
                return cached
            if not pol.allow_network:
                raise DownloadError("Network download is prohibited by acquisition policy")
            root.mkdir(parents=True, exist_ok=True)
            _no_links(root)
            with self._publication(root, manifest, check):
                check()
                cached = self._verify_existing_installation(target, manifest, cancel_event=own, check=check)
                if cached:
                    return cached
                staging = root / (".staging_" + token)
                staging.mkdir()
                archive = staging / "download.pkg"
                request = urllib.request.Request(source, headers={"User-Agent": "Quartz-Workbench/1.0"})
                opener = urllib.request.build_opener(_CheckedRedirect(pol.allowed_sources, source))
                hasher = hashlib.sha256()
                total = 0
                try:
                    with opener.open(request, timeout=min(5.0, max(.1, deadline - time.monotonic()))) as response, archive.open("wb") as output:
                        # Validate final URL too, including unusual opener implementations.
                        final_url = response.geturl()
                        final = urllib.parse.urlsplit(final_url)
                        asset = (urllib.parse.urlsplit(source).hostname == "github.com" and final.scheme == "https"
                                 and final.hostname == "release-assets.githubusercontent.com" and final.port in {None,443}
                                 and not final.username and not final.password and not final.fragment)
                        if not _source_allowed(final_url, pol.allowed_sources) and not asset:
                            raise SecurityViolationError("Untrusted tool redirect rejected")
                        while True:
                            check()
                            block = response.read(_CHUNK)
                            if not block:
                                break
                            total += len(block)
                            if total > pol.max_download_bytes:
                                raise SecurityViolationError("Download exceeded size limit")
                            hasher.update(block); output.write(block)
                except (urllib.error.URLError, TimeoutError) as exc:
                    raise DownloadError("Tool package download failed") from exc
                check()
                computed = hasher.hexdigest()
                if computed != manifest.package_digest.lower():
                    raise DigestMismatchError("Cryptographic digest mismatch for managed tool")
                extracted = staging / "extracted"
                extracted.mkdir()
                self._safe_extract_zip(archive, extracted, pol, cancel_event=own, check=check)
                exe = _no_links(extracted / _relative(manifest.executable_subpath))
                if not exe.is_file():
                    raise CorruptedArchiveError("Executable not found in verified package")
                files = self._inventory(extracted, check)
                now_ts = time.time()
                data = {"schema_version": 1, "tool_id": manifest.tool_id, "pinned_revision": manifest.pinned_revision,
                        "package_digest": computed, "manifest_fingerprint": manifest_fingerprint(manifest),
                        "manifest": manifest.to_dict(), "files": files, "acquired_at": now_ts,
                        "managed_by": "Quartz-ToolWorkbench"}
                (extracted / _RECEIPT).write_text(json.dumps(data, sort_keys=True, allow_nan=False), encoding="utf-8")
                with self._lock:
                    check()  # Same fence as stop/close; no later publication after cancellation.
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _no_links(target.parent)
                    displaced = None
                    if target.exists():
                        _no_links(target)
                        displaced = staging / "previous"
                        target.rename(displaced)
                    try:
                        os.replace(extracted, target)
                    except BaseException:
                        if displaced is not None:
                            displaced.rename(target)
                        raise
                result = self._verify_existing_installation(target, manifest, cancel_event=own, check=check)
                check()
                if result is None:
                    raise SecurityViolationError("Published package verification failed")
                result["status"] = "acquired"
                return result
        finally:
            try:
                if staging is not None and staging.exists():
                    _no_links(staging)
                    shutil.rmtree(staging)
            except Exception:
                with self._lock:
                    self._cleanup_errors += 1
                raise
            finally:
                with self._lock:
                    self._active.pop(token, None)

    def stop(self):
        with self._lock:
            for event in self._active.values():
                event.set()
            pending = len(self._active)
            errors = self._cleanup_errors
        return {"status": "pending" if pending else ("failed" if errors else "confirmed"),
                "active_acquisitions": pending, "cleanup_errors": errors, "all_exited": pending == 0}

    def close(self):
        with self._lock:
            self._closed = True
            return self.stop()

    def _safe_extract_zip(self, archive_path, dest_dir, policy, cancel_event=None, check=None):
        check = check or (lambda: self._check(threading.Event(), cancel_event, float("inf")))
        root = _no_links(dest_dir)
        names = set()
        total = 0
        try:
            with zipfile.ZipFile(archive_path) as archive:
                entries = archive.infolist()
                if len(entries) > policy.max_archive_entries:
                    raise SecurityViolationError("Too many archive entries")
                for member in entries:
                    check()
                    relative = _relative(member.filename)
                    key = relative.as_posix().casefold()
                    if key in names or key == _RECEIPT:
                        raise SecurityViolationError("Duplicate or reserved archive member")
                    names.add(key)
                    mode = (member.external_attr >> 16) & 0o170000
                    if mode == stat.S_IFLNK:
                        raise SecurityViolationError("Symlinks prohibited in tool archives")
                    if mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
                        raise SecurityViolationError("Special archive member prohibited")
                    total += member.file_size
                    if total > policy.max_uncompressed_bytes:
                        raise SecurityViolationError("Uncompressed archive size exceeded safe limit")
                    target = _no_links(root / relative)
                    target.relative_to(root)
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    actual = 0
                    with archive.open(member) as source, target.open("xb") as output:
                        while True:
                            check()
                            block = source.read(_CHUNK)
                            if not block:
                                break
                            actual += len(block)
                            if actual > member.file_size:
                                raise SecurityViolationError("Archive size mismatch")
                            output.write(block)
                    if actual != member.file_size:
                        raise CorruptedArchiveError("Truncated archive member")
        except zipfile.BadZipFile as exc:
            raise CorruptedArchiveError("Archive is corrupted or invalid zip") from exc
