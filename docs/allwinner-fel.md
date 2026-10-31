# Allwinner FEL — back up, restore, install

FEL is a USB mode built into the chip: it works whatever is on the eMMC, even on a box that no
longer boots. Through it the host, macOS or Linux, runs a small loader that opens the box's eMMC as
a USB disk. Every command here runs on the host.

## Prerequisites

A USB-A male-to-male cable for the box's OTG port, and the box's FEL button. Keep the box's power
supply unplugged: the cable powers it, and both at once can damage the box or the host. Build the
tools once:

```sh
./build.sh tool sunxi-fel                    # -> build/bin/sunxi-fel
./build.sh loader <board>                    # the loader -> boards/<board>/fel_loader.bin
```

A serial adapter is optional: it shows the loader's log when something fails.

## Start the loader

Hold the FEL button, plug the cable into the box and the host, and let go after two seconds; the
screen stays dark. Check the box is in FEL (if not, unplug and try again), then start the loader:

```sh
build/bin/sunxi-fel version                 # AWUSBFEX soc=…
build/bin/sunxi-fel uboot boards/<board>/fel_loader.bin
```

A few seconds later the eMMC appears as a disk. Find it by its size and unmount it at once, before
the desktop uses it. Below, `<disk>` is `/dev/rdiskN` on macOS, `/dev/sdX` on Linux.

```sh
diskutil list external physical             # macOS: /dev/diskN
diskutil unmountDisk /dev/diskN
lsblk -d -o NAME,SIZE,TRAN                  # Linux: /dev/sdX, TRAN usb
sudo umount /dev/sdX?*
```

When done, eject the disk (`diskutil eject /dev/diskN`, `sudo eject /dev/sdX`), unplug the cable and
plug the power back in.

## Back up

The whole eMMC, the box's MAC address, serial number and keys included: the only way back to stock
Android. Tens of minutes.

```sh
sudo dd if=<disk> bs=4M | xz -T0 > backup/<board>-stock.img.xz
```

## Restore

The box's own backup, written back whole:

```sh
xz -dc backup/<board>-stock.img.xz | sudo dd of=<disk> bs=4M
sync
```

## Install

On a box with an SD card slot, booting the image from an SD card and running `sudo tvb-install` from
it is recommended instead: the box runs the image before anything is written to its eMMC.

An image is written around the box's secure storage, which holds its MAC address, serial number and
keys. The first line reads its sectors from the board's `preserve-sectors`:

```sh
read first last <<<"$(sed -n '1s/^\([0-9]*\)-\([0-9]*\).*/\1 \2/p' boards/<board>/preserve-sectors)"
xz -dc <image>.img.xz > image.img
sudo dd if=image.img of=<disk> bs=64K count=$((first / 128))   # 64K: 128 sectors
sudo dd if=image.img of=<disk> bs=64K skip=$(((last + 1) / 128)) seek=$(((last + 1) / 128))
sync
```

## Caveats

- **No disk after the loader:** serial shows why.
- **macOS asks for approval:** every `sudo` wants the password, and a new disk may need allowing.
- **macOS says `Operation not permitted` on `/dev/rdiskN`, even with `sudo`:** the terminal app
  needs Full Disk Access (System Settings, Privacy & Security).
- **The desktop opened the box's partitions first:** macOS writes a `.fseventsd` folder to each,
  harmless, on partitions Android never reads.
