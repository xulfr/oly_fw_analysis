# OM-5 II: the third failure traced to stores into the loaded image

11 November 2026. Follows the [third incident report](OM5II-THIRD-BOOT-FAILURE-2026-11-08.md).
Offline work only: static analysis and OM-Emu sessions driving the firmware's own GUI. **No camera was
used. The corrected build has not been flashed, so this is a well-supported explanation and a tested
correction of a defect, not confirmation that the camera fault is resolved.**

## Summary

Build `e2ca5b28…92e1` booted on the camera, then froze for about two seconds and reset when the
colour-profile selection screen was used, and looped on every later start.

That build kept its runtime state inside the loaded firmware image. On the path the owner took, the
first stores into that image happen on the first highlight move in the Picture Mode direct screen.
Stock E148 never makes such a store by absolute address, and its only store into the image at all
is one site writing its own section-7 words. The same class of store crashed an E-P7 in the same way
(cakelesscoder/caduceus-ep7 `docs/SD_V2_CRASH.md`: a byte store into section-3 RAM through the cached
alias; the camera restarted on first use; moving the state to `.bss`/heap fixed it on camera).

The source now keeps no state in the image. `tools/om5ii_ui_session.mjs --watch` shows no store into
the image from patch code in the same sessions, with the Colour Profile screens and the axis editor
still working.

## Evidence

Input: official E148 1.1/1100, SHA-256 `9de5d77e…d637`. OM-Emu `xulfr/om-emu` branch
`fix/e148-ipi-stride` at `bdb3347`, node 22, `OM_EMU_MODEL=E148`. GNU binutils 2.45 `mn10300-elf`.
The emulator does not run E148's loader, so the ten completion bits at `0xa26e2694` are published
after the start (`--ready`); the hooks' guards then behave as on a started camera.

### 1. Stock makes no absolute store into the image

A byte-level sweep of the expanded stock main for `fc 8x` (`mov`/`movbu`/`movhu reg,(abs32)`) followed
by an address in `0x60021020..0x617e1020` or its `0xa…` alias finds 25 candidates among 24.9 MB. They are
isolated (ten share one target outside any state area) and were not each disassembled, so treat this as
"at most a handful, none found in a session", not as a proof of zero. (E-P7, by full disassembly: 0 of
32,217.) The dynamic result below is the stronger evidence.

With a write watch over the whole image and both aliases, a stock session (start, OK, OK, twelve
moves, the colour page, MENU, MENU) logs one storing site: `0x60d52ed0` writing
`0x61110d0c/10/14` and `0x61111114/18/1c`. That is stock GUI code updating its own section-7 words
through a register. It shows those words are writable through the cached alias. It says nothing
about sections 2 and 6.

### 2. The failed build's first image stores are on the reported path

Same session, build `e2ca5b28` (source `25a336e`):

| Step | New stores into the image |
| --- | --- |
| Start, OK (Super Control Panel), OK (Picture Mode direct screen) | none |
| First RIGHT (highlight moves to the next picture mode) | `0x605af61b → 0xa0ca7ff8` (`busy` = 1), `0x60845a0f → 0x605af575` (`refresh_profile`, **cached alias, section 2**), `0x605af67b → 0xa0ca7ff8` (`busy` = 0) |
| Every later move | the same three |
| Highlight on Color Profile 1–3 | also `0x605af56a → 0x605af575` (the jump-table case) |
| Colour page, Delete | `axis` and the label buffer at `0xa0ca7fc0..0xa0ca7fe4` (section 6 tail) |

Nothing in the patch stores into the image before that first move: not at the start, not on opening
either screen. So on the camera these were the first executions of an operation stock never
performs, at the moment the owner reported the freeze. The picture mode is a saved setting; if the commit or refresh hooks run when settings are
applied at the next start, the loop that followed is explained too, but that start-up path was
not traced. The reset cause was not captured, so the mechanism (a protection or bus error raised
for those regions, then the watchdog) remains an inference, as it does for the E-P7.

The earlier explanation candidates in the third report (carousel data, availability lookup, resource
aliases) are not excluded by this. They draw identical frames to stock until the highlight reaches
the new entries, and no fault was seen in them in the emulator.

### 3. Other state in the image

`hsl_delete_action` stored to `axis+9`/`axis+12` on **every** Delete press in the direct screen;
`creset` kept a 300-byte scratch area at `0xa0ca7e70`; `paint_axis` built its label at `axis+16`.
The Caduceus draft runtime (`caduceus-om5` `firmware/om5/runtime.s`, `STATE = 0xa0621e80`) had the
same defect in section 3 and must not be composed as written.

## Correction

| State | Before | Now |
| --- | --- | --- |
| `refresh_profile` | byte at `0x605af575` (section 2), written by the jump-table case and by the refresh tail | tag `0x5246_00pp` left in `d2` by the case, read by the tail in the same call. `d2` is callee-saved and this path of `0x602e00bf` neither reads nor writes it between `0x602e06ca` and `0x602e0826` (the one writer, `0x602e06f8`, is on the art-filter branch and removes the tag). No store. |
| `axis`, editor pointer, reset flag, label text, WB `busy` | section 6 tail, uncached alias | a 1024-byte block **P** from stock `malloc` (`0x60023818`, class-1 pool `0xa1e27d80..0xa1e32ac0`, uncached). Its handle (`P − pool + 1`) is the padding halfword `0x6218c2fe` after the HLS event manager's task id (`0x6218c2fc`), zero at power-on. |
| Delete-action temporaries | `axis+9`, `axis+12` | the hook's own stack frame |
| Custom-mode reset buffer | 300 bytes at `0xa0ca7e70` | 304 bytes of the calling task's stack for the duration of the reset |

P is allocated once, on the first shutter half-press after start (`0x602f0b95`, the HLS_EVENT
task's trigger tracker; the displaced call is replayed first). The gate requires event
`0x02000100`, all ten completion bits, and the caller to be the HLS_EVENT task. This is the E-P7
mod's camera-proven arrangement, at the byte-identical E148 site.

**Until the first half-press every hook that needs state behaves as stock**: the WB wrapper
replays the stock commit, the editor stays on Saturation, Delete is inert and the axis title is not
drawn. Nothing that needs state can therefore run during start-up.

The state accessors and the arming code are 251 bytes at `0x613f2ed8` in section 8, which loads
before sections 2, 6 and 7 whose hooks call them. `wb_extension` moved from `0x605af5cc` to
`0x605af590` to stay inside section 2's loaded extent (`0x605af800`); the layout audit rejected the
first attempt.

Not changed: every table and resource edit, the carousel, the builder hook, ND32/ND64, the
Monochrome Profiles and the 6 November readiness guards.

## Verification

```sh
python3 tools/oly_patch.py patches/hsl/om-5-ii --stock OLY_E_148_1100_0000_0000.BIN --out fixed --decoded
OM5II_BUILD=fixed python3 -m unittest tests/test_om5ii_store_audit.py
node research/test_om5ii_image_stores.mjs /path/to/om-emu stock/0100.bin stock/0101.bin failed fixed
```

- Static audit of the linked patch: one absolute store remains, the handle halfword. Run against the
  failed build it reports the image stores.
- Four GUI sessions (stock; the failed build as a negative control, 17 distinct store targets in the
  image; corrected, not armed; corrected, armed by S1): the corrected build stores into the image
  only from stock's own site. The handle word is read and written only from `.st8`
  (`0x613f2eda`, `0x613f2f4d`, `0x613f2fca`), once written when armed, never when not.
- Frames: the carousel, labels, colour page and tone page are those of the previous build. Armed,
  Delete cycles Saturation → Hue → Lightness and the value label follows. Not armed, it is inert.
- Corrected expanded main `4f26e2da…6df1`; complete candidate `b038ce1a…ff69` (90,832,896 bytes);
  restore is the official file. OM-5 I candidate rebuilt on the corrected donor: `97d87d24…eb9e`
  (92,274,688 bytes).

## Limits and what a camera must still show

- OM-Emu is not the camera: no loader, cache, second CPU, ISP or C3D wheel. A fault that needs any
  of them is invisible to it. It did not predict any of the three failures before this analysis.
- The handle's padding is untouched by every access the sessions made, and the stock image holds no
  reference to its address (either alias); that is not proof that no stock code copies or clears the object it sits in.
- `malloc` is called from the HLS_EVENT task, as the E-P7 mod does; E148's heap behaviour there is
  untested on hardware.
- The custom-mode reset now needs 304 more bytes of stack in the menu task. Its margin is unmeasured.
- The first two failures (black screen at start) had the task-92 overlay and the old readiness
  guards. They are not explained by this defect and remain open.
- `KNOWN_BOOT_FAILURES` still blocks `35f0caac…`, the overlay build and `e2ca5b28…`.

Do not treat the corrected build as safe. If a trial is ever made, follow the staged order in
`patches/hsl/om-5-ii/BRICK-RISK.md` and stop at the first anomaly.

## 12 November additions for a further layer

Three changes let another layer (Caduceus) be composed onto this patch without touching its code:

- **Extension vector** `0x613f2ffc` (last word of section 8, zero here). When armed, the half-press hook
  calls the entry stored there, in the HLS_EVENT task, after every section is initialised. Zero: no call.
- **H/L cells accept −7..7**, the span the hue and lightness tables already had. The on-camera editor still
  writes −5..5 and shows the nearest list entry for a wider value; its value label has no text beyond ±5.
- **One section-extent edit is allowed** (`section_extent_10` in `tools/om5ii_boot_audit.py`): the loader's
  end constant for section 10 may move from `0x6169d000` up to `0x616a3000`. The flash span is `0xff`, the
  loader's copy length is `end − start` and nothing else consumes that constant except the bus-monitor
  bound, which then covers the same bytes. This is a change to resident boot code and is unproven on
  hardware; this patch does not use it. No other section end may move.

`tools/om5i_donor_patch.py --donor-patch DIR` builds the transplant from a composed patch directory.
With these, the patch alone builds expanded main and package hashes recorded in `patch.json`
(`42fcf6de…4485`); the OM-5 I candidate changes accordingly.
