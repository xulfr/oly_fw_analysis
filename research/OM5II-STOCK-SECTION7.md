# OM-5 II full-feature redesign: stock Section 7

> **DO NOT FLASH.** The complete five-component build SHA-256
> `cfce2fb8393a20c746a91e94ef4143d880170efed9d43e43b134f87fe67f349c`
> produced the same reported camera boot loop as the earlier two-component
> build. The owner reports that stock restore succeeded afterward. See the
> [second incident report](OM5II-SECOND-BOOT-FAILURE-2026-11-05.md).

5 November 2026. Research on `codex/om5ii-stock-section7`, based on the
xulfr fork's `codex/om5ii-hsl` at `ebda837`. This document records the offline
build evidence. A complete image was subsequently installed and failed to boot.
The 4 and 5 November root causes remain unexplained.

**6 November correction:** the installer exceeds the actual section-5 loaded
end by 3,036 bytes. The direct-memory emulator fixture concealed this error.
The builder now rejects it; see [native loader findings](OM5II-STARTUP-FIX-2026-11-06.md).

## Build boundary

The official E148 1.1 main payload contains two `olycompress` spans:

| Firmware section | Stored main-payload offset | Loaded address range | Size |
| --- | --- | --- | ---: |
| 6 | `0x825fe0` | `0x60847000–0x60cbe800` | 4,683,776 |
| 7 | `0xc9d7e0` | `0x60cbe800–0x61343800` | 6,836,224 |

The SD updater `FIRMUP_CLI` is inside Section 7. The failed build changed both
stored spans. For a redesigned manifest, set
`components["0x100"].preserve_olycompress_spans` to at least
`["0xc9d7e0"]`, preferably `["0x825fe0", "0xc9d7e0"]`. The builder then
requires both the expanded and entire stored span to equal the official stock
input, and records their hashes in `build.json`. This is not yet set on the old
manifest: doing so would correctly reject that build. No full-feature candidate
has been built.

## Existing edit inventory

The current HSL manifest has 11 declared Section 7 ranges: `delete_pointer`,
`label_hook`, `container_pointer`, `reset_hook`, `parent_hook`, `paint_pointer`,
`pages_hook`, 840 bytes of `ext7`, and `color_profile_53`–`55` carousel/table
edits. These implement direct-screen pages, axis switching and labels, paint,
reset integration and profile presentation. Their replacement must be found
outside Section 7 or applied in RAM only after the stock span has loaded.

Section 6 has five ranges: `read_hook`, `write_hook`, `display_hook`, 731 bytes of
`ext6`, and 64 bytes of `state`. They implement the H/L editor's value access
and display plus shared state. Moving only the Section 7 ranges would leave a
changed Section 6 stream, which loads earlier. The target is stock equality for
both compressed spans.

The other 70 main ranges include profile descriptors/tables, effective-value
refresh, WB and custom-mode handling, capture builder hooks, and ND32/64. They
are potential building blocks, not a validated standalone feature set. The OSD
resource alias is a separate changed component and should be isolated in the
first redesigned variant.

Initial call-path check: stock `pages_hook` replaces the final call inside
`0x60dad4eb`. A full-image disassembly found direct calls to `0x60dad4eb`
at `0x60dad440` and `0x60dad4ae`; both callers are themselves in Section 7.
A raw pointer scan found no four-byte pointer to any of these three entries.
A further scan places the entry points of those two callers in a Section 7
method table (`0x61009538` and `0x6100955c`). This does not exclude an
indirect or computed higher caller, but the obvious one-level interception
points do not escape Section 7. The earlier emulator handoff also
reports that `parent_hook` was not reached in the UI flows tried and the
Section 6 `display_hook` was not called with the page visible. Those two sites
need an actual-use check before spending relocation effort on them.

`om5ii_overlay_inventory.py` independently validates the locally supplied
official BIN, the failed build's expanded main image and all declared ranges.
It proves that copying the 16 Section 6/7 ranges (1,712 bytes total) into a
stock expanded main reproduces both changed expanded spans exactly. The report
contains addresses and hashes, not firmware or patch bytes. This establishes
the payload needed by a hypothetical RAM overlay; it does not establish a safe
installer. The Section 4 task at `0x6081e273` waits for Section 6 and calls
the task-start routine for `FIRMUP_CLI` at `0x6081e2ea`. Its next instruction
is at `0x6081e2f1`, but that is only a *candidate* interception point: the
Section 7 load state, task scheduling and cache behavior require proof.

## Full-feature main-image design (5 November)

`build_om5ii_overlay_prototype.py` now creates a **non-installable main payload**
from the official BIN and a decoded build of the current source. The current
source was independently rebuilt with `tools/oly_patch.py` and its decoded
main was byte-identical to the archived failed build. The prototype keeps all
non-Section-6/7 main edits, restores both compressed spans to stock, places a
3,804-byte installer/table in verified `0xff` space at `0x60845d00`, and
replaces the six-byte instruction at `0x6081e2f1` with a jump. The installer
waits for Section 7, compares **all 1,712 original target bytes** before any
write, copies the 16 edit ranges through their uncached aliases, replays the
displaced stock instruction, and resumes at `0x6081e2f7`. Extension/state
ranges are copied before hooks and pointers. By default the generated output
contains decoded and stored `0x100` payloads, assembly intermediates and
`build.json`; writing an update container requires `--write-complete-update`.

The prototype builder independently checks linked table addresses, before and
after bytes, hook size, cave capacity, main-image round trip and exact hashes
for the entire stored *and* expanded Sections 6 and 7. Both stored hashes
match the official source (`28e6ccc8…cf152` and `99a299fc…cd97`). The native
OM-Emu fixture reached the stock continuation with its original registers,
PSW and stack preserved, then read back all 16 expected edited ranges. Corrupting one
original byte made the installer return without changing any range. These
tests were performed with explicit emulator RAM setup because OM-Emu does not
run the real E148 loader. A whole-main comparison after simulated overlay
application matches the current full patch except for the new installer and
the six-byte task-92 hook.

The builder can also take the independently rebuilt `0x101` payload
with `--modified-osd`. It validates its exact source-defined hash and writes it
separately, preserving the existing profile-icon treatment. Without that option,
the report names stock OSD. With modified OSD, it composes all five official
components, verifies payloads, metadata and parser round trip, and records a
full-container hash.

At the owner's request, `--write-complete-update` wrote the complete
five-component image to `install/DCOLYMP/E1489999.BIN` and the complete
official stock image to `restore-stock/DCOLYMP/E1489999.BIN`. The full-feature
build generated on 5 November 2026 is 90,832,896 bytes, SHA-256
`cfce2fb8393a20c746a91e94ef4143d880170efed9d43e43b134f87fe67f349c`.
An independent parse and round trip confirmed ordered kinds `0x100`, `0x101`,
`0x106`, `0x10e`, `0x102`; unchanged headers/metadata; byte-identical stock
payloads for the last three; stock stored Sections 6 and 7; and a full stock
restore hash of `9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`.
The owner reports that this complete update caused a boot loop and the stock
restore then worked. Both builders now reject install output for their exact
known failed image hashes.

The output is structurally installable but **not camera-qualified**. The actual Section 7 load completion and
task schedule, physical instruction-cache visibility after RAM writes,
cross-core behavior, saved-settings startup and real capture remain untested.
The original non-Section-6/7 boot-time edits remain, so exact stock compressed
spans alone would not establish the boot-loop cause or a safe recovery route.

Reproduction from this repository, using a locally held official BIN and the
MN103 toolchain (all output paths must be new):

```sh
python3 tools/oly_patch.py patches/hsl/om-5-ii \
  --stock /path/to/OLY_E_148_1100_0000_0000.BIN \
  --out /tmp/om5ii-original-build --decoded \
  --as /path/to/mn10300-elf-as --ld /path/to/mn10300-elf-ld \
  --objcopy /path/to/mn10300-elf-objcopy
python3 research/build_om5ii_overlay_prototype.py \
  --patch patches/hsl/om-5-ii/patch.json \
  --stock /path/to/OLY_E_148_1100_0000_0000.BIN \
  --decoded /tmp/om5ii-original-build/decoded/0100.bin \
  --modified-osd /tmp/om5ii-original-build/decoded/0101.bin \
  --out /tmp/om5ii-overlay-prototype \
  --as /path/to/mn10300-elf-as --ld /path/to/mn10300-elf-ld \
  --objcopy /path/to/mn10300-elf-objcopy
```

## Historical investigation order (superseded)

The steps below were drafted before the second camera failure. They are kept
as design history, not as a recommendation to install another variant. The
[second incident report](OM5II-SECOND-BOOT-FAILURE-2026-11-05.md) governs
further work.

1. For each Section 7 site, trace the stock caller and ownership of the
   pointer/table. Test whether an earlier-section hook can intercept the same
   event and supply the existing UI behavior without writing Section 7.
   Preserve the stock call on every non-profile path. Record ABI, call order,
   load dependencies, and emulator coverage per site.
2. Do the same for Section 6 read/write/display paths. Relocate extension code
   and state into verified spare space outside both compressed spans; check
   ownership, alignment, branch reach, and cross-core visibility.
3. If an outside hook cannot supply a feature, investigate a late RAM overlay
   as a separate design. Prove the installation point follows successful
   Section 7 load and updater-task creation. Prove instruction/data cache
   handling, once-only behavior, atomic patching, and safe behavior under
   concurrent UI/updater tasks before treating it as a candidate. The observed
   writability of Section 7 RAM alone is insufficient.
4. Preserve the corrected H/L profile-source logic in current source, then
   resolve its remaining snapshot-to-build timing window. Repeat the native
   dispatcher/builder/writer fixture for CP1–3 and all 12 sectors; this fixture
   still does not prove real ISP/JPEG output.
5. Build a non-installable candidate with stock Section 7, then stock Section 6
   if the relocation permits it. Assert full-span equality and run saved-state
   boot-path, context/bank, UI and capture regression checks. The current
   emulator bypasses the physical loader, so device loader evidence remains a
   separate gate before any camera trial.

The next decisive result is an outside-section interception map for all seven
Section 7 hook/pointer sites and the three carousel edits. A feature whose
only viable path is a live RAM patch must be marked as such; there is no proven
full-feature no-repack architecture yet.
