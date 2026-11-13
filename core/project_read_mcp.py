"""SpeS-owned read-only project tools as a stdio MCP server.

The agent gets only list/read/search over one project root. SpeS, not the
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


def _kernel32():
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    k32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    return k32


def _handle_path(handle):
    """Real path of an open Windows handle, normalised WITHOUT asking the file system again."""
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    size = _kernel32().GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
    if not size or size >= len(buffer):
        raise OSError("Cannot verify the opened object")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return value


def _final_path(fd):
    """The real path of an open file descriptor (Windows), or None elsewhere."""
    if os.name != "nt":
        return None
    import msvcrt
    return _handle_path(msvcrt.get_osfhandle(fd))


class _DirHandle:
    """An open directory handle: verified by its real path, then listed FROM THE
    HANDLE (GetFileInformationByHandleEx), never by reopening the name.

    Holding a handle does not stop a rename on current Windows (POSIX rename
    semantics; found by test), so the listing itself must come from the handle.
    """

    def __init__(self, path):
        self.path, self.handle = str(path), None

    def __enter__(self):
        if os.name != "nt":
            return os.path.realpath(self.path)
        k32 = _kernel32()
        handle = k32.CreateFileW(self.path, 0x0001 | 0x0080,  # FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES
                                 0x1 | 0x2 | 0x4,  # share read/write/delete: never block the user's work
                                 None, 3,  # OPEN_EXISTING
                                 0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
                                 None)
        if handle in (None, 0, -1) or handle == ctypes_invalid():
            raise OSError("Cannot open the folder")
        try:
            real = _handle_path(handle)
        except BaseException:
            k32.CloseHandle(handle)  # __exit__ will not run when __enter__ fails
            raise
        self.handle = handle
        return real

    def entries(self):
        """(name, is_dir, is_reparse) for every child, read from this handle."""
        if os.name != "nt":
            with os.scandir(self.path) as items:
                return [(i.name, i.is_dir(follow_symlinks=False), i.is_symlink()) for i in items]
        import ctypes
        import struct
        from ctypes import wintypes
        k32 = _kernel32()
        k32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k32.GetFileInformationByHandleEx.restype = wintypes.BOOL
        buffer = ctypes.create_string_buffer(64 * 1024)
        out, info_class = [], 15  # FileFullDirectoryRestartInfo, then FileFullDirectoryInfo (14)
        while True:
            if not k32.GetFileInformationByHandleEx(self.handle, info_class, buffer, len(buffer)):
                if ctypes.get_last_error() == 18:  # ERROR_NO_MORE_FILES
                    return out
                raise OSError("Cannot list the folder")
            info_class, offset, raw = 14, 0, buffer.raw
            while True:
                next_offset, = struct.unpack_from("<I", raw, offset)
                attributes, name_length = struct.unpack_from("<II", raw, offset + 56)
                name = raw[offset + 68: offset + 68 + name_length].decode("utf-16-le")
                if name not in (".", ".."):
                    out.append((name, bool(attributes & 0x10), bool(attributes & 0x400)))
                if not next_offset:
                    break
                offset += next_offset

    def __exit__(self, *exc):
        if self.handle is not None:
            _kernel32().CloseHandle(self.handle)


def ctypes_invalid():
    import ctypes
    return ctypes.c_void_p(-1).value


def _same_or_under(real, root):
    """Pure string comparison: no resolve(), so the decision is the handle's, not a fresh lookup."""
    real_n = os.path.normcase(os.path.normpath(str(real)))
    root_n = os.path.normcase(os.path.normpath(str(root)))
    if real_n == root_n:
        return ""
    prefix = root_n.rstrip("\\/") + os.sep
    if not real_n.startswith(prefix):
        return None
    return os.path.normpath(str(real))[len(prefix):]


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
        """Lexical, link-free path under the root; checked on the REQUESTED parts.

        No ".." and no resolve() before the checks: every requested component is
        lstat'ed and rejected if it is a link/junction or a secret name.
        """
        text = str(raw or "").strip().replace("\\", "/")
        if text.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", text) or ":" in text:
            raise ValueError("Use a path relative to the project root")
        parts = [p for p in text.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise ValueError("Path is outside the project")
        if self._hidden(parts):
            raise ValueError("This file is protected and not readable here")
        probe = self.root
        for part in parts:
            probe = probe / part
            if _is_link(probe) and probe.exists():
                raise ValueError("Linked paths are not followed")
        return probe

    def _inside(self, real):
        relative = _same_or_under(real, self.root)
        if relative is None:
            return False
        return not self._hidden([p for p in re.split(r"[\\/]+", relative) if p])

    def _read_verified(self, path):
        """Open first, then prove the OPENED object lives under the root (no check/use race).

        The CRT opens without delete sharing, so the file and its folders cannot
        be renamed away between the handle check and the read.
        """
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fd = os.open(str(path), flags)
        try:
            info = os.fstat(fd)
            real = _final_path(fd) or os.path.realpath(str(path))
            if not self._inside(real):
                raise ValueError("Path is outside the project")
            if info.st_size > MAX_FILE_BYTES:
                raise ValueError("File is too large to read here")
            with os.fdopen(os.dup(fd), "rb") as handle:
                return handle.read(MAX_FILE_BYTES + 1)
        finally:
            os.close(fd)

    def _entries(self, folder):
        """List a folder while it is held open and verified (names only, links marked)."""
        holder = _DirHandle(folder)
        with holder as real:
            if not self._inside(real):
                raise ValueError("Folder is outside the project")
            return holder.entries()

    def list(self, path=""):
        folder = self.resolve(path)
        if not folder.is_dir():
            raise NotADirectoryError("Not a folder in the project")
        entries = []
        for name, is_dir, linked in sorted(self._entries(folder), key=lambda e: (not e[1], e[0].lower())):
            if SECRET_NAME.match(name) or linked:
                continue
            entries.append(name + ("/" if is_dir else ""))
            if len(entries) >= MAX_LIST:
                entries.append("… (list truncated)")
                break
        return "\n".join(entries) or "(empty folder)"

    def read(self, path, start_line=1, max_lines=MAX_READ_LINES):
        target = self.resolve(path)
        if not target.is_file():
            raise FileNotFoundError("Not a file")
        data = self._read_verified(target)
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
        if not base.is_dir():
            raise NotADirectoryError("Not a folder in the project")
        hits, scanned = [], 0
        pending = [base]
        while pending:
            folder = pending.pop(0)
            try:
                # Each folder is listed while held open and verified (same rule as project_list);
                # links/junctions are never entered.
                entries = self._entries(folder)
            except (OSError, ValueError):
                continue
            pending.extend(folder / name for name, is_dir, linked in sorted(entries)
                           if is_dir and not linked and name not in SKIP_DIRS and not SECRET_NAME.match(name))
            files = sorted(name for name, is_dir, linked in entries if not is_dir and not linked)
            for name in files:
                if SECRET_NAME.match(name) or (glob and not fnmatch.fnmatch(name, glob)):
                    continue
                scanned += 1
                if scanned > MAX_SEARCH_FILES:
                    return "\n".join(hits + ["… (search stopped: too many files)"])
                file_path = Path(folder) / name
                try:
                    if _is_link(file_path):
                        continue
                    data = self._read_verified(file_path)
                except (OSError, ValueError):
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


def expected_server(root):
    """The exact helper identity SpeS registers for a project read: program and arguments."""
    from core.helper_command import mcp_command  # stdlib-only: keeps the guard exe small
    command = mcp_command()
    clean = str(Path(root).resolve(strict=True))
    return {"command": command[0], "args": command[1:] + ["--project-read-server", clean]}


def codex_override(root):
    """Per-run Codex config: this server only, read-only tools auto-approved."""
    server = expected_server(root)
    return ('mcp_servers.quartz_project={command=' + json.dumps(server["command"]) +
            ',args=' + json.dumps(server["args"]) +
            ',enabled_tools=' + json.dumps([t["name"] for t in TOOLS]) +
            ',tool_timeout_sec=60,default_tools_approval_mode="approve"}')
