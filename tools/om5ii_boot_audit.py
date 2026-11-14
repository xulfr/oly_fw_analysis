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


# Section 10 loads last, after the section-7 card updater is running. The flash image is 0xff from its
# stock end to the resident library image at 0x616a3000, and the loader takes its copy length from the
# end selector alone (0x60046452..0x60046483: size = end - start; the only other selector users pass 10
# to bound the bus monitor, which then covers the same bytes). A patch may therefore declare ONE edit,
# `section_extent_10`, of that constant. Nothing else may move a section end.
EXTENT_EDIT = 'section_extent_10'
EXTENT_LIMIT = 0x616a3000


def extended_regions(stock, data_edits):
    regions = loader_regions(stock)
    edits = [e for e in data_edits if e['name'].startswith('section_extent')]
    if not edits:
        return regions
    if len(edits) != 1 or edits[0]['name'] != EXTENT_EDIT or edits[0].get('component') != '0x100':
        raise ValueError('Only one section_extent_10 edit is allowed')
    region = regions[9]
    at = 0x60047868 + 4*9 - BASE
    target, = struct.unpack('<I', stock[at:at + 4])
    if int(edits[0]['address'], 16) != target + 2 or len(bytes.fromhex(edits[0]['after'])) != 4:
        raise ValueError('section_extent_10 must replace the end operand of the native selector')
    end, = struct.unpack('<I', bytes.fromhex(edits[0]['after']))
    if not region['end'] < end <= EXTENT_LIMIT or (end - region['start']) % 0x800:
        raise ValueError('section_extent_10 outside the free flash span or not 2 KiB aligned')
    if stock[region['end'] - BASE:end - BASE].count(0xff) != end - region['end']:
        raise ValueError('section_extent_10 covers stock bytes')
    region['stock_end'], region['end'] = region['end'], end
    return regions


def audit_ranges(stock, ranges, data_edits=()):
    regions = extended_regions(stock, data_edits)
    return {r['name']: require_loaded_range(regions, int(r['address'], 16),
                                            r['bytes'], r['name'])
            for r in ranges if r['component'] == '0x100' and 'address' in r
            # the extent operand is resident boot code, checked by extended_regions
            and r['name'] != EXTENT_EDIT}
