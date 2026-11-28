# SWT6621S worklog

## 2026-11-15 — first mainline build and translation

- The vendor Seekwave driver fails on 7.3: removed OF integer-GPIO lookup, unquoted namespace,
  `strncpy`, changed cfg80211 callbacks, wakeup-source and timer APIs, vendor `rfkill-wlan.h`.
- A separate `swt6621s-mainline` module variant; the vendor variant unchanged.
- GPIO consumers use descriptors and raw levels; numeric GPIO/debug overrides are refused.
- GPIO3_B2 belongs to MMC reset; the vendor driver accesses it without ownership after its GPIO
  request fails. The mainline variant requests it nonexclusively, with MMC reset's active-low
  polarity.
- Kbuild: external `src` is relative to the module root, not the kernel root. Corrected the
  version-header generator path.
- cfg80211 owns management and remain-on-channel cookies on 7.3. The port preserves those values
  through firmware commands; it refuses a remain-on-channel receive address it cannot configure.
- All three radio modules compile.
- The first combined build failed: the module conf sourced its base relative to the kernel build
  directory. The mainline variant is an independent pin/config.

## 2026-11-15 — ready for the first boot

- A binding for the radio GPIO consumers and the Seekwave vendor prefix.
- The reset consumer is `reset-gpios`; MMC and the loader share its active-low descriptor.
- Build log: `build/out/logs/rk35xx-next2/module-swt6621s-mainline.log`.

## 2026-11-16 — Power-domain policy diagnostic

- Module aliases cover SDIO IDs only. The platform boot driver registers after SDIO discovery, so
  exporting its OF table alone would not fix a missing card.

## 2026-11-16 — SDIO found: the radio's PCM pins

- The chip answers CMD5 on mainline once SAI0's `i2s0m0` pins, its PCM, are muxed as the factory
  tree has them; `skw_sdio_lite` and `skwbt` then load and `wlan0` associates.

## 2026-11-21 — one Seekwave conf for every kernel

- `modules/swt6621s-mainline.conf` folded into `modules/swt6621s.conf`: `0008`–`0012` guard each
  mainline change by the release that made it (assoc response struct 6.7, `hrtimer_setup` 6.13,
  `set_monitor_channel` 6.13, `radio_idx` 6.17, `WQ_PERCPU` 6.17, wdev key and station ops and the
  action frame 7.1, `beacon.ht_required` 7.2, value cookies and `probe_client` gone 7.3).
- `0009` reads the vendor tree's `gpio_*` names where `of_gpio.h` still exists; the vendor tree's
  SDIO power sequence holds the reset line, so a busy request there drives it shared, as next2's
  `NONEXCLUSIVE` does.
- Wrong turn: module packages built against today's 6.1 rebuild were installed over the boxes' 31
  October 6.1 kernel of the same version string; 14,442 exported symbols' CRCs differ and the Wi-Fi
  module did not load. A kernel and its modules go on together, from one build.

## 2026-11-21 — the Seekwave address: the chip's, else the SoC serial

- The driver took its address from the `mac` parameter, the vendor kernel's `WIFI_MAC`, then the
  chip's eFUSE, else `eth_random_addr` under `fe:fd:fc`: a new host every boot. The 3518, 3518D and
  M2 Plus store no `WIFI_MAC` or `BT_MAC`, yet kept one address across boots and kernels: the chip's
  eFUSE.
- `0014` replaces the random draw with the SoC serial's low bytes. The fallback itself is not
  exercised on these boxes.
- The retired `tvb-swt6621s-mainline-modules` debs were still in `build/out/debs/`: deleted.

## 2026-11-24 — the board firmware's misses and `GET_STA`'s short reply

- `0015`: the board-named firmware the helper tries first is optional; asked with
  `firmware_request_nowarn()`, three boots of the H96 Max 3518 on next2 7.3.6 log no "Direct
  firmware load", where each boot logged four, and the radio comes up as before.
- `0016`: the firmware answers `SKW_CMD_GET_STA` with 172 bytes of the driver's 385, the struct
  without `tx_percent`, `rx_percent` and `sinfo`; the driver warned on each poll (11–22 in a soak)
  and reported those as zero. It records the reply's length, fills only what it carries and reports
  a short reply once. The 3518 on next2: 20 polls, no warning, one "replies 172 of 385 bytes";
  `iw dev wlan0 link` −27 dBm. `iw station dump` is empty on every kernel: the driver has no
  `dump_station`.

## 2026-11-28 — `0016`'s reply length under the command lock

- `0016` read the station reply's length from `skw->cmd` after `skw_msg_xmit_timeout` had released
  the command lock, so a command in between could change it. `skw_msg_xmit_reply()` now hands the
  length back before the unlock, `skw_msg_xmit_timeout` a wrapper passing none, and GET_STA asks
  through `skw_send_msg_reply`. Both bounds are `offsetofend`; the once-only bitmap moved below the
  includes.
- The H96 Max 3518, each kernel with its own build's module packages, 20 `iw station get` polls:
  next2 7.3.6 by kexec from 6.1, vendor 6.1 by reboot, vendor 6.12 by kexec from 6.1. On each: no
  "expect len" warning, one "GET_STA replies 172 of 385 bytes", no inactive time reported, no
  firmware load failure, no kernel warning; a scan (29 to 36 networks) and a reconnect clean.
- Before the fix, the 6.1 module built for the watchdog test already carried `0015` and the first
  `0016`: the same counts, the first run of either on a vendor kernel.
