"""Official ntn transport. No Desktop IPC, shell, copied token or .env access."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import threading
import urllib.request
import uuid
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json
from core.cli_installer import managed_root

# Official npm package listed in Notion's CLI installation documentation.
# Deliberately pinned; updating this requires reviewing package + checksum.
VERSION = "0.23.25"
INTEGRITY = "eUgMS0qEvLuXcAfrmi+YDXsTO+m9R27r/C0wJeyxYdBnFJWjqbVjuXP9rMgEhIFu6gAQL5f9JfqyelwzhNeh/g=="
API_VERSION = "2026-03-11"
_INSTALL_LOCK = threading.Lock()


def identifier(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Geçerli bir Notion kimliği gerekiyor.") from None


def profile_root():
    return Path(os.environ.get("QUARTZ_NOTION_HOME") or
                Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Quartz" / "notion")


def cli_environment(workspace_id=None):
    env = os.environ.copy()
    for key in tuple(env):
        # No alternate API host, unsafe diagnostics or plaintext keyring inherited
        # from a project shell. Credentials are resolved by official OS keychain.
        if key.upper().startswith("NOTION_") or re.search(r"(?:API_KEY|TOKEN|SECRET|PASSWORD)$", key, re.I):
            env.pop(key, None)
    env["NOTION_ENV"] = "prod"
    # An existing CLI config may contain keyring=false. The environment setting
    # must override that too, rather than merely removing NOTION_KEYRING=0.
    env["NOTION_KEYRING"] = "1"
    env["NOTION_API_BASE_URL"] = "https://api.notion.com"
    env["NOTION_API_DOCS_BASE_URL"] = "https://developers.notion.com"
    if workspace_id:
        env["NOTION_WORKSPACE_ID"] = identifier(workspace_id)
    env["NO_COLOR"] = "1"
    return env


def resolve_ntn(root=None):
    root = Path(root) if root else managed_root()
    for candidate in (os.environ.get("QUARTZ_NTN_PATH"),
                      root / "notion" / VERSION / "ntn.exe", shutil.which("ntn.exe"),
                      shutil.which("ntn")):
        if candidate and Path(candidate).is_file():
            path = Path(candidate).resolve()
            # Never pass model text to a .cmd/.ps1 wrapper or a shell.
            if path.suffix.lower() in {".cmd", ".ps1", ".bat", ".js"}:
                continue
            return str(path)
    raise FileNotFoundError("Notion CLI kurulu değil. Önce Notion bağlantı kurulumunu çalıştırın.")


def install_ntn(root=None, *, fetch=None, run=None):
    """Extract only the native Windows binary. Never execute npm install hooks."""
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Bu Notion CLI paketi yalnız Windows x64 içindir.")
    root = Path(root) if root else managed_root()
    runner = run or subprocess.run
    with _INSTALL_LOCK:
        dest = root / "notion" / VERSION / "ntn.exe"
        if dest.is_file():
            receipt = load_json(dest.parent / "provenance.json", {})
            if receipt.get("sha512") != INTEGRITY or receipt.get("binary_sha256") != hashlib.sha256(dest.read_bytes()).hexdigest():
                raise ValueError("Mevcut Notion CLI kurulumunun bütünlüğü doğrulanamadı.")
            return {"executable": str(dest), "version": VERSION, "reused": True}
        url = f"https://registry.npmjs.org/ntn/-/ntn-{VERSION}.tgz"
        if fetch:
            data = fetch(url)
        else:
            with urllib.request.urlopen(url, timeout=60) as response:
                if response.geturl() != url:
                    raise ValueError("Notion indirme yönlendirmesi beklenmiyor.")
                data = response.read(45 * 1024 * 1024 + 1)
        if len(data) > 45 * 1024 * 1024 or base64.b64encode(hashlib.sha512(data).digest()).decode() != INTEGRITY:
            raise ValueError("Notion CLI SHA512 doğrulaması başarısız.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        stage = dest.with_name("ntn-" + uuid.uuid4().hex + ".exe")
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                member = archive.getmember("package/dist/ntn-win32-x64/ntn.exe")
                if not member.isfile() or not 0 < member.size <= 100 * 1024 * 1024:
                    raise ValueError("Notion CLI arşiv girdisi geçersiz.")
                source = archive.extractfile(member)
                with source, stage.open("wb") as target:
                    shutil.copyfileobj(source, target)
            check = runner([str(stage), "--version"], capture_output=True, text=True,
                           timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if check.returncode != 0 or VERSION not in check.stdout:
                raise RuntimeError("Notion CLI başlangıç doğrulaması başarısız.")
            stage.replace(dest)
            atomic_write_json(dest.parent / "provenance.json", {
                "package": "ntn", "version": VERSION, "source": url,
                "sha512": INTEGRITY, "binary_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            })
        finally:
            stage.unlink(missing_ok=True)
        return {"executable": str(dest), "version": VERSION, "reused": False}


class NotionError(RuntimeError):
    def __init__(self, message, *, code="transport_error", uncertain=False):
        super().__init__(message)
        self.code, self.uncertain = code, uncertain


class NotionCli:
    def __init__(self, workspace_id, *, executable=None, run=None):
        self.workspace_id = identifier(workspace_id)
        self.executable = executable
        self.run = run or subprocess.run

    def environment(self):
        return cli_environment(self.workspace_id)

    def request(self, path, body=None):
        # Transport is intentionally not a generic arbitrary Notion writer.
        if not (path in {"v1/agents/query", "v1/users/me", "v1/sessions"} or
                re.fullmatch(r"v1/sessions/[a-f0-9-]{36}(?:/events/query|/cancel)?", path)):
            raise ValueError("Notion API yolu izinli değil.")
        method = "POST" if body is not None else "GET"
        args = [self.executable or resolve_ntn(), "api", path, "-X", method,
                "--notion-version", API_VERSION, "Accept:application/json"]
        try:
            result = self.run(args, input=json.dumps(body, ensure_ascii=False) if body is not None else "",
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=30, env=self.environment(),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise NotionError("Notion isteği zaman aşımına uğradı; gönderim otomatik tekrarlanmadı.",
                              code="timeout", uncertain=path == "v1/sessions") from None
        except OSError:
            raise NotionError("Notion CLI başlatılamadı. Kurulumu kontrol edin.") from None
        if result.returncode == 4 and "No auth token found" in (result.stderr or ""):
            raise NotionError("Notion oturumu açık değil. Resmî CLI ile giriş yapın.", code="unauthorized")
        try:
            data = json.loads(result.stdout)
        except (ValueError, TypeError):
            # CLI stderr may contain auth URLs, headers or user data: do not expose it.
            raise NotionError("Notion yanıtı okunamadı. CLI girişini ve bağlantıyı kontrol edin.",
                              uncertain=path == "v1/sessions") from None
        if not isinstance(data, dict):
            raise NotionError("Notion yanıt biçimi beklenmiyor.")
        if result.returncode or data.get("object") == "error":
            code = data.get("code")
            messages = {
                "unauthorized": "Notion oturumu açık değil. Resmî CLI ile giriş yapın.",
                "restricted_resource": "Bu Notion ajanına erişim yok. Ajan paylaşımını ve bağlantı yetkisini kontrol edin.",
                "object_not_found": "Notion ajanı veya oturumu bulunamadı; çalışma alanını kontrol edin.",
                "rate_limited": "Notion kullanım sınırına ulaşıldı. İstek otomatik tekrarlanmadı.",
            }
            safe_code = code if code in messages else "api_error"
            raise NotionError(messages.get(code, "Notion isteği başarısız oldu. İstek otomatik tekrarlanmadı."),
                              code=safe_code, uncertain=path == "v1/sessions" and safe_code == "api_error")
        return data

    def agents(self):
        agents, cursor, seen = [], None, set()
        for _ in range(20):
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = self.request("v1/agents/query", body)
            agents.extend(data.get("results", []))
            if not data.get("has_more"):
                return agents
            cursor = data.get("next_cursor")
            if not cursor or cursor in seen:
                break
            seen.add(cursor)
        raise NotionError("Ajan listesi tamamen okunamadı; seçim kaydedilmedi.")
