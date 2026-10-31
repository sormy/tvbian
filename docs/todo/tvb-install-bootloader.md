# tvb-install and the bootloader

An install must never leave a box unbootable with no way back. Today `tvb-install` copies every
sector before the rootfs, the bootloader and its DRAM init included, from the disk it runs on.

## Why the bootloader is the risk

- A box whose only button is Android's recovery, read by U-Boot, has no way into the service mode
  once the boot dies before U-Boot: a wrong DDR blob, a corrupt SPL. What is left is shorting eMMC
  CLK or D0, unmarked, under a BGA. A full backup cannot be written to a box nothing reaches.
- Booting from a stick or card does not prove the bootloader that will run from the eMMC: part of
  the boot still comes from the eMMC, and an SD card's DRAM init is not the eMMC's.
- Boxes are sold under wrong and shared names: an image for another board, booted fine from a card,
  then installed, is the expected mistake.
- A board with a BootROM button (maskrom, FEL) only costs a cable to recover; most TV boxes have
  none.
- A direct write over the service mode (FEL, maskrom), the image never booted from external media,
  installs a bootloader that has not run once on the box: riskier than `tvb-install`, and only safe
  where a BootROM button reaches that mode again.

## Proposal

- [ ] **Default: the bootloader on the eMMC stays.** `tvb-install` writes the partition table and
      the rootfs, and no sector below the rootfs. ❓ Per family: whether the factory bootloader
      boots our kernel, from extlinux or a script it reads.
- [ ] **Compare before writing.** The eMMC's bootloader against the image's, region by region; a
      mismatch prints that the image was built for another board or revision, and that booting from
      external media did not prove it: 1) keep the eMMC's bootloader (default), 2) overwrite it
      (destructive), 3) cancel. Keeping it can still fail, where the factory bootloader cannot boot
      ours, so it warns too; it is the lesser risk, the factory U-Boot still reading its button.
- [ ] **A bootloader we must patch** (Amlogic) is patched in place from the eMMC's own, never
      replaced by the one in our package.
- [ ] **Bring-up: a boot from external media that writes nothing to the eMMC**, per family, so the
      bootloader we would install is tested end to end before any install: FEL on Allwinner, the USB
      service mode where it can load a whole U-Boot.
- [ ] **Each family's README outlines its install risks**, before its install routes: whether its
      boxes have a BootROM button or only U-Boot's recovery, which routes write the bootloader, and
      the soft brick a wrong one leaves.
