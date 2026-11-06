"""E148 1100 native loader boundaries; offsets are expanded-main addresses.

The compressed storage span is NOT the uncompressed section's loaded end.
Do not infer executable space from FF padding or the next section's start.
"""
import hashlib
import struct

BASE = 0x60021020
STOCK_SHA = '7ae7d4c60990cc859c070e0ceb6cbe612f9c5b260713f2f1256e51d137851c61'
SUBMITTED = 0xa26e2698
READY = 0xa26e2694


def loader_regions(stock):
    """Read the descriptors and native end-selector immediates from pinned stock."""
    if hashlib.sha256(stock).hexdigest() != STOCK_SHA:
        raise ValueError('E148 boot audit requires the pinned expanded 1100 image')
    def read(address, size):
        return stock[address - BASE:address - BASE + size]
    # The selector bounds IDs 1..10, subtracts one, and dispatches through this table.
    if read(0x600463af, 22) != bytes.fromhex('04a001c063a00ac15f28ff54fcdc68780460f380f0f4'):
        raise ValueError('E148 native end selector changed')
    regions = []
    for i in range(10):
        start, source, compressed = struct.unpack('<III', read(0x600284fc + 12*i, 12))
        target, = struct.unpack('<I', read(0x60047868 + 4*i, 4))
        instruction = read(target, 6)
        if instruction[:2] != b'\xfc\xcc':
            raise ValueError('Unexpected native section-end instruction')
        end, = struct.unpack('<I', instruction[2:])
        if not BASE <= start < end <= BASE + len(stock):
            raise ValueError('Invalid native section extent')
        regions.append({'id': i+1, 'start': start, 'end': end,
                        'source': source, 'compressed': compressed})
    return regions


def require_loaded_range(regions, address, size, name):
    owner = next((r for r in regions if r['start'] <= address and
                  address + size <= r['end']), None)
    if size <= 0 or owner is None:
        raise ValueError(f'{name}: {address:#x}..{address+size:#x} is not wholly '
                         'inside a native loaded section')
    return owner['id']


def audit_ranges(stock, ranges):
    regions = loader_regions(stock)
    return {r['name']: require_loaded_range(regions, int(r['address'], 16),
                                            r['bytes'], r['name'])
            for r in ranges if r['component'] == '0x100' and 'address' in r}
