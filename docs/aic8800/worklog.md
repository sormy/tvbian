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
