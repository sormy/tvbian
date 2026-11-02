# atbm6031 — the AltoBeam ATBM6031 SDIO driver

`modules/atbm6031.conf` builds AltoBeam's vendor driver as gtxaspec/atbm-wifi publishes it, at
`380838e`, with these on top, in order.

| Patch  | Source                                                                   |
| ------ | ------------------------------------------------------------------------ |
| `0001` | NoNamedCat/armbian-tanix-tx1-6031: the 603x on SDIO, the 6.18 API ported |
| `0002` | ours: AltoBeam's SDIO IDs only                                           |
| `0003` | ours: build paths relative to the driver, not `/tmp/wifi-test`           |
| `0004` | ours: `<asm/unaligned.h>` forwarded, the driver's bridging off           |
| `0005` | ours: SAE authentication on, for WPA3                                    |
| `0006` | ours: the MAC set through `eth_hw_addr_set`                              |
| `0007` | ours: TX buffer polls sleep 100–200 µs, not a jiffy                      |
| `0008` | ours: the SDIO bus released between TX buffer polls                      |
| `0009` | ours: 488-byte SDIO blocks, as the stock driver                          |
| `0010` | ours: cfg80211's 6.19 ops, on the `wireless_dev`                         |
| `0011` | ours: BLE through BlueZ, chosen by `wifi_bt_comb`                        |
| `0012` | ours: received frames through NAPI and GRO, as AltoBeam's newer SDK      |
| `0013` | ours: a firmware that rebooted itself reloaded at once                   |
| `0014` | ours: the probe's per-rate power and auto-CFO sent again on a restart    |
| `0015` | ours: DSSS/CCK on a strong link restarts the firmware                    |
| `0016` | ours: routine events at debug level, masked by default                   |
| `0017` | ours: a flush with nothing joined drops, not waits 7 s                   |

`0001` is that repo's `atbm6031_driver_linux6.18.patch` reduced to its substance: the same 214 added
and 63 removed lines in 13 files, without its line-ending and whitespace churn across 132 more. It
selects the 603x, SDIO, and firmware from a file (`atbm6031_fw.bin`).

`0002`: the port matched any SDIO device and any AltoBeam one; on every board carrying the module it
would bind every SDIO card. `0004`: Linux 6.12 moved the header; `bridge.c` includes `<net/ipx.h>`,
gone with IPX in 5.15. `0005`: without its SAE, the driver does not declare `NL80211_FEATURE_SAE`,
and cfg80211 refuses the SAE a WPA2/WPA3 transition network gets. `0006`: a `memcpy` into `dev_addr`
leaves 5.17's shadow copy zero, and the kernel warns `Incorrect netdev->dev_addr`.

`0007` and `0008` raise throughput: with TX confirms off, the driver learns of free firmware buffers
only by polling, and slept a jiffy (up to 4 ms at 250 Hz) every 4 polls, while holding the bus. At
-33 dBm against a wired host: 6.9 up, 14.2 down Mbit/s before; 24.7 up, 17.2 down after, with the
stock firmware. TX confirms on, the other way out, makes the driver exit: `[BH] Fatal error`.

`0009`: the stock 613x driver runs the function at a 488-byte block, so a 1.6 KB frame takes 4
blocks, not 7; `wsm_buf_reserve()` now rounds up instead of masking. With stock's no-BLE firmware:
64.6 up, 61.8 down before; 69.1 up, 70.0 down after.

`0011`: BLE costs Wi-Fi two thirds of its throughput, so the user picks. The glue is built in;
`wifi_bt_comb=1` loads `atbm6031_ble_fw.bin` and registers the controller with BlueZ, the driver's
own `CONFIG_ATBM_SUPPORT_BLUEZ` path, ported to 6.4's `class_create()`, 6.11's void `remove` and
`hci_dev_set_flag()`. At 0, the default, no BLE device is registered and the Wi-Fi firmware is the
no-BLE image. The module now depends on `bluetooth`.

`0012`: frames went up one by one through `netif_rx()`, which GRO cannot merge. Against `plex`:
66.5–69.5 Mbit/s down at 18–19% of four cores before; 79.0–81.4 at 8–12% after.

`0013`: a message numbered 0 out of turn reloads the firmware. The sequence restarting at 0 is the
firmware having rebooted and lost the driver's setup; the driver logged the mismatch and ran on
until a command timed out, 11–26 s later or never.

`0014`: the restart sent neither `wsm_set_rate_power()` nor `"cfo 1 0"`, the firmware's automatic
CFO calibration; its CFO MIB read uninitialised for 40+ min after a restart, and calibrated 1 s
after reassociating with the patch.

`0015`: every 5 s, unicast data from the AP. `latch_strikes` windows of at least `latch_dsss_pct`
DSSS/CCK, above `latch_rssi`, restart the firmware, at most once per `latch_holdoff` (300 s).
`latch_trace`, `latch_fwlog` and `latch_ppm` read the firmware's CFO, forward its log and warn on
its crystal estimate; off by default, as its log over SDIO coincided with faster reboots.

`0016`: every message went out at `KERN_ERR`, routine scans and block-ack sessions included; each
class now prints at its own level, and `atbm_printk_mask` defaults to errors and warnings.

`0017`: after a restart, the scan's idle recalculation flushed under `iflist_mtx`, waiting 7 s for
frames to the lost AP; wpa_supplicant's authenticate waited on the mutex. A forced restart now
reconnects in 2.8 s, not 10.

The driver names its host `mmc1` to nudge a rescan; on 6.18 that is the eMMC, which has a card, so
it only logs. The tree's `mmc-pwrseq` brings the card up.

## Upstream

None submitted. AltoBeam's driver has no road into mainline: it carries its own copy of mac80211.
