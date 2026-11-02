"""Bounded package inventories. Never extracts or executes members."""
import io
import hashlib
import json
import struct
import zipfile

from .binary import FormatError, Reader

MAX_ENTRIES = 8192


def inspect_pck(data, check):
    """Standalone unencrypted Godot PCK v2/v3/v4 (official 4.7.1 layout).

    Does not follow resource paths, load scripts, decrypt or support sparse/delta
    bundles. MD5 is an integrity field, not a signature or authenticity claim.
    """
    reader = Reader(data, check)
    if reader.read(0, 4) != b'GDPC':
        raise FormatError('not-godot-pck')
    version, major, minor, patch, flags = reader.unpack('<IIIII', 4)
    if version not in (2, 3, 4) or flags & ~2:
        raise FormatError('pck-version-encryption-or-sparse-unsupported')
    file_base = reader.uint(24, 8)
    directory = 96 if version == 2 else reader.uint(32, 8)
    if directory < (96 if version == 2 else 104) or file_base > len(data):
        raise FormatError('pck-header-bounds')
    count = reader.uint(directory)
    if count > MAX_ENTRIES:
        raise FormatError('pck-entry-limit')
    position, total = directory + 4, 0
    entries, names = [], set()
    for _ in range(count):
        length = reader.uint(position)
        if not 1 <= length <= 2048:
            raise FormatError('pck-name-limit')
        raw_name = reader.read(position + 4, length)
        try:
            name = raw_name.rstrip(b'\0').decode('utf-8')
        except UnicodeError:
            raise FormatError('pck-name-encoding') from None
        if (not name or '\0' in name or ':' in name or '\\' in name or name.startswith('/')
                or any(part in ('', '.', '..') for part in name.split('/')) or name in names):
            raise FormatError('pck-ambiguous-resource-path')
        names.add(name)
        pos = position + 4 + length
        offset, size = reader.unpack('<QQ', pos)
        declared = reader.read(pos + 16, 16).hex()
        entry_flags = reader.uint(pos + 32)
        if entry_flags:
            raise FormatError('pck-encrypted-removal-or-delta-unsupported')
        absolute = file_base + offset
        if absolute + size > len(data):
            raise FormatError('pck-member-bounds')
        total += size
        if total > 128 * 1024 * 1024:
            raise FormatError('pck-total-member-limit')
        md5 = hashlib.md5(usedforsecurity=False)
        sha256 = hashlib.sha256()
        for p in range(absolute, absolute + size, 256 * 1024):
            block = reader.read(p, min(256 * 1024, absolute + size - p))
            md5.update(block)
            sha256.update(block)
        if md5.hexdigest() != declared:
            raise FormatError('pck-member-digest-mismatch')
        entries.append({'name': name, 'resource_path': 'res://' + name, 'offset': absolute, 'size': size,
                        'md5': declared, 'md5_verified': True, 'sha256': sha256.hexdigest(), 'flags': entry_flags})
        position = pos + 36
    return {'format': 'godot-pck', 'pack_format_version': version, 'declared_engine_version': f'{major}.{minor}.{patch}',
            'flags': flags, 'file_base': file_base, 'directory_offset': directory, 'entries': entries}


def inspect_zip(data, check):
    # Validate the classic central-directory count before zipfile allocates its
    # list. ZIP64 and multi-disk archives deliberately require another provider.
    end = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    if end < 0 or len(data) < end + 22:
        raise FormatError('missing-zip-end-record')
    disk, central_disk, disk_count, count, central_size, central_offset, comment = struct.unpack_from('<HHHHIIH', data, end + 4)
    if (disk or central_disk or disk_count != count or count > MAX_ENTRIES or count == 65535
            or central_size == 0xffffffff or central_offset == 0xffffffff or end + 22 + comment != len(data)):
        raise FormatError('zip-limit-or-unsupported-layout')
    if central_offset + central_size > end:
        raise FormatError('zip-central-directory-bounds')
    observations = {'format': 'zip', 'entries': [], 'manifests': []}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) != count:
                raise FormatError('zip-entry-count-mismatch')
            seen = set()
            for item in entries:
                check()
                if item.filename in seen:
                    raise FormatError('zip-duplicate-member')
                seen.add(item.filename)
                if len(item.filename) > 2048:
                    raise FormatError('zip-member-name-limit')
                observations['entries'].append({'name': item.filename, 'size': item.file_size,
                    'compressed_size': item.compress_size, 'crc32': f'{item.CRC:08x}',
                    'encrypted': bool(item.flag_bits & 1), 'compression': item.compress_type})
                # Only public package manifests; arbitrary text is not scanned.
                if item.filename.rsplit('/', 1)[-1] == 'package.json' and not item.flag_bits & 1 and item.file_size <= 65536:
                    raw = archive.read(item)
                    try:
                        manifest = json.loads(raw)
                    except (ValueError, UnicodeError, RecursionError):
                        continue
                    if not isinstance(manifest, dict):
                        continue
                    dependencies = {}
                    for field in ('dependencies', 'devDependencies', 'optionalDependencies'):
                        value = manifest.get(field, {})
                        if isinstance(value, dict) and len(value) <= 256:
                            dependencies[field] = {k: v for k, v in value.items() if isinstance(k, str) and len(k) <= 256 and isinstance(v, str) and len(v) <= 512}
                    observations['manifests'].append({'member': item.filename,
                        'name': manifest.get('name') if isinstance(manifest.get('name'), str) else None,
                        'version': manifest.get('version') if isinstance(manifest.get('version'), str) else None,
                        'dependencies': dependencies})
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
        raise FormatError('invalid-or-unsupported-zip') from exc
    return observations


def inspect_pyinstaller(data, check):
    """PyInstaller 2.1+ CArchive cookie/TOC, big-endian packed structures.

    A module's TOC name/type is observed; Python bytecode semantics are not.
    """
    magic = b'MEI\x0c\x0b\x0a\x0b\x0e'
    cookie = data.rfind(magic, max(0, len(data) - 8 * 1024 * 1024))
    if cookie < 0:
        return None
    reader = Reader(data, check)
    _, length, toc_offset, toc_size, version, library = reader.unpack('!8sIIII64s', cookie)
    start = cookie + 88 - length
    if start < 0 or start + toc_offset < start or start + toc_offset + toc_size > cookie:
        raise FormatError('pyinstaller-cookie-bounds')
    pos, end = start + toc_offset, start + toc_offset + toc_size
    entries = []
    while pos < end:
        check()
        if len(entries) >= MAX_ENTRIES or end - pos < 18:
            raise FormatError('pyinstaller-toc-limit')
        stride, offset, compressed, size, flag, kind = reader.unpack('!IIIIBB', pos)
        if stride < 19 or pos + stride > end or flag not in (0, 1) or start + offset + compressed > start + toc_offset:
            raise FormatError('pyinstaller-toc-bounds')
        raw_name = reader.read(pos + 18, stride - 18)
        if b'\0' not in raw_name:
            raise FormatError('pyinstaller-name-not-terminated')
        name = raw_name.split(b'\0', 1)[0]
        if len(name) > 2048:
            raise FormatError('pyinstaller-name-limit')
        entries.append({'name': name.decode('utf-8', 'replace'), 'type': chr(kind), 'offset': start + offset,
                        'compressed_size': compressed, 'size': size, 'compressed': bool(flag)})
        pos += stride
    return {'format': 'pyinstaller', 'python_version': version, 'python_library': library.split(b'\0')[0].decode('ascii', 'replace'),
            'archive_start': start, 'cookie_offset': cookie, 'entries': entries}
