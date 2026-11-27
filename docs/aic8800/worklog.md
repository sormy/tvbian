# AIC8800 worklog

## 2026-11-21 — one Wi-Fi MAC on every kernel

- Vendor 6.1 derived the address from `system_serial`; next2 from a CRC of the OTP id named by a
  `soc-id` cell: two addresses for one box. `99-stable-mac.patch` now reads the root `serial-number`
  U-Boot writes, the fused SoC ID hashed, on every kernel; the `soc-id` cell left both RK3528
  AIC8800 boards' next2 patches.
- The H313's address comes from its tree's `local-mac-address` and does not change.

## 2026-11-21 — Bluetooth on next2, and what the translator dropped

- `bluetooth-hci-h4-aic8800-bdaddr.patch` derived the address from `system_serial`, empty on
  mainline. It now reads the root `serial-number`, as `99-stable-mac` does; a 7.x copy in
  `patches/linux-rockchip-mainline/` uses `hci_set_quirk()`.

## 2026-11-21 — AIC8800 `96` and `97` on the vendor kernels

- On the R69-1: `96` on 6.1.172, the phy following `iw reg set`; `97` on 6.12.69, two reloads where
  6.12 failed before. Each release logs `aicwf_sdio_release: reg:0 write failed!`; the next load is
  unaffected.

## 2026-11-22 — `wifi.reloads` on 6.1: the suite reloaded nothing

- The regression's 6.1 runs failed `wifi.reloads` (0 of 1) on the R69-1 and the HK1, 6.12 and next2
  passing. By hand, two reloads on 6.1 each had an address after 4 s.
- The suite reads the module from `/sys/class/net/wlan0/device/driver/module`. 6.1's
  `sdio_register_driver()` records no owner, 6.12's sets it, so on 6.1 `aicwf_sdio` had no module
  link and the suite ran `modprobe -r module`.
- `95` sets `.drv.owner` in `aic8800_fdrv`'s `aicwf_sdio` and `aic8800_bsp`'s two SDIO drivers. On
  the R69-1, 6.1: the link names `aic8800_fdrv`; the suite's own reload code, two of two back.

## 2026-11-24 — a host rebind under the loaded driver

- The HK1, 6.1: `ffc20000.mmc` unbound and bound with `aic8800_fdrv` loaded. The card enumerated
  `c8a1:0082`; `aicwf_sdio_probe` oopsed in `aicbsp_get_feature`, a NULL at `0xb4`, in
  `mmc_rescan`'s worker. The reboot after it waited 5 minutes on unkillable processes.
- With both modules unloaded around the rebind, five of five came back with an address.
- `94`: the Wi-Fi probe refuses a card the platform driver did not power up, `get_sdio_func()` NULL
  where the platform driver holds no card. Built for 6.1 and 6.12: the probe calls `get_sdio_func`
  before its first allocation, which tests for NULL (`llvm-objdump`).
- With `94` on the HK1, the host unbound and bound under the loaded driver: no oops, function 1
  unbound, function 2 on `aicbsp_sdio`, no `wlan0`; unloading `aic8800_fdrv` brought it back. Three
  of three on 6.1, three of three on 6.12.
- Unloading the Wi-Fi driver re-probes the host (`97`), and udev loads `aic8800_fdrv` back by the
  card's modalias: an `rmmod` of both modules finds the platform driver in use when udev wins.
