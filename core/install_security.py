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


def verify_publisher(path, publisher):
    """Authenticode is required; never unblock files or alter execution policy."""
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    env = os.environ.copy()
    env["QUARTZ_VERIFY_FILE"] = str(Path(path).resolve(strict=True))
    env["PSModulePath"] = str(shell.parent / "Modules")
    script = ("$ErrorActionPreference='Stop'; "
              "$s=Get-AuthenticodeSignature -LiteralPath $env:QUARTZ_VERIFY_FILE; "
              "@{status=[string]$s.Status; subject=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress")
    result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
                            env=env, capture_output=True, text=True, timeout=45,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        data = {}
    # Exact organization field, not an arbitrary substring of a certificate name.
    fields = [field.strip() for field in str(data.get("subject", "")).split(",")]
    if result.returncode or data.get("status") != "Valid" or "O=" + publisher not in fields:
        raise ValueError("İndirilen dosyanın yayıncı imzası doğrulanamadı")
    return {"status": "Valid", "publisher": publisher}
