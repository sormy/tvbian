# arm-trusted-firmware — Trusted Firmware-A, BL31 for Allwinner boards

`uboot/build.sh` builds BL31 at the conf's `TFA_TAG` with its `TFA_PATCHES` over it, and puts it in
the board's U-Boot.

| Patch  | Fixes                                       | Upstream      |
| ------ | ------------------------------------------- | ------------- |
| `0001` | system reset with the watchdog left running | not submitted |

`0001`: `sunxi_system_reset()` sets the watchdog's shortest timeout and waits, without restarting
its count. Linux leaves the watchdog running on a panic, so the count is past the new timeout, the
reset never comes, BL31 panics with `PSCI: System reset failed`, and the board stays dark until its
power is cut. The patch restarts the count, as Linux's `sunxi-wdt` restart handler does. On the
Tanix TX1 V2.0 (H313): a panic with `kernel.panic` 10 brings the box back on its own, in ~50 s.
