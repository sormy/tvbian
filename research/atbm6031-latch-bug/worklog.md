# ATBM6031 latch — worklog

## 2026-10-31 — calibration, CFO, the bus, the display

Source read as built: `380838e` with 0001-0017 applied. Paths below are that tree's `hal_apollo/`.
The stock module is `atbm613x_wifi_sdio.ko`, carved from the factory image's `super` partition (ELF,
1072184 bytes, as `sdio.txt` lists it), built from AltoBeam's `atbm6132bs` tree, `HMAC_VER` 3352,
against 4.9.170.

- What the host sends the firmware, ours: at probe `atbm_phy_init()` (ARES_LITE only, returns at
  once unless the firmware's ex-capability `DRIVER_PHY_REG_INIT` is set, `phy_reg.c:1210`),
  `wsm_set_rate_power(1)` and `open_auto_cfo(1)`, `"cfo 1 0"` to `WSM_MIB_ID_FW_CMD` (`main.c:1755`,
  `:1763`, `internal_cmd.c:2058`); a `set_txpwr_and_dcxo` only when
  `/usr/share/wifi/atbm_txpwer_dcxo_cfg.txt` exists (`main.c:1717`); after a restart the last two
  again (`util.c:397`, 0014). Nothing periodic: no timer reads or writes temperature, CFO or DCXO.
- Stock, disassembled: `open_auto_cfo(hw, 1, 0)` formats `"cfo %d %d"` to the same `"cfo 1 0"`, MIB
  0x1039; its only caller outside test ioctls is `atbm_Default_driver_configuration` (probe), beside
  `wsm_set_rate_power(1)`. No caller of `wsm_get_temperature` at all; `atbm_reinit_firmware` sends
  neither. Our restart path sends more than stock's.
- Stock's calibration files are `/tmp/atbm_txpwer_dcxo_cfg.txt` and `/tmp/set_rate_power.txt`, a
  directory Android does not have; `/data/.efuse.info` only with `efuse=1`. No `atbm` config in
  `super`; the `private` partition is all zeros. Stock's `insmod` arguments are not in the dump.
- The eFuse is factory calibrated: `atbmfs/atbm_efuse` and `atbm_first_efuse` both `dcxo[59]`,
  `gain1[25] gain2[25] gain3[26]`; `atbm_get_cfg_power` all 0 (no file). The firmware reads it.
- Firmware capabilities (`atbmfs/atbm_sys`): `LMAC_TEMPC`, `LMAC_TPC`, `AGC`, `TXCAL`,
  `TX_CFO_PPM_CORRECTION` 1; `CFO`, `NOISE_SET_DCXO` 0. Temperature compensation is the firmware's
  own. Stock's dmesg: ex-capability `0x834` (`get chip id [834]`), no `DRIVER_PHY_REG_INIT`: the
  skipped `atbm_phy_init` is right.
- CFO against the AP, `latch_trace=5`: -4 ppm at 431 s (69 °C, latched), +3 ppm at 1000-1056 s
  (66-69 °C, MCS 0-1), -4/-5 ppm at 1319-1862 s (64-67 °C). 802.11 allows ±25 ppm; a few ppm does
  not cost OFDM its fast rates.
- A firmware restart no longer cures it: latched at 431 s, restarted, latched again at 477 s, 38 s
  after reassociating.
- Diagnostic module, `latch_trace` adding the firmware's noise MIB (0x1061), SNR MIB (0x1062) and
  channel idle (0x1053), loaded from `/tmp` over the installed one: right after the reload, the
  player idle, the screen at 3840x2160@60, 65 °C: rx MCS 0-1, `iperf3 -R` to `plex` 5.8 Mbit/s, up
  4.8. Noise reads -70 dBm at `initg` 30-40 (the driver's own help: exact only at 60); SNR
  `10*log10(4096/snr)` median 7.3 dB idle, single samples to 36 dB under heavy RX. The noise MIB
  stays uninformative; the SNR's healthy baseline is below.
- SDIO clock: `/sys/kernel/debug/mmc1/clock` 50 → 25 MHz for 50 s, then back: `iperf3 -R` 2.8 Mbit/s
  at 50, 2.6 and 2.7 at 25, rx MCS 0-1 throughout. The bus clock is not it.
- HDMI: the mode is 3840x2160@60 4:2:0, `tcon-tv0` and `hdmi` at 297 MHz (`clk_summary`), 2.97
  Gbit/s a TMDS lane; its 8th harmonic is 2376 MHz, 36 MHz under channel 1's centre, and the lanes'
  spectrum covers 2.4 GHz. The 10-27 latches came on the BOE monitor, 2256x1504 at 235.5 MHz.
- HDMI at 1080p, live: fuseamp ignores `QT_QPA_EGLFS_KMS_CONFIG` (its own KMS code picks the mode);
  a base-block-only EDID, its DTDs 1920x1080@60, written to
  `/sys/kernel/debug/dri/0/HDMI-A-1/edid_override` and fuseamp restarted gives
  `1920x1080 60 148500`; `printf reset` to the same file and a restart, 4K60 again (`echo reset`
  adds a newline: `I/O error`). `/tmp/measure.sh`, three rounds of 10 s `iperf3 -R` and 10 s up,
  Mbit/s:

| Window, uptime s | Mode       | Down          | Up               | rx rate          | SNR median |
| ---------------- | ---------- | ------------- | ---------------- | ---------------- | ---------- |
| 2208-2319        | 4K60, play | 1.7, 3.9, 3.2 | 15.0, 2.5, 9.4   | 5.5, MCS 1, 1    | 10.1 dB    |
| 2345-2457        | 4K60       | 3.0, 2.3, 1.9 | 7.9, 2.6, 1.9    | MCS 0, 0, 1      | 6.0 dB     |
| 2484-2592        | 4K60       | 1.7, 1.2, 4.0 | 6.2, 5.6, 5.3    | 5.5, 5.5, MCS 1  | 10.0 dB    |
| 2725-2852        | 1080p60    | 8.8, 2.3, 1.1 | 28.8, 22.0, 20.5 | MCS 1, 1, 1      | 10.1 dB    |
| 2878-2998        | 1080p60    | 5.0, 2.8, 5.6 | 5.4, 11.9, 20.4  | MCS 1, 0, 1      | 10.0 dB    |
| 3035-3143        | 4K60       | 3.3, 4.3, 5.0 | 9.2, 14.4, 11.1  | MCS 1, 12, MCS 1 | 10.0 dB    |

- 1080p did not bring the AP's rate to us back: MCS 0-1 throughout, down 1-9 Mbit/s against 1-5. Up
  rose in the first 1080p window, not the second. The 2345 s window was meant as 1080p and ran 4K:
  the Qt config was ignored.
- A MAC change to rule out the AP's per-station state:
  `nmcli dev modify wlan0 802-11-wireless.cloned-mac-address` cannot be reapplied live; not run.
- Reboot, 21:05, fuseamp idle at 4K60, `/root/bootlog.sh` every ~28 s from 24 s uptime (the box warm
  from before, 63-67 °C at every zone throughout): rx MCS 0-1 or CCK 5.5-12 from the first sample, 5
  s `iperf3 -R` 1.3-4.8 Mbit/s. A reboot does not cure it today; bad from the first minute at 4K60
  and at 63 °C.
- Moved nearer the AP and rebooted, 21:11, on the BOE monitor at 2256x1504, `tools/bootlog.sh` for
  15 min: signal -35/-36 dBm; 5 s `iperf3 -R` 64-75 Mbit/s at 40 MHz to 321 s, 1.5-2.5 at 354-393 s
  (rx MCS 0, the link at 20 MHz from 354 s after a scan at 313 s), 46 at 20 MHz from 475 s to the
  end, rx MCS 6-7. No firmware restart.
- Firmware SNR (`snrstat.py` over `latch trace`), chip temperature from the firmware's own MIB:

| Spot          | Signal  | Chip °C | SNR median | `initg` | rx rate      | Down, 5-10 s |
| ------------- | ------- | ------- | ---------- | ------- | ------------ | ------------ |
| by the TV     | -45 dBm | 67      | 9.4 dB     | 32-40   | MCS 0-1, CCK | 1-9 Mbit/s   |
| nearer the AP | -35 dBm | 65-66   | 18.8 dB    | 24      | MCS 2-5      | 64-75 Mbit/s |
| nearer, later | -36 dBm | 66      | 24.7 dB    | 24      | MCS 6-7, 20M | 45-47 Mbit/s |

- The SNR follows the signal dB for dB, at the same chip temperature: an in-band noise floor near
  -55 dBm at the receiver, where a radio is normally near -90. Whether it is the box's own or the TV
  spot's is not yet separated.

## 2026-11-01 — the AP's channel

The AP moved from channel 1 to 6. Same box, iperf3 against a wired host, 15 s:

| AP setting        | Spot      | Signal  | Down, Mbit/s  | Up, Mbit/s |
| ----------------- | --------- | ------- | ------------- | ---------- |
| channel 1, 40 MHz | near      | -35 dBm | 30-44         |            |
| channel 6, 20 MHz | near      | -19 dBm | 18.9          | 24.9       |
| channel 6, 40 MHz | near      | -22 dBm | 72.6          | 62.2       |
| channel 1, 40 MHz | far, 15 m | -45 dBm | 1-9           |            |
| channel 6, 40 MHz | far, 15 m | -53 dBm | 24.5, 33.9 ×4 | 22.6       |

The scan's three networks on channel 1 are the conflict. Channel 6 at 20 MHz stayed slow, 18.9
Mbit/s down near the AP; channel 6 at 40 MHz recovered it, 72.6 down and 62.2 up. At 15 m on channel
6 the box sends at MCS 7, 40 MHz and receives at MCS 2-3. No latch in either channel-6 run. The slow
receive and the drops were this. The 2026-10-31 SNR readings were taken on channel 1.
