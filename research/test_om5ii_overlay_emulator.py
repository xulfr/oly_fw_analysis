#!/usr/bin/env python3
"""Run the post-load overlay worker in an existing E148 OM-Emu debug session.

This tests native instructions and memory writes in the emulator. OM-Emu does
not model the physical loader, caches, other CPU, or camera startup sequence.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[2] / 'phase4-om5ii-hsl' / 'scripts'
sys.path.insert(0, str(LAB))
import emu  # noqa: E402
from om5ii_overlay_inventory import BASE, inventory  # noqa: E402

OVERLAY = 0x60845d00
WORKER = 0x60845d10
ENTRY = 0x60845d00
RETURN = 0x6081e2f7
LOADED_BITS = 0xa26e2694


def debug(body):
    result = emu.post('/api/debug', body)
    if result.get('error'):
        raise ValueError(result['error'])
    return result


def read(address, size):
    return bytes.fromhex(debug({'op': 'read', 'addr': hex(address), 'size': size})['hex'])


def write(address, data):
    debug({'op': 'write', 'addr': hex(address), 'hex': data.hex()})
    if read(address, len(data)) != data:
        raise ValueError(f'Emulator write/readback differs at {address:#x}')


def run_entry():
    hot = '0x602d000d'
    debug({'op': 'break', 'pcs': [hot]})
    threading.Thread(target=lambda: emu.key('info'), daemon=True).start()
    parked = debug({'op': 'cont', 'maxMs': 8000})
    if parked.get('stop') != 'break':
        raise ValueError(f'Could not park emulator task: {parked}')
    saved = debug({'op': 'regs'})['regs']
    sp = (int(saved['sp'], 16) - 0x3000) & ~3
    debug({'op': 'setRegs', 'regs': {'pc': hex(ENTRY), 'sp': hex(sp)}})
    debug({'op': 'break', 'pcs': [hex(RETURN)]})
    result = debug({'op': 'cont', 'maxMs': 5000})
    if result.get('stop') != 'break':
        raise ValueError(f'Overlay entry did not reach stock continuation: {result}')
    regs = debug({'op': 'regs'})['regs']
    for name in ('d0', 'd1', 'd2', 'd3', 'a1', 'a2', 'a3', 'psw'):
        if regs[name] != saved[name]:
            raise ValueError(f'Overlay entry changed {name}')
    if int(regs['a0'], 16) != 0x60b3eb97 or int(regs['sp'], 16) != sp:
        raise ValueError('Overlay entry did not replay stock instruction and stack')
    debug({'op': 'break', 'pcs': []})
    writable = ('pc', 'sp', 'psw', 'd0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3',
                'mdr', 'lir', 'lar', 'e0', 'e1', 'e2', 'e3', 'e4', 'e5', 'e6', 'e7', 'mcrh', 'mcrl', 'mcvf')
    debug({'op': 'setRegs', 'regs': {name: value for name, value in saved.items() if name in writable}})
    debug({'op': 'resume'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('patch', 'stock', 'decoded', 'prototype'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--entry', action='store_true', help='test task-92 hook entry and stock continuation')
    parser.add_argument('--reject-one', action='store_true',
                        help='change one stock target byte and require the all-or-nothing preflight to reject')
    args = parser.parse_args()
    report = inventory(args.patch, args.stock, args.decoded)
    prototype = Path(args.prototype)
    summary = json.loads((prototype / 'build.json').read_text())
    if summary['source_patch_expanded_sha256'] != report['patched_expanded_sha256']:
        raise ValueError('Prototype and current patch differ')
    source = Path(args.stock).read_bytes()
    sys.path.insert(0, str(HERE.parents[0] / 'tools'))
    from oly_container import parse  # noqa: E402
    from oly_compress import expand_image  # noqa: E402
    stock_main = expand_image(next(b.payload for b in parse(source) if b.kind == 0x100))
    patched_main = Path(args.decoded).read_bytes()

    write(OVERLAY, (prototype / 'overlay.bin').read_bytes())
    for row in report['ranges']:
        address, size = int(row['address'], 16), row['bytes']
        write(address, stock_main[address - BASE:address - BASE + size])
    if args.reject_one:
        address = int(report['ranges'][-1]['address'], 16)
        write(address, bytes([read(address, 1)[0] ^ 1]))
    loaded = int.from_bytes(read(LOADED_BITS, 4), 'little')
    write(LOADED_BITS, (loaded | 0x40).to_bytes(4, 'little'))
    if args.prepare_only:
        print('Prepared emulator memory for native overlay call')
        return

    if args.entry:
        run_entry()
    else:
        env = dict(os.environ, CALL_MASK='0x00', CALL_FRAME='0')
        result = subprocess.run([sys.executable, str(LAB / 'callfn.py'), hex(WORKER), '{}'],
                                check=True, env=env, capture_output=True, text=True)
        if 'stop break' not in result.stdout:
            raise ValueError(f'Native worker did not return: {result.stdout}')
    for row in report['ranges']:
        address, size = int(row['address'], 16), row['bytes']
        expected = (patched_main if not args.reject_one else stock_main)[address - BASE:address - BASE + size]
        if args.reject_one and row is report['ranges'][-1]:
            expected = bytes([expected[0] ^ 1]) + expected[1:]
        if read(address, size) != expected:
            raise ValueError(f"Native overlay produced unexpected bytes at {row['name']}")
    verdict = 'rejected without changes' if args.reject_one else 'installed'
    print(f"Native emulator overlay {verdict}: {report['range_count']} ranges checked")


if __name__ == '__main__':
    main()
