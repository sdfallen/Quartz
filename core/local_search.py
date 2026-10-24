"""Private, folder-scoped local document indexing and lexical search."""

import math
import re
import threading
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json
from core.sandbox import PathSandbox


TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".html",
    ".css", ".csv", ".log",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\wçğıöşüÇĞİÖŞÜ]{2,}", text.lower())


class LocalSearchEngine:
    def __init__(self, index_path):
        self.index_path = Path(index_path)
        self._lock = threading.RLock()
        value = load_json(self.index_path, {"roots": [], "chunks": []})
        self._index = value if isinstance(value, dict) else {"roots": [], "chunks": []}

    def index_folder(self, folder: str, *, max_files: int = 1000) -> dict:
        root = Path(folder).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Folder not found: {root}")
        sandbox = PathSandbox([root])
        chunks, files, skipped = [], 0, 0
        for path in root.rglob("*"):
            if files >= max_files:
                break
            if not path.is_file() or any(part.startswith(".") for part in path.parts):
                continue
            try:
                safe_path = sandbox.resolve(path)
                if safe_path.stat().st_size > 2 * 1024 * 1024:
                    skipped += 1
                    continue
                text = self._read(safe_path)
                if not text.strip():
                    continue
                files += 1
                for index, chunk in enumerate(self._chunk(text)):
                    chunks.append({
                        "path": str(safe_path), "chunk": index,
                        "text": chunk, "tokens": _tokens(chunk),
                    })
            except (OSError, UnicodeError, ValueError):
                skipped += 1
        with self._lock:
            self._index = {"roots": [str(root)], "chunks": chunks}
            atomic_write_json(self.index_path, self._index)
        return {"root": str(root), "files": files,
                "chunks": len(chunks), "skipped": skipped}

    def search(self, query: str, *, limit: int = 8) -> list[dict]:
        terms = _tokens(query)
        if not terms:
            return []
        with self._lock:
            chunks = list(self._index.get("chunks", []))
        document_frequency = {
            term: sum(1 for chunk in chunks if term in set(chunk.get("tokens", [])))
            for term in terms
        }
        scored = []
        total = max(1, len(chunks))
        for chunk in chunks:
            tokens = chunk.get("tokens", [])
            if not tokens:
                continue
            score = 0.0
            for term in terms:
                count = tokens.count(term)
                if count:
                    score += (1 + math.log(count)) * math.log(
                        1 + total / max(1, document_frequency[term]))
            if score:
                text = chunk["text"]
                scored.append({
                    "path": chunk["path"], "chunk": chunk["chunk"],
                    "score": round(score, 3), "snippet": text[:500].strip(),
                })
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]

    @staticmethod
    def _chunk(text: str, size: int = 1200, overlap: int = 150):
        text = text.replace("\x00", " ")
        start = 0
        while start < len(text):
            yield text[start:start + size]
            start += max(1, size - overlap)

    @staticmethod
    def _read(path: Path) -> str:
        if path.suffix.lower() in TEXT_EXTENSIONS:
            return path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                return ""
            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        return ""
