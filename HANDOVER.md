# Handover: Caduceus for OM-5 (state at 2026-11-14, end of session 1)

Read this first in a new session. It replaces re-deriving the context.

## Goal (owner: Tom / xulfr)
A dedicated, stripped-down `caduceus-om5` repository (Apache-2.0, as the Caduceus family) with OM-5 Mark II (E148 fw 1.1)
first, OM-5 (E144 fw 1.2) second, a GitHub Pages site like androidfanman.github.io/caduceus-om3 (tour, install, using,
FAQ, LookLab), and films loaded from one `LOOKS.BIN`. Owner will hand the project to the community.
Must-haves: film slots from LOOKS.BIN made by the web app, full HSL, ND64, tone curve. Effects (grain, halation) optional.

## Hard facts (do not lose)
- **No OM-5 II build has ever run correctly on a camera.** Three builds boot-looped (4, 5, 8 Nov 2026; owner restored
  stock each time). The 12 Nov candidate (`42fcf6de…`, heap state, no image stores) was NOT flashed as far as the
  repo records. Ask the owner whether it has been flashed since. Everything here is emulator-only.
  The site and patcher must say so and must not present this as a tested install.
- Sources this repo was built from: `xulfr/oly_fw_analysis` branch `fix/om5ii-no-image-stores` (patches/hsl/om-5-ii,
  tools/, research/OM5II-*.md, patches/ports/om-5-i-from-ii). All of that OM-5 code is xulfr-authored, EXCEPT
  `tools/oly_container.py` (fishku, unlicensed): replace it with a container module written from Caduceus's
  `firmware/oe_container.py` (Apache-2.0) before publishing.
- The earlier `caduceus-om5-fork.bundle` (branch port/om5) was not found in any cloud repo. Not needed now.
- References (read-only): `androidfanman/caduceus-om3` v0.29.1 (site layout, LookLab = `webapp/`, patch.py that
  downloads stock firmware from OM's server, FORMATS.md), `cakelesscoder/caduceus-ep7`.
- Session cannot create GitHub repos. This tree is stored as branch `caduceus-om5` of `xulfr/oly_fw_analysis`
  (orphan branch) until the owner creates `xulfr/caduceus-om5` and it is pushed there.

## Workspace recipe (about 5 minutes, all scripted in session 1)
- Toolchain: binutils 2.42 `--target=mn10300-elf` from archive.ubuntu.com `binutils_2.42.orig.tar.xz`
  (configure flags as in caduceus-om3 `research/setup.sh`), installed to `/home/user/work/toolchain/install/bin`.
- Stock firmware: OM's update server serves all three (request as in caduceus-om3 `firmware/patch.py fetch_stock`,
  hard_code `OLYE148…`, `OLYE144…`, `OLYE147…`). SHA-256: E148 1100 `9de5d77e…d637`, E144 1200 `a0c91f3a…3d11`,
  E147 1100 `8c133084…696d`.
- Emulator: `xulfr/om-emu` branch `fix/e148-ipi-stride` (node 22 works). `OM_EMU_MODEL=E148`.
- Build + record hashes: `tools/dev/build.sh NAME` (paths assume /home/user/work). Emulator session:
  `tools/dev/run.sh BUILD OUT 'keys' [--watch --json --cells=ID:N]` (wraps `tools/dev/sess.mjs`, a copy of
  om5ii_ui_session.mjs with a `PRE=script.mjs` hook; `mount.mjs` sets the card-mounted word, which the emulator
  does not model). Keys to reach Color Profile 1: `s1 ok ok` then 8 x `right`.
- `tools/dev/xm.py ADDR`: finds the E148 counterpart of an E147 (OM-3) code address by instruction shape.
  Needs expanded mains in /home/user/work/dec (`oly_compress.expand_image` of component 0x100).

## What exists in this tree
- `firmware/om5ii/`: hsl.s, wb.s, layout.ld, wb.ld, color_profiles.py, nd64.py, patch.json (the 12 Nov base:
  Color Profile 1-3 restored, Hue/Lightness, per-profile WB, Monochrome Profile 1-3, tone curve pages, Live ND32/64)
  plus **films.s (new, session 1)**.
- `card/mklooks.py`: LOOKS.BIN maker (format below). `tools/`: oly_patch.py builder, recorder, boot audit.

## Films layer (films.s) — design and emulator status
- FILM 1-3 = the three Color Profile slots. `C:\OM5MOD\LOOKS.BIN`, magic `OM5F`: 32-byte header (u32 total,
  u32 CRC-32 of bytes 12.., u16 version 1, u16 count 1..10) + count x 80 bytes (64-byte record in the OM-3 LOOKS
  record layout: hue[12] +0, light[12] +12 (-7..7), sat[12] +24 (-5..5), +36 WB on, +37 A/B, +38 G/M (-7..7),
  +41 contrast, +42 sharpness (-2..2), +43 shading (-5..5), +44/45/46 shadows/mid/highlights (-7..7);
  then a 16-byte ASCII name, 12 characters used).
- Half-press (HLS_EVENT task, via hsl.s extension vector 0x613f2ffc -> `fl_entry`, section 10 tail 0x6169c820):
  reads and checks the file into heap block P+152. One attempt per power-on; needs MS_A/B/C == 0xf000.
- **Delete (trash) on the Picture Mode screen while a Color Profile is selected = that slot takes the next film.**
  Values are written with the camera's UI writer `0x60855cdc` (saturation, contrast, sharpness, shading, tone,
  WB shift) and `active_write` part 1 (H/L words, name). Name + index live in part-1 cells 916-919 / 924-927 /
  972-975 (slot 1/2/3), so the film stays in the camera with no card. Inside the colour wheel Delete still only
  switches Saturation/Hue/Lightness (detected by the axis changing).
- String getter hook `0x60d52ed5` (ids 2749-2754, 2859-2861) shows the film name instead of "Color Profile n".
- E148 addresses found in session 1: fopen 0x606aa3bd, fclose 0x606aa3c6, fread 0x606aa54e, medium words
  0x61e43b88/90/98, string getter 0x60d52ed5 (lang fn 0x60d52eec).
- Emulator results (build `6590440c…`): 4-film and 10-film files load; slot 1 -> "Portra 400", second press ->
  "Velvia 50"; slot 2 independent; all 12 H/L pairs, tone, contrast and the WB record correct; no store into the
  firmware image from patch code; bad CRC / out-of-range value / no file / no card -> stock behaviour.
- Known gaps: the title and values redraw only after the highlight moves (two refresh attempts failed: forwarding
  0x900c, re-writing setting 111); Delete on the Sharpness/Contrast/Shading/Tone rows also steps the film;
  empty-card run not yet re-checked (grep choked on binary output, re-run); free loaded-tail space left:
  sec3 384, sec4 656, sec5 ~850, sec6 ~550, sec7 ~250, sec9 568, sec10 ~1000 bytes.

## Still to do (in order)
1. Replace oly_container.py (licence), add README/NOTICE/CLAUDE.md, FORMATS/INSTALL/USING/FAQ/SAFETY docs,
   move research/OM5II-*.md incident reports over.
2. User-facing `patch.py` (downloads stock, applies a release `patch.json` of byte edits, no toolchain) and
   Mac/Windows launchers; keep the "untested" gate until a camera result exists.
3. LookLab for OM-5: fork caduceus-om3 `webapp/`, add an OM-5 mode that writes the `OM5F` file (10 films,
   12-character names, only the fields above), build into `looklab/`.
4. Site: `index.html` tour + `pages/` (install, using, faq, roadmap, changelog) in the OM-3 style, with emulator
   screenshots; prominent experimental banner.
5. OM-5 (E144): carry `patches/ports/om-5-i-from-ii` (donor transplant builder) and rebuild on the films build.
6. Regression tests in `tests/` from the session-1 emulator checks; then a first-flash plan with the owner.
