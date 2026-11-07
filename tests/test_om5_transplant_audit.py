import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from oly_container import Block
from om5_transplant_audit import audit, extent, overlaps, read_image


def block(kind, address, span):
    header = bytearray(32)
    struct.pack_into('<I', header, 8, address)
    struct.pack_into('<H', header, 20, kind)
    return Block(0, 0, bytes(header), bytes(span-64), bytes(32))


class ExtentTests(unittest.TestCase):
    def test_container_metadata_is_included(self):
        self.assertEqual(extent(block(0x101, 0x1000, 128)), (0x1000, 0x1080))

    def test_special_zero_address_is_not_flash(self):
        self.assertIsNone(extent(block(0x10e, 0, 0x1000)))

    def test_adjacent_ranges_and_overlap(self):
        a = block(0x101, 0x1000, 128)
        self.assertEqual(overlaps([a, block(0x106, 0x1080, 128)]), [])
        self.assertEqual(overlaps([a, block(0x106, 0x1070, 128)])[0]['bytes'], 16)

    def test_reject_unknown_build_before_parsing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'not-firmware'; p.write_bytes(b'unrecognised')
            with self.assertRaisesRegex(ValueError, 'pinned official'):
                read_image(p, 'E144')


@unittest.skipUnless(os.environ.get('OM5I_STOCK') and os.environ.get('OM5II_STOCK'),
                     'supply official packages via OM5I_STOCK and OM5II_STOCK')
class StockComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit(Path(os.environ['OM5I_STOCK']), Path(os.environ['OM5II_STOCK']))

    def test_all_components_differ_and_library_has_shifted_entry(self):
        r = self.report
        self.assertFalse(any(r['component_identity'].values()))
        self.assertEqual(r['startup_library_different_bytes'], 2088)
        self.assertEqual(r['recipient']['startup_library']['memset_entry'], '0x4700114b')
        self.assertEqual(r['donor']['startup_library']['memset_entry'], '0x47001154')

    def test_mixed_resource_overlap_is_detected(self):
        rows = self.report['scenarios']['donor_resources_with_recipient_osd']['logical_overlaps']
        self.assertEqual(rows, [{'kinds': ['0x101', '0x106'], 'start': '0x42d40000',
                                 'end': '0x42ea0000', 'bytes': 0x160000}])

    def test_nonoverlapping_donor_does_not_become_compatible(self):
        r = self.report
        self.assertFalse(r['hardware_compatibility_established'])
        self.assertEqual(r['scenarios']['donor_stock']['logical_overlaps'], [])
        self.assertIsNone(r['scenarios']['donor_stock']['compatible'])


if __name__ == '__main__':
    unittest.main()
