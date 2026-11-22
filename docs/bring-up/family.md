# Family bring-up

The largest bring-up: a service mode, backup and restore, U-Boot, an install path and two kernels'
worth of patches, before the first board of the family can land. It lands with that board, its only
validation; its service-mode tool may land alone, validated by a full read and a restore that boots
stock.

## Do

In order: each stage is the way back for the next.

0. **The SoC's datasheet first**, else its reference manual or product brief. Each capability it
   lists is brought up, a row in `docs/todo/<family>.md`, or ➖ with its reason. Its title, revision
   and source go in the family's worklog.
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
   boots: the console font (`TER16x32`), full preemption (`PREEMPT`) at `HZ` 300, which 50 and 60 Hz
   frames both divide, the watchdog armed past a reboot cycle, the kernel pinging between the
   hardware's maximum and systemd's timeout, soft and hard lockups that panic, a panic that reboots,
   `ramoops` with pstore built in, Debian's regulatory database key trusted.
7. **Translate the vendor dialect** when the factory trees are the SoC vendor's and we ship mainline
   (sunxi and Amlogic now; Rockchip if it moves to mainline). Write a
   `tools/dtcx/bases/<source>.translate.conf` (`tools/dtcx/README.md`) so each board's patch holds
   only its own decisions.
   - Pin `soc` to mainline's SoC dtsi at a tag, and `soc-patches` to the `-next` conf (the superset
     both kernels' trees are written from).
   - Run `translate.py --report` on every factory tree in the family. Give each reported token one
     generic outcome, never one board's value: a conversion; `none`, only with evidence that
     dropping it is safe (a mainline driver's source at the pinned tag, or the vendor BSP's);
     `unsupported` when no mainline binding describes the block; `unresolved` when only a board can
     answer.
   - A wrong stock value stays as the vendor wrote it; the fix goes in that board's patch. A board's
     patch is the diff from its translation to its final tree; blocks the board lacks are disabled,
     not deleted.
   - **Explain every drop and question** in the comment above its rule: the evidence for a drop, the
     question for a question. One subject per rule, under a heading; readable beats short.
   - **A SoC fact mainline lacks is a kernel dts patch** in both kernels' confs, never a board's
     patch. A variant with no mainline dtsi gets one (the GXLX2's `meson-gxlx2-s905l3.dtsi`).
   - **Name each cell from the table its own driver used.** That may not be the family's header:
     GXLX numbers GPIOH with 13 pins, GXL with 10, so every M20 pin from BOOT on is 3 higher than
     `gxl.h` says. A table no public tree has is read off the box and kept in `tools/dtcx/headers/`,
     with its evidence.
   - **Diff a translated tree against the last proven one before booting it**:
     `tools/dtcx/semdiff.py <proven.dtb> <new.dtb>`. Explain every line it prints by the conf or the
     patch; anything else is a bug.
   - **The final tree has an upstream view**: `tools/dtcx/upstream.py --prove board.dtb` writes the
     SoC dtsi plus only the board's changes, and proves it describes the dtb
     (`tools/dtcx/README.md`). Its size is what an upstream board file would be; a block in it that
     no board fact explains is a bug.
   - **The view's base is tried, not assumed** (`BOARD_KERNEL_DTB_UPSTREAM`): build the view over
     each upstream board of the SoC and keep the one that shrinks it most; else the SoC dtsi.
   - **Fix translation bugs in the tool**, with a test that fails without the fix, then re-run every
     board's translation: unchanged, or changed only as intended. A conf refactor must leave every
     tree byte-identical.

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
- **A dts patch completes a driver patch**: its message names the driver patch whose compatible
  reads the node. Write a value by its kernel header name, exporting the name where mainline keeps
  it private; a value with no name anywhere (a DMA request, an IOMMU master) is written as mainline
  writes it.
- **A missing rail only shows on the box**: an MMC host without `vmmc-supply` reports no card
  voltage, a GPU without a supply runs unscaled. Boot the translated tree on both kernels, and run
  `video.py` against each kernel's last run (`ffmpeg9` on the box), before trimming a board's patch.

## Check

- [ ] **F0** Every capability the SoC's datasheet lists is brought up, a row in the family's todo
      page, or ➖ with its reason
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
- [ ] **F13** Where the factory trees are the vendor's: every factory tree translates with no
      `unknown`, every drop names its evidence, every question is stated, and each board's patch is
      under 300 lines
- [ ] **F14** Each translated tree compiles, and the board tree built from it is the one proven on
      the box, except for what its patch says
- [ ] **F15** Both kernels' SoC dtsi are byte-identical after their patches
- [ ] **F16** Every cell a header names is written by name: the decompile runs `--strict`, or each
      cell it leaves is a finding in `dtb.md`
