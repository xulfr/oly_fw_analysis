"""Regressions for the actual loaded end, not the next section's address."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from om5ii_boot_audit import loader_regions, require_loaded_range, audit_ranges


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.regions = [{'id': 5, 'start': 0x60843000, 'end': 0x60846000},
                        {'id': 6, 'start': 0x60847000, 'end': 0x60ca8000}]

    def test_original_refresh_fits(self):
        self.assertEqual(require_loaded_range(self.regions, 0x60845a00, 692, 'refresh'), 5)

    def test_second_failed_overlay_exceeds_native_end(self):
        with self.assertRaisesRegex(ValueError, 'not wholly inside'):
            require_loaded_range(self.regions, 0x60845d00, 3804, 'failed overlay')

    def test_exact_end_and_first_unloaded_byte(self):
        self.assertEqual(require_loaded_range(self.regions, 0x60845d00, 768, 'fits'), 5)
        with self.assertRaises(ValueError):
            require_loaded_range(self.regions, 0x60845d00, 769, 'one byte too long')

    def test_gap_is_not_a_section(self):
        with self.assertRaises(ValueError):
            require_loaded_range(self.regions, 0x60846000, 4, 'gap')


@unittest.skipUnless(os.environ.get('OM5II_STOCK_MAIN'), 'supply pinned expanded stock via OM5II_STOCK_MAIN')
class NativeLayoutTests(unittest.TestCase):
    def test_native_map_and_current_manifest(self):
        import json
        stock = Path(os.environ['OM5II_STOCK_MAIN']).read_bytes()
        regions = loader_regions(stock)
        self.assertEqual(regions[4]['end'], 0x60846000)
        self.assertEqual(regions[5]['start'], 0x60847000)
        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root/'patches/hsl/om-5-ii/patch.json').read_text())
        owners = audit_ranges(stock, spec['ranges'])
        self.assertEqual(owners['ext5'], 5)
        self.assertEqual(owners['nd_step_selector'], 1)
        with self.assertRaises(ValueError):
            require_loaded_range(regions, 0x60845d00, 3804, 'archived overlay')


if __name__ == '__main__':
    unittest.main()
