# OM-5 II full-feature redesign: stock Section 7

5 November 2026. Offline work on `codex/om5ii-stock-section7`, based on the
xulfr fork's `codex/om5ii-hsl` at `ebda837`. No camera access or installable
image is part of this milestone. The 4 November boot failure remains unexplained.

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

## Investigation order

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
