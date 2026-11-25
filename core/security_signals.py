"""Signals Eos reads before deciding (see core.security_manifest).

Signature: Windows' own Authenticode check (`Get-AuthenticodeSignature`), which also covers
catalog-signed system files such as DismHost.exe, wherever they were copied. Measured on the
user's machine (25 Nov): 8 files in 1.5 s, one in 0.6 s. Paths go to the helper as JSON in an
environment variable, never inside the command text; the command is plain (never
-EncodedCommand, which Eos itself reports). Results are cached by path, size and modification
time, so a program that starts again costs nothing.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
from pathlib import Path

SIGNATURE_TIMEOUT = 25
_MS_SUBJECT = re.compile(r"(^|,\s*)O=Microsoft Corporation(,|$)", re.I)
_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$paths = ConvertFrom-Json $env:SPES_SIGNATURE_PATHS;"
    "$out = foreach ($p in $paths) {"
    "  $s = Get-AuthenticodeSignature -LiteralPath $p;"
    "  [pscustomobject]@{path=[string]$p; status=[string]$s.Status;"
    "    subject=[string]$s.SignerCertificate.Subject} };"
    "ConvertTo-Json -Compress -Depth 3 @($out)"
)


def verdict_from(status: str, subject: str, exists: bool) -> str:
    """Map Windows' answer to the manifest's signature words."""
    if not exists:
        return "missing"
    status = (status or "").strip()
    if status == "Valid":
        return "microsoft" if _MS_SUBJECT.search(subject or "") else "signed"
    if status == "NotSigned":
        return "unsigned"
    if status in ("HashMismatch", "NotTrusted", "Incompatible"):
        return "invalid"
    return "unknown"  # UnknownError, timeouts, empty answers


def publisher(subject: str) -> str:
    match = re.search(r"(?:^|,\s*)O=([^,]+)", subject or "") or re.search(r"(?:^|,\s*)CN=([^,]+)", subject or "")
    return match.group(1).strip().strip('"') if match else ""


class SignatureChecker:
    """`check(paths) -> {path: {"verdict", "publisher"}}`, batched and cached."""

    def __init__(self, run=subprocess.run):
        self._run = run
        self._cache: dict[tuple, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(path):
        try:
            stat = os.stat(path)
            return (os.path.normcase(str(path)), stat.st_size, stat.st_mtime_ns)
        except OSError:
            return None

    def check(self, paths) -> dict:
        result, pending = {}, {}
        for path in dict.fromkeys(str(p) for p in paths if p):
            key = self._key(path)
            if key is None:
                result[path] = {"verdict": "missing", "publisher": ""}
                continue
            with self._lock:
                cached = self._cache.get(key)
            if cached:
                result[path] = cached
            else:
                pending[path] = key
        if pending:
            answers = self._ask(list(pending))
            for path, key in pending.items():
                status, subject = answers.get(path, ("", ""))
                entry = {"verdict": verdict_from(status, subject, Path(path).exists()), "publisher": publisher(subject)}
                result[path] = entry
                if entry["verdict"] != "unknown":
                    with self._lock:
                        if len(self._cache) > 4000:
                            self._cache.clear()
                        self._cache[key] = entry
        return result

    def _ask(self, paths) -> dict:
        try:
            done = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                             env=dict(os.environ, SPES_SIGNATURE_PATHS=json.dumps(paths)),
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=SIGNATURE_TIMEOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            rows = json.loads(done.stdout or "[]")
        except (OSError, subprocess.SubprocessError, ValueError):
            return {}
        rows = rows if isinstance(rows, list) else [rows]
        return {str(r.get("path")): (str(r.get("status") or ""), str(r.get("subject") or ""))
                for r in rows if isinstance(r, dict)}


_EXE = re.compile(r"\.(exe|com|scr|bat|cmd|ps1|vbs|js|msi|dll|lnk)$", re.I)


def command_target(command: str) -> str:
    """The program an autostart command runs: the quoted first part, or the longest leading
    part that ends in an executable extension ('C:\\Program Files\\x\\y.exe --flag')."""
    text = (command or "").strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        return text[1:end] if end > 0 else text[1:]
    parts = text.split(" ")
    for n in range(len(parts), 0, -1):
        candidate = " ".join(parts[:n])
        if _EXE.search(candidate):
            return candidate
    try:
        return shlex.split(text, posix=False)[0] if text else ""
    except ValueError:
        return parts[0] if parts else ""


def parent_name(pid) -> str:
    try:
        import psutil
        parent = psutil.Process(int(pid)).parent()
        return parent.name() if parent else ""
    except Exception:
        return ""
