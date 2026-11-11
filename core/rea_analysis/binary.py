"""PE/COFF structural reader, based on Microsoft's PE format specification.

All offsets refer to the file (not mapped process memory). No disassembly,
runtime execution, signature trust or arbitrary directory scanning is implied.
"""
import struct


class FormatError(ValueError):
    pass


class Reader:
    def __init__(self, data, check=lambda: None):
        self.data, self.check = data, check

    def read(self, offset, size):
        self.check()
        if type(offset) is not int or type(size) is not int or min(offset, size) < 0 or offset + size > len(self.data):
            raise FormatError('file-bounds')
        return self.data[offset:offset + size]

    def unpack(self, fmt, offset):
        return struct.unpack(fmt, self.read(offset, struct.calcsize(fmt)))

    def uint(self, offset, size=4):
        return int.from_bytes(self.read(offset, size), 'little')

    def cstring(self, offset, maximum=512):
        raw = self.read(offset, min(maximum, len(self.data) - offset))
        end = raw.find(b'\0')
        if end < 0:
            raise FormatError('unterminated-string')
        return raw[:end].decode('utf-8', 'replace')


class PE(Reader):
    MAX_ITEMS = 8192

    def __init__(self, data, check=lambda: None):
        super().__init__(data, check)
        if self.read(0, 2) != b'MZ':
            raise FormatError('not-pe')
        pos = self.uint(0x3c)
        if self.read(pos, 4) != b'PE\0\0':
            raise FormatError('invalid-pe-signature')
        self.machine, count, self.timestamp, _, _, optional_size, self.characteristics = self.unpack('<HHIIIHH', pos + 4)
        if not 1 <= count <= 96:
            raise FormatError('section-limit')
        opt = pos + 24
        self.read(opt, optional_size)
        magic = self.uint(opt, 2)
        if magic not in (0x10b, 0x20b):
            raise FormatError('unsupported-pe-magic')
        self.bits = 64 if magic == 0x20b else 32
        directory_start = 112 if self.bits == 64 else 96
        if optional_size < directory_start:
            raise FormatError('short-optional-header')
        self.entry_rva = self.uint(opt + 16)
        self.headers_size = self.uint(opt + 60)
        self.subsystem = self.uint(opt + 68, 2)
        self.image_base = self.uint(opt + (24 if self.bits == 64 else 28), self.bits // 8)
        directories = self.uint(opt + directory_start - 4)
        if directories > (optional_size - directory_start) // 8:
            raise FormatError('directory-bounds')
        self.directories = [self.unpack('<II', opt + directory_start + i * 8) for i in range(min(directories, 16))]
        self.sections = []
        for i in range(count):
            p = opt + optional_size + i * 40
            name, virtual_size, rva, raw_size, raw_offset, _, _, _, _, flags = self.unpack('<8sIIIIIIHHI', p)
            if raw_size:
                self.read(raw_offset, raw_size)
            self.sections.append({'name': name.rstrip(b'\0').decode('ascii', 'replace'), 'rva': rva,
                                  'virtual_size': virtual_size, 'raw_size': raw_size,
                                  'raw_offset': raw_offset, 'characteristics': flags})

    def directory(self, index):
        return self.directories[index] if index < len(self.directories) else (0, 0)

    def rva(self, value, size=1):
        if value < self.headers_size and value + size <= self.headers_size:
            self.read(value, size)
            return value
        candidates = [s for s in self.sections if s['rva'] <= value and value + size <= s['rva'] + s['raw_size']]
        if len(candidates) != 1:
            raise FormatError('unmapped-or-ambiguous-rva')
        offset = candidates[0]['raw_offset'] + value - candidates[0]['rva']
        self.read(offset, size)
        return offset

    def rstring(self, value):
        # Require every byte including the terminator to have file backing.
        offset = self.rva(value)
        raw = self.read(offset, min(512, len(self.data) - offset))
        end = raw.find(b'\0')
        if end < 0:
            raise FormatError('unterminated-string')
        self.rva(value, end + 1)
        return raw[:end].decode('utf-8', 'replace')

    def imports(self):
        address, size = self.directory(1)
        if not address or not size:
            return []
        result, total = [], 0
        for index in range(min(size // 20, 512)):
            p = self.rva(address + index * 20, 20)
            original, stamp, chain, name, iat = self.unpack('<IIIII', p)
            if not any((original, stamp, chain, name, iat)):
                return result
            if not name or not iat:
                raise FormatError('invalid-import-descriptor')
            symbols = []
            step = self.bits // 8
            for number in range(self.MAX_ITEMS - total):
                value = self.uint(self.rva((original or iat) + number * step, step), step)
                if not value:
                    break
                self.rva(iat + number * step, step)
                total += 1
                if value & (1 << (self.bits - 1)):
                    symbol = {'ordinal': value & 0xffff}
                else:
                    p = self.rva(value, 3)
                    symbol = {'name': self.rstring(value + 2), 'hint': self.uint(p, 2)}
                symbols.append(dict(symbol, iat_rva=iat + number * step, lookup_rva=(original or iat) + number * step))
            else:
                raise FormatError('import-limit-or-missing-terminator')
            result.append({'library': self.rstring(name), 'symbols': symbols})
        raise FormatError('import-directory-missing-terminator')

    def exports(self):
        address, size = self.directory(0)
        if not address or not size:
            return []
        p = self.rva(address, 40)
        _, _, _, _, _, base, functions, names, function_rva, name_rva, ordinal_rva = self.unpack('<IIHHIIIIIII', p)
        if max(functions, names) > self.MAX_ITEMS or names > functions:
            raise FormatError('export-limit')
        labels = {}
        for i in range(names):
            ordinal = self.uint(self.rva(ordinal_rva + i * 2, 2), 2)
            if ordinal >= functions:
                raise FormatError('invalid-export-ordinal')
            labels.setdefault(ordinal, []).append(self.rstring(self.uint(self.rva(name_rva + i * 4, 4))))
        result = []
        for i in range(functions):
            value = self.uint(self.rva(function_rva + i * 4, 4))
            if value:
                item = {'ordinal': base + i, 'names': labels.get(i, []), 'rva': value}
                if address <= value < address + size:
                    item['forwarder'] = self.rstring(value)
                result.append(item)
        return result

    def runtime_functions(self):
        address, size = self.directory(3)
        if self.machine != 0x8664 or not address or not size:
            return []
        if size % 12 or size // 12 > self.MAX_ITEMS:
            raise FormatError('runtime-function-limit')
        result = []
        for i in range(size // 12):
            start, end, unwind = self.unpack('<III', self.rva(address + i * 12, 12))
            if start >= end:
                raise FormatError('invalid-runtime-function-range')
            self.rva(start, end - start)
            self.rva(unwind)
            result.append({'begin_rva': start, 'end_rva': end, 'unwind_info_rva': unwind})
        return result

    def inspect(self):
        return {'format': 'pe', 'machine': hex(self.machine), 'bits': self.bits, 'subsystem': self.subsystem,
                'entry_point_rva': self.entry_rva, 'image_base': self.image_base,
                'sections': self.sections, 'imports': self.imports(), 'exports': self.exports(),
                'runtime_functions': self.runtime_functions()}
