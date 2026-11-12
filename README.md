# Olympus / OM System firmware research

> **OM-5 Mark II status (12 November 2026):** The current source at `145896f`
> builds an experimental firmware 1.1 candidate with SHA-256
> `42fcf6de11033f155cf2771d4a82c80243383c1ca3e885faa17d155c38c94485`.
> The build and static store/layout checks pass, but this candidate has **not
> been tested on a camera**. See the [patch README](patches/hsl/om-5-ii/README.md)
> for build instructions and limitations.
>
> Three earlier OM-5 Mark II builds failed on a camera: the
> [4 November patch](patches/hsl/om-5-ii/BRICK-RISK.md), the
> [5 November overlay](research/OM5II-SECOND-BOOT-FAILURE-2026-11-05.md),
> and the [8 November startup-readiness build](research/OM5II-THIRD-BOOT-FAILURE-2026-11-08.md).
> The owner restored stock firmware after each. Their failed packages are
> blocked as install outputs; the new candidate does not establish camera safety.

Shared knowledge and tools for studying and modifying Olympus and OM System
camera firmware. The repository covers update files, startup, settings, image
processing and camera interfaces.

PEN-F has the deepest coverage. Comparisons also cover E-M1, E-M5 and E-M10
models, E-P7, OM-3 and OM-5. Findings identify the model and firmware build;
similar code does not imply identical hardware or interchangeable patches.

- [Browse findings by topic](docs/README.md)
- [Set up the tools](REPRODUCING.md)
- [Choose a tool](tools/README.md)
- [Build the PEN-F HSL patch from source](patches/hsl/pen-f/README.md)
- [Build the experimental OM-5 I candidate from the OM-5 II donor](patches/ports/om-5-i-from-ii/README.md)
- [Use IDA with the MN103 module](docs/tooling/ida/README.md)
- [Find firmware identities and sources](provenance/README.md)
- [Contribute a finding or another camera model](CONTRIBUTING.md)

The tools include a component decoder, checksum checks, disassembly helpers,
and an MN103 instruction emulator. Image-processing hardware is not emulated.
Reports distinguish code inspection, execution with modeled hardware, and
physical camera tests.

References are organized by function, with model-specific details below each
topic. Shared formats and cross-model comparisons stay at the topic level.

Supply the firmware files required by each tool. A matching version label is
not enough: check the exact hash. The [update and recovery reference](docs/boot/pen-f/RECOVERY.md)
explains the limits of checksum and recovery evidence.

Ready-to-install PEN-F HSL packages are available under
[Releases](https://github.com/fishcu/oly_fw_analysis/releases):
[17 October 2026](https://github.com/fishcu/oly_fw_analysis/releases/tag/alpha-20261017)
and [13 October 2026](https://github.com/fishcu/oly_fw_analysis/releases/tag/alpha-20261013).
Each includes the patched firmware, stock restore, instructions and checksums.
See [license information](RIGHTS-AND-PROVENANCE.md) before reusing code.
