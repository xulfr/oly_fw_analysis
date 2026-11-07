"""Bounded resource relocation for the pinned OM-5 II -> OM-5 I port.

Only parsed directory pointers and nested container metadata are relocated.
JPEGs are losslessly entropy-coded by jpegtran, then decoded for comparison.
No floating-point constants, image pixels or opaque resource bodies are rebased.
"""
import io
import struct
import subprocess

from oly_container import sha256, sum32


def require(ok, message):
    if not ok:
        raise ValueError(message)


def directory(data, table, origin, end):
    require(0 <= table < table+16 <= end <= len(data), 'Invalid directory bounds')
    first = struct.unpack_from('<I', data, table)[0] - origin
    require(table < first <= end and (first-table) % 16 == 0, 'Invalid directory first pointer')
    result = []
    for at in range(table, first, 16):
        pointer, size, x, y = struct.unpack_from('<4I', data, at)
        require(x == y == 0, 'Unsupported resource record flags')
        if size:
            offset = pointer-origin
            require(first <= offset < offset+size <= end, 'Resource outside directory')
            result.append((at, offset, size))
        else:
            require(pointer == 0 or first <= pointer-origin <= end,
                    'Empty record pointer outside directory')
    return first, result


def relocate_common(payload, old_address, new_address, target_size):
    """Move the 11 nested banks; retain every leaf's exact contents and index."""
    origin = old_address+32
    delta = new_address-old_address
    require(len(payload) <= target_size, 'Common resources exceed recipient slot')
    out = bytearray(payload)
    _, banks = directory(payload, 0, origin, len(payload))
    require(len(banks) == 11, 'Unexpected common resource bank count')
    leaves = []
    for index, (record, offset, size) in enumerate(banks):
        end = offset+size
        head, tail = payload[offset:offset+32], payload[end-32:end]
        require(head[:4] == bytes.fromhex('4f451480') and head[:28] == tail[:28],
                'Unexpected nested resource header')
        require(struct.unpack_from('<I', head, 8)[0] == origin+offset,
                'Nested header address does not match its directory')
        require(struct.unpack_from('<I', head, 12)[0] == size-64, 'Nested size mismatch')
        require(head[28:] == bytes(4), 'Unexpected nested header checksum')
        checksummed = tail[28:] != bytes(4)
        if checksummed:
            require(sum32(payload[offset:end]) == 0, 'Bad nested checksum')
        _, entries = directory(payload, offset+32, origin, end-32)
        struct.pack_into('<I', out, record, origin+offset+delta)
        for at in (offset, end-32):
            out[at+2:at+4] = bytes.fromhex('1440')
            struct.pack_into('<I', out, at+8, origin+offset+delta)
        for at, start, length in entries:
            struct.pack_into('<I', out, at, origin+start+delta)
            leaves.append((start, length))
        if checksummed:
            out[end-4:end] = bytes(4)
            struct.pack_into('<I', out, end-4, (-sum32(out[offset:end])) & 0xffffffff)
        # Parse using the new origin, independently checking every relocated pointer.
        _, relocated = directory(out, offset+32, new_address+32, end-32)
        require(relocated == entries, 'Nested relocation changed resource offsets')
        if checksummed:
            require(sum32(out[offset:end]) == 0, 'Rebuilt nested checksum failed')
    for start, length in leaves:
        require(out[start:start+length] == payload[start:start+length], 'Leaf resource changed')
    _, relocated_banks = directory(out, 0, new_address+32, len(payload))
    require(relocated_banks == banks, 'Common relocation changed bank positions')
    out.extend(b'\xff' * (target_size-len(out)))
    return bytes(out), {'banks': len(banks), 'unchanged_leaf_records': len(leaves),
                        'delta': delta, 'sha256': sha256(out)}


def jpeg_pixels(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return image.size, image.mode, image.tobytes()


def pack_pictures(payload, old_address, new_address, target_size, jpegtran):
    origin = old_address+32
    first, entries = directory(payload, 0, origin, len(payload))
    require(first == 0x2fe0 and len(entries) == 116, 'Unexpected E148 picture directory')
    out = bytearray(b'\xff' * target_size)
    out[:first] = payload[:first]
    cursor = first
    cache, records, boundaries = {}, [], {}
    jpeg_count = 0
    for at, offset, size in entries:
        source = payload[offset:offset+size]
        key = sha256(source)
        if key not in cache:
            data = source
            if source[:2] == b'\xff\xd8':
                result = subprocess.run([str(jpegtran), '-copy', 'all', '-optimize'], input=source,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                data = result.stdout
                require(jpeg_pixels(data) == jpeg_pixels(source), 'JPEG optimisation changed decoded pixels')
                jpeg_count += 1
            length = (len(data)+511)//512*512
            require(cursor+length <= target_size, 'Lossless pictures exceed OM-5 I slot')
            out[cursor:cursor+len(data)] = data
            cache[key] = (cursor, length)
            cursor += length
        start, length = cache[key]
        boundaries[offset+size] = start+length
        boundaries[offset] = start
        struct.pack_into('<4I', out, at, new_address+32+start, length, 0, 0)
        records.append({'index': at//16, 'source_sha256': key, 'offset': start, 'bytes': length,
                        'sha256': sha256(out[start:start+length])})
    for at in range(0, first, 16):
        pointer, size, _, _ = struct.unpack_from('<4I', payload, at)
        if pointer and not size:
            require(pointer-origin in boundaries, 'Empty picture pointer lacks a known boundary')
            struct.pack_into('<I', out, at, new_address+32+boundaries[pointer-origin])
    _, packed = directory(out, 0, new_address+32, len(out))
    require(len(packed) == len(entries), 'Picture record count changed')
    # Check each ID after packing, including aliases, rather than only cached JPEGs.
    for (at, old_start, old_size), (new_at, start, size) in zip(entries, packed):
        require(at == new_at, 'Picture ID changed')
        old, new = payload[old_start:old_start+old_size], bytes(out[start:start+size])
        if old[:2] == b'\xff\xd8':
            require(jpeg_pixels(old) == jpeg_pixels(new), 'Packed JPEG changed pixels')
        else:
            require(old == new, 'Opaque picture resource changed')
    return bytes(out), {'records': records, 'unique_jpegs_optimised': jpeg_count,
                        'used_bytes': cursor, 'capacity': target_size,
                        'free_bytes': target_size-cursor, 'sha256': sha256(out)}
