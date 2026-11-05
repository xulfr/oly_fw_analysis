#!/usr/bin/env python3
"""Audit the current OM-5 II edits that would need a post-load RAM overlay.

Reads locally supplied firmware and decoded patch images. Does not create a
firmware image or include patch bytes in its report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from oly_compress import expand_image, spans  # noqa: E402
from oly_container import parse  # noqa: E402

BASE = 0x60021020
COMPRESSED_OFFSETS = (0x825fe0, 0xc9d7e0)
UPDATER_START, UPDATER_END = 0x60ce5b00, 0x60ce7c00


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(patch, stock, decoded):
    spec = json.loads(Path(patch).read_text())
    source = Path(stock).read_bytes()
    if sha(source) != spec['stock']['sha256']:
        raise ValueError('Official stock file hash differs from patch definition')
    main = next(b.payload for b in parse(source) if b.kind == 0x100)
    wanted = spec['components']['0x100']
    if sha(main) != wanted['stored_before_sha256']:
        raise ValueError('Stock main payload differs from patch definition')
    expanded = expand_image(main)
    patched = Path(decoded).read_bytes()
    if sha(expanded) != wanted['before_sha256'] or sha(patched) != wanted['after_sha256']:
        raise ValueError('Expanded main image differs from patch definition')
    found = {offset: size for offset, _, size in spans(main)}
    if set(found) != set(COMPRESSED_OFFSETS):
        raise ValueError('Unexpected E148 compressed-span map')

    simulated = bytearray(expanded)
    rows = []
    for row in spec['ranges']:
        if row['component'] != '0x100' or 'address' not in row:
            continue
        address, size = int(row['address'], 16), row['bytes']
        at = address - BASE
        owner = next((offset for offset, length in found.items() if offset <= at and at + size <= offset + length), None)
        if owner is None:
            continue
        before, after = expanded[at:at + size], patched[at:at + size]
        if sha(before) != row['before_sha256'] or sha(after) != row['after_sha256']:
            raise ValueError(f"Range {row['name']} differs from the manifest")
        if address < UPDATER_END and address + size > UPDATER_START:
            raise ValueError(f"Range {row['name']} overlaps the updater")
        simulated[at:at + size] = after
        rows.append({'name': row['name'], 'address': row['address'], 'bytes': size,
                     'span_offset': hex(owner), 'after_sha256': sha(after)})

    for offset in COMPRESSED_OFFSETS:
        size = found[offset]
        if simulated[offset:offset + size] != patched[offset:offset + size]:
            raise ValueError(f'Overlay ranges do not reproduce patched span {offset:#x}')
    return {'schema': 'om5ii-overlay-inventory/1', 'stock_sha256': sha(source),
            'patched_expanded_sha256': sha(patched), 'range_count': len(rows),
            'overlay_data_bytes': sum(row['bytes'] for row in rows), 'ranges': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patch', type=Path, required=True)
    parser.add_argument('--stock', type=Path, required=True)
    parser.add_argument('--decoded', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.patch, args.stock, args.decoded)
    if args.out.exists():
        parser.error('Output path must be new')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(f"Verified {report['range_count']} RAM-overlay ranges ({report['overlay_data_bytes']} bytes)")


if __name__ == '__main__':
    main()
