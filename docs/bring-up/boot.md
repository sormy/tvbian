# Boot

From loaders to an installed system, and how a running box is changed without losing it.

## Do

1. **The board data**: copy the closest `boards/<board>/`, change only what the dump says.
   - `board.conf`: `BOARD_ID`, `BOARD_NAME`, `BOARD_PCB`, `BOARD_DATE`, `BOARD_FAMILY`,
     `BOARD_HOSTNAME`, `BOARD_KERNEL`, `BOARD_UBOOT`, `BOARD_DEPENDS`, the `_DTB_SOURCE` and
     `_DTB_TARGET` bases, `BOARD_HOME` and `BOARD_STORE`, and the family's own keys.
   - `package.list`: mode, repo file, install path, at Debian's paths; `link <target> <dest>` makes
     a symlink.
   - **Firmware is per chip, the SoC's blocks counted**: `tvb-firmware-<chip>` from
     `firmware/<chip>/`, the vendor's from the stock image, assumed the same on every board. A file
     keeps its stock name, mapped by `package.list` to what the driver asks for; settings variants
     (Seekwave's RF NV by antenna) ship in the chip package, the board picking one with a `link`.
     Firmware only one board needs goes in its own package, at `/usr/lib/tvb/firmware`, searched
     first.
2. **The loaders**, by family:

   | Family    | Factory, kept           | Ours                                           |
   | --------- | ----------------------- | ---------------------------------------------- |
   | Rockchip  | the idbloader: DDR init | U-Boot, with `uboot.dts` from the factory tree |
   | Amlogic   | U-Boot, and its tree    | mainline U-Boot, chain-loaded, no board tree   |
   | Allwinner | boot0's DRAM settings   | mainline SPL and U-Boot, settings from boot0   |

   The service-mode loader never depends on the board tree: a tree bug must not take the way in
   away.

3. **RAM before anything else**: `mtest` over every range from a U-Boot loaded over the service
   mode, then `stress-ng --vm` over most of RAM on the first boot. A box that fails only under
   memory load has a RAM fault until shown otherwise.
4. **The first boot from RAM**: the service mode loads U-Boot, the tree and a boot script; the
   kernel boots with nothing written. Then from an SD card or USB stick, the eMMC untouched.
5. **Network first**: a boot that comes up on Ethernet or Wi-Fi and takes `ssh`; the USB Ethernet
   adapter stands in until the board's own works (`r8152` is in every family's kernel).
6. **Install** with `tvb-install` from external media, which keeps the eMMC's bootloader.
7. **Changing a running box**, every tree or kernel change:
   1. a second way in plugged: USB Ethernet or serial;
   2. a driver patch is built and loaded on the box, no reboot; only a kernel change needs one;
   3. the kernel builds through `./build.sh`; a string only the patch adds, `grep -a` in
      `/boot/vmlinuz-*`, proves the installed image is the one tested;
   4. the test kernel goes in beside the known-good one, never over it;
   5. the kernel and every driver package of its release in one `dpkg -i`; before the reboot
      `modinfo -k <release> <driver>` finds each out-of-tree driver;
   6. the reboot is bounded: back on `ssh` within 2 min, or straight to the second way in;
   7. after: `uname -r` and `/boot/config-$(uname -r)` show the build just made, `ip -br link` has
      every interface, `lsmod` every driver, `dmesg -l err,warn` nothing the last good boot did not.

## Bites

- **A box that boots U-Boot is never lost**: stop it over serial, load the disk's kernel and tree,
  `fdt rm` or `fdt set` the suspect, `booti`.
- **A log that stops at `bootconsole [uart0] disabled`** is not a hang yet: boot with `keep_bootcon`
  and the kernel's last words show.
- **A test harness checks its own premise** in the log before it reports: the test kernel's or
  tree's marker line, or the run tested nothing. Bootstd ignores a FEL script and boots the disk.
- **A new tree's U-Boot is tested over the service mode** before it is written: there the SPL has
  set nothing up for it.

## Check

- [ ] **O1** The service-mode loader boots without the board tree
- [ ] **O2** `mtest` passes over every RAM range
- [ ] **O3** 👤 A kernel boots from RAM over the service mode, nothing written
- [ ] **O4** 👤 The image boots from an SD card or USB stick, the eMMC untouched
- [ ] **O5** It comes up on the network and takes `ssh`
- [ ] **O6** On Rockchip, the image's loaders at sectors 64 and 16384 are the board's
- [ ] **O7** `/usr/lib/tvb/board.dtb` is identical to `boards/<board>/board.dtb`
- [ ] **O8** Every firmware file is in its chip's or SoC's package, or the board's where it differs
