# OM-5 II: second reported boot loop after full stock-span build

5 November 2026. The owner reports that the complete E148 1.1 update built
from `codex/om5ii-stock-section7` at `bc4e4d2` produced **the same boot-loop
result as the 4 November installation**. The owner subsequently reported that
the **stock restore worked fine**. No diagnostic log, installed-flash readback,
section-load status, or capture trace is available. Do not install this build
again.

## Exact build and offline checks

- Complete update SHA-256:
  `cfce2fb8393a20c746a91e94ef4143d880170efed9d43e43b134f87fe67f349c`;
  90,832,896 bytes. Generated from the official E148 1.1 BIN with
  `build_om5ii_overlay_prototype.py --write-complete-update`.
- The package independently parsed and round-tripped. It had all five kinds
  in stock order: `0x100` USR/main, `0x101` OSD, `0x106` RESCOM, `0x10e` LUKE,
  `0x102` PIC. The last three components' headers, payloads and trailers were
  byte-identical to official stock.
- The entire **stored and expanded** Section 6 and Section 7 spans in `0x100`
  were byte-identical to official stock. The stock Section 7 contains the
  in-main updater. The `0x101` OSD component remained modified for icons.
- The changed main still contained the original edits outside Sections 6/7,
  plus a six-byte task-92 hook at `0x6081e2f1` and a 3,804-byte Section-5
  RAM-overlay installer/table at `0x60845d00`. The installer was intended to
  write 16 former Section-6/7 ranges after load. Whether it ran on the camera
  is unknown. OM-Emu exercised its native code with explicit memory setup but
  does not run the physical loader or model instruction-cache behavior.

## What the second result changes

| Hypothesis from the first failure | Effect of this observation |
| --- | --- |
| Changed stored Section-6/7 compression stream is necessary for the boot loop | Weakened substantially: this complete update had stock bytes for both whole spans and still led to a reported boot loop. The actual installed bytes were not read back, and two builds can fail for different reasons. |
| Omitting three components from the first two-component update is necessary for the boot loop | Weakened substantially: this update contained all five official kinds, with the three additional components stock-identical, yet reportedly boot-looped. |
| Changed `0x101` OSD resources contribute to startup failure | Still possible: both failed builds used the modified OSD. The repeated autofocus/screen cycle is not enough to isolate it. |
| Main-image code/data or boot-time hook causes a restart | Still possible. The builds share many non-Section-6/7 edits; the second also adds the task-92 hook and runtime installer. No failing instruction or reset cause has been observed. |
| Stock reflash is impossible after a failed mod | False for these two reported incidents: the owner recovered the camera after each. This does not establish a general independent recovery path. |

The same visible symptom does not prove the same root cause. In particular,
stock compressed spans do not establish that the runtime overlay installed,
that a Section 7 load succeeded on the camera, or that its instruction-cache
state was coherent. The successful stock restore shows recovery on this
occasion; it does not show which part of the modified boot path executed.

## Decision

Both exact update hashes are known to be associated with a physical boot loop:

- 4 November, two-component build:
  `35f0caac4b70f1e59e3d5311fdf74a8c021d720755a7441796b080707b79d434`
- 5 November, five-component stock-span build:
  `cfce2fb8393a20c746a91e94ef4143d880170efed9d43e43b134f87fe67f349c`

Keep both files as evidence and block their regeneration as install outputs.
Do not use the same-feature RAM-overlay design for another camera trial based
on emulator success or the observed recovery. The next useful evidence is a
real reset-to-live-view trace, section-load status, reset/watchdog cause, or a
readback from a controlled service/spare-body setup. Offline work should first
separate the shared early main edits and OSD resources from the new task-92
overlay path, without treating another flash as a diagnostic shortcut.
