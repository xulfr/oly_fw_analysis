# E148 1.1 boot-loop trace and reduced complete build

5 November 2026, `codex/om5ii-stock-section7`. Read alongside
`OM5II-SECOND-BOOT-FAILURE-2026-11-05.md` and
`../../phase4-om5ii-hsl/BOOT-FAILURE-INVESTIGATION-2026-11-04.md`.

## Failing stage: bounded, not pinpointed

The owner observed a roughly one-second cycle of a lit but black screen,
autofocus movement, and screen off after both updates. Stock restore succeeded
after each. This is direct evidence of repeated power-on/startup activity and
failure to reach stable live view. It does **not** prove a whole-CPU reset,
watchdog timeout, successful Section 6 or 7 load, task-92 execution, OSD
lookup, or a particular failing instruction. No reset log, loader trace, or
installed-flash readback exists. The exact failing stage and root cause remain
unestablished.

The stock main's base loader starts sections in order 1, 8, 2, 3, 4, 5, 6, 7,
9, 10. Both failed images leave the base region unchanged, but edited section
code/data can run during startup. OM-Emu starts beyond parts of the real boot
and does not execute the physical section loader or model the camera's caches.
Its successful UI and native overlay tests cannot locate this failure.

## Exact-image comparison

Independent parsing and expansion of the archived files found:

| Property | 4 November `35f0caac…9d434` | 5 November `cfce2fb8…349c` |
| --- | --- | --- |
| Components | `0x100`, `0x101` | All five stock kinds in stock order |
| OSD `0x101` | Modified, SHA-256 `6b93ba21…7a22` | Same modified payload, byte-identical to first |
| Stored and expanded Section 6/7 | Changed | Both whole spans byte-identical to stock |
| Expanded main outside Section 6/7 | 3,631 changed bytes | The same 3,631 changed bytes, plus 2,134 bytes in the task-92 hook/installer area |

The second file's `0x106`, `0x10e`, and `0x102` headers, payloads, and trailers
are stock-identical. These facts weaken *changed compressed spans* and *missing
components* as necessary explanations for the repeated symptom. They do not
prove a common root cause: the second image introduced another boot-time path,
and neither installed image was read back.

## Candidate causal paths

1. **Shared early main edits.** The common 3,631 non-Section-6/7 changed bytes
   include Section 2 picture-mode descriptors, availability and refresh tables,
   WB commit at `0x602d19b6`, refresh at `0x602e0826`, Section 4 editor
   read/write sites `0x6091c66d`/`0x6091c6bd`, and extension code. Earlier
   forced-guard OM-Emu boot observed the stock WB commit and editor read/write
   paths, making these credible startup candidates. Their actual camera call
   order, saved settings, and state at the reset were not observed. The WB
   extension has a Section-6 loaded-bit guard, but a real loader error can set
   that bit, so the guard does not prove valid Section-6 contents.
2. **Shared OSD.** The two archived `0x101` payloads are identical. The edit
   aliases 42 record-0 image pointers to existing stock images and repacks
   the resource. A startup artwork lookup could fault, but no physical lookup
   or fault path has been captured. A black display alone would not explain
   repeated lens activity.
3. **Second-only task-92 overlay.** The six-byte hook at `0x6081e2f1` diverts
   the task just after it launches `FIRMUP_CLI`; the 3,804-byte installer at
   `0x60845d00` waits for Section 7, compares 1,712 stock target bytes, and
   writes 16 Section-6/7 ranges through uncached aliases. Its displaced
   instruction and return were verified in OM-Emu with memory set up explicitly.
   On hardware, Section-7 load completion, scheduling, instruction-cache
   visibility, and concurrent consumers are unproven. The hook cannot be a
   necessary common cause because it is absent from the first failed image.
   It can independently cause or amplify the second failure.

There is no defensible ranking between the shared early main and OSD paths
without a reset-to-live-view trace or readback. The physical loader remains a
separate possibility for the first image; stock Section-6/7 bytes in the
second image remove that particular changed-stream precondition, assuming the
archived update is what was installed.

## Complete reduced artifact

At the owner's request, `patches/hsl/om-5-ii-nd-reduced/patch.json` retains
only the three previously audited Live ND32/ND64 edits. Running `oly_patch.py`
produced `generated/om5ii-nd-reduced-full-20261105-v2/install/DCOLYMP/E1489999.BIN`,
90,832,896 bytes, SHA-256
`9f4b017329210b37ca4a5286c46e1871d5de83894a81740c5fb89c51b9cfdc5e`.
An independent parse/round trip verified all five components in stock order;
OSD and the last three kinds are completely stock-identical; stored and expanded
Sections 6 and 7 are stock-identical. Exactly 37 expanded main bytes differ
from stock, all within the three declared ND ranges. This build excludes HSL,
profile WB, profile UI, icons, and the task-92 overlay. It is structurally
installable and **not camera-qualified**. These offline checks do not establish
that it boots on the camera, so it must not be used as a diagnostic flash.

Both failed BIN files remain intact in `generated/om5ii-hsl-1bd6276/` and
`generated/om5ii-stock-section7-full-20261105/`. Their known failed hashes
remain blocked by the respective builders. Decisive missing evidence is a
physical reset/loader trace, section-load and reset cause, or installed readback
from a controlled service or spare-body setup. No additional camera flash is
proposed as a diagnostic test.
