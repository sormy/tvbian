# x98h — bring-up state

X98H, Allwinner H618, PCB silkscreen `Y8927_141_V1.1 23253`. Photos of both sides
are in this folder. A full user-area eMMC dump exists (31,268,536,320 bytes,
matching `/sys/block/mmcblk2/size × 512`), kept offline per `dump.md`.

What is in the branch so far, and what it is not:

| File | What |
|---|---|
| `boards/x98h/vendor_board.dtb`, `.dts` | the vendor U-Boot tree, carved from `mmcblk2p7` at the `d00dfeed` magic |
| `boards/x98h/upstream_board.dtb` | the mainline H618 tree that currently boots this box (from Armbian), a starting point for the translation |
| `boards/x98h/factory_boot0.bin` | sector 16, 128 sectors: the `eGON.BT0` stage |
| `boards/x98h/board.conf` | board data; `_DTB_SOURCE` deliberately absent until the vendor kernel version is read from its own image |

There is **no `board.dtb`**: the vendor tree is not a translated one, and using it
would be pretending the translation is done. That, and the rest of the run, is the
work this branch still needs.

## Front panel

The 4-digit display is an **SM1628** behind three wires. The vendor tree declares
it as `amediatech,yxt_vfd`:

```
vfd_data_gpio  = <&pio 2 2 0>    PC2
vfd_clock_gpio = <&pio 2 7 0>    PC7
vfd_stb_gpio   = <&pio 2 12 0>   PC12
```

None of those is a hardware SPI controller, so the intended node is a `spi-gpio`
bus with a `titanmec,tm1628` child, taking the `digits { digit@N { segments = <row col>, ... } }`
shape from `hk1-rbox-k8s`. Segment/address facts measured on this box, which the
node's mapping has to express (address = segment line, data bit = digit):

```
segments  a=addr0 b=2 c=4 d=6 e=8 f=10 g=12      (odd addresses unused)
digits    bit7 = leftmost ... bit4 = rightmost
icons     bit3, per segment address: usb@4 card@6 colon@8 hd@10 cvbs@12
```

## IR

`sunxi-cir` on `rc1`. The vendor tree carries the remote's power codes
(`ir_power_key_code0..3` / `ir_addr_code0..3`); the shipped remote's full key set
was captured on the box and can go in as an `rc_maps.cfg` entry if wanted.
