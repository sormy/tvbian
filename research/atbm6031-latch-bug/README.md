# ATBM6031 — Wi-Fi rate latch

The Tanix TX1 V2.0's AltoBeam ATBM6031 (SDIO, 2.4 GHz, 1x1 802.11n) goes slow, and drops its link,
with the AP's own networks on channel 1. Channel 6 at 40 MHz holds it. A firmware restart does not.
Measurements are in `worklog.md`.

## Symptom

| State                    | tx bitrate                | rx bitrate        | iperf3 up / down   |
| ------------------------ | ------------------------- | ----------------- | ------------------ |
| healthy                  | 135.0 MBit/s MCS 7 40 MHz | MCS 7             | 66.7 / 67.5 Mbit/s |
| latched, 10169 s in      | 65.0 MBit/s MCS 7 20 MHz  | 11.0 MBit/s       | 18.7 / 3.4 Mbit/s  |
| latched, after reconnect | 65.0 MBit/s MCS 7         | 11.0 MBit/s       | 17.3 / 5.3 Mbit/s  |
| after `rmmod`/`modprobe` | 135.0 MBit/s MCS 7 40 MHz | 65.0 MBit/s MCS 7 | 66.7 / 67.5 Mbit/s |

Signal -41 dBm throughout. A reassociation does not clear that session.

## Known

- `[atbm_log]:aggr token not enough` beside the AP's ADDBA requests, a flat 36 per 10 min all boot,
  latched or not: RX aggregation refused for some TIDs from the start.
- The box's own scan saw the AP at 20 MHz, no secondary, while latched; after the reload, 40 MHz.

## The driver, read

Paths under the built tree's `hal_apollo/`. Rate control runs in firmware
(`CONFIG_RATE_HW_CONTROL`); RF, DCXO and DPLL calibration run only at probe.

- **`aggr token not enough`:** the firmware's RX block-ack slots, a global bitmap sized at load by
  `(Config[0] >> 8) & 0xFF` (`wsm.c:1644`, printed by `wsm_caps.firmwareCap`). Full, the AP's ADDBA
  is declined (`mac80211/agg-rx.c:270`, `:405`) and that TID goes unaggregated; the AP retries.
  Alloc and free balance on every path read: not the latch. First come, first served, so bulk
  (TID 0) can lose its slot; the `ampdu` parameter (default `0xff`) reaches only the firmware, not
  the host's ADDBA handling.
- **`atbm_sdio_irq_period:Miss`** (`apollo_sdio.c:348`): the RX thread's 30 ms idle poll found data
  no interrupt announced, an RX stall each time.
- **Firmware-only reset:** `echo "halt ifname=wlan0" > /sys/module/atbm6031/atbmfs/atbm_cmd` resets
  the LMAC and reloads the firmware without the probe's calibration; block-ack state is not torn
  down (`IEEE80211_HW_AMPDU_AGGREGATION` off), so a reconnect follows it.
- No code watches for a slow but working link.

The box's module lists `spec_oui`, `wifi_freq` and `wifi_txpw`, absent from this tree: confirm the
source before patching by line.

## Newer sources

None public for the 603x past `DRIVER_VER` 3174, gtxaspec/atbm-wifi `master`, the one built here.
Stock's `atbm613x_wifi_sdio.ko` reports `HMAC_VER:3352`, the same counter (`hmac_ver` is
`DRIVER_VER`), unpublished.

- gtxaspec/atbm-wifi `atbm-606x-c` (4327) and `atbm-606x` (33341, its own counter): Wi-Fi 6 chips
  only (`PROJ_TYPE=CRONUS`), but their `bh_sdio.c` receives through NAPI with GRO, as stock does:
  the reference for a backport.
- MultiX0/wudung-w01-linux, the same box as the Wudung W01: the 3174 driver on 7.2.3 with stock's
  19040 firmware, its README listing a BSS_LOST debounce under `CONFIG_TX_NO_CONFIRM`, MIB 0x1024
  rejected and a station-count clamp; it still reports a low TX rate and loss.
- OpenIPC (20811) and Luckfox (226810) are 2022 code despite the numbers.

## Two readings corrected

- `iw`'s tx bitrate is the host's: under `CONFIG_RATE_HW_CONTROL` and `NOTXCONFIRM` every HT frame
  is stamped MCS 7 and reported acked (`txrx.c` `atbm_tx_h_rate_policy`, `bh_sdio.c`
  `atbm_sdio_free_tx_wsm`). Only the rx bitrate and throughput at the peer are real.
- `halt` leaves the host's block-ack sessions standing (`IEEE80211_HW_AMPDU_AGGREGATION` off, so
  `ieee80211_reconfig` skips them) while the reloaded firmware has none: a `halt` test needs
  `stop_ba` or a reconnect after it. The sweep's `halt` result does not stand.

## Token collision

TX and RX block-ack tokens are numbered from 0 in separate host maps (`tx_aggr_map`, 8 from
`Config[0]>>24`; `rx_aggr_map`, 4), sent to the firmware with an rx/tx flag (`ap.c`). After a load:
TX token 0 on TID 0, RX token 0 on TID 7. If the firmware keeps one table, they overwrite each
other. Unverified; a test keeps TX on 4-7.

## Hypothesis

The firmware reboots itself and runs on without the setup the driver gave it. It does not.

## Sweep, 2026-10-27

`tools/sweep.sh`, ten mixes of 120 s with sparse traffic, `iperf3` 5 s each way to `plex` after
each:

- The throughput sank across the run, 26 Mbit/s down at the start to 19 after `--cpu 8 --iomix 2`,
  the rates reading MCS 7 throughout: frames lost behind good rates, no collapse.
- The 20 MHz drops are the AP's: its beacon switched to 20 MHz (`[74:90:bc:12:33:90]:20M channel`,
  `chatype(1)`, HT20) at 12890 s.
- `halt` ran (`bh_halt`, `__atbm_sdio_lmac_restart`, the firmware's capabilities read again) and
  left 17 Mbit/s; a module reload gave 43 at 20 MHz and held 41-45 through the last two mixes. The
  state is not the firmware's: it is what only a reload redoes, the chip reset with its calibration,
  or host state built at probe.
- `wsm_caps.firmwareCap 5184f1a9 4`: four RX block-ack slots in all, behind `aggr token not enough`.

## Player soak, 2026-10-27

`tools/playsoak.sh`: the 4K HDR10 clip decoding in a loop and a 50 Mbit/s stream from `plex` for an
hour, a 10 s probe each way every 5 min. No deep latch; the rx rate the AP picks fell to MCS 1-5
under the stream every sample. Twice, at 429 s and 3676 s:

    atbm_sdio_tx_bh: wait space timeout
    atbm_bh:bh_halt
    __atbm_sdio_lmac_restart: Prepare Restart
    <WARNING>wlan0:AP 74:90:bc:12:33:90 lost.....

The firmware returned no TX buffer for the whole poll budget (120000 polls, a 100-200 us sleep every
4: some 10-15 s; 0007 kept the old 6000 polls at a jiffy each about equal), the driver restarted it,
and mac80211 reassociated. The "AP lost" lines are this, not beacon loss: the beacon monitor is
under `CONFIG_ATBM_MAC80211_NO_USE`, unset, and the driver's BSS-loss confirmation never enters
`CHECKING`. TX tokens after each restart came back as 0-3: no token leak this time.

## Reproduced, and where it lives, 2026-10-27

The player hour latched it with 0007's poll slowed to 1-2 ms (no TX stall all hour): at t+60m up 23,
down 6, rx 11 Mbit/s; idle after, 20.2 / 5.6, `connected time` 3609 s, no reconnect.
`tools/latchdiag.sh`, cheapest cure first, throughput at the peer after each:

| Step                                   | Down | Up   | rx          |
| -------------------------------------- | ---- | ---- | ----------- |
| latched                                | 5.5  | 22.5 | 11.0 legacy |
| `stop_ba`, every block-ack session off | 5.6  | 21.1 | 11.0 legacy |
| `iw disconnect`, reassociated          | 5.5  | 22.5 | 11.0 legacy |
| `halt`, then a reconnect               | 52.4 | 59.2 | 39.0 MCS 4  |

Host block-ack sessions, tokens and the association rebuilt changed nothing; a firmware restart
without the probe's calibration recovered that session. The sweep's `halt` result was the block-ack
mismatch of a `halt` without a reconnect.

## Firmware reboots, 2026-10-27

- `wsm_seq=0` out of turn: the firmware's message sequence restarting, minutes to hours apart under
  the player load. Every TX stall followed one by 11-26 s.
- The restart path skipped the probe's `"cfo 1 0"` and per-rate power: CFO MIB `init 0` after every
  restart until 0014.
- Its log over SDIO (`WSM_MIB_ID_DBG_PRINT_TO_HOST`) coincided with reboots: 4 in 73 min on, 0 in 64
  min off.
- Its own log, forwarded through two reboots on 7.2, is routine to the last line (CPU 12-16%,
  `ppm-4`): the firmware reboots without a warning.
- Firmware strings (`atbm6031_fw.bin`, NDS32): `compenCfo`, `DCXO%u->%u`, `ppm%d,cnt%d`, `WdtCnt`,
  `HIF HW ERR0-8`.

## Verdict, 2026-10-31

There are a few issues, firmware restart causing latch, wireless interference. Both kind of leaded
to horrible experience and fixing AP configuration (moving to another channel with forced 40Mhz wide)
and better handling firmware restart seemed to fix all the issues.

## Reproducing

On channel 1, `tools/playsoak.sh` for an hour: the 4K decode and a 50 Mbit/s stream.
`tools/force.sh` arms of scans, reconnects and heat reproduced nothing in 10 min each.

## Tools

- `tools/bootlog.sh <minutes>`: temperatures, signal, rx and tx rates, a 5 s `iperf3 -R` to `plex`,
  every ~28 s.
- `tools/wifimon.sh`: the link's rates, width, signal and station counters every minute.
