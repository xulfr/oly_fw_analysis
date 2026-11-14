#!/usr/bin/env python3
"""Re-record a patch.json's reference hashes after a deliberate source change.

`oly_patch.py` only builds when every assembled range, component and package
matches the hashes recorded in patch.json. After editing a source file those
references must be recorded again. This tool does one lenient build to collect
the new section sizes and hashes, rewrites patch.json, and then runs the normal
strict build as the check. Stock (`before`) hashes are always taken from the
user's hash-pinned stock file, never from the patch.

    python3 tools/oly_patch_record.py patches/hsl/om-5-ii --stock E148.BIN --work /tmp/new-dir

It writes no install file and never talks to a camera. Review the diff.
"""
import argparse, json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import oly_patch
from oly_patch import sha, kind_of

LENIENT = ('Built bytes differ', 'Section size differs', 'Patched component', 'Repacked component',
           'Package sha256 differs', 'Original bytes differ', 'Install output blocked')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('patch'); p.add_argument('--stock', required=True); p.add_argument('--work', required=True)
    a = p.parse_args()
    patch = Path(a.patch).resolve(); work = Path(a.work).resolve()
    strict = oly_patch.require
    def lenient(condition, message):
        if not condition and not message.startswith(LENIENT):
            strict(condition, message)
    spec_path = patch / 'patch.json'
    spec = json.loads(spec_path.read_text())
    # pass 1: sizes of assembled sections (declared sizes may be stale)
    oly_patch.require = lenient
    # the lenient pass must not trip the layout audit on placeholder sizes
    first = oly_patch.build(patch, a.stock, work / 'pass1', decoded=True)
    stock_main = oly_patch.expand_image(next(b for b in oly_patch.parse(Path(a.stock).read_bytes()) if b.kind == 0x100).payload)
    for group in spec.get('assembly', []):
        base = int(spec['components'][group['component']]['cpu_base'], 16)
        for name, address in group['sections'].items():
            data = (work / 'pass1' / 'assembly' / group['name'] / (name + '.bytes')).read_bytes()
            row = next(r for r in spec['ranges'] if r['name'] == name and r.get('address') == address)
            at = int(address, 16) - base
            row.update(bytes=len(data), before_sha256=sha(stock_main[at:at + len(data)]), after_sha256=sha(data))
    spec_path.write_text(json.dumps(spec, indent=2) + '\n')
    # pass 2: component and package hashes with the corrected ranges
    second = oly_patch.build(patch, a.stock, work / 'pass2', decoded=True)
    for kind, got in second['components'].items():
        c = spec['components'][kind]
        c['after_sha256'] = got['expanded_sha256']
        if 'stored_after_sha256' in c:
            c['stored_after_sha256'] = got['sha256']
    if spec.get('package') and 'sha256' in spec['package']:
        spec['package']['sha256'] = second['package_sha256']
    spec_path.write_text(json.dumps(spec, indent=2) + '\n')
    oly_patch.require = strict
    final = oly_patch.build(patch, a.stock, work / 'strict', decoded=True)
    print(json.dumps({'package_sha256': final['package_sha256'], 'components': final['components']}, indent=2))


if __name__ == '__main__':
    main()
