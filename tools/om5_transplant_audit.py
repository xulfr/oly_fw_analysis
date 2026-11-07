#!/usr/bin/env python3
"""Compare pinned E148 donor / E144 recipient packages for a donor-first port.

Read-only: emits evidence, never an update package or a compatibility verdict.
Addresses in a container are logical addresses, not verified physical NAND
partitions. In particular, component 010e's zero address is not a flash extent.
"""
import argparse
import json
from pathlib import Path
import re
import struct

from oly_container import parse, sha256
from oly_compress import expand_image

BASE = 0x60021020
KINDS = (0x100, 0x101, 0x106, 0x10e, 0x102)
PINS = {
    'E144': ('a0c91f3ac7caaf0925b2af609e711183cf3b5982b3333224bcef26c0c5943d11',
             '692f1b9eb6f89fe6467ade3c88092305b0423ac1aa6ba759eac83b6cd5d36487'),
    'E148': ('9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637',
             '7ae7d4c60990cc859c070e0ceb6cbe612f9c5b260713f2f1256e51d137851c61'),
}
LIBRARY_OFFSET, LIBRARY_SIZE, LIBRARY_BASE = 0x1681fe0, 0x1800, 0x47000800
MEMSET = {'E144': 0x4700114b, 'E148': 0x47001154}
# First memset in each build's internal-charger register routine, independently
# disassembled. The targets are absolute library addresses, not relocations.
CHARGER_CALL = {'E144': 0x600621dc, 'E148': 0x6006249b}


def read_image(path, model):
    raw = path.read_bytes()
    if sha256(raw) != PINS[model][0]:
        raise ValueError(f'{model}: requires the pinned official package')
    blocks = parse(raw)
    if tuple(b.kind for b in blocks) != KINDS:
        raise ValueError(f'{model}: component order changed')
    if any(b.header[2:4].hex() != model[1:] + '0' for b in blocks):
        raise ValueError(f'{model}: wrong container model')
    expanded = expand_image(blocks[0].payload)
    if sha256(expanded) != PINS[model][1]:
        raise ValueError(f'{model}: expanded main hash changed')
    return blocks, expanded


def extent(block):
    if block.address == 0:
        return None
    return (block.address, block.address + len(block.payload) + 64)


def overlaps(blocks):
    """Logical container overlaps; touching endpoints are allowed."""
    result = []
    for i, left in enumerate(blocks):
        a = extent(left)
        if a is None:
            continue
        for right in blocks[i+1:]:
            b = extent(right)
            if b is None:
                continue
            lo, hi = max(a[0], b[0]), min(a[1], b[1])
            if lo < hi:
                result.append({'kinds': [hex(left.kind), hex(right.kind)],
                               'start': hex(lo), 'end': hex(hi), 'bytes': hi-lo})
    return result


def library_facts(model, main):
    call = CHARGER_CALL[model]
    instruction = main[call-BASE:call-BASE+7]
    if instruction[0] != 0xdd or instruction[5:] != b'\xa0\x08':
        raise ValueError('Charger library-call form changed')
    target = (call + int.from_bytes(instruction[1:5], 'little', signed=True)) & 0xffffffff
    if target != MEMSET[model]:
        raise ValueError('Charger library-call target changed')
    library = main[LIBRARY_OFFSET:LIBRARY_OFFSET+LIBRARY_SIZE]
    if library[target-LIBRARY_BASE:target-LIBRARY_BASE+9] != bytes.fromhex('a500c8721482f8c208'):
        raise ValueError('Native memset entry changed')
    return {'offset': hex(LIBRARY_OFFSET), 'bytes': len(library),
            'sha256': sha256(library), 'runtime_base': hex(LIBRARY_BASE),
            'charger_call': hex(call), 'memset_entry': hex(target)}


def describe(model, blocks, main):
    # One explicit jump in the first reset page; inspect the instruction rather
    # than deriving the run-time base from the container address.
    matches = list(re.finditer(rb'\xfc\xdc(.{4})\xf0\xf4', main[:0x400], re.DOTALL))
    if len(matches) != 1:
        raise ValueError('Reset head must have one absolute jump')
    jump = matches[0]
    patterns = [{'address': hex(BASE+m.start()), 'pattern': m.group().decode()}
                for m in re.finditer(rb'[SEGHWAMVDTIKN]\d{3}\?{4}BIN', main)]
    return {
        'package_sha256': PINS[model][0], 'expanded_main_sha256': sha256(main),
        'reset_jump': {'instruction': hex(BASE+jump.start()),
                       'target': hex(struct.unpack('<I', jump.group(1))[0])},
        'components': [{'kind': hex(b.kind), 'model': b.header[2:4].hex(),
                        'address': hex(b.address), 'payload_bytes': len(b.payload),
                        'logical_extent': None if extent(b) is None else list(map(hex, extent(b))),
                        'sha256': sha256(b.payload)} for b in blocks],
        'startup_library': library_facts(model, main),
        'update_filename_patterns': patterns,
    }


def audit(recipient, donor):
    r_blocks, r_main = read_image(recipient, 'E144')
    d_blocks, d_main = read_image(donor, 'E148')
    r = {b.kind: b for b in r_blocks}
    d = {b.kind: b for b in d_blocks}
    # Evaluate tempting partial substitutions without constructing an image.
    scenarios = {}
    for name, donor_kinds in (
        ('recipient_stock', set()), ('donor_stock', set(KINDS)),
        ('donor_main_and_osd', {0x100, 0x101}),
        ('donor_resources_with_recipient_osd', {0x100, 0x106, 0x102}),
        ('donor_except_recipient_010e', set(KINDS)-{0x10e}),
    ):
        choice = [d[k] if k in donor_kinds else r[k] for k in KINDS]
        scenarios[name] = {'logical_overlaps': overlaps(choice),
                           'compatible': None,
                           'note': 'No overlaps does not establish driver, resource, settings or updater compatibility.'}
    return {
        'schema': 'om5-transplant-audit/1', 'direction': 'E148 donor -> E144 hardware',
        'status': 'research_only_not_a_port', 'hardware_compatibility_established': False,
        'recipient': describe('E144', r_blocks, r_main),
        'donor': describe('E148', d_blocks, d_main),
        'component_identity': {hex(k): r[k].payload == d[k].payload for k in KINDS},
        'startup_library_different_bytes': sum(a != b for a, b in zip(
            r_main[LIBRARY_OFFSET:LIBRARY_OFFSET+LIBRARY_SIZE],
            d_main[LIBRARY_OFFSET:LIBRARY_OFFSET+LIBRARY_SIZE])),
        'scenarios': scenarios,
        'unresolved': [
            'Recipient bootloader acceptance and the complete logical-to-physical flash map.',
            'E148 main and E144 controller/component-010e protocol compatibility.',
            'Board pin routing, USB/charging, sensor/ISP, IBIS and lens initialisation.',
            'E144 retained settings and per-camera calibration consumed by E148 code.',
            'Physical boot of the corrected E148 HSL/WB/ND64 donor itself.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipient', type=Path, required=True)
    parser.add_argument('--donor', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New JSON report file')
    args = parser.parse_args()
    report = audit(args.recipient, args.donor)
    with args.out.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print('Recorded donor/recipient dependencies; hardware compatibility is not established.')


if __name__ == '__main__':
    main()
