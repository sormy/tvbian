# RK35xx vendor kernel worklog

The vendor kernel, 6.1: its patches and fixes.

## 2026-11-25 — the watchdog at power-off

- next2's `watchdog-dw-wdt-stop-at-power-off.patch` ported to the vendor 6.1 `dw_wdt.c`, from
  `rockchip-linux/kernel` `develop-6.1`, as
  `patches/linux-rockchip/watchdog-dw-wdt-stop-at-power-off.patch` in `kernel/rk35xx.conf`: the same
  added lines; the vendor tree has the sys-off API and the optional `pclk`.
  `patch -p1 --dry-run -F0` against the fetched file: clean. Not yet built or tested on a box: the
  HK1's session was building vendor 6.1.
- Built in `kernel/rk35xx.conf` (12 patches) and installed on the 3518 with its own module packages:
  `systemctl poweroff`, then no answer for 328 s, where 6.1 answered again about 80 s after
  power-off before; the strip brought it back. lima loaded with no error and its devfreq present
  (`drm-lima-devfreq-rockchip-opp.patch`, until now tested on the HK1 alone).
- Installing the image reset the menu default to the newest kernel, next2: put back to 6.1 by hand.
