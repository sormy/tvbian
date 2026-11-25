# x98h

X98H, Allwinner H618 (same `sunxi-h616` family as the h96max boards), 4 GB RAM,
~29 GB eMMC, onboard AIC8800 wifi/BT. I've been running Armbian 26.11 on it from
SD, and it also boots from eMMC once installed there (done with `armbian-install`
from the ophub image — `tvb-install` hasn't been tried on this box yet).

Everything below was measured on the actual box, not taken from a datasheet.

## The front panel

The 4-digit display is not wired as 12 GPIOs. It's an **SM1628** (TM1623-class)
serial driver on three wires, and the pin map is declared in the *vendor
loader's* device tree (eMMC `mmcblk2p7`, node `aw_vfd`, compatible
`amediatech,yxt_vfd`):

```
vfd_data_gpio  = <&pio 2 2 0>    PC2  = gpiochip1 line 66
vfd_clock_gpio = <&pio 2 7 0>    PC7  = line 71
vfd_stb_gpio   = <&pio 2 12 0>   PC12 = line 76
```

Cross-check that bank 2 is PC: the eMMC's own pins are PC1, PC5, PC6, PC8..PC11,
PC13..PC16 — exactly the pads those three skip — and `cd-gpios = <&pio 5 6>`
resolves to gpio-166 = PG6, which is what the running kernel reports.

The matrix is transposed: **address selects the segment, data bit selects the
digit**.

```
segments  a=addr0  b=2  c=4  d=6  e=8  f=10  g=12      (odd addresses unused)
digits    bit7 = leftmost ... bit6, bit5, bit4 = rightmost
icons     bit3, chosen per segment address: usb@4 card@6 colon@8 hd@10 cvbs@12
```

The icons share the address byte with a segment, so they have to be OR'd into it.
Writing an icon as its own transaction silently wipes that segment (found that
the hard way: "12:34" was missing segment `e` because the colon ate it).

`panel/` holds the userspace driver: `vfdd` owns the three lines and shows the
clock when nothing else wants the display, `x98h-vfd` is the CLI. It does not
plug into `base/front-panel` because that expects a kernel leds device with a
`message` attribute, and there is no in-tree driver for this chip. If you'd
rather have one, the pin map above plus the transpose is the whole problem; the
rest is just clocking bytes out LSB-first.

## IR

Receiver works (`sunxi-cir`, `rc1`). The vendor DT carries the remote's power
codes:

```
ir_power_key_code0 = 0x40  ir_addr_code0 = 0xfe01
ir_power_key_code1 = 0x1a  ir_addr_code1 = 0xfb04
ir_power_key_code2 = 0xf2  ir_addr_code2 = 0x2992
ir_power_key_code3 = 0x57  ir_addr_code3 = 0x9f00
```

The kernel reports `(addr_low << 8) | cmd`, so the actual scancode is `0x140`,
not `0xfe0140`. All 30 keys on the shipped remote are mapped; I collected them
with `ir-keytable -t` and can send the table as an `/etc/rc_maps.cfg` entry or a
`rc-` keymap if that's the shape you prefer. Right now a small unit loads it.

One gotcha worth knowing: this remote has no colour buttons, and its CH+/- come
through as `KEY_NEXT`/`KEY_PREVIOUS`.

## What's missing / unverified

- **`board.dtb` here is the vendor DT pulled out of `mmcblk2p7`.** It's what the
  stock loader used, not a translated one — replace it with whatever your
  pipeline produces.
- `BOARD_KERNEL_DTB_SOURCE` is left out on purpose: I don't know which vendor
  kernel this box shipped with.
- Nothing here has been through the tvbian build. The panel driver and the pin
  map are tested on the box; the build integration is not.
- `vfdd.service` needs enabling after install.
