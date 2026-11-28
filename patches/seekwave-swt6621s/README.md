# seekwave-swt6621s — driver patches

Fixes for the SWT6621S Wi-Fi/BT driver, applied in filename order to the pinned source by
`modules/swt6621s.conf`, which builds it for every Rockchip kernel.

- `0002` — uplink latching at 6 Mbit/s until re-association.
  [PR #1](https://github.com/retro98boy/seekwave-swt6621s/pull/1)
- `0003` — driver chatter filling the kernel error log.
  [PR #2](https://github.com/retro98boy/seekwave-swt6621s/pull/2)
- `0005` — the factory chip images advertise the HCI codec reads and then assert on them
  (`BSPASSERT:hci_tl.c-386`), ending controller init. The driver answers `0x100b`, `0x100d` and
  `0x100e` locally with Unknown HCI Command so they never reach the chip. Off by default; both
  boards enable it with `skwbt.skip_codec_reads=1` from `firmware/swt6621s/skwbt-options.conf`,
  since both run the factory chip code. Not submitted upstream.
- `0006` — the Bluetooth driver fails to build on 6.11 and later: `platform_driver.remove` returns
  void, and `class_create()` takes no module. Not submitted upstream.
- `0007` — nothing can load the drivers on demand: the SDIO id table is never exported, and the
  Wi-Fi and Bluetooth drivers have no alias for the platform devices they bind. Exports the table
  and adds both aliases, so udev loads all three as the card and its devices appear. Not submitted
  upstream.

Every patch here applies to pinned commit `b1b15016`; after a bump,
`./build.sh kernel kernel/rk35xx.conf` builds the module from them, which is how to check they still
apply.

- `0013` — a chip exception's recovery reloads the chip through the boot device; when that device
  failed to probe, it dereferenced NULL and the oops rebooted the box. Recovery is refused instead:
  the radio stays down, the box up. Not submitted upstream.
- `0014` — with no address passed and none in the chip's eFUSE, the driver drew a random one each
  probe: a new host on every boot. It takes the SoC serial's low bytes under its own `fe:fd:fc`
  instead, random only without a serial. Not submitted upstream.
- `0015` — the board-named firmware the driver tries first is optional, the generic file its
  fallback; asked for as any other, each absent one logged a load failure though the radio came up.
  It is asked for with `firmware_request_nowarn()`. Not submitted upstream.
- `0016` — the firmware answers `SKW_CMD_GET_STA` with 172 bytes of the driver's 385, everything to
  the receive rate. The driver warned on each poll and reported the missing airtime and inactive
  time as zero; it now fills only what the reply carries and reports a short reply once. The reply's
  length comes back while the command lock is still held, so a later command cannot change it. Not
  submitted upstream.

## Mainline

`0008`–`0012` port the driver to mainline 7.3 for `rk35xx-next2`, each change guarded by the release
that made it, so the one series builds for the vendor kernels too:

| Patch  | Mainline change                      |
| ------ | ------------------------------------ |
| `0008` | Namespace strings, padded copies     |
| `0009` | GPIO descriptors, module source path |
| `0010` | cfg80211, timer and wakeup APIs      |
| `0011` | No one-shot flag without a thread    |
| `0012` | Per-CPU TX workqueue named           |

The GPIO port reads a tree's mainline names (`reset`, `host-wake`, `chip-wake`) and, on a kernel
that still has `of_get_named_gpio`, a vendor tree's `gpio_chip_en`, `gpio_host_wake` and
`gpio_chip_wake`; a vendor tree's SDIO power sequence also holds the reset line, which both drive.
It keeps raw handshake levels and shares the active-low reset with MMC power sequencing. Numeric
GPIO and debug overrides are refused. From 7.3 cfg80211 supplies transmit cookies and the driver
keeps them through firmware commands; before it, the driver makes its own. A receive address it
cannot configure is refused.

On the H96 Max 3518D, Wi-Fi associates and Bluetooth comes up on 6.1, 6.12 and 7.3.5. These patches
are not submitted upstream.
