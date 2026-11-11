"""Static audit: OM-5 II patch code makes no absolute store into the loaded main image.

Stock E148 has no such store (tools/om5ii_ui_session.mjs --watch shows one register-indirect stock site only).
The 8 November 2026 camera failure began at the first image stores the patch made. Supply a build directory
(`oly_patch.py` output) through OM5II_BUILD and an MN103 objdump through OM5II_OBJDUMP or PATH.
"""
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

IMAGE = (0x60021020, 0x617e1020)
ALIAS = 0x40000000
STORE = re.compile(r'\b(mov|movbu|movhu|bset|bclr)\s+[^,]+,\((?:0x)?([0-9a-f]{8})(?: <[^>]*>)?\)\s*$')
PATCH = Path(__file__).resolve().parents[1]/'patches/hsl/om-5-ii'


def in_image(address):
    return any(lo <= address < hi for lo, hi in (IMAGE, (IMAGE[0]+ALIAS, IMAGE[1]+ALIAS)))


class SourceTests(unittest.TestCase):
    def test_sources_declare_no_image_state(self):
        for name in ('hsl.s', 'wb.s', 'layout.ld', 'wb.ld'):
            text = (PATCH/name).read_text()
            for gone in ('refresh_profile', 'creset_buf', 'creset_ptr', 'creset_kind', 'creset_ret',
                         '0xa0ca7', '.state'):
                self.assertNotIn(gone, text.replace('refresh_profile holds', ''), f'{name}: {gone}')
        self.assertNotRegex((PATCH/'wb.ld').read_text(), r'\bbusy\s*=')
        self.assertNotRegex((PATCH/'layout.ld').read_text(), r'\baxis\s*=')


@unittest.skipUnless(os.environ.get('OM5II_BUILD'), 'supply OM5II_BUILD (oly_patch.py output directory)')
class BuiltTests(unittest.TestCase):
    def test_no_absolute_store_into_the_loaded_image(self):
        objdump = os.environ.get('OM5II_OBJDUMP') or shutil.which('mn10300-elf-objdump')
        self.assertTrue(objdump, 'mn10300-elf-objdump not found')
        checked = 0
        for elf in sorted(Path(os.environ['OM5II_BUILD']).glob('assembly/*/patch.elf')):
            listing = subprocess.check_output([objdump, '-d', '-m', 'am33-2', str(elf)], text=True)
            for line in listing.splitlines():
                m = STORE.search(' '.join(line.split('\t')[2:])) if line.count('\t') >= 3 else None
                if not m:
                    continue
                checked += 1
                self.assertFalse(in_image(int(m.group(2), 16)), f'{elf.parent.name}: image store: {line.strip()}')
        # the one absolute store left is the handle halfword in .bss
        self.assertEqual(checked, 1)


if __name__ == '__main__':
    unittest.main()
