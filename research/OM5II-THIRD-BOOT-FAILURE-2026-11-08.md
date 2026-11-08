# OM-5 II: third reported boot loop, after the startup-readiness correction

8 November 2026. The owner reports that the build from `fix/om5ii-startup-readiness`
at `25a336e` **booted, then failed when the colour-profile selection screen was
opened**. This is the first build to reach a running UI on hardware.

## Build

- Package SHA-256: `e2ca5b281b9cb43ff3b7d49c745c908ec02210f79ab9a52245b379afc66d92e1`,
  90,832,896 bytes, written with `tools/oly_patch.py patches/hsl/om-5-ii
  --write-untested-package` from the official E148 1.1 BIN
  (`9de5d77e…d637`). Builder hash checks all passed.
- Components rewritten: `0x100` main and `0x101` OSD only (stock restore file is
  byte-identical to the official BIN).
- Installed as `DCOLYMP/E1489999.BIN` with the OK+power card update.

## Owner's observations (verbatim summary)

1. The update installed and the camera booted normally to its UI.
2. Opening the **colour profile selection screen** (picture-mode selection with the
   restored COLOR1–3 slots) froze the camera for a couple of seconds.
3. The camera then reset into a **boot loop**, and kept looping on every
   subsequent power-on until stock was restored.
4. Recovery: stock reflash (route being re-run at time of writing; update this
   file with the outcome).

No log, reset cause, readback, or exact screen/mode-dial position is available.
Whether the menu entered was the Super Control Panel carousel or the menu item,
and whether a CP slot was highlighted, is not recorded.

## What this changes

| Hypothesis | Effect |
| --- | --- |
| Boot-time failure from early main edits, section-6/7 repack, missing components, or the task-92 overlay (failures 1 and 2) | Weakened for this build: it has none of the overlay and booted. These may still have contributed to failures 1 and 2. |
| Startup guards used the wrong readiness word (6 Nov fix) | Plausibly a real defect, but it did not prevent this failure; it does not explain a post-boot, UI-triggered fault. |
| A runtime fault in code reached only by the picture-mode/colour-profile UI | **Now the leading candidate.** The 2-second hang then reset fits a watchdog or fault while a hook runs. |

Candidates in the hook map (BRICK-RISK.md) executed on opening that screen:
the carousel/label data (`0x61199b5c`, `0x611a1a00/08`), the picture-mode
descriptor and rule tables, the availability lookup (`0x602ddb89/9b`), the
refresh tail (`0x602e0826`) with its section-8 guard, the case hook for modes
54–56 (`0x604997f0`), and the section-7 pages/paint/label hooks. Section-7
hooks in particular were never executed by the emulator on E148's real loader
and GPU path. The two Color Profile paths that the emulator could not exercise
(carousel graphics and wheel/curve pages) are the first suspects.

## Decision

Added `e2ca5b28…92e1` to `KNOWN_BOOT_FAILURES` in `tools/oly_patch.py`, marked
the package `known_boot_failure` in `patches/hsl/om-5-ii/patch.json`, and put a
warning on the patch and repository READMEs. The OM-5 I donor builder
(`om5i_donor_patch.py`) imports the same block list and the same E148 donor
code, so it should be treated as unsafe as well until this is resolved.

Next useful work, offline: bisect by feature using emulator-built variants that
differ only in the carousel/availability data, the refresh/case hooks and the
section-7 UI hooks, and ask for a **real trace** (reset cause, watchdog status,
section-load status) before any further camera trial. A further flash is not a
diagnostic shortcut; each failure so far has needed a stock reflash to recover.
