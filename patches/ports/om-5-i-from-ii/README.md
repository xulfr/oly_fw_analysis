# OM-5 I candidate built from OM-5 II firmware

This builder uses the corrected **E148 1100** HSL/WB/monochrome/ND64 main
program and resources as the donor, and targets the **E144 1200** update layout.
It does not implement those features in the old E144 application.

**Experimental; not tested on a camera.** The patcher produces a complete
candidate package, but neither successful OM-5 I boot nor full hardware
compatibility has been established. The E148 donor's startup correction also
still needs physical validation. Passing these checks is not a claim that the
previous boot loop is resolved on either body.

## Build

Requirements: Python 3, Pillow, liblz4, MN10300 GNU binutils and libjpeg-turbo's
`jpegtran`. Supply both official firmware files; no vendor firmware is included
in this repository.

```sh
python3 patches/ports/om-5-i-from-ii/build.py \
  --stock OLY_E_144_1200_0000_0000.BIN \
  --donor-stock OLY_E_148_1100_0000_0000.BIN \
  --out generated/om5i-donor
```

Use `--as`, `--ld`, `--objcopy` and `--jpegtran` if the executables are not on
PATH. `--stock` always means the recipient's original OM-5 I firmware.

The default writes `decoded/`, an exact complete E144 stock restore under
`restore-stock/DCOLYMP/E1449999.BIN`, and `build.json`. To also generate the
experimental update under `install/DCOLYMP/E1449999.BIN`, add
`--write-untested-package`. A new output directory is required for each run.
The builder never communicates with a camera. The stock restore file is not
evidence that recovery will remain reachable after a cross-model installation.

## What the port changes

The E148 resource layout cannot simply be installed over E144. Its picture
component is allocated 10 MiB where E144 has 7 MiB, and its factory sound and
mode-17 directory addresses differ. Merely changing the model tag would leave
those accesses pointing at the wrong locations.

| Component / region | E148 original | Candidate on E144 |
|---|---:|---:|
| Main program | `0x40780000` | `0x40780000` |
| OSD | `0x42140000`, 12 MiB | `0x42140000`, E144 slot size |
| Common resources | `0x42d40000` | `0x42ea0000` |
| Resident mode-17 directory | `0x455e0000` | `0x45a40000` |
| Picture resources | `0x45c20000`, 10 MiB | `0x45cc0000`, 7 MiB |
| Resident sound directory | `0x46620000` | `0x463c0000` |
| Subsequent flash range boundary | `0x46c40000` | `0x469e0000` |

Sizes in this table include the 64-byte container envelope. Addresses are the
firmware's logical storage addresses, not a physical NAND/ECC map.

The builder:

- Rebuilds the corrected E148 feature patch from source and checks its existing
  hashes, loaded-section boundaries and known-failed-image exclusions.
- Adapts 21 inspected native address operands, including the aliases and sound
  write/reload paths, to the recipient layout. It deliberately leaves numerical
  coincidences in other instructions/data untouched.
- Relocates the common resource directory and its 11 nested banks. All 557
  leaf records remain byte-identical; the checksummed nested bank is repaired.
- Losslessly optimises JPEG Huffman coding and packs all 116 picture IDs into
  E144's 7 MiB slot. Every JPEG is decoded and compared before and after packing;
  the non-JPEG picture record remains exact. No illustration is removed or
  downsampled. With jpegtran 2.1.5, 283,616 payload bytes remain free.
- Retains E148's matching startup library and every HSL/WB/ND feature range.
  E144's library is not ABI-compatible: the same memset entry has moved nine
  bytes, and a native negative control demonstrates corrupted output if mixed.
- Preserves all five E144 outer headers, addresses and component sizes, and the
  entire E144 `010e` controller component. It writes nothing outside the
  recipient's original update slots; factory-only regions are not copied,
  cleared or synthesised.
- Retargets the update filename patterns and three model-name defaults to E144.
  This is not a general settings migration: E144 retained settings, calibration
  consumption and controller behaviour remain unverified on hardware.

Both stock inputs must match their full SHA-256:

| Input | SHA-256 |
|---|---|
| E144 1200 | `a0c91f3ac7caaf0925b2af609e711183cf3b5982b3333224bcef26c0c5943d11` |
| E148 1100 | `9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637` |

## Verification

The complete build was run with GNU binutils 2.45 and jpegtran 2.1.5. Its
92,274,688-byte experimental package has SHA-256
`dcbee4c9997d1cb0eeeccfcac3f20b9ea9ba4c6848f6b446277b7665a85d5b9a`.
`build.json` records actual hashes, tool versions and source hashes on each run.
JPEG encoder versions may produce different valid entropy coding.

Eight patcher tests cover the complete generated package, exact stock restore,
recipient slot metadata/controller, all feature ranges, all common leaf records,
all picture IDs and refusal of invalid inputs. Seven prerequisite audit tests
also pass. Native MN103 checks run the following:

- 450 range-boundary/alias cases agree with E144's native guard; unadapted E148
  disagrees in 116 cases.
- 30 native library controls pass, and mixing the donor caller with the recipient
  library demonstrably fails the zero-fill result.

These are bounded native routines and host package/resource checks, **not a
reset-to-shooting camera boot test**. Matching 236 GPIO register addresses and
180 recipient parameter descriptors supports the shared-platform approach, but
does not establish pin routing, sensor/ISP, IBIS, charging/USB or calibration
behaviour. Hardware JPEG decoding and E148-to-E144 controller protocol behaviour
are also not exercised here.

```sh
OM5I_STOCK=/path/to/E144.BIN OM5II_STOCK=/path/to/E148.BIN \
  OM5I_BUILD=generated/om5i-donor \
  python3 -m unittest discover -s tests -p test_om5i_donor_patch.py -v

node research/test_om5i_flash_guard.mjs /path/to/om-emu \
  /path/to/E144-expanded.bin /path/to/E148-expanded.bin \
  generated/om5i-donor/decoded/0100.bin

node research/test_om5_transplant_library.mjs /path/to/om-emu \
  /path/to/E144-expanded.bin /path/to/E148-expanded.bin
```

The native tests used OM-Emu commit
`147ca89c60b24774f3145c2813d79714e0f0b7b7`.
