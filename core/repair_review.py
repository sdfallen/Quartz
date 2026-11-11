"""Bounded advisory signals from host-owned writer checkpoints; never acceptance."""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import zipfile


_SIGNALS = {
    '__main__': r'\b__main__\b',
    'gc.get_objects': r'\bgc\s*\.\s*get_objects\b',
    'sys._getframe': r'\bsys\s*\.\s*_getframe\b',
    'inspect': r'\binspect\b',
    'os._exit': r'\bos\s*\.\s*_exit\b',
    'unittest': r'\bunittest\b',
    'quartz-host-unittest': r'quartz-host-unittest',
    '__import__': r'\b__import__\b',
    'importlib': r'\bimportlib\b',
    'getattr': r'\b(?:builtins\s*\.\s*|__builtins__\s*\.\s*)?getattr\s*\(\s*(?:sys|os|builtins|__builtins__)\b',
}


def _long_path(path):
    """Expand Windows 8.3 short names (RUNNER~1) lexically, without following links."""
    if os.name != 'nt' or '~' not in str(path):
        return path
    import ctypes
    existing, rest = path, []
    while not existing.exists() and existing.parent != existing:
        rest.insert(0, existing.name)
        existing = existing.parent
    buffer = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetLongPathNameW(str(existing), buffer, len(buffer))
    if not size or size >= len(buffer):
        return path
    return Path(buffer.value, *rest)


def review_writer_changes(workspace, run):
    """Read only declared changed files and their verified pre-write archive bytes.

    Line-set differences are a cheap heuristic, not a parser or security oracle.
    Only labels, never source lines, enter the result. Missing/truncated evidence
    is explicitly unknown and cannot suppress mandatory independent review.
    """
    result = {'status': 'clear', 'signals': [], 'independent_review_required': True}
    try:
        checkpoint = run.get('checkpoint')
        changed = run.get('files_changed')
        if (not isinstance(checkpoint, dict) or checkpoint.get('complete') is not True
                or not isinstance(changed, list) or len(changed) > 200 or run.get('evidence_warning')):
            raise ValueError('Incomplete writer evidence')
        root = Path(workspace).resolve(strict=True)
        with zipfile.ZipFile(checkpoint['archive']) as archive:
            info = archive.getinfo('checkpoint-manifest.json')
            if info.file_size > 4 * 1024 * 1024: raise ValueError('Manifest budget')
            manifest = json.loads(archive.read(info))
            if Path(manifest['workspace']).resolve() != root: raise ValueError('Checkpoint scope')
            saved_files = {Path(name).as_posix(): saved for name, saved in manifest['files'].items()}
            total = 0
            for value in changed:
                path = Path(value)
                if not path.is_absolute(): path = root / path
                if '..' in path.parts or PureWindowsPath(str(path)).drive.lower() != PureWindowsPath(str(root)).drive.lower():
                    raise ValueError('Changed path scope')
                path = _long_path(path)
                relative = path.relative_to(root).as_posix()
                for part in (path, *path.parents):
                    if part == root: break
                    if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
                        raise ValueError('Changed path link')
                if not path.resolve().is_relative_to(root): raise ValueError('Changed path scope')
                before = b''
                saved = saved_files.get(relative)
                if saved and saved.get('exists'):
                    info = archive.getinfo('files/'+relative)
                    if info.file_size > 1024 * 1024: raise ValueError('Source budget')
                    before = archive.read(info)
                    if hashlib.sha256(before).hexdigest() != saved['sha256']: raise ValueError('Checkpoint hash')
                after = b''
                if path.exists():
                    with path.open('rb') as source: after = source.read(1024 * 1024 + 1)
                total += len(before) + len(after)
                if len(after) > 1024 * 1024 or total > 8 * 1024 * 1024: raise ValueError('Diff budget')
                if b'\0' in before or b'\0' in after: raise ValueError('Binary diff unsupported')
                b_lines, a_lines = before.decode('utf-8').splitlines(), after.decode('utf-8').splitlines()
                b_set, a_set = set(b_lines), set(a_lines)
                lines = '\n'.join([line for line in a_lines if line not in b_set] + [line for line in b_lines if line not in a_set])
                result['signals'].extend({'file': relative, 'signal': label} for label, pattern in _SIGNALS.items()
                                         if re.search(pattern, lines))
        if result['signals']: result['status'] = 'suspicious'
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
        result['status'] = 'unknown'
    return result
