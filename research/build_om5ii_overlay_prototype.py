#!/usr/bin/env python3
"""Build a non-installable OM-5 II main-image prototype with stock LZ4 spans.

The prototype has a post-load RAM overlay for the original Section 6/7 edits.
It is for static review and emulator work; instruction-cache synchronization,
task concurrency and physical boot have not been qualified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from oly_compress import expand_image, repack_image, spans  # noqa: E402
from oly_container import parse, reconstruct, replace_payload  # noqa: E402
from oly_patch import preserved_spans  # noqa: E402
from om5ii_overlay_inventory import BASE, COMPRESSED_OFFSETS, inventory  # noqa: E402

HOOK = 0x6081e2f1
OVERLAY = 0x60845d00
OVERLAY_END = 0x60847000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def emit_data(rows, stock, patched, path):
    lines = ['.section .overlay_data,"a"', '.balign 4', '.globl overlay_table', 'overlay_table:']
    for i, row in enumerate(rows):
        address, size = int(row['address'], 16), row['bytes']
        lines.append(f' .long {hex(address + 0x40000000)}, before_{i}, after_{i}, {size}')
    for i, row in enumerate(rows):
        at, size = int(row['address'], 16) - BASE, row['bytes']
        for label, data in ((f'before_{i}', stock[at:at + size]),
                            (f'after_{i}', patched[at:at + size])):
            lines.append(label + ':')
            for pos in range(0, size, 16):
                lines.append(' .byte ' + ','.join(hex(x) for x in data[pos:pos + 16]))
    path.write_text('\n'.join(lines) + '\n')


def build(args):
    report = inventory(args.patch, args.stock, args.decoded)
    source = Path(args.stock).read_bytes()
    blocks = parse(source)
    stock_blocks = {b.kind: b.payload for b in blocks}
    stock = stock_blocks[0x100]
    stock_expanded = expand_image(stock)
    patched = Path(args.decoded).read_bytes()
    rows = report['ranges']
    first = {'ext6', 'ext7', 'state'}
    rows = sorted(rows, key=lambda row: (row['name'] not in first, int(row['address'], 16)))
    if len(rows) != 16 or any(row['bytes'] == 0 for row in rows):
        raise ValueError('Unexpected overlay layout')

    out = Path(args.out)
    if out.exists():
        raise ValueError('Output directory must be new')
    out.mkdir(parents=True)
    emit_data(rows, stock_expanded, patched, out / 'overlay_data.s')
    here = Path(__file__).resolve().parent
    as_exe, ld_exe, objcopy = (str(Path(x).resolve()) for x in (args.assembler, args.linker, args.objcopy))
    subprocess.run([as_exe, '-o', str(out / 'overlay.o'), str(here / 'om5ii_overlay.s')], check=True)
    subprocess.run([as_exe, '-o', str(out / 'overlay_data.o'), str(out / 'overlay_data.s')], check=True)
    subprocess.run([ld_exe, '--no-relax', '-T', str(here / 'om5ii_overlay.ld'), '-o', str(out / 'overlay.elf'),
                    str(out / 'overlay.o'), str(out / 'overlay_data.o')], check=True)
    for section in ('overlay_hook', 'overlay'):
        subprocess.run([objcopy, '-O', 'binary', '--only-section=.' + section,
                        str(out / 'overlay.elf'), str(out / (section + '.bin'))], check=True)
    hook_bytes = (out / 'overlay_hook.bin').read_bytes()
    overlay_bytes = (out / 'overlay.bin').read_bytes()
    if len(hook_bytes) != 6 or len(overlay_bytes) > OVERLAY_END - OVERLAY:
        raise ValueError(f'Hook or overlay exceeds allocation: {len(hook_bytes)}, {len(overlay_bytes)}')
    if stock_expanded[HOOK - BASE:HOOK - BASE + 6] != bytes.fromhex('fcdc97ebb360'):
        raise ValueError('Task 92 displaced instruction differs from audited stock')
    # Verify linked pointers and every source byte, not only the source file
    # used to assemble them. Locate the table by its first uncached target.
    first_target = (int(rows[0]['address'], 16) + 0x40000000).to_bytes(4, 'little')
    table_at = overlay_bytes.find(first_target)
    if not 0 <= table_at < 256:
        raise ValueError('Linked overlay table was not found near installer code')
    for i, row in enumerate(rows):
        entry = overlay_bytes[table_at + 16 * i:table_at + 16 * (i + 1)]
        if len(entry) != 16:
            raise ValueError('Truncated linked overlay table')
        target, before_ptr, after_ptr, size = (int.from_bytes(entry[j:j + 4], 'little') for j in (0, 4, 8, 12))
        address, expected_size = int(row['address'], 16), row['bytes']
        if target != address + 0x40000000 or size != expected_size:
            raise ValueError(f"Linked table destination differs: {row['name']}")
        at = address - BASE
        for ptr, expected in ((before_ptr, stock_expanded[at:at + size]),
                              (after_ptr, patched[at:at + size])):
            source_at = ptr - OVERLAY
            if source_at < 0 or overlay_bytes[source_at:source_at + size] != expected:
                raise ValueError(f"Linked overlay bytes differ: {row['name']}")

    candidate = bytearray(patched)
    for offset, _, size in spans(stock):
        candidate[offset:offset + size] = stock_expanded[offset:offset + size]
    for address, data in ((HOOK, hook_bytes), (OVERLAY, overlay_bytes)):
        at = address - BASE
        if any(byte != 0xff for byte in candidate[at:at + len(data)]) and address == OVERLAY:
            raise ValueError('Overlay allocation is not empty')
        candidate[at:at + len(data)] = data
    expanded = bytes(candidate)
    stored = repack_image(stock, expanded, split=True, literal_limit=0)
    equality = preserved_spans(stock, expanded, stored, [hex(x) for x in COMPRESSED_OFFSETS])
    if expand_image(stored) != expanded:
        raise ValueError('Candidate main round trip failed')
    runtime = bytearray(expanded)
    expected_runtime = bytearray(patched)
    for row in rows:
        at, size = int(row['address'], 16) - BASE, row['bytes']
        runtime[at:at + size] = patched[at:at + size]
    for address, data in ((HOOK, hook_bytes), (OVERLAY, overlay_bytes)):
        expected_runtime[address - BASE:address - BASE + len(data)] = data
    if runtime != expected_runtime:
        raise ValueError('Post-overlay main differs from the current full patch')

    (out / 'expanded-main.bin').write_bytes(expanded)
    (out / 'stored-main.bin').write_bytes(stored)
    osd = stock_blocks[0x101]
    osd_variant = 'stock'
    if args.modified_osd:
        osd = Path(args.modified_osd).read_bytes()
        osd_spec = json.loads(Path(args.patch).read_text())['components']['0x101']
        if sha(stock_blocks[0x101]) != osd_spec['before_sha256'] or sha(osd) != osd_spec['after_sha256']:
            raise ValueError('Modified OSD does not match the current source definition')
        osd_variant = 'modified'
        (out / 'modified-osd.bin').write_bytes(osd)
    composed = [replace_payload(block, stored) if block.kind == 0x100 else
                replace_payload(block, osd) if block.kind == 0x101 else block for block in blocks]
    image = reconstruct(composed)
    verified = parse(image)
    if [block.payload for block in verified] != [block.payload for block in composed]:
        raise ValueError('In-memory full-container round trip failed')
    if any(before.header != after.header or before.trailer[:28] != after.trailer[:28]
           for before, after in zip(blocks, verified)):
        raise ValueError('In-memory full-container metadata changed')
    summary = {'schema': 'om5ii-overlay-prototype/1', 'stock_sha256': sha(source),
               'source_patch_expanded_sha256': sha(patched), 'expanded_main_sha256': sha(expanded),
               'stored_main_sha256': sha(stored), 'hook_address': hex(HOOK), 'hook_bytes': len(hook_bytes),
               'overlay_address': hex(OVERLAY), 'overlay_bytes': len(overlay_bytes),
               'overlay_range_count': len(rows), 'overlay_data_bytes': report['overlay_data_bytes'],
               'preserved_olycompress_spans': equality, 'installable': False,
               'post_overlay_matches_current_patch': True, 'osd_variant': osd_variant,
               'osd_sha256': sha(osd), 'full_container_sha256': sha(image),
               'full_container_bytes': len(image), 'camera_tested': False}
    (out / 'build.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ('hook_bytes', 'overlay_bytes', 'overlay_range_count',
                                             'preserved_olycompress_spans', 'installable')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('patch', 'stock', 'decoded', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--modified-osd', type=Path,
                        help='optional rebuilt 0x101 payload; preserves the full icon treatment')
    parser.add_argument('--as', dest='assembler', required=True)
    parser.add_argument('--ld', dest='linker', required=True)
    parser.add_argument('--objcopy', required=True)
    build(parser.parse_args())


if __name__ == '__main__':
    main()
