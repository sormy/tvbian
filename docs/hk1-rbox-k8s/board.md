# HK1 RBOX K8S

## Identity

| Item           | Detail                               | Source              |
| -------------- | ------------------------------------ | ------------------- |
| PCB            | FX-RX3528-D4, 20230822               | silkscreen          |
| SoC            | Rockchip RK3528                      | USB `2207:350c`     |
| CPU            | Quad-core Cortex-A53, AArch64        | `lscpu`             |
| GPU            | Mali-450                             | glmark2's renderer  |
| Factory OS     | Android 13, API 33                   | stock `build.prop`  |
| RAM            | 4 GB                                 | owner               |
| DRAM chips     | 8 discrete, maker unconfirmed        | owner               |
| eMMC           | MMC32G, 31,264,342,016 bytes         | `rkdeveloptool rfi` |
| Radio          | HK5246F, AIC8800D80                  | SDIO `c8a1:0082`    |
| Front display  | FD650B-S, clock digits, no icons     | owner               |
| LEDs           | none, the panel only                 | owner               |
| Power          | 5 V / 2 A, DC jack                   | owner               |
| Ports          | RJ45, HDMI, AV, USB 2, USB 3, SD, IR | owner               |
| microSD tested | 64 GB card, 64,088,965,120 bytes     | `lsblk`             |

![HK1 RBOX K8S and bundled IR remote](image1.webp)

[Port layout](image2.webp) · [Package contents](image3.webp) · [PCB top](pcb-top.webp) ·
[PCB bottom](pcb-bottom.webp)

## Advertised variants and limits

Source: product specifications supplied by the owner.

| Item           | Advertised                                       |
| -------------- | ------------------------------------------------ |
| Memory         | 2 or 4 GB RAM                                    |
| eMMC           | 16, 32, 64 or 128 GB                             |
| microSD        | 4–256 GB                                         |
| Wi-Fi          | 802.11 a/b/g/n/ac/ax, 2.4 and 5 GHz              |
| Bluetooth      | 5.0                                              |
| Wired Ethernet | 100 Mb/s                                         |
| HDMI           | 2.0b, up to 4K60 at 10 bits                      |
| Composite AV   | NTSC 480i and PAL 576i                           |
| HDR formats    | HDR10, HLG, HDR Vivid                            |
| Box contents   | HDMI cable, IR remote, manual, 5 V / 2 A adapter |

## Serial console

Pads near the IR port, marked `GND RX TX`, with an unlabelled square pad reported as NC: `ttyFIQ0`
at 1500000 baud, 3.3 V.

## Test report

| Check               | Result | Evidence                                                   |
| ------------------- | ------ | ---------------------------------------------------------- |
| Factory idbloader   | ✅     | Two factory reads and one Maskrom read match               |
| Stock eMMC read     | ✅     | Full size, matching idbloader and GPT copies               |
| Boot from SD        | ✅     | Root on SD; eMMC has the factory partition map             |
| Install to eMMC     | ✅     | `tvb-install`; idbloader, vendor and secure storage kept   |
| Boot from eMMC      | ✅     | Root on eMMC, SD out; 6.1, Wi-Fi up                        |
| Vendor warm reboots | ✅     | 20 on 6.1 and 20 on 6.12, none hung; the DMC off around it |
| Panic recovery      | ✅     | SysRq crash rebooted and saved a ramoops record            |
| Unpinged watchdog   | ✅     | Armed at 11 s, rebooted and rearmed under systemd          |
| All-CPU soft lockup | ✅     | Panic at 26 s, reboot and ramoops record                   |

## Measured

| Check                | Result | Evidence                                                  |
| -------------------- | ------ | --------------------------------------------------------- |
| RAM                  | ✅     | 3921 MiB available to Linux, 3 GiB verified for 60 s      |
| CPU stress           | ✅     | 62.7 °C over 300 s, no cooling state engaged              |
| Combined load        | ✅     | 68.9 °C in 120 s, CPU, RAM and GPU; DDR at 786 MHz        |
| RAM STREAM read      | ✅     | 1253 MB/s with one worker, 2794 with four; DDR at 786 MHz |
| eMMC sequential read | ✅     | 242 MB/s, 512 MiB direct I/O                              |

Wi-Fi TCP throughput on vendor 6.1, measured 2026-11-21 with `iperf3 --bind-dev wlan0`; 5 GHz after
a driver reload: 185 Mb/s up, 198 down.

| Band    | Upload   | Download  |
| ------- | -------- | --------- |
| 2.4 GHz | 124 Mb/s | 113 Mb/s  |
| 5 GHz   | 163 Mb/s | 84.7 Mb/s |

## Network

| Check                            | Result | Evidence                                            |
| -------------------------------- | ------ | --------------------------------------------------- |
| USB Ethernet                     | ✅     | 15 warm boots back at 1000; 309 up, 321 down Mb/s   |
| Wi-Fi scans                      | ✅     | `nmcli` lists 2.4 and 5 GHz channels                |
| Wi-Fi association and throughput | ✅     | Both bands. 5 GHz link reported HE-MCS 11           |
| Built-in Ethernet link           | ✅     | 100 Mb/s full duplex. TCP 93.7 up, 94.1 down        |
| Bluetooth discovery              | ✅     | UART2 H4, BR/EDR and LE. Controller reports HCI 5.4 |

## Display and audio on vendor 6.1

| Check               | Result | Evidence                                                |
| ------------------- | ------ | ------------------------------------------------------- |
| HDMI composition    | ✅     | Synthetic sink and all-plane writeback                  |
| Headless GPU        | ✅     | Mali450 rendered the glmark2 build scene                |
| Analog codec timing | ✅     | 3.02 s at 44.1 and 48 kHz                               |
| Composite writeback | ❌     | PAL and NTSC modes set; the colour bars lost            |
| HDMI picture        | ✅     | A screen attached at boot: EDID, 2256×1504 at 60 Hz set |

## Video on vendor 6.1

| Codec            | Decode                                     | Encode       |
| ---------------- | ------------------------------------------ | ------------ |
| H.264            | ✅ 8192×8192, exact                        | ✅ 8192×8192 |
| Interlaced H.264 | ✅ 1080i, 60 progressive outputs           | ❓           |
| HEVC             | ✅ 8192×8192, exact                        | ✅ 8192×8192 |
| HEVC Main10      | ✅ 8192×8192, frame count                  | ➖           |
| VC-1             | ❓ no FFmpeg path                          | ➖           |
| VP9 profile 0    | ✅ 8192×4320, exact                        | ➖           |
| VP8              | ✅ 1920×1080, exact                        | ➖           |
| H.264 10-bit     | ✅ 8192×8192                               | ➖           |
| VP9 profile 2    | ✅ 8192×4320                               | ➖           |
| H.263            | ✅ 1408×1152                               | ➖           |
| MPEG-1           | ✅ 1080p60 clip, 30 frames, 75.71 dB luma  | ➖           |
| MPEG-2           | ✅ 1920×1080, Y-PSNR 75.76 dB              | ➖           |
| MPEG-4 Part 2    | ✅ 1920×1080, Y-PSNR 75.98 dB              | ➖           |
| Decoder scaling  | ✅ 4K to 1080p, H.264 67.00, HEVC 65.35 dB | ➖           |

Encode fps at 1920×1080: H.264 High 52.9, HEVC Main 60.0. The encoder is 8-bit: Rockchip's MPP and
next2's driver take 8-bit sources only, and a 10-bit one comes out 8-bit Main.

Interlaced H.264 uses the patched MPP bundled with `ffmpeg9`.

Decode speed, the engine alone (`tools/validate/video.py` decode), the DDR at 786 MHz:

| Codec at 3840×2160 | Result | fps   |
| ------------------ | ------ | ----- |
| H.264              | ✅     | 61.6  |
| H.264 10-bit       | ✅     | 58.0  |
| HEVC               | ✅     | 116.9 |
| HEVC Main10        | ✅     | 112.4 |
| H.264 4:2:2        | ✅     | 46.9  |
| H.264 4:0:0        | ✅     | 75.5  |

## Vendor 6.12 test

| Check                   | Result | Evidence                                   |
| ----------------------- | ------ | ------------------------------------------ |
| SD boot                 | ✅     | 6.12.69 reached SSH                        |
| Wi-Fi                   | ✅     | 205 Mb/s up and 174 Mb/s down              |
| Bluetooth               | ✅     | H4 driver up; LE discovery                 |
| Front-panel clock       | ✅     | TM16xx bound and the display timer started |
| H.264 decode            | ✅     | Exact 1080p output                         |
| Interlaced H.264 decode | ✅     | All 60 source luma fields matched          |
| HDMI flip pacing        | ✅     | 3601 commits in 60 s                       |
| Composite writeback     | ❌     | PAL and NTSC lost colour bars              |
| SDR to HDR mapping      | ✅     | PQ and HLG within one code                 |
| Analog codec timing     | ✅     | 2.027 s at 44.1 kHz and 2.019 s at 48 kHz  |
| HDR10 film on a screen  | ✅     | 10-bit YCbCr 4:2:2, BT.2020, PQ, smooth    |

HDMI writeback rejects capture after a composite test. HDMI display commits still succeed.

## Mainline 7.3 test

| Check                        | Result | Evidence                                     |
| ---------------------------- | ------ | -------------------------------------------- |
| SD boot                      | ✅     | 7.3.5 reached SSH, vendor menu restored      |
| Wi-Fi association and upload | ✅     | DHCP and 120 Mb/s at 2.4 GHz                 |
| Wi-Fi download at 2.4 GHz    | ❌     | Four runs: nothing twice, 13.1 and 74.7 Mb/s |
| Wi-Fi download at 5 GHz      | ✅     | 209 Mb/s over six seconds                    |
| eMMC at HS400ES, 148.5 MHz   | ✅     | 102 MiB/s read; `boot0` writes verified      |
| Bluetooth discovery          | ✅     | UART2 H4, 8 found, no HCI errors             |
| HDMI scanout, synthetic 4K60 | ✅     | 601 flips, none late or refused              |
| Composite writeback          | ✅     | PAL and NTSC keep six colour bars            |

## Video on mainline 7.3

| Codec         | Decode                        | Encode       |
| ------------- | ----------------------------- | ------------ |
| H.264         | ✅ 3840×2160, exact           | ✅ 3840×2160 |
| HEVC          | ✅ 3840×2160, exact           | ✅ 3840×2160 |
| HEVC Main10   | ✅ 3840×2160, frame count     | ❓           |
| VP9 profile 0 | ✅ 1920×1080, exact           | ❓           |
| MJPEG         | ✅ 1920×1080, Y-PSNR 55.12 dB | ✅ 1920×1080 |

## Power

- Suspend: `deep` by default, `s2idle` offered.
- RTC: ➖ on vendor 6.1, none registered; ❓ on next2.

## Hands-on checks

| Check                | 6.1 | next2 | Evidence                                          |
| -------------------- | --- | ----- | ------------------------------------------------- |
| The IR remote        | ✅  | ✅    | All 12 keys canonical in `evtest`                 |
| The BLE remote       | ➖  | ➖    | None comes with the box                           |
| Bluetooth keyboard   | 🟡  | ❓    | LE scan finds 16, BR/EDR discovery works          |
| Wi-Fi, owner's       | ✅  | ✅    | Joined on both                                    |
| Sleep and wake       | ✅  | ❌    | Deep, woken by the remote, the DMC off            |
| Power off and on     | ✅  | ❌    | Off 5 minutes, then on from the remote            |
| Reboots by hand      | ✅  | ✅    | 6.1 and 6.12, with the DMC off                    |
| HDMI on a screen     | ✅  | ✅    | EDID, 23 modes; 6.1 sets 2256×1504 at 60 Hz       |
| HDMI sound           | ✅  | ❓    | Heard on the screen's speakers                    |
| The GPU on a screen  | ✅  | ❓    | glmark2 at 60 fps, no artifacts seen              |
| A player on a screen | ✅  | ❓    | 4K24 HEVC with Dolby, H.264, in Fuseamp           |
| HDR on an HDR TV     | ✅  | ❓    | 6.1, 6.12: 10-bit YCbCr 4:2:2, BT.2020, PQ        |
| The AV jack          | ✅  | ❓    | PAL and NTSC bars seen; analog sound heard        |
| S/PDIF               | ➖  | ➖    | No S/PDIF port                                    |
| A monitor's DDC/CI   | ✅  | ❓    | Brightness, contrast, volume read; brightness set |
| Ethernet             | ✅  | ❓    | 10 and 100 Mb/s full duplex at line rate          |
| USB 3                | ✅  | ❓    | 5000M on `uas`, 360 read, 317 write MB/s          |
| USB 2                | ✅  | ❓    | The Lexar at 480M, 34.9 read, 32.0 write MB/s     |
| The OTG port         | ✅  | ❓    | The USB 2 port: a 12M keyboard; the Loader        |
| The SD slot          | ✅  | ❓    | High speed, stock's mode, 23.9 MB/s; hotplug      |
| The recovery button  | ✅  | ✅    | Factory Loader on OTG                             |
| The recovery path    | ✅  | ✅    | Loader and Maskrom on OTG, the eMMC read whole    |
| Buttons and LEDs     | ➖  | ➖    | No LEDs; the panel only                           |
| The front panel      | ✅  | ✅    | Clock, time zone and brightness 1 to 8            |
| The serial pads      | ✅  | ✅    | `GND RX TX` as labelled, 1500000 baud             |

## Known gaps

| Advertised feature                  | TVBian test gap                     |
| ----------------------------------- | ----------------------------------- |
| Other RAM and eMMC sizes            | ❓ No other hardware variant tested |
| microSD sizes outside the test card | ❓                                  |
| HDMI 4K60 at 10 bits                | ❌ Vendor sends RGB 8-bit, no 4:2:0 |
| HDR Vivid                           | ❓                                  |
| MVC, AVS, AVS+ and AVS2             | ❓ Hardware decode on this board    |

## Recovery

✅ Hold the button inside the AV jack while connecting USB 2.0 OTG with DC power disconnected. Stock
enters `Loader`. On the host, `build/bin/rkdeveloptool rd 3` switches it to `Maskrom`. The board's
loader uploads successfully and reads back the same factory idbloader as stock.
