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


## Bluetooth

Works, but not out of the box: the AIC8800's BT half is on **UART1** (PG6/PG7, with
PG8/PG9 as RTS/CTS) and needs a serdev child, which the vendor DT has and a stock
arm64 DT doesn't.

The vendor nodes, from `vendor_boot_a` in the Android image:

```
bt    { compatible = "allwinner,sunxi-bt";
        clocks = <&r_ccu ...>; clock-names = "osc32k-out";
        bt_rst_n    = <&pio 6 19 1>; }      /* PG19, active low */
btlpm { compatible = "allwinner,sunxi-btlpm";
        uart_index  = <1>;
        bt_wake     = <&pio 6 17 0>; }      /* PG17, active high */
        bt_hostwake = <&pio 6 16 1>; }      /* PG16, active low  */
```

`aic8800-bt-overlay.dts` here is the overlay that makes it work with the in-tree
`hci_aic8800` serdev driver (compatible `aic,aic8800-bt`).

Two things that cost me the afternoon, in case they save yours:

- **The polarity flags are load-bearing.** With `enable` active-high the driver
  still logs `enable(BT_REG_ON)=1` and `bt_fw_ready=1`, but the controller never
  registers and `btmgmt info` says "Index list with 0 items". Use
  `enable` **active-low**, `device-wakeup` **active-high**, `host-wakeup`
  **active-low** — that's the vendor's set and it's the difference between a dead
  adapter and a working one.
- **Keep `max-speed = <1500000>`.** At 115200 the driver's own handshake passes but
  HCI Reset (0x0c03) times out, because the chip has already switched its own baud.

With that, `hci0` registers, `bluetoothctl` shows the controller, and a scan finds
devices normally.

## What's missing / unverified

- **`board.dtb` here is the vendor DT pulled out of `mmcblk2p7`.** It's what the
  stock loader used, not a translated one — replace it with whatever your
  pipeline produces.
- `BOARD_KERNEL_DTB_SOURCE` is left out on purpose: I don't know which vendor
  kernel this box shipped with.
- Nothing here has been through the tvbian build. The panel driver and the pin
  map are tested on the box; the build integration is not.
- `vfdd.service` needs enabling after install.
- The BT overlay above is tested on Armbian 6.18; on tvbian it could go straight
  into `board.dts` instead of being an overlay.
