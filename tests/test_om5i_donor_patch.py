import json
import os
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from oly_container import parse, reconstruct, sha256
from oly_compress import expand_image
from om5_donor_resources import directory, jpeg_pixels
from om5i_donor_patch import adapt_main, LAYOUT_EDITS, BASE


class RefusalTests(unittest.TestCase):
    def test_unknown_main_is_not_retargeted(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected donor bytes'):
            adapt_main(bytes(0x1800000), bytes(0x1800000))

    def test_resource_pointer_outside_component_is_rejected(self):
        data = struct.pack('<4I', 0x1010, 128, 0, 0)+bytes(16)
        with self.assertRaisesRegex(ValueError, 'outside directory'):
            directory(data, 0, 0x1000, len(data))


@unittest.skipUnless(all(os.environ.get(v) for v in ('OM5I_STOCK', 'OM5II_STOCK', 'OM5I_BUILD')),
                     'supply stock packages and generated build via environment')
class BuiltCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = Path(os.environ['OM5I_BUILD'])
        cls.report = json.loads((cls.folder/'build.json').read_text())
        cls.r = parse(Path(os.environ['OM5I_STOCK']).read_bytes())
        cls.d = {b.kind: b for b in parse(Path(os.environ['OM5II_STOCK']).read_bytes())}
        cls.raw = (cls.folder/'install/DCOLYMP/E1449999.BIN').read_bytes()
        cls.p = parse(cls.raw)
        cls.main = expand_image(cls.p[0].payload)

    def test_recipient_metadata_slots_and_controller_are_exact(self):
        self.assertEqual(len(self.raw), sum(len(b.payload)+64 for b in self.r))
        self.assertEqual(reconstruct(self.p), self.raw)
        for old, new in zip(self.r, self.p):
            self.assertEqual(new.header, old.header)
            self.assertEqual(new.offset, old.offset)
            self.assertEqual(len(new.payload), len(old.payload))
        self.assertEqual(self.r[3], self.p[3])
        self.assertEqual((self.folder/'restore-stock/DCOLYMP/E1449999.BIN').read_bytes(), reconstruct(self.r))

    def test_main_edits_are_bounded_and_false_pointer_match_is_untouched(self):
        donor = expand_image(self.d[0x100].payload)
        for address, opcode, old, new, _ in LAYOUT_EDITS:
            at = address-BASE
            self.assertEqual(self.main[at:at+6], bytes.fromhex(opcode)+struct.pack('<I',new))
        at = 0x6063fd7f-BASE
        self.assertEqual(self.main[at:at+4], donor[at:at+4])
        self.assertEqual(self.main[at:at+4], struct.pack('<I',0x45c20000))
        self.assertNotIn(b'E148????BIN', self.main)
        self.assertIn(b'E144????BIN', self.main)

    def test_hsl_wb_nd_ranges_and_donor_library_are_preserved(self):
        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root/'patches/hsl/om-5-ii/patch.json').read_text())
        for row in spec['ranges']:
            if row['component'] == '0x100' and 'address' in row:
                at = int(row['address'],16)-BASE
                self.assertEqual(sha256(self.main[at:at+row['bytes']]), row['after_sha256'], row['name'])
        donor = expand_image(self.d[0x100].payload)
        self.assertEqual(self.main[0x1681fe0:0x16837e0], donor[0x1681fe0:0x16837e0])

    def test_common_leaf_resources_survive_relocation(self):
        old = self.d[0x106]; new = self.p[2]
        _, banks = directory(old.payload, 0, old.address+32, len(old.payload))
        _, relocated = directory(new.payload, 0, new.address+32, len(new.payload))
        self.assertEqual(banks, relocated)
        checked = 0
        for _, offset, size in banks:
            _, leaves = directory(old.payload, offset+32, old.address+32, offset+size-32)
            _, moved = directory(new.payload, offset+32, new.address+32, offset+size-32)
            self.assertEqual(leaves, moved)
            for _, start, length in leaves:
                self.assertEqual(old.payload[start:start+length], new.payload[start:start+length])
                checked += 1
        self.assertEqual(checked, 557)

    def test_all_picture_ids_keep_their_pixels(self):
        old, new = self.d[0x102], self.p[4]
        _, old_rows = directory(old.payload,0,old.address+32,len(old.payload))
        _, new_rows = directory(new.payload,0,new.address+32,len(new.payload))
        self.assertEqual(len(old_rows),116)
        self.assertEqual(len(new_rows),116)
        for (index,a,n),(new_index,b,m) in zip(old_rows,new_rows):
            self.assertEqual(index,new_index)
            before, after = old.payload[a:a+n], new.payload[b:b+m]
            if before[:2] == b'\xff\xd8':
                self.assertEqual(jpeg_pixels(before),jpeg_pixels(after),f'image {index//16}')
            else:
                self.assertEqual(before,after)

    def test_report_matches_actual_image_without_claiming_hardware_validation(self):
        self.assertEqual(sha256(self.raw),self.report['package_sha256'])
        self.assertFalse(self.report['camera_tested'])
        self.assertFalse(self.report['hardware_compatibility_established'])


if __name__ == '__main__':
    unittest.main()
