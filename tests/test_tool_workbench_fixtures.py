"""
tests/test_tool_workbench_fixtures.py
Test fixtures and archive generators for Tool Workbench test suites:
- Valid test archives
- Zip-Slip path traversal attack archives
- Corrupted / truncated archives
- Symlink archive attacks
- Digest-mismatched archives
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import tempfile
import zipfile


def create_valid_tool_archive(
    executable_subpath: str = "tool/tool.bat",
    script_content: str = "@echo off\r\necho TEST_TOOL_SUCCESS\r\n",
) -> tuple[bytes, str]:
    """Create a valid in-memory zip archive and return (archive_bytes, sha256_hex)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(executable_subpath, script_content)
        zf.writestr("README.txt", "Test tool package")
    data = buf.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    return data, digest


def create_zip_slip_archive(
    slip_path: str = "../../escaped_malicious.exe",
    content: str = "malicious payload",
) -> tuple[bytes, str]:
    """Create an archive containing a Zip-Slip traversal member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("normal.txt", "normal content")
        zf.writestr(slip_path, content)
    data = buf.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    return data, digest


def create_absolute_path_archive(
    abs_path: str = "C:/Windows/System32/evil.dll",
    content: str = "evil content",
) -> tuple[bytes, str]:
    """Create an archive containing an absolute path member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(abs_path, content)
    data = buf.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    return data, digest


def create_symlink_archive(
    target_path: str = "symlink_entry",
    destination: str = "../../../secret.txt",
) -> tuple[bytes, str]:
    """Create an archive containing a Unix symlink entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zi = zipfile.ZipInfo(target_path)
        # Unix symlink mode: 0o120777
        zi.external_attr = 0o120777 << 16
        zf.writestr(zi, destination)
    data = buf.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    return data, digest


def create_corrupted_archive() -> tuple[bytes, str]:
    """Create a truncated/corrupted zip archive."""
    data = b"PK\x03\x04\x14\x00\x00\x00\x08\x00corrupted_truncated_bytes"
    digest = hashlib.sha256(data).hexdigest()
    return data, digest
