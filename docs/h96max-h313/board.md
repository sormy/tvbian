# H96 Max H313 — board details

## Identity

| Field           | Value                                 | Source                              |
| --------------- | ------------------------------------- | ----------------------------------- |
| Model           | H96 Max H313                          | Owner                               |
| SoC family      | Allwinner H616/H313                   | FEL `soc=00001823(H616)`            |
| Exact SoC       | H616 die, sold as H313                | FEL; listing                        |
| RAM             | LPDDR3, 600 MHz, 2048 MiB configured  | Factory boot0                       |
| eMMC            | 15758000128 bytes                     | USB block device                    |
| PCB             | `BA979_627_V1.0`; code `24353`        | `pcb-top.jpeg`                      |
| Ports           | SD, 2 × USB-A, AV, HDMI, Ethernet, DC | Owner                               |
| OTG             | USB-A nearest SD slot                 | Owner's port description            |
| Power           | 5 V / 2 A                             | Owner                               |
| LED             | Bicolor: blue and red                 | Owner                               |
| IR              | Bundled H96 Max remote, NEC 0x04      | Owner; stock wake list              |
| Serial          | RX / TX / GND beside AV               | `pcb-bottom.jpeg`                   |
| Wi-Fi / BT chip | AIC8800D40L                           | `pcb-wifi.jpeg`, sticker on the PCB |
| Ethernet PHY    | AC300 EPHY, co-packaged, 100 Mb/s     | SID word 0x2c = `0x0507`            |
| Photos          | Product, PCB top/bottom, radio        | JPEGs beside this file              |

Product pages: <https://h5.h96max.com/products-details/h96-max-h313-android-14-4k-wifi-6-tv-box>
(`BOARD_HOME`), and <https://www.h96tvbox.com/product/h96-max-h313-android-14-atv-tv-box/>. The
listing's Wi-Fi 6 and Mali-G31 hold; its Bluetooth 5.0 is 5.4 here (HCI version 13), LE only.

## Serial console

| Item          | Status                                   |
| ------------- | ---------------------------------------- |
| PCB labels    | RX / TX / GND, top to bottom as pictured |
| Voltage       | 3.3 V, as on every Allwinner board       |
| Baud          | 115200, the standard                     |
| Stock console | Not captured                             |

## Addresses

| Interface | Address             | Source                                                |
| --------- | ------------------- | ----------------------------------------------------- |
| Ethernet  | `90:0e:b3:d6:9a:ba` | sticker on the PCB; secure storage `mac`              |
| Wi-Fi     | `88:00:d4:d4:3a:b2` | secure storage `wifi_mac`, set by U-Boot; eFuse empty |
| Bluetooth | `88:00:d4:d4:3a:b3` | the Wi-Fi's plus one, set by U-Boot; eFuse empty      |

## Test report — 2026-11-09, 6.18.62 / 7.3.3

In the bring-up checklist's order, each kernel's mark side by side; numbers read 6.x / 7.x.

| Check                   | 6.x | 7.x | What shows it                                      |
| ----------------------- | :-: | :-: | -------------------------------------------------- |
| SoC                     | ✅  | ✅  | FEL `soc=00001823(H616)`; AC300 EPHY by SID        |
| PCB identity            | ✅  | ✅  | `BA979_627_V1.0`, owner and photos                 |
| backup                  | ✅  | ✅  | `backup/h96max-h313-stock.img.xz`, xz verified     |
| factory DRAM init       | ✅  | ✅  | factory-settings SPL; RAM readback                 |
| SD boot                 | ✅  | ✅  | root media SD; 6.18 the default                    |
| boot time               | ✅  | ✅  | 16.0 s / 12.7 s                                    |
| failed units            | ✅  | ✅  | 0 / 0                                              |
| dmesg accounted         | 🟠  | 🟠  | AIC8800 at warning level; PA/PL supplies           |
| RAM                     | ✅  | ✅  | 1976 MiB; `stress-ng --vm --verify`, 0 failed      |
| ten warm reboots        | ✅  | ❓  | every device back each time                        |
| watchdog reset          | ✅  | ✅  | 30 s set: reset at 30 s, not 16 s                  |
| forced panic            | ✅  | ✅  | reboots; oops in pstore                            |
| lockup panic            | ✅  | 🟠  | 6.18 panics with a record; 7.3 by watchdog         |
| all-CPU lockup          | 🟠  | ❓  | reset at 16 s by watchdog, no record               |
| OPP table               | ✅  | ✅  | factory bin 4: 480–1416 MHz, 1150 mV top           |
| 4-core heat             | 🟠  | 🟠  | 70 °C trip: 1200–1320 MHz, 73 °C peak              |
| Ethernet 10/100         | ✅  | ✅  | both rates link; AC300 EPHY driver                 |
| Ethernet rate           | ✅  | ✅  | 93.9 / 93.3 idle, 93.8 / 89.4 loaded               |
| Wi-Fi bands             | ✅  | ✅  | scan: 9 on 2.4 GHz, 20 on 5 GHz                    |
| Wi-Fi rate              | ✅  | ✅  | Wi-Fi 6 5 GHz: 113 / 93 idle and loaded            |
| Wi-Fi country           | ❌  | ❌  | self-managed at `00`, `iw reg set` ignored         |
| Bluetooth               | ✅  | ✅  | `hci0` LE only, errors 0; scan finds 117           |
| addresses               | ✅  | ✅  | sticker on the PCB; BT Wi-Fi + 1                   |
| eMMC read               | ✅  | ❓  | HS200: 88.9 MB/s, 3815 IOPS, read-only             |
| MMC bus modes           | 🟠  | 🟡  | eMMC HS200 100 MHz; SD, SDIO high-speed            |
| SD card                 | ✅  | ❓  | 20.9 / 22.3 MB/s, 1536 IOPS; no UHS                |
| USB 1.1                 | ✅  | ✅  | 12M receiver enumerates                            |
| USB 2.0 480M            | ❓  | ❓  | 👤 a stick in each USB-A port; `fio`               |
| OTG port host           | ❓  | ❓  | 👤 a stick in the port nearest the SD slot         |
| input names             | ✅  | 🟡  | `cec-remote`, `ir-remote`                          |
| IR keymap               | ✅  | ✅  | `rc-h96max`, 22 keys, NEC                          |
| s2idle 20 s             | ✅  | ❓  | RTC wake, same boot                                |
| s2idle 100 s            | ❌  | ❓  | resets with no record                              |
| deep suspend            | ❌  | ❌  | H616: no SCPI; s2idle only                         |
| RTC                     | ✅  | ✅  | `sun6i-rtc` keeps time                             |
| HDMI planes and compose | ✅  | ✅  | display.py 35/35 with writeback                    |
| planes at once          | ✅  | ✅  | 3 planes in one commit                             |
| HDMI rating             | ✅  | ✅  | 4K60 and 1080p120 sustained                        |
| HDR signalling          | ✅  | ✅  | PQ, HLG, HDR10+ InfoFrames                         |
| CEC                     | ❓  | ✅  | 6.18 reads no address                              |
| sound cards             | ✅  | ✅  | Codec and HDMI, 3 s in 3.0–3.2 s                   |
| AV picture              | 🟡  | ✅  | PAL bars; 6.18 registers match                     |
| AV sound                | ✅  | ✅  | line out, heard; board swaps L/R                   |
| GPU correctness         | ✅  | ✅  | dEQP 1/20: 4980 pass, 0 unexpected                 |
| GPU speed               | ✅  | ❓  | glmark2 on screen, 2256×1504: 122                  |
| video decode            | ✅  | ✅  | Tanix's Cedrus profile, nothing worse              |
| AFBC decode             | ✅  | ✅  | HEVC, VP9 8- and 10-bit                            |
| deinterlace             | ✅  | ✅  | a frame per field, 27 dB to bwdif                  |
| encode                  | ✅  | ✅  | H.264 and MJPEG to 4096×4096                       |
| remote buttons          | ❓  | ❓  | 👤 press every button                              |
| BLE remote              | ❓  | ❓  | 👤 pair, keep across reboot                        |
| LED colours             | ❓  | ❓  | 👤 on, off, asleep                                 |
| SD hotplug              | ❓  | ❓  | 👤 in and out                                      |
| FEL button              | ✅  | ✅  | the boot ROM's; how FEL was entered for the backup |
| eMMC install            | ❓  | ❓  | awaits the owner's go-ahead                        |

## Measured

| Item                       | Value                     | Source                           |
| -------------------------- | ------------------------- | -------------------------------- |
| eMMC size                  | 15758000128 bytes         | USB disk, 2026-11-08             |
| DRAM configuration         | LPDDR3, 600 MHz, 2048 MiB | Factory boot0                    |
| RAM bandwidth, 1 / 4 cores | 858 / 831 MB/s read       | `stress-ng --stream`, 2026-11-09 |
| RAM quick check            | 1400 MiB, 60 s, no errors | `ram-first-60s.log`              |
| End-of-check sensor max    | 55.5 °C                   | `ram-first-60s.log`              |
| Ethernet, host to box      | 94.0 Mb/s, 10 s           | iperf3, 2026-11-08               |
| Ethernet, box to host      | 91.5 Mb/s, 10 s           | iperf3, 2026-11-08               |

## Backup

The full eMMC, per-unit data included; six independent readback windows match it.

## AV jack

- **The kit's AV cable**: through a CTIA-to-OMTP adapter, two swaps: red and yellow first, red into
  the video input; then white and yellow, for left and right audio.
- **Channels**: the codec's routing matches stock's; the swap is this board's jack wiring.
- **Composite**: off by default; `echo on > /sys/class/drm/card0-Composite-1/status` turns it on,
  720x576i50 with the connector's `TV mode` PAL, or 720x480i60 NTSC.
- **Sound**: line out and DAC are muted at boot:
  `amixer -c 0 sset "Line Out" 26 on; amixer -c 0 sset DAC 63 on`.

## Known gaps

- SoC and memory markings hidden by heatsink.

## Recovery

FEL: the button in the AV jack, pressed with a toothpick, held while the OTG cable goes in with DC
unplugged. The boot ROM reads it, so it recovers from any eMMC state. No U-Boot recovery button.
