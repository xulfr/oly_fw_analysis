# E148 startup readiness correction and overlay placement defect

Reviewed `codex/om5ii-stock-section7` at `bd5fffd`, including the shared HSL,
WB and ND edits. Two concrete defects were found. The readiness correction is
implemented in the full HSL/ND source. The invalid overlay is rejected at link
and build time; its placement has not been redesigned. Neither physical boot
loop has been reproduced with a reset trace, so this is a tested correction of
startup defects, **not confirmation that the camera boot loop is resolved**.

## 1. The guards were testing submission, not completion

The E148 loader maintains two distinct words:

| Word | Producer | Meaning established by native code |
| --- | --- | --- |
| `0xa26e2698` | `0x600464bf..0x600464c7` | Section load request has returned; for compressed sections, the decoder has accepted a job. |
| `0xa26e2694` | `0x600465be..0x600465c6` | Finalisation has passed the decoder completion wait and the section's constructor loop. This is what native `section_wait` uses. |

For section 6 or 7, `0x60046418` calls `0x6005b249`. That routine submits the
source, destination and lengths through `0x8ff00b80..0x8ff00b90`, waits for
status **2** at `0x8ff00b94`, acknowledges it, and returns. The loader then sets
`0xa26e2698`. The separate finaliser `0x600464d0` waits for that bit, acquires
the native synchronisation primitive, and calls `0x6005b393`, which waits for
status **1**. Only after that wait and constructors does it set `0xa26e2694`.
`0x6004637c`, called by `section_wait` at `0x60046395`, reads the latter word.

The WB wrapper was reading section-6 `busy` and potentially calling section-6
`stock_ui_write` on the earlier flag. Custom-mode reset likewise accessed
section-6 scratch storage. This admits accesses while that section is still
being decompressed or initialised. Both failed designs contain these guards.
Whether the observed camera reset actually traversed this window is unknown.

Both linker scripts now bind `loaded_bits` to `0xa26e2694`. This also makes the
section-5 refresh guard use native readiness consistently. The complete
expanded main differs from the reproduced failed HSL main at exactly three
bytes: `0x605af578`, `0x605af5ce`, `0x613f2c28`, each changing `98` to `94` in
an address operand. No HSL, WB or ND feature logic is removed.

## 2. The overlay extends outside the bytes the native loader copies

The native descriptor table at `0x600284fc` and end selector at `0x600463af`
put section 5 at **`0x60843000..0x60846000`** (end exclusive). Section 6 starts
at `0x60847000`. The 4 KiB between them is not section-5 loadable space.

The failed overlay builder used `0x60847000` as its allocation end. Its
3,804-byte code/table/data block at `0x60845d00` ends at `0x60846bdc`: only
768 bytes lie in section 5; **3,036 bytes are outside its native loaded extent**.
The test wrote the entire block into emulator RAM directly, masking this
placement error. In a native section-5 copy the later preflight/payload bytes
are absent. This can cause preflight rejection or other invalid operation;
it does not by itself establish the observed reset instruction.

The linker now asserts the real section end. The Python builder independently
reads the native layout and rejects ranges that cross it. The ordinary patch
builder applies the same layout check to all declared E148 main edits. The
old overlay cannot be rebuilt as an update merely by changing its hash.
A new overlay design would additionally need cache and concurrency work.

## Other hypotheses checked

- ND's 768 selector cases pass (256 steps × three EV units); the ND bytes are
  unchanged by this fix. This does not test the ISP's ND32/64 processing.
- The FF word at `0x605af4b0`, reused by the HSL extension, immediately follows
  the section-2 constructor table. The actual native runner at `0x601ae87a`
  uses a fixed **52-byte** count, not a sentinel scan. It therefore does not
  call the injected code as an extra constructor. Section 7 and 8 tables also
  have fixed counts. The apparent sentinel overwrite is not the explanation.
- All 86 declared main ranges in the ordinary HSL manifest fit actual native
  section extents. The oversized task-92 installer is separate.
- Original compression and OSD output reproduced the recorded failed hash
  exactly. No unsupported claim about OSD or compression being harmless is
  made from that result.

## Verification and reproduction

Input: official E148 1.1/build 1100 update SHA-256
`9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`.
Downloaded from the vendor catalogue and independently parsed/expanded.
GNU binutils 2.45, target `mn10300-elf`; OM-Emu checkout
`147ca89c60b24774f3145c2813d79714e0f0b7b7`.

The original source at `bd5fffd` reproduced package hash
`35f0caac4b70f1e59e3d5311fdf74a8c021d720755a7441796b080707b79d434`.
The corrected source rebuilds expanded main
`ab6151ff53f024ddd6d1fb14712cde7ce47693382104a13e631af79b7ecff63e`.
Its manifest now composes all five stock component kinds, changing only main
and OSD, and produces full stock restoration rather than a two-component
subset. The computed complete candidate hash is
`e2ca5b281b9cb43ff3b7d49c745c908ec02210f79ab9a52245b379afc66d92e1`.
An install file is withheld by default; no camera was flashed during this work.
Both previously failed package hashes remain independently blocked in the
builder even if a manifest omits its `known_boot_failure` flag.

Run the normal `tools/oly_patch.py` command in the patch README, with the three
MN103 tool paths and `--decoded`. To compare native guards, retain the original
expanded output from a separate checkout of `bd5fffd`:

```sh
node research/test_om5ii_startup_guards.mjs /path/to/om-emu \
  /path/to/original/decoded/0100.bin /path/to/fixed/decoded/0100.bin
OM5II_STOCK_MAIN=/path/to/expanded-stock.bin \
  python3 -m unittest discover -s tests -p test_om5ii_boot_audit.py -v
python3 patches/live-nd/om-5-ii/nd64.py /path/to/expanded-stock.bin
```

Eight native guard cases pass, including two negative controls showing the
old WB/reset wrappers entering extension logic with submission set and
completion clear. The corrected wrappers take their stock continuations in
that state and enter extension logic when completion is set. Two native
publication sequences confirm the separate words. Five placement tests pass,
including reading the real stock layout, validating the ordinary manifest,
and rejecting the archived 3,804-byte overlay. These are bounded CPU and
layout regressions, not a physical loader/cache/full-camera simulation.
