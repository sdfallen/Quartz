"""Private, reversible CLI installation. No Desktop app or global PATH required."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import tempfile
import urllib.request
import uuid
import zipfile
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json

PACKAGES = {"codex": "@openai/codex", "gemini": "@google/gemini-cli"}
_LOCK = threading.Lock()


def managed_root():
    return Path(os.environ.get("QUARTZ_CLI_ROOT") or Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Quartz" / "bin")


def app_root():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def package_entry(prefix, provider):
    package = Path(prefix) / "node_modules" / PACKAGES[provider]
    metadata = json.loads((package / "package.json").read_text(encoding="utf-8"))
    if metadata.get("name") != PACKAGES[provider]:
        raise ValueError("CLI paket kimliği uyuşmuyor")
    entry = metadata.get("bin")
    relative = entry.get(provider) if isinstance(entry, dict) else entry
    if not isinstance(relative, str):
        raise ValueError("CLI giriş tanımı bulunamadı")
    resolved = (package / relative).resolve()
    if package.resolve() not in resolved.parents or not resolved.is_file():
        raise ValueError("CLI giriş yolu geçersiz")
    return resolved


def resolve_cli(provider, explicit=None, *, root=None):
    if provider not in {*PACKAGES, "agy"}:
        raise ValueError("Bilinmeyen CLI")
    env_name = {"codex": "QUARTZ_CODEX_PATH", "gemini": "QUARTZ_GEMINI_PATH", "agy": "QUARTZ_ANTIGRAVITY_PATH"}[provider]
    candidates = [explicit, os.getenv(env_name)]
    managed = Path(root) if root else managed_root()
    manifest = load_json(managed / "installed.json", {})
    candidates += [manifest.get(provider, {}).get("executable")]
    for folder in (app_root() / "bin", managed):
        candidates += [folder / (provider + suffix) for suffix in (".exe", ".cmd", "")]
    candidates.append(shutil.which(provider + ".exe"))
    if provider == "agy" and os.getenv("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "agy/bin/agy.exe")
    # Optional existing CLI cache: preserve prior logins when Quartz is launched
    # from an IDE/Explorer with a different PATH. Never require/install Desktop.
    if provider == "codex" and os.getenv("LOCALAPPDATA"):
        cache = Path(os.environ["LOCALAPPDATA"]) / "OpenAI/Codex/bin"
        try:
            candidates += sorted(cache.glob("*/codex.exe"), key=lambda p:p.stat().st_mtime, reverse=True)
        except OSError:
            pass
    candidates += [shutil.which(provider + suffix) for suffix in (".cmd", "")]
    for value in candidates:
        if value and Path(value).is_file():
            return str(Path(value).resolve())
    raise FileNotFoundError(f"{provider} CLI henüz kurulu değil")


def node_command(executable, args=()):
    path = Path(executable).resolve(strict=False)
    if path.suffix.lower() in {".js", ".mjs", ".cjs"}:
        node = next((parent / "node/node.exe" for parent in path.resolve().parents if (parent / "node/node.exe").is_file()), managed_root() / "node/node.exe")
        manifest = load_json(managed_root() / "installed.json", {})
        recorded = next((v.get("node") for v in manifest.values() if v.get("executable") == str(path)), None)
        candidate = str(node) if node.is_file() else recorded if recorded and Path(recorded).is_file() else shutil.which("node")
        if not candidate:
            raise FileNotFoundError("Node çalışma zamanı bulunamadı")
        return [str(Path(candidate).resolve(strict=False)), str(path), *args]
    if path.suffix.lower() == ".cmd":
        package = "codex" if path.stem == "codex" else "gemini"
        try:
            return node_command(package_entry(path.parent, package), args)
        except (OSError, ValueError):
            pass
        # Unknown wrappers are not executed through a shell with model text.
        raise RuntimeError("CLI sarmalayıcısı tanınmadı; Quartz içinden yeniden kurun")
    return [str(path), *args]


def cli_environment():
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(managed_root() / "node"), str(managed_root()), env.get("PATH", "")])
    # Read only Quartz's config, regardless of the task's working directory.
    from dotenv import dotenv_values
    values = dotenv_values(app_root() / ".env")
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        if values.get(name):
            env[name] = values[name]
    return env


class CliInstaller:
    def __init__(self, root=None, fetch=None, run=None):
        self.root = Path(root) if root else managed_root()
        self.fetch = fetch or self._fetch
        self.run = run or subprocess.run

    @staticmethod
    def _fetch(url, limit=150 * 1024 * 1024):
        if not url.startswith(("https://nodejs.org/", "https://registry.npmjs.org/")):
            raise ValueError("Kurulum kaynağı izinli değil")
        with urllib.request.urlopen(url, timeout=60) as response:
            if not response.geturl().startswith(("https://nodejs.org/", "https://registry.npmjs.org/")):
                raise ValueError("Kurulum yönlendirmesi izinli değil")
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("İndirme boyutu sınırı aşıldı")
        return data

    def status(self):
        result = {}
        for provider in PACKAGES:
            try:
                result[provider] = {"installed": True, "executable": resolve_cli(provider, root=self.root)}
            except FileNotFoundError:
                result[provider] = {"installed": False, "executable": None}
        return result

    def _node(self, prefer_private=False):
        local = self.root / "node" / "node.exe"
        if local.is_file():
            return local, local.parent / "node_modules/npm/bin/npm-cli.js"
        existing = shutil.which("node")
        if existing and not prefer_private:
            npm = Path(existing).parent / "node_modules/npm/bin/npm-cli.js"
            version = self.run([existing, "--version"], capture_output=True, text=True, timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            match = re.match(r"v(\d+)", version.stdout)
            if npm.is_file() and version.returncode == 0 and match and int(match[1]) >= 22:
                return Path(existing), npm
        if platform.system() != "Windows":
            raise RuntimeError("Bu otomatik taşınabilir kurulum Windows içindir")
        machine = platform.machine().lower()
        arch = "arm64" if machine in {"arm64", "aarch64"} else "x64" if machine in {"amd64", "x86_64"} else None
        if not arch:
            raise RuntimeError("Bu Windows işlemci mimarisi desteklenmiyor")
        releases = json.loads(self.fetch("https://nodejs.org/dist/index.json"))
        release = next(r for r in releases if r.get("lts") and f"win-{arch}-zip" in r.get("files", []))
        version = release["version"]
        if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
            raise ValueError("Geçersiz Node sürümü")
        filename = f"node-{version}-win-{arch}.zip"
        base = f"https://nodejs.org/dist/{version}/"
        sums = self.fetch(base + "SHASUMS256.txt").decode()
        expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == filename)
        data = self.fetch(base + filename)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Node indirmesi SHA256 doğrulamasını geçemedi")
        import io
        staging = self.root / ("node-stage-" + uuid.uuid4().hex)
        staging.mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                target = (staging / entry.filename).resolve()
                if staging.resolve() not in target.parents or entry.file_size > 200 * 1024 * 1024:
                    raise ValueError("Güvensiz Node arşivi")
            archive.extractall(staging)
        folder = staging / filename[:-4]
        if not (folder / "node.exe").is_file():
            raise RuntimeError("Node paketi eksik")
        folder.rename(self.root / "node")
        return local, local.parent / "node_modules/npm/bin/npm-cli.js"

    def install(self, provider):
        if provider == "agy":
            return self._install_agy()
        if provider not in PACKAGES:
            raise ValueError("Bilinmeyen CLI")
        with _LOCK:
            try:
                existing_exe = resolve_cli(provider, root=self.root)
                probe_cmd = node_command(existing_exe, ["--version"])
                probe = self.run(
                    probe_cmd,
                    env=cli_environment(),
                    capture_output=True,
                    text=True,
                    timeout=15,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if getattr(probe, "returncode", 1) == 0:
                    return {
                        "installed": True,
                        "executable": existing_exe,
                        "version": getattr(probe, "stdout", "").strip(),
                        "reused": True,
                    }
            except (FileNotFoundError, RuntimeError, ValueError, OSError, subprocess.SubprocessError):
                pass
            self.root.mkdir(parents=True, exist_ok=True)
            node, npm = self._node()
            package = PACKAGES[provider]
            metadata = json.loads(self.fetch("https://registry.npmjs.org/" + package.replace("/", "%2f") + "/latest"))
            version = metadata["version"]
            if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
                raise ValueError("Geçersiz CLI sürümü")
            prefix = self.root / "packages" / (provider + "-" + version + "-" + uuid.uuid4().hex[:8])
            env = cli_environment()
            env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
            result = self.run([str(node), str(npm), "install", "--prefix", str(prefix),
                               "--registry=https://registry.npmjs.org", "--ignore-scripts", "--no-audit", "--no-fund", package + "@" + version],
                              env=env, capture_output=True, text=True, timeout=600,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError("CLI kurulumu tamamlanamadı. Ağ bağlantısını kontrol edip yeniden deneyin.")
            executable = package_entry(prefix, provider)
            if not executable.is_file():
                raise RuntimeError("Kurulan CLI giriş dosyası bulunamadı")
            check = self.run([str(node), str(executable), "--version"], env=env, capture_output=True, text=True, timeout=30,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if check.returncode:
                raise RuntimeError("CLI kuruldu ancak başlangıç doğrulaması başarısız")
            manifest = load_json(self.root / "installed.json", {})
            manifest[provider] = {"executable": str(executable), "version": version, "node": str(node)}
            atomic_write_json(self.root / "installed.json", manifest)
            return {"installed": True, **manifest[provider], "reused": False}

    def _install_agy(self):
        """Use Google's manifest contract, without running downloaded shell scripts.

        Private versioned install, SHA512 + Google Authenticode + --version gate.
        No global PATH, IDE, registry writes or automatic account sign-in.
        """
        from core.install_security import download, verify_publisher
        if platform.system() != "Windows":
            raise RuntimeError("Antigravity otomatik kurulumu Windows içindir")
        arch = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower())
        if not arch:
            raise RuntimeError("Bu Windows işlemci mimarisi desteklenmiyor")
        with _LOCK:
            try:
                existing = resolve_cli("agy", root=self.root)
                check = self.run([existing, "--version"], capture_output=True, text=True, timeout=30,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if check.returncode == 0:
                    return {"installed": True, "executable": existing, "version": check.stdout.strip(), "reused": True}
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            self.root.mkdir(parents=True, exist_ok=True)
            host = "antigravity-cli-auto-updater-974169037036.us-central1.run.app"
            with tempfile.TemporaryDirectory(prefix="agy-stage-", dir=self.root) as temporary:
                stage = Path(temporary)
                manifest_file = download(f"https://{host}/manifests/windows_{arch}.json", stage / "release.json",
                                         allowed=[(host, "/manifests/")], limit=1024 * 1024)
                release = json.loads(manifest_file.read_text(encoding="utf-8"))
                version = str(release.get("version", ""))
                checksum = str(release.get("sha512", "")).lower()
                if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version) or not re.fullmatch(r"[a-f0-9]{128}", checksum):
                    raise ValueError("Antigravity sürüm manifesti geçersiz")
                binary = download(release["url"], stage / "agy.exe", limit=350 * 1024 * 1024,
                                  allowed=[("storage.googleapis.com", "/antigravity-public/antigravity-cli/")])
                with binary.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha512").hexdigest()
                if actual != checksum:
                    raise ValueError("Antigravity SHA512 doğrulaması başarısız")
                signature = verify_publisher(binary, "Google LLC")
                check = self.run([str(binary), "--version"], capture_output=True, text=True, timeout=30,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if check.returncode or version not in check.stdout:
                    raise RuntimeError("Antigravity kuruldu ancak sürüm doğrulaması başarısız")
                # Keep prior binaries intact; only publish the manifest after all gates.
                target = self.root / "packages" / ("agy-" + version + "-" + uuid.uuid4().hex[:8]) / "agy.exe"
                target.parent.mkdir(parents=True)
                binary.replace(target)
                entry = {"executable": str(target), "version": version, "sha512": checksum,
                         "signature": signature, "source": release["url"]}
                manifest = load_json(self.root / "installed.json", {})
                manifest["agy"] = entry
                atomic_write_json(self.root / "installed.json", manifest)
                return {"installed": True, **entry, "reused": False}
