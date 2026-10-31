# H96 Max M20: what is left

The board's open items.

- [ ] **Wi-Fi stays on 2.4 GHz.** Not mt76: both bands join, and `0013` reloads the firmware for a
      switch between the access point's two BSSIDs. The box's network pins `bssid=` to the 2.4 GHz
      radio, and with no `bgscan` nothing re-picks once joined. Next: the SSID alone plus `bgscan`,
      then time a band switch, which `0013` costs about 6 s.

- [ ] **Sluggish.** Idle, zram and CMA sat unused for 8 h 26 min, 2026-10-20, which says nothing
      about load. Play 4K and watch `vmstat 1` and `CmaFree` together.

- [ ] **Unbrick from the mask ROM.** Needed only once the eMMC's bootloader is gone; the factory
      U-Boot's burning gadget covers every other path. A USB-boot BL2 from
      `stock/h96max-m20/loader-stages/bl2.sign` and `acs.bin` (format v3), repacked with `gxlimg`
      and committed beside the board as Rockchip's `maskrom_loader.bin` is; then `amlcmd` loads it
      and U-Boot, which takes bulk writes and BL2's USB stage — `pyamlboot` has both. Safe to try:
      `amlcmd set_usb_boot 2` enters the ROM, a power cut leaves it.

- [ ] **The watchdog left a hard hang standing.** A VP9 4K decode hung the SoC at 13:51 on
      2026-10-31; no reset followed, the box stayed down until power-cycled at 13:58. No hang that
      day reset: each was a power cycle. `meson_gxbb_wdt` is active, 80 s, petted by systemd. The
      previous boot's journal stops with no oops.

- [ ] **The MT7668S's known gaps** in mainline mt76, as its patches list them.

- [ ] **Wake the H96 Max M20 from `s2idle` on its Bluetooth remote**, its only remote. The SDIO
      interrupt carries the wake but `meson-gx-mmc` never arms it as a wake source, and `btmtksdio`
      keeps the card powered only in runtime suspend. The other route is the combo chip's host-wake
      GPIO 100, which needs the chip-side pin for the low-power command. Until one works, the M20's
      keys ignore suspend and poweroff.
