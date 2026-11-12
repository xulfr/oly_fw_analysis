#!/usr/bin/env python3
"""Build an experimental OM-5 I candidate from the corrected OM-5 II HSL donor.

Uses both official files supplied by the owner. Retains the recipient's five
component addresses/sizes, controller component and untouched flash gaps.
Does not access a camera. An install file requires --write-untested-package.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from oly_container import parse, reconstruct, replace_payload, sha256
from oly_compress import expand_image, repack_image
from oly_patch import build as build_donor, KNOWN_BOOT_FAILURES, require
from om5_donor_resources import relocate_common, pack_pictures
from om5_transplant_audit import BASE, KINDS, read_image, extent, overlaps, LIBRARY_OFFSET, LIBRARY_SIZE

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT/'patches/hsl/om-5-ii'
# Each site is an instruction boundary inspected in both pinned images. Do not
# replace all occurrences of these numbers: some are misaligned pointers or
# floating-point constants, including 0x45c20000 at 0x6063fd7f.
LAYOUT_EDITS = [
    (0x60178e3c, 'fcdc', 0x42d40000, 0x42ea0000, 'common directory'),
    (0x60178d85, 'fcdc', 0x45c20000, 0x45cc0000, 'picture directory'),
    (0x60178db4, 'fcdc', 0x455e0000, 0x45a40000, 'resident mode-17 directory'),
    (0x60178d56, 'fcdc', 0x46620000, 0x463c0000, 'resident sound directory'),
    (0x60179dd3, 'fcdd', 0x46620000, 0x463c0000, 'sound offset origin'),
    (0x60179de7, 'fcdc', 0x46620000, 0x463c0000, 'sound reload origin'),
    (0x6002175d, 'fcce', 0x46620000, 0x463c0000, 'range lower bound'),
    (0x600218d0, 'fcca', 0x46620000, 0x463c0000, 'range lower bound'),
    (0x60021767, 'fcda', 0x46c40000, 0x469e0000, 'range upper bound'),
    (0x6002178a, 'fcc9', 0x46c40000, 0x469e0000, 'range upper bound'),
    (0x600217e9, 'fcce', 0x46c40000, 0x469e0000, 'next range lower bound'),
    (0x600218d8, 'fcca', 0x46c40000, 0x469e0000, 'range upper bound'),
    (0x6002191c, 'fcca', 0x46c40000, 0x469e0000, 'next range lower bound'),
    (0x6005b7eb, 'fccb', 0x46c40000, 0x469e0000, 'flash range limit'),
    (0x60021772, 'fccc', 0x86620000, 0x863c0000, 'alias lower bound'),
    (0x600218e3, 'fcca', 0x86620000, 0x863c0000, 'alias lower bound'),
    (0x6002177c, 'fcda', 0x86c40000, 0x869e0000, 'alias upper bound'),
    (0x60021798, 'fcc9', 0x86c40000, 0x869e0000, 'alias upper bound'),
    (0x600217fe, 'fccc', 0x86c40000, 0x869e0000, 'next alias lower bound'),
    (0x600218eb, 'fcca', 0x86c40000, 0x869e0000, 'alias upper bound'),
    (0x6002192c, 'fcca', 0x86c40000, 0x869e0000, 'next alias lower bound'),
]


def adapt_main(donor, recipient):
    out = bytearray(donor)
    edits = []

    def edit(address, before, after, purpose):
        at = address-BASE
        require(len(before) == len(after) and out[at:at+len(before)] == before,
                f'Unexpected donor bytes at {address:#x}')
        out[at:at+len(after)] = after
        edits.append({'address': hex(address), 'before': before.hex(), 'after': after.hex(),
                      'purpose': purpose})

    for address, opcode, old, new, purpose in LAYOUT_EDITS:
        op = bytes.fromhex(opcode)
        edit(address, op+struct.pack('<I', old), op+struct.pack('<I', new), purpose)
    for address, old, new in (
        (0x6007e788, b'OM-5MKII\0', b'OM-5\0\0\0\0\0'),
        (0x6008a934, b'OM-5MarkII      ', b'OM-5            '),
        (0x6008a9fc, b'OM-5MarkII\0', b'OM-5\0\0\0\0\0\0\0'),
    ):
        edit(address, old, new, 'recipient model-name default')
    # The padded model-name record stays 16 bytes; following fields never move.
    patterns = list(re.finditer(rb'[SEGHWAMVDTIKN]148\?{4}BIN', donor))
    require(len(patterns) == 17, 'Unexpected donor update filename pattern count')
    for m in patterns:
        edit(BASE+m.start(), m.group(), m.group().replace(b'148', b'144'), 'recipient update filename')
    # The first range guard is byte-identical to the recipient after relocation.
    lo, hi = 0x60021714-BASE, 0x6002182c-BASE
    require(out[lo:hi] == recipient[lo:hi], 'Recipient range guard differs')
    # Caller/library ABI must remain entirely donor-native.
    lo, hi = LIBRARY_OFFSET, LIBRARY_OFFSET+LIBRARY_SIZE
    require(out[lo:hi] == donor[lo:hi], 'Donor startup library changed')
    return bytes(out), edits


def build(recipient_path, donor_path, out, toolchain=None, jpegtran=None, untested=False, patch_dir=None):
    patch_dir = Path(patch_dir).resolve() if patch_dir else PATCH
    out = Path(out).resolve()
    require(not out.exists(), 'Output directory must be new')
    require(ROOT/'patches' not in out.parents, 'Keep output outside patch sources')
    recipient_blocks, recipient_main = read_image(Path(recipient_path), 'E144')
    donor_blocks, donor_main = read_image(Path(donor_path), 'E148')
    r = {b.kind: b for b in recipient_blocks}
    d = {b.kind: b for b in donor_blocks}
    gpio_r = recipient_main[0x6002500c-BASE:0x6002500c-BASE+944]
    gpio_d = donor_main[0x6002550c-BASE:0x6002550c-BASE+944]
    require(gpio_r == gpio_d, 'GPIO register-address table differs')
    def definitions(data):
        return {m.group().split(b',')[0]: m.group()
                for m in re.finditer(rb'PRM_[A-Z0-9_]+,[ -~]{1,160}', data)}
    recipient_definitions, donor_definitions = definitions(recipient_main), definitions(donor_main)
    require(len(recipient_definitions) == 180 and all(donor_definitions.get(k) == v
                for k, v in recipient_definitions.items()), 'Recipient parameter descriptors differ')
    jpegtran = jpegtran or shutil.which('jpegtran')
    require(jpegtran is not None, 'Install libjpeg-turbo jpegtran or supply --jpegtran')
    jpegtran = str(Path(jpegtran).resolve())
    jpeg_version = subprocess.run([jpegtran, '-version'], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, check=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix='om5i-donor-') as scratch:
        donor_out = Path(scratch)/'build'
        donor_report = build_donor(patch_dir, donor_path, donor_out, tools=toolchain, decoded=True, untested=False)
        require(donor_report['package_sha256'] not in KNOWN_BOOT_FAILURES, 'Failed donor image')
        feature_main = (donor_out/'decoded/0100.bin').read_bytes()
        feature_osd = (donor_out/'decoded/0101.bin').read_bytes()
        main, edits = adapt_main(feature_main, recipient_main)
        spec = json.loads((patch_dir/'patch.json').read_text())
        # Rebased runtime ranges cannot overwrite any feature patch.
        for row in spec['ranges']:
            if row['component'] == '0x100' and 'address' in row:
                a, size = int(row['address'], 16)-BASE, row['bytes']
                require(main[a:a+size] == feature_main[a:a+size], f'Feature range changed: {row["name"]}')
        stored_main = repack_image(d[0x100].payload, main, split=True, literal_limit=0)
        require(expand_image(stored_main) == main, 'Main compression round trip failed')
        require(len(feature_osd) <= len(r[0x101].payload), 'OSD exceeds recipient slot')
        osd = feature_osd + b'\xff'*(len(r[0x101].payload)-len(feature_osd))
        common, common_report = relocate_common(d[0x106].payload, d[0x106].address,
                                                r[0x106].address, len(r[0x106].payload))
        pictures, picture_report = pack_pictures(d[0x102].payload, d[0x102].address,
                                                 r[0x102].address, len(r[0x102].payload), jpegtran)
    payloads = {0x100: stored_main, 0x101: osd, 0x106: common,
                0x10e: r[0x10e].payload, 0x102: pictures}
    blocks = [replace_payload(b, payloads[b.kind]) for b in recipient_blocks]
    require(not overlaps(blocks), 'Recipient component overlap')
    image = reconstruct(blocks)
    verified = parse(image)
    require(reconstruct(verified) == image, 'Candidate container round trip failed')
    require(tuple(b.kind for b in verified) == KINDS, 'Candidate component order changed')
    for before, after in zip(recipient_blocks, verified):
        require(before.header == after.header and extent(before) == extent(after), 'Recipient slot metadata changed')
        require(after.payload == payloads[after.kind], 'Candidate payload changed during packaging')
    require(verified[3] == recipient_blocks[3], 'Recipient controller component changed')
    restore = reconstruct(recipient_blocks)
    require(restore == Path(recipient_path).read_bytes(), 'Stock restore is not exact')
    sources = [Path(__file__), ROOT/'tools/om5_donor_resources.py',
               ROOT/'tools/om5_transplant_audit.py', ROOT/'tools/oly_container.py',
               ROOT/'tools/oly_compress.py', ROOT/'tools/oly_patch.py']
    report = {
        'schema': 'om5i-donor-patch/1', 'target': 'OM-5 I / E144 1200 slot map',
        'donor': 'OM-5 II / E148 1100 with HSL, WB, monochrome profiles and ND64',
        'camera_tested': False, 'hardware_compatibility_established': False,
        'camera_access': False, 'package_sha256': sha256(image), 'package_bytes': len(image),
        'restore_sha256': sha256(restore), 'donor_build': donor_report,
        'jpegtran_version': jpeg_version, 'main_edits': edits,
        'shared_static_evidence': {'gpio_register_addresses': 236, 'gpio_table_sha256': sha256(gpio_r),
                                  'matching_recipient_parameter_descriptors': 180,
                                  'note': 'Register locations/descriptors only; pin roles and physical behaviour are untested.'},
        'source_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in sources},
        'common_resources': common_report, 'pictures': picture_report,
        'expanded_main_sha256': sha256(main),
        'components': {hex(k): {'bytes': len(v), 'sha256': sha256(v)} for k, v in payloads.items()},
        'preservation': {'recipient_component_metadata': True, 'recipient_010e_exact': True,
                         'donor_startup_library_exact': True, 'donor_feature_ranges_exact': True,
                         'writes_outside_recipient_update_slots': False},
        'limitations': [
            'A candidate port, not evidence of a successful camera boot.',
            'GPIO, sensor/ISP, IBIS, USB/charging and E144 controller protocol need physical validation.',
            'Retained settings and calibration reads are not exercised by these host checks.',
            'JPEG pixels match in the host decoder; the camera hardware decoder is not tested.',
            'The previous E148 startup correction is also not physically validated.',
        ],
        'install': 'install/DCOLYMP/E1449999.BIN' if untested else None,
    }
    # Finish every transformation and check before publishing output files.
    out.mkdir(parents=True)
    decoded = out/'decoded'; decoded.mkdir()
    for k, data in payloads.items():
        (decoded/f'{k:04x}.bin').write_bytes(main if k == 0x100 else data)
    restore_path = out/'restore-stock/DCOLYMP/E1449999.BIN'
    restore_path.parent.mkdir(parents=True); restore_path.write_bytes(restore)
    if untested:
        target = out/report['install']; target.parent.mkdir(parents=True); target.write_bytes(image)
    (out/'build.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stock', type=Path, required=True, help='Official OM-5 I 1.2/1200 update')
    p.add_argument('--donor-stock', type=Path, required=True, help='Official OM-5 II 1.1/1100 update')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--as', dest='assembler')
    p.add_argument('--ld', dest='linker')
    p.add_argument('--objcopy')
    p.add_argument('--jpegtran')
    p.add_argument('--donor-patch', type=Path, help='donor patch directory (default: patches/hsl/om-5-ii); '
                   'a composed directory lets further layers be built into the donor before the transplant')
    p.add_argument('--write-untested-package', action='store_true')
    a = p.parse_args()
    report = build(a.stock, a.donor_stock, a.out,
                   {'as': a.assembler, 'ld': a.linker, 'objcopy': a.objcopy},
                   a.jpegtran, a.write_untested_package, a.donor_patch)
    print(json.dumps({k: report[k] for k in ('target', 'package_sha256', 'package_bytes', 'install',
                                            'camera_tested', 'hardware_compatibility_established')}, indent=2))


if __name__ == '__main__':
    main()
