# Family bring-up

The largest bring-up: a service mode, backup and restore, U-Boot, an install path and two kernels'
worth of patches, before the first board of the family can land. It lands with that board, its only
validation; its service-mode tool may land alone, validated by a full read and a restore that boots
stock.

## Do

In order: each stage is the way back for the next.

1. **The service-mode tool**, built from source in `tools/`, on macOS and Linux: a closed or
   x86-64-only vendor tool is patched open, as `rkdeveloptool` was, or rewritten, as `amlcmd` was.
   Its loader carries the board's own DRAM settings. Proven by a full read and a restore that boots
   stock, before anything else is written.
2. **U-Boot**: the family's approach (`boot.md`), its SPL detecting RAM itself; tested over the
   service mode before it is ever written.
3. **The image layout and `tvb-install`**: where the loaders and the rootfs sit for this family, an
   image booting from external media, and `tvb-install` putting it on the eMMC with the per-unit
   window and the eMMC's bootloader kept. The loader's magic and offset go into `base/board-check`,
   so `apt` refuses another family's board package on these boxes.
4. **Both kernels from the start**: `kernel/<family>.conf` on longterm, `<family>-next.conf` on
   stable. Sources, best first: mainline; the SoC vendor's, where mainline lacks what the board
   needs; an unofficial newer tree, last, from a maintained place. The defconfig starts from a
   maintained distribution's, Armbian's or LibreELEC's; a patch list is explicit, one path a line.
5. **The patches, tested one subsystem at a time**: each set booted from RAM first, then on the box
   by `boot.md`'s procedure for changing a running box, its effect shown on the box before the next.
6. **The family baseline**, diffed against an existing family's built config before the first board
   boots: the console font (`TER16x32`), the watchdog armed within its hardware's maximum, a panic
   that reboots, `ramoops` with pstore built in, Debian's regulatory database key trusted.

## Bites

- **Read the repo's pattern before asking** how to split kernels or patches: the existing families
  answer it.
- **What works on `-next` is a backport to do**: the current kernel gets it before the release, or a
  scoped to-do says why not. Size a backport by applying it: the patch-by-patch failures, then the
  whole subsystem from the newer kernel.
- **One driver stack per function, the same on both kernels**: a series is taken whole for a
  subsystem, never the patches one feature needs.
- **A baseline is claimed only after checking each family's built config.**
- **RAM size is detected, never hardcoded**: a layout the SPL gets wrong is fixed as a quirk in its
  DRAM driver, keyed on what it detects.

## Check

- [ ] **F1** The service-mode tool builds from source, on macOS and Linux
- [ ] **F2** 👤 It reads a box in full
- [ ] **F3** 👤 It restores a box, which boots stock
- [ ] **F4** `kernel/<family>.conf` builds in CI
- [ ] **F5** Its `-next` builds in CI
- [ ] **F6** The family baseline holds on the box: font, watchdog, panic reboot, `ramoops`, regdb
- [ ] **F7** The bootloader approach is built
- [ ] **F8** An image comes out of a release run
- [ ] **F9** Our U-Boot boots over the service mode before it is written
- [ ] **F10** `tvb-install` installs the family's image, the per-unit window and bootloader kept
- [ ] **F11** Each patched subsystem's effect shown on the box, on both kernels
- [ ] **F12** `base/board-check` refuses another family's board package on the box
