# Bring-up over OTG

A box in hand with no serial console. Like an import, the board is built from its stock firmware,
but the box is here: the dump is taken from it, and every check runs on it. The way in is the SoC's
USB service mode on the OTG port; once an image boots, SSH is the console. It suits a box with a
similar board already here: without serial a failed first boot is blind, and a sibling's image is a
first one to try, its patch showing which of this tree's nodes need work. Every command runs on the
host.

## Into the service mode

Unplug the DC supply. On Amlogic, start `build/bin/amlcmd connect` first: the box leaves burning
mode unless the host answers within 750 ms. Hold the box's recovery or FEL button, then plug the
cable into the box and the host. Start with the port most likely to be OTG; if nothing shows, try
each other USB port.

| Family    | Check                         | Shows                        |
| --------- | ----------------------------- | ---------------------------- |
| Rockchip  | `build/bin/rkdeveloptool ld`  | `Loader` on stock, `Maskrom` |
| Allwinner | `build/bin/sunxi-fel version` | `AWUSBFEX` and the SoC       |
| Amlogic   | `build/bin/amlcmd status`     | the gadget that answered     |

## The dump

The whole eMMC, read and verified as `backup.md` says. What it takes depends on the family:

- **Amlogic**: nothing to build; stock's U-Boot is the loader, its burning mode reading the eMMC as
  it is. The mask ROM below it reaches no storage.
- **Allwinner**: a FEL loader, which serves the eMMC as a USB disk. One on guessed DRAM settings, a
  sibling's, reads it as it is; the board's own is built from the boot0 in that dump.
- **Rockchip**: stock's `Loader` stops reading at 32 MiB without an error, so the whole eMMC goes
  through Maskrom and a loader of the board's own. Those 32 MiB hold the idbloader and its DDR blob,
  which the loader is built from; only a broken `Loader` leaves the blob to a guess from the SoC and
  the RAM type.

```sh
./build.sh loader <board>                   # the board's Rockchip or Allwinner loader
```

## First boot

From the dump come the trees and a first image (`dump.md`, `trees.md`, `boot.md`). With an SD slot,
write the image to a card and boot the box from it; without one, the service mode writes it to the
eMMC. Without working Wi-Fi, a USB Ethernet adapter gives SSH. From there the board's phases run as
for any board, every check on the box.
