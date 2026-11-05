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

- [ ] **An underrun count for the VPU.** Without one the rating's 4K60 is unmeasured, and 4K60 NV12
      video is known to glitch. `VIU_OSD1_FIFO_CTRL_STAT` bit 20 moves only when memory is starved,
      but it is no sticky flag: a screen, to tie it to what shows, or the register's documentation.
- [ ] **No HDMI sound at a non-CEA mode.** At 2256x1504@60 (235.7 MHz, no CEA timing), the HDMI PCM
      consumes at 0.74 times real time and the screen stays silent, though its EDID lists 2-channel
      LPCM at 32/44.1/48 kHz; `hdmi-audio-codec` logs `Unknown ELD version 0`, so the ELD never
      reaches the codec. Suspects: meson dw-hdmi's audio N/CTS or I2S clock from a TMDS rate it
      knows for CEA modes only. Check: `speaker-test -D hw:0,0 -r 48000 -c 2` timed against the
      clock.
- [ ] **The MT7668S's known gaps** in mainline mt76, as its patches list them.

- [ ] **Wake the H96 Max M20 from `s2idle` on its Bluetooth remote**, its only remote. The SDIO
      interrupt carries the wake but `meson-gx-mmc` never arms it as a wake source, and `btmtksdio`
      keeps the card powered only in runtime suspend. The other route is the combo chip's host-wake
      GPIO 100, which needs the chip-side pin for the low-power command. Until one works, the M20's
      keys ignore suspend and poweroff.
