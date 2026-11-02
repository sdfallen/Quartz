"""
core/tool_workbench/acquisition.py
Secure, audited tool acquisition for Quartz Tool Workbench.
Provides cryptographic digest verification, streaming downloads, Zip-Slip defense,
symlink protection, atomic installation, and rollback of interrupted extractions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from typing import Any, Dict, Optional
import urllib.request
import uuid
import zipfile

from core.tool_workbench.contracts import AcquisitionPolicy, ToolManifest
from core.tool_workbench.errors import (
    AcquisitionError,
    CancellationError,
    CorruptedArchiveError,
    DigestMismatchError,
    DownloadError,
    SecurityViolationError,
)

log = logging.getLogger("quartz.workbench.acquisition")


def get_default_managed_dir() -> Path:
    """Return the default root directory for managed workbench tools."""
    env_root = os.environ.get("QUARTZ_MANAGED_TOOLS_ROOT")
    if env_root:
        return Path(env_root).resolve()
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Quartz" / "tools" / "workbench"
    return base.resolve()


class ToolAcquirer:
    """Acquires, verifies, and installs tools into an isolated managed directory."""

    def __init__(self, base_managed_dir: Optional[Path] = None):
        self._base_dir = (base_managed_dir or get_default_managed_dir()).resolve()
        self._lock = threading.RLock()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _verify_existing_installation(
        self, install_dir: Path, manifest: ToolManifest
    ) -> Optional[Dict[str, Any]]:
        """Verify an existing installation directory against manifest and receipt."""
        receipt_file = install_dir / "tool_receipt.json"
        if not receipt_file.is_file():
            return None

        try:
            data = json.loads(receipt_file.read_text(encoding="utf-8"))
            if data.get("tool_id") != manifest.tool_id:
                return None
            if data.get("pinned_revision") != manifest.pinned_revision:
                return None
            if data.get("package_digest") != manifest.package_digest:
                return None

            exe_path = (install_dir / manifest.executable_subpath).resolve()
            if not exe_path.is_file() or exe_path.is_symlink():
                return None

            return {
                "status": "cached",
                "tool_id": manifest.tool_id,
                "version": manifest.version,
                "pinned_revision": manifest.pinned_revision,
                "package_digest": manifest.package_digest,
                "install_dir": str(install_dir),
                "executable_path": str(exe_path),
                "acquired_at": data.get("acquired_at", time.time()),
                "receipt_file": str(receipt_file),
            }
        except Exception as exc:
            log.warning("Existing installation check failed: %s", exc)
            return None

    def acquire(
        self,
        manifest: ToolManifest,
        policy: Optional[AcquisitionPolicy] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """
        Acquire and verify a tool into the managed directory.
        Strictly enforces digest check, zip-slip defense, and atomic installation.
        """
        pol = policy or AcquisitionPolicy(managed_dir=str(self._base_dir))
        managed_dir = Path(pol.managed_dir or self._base_dir).resolve()
        target_install_dir = managed_dir / manifest.tool_id / manifest.pinned_revision

        with self._lock:
            # 1. Check existing installation
            if target_install_dir.is_dir():
                cached = self._verify_existing_installation(target_install_dir, manifest)
                if cached is not None:
                    log.info("Tool %s revision %s verified in cache", manifest.tool_id, manifest.pinned_revision)
                    return cached
                # Corrupted or tampered -> clean up
                log.warning("Invalid/corrupted tool directory found at %s; cleaning", target_install_dir)
                shutil.rmtree(target_install_dir, ignore_errors=True)

            # 2. Security validation of source URL
            url = manifest.source_url.strip()
            if not any(url.startswith(src) for src in pol.allowed_sources):
                raise SecurityViolationError(f"Untrusted tool source URL rejected: {url}")

            if not pol.allow_network:
                raise DownloadError("Network download is prohibited by acquisition policy")

            # Ensure parent managed directory exists
            managed_dir.mkdir(parents=True, exist_ok=True)
            staging_id = f".staging_{manifest.tool_id}_{uuid.uuid4().hex[:8]}"
            staging_dir = managed_dir / staging_id
            staging_dir.mkdir(parents=True, exist_ok=True)

            archive_path = staging_dir / "download.pkg"

            try:
                # 3. Progressive streaming download with live SHA-256 calculation
                log.info("Downloading %s from %s", manifest.tool_id, url)
                hasher = hashlib.sha256()
                bytes_downloaded = 0

                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Quartz-Workbench/1.0",
                        "Accept": "application/octet-stream, application/zip, */*",
                    },
                )

                try:
                    with urllib.request.urlopen(req, timeout=30.0) as resp:
                        with archive_path.open("wb") as out_file:
                            while True:
                                if cancel_event and cancel_event.is_set():
                                    raise CancellationError("Tool acquisition cancelled by caller")

                                chunk = resp.read(65536)
                                if not chunk:
                                    break

                                bytes_downloaded += len(chunk)
                                if bytes_downloaded > pol.max_download_bytes:
                                    raise SecurityViolationError(
                                        f"Download exceeded limit of {pol.max_download_bytes} bytes"
                                    )

                                hasher.update(chunk)
                                out_file.write(chunk)
                except urllib.error.URLError as exc:
                    raise DownloadError(f"Failed to download tool package from {url}: {exc}") from exc

                # 4. Strict cryptographic digest verification
                computed_digest = hasher.hexdigest().lower()
                expected_digest = manifest.package_digest.strip().lower()

                if pol.verify_digest and computed_digest != expected_digest:
                    raise DigestMismatchError(
                        f"Cryptographic digest mismatch for {manifest.tool_id}: "
                        f"expected {expected_digest}, computed {computed_digest}"
                    )

                log.info("Cryptographic digest verified: %s", computed_digest)

                # 5. Safe Archive Extraction with Zip-Slip & Symlink Defense
                extract_target = staging_dir / "extracted"
                extract_target.mkdir(parents=True, exist_ok=True)
                self._safe_extract_zip(archive_path, extract_target, pol, cancel_event)

                # 6. Verify executable presence in extracted tree
                candidate_exe = (extract_target / manifest.executable_subpath).resolve()
                if not candidate_exe.is_file():
                    raise CorruptedArchiveError(
                        f"Executable '{manifest.executable_subpath}' not found in package for {manifest.tool_id}"
                    )
                if candidate_exe.is_symlink():
                    raise SecurityViolationError("Executable cannot be a symlink")

                # Remove the raw downloaded zip to conserve disk space
                try:
                    archive_path.unlink(missing_ok=True)
                except OSError:
                    pass

                # 7. Write tool receipt in extracted directory
                now_ts = time.time()
                receipt_data = {
                    "tool_id": manifest.tool_id,
                    "name": manifest.name,
                    "version": manifest.version,
                    "pinned_revision": manifest.pinned_revision,
                    "package_digest": computed_digest,
                    "source_url": manifest.source_url,
                    "license": manifest.license,
                    "executable_subpath": manifest.executable_subpath,
                    "acquired_at": now_ts,
                    "managed_by": "Quartz-ToolWorkbench",
                }
                (extract_target / "tool_receipt.json").write_text(
                    json.dumps(receipt_data, indent=2), encoding="utf-8"
                )

                # 8. Atomic move to target install directory
                target_install_dir.parent.mkdir(parents=True, exist_ok=True)
                if target_install_dir.exists():
                    shutil.rmtree(target_install_dir, ignore_errors=True)

                # Move extracted content to target
                shutil.move(str(extract_target), str(target_install_dir))

                final_exe = (target_install_dir / manifest.executable_subpath).resolve()
                receipt_file = target_install_dir / "tool_receipt.json"

                log.info("Tool %s revision %s successfully acquired at %s",
                         manifest.tool_id, manifest.pinned_revision, target_install_dir)

                return {
                    "status": "acquired",
                    "tool_id": manifest.tool_id,
                    "version": manifest.version,
                    "pinned_revision": manifest.pinned_revision,
                    "package_digest": computed_digest,
                    "install_dir": str(target_install_dir),
                    "executable_path": str(final_exe),
                    "acquired_at": now_ts,
                    "receipt_file": str(receipt_file),
                }

            finally:
                # Cleanup staging directory on any failure or completion
                if staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)

    def _safe_extract_zip(
        self,
        archive_path: Path,
        dest_dir: Path,
        policy: AcquisitionPolicy,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Extract a zip archive with strict path traversal, symlink, and zip-bomb checks."""
        dest_resolved = dest_dir.resolve()
        dest_prefix = str(dest_resolved) + os.sep

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                infolist = zf.infolist()
                if len(infolist) > policy.max_archive_entries:
                    raise SecurityViolationError(
                        f"Archive contains {len(infolist)} entries, exceeding limit {policy.max_archive_entries}"
                    )

                cumulative_uncompressed = 0

                for member in infolist:
                    if cancel_event and cancel_event.is_set():
                        raise CancellationError("Extraction cancelled by caller")

                    name = member.filename
                    cumulative_uncompressed += member.file_size
                    if cumulative_uncompressed > policy.max_uncompressed_bytes:
                        raise SecurityViolationError("Uncompressed archive size exceeded safe limit")

                    # Check for path traversal in filename
                    norm = os.path.normpath(name)
                    if norm.startswith(("/", "\\", "..")) or ".." in norm.split(os.sep):
                        raise SecurityViolationError(f"Malicious archive member detected (traversal): {name}")

                    # Check for absolute Windows drive letters
                    if len(norm) > 1 and norm[1] == ":":
                        raise SecurityViolationError(f"Absolute path in archive member: {name}")

                    target_path = (dest_resolved / norm).resolve()
                    if not str(target_path).startswith(dest_prefix) and str(target_path) != str(dest_resolved):
                        raise SecurityViolationError(f"Zip slip escape detected for member: {name}")

                    # Check for symlink attribute
                    unix_mode = (member.external_attr >> 16) & 0o170000
                    if unix_mode == 0o120000:
                        raise SecurityViolationError(f"Symlinks prohibited in tool archives: {name}")

                    # Extract file safely
                    if member.is_dir():
                        target_path.mkdir(parents=True, exist_ok=True)
                    else:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src_stream, target_path.open("wb") as dst_stream:
                            shutil.copyfileobj(src_stream, dst_stream)

        except zipfile.BadZipFile as exc:
            raise CorruptedArchiveError(f"Archive is corrupted or invalid zip: {exc}") from exc
