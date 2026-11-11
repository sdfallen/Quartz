"""Quartz-owned read-only project tools as a stdio MCP server.

The agent gets only list/read/search over one project root. Quartz, not the
agent's shell, enforces the root, hides secret-looking files (in listings,
reads and search results alike), skips binaries and bounds every result. No
tool writes, executes, or reaches the network.
"""
from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import re
import sys

MAX_READ_LINES = 400
MAX_LINE_CHARS = 2000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_LIST = 500
MAX_HITS = 100
MAX_SEARCH_FILES = 20000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache", ".pytest_cache"}
SECRET_NAME = re.compile(r"^(?:\.env(?:\..*)?|.*\.(?:pem|key|pfx|p12|kdbx)|id_(?:rsa|ed25519|ecdsa)(?:\.pub)?|"
                         r"\.ssh|\.codex|\.gemini|\.aws|\.azure|\.git-credentials|\.npmrc|\.pypirc|"
                         r"credentials(?:\.json)?|secrets?(?:\.json|\.toml|\.ya?ml)?|token(?:s)?(?:\.json)?|"
                         r"quartz_(?:memory|conversations|projects)\.json|mobile_access\.json|cli_connections\.json)$", re.I)

TOOLS = [
    {"name": "project_list", "description": "List files and folders in a project folder (relative path, '' for the project root). Secret files are hidden.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "additionalProperties": False}},
    {"name": "project_read", "description": "Read lines of a text file in the project (relative path). Returns at most 400 lines from start_line.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer", "minimum": 1},
                                                      "max_lines": {"type": "integer", "minimum": 1, "maximum": MAX_READ_LINES}},
                     "required": ["path"], "additionalProperties": False}},
    {"name": "project_search", "description": "Search text (case-insensitive, plain text) in project files, optionally under a relative folder and a filename glob like *.py. Returns path:line matches.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "minLength": 2, "maxLength": 200},
                                                      "path": {"type": "string"}, "glob": {"type": "string", "maxLength": 60}},
                     "required": ["query"], "additionalProperties": False}},
]
for _tool in TOOLS:
    _tool["annotations"] = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}


def _is_link(path):
    """Symlink or any Windows reparse point (junction, mount point)."""
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except OSError:
        return True


class ProjectReader:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(str(self.root))

    def _hidden(self, relative_parts):
        return any(SECRET_NAME.match(part) for part in relative_parts)

    def resolve(self, raw):
        text = str(raw or "").strip().replace("\\", "/")
        if text.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", text) or ":" in text:
            raise ValueError("Use a path relative to the project root")
        target = (self.root / text).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise ValueError("Path is outside the project")
        relative = target.relative_to(self.root)
        if self._hidden(relative.parts):
            raise ValueError("This file is protected and not readable here")
        # A link/junction inside the project must not lead outside it.
        probe = self.root
        for part in relative.parts:
            probe = probe / part
            if probe.exists() and _is_link(probe):
                raise ValueError("Linked paths are not followed")
        return target

    def list(self, path=""):
        folder = self.resolve(path)
        if not folder.is_dir():
            raise NotADirectoryError("Not a folder")
        entries = []
        for child in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if SECRET_NAME.match(child.name):
                continue
            entries.append(child.name + ("/" if child.is_dir() else ""))
            if len(entries) >= MAX_LIST:
                entries.append("… (list truncated)")
                break
        return "\n".join(entries) or "(empty folder)"

    def read(self, path, start_line=1, max_lines=MAX_READ_LINES):
        target = self.resolve(path)
        if not target.is_file():
            raise FileNotFoundError("Not a file")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("File is too large to read here")
        data = target.read_bytes()
        if b"\0" in data[:8192]:
            raise ValueError("Binary file")
        lines = data.decode("utf-8", errors="replace").splitlines()
        start = max(1, int(start_line or 1))
        count = max(1, min(int(max_lines or MAX_READ_LINES), MAX_READ_LINES))
        chunk = lines[start - 1:start - 1 + count]
        body = "\n".join(f"{start + i}: {line[:MAX_LINE_CHARS]}" for i, line in enumerate(chunk))
        more = start - 1 + count < len(lines)
        return f"{target.relative_to(self.root).as_posix()} ({len(lines)} lines)\n{body}" + (
            f"\n… continue with start_line={start + count}" if more else "")

    def search(self, query, path="", glob=None):
        needle = str(query or "").strip().lower()
        if len(needle) < 2:
            raise ValueError("Query is too short")
        base = self.resolve(path)
        hits, scanned = [], 0
        for folder, dirs, files in os.walk(base, followlinks=False):
            # os.walk does not treat Windows junctions as links: skip every
            # reparse point explicitly so a search never leaves the project.
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not SECRET_NAME.match(d)
                       and not _is_link(Path(folder) / d)]
            for name in files:
                if SECRET_NAME.match(name) or (glob and not fnmatch.fnmatch(name, glob)):
                    continue
                scanned += 1
                if scanned > MAX_SEARCH_FILES:
                    return "\n".join(hits + ["… (search stopped: too many files)"])
                file_path = Path(folder) / name
                try:
                    if _is_link(file_path) or file_path.stat().st_size > MAX_FILE_BYTES:
                        continue
                    data = file_path.read_bytes()
                except OSError:
                    continue
                if b"\0" in data[:8192]:
                    continue
                rel = file_path.relative_to(self.root).as_posix()
                for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
                    if needle in line.lower():
                        hits.append(f"{rel}:{number}: {line.strip()[:300]}")
                        if len(hits) >= MAX_HITS:
                            return "\n".join(hits + ["… (more matches; narrow the search)"])
        return "\n".join(hits) or "(no matches)"

    def call(self, name, args):
        args = args if isinstance(args, dict) else {}
        if name == "project_list":
            return self.list(args.get("path", ""))
        if name == "project_read":
            return self.read(args["path"], args.get("start_line", 1), args.get("max_lines", MAX_READ_LINES))
        if name == "project_search":
            return self.search(args["query"], args.get("path", ""), args.get("glob"))
        raise ValueError("Unknown tool")


def handle(reader, request):
    method = request.get("method")
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "quartz-project", "version": "0.1.0"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method != "tools/call":
        raise ValueError("Unsupported MCP method")
    params = request.get("params") or {}
    try:
        text = reader.call(params.get("name"), params.get("arguments") or {})
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}


def main(root):
    reader = ProjectReader(root)
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    for line in sys.stdin:
        if len(line) > 65536:
            break
        request = None
        try:
            request = json.loads(line)
            if "id" not in request:
                continue
            response = {"jsonrpc": "2.0", "id": request["id"], "result": handle(reader, request)}
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32603, "message": str(exc)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


def codex_override(root):
    """Per-run Codex config: this server only, read-only tools auto-approved."""
    from core.desktop_agents import mcp_command
    command = mcp_command()
    clean = str(Path(root).resolve(strict=True))
    return ('mcp_servers.quartz_project={command=' + json.dumps(command[0]) +
            ',args=' + json.dumps(command[1:] + ["--project-read-server", clean]) +
            ',enabled_tools=' + json.dumps([t["name"] for t in TOOLS]) +
            ',tool_timeout_sec=60,default_tools_approval_mode="approve"}')
