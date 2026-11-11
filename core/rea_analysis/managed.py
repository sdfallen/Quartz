"""ECMA-335 II.24 metadata: assembly, references and TypeDef/MethodDef ownership.

Reads table layouts, not string guesses. Method semantics/IL disassembly remain
outside this reader. Unknown metadata tables are rejected, never guessed.
"""
from .binary import FormatError, Reader

# Fixed-width fields are integers. s/g/b are #Strings/#GUID/#Blob indexes;
# tN is a table index; cNAME is a tagged (coded) table index.
CODED = {
    'ResolutionScope': (2, [0, 26, 35, 1]), 'TypeDefOrRef': (2, [2, 1, 27]),
    'HasConstant': (2, [4, 8, 23]), 'HasCustomAttribute': (5, [6, 4, 1, 2, 8, 9, 10, 0, 14, 23, 20, 17, 26, 27, 32, 35, 38, 39, 40, 42, 44, 43]),
    'CustomAttributeType': (3, [6, 10]), 'HasFieldMarshal': (1, [4, 8]),
    'HasDeclSecurity': (2, [2, 6, 32]), 'MemberRefParent': (3, [2, 1, 26, 6, 27]),
    'HasSemantics': (1, [20, 23]), 'MethodDefOrRef': (1, [6, 10]),
    'MemberForwarded': (1, [4, 6]), 'Implementation': (2, [38, 35, 39]),
    'TypeOrMethodDef': (1, [2, 6]),
}
TABLES = [
    [2, 's', 'g', 'g', 'g'], ['cResolutionScope', 's', 's'],
    [4, 's', 's', 'cTypeDefOrRef', 't4', 't6'], ['t4'], [2, 's', 'b'], ['t6'],
    [4, 2, 2, 's', 'b', 't8'], ['t8'], [2, 2, 's'], ['t2', 'cTypeDefOrRef'],
    ['cMemberRefParent', 's', 'b'], [2, 'cHasConstant', 'b'], ['cHasCustomAttribute', 'cCustomAttributeType', 'b'],
    ['cHasFieldMarshal', 'b'], [2, 'cHasDeclSecurity', 'b'], [2, 4, 't2'], [4, 't4'],
    ['b'], ['t2', 't20'], ['t20'], [2, 's', 'cTypeDefOrRef'], ['t2', 't23'], ['t23'],
    [2, 's', 'b'], [2, 't6', 'cHasSemantics'], ['t2', 'cMethodDefOrRef', 'cMethodDefOrRef'],
    ['s'], ['b'], [2, 'cMemberForwarded', 's', 't26'], [4, 't4'], [4, 4], [4],
    [4, 2, 2, 2, 2, 4, 'b', 's', 's'], [4], [4, 4, 4],
    [2, 2, 2, 2, 4, 'b', 's', 's', 'b'], [4, 't35'], [4, 4, 4, 't35'],
    [4, 's', 'b'], [4, 4, 's', 's', 'cImplementation'], [4, 4, 's', 'cImplementation'],
    ['t2', 't2'], [2, 2, 'cTypeOrMethodDef', 's'], ['cMethodDefOrRef', 'b'], ['t42', 'cTypeDefOrRef'],
]


def inspect_managed(pe):
    address, size = pe.directory(14)
    if not address or not size:
        return None
    if size < 72:
        raise FormatError('short-cli-header')
    cli = pe.rva(address, 72)
    if pe.uint(cli) < 72:
        raise FormatError('short-cli-header')
    metadata_rva, metadata_size, flags, entry = pe.unpack('<IIII', cli + 8)
    metadata = Reader(pe.read(pe.rva(metadata_rva, metadata_size), metadata_size), pe.check)
    if metadata.read(0, 4) != b'BSJB':
        raise FormatError('invalid-cli-metadata-signature')
    version_length = metadata.uint(12)
    if not 1 <= version_length <= 256:
        raise FormatError('metadata-version-limit')
    runtime = metadata.read(16, version_length).rstrip(b'\0').decode('ascii', 'replace')
    pos = (16 + version_length + 3) & ~3
    count = metadata.uint(pos + 2, 2)
    if count > 32:
        raise FormatError('metadata-stream-limit')
    pos += 4
    streams = {}
    for _ in range(count):
        offset, length = metadata.unpack('<II', pos)
        name = metadata.cstring(pos + 8, 32)
        if name in streams:
            raise FormatError('duplicate-metadata-stream')
        streams[name] = Reader(metadata.read(offset, length), pe.check)
        pos = (pos + 8 + len(name.encode()) + 1 + 3) & ~3
    table = streams.get('#~') or streams.get('#-')
    strings = streams.get('#Strings')
    if table is None or strings is None:
        raise FormatError('missing-metadata-stream')
    heaps = table.uint(6, 1)
    if heaps & ~7:
        raise FormatError('metadata-heap-layout-unsupported')
    valid = table.uint(8, 8)
    counts, pos = {}, 24
    for i in range(64):
        if valid & (1 << i):
            counts[i] = table.uint(pos)
            pos += 4
            if i >= len(TABLES) or counts[i] > 1000000:
                raise FormatError('metadata-table-limit-or-unsupported')
    widths = {'s': 4 if heaps & 1 else 2, 'g': 4 if heaps & 2 else 2, 'b': 4 if heaps & 4 else 2}

    def width(field):
        if isinstance(field, int):
            return field
        if field in widths:
            return widths[field]
        if field.startswith('t'):
            return 4 if counts.get(int(field[1:]), 0) >= 65536 else 2
        bits, targets = CODED[field[1:]]
        return 4 if max((counts.get(i, 0) for i in targets), default=0) >= 1 << (16 - bits) else 2

    layouts = {}
    for i, number in counts.items():
        sizes = [width(field) for field in TABLES[i]]
        size = sum(sizes)
        table.read(pos, size * number)
        layouts[i] = pos, size, sizes
        pos += size * number

    def row(kind, index):
        if not 1 <= index <= counts.get(kind, 0):
            raise FormatError('metadata-row-bounds')
        offset, stride, sizes = layouts[kind]
        offset += (index - 1) * stride
        values = []
        for n in sizes:
            values.append(table.uint(offset, n))
            offset += n
        return values

    def name(index):
        return strings.cstring(index, 1024)

    if counts.get(3) or counts.get(5) or counts.get(7):
        # Unoptimized pointer tables change list ownership interpretation.
        raise FormatError('metadata-pointer-tables-unsupported')
    if sum(counts.get(i, 0) for i in (2, 6, 35, 10, 28)) > 8192:
        raise FormatError('metadata-observation-limit')
    assemblies = []
    for i in range(1, counts.get(32, 0) + 1):
        values = row(32, i)
        assemblies.append({'name': name(values[7]), 'version': '.'.join(map(str, values[1:5])), 'culture': name(values[8])})
    references = []
    for i in range(1, counts.get(35, 0) + 1):
        values = row(35, i)
        references.append({'name': name(values[6]), 'version': '.'.join(map(str, values[:4])), 'culture': name(values[7])})
    methods, types = [], []
    for i in range(1, counts.get(6, 0) + 1):
        values = row(6, i)
        # RVA is an actual MethodDef field; this makes no semantics claim.
        if values[0]:
            pe.rva(values[0])
        methods.append({'token': hex(0x06000000 | i), 'name': name(values[3]), 'rva': values[0],
                        'impl_flags': values[1], 'flags': values[2], 'signature_blob_index': values[4]})
    previous = 1
    for i in range(1, counts.get(2, 0) + 1):
        values = row(2, i)
        start = values[5]
        end = row(2, i + 1)[5] if i < counts[2] else counts.get(6, 0) + 1
        if not previous <= start <= end <= counts.get(6, 0) + 1:
            raise FormatError('metadata-method-ownership-bounds')
        previous = end
        types.append({'token': hex(0x02000000 | i), 'name': name(values[1]), 'namespace': name(values[2]), 'flags': values[0],
                      'method_tokens': [m['token'] for m in methods[start - 1:end - 1]]})
    pinvokes = []
    for i in range(1, counts.get(28, 0) + 1):
        values = row(28, i)
        module = row(26, values[3])
        pinvokes.append({'member_token': hex(((0x06000000 if values[1] & 1 else 0x04000000) | (values[1] >> 1))),
                         'import_name': name(values[2]), 'module': name(module[0]), 'flags': values[0]})
    return {'runtime_metadata_version': runtime, 'cli_flags': flags, 'entry_point_token_or_rva': entry,
            'assemblies': assemblies, 'assembly_references': references, 'types': types, 'methods': methods,
            'pinvoke': pinvokes, 'table_row_counts': {str(k): v for k, v in counts.items()}}
