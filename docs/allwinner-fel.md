# Allwinner FEL — back up, restore, install

FEL is a USB rescue mode built into the chip. Through it the host, macOS or Linux, runs a small
loader that shows the box's eMMC as a USB disk. Every command here runs on the host.

A FEL button is wired to the chip and works whatever is on the eMMC. A recovery button is read by
the bootloader on the eMMC instead, so it works only while that bootloader runs.

## Prerequisites

A USB-A male-to-male cable for the box's OTG port, and the box's FEL or recovery button. Keep the
box's power supply unplugged: the cable powers it, and both at once can damage the box or the host.
Build the tools once:

```sh
./build.sh tool sunxi-fel                    # -> build/bin/sunxi-fel
./build.sh loader <board>                    # the loader -> boards/<board>/fel_loader.bin
```

A serial adapter is optional: it shows the loader's log when something fails.

## Start the loader

Hold the button, plug the cable into the box and the host, and let go after two seconds; the screen
stays dark. Check the box is in FEL (if not, unplug and try again), then start the loader:

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

## Recovery

With a button wired to the chip, the steps above work whatever state the eMMC is in. With one the
bootloader reads, they work while the bootloader runs. Either way an SD card holding an image boots
first: the chip tries it before the eMMC.

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

Write the image around the family's `preserve-sectors`, which holds the box's MAC address, serial
number and keys:

```sh
xz -dc <image>.img.xz > image.img
pos=0
for range in $(grep -o '^[0-9]*-[0-9]*' boards/common/preserve-sectors.sunxi-h616); do
  first=${range%-*}
  [ "$first" -le "$pos" ] || sudo dd if=image.img of=<disk> bs=512 skip=$pos seek=$pos count=$((first - pos))
  pos=$((${range#*-} + 1))
done
sudo dd if=image.img of=<disk> bs=1M skip=$((pos / 2048)) seek=$((pos / 2048))   # the rootfs
sync
```

## Caveats

- **No disk after the loader:** serial shows why.
- **macOS asks for approval:** every `sudo` wants the password, and a new disk may need allowing.
- **macOS says `Operation not permitted` on `/dev/rdiskN`, even with `sudo`:** the terminal app
  needs Full Disk Access (System Settings, Privacy & Security).
- **The desktop opened the box's partitions first:** macOS writes a `.fseventsd` folder to each,
  harmless, on partitions Android never reads.
