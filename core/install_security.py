"""Bounded official downloads and publisher checks before executing installers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request


def checked_url(url, allowed):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment
            or not any(parsed.hostname == host and parsed.path.startswith(prefix)
                       for host, prefix in allowed)):
        raise ValueError("İndirme adresi resmî izinli kaynakla eşleşmiyor")
    return url


def download(url, destination, *, allowed, limit):
    """Check every redirect before following it; stream large CLI binaries."""
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            checked_url(newurl, allowed)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    checked_url(url, allowed)
    path = Path(destination)
    count = 0
    created = False
    deadline = time.monotonic() + 600
    try:
        with urllib.request.build_opener(Redirect()).open(url, timeout=60) as response:
            checked_url(response.geturl(), allowed)
            with path.open("xb") as stream:
                created = True
                while chunk := response.read(64 * 1024):
                    if time.monotonic() > deadline:
                        raise TimeoutError("İndirme süresi doldu; yeniden deneyin")
                    count += len(chunk)
                    if count > limit:
                        raise ValueError("İndirme boyutu sınırı aşıldı")
                    stream.write(chunk)
        if not count:
            raise ValueError("İndirilen dosya boş")
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise
    return path


def distinguished_name(text: str) -> list:
    """(KEY, value) pairs of a Windows certificate subject, read character by character.

    A comma separates fields only outside quotes and when not escaped; quoted values may hold
    commas and escaped quotes (""). A field without a KEY= part makes the whole subject invalid,
    so nothing half-parsed can grant a publisher."""
    fields, current, quoted, i = [], [], False, 0
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == '"' and i + 1 < len(text) and text[i + 1] == '"':
                current.append('"'); i += 2; continue
            if ch == '"':
                quoted = False
            else:
                current.append(ch)
        elif ch == "\\" and i + 1 < len(text):
            current.append(text[i + 1]); i += 2; continue
        elif ch == '"':
            quoted = True
        elif ch in ",;":
            fields.append("".join(current)); current = []
        else:
            current.append(ch)
        i += 1
    if quoted:
        return []
    fields.append("".join(current))
    pairs = []
    for field in fields:
        if not field.strip():
            continue
        key, sep, value = field.partition("=")
        if not sep or not key.strip().replace(".", "").isalnum():
            return []
        pairs.append((key.strip().upper(), value.strip()))
    return pairs


def verify_publisher(path, publisher):
    """Authenticode is required; never unblock files or alter execution policy."""
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    env = os.environ.copy()
    env["QUARTZ_VERIFY_FILE"] = str(Path(path).resolve(strict=True))
    env["PSModulePath"] = str(shell.parent / "Modules")
    script = ("$ErrorActionPreference='Stop'; "
              "$s=Get-AuthenticodeSignature -LiteralPath $env:QUARTZ_VERIFY_FILE; "
              "@{status=[string]$s.Status; subject=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress")
    # Fides RFS4 (27 Nov): the signature check is a setup step too, so it runs owned (suspended,
    # kill-on-close Job Object): a timeout or SpeS closing ends it. Imported here: cli_installer
    # imports this module only inside its functions, so there is no import cycle.
    from core.cli_installer import owned_run
    result = owned_run([str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
                       env=env, capture_output=True, text=True, timeout=45,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        data = {}
    # Exact organization field, not an arbitrary substring of a certificate name. A value with a
    # comma is quoted by Windows (27 Nov: O="Anthropic, PBC"); text inside another field's quotes
    # (CN="x, O=Google LLC") is never a field (Fides FS5).
    organizations = [value for key, value in distinguished_name(str(data.get("subject", ""))) if key == "O"]
    if result.returncode or data.get("status") != "Valid" or publisher not in organizations:
        raise ValueError("İndirilen dosyanın yayıncı imzası doğrulanamadı")
    return {"status": "Valid", "publisher": publisher}
