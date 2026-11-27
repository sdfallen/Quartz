"""Show what the team built: a loopback static server and a root-bound reader (14 Nov 2026).

The work panel previews a site or an app UI the agents wrote as files. One server per
folder, bound to 127.0.0.1 on a free port, GET/HEAD only, never outside its root, no
directory listings, no hidden or secret-looking files. Stopped when SpeS closes.
"""
from __future__ import annotations

import mimetypes
import os
import threading
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.project_read_mcp import SECRET_NAME

MAX_TEXT_BYTES = 400 * 1024
TEXT_SUFFIXES = {".html", ".htm", ".css", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".py",
                 ".yml", ".yaml", ".toml", ".ini", ".cfg", ".xml", ".svg", ".csv", ".sql", ".sh", ".ps1",
                 ".bat", ".kt", ".java", ".cs", ".go", ".rs", ".c", ".h", ".cpp", ".php", ".rb", ".vue", ".svelte"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}


class PreviewError(ValueError):
    """Not a file SpeS shows."""


def _is_link(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return True
    return path.is_symlink() or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def resolve_inside(root, relative) -> Path:
    """``root/relative`` if it is a visible, non-secret, link-free path strictly inside ``root``."""
    raw_root = Path(root)
    if os.path.lexists(raw_root) and _is_link(raw_root):
        raise PreviewError("Bağlantılar gösterilmez")
    base = raw_root.resolve(strict=True)
    rel = str(relative or "").replace("\\", "/").lstrip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    cur = base
    for part in parts:
        if part == ".." or part.startswith(".") or SECRET_NAME.match(part):
            raise PreviewError("Bu dosya gösterilmez")
        cur = cur / part
        if os.path.lexists(cur) and _is_link(cur):
            raise PreviewError("Bağlantılar gösterilmez")
    target = cur.resolve()
    if target != base and base not in target.parents:
        raise PreviewError("Klasör dışına çıkılamaz")
    rel_parts = target.relative_to(base).parts
    if any(p.startswith(".") or SECRET_NAME.match(p) for p in rel_parts):
        raise PreviewError("Bu dosya gösterilmez")
    if os.path.lexists(target) and _is_link(target):
        raise PreviewError("Bağlantılar gösterilmez")
    return target


def read_for_panel(root, relative) -> dict:
    """``{"kind": "text"|"image"|"binary", ...}`` for the panel; text and images are bounded."""
    target = resolve_inside(root, relative)
    if not target.is_file():
        raise PreviewError("Dosya bulunamadı")
    suffix = target.suffix.lower()
    size = target.stat().st_size
    if suffix in IMAGE_SUFFIXES:
        if size > 8 * 1024 * 1024:
            raise PreviewError("Görsel çok büyük")
        import base64
        mime = mimetypes.guess_type(target.name)[0] or "image/png"
        return {"kind": "image", "name": target.name, "mime": mime, "size": size,
                "data": base64.b64encode(target.read_bytes()).decode("ascii")}
    if suffix in TEXT_SUFFIXES or size < 64 * 1024:
        raw = target.read_bytes()[:MAX_TEXT_BYTES]
        if b"\x00" in raw[:4096] and suffix not in TEXT_SUFFIXES:
            return {"kind": "binary", "name": target.name, "size": size}
        return {"kind": "text", "name": target.name, "size": size, "truncated": size > MAX_TEXT_BYTES,
                "language": suffix.lstrip("."), "text": raw.decode("utf-8", errors="replace")}
    return {"kind": "binary", "name": target.name, "size": size}


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def list_directory(self, path):  # never a listing
        self.send_error(404)
        return None

    def translate_path(self, path):
        clean = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        try:
            target = resolve_inside(self.directory, clean)
        except (PreviewError, OSError):
            return str(Path(self.directory) / "__spes_missing__" / "404")
        if target.is_dir():
            base = Path(self.directory).resolve()
            rel_dir = "" if target == base else target.relative_to(base).as_posix()
            index_rel = f"{rel_dir}/index.html".lstrip("/")
            try:
                index = resolve_inside(self.directory, index_rel)
            except (PreviewError, OSError):
                return str(Path(self.directory) / "__spes_missing__" / "404")
            return str(index) if index.is_file() else str(Path(self.directory) / "__spes_missing__" / "404")
        return str(target)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_POST(self):
        self.send_error(405)

    do_PUT = do_DELETE = do_PATCH = do_POST


class PreviewServers:
    """One loopback server per folder; ``url_for(root)`` starts it on first use."""

    def __init__(self):
        self._lock = threading.Lock()
        self._servers: dict[str, ThreadingHTTPServer] = {}

    def url_for(self, root) -> str:
        base = str(Path(root).resolve(strict=True))
        if not Path(base).is_dir():
            raise PreviewError("Önizlenecek klasör yok")
        with self._lock:
            server = self._servers.get(base.lower())
            if server is None:
                server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, directory=base))
                server.daemon_threads = True
                threading.Thread(target=server.serve_forever, daemon=True, name="spes-preview").start()
                self._servers[base.lower()] = server
            return f"http://127.0.0.1:{server.server_port}/"

    def stop_all(self):
        with self._lock:
            servers, self._servers = list(self._servers.values()), {}
        for server in servers:
            server.shutdown()
            server.server_close()


def best_preview_file(files) -> str | None:
    """Which changed file the panel opens first: a page, then a document, an image, code."""
    names = [str(f).replace("\\", "/") for f in files or []]
    ranked = sorted(names, key=lambda n: (
        0 if n.lower().endswith("index.html") else 1 if n.lower().endswith((".html", ".htm")) else
        2 if n.lower().endswith(".md") else 3 if Path(n).suffix.lower() in IMAGE_SUFFIXES else 4, len(n)))
    return ranked[0] if ranked else None
