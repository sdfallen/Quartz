"""GUI-selected executable inspection. No directory scans or target execution."""
from pathlib import Path
import struct

from core.self_diagnostics import SelfDiagnosticsService


def selected_executable(value):
    path = Path(value).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('Bağlantılı hedefler incelenmez')
    path = path.resolve(strict=True)
    if (path.suffix.lower() != '.exe' or not path.is_file()
            or path.stat().st_size > 512 * 1024 * 1024
            or any(p.casefold() in {'warbandisland', 'ai_island_test'} for p in path.parts)):
        raise ValueError('Bu dosya izinli uygulama incelemesi kapsamında değil')
    return path


def parse_pe_metadata(stream, file_size: int) -> dict | None:
    """Parse bounded MZ/COFF/OptionalHeader/SectionTable facts without reading code or strings."""
    stream.seek(0)
    header = stream.read(64)
    offset = struct.unpack_from('<I', header, 60)[0] if len(header) == 64 else -1
    if header[:2] != b'MZ' or not (64 <= offset <= min(file_size - 24, 1024 * 1024)):
        return None
    stream.seek(offset)
    coff = stream.read(24)
    if len(coff) != 24 or coff[:4] != b'PE\0\0':
        return None
    machine, sections, _ts, _sym_ptr, _sym_cnt, opt_size, characteristics = struct.unpack_from('<HHIIIHH', coff, 4)
    arch = {0x8664: 'x64', 0x014c: 'x86', 0xaa64: 'arm64'}.get(machine, 'unknown')
    meta = {
        'machine': int(machine),
        'sections': int(sections),
        'architecture': arch,
        'is_dll': bool(characteristics & 0x2000),
        'large_address_aware': bool(characteristics & 0x0020),
    }
    if 2 <= opt_size <= 4096 and offset + 24 + opt_size <= file_size:
        opt = stream.read(opt_size)
        if len(opt) == opt_size:
            magic = struct.unpack_from('<H', opt, 0)[0]
            meta['pe_format'] = {0x20b: 'PE32+', 0x10b: 'PE32'}.get(magic, 'unknown')
            if len(opt) >= 72 and magic in {0x10b, 0x20b}:
                subsystem_code, dll_chars = struct.unpack_from('<HH', opt, 68)
                meta['subsystem'] = {
                    1: 'native',
                    2: 'windows_gui',
                    3: 'windows_cui',
                    10: 'efi',
                    11: 'efi',
                    12: 'efi',
                    13: 'efi',
                }.get(subsystem_code, 'other')
                meta['dynamic_base'] = bool(dll_chars & 0x0040)
                meta['high_entropy_va'] = bool(dll_chars & 0x0020)
                meta['nx_compat'] = bool(dll_chars & 0x0100)
            if 0 < sections <= 96 and offset + 24 + opt_size + sections * 40 <= file_size:
                sec_table = stream.read(sections * 40)
                if len(sec_table) == sections * 40:
                    has_resources = False
                    max_raw_end = 0
                    for idx in range(sections):
                        entry = sec_table[idx * 40:(idx + 1) * 40]
                        raw_name = entry[:8].split(b'\0', 1)[0].decode('ascii', 'ignore').strip().lower()
                        if raw_name == '.rsrc':
                            has_resources = True
                        raw_size, raw_ptr = struct.unpack_from('<II', entry, 16)
                        if raw_ptr > 0 and raw_size > 0:
                            end = raw_ptr + raw_size
                            if end > max_raw_end:
                                max_raw_end = end
                    meta['has_resources'] = has_resources
                    if max_raw_end > 0:
                        overlay = max(0, file_size - max_raw_end)
                        meta['has_overlay'] = overlay > 0
                        meta['overlay_bytes'] = int(overlay)
    return meta


class ArtifactDiagnosticsService(SelfDiagnosticsService):
    SCOPE = 'artifact'

    def __init__(self, selected_path, *, knowledge=None, **kwargs):
        self.target = selected_executable(selected_path)
        stat = self.target.stat()
        self.identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        super().__init__(**kwargs)
        if knowledge is False:
            self.knowledge = None
        elif knowledge is not None:
            self.knowledge = knowledge
        else:
            from core.application_knowledge import ApplicationKnowledge
            reports_dir = kwargs.get('reports')
            knowledge_root = (Path(reports_dir).parent / 'application-knowledge') if reports_dir is not None else None
            self.knowledge = ApplicationKnowledge(knowledge_root)

    def _on_completed(self, identity, snapshot):
        if self.knowledge is not None:
            try:
                self.knowledge.save(self.target, snapshot)
                snapshot['knowledge_saved'] = True
            except Exception:
                snapshot['knowledge_saved'] = False

    def _inspect(self, identity, event, deadline, include_rea):
        target = selected_executable(self.target)
        stat = target.stat()
        if self.identity != (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns):
            raise ValueError('Seçilen dosya değişti; yeniden seçilmeli')
        self._update(identity, phase='scope', progress=10,
                     message='Seçilen uygulama çalıştırılmadan inceleniyor…',
                     limitations=['Yalnız seçilen EXE okunur; komşu dosyalar, hesaplar ve günlükler taranmaz.',
                                  'Statik dosya incelemesi; güvenlik, ekran davranışı veya hatasız çalışma garantisi değildir.'])
        digest = self._hash(target, event, deadline)
        self._check(identity, 'artifact', 'PASS', 'Seçilen dosya',
                    'Dosya kimliği ve SHA-256 kaydedildi; uygulama çalıştırılmadı.',
                    sha256=digest, bytes=stat.st_size)
        # Parse only a bounded PE header, never imports, code or embedded strings.
        with target.open('rb') as stream:
            pe_meta = parse_pe_metadata(stream, stat.st_size)
            if pe_meta is not None:
                self._check(identity, 'pe', 'PASS', 'Windows dosya başlığı',
                            'PE başlığı ve mimari yapısı okunabildi; bu bir çalıştırma testi değildir.',
                            **pe_meta)
            else:
                self._check(identity, 'pe', 'UNKNOWN', 'Windows dosya başlığı',
                            'Desteklenen PE başlığı doğrulanamadı.')
        self._guard(event, deadline)
        if include_rea:
            from core.rea_adapter import ReaAdapter
            result = (self.rea or ReaAdapter()).inspect(target, event=event, deadline=deadline)
            self._guard(event, deadline)
            self._check(identity, 'rea', result['status'], 'REA statik incelemesi',
                        result['message'], **result.get('evidence', {}))
            self._update(identity, rea_used=bool(result.get('used')))
        else:
            self._check(identity, 'rea', 'NOT_TESTED', 'REA', 'REA kullanılmadı.')
        if self._hash(target, event, deadline) != digest:
            raise ValueError('İnceleme sırasında dosya değişti')
