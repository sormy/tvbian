# RK3528, RK3528A and RK3518 on mainline Linux, block by block

This page goes through every block in the RK3528A datasheet (Rockchip, rev 1.2): what mainline Linux
does with it on the `rk35xx-next2` kernel (next2 below), and the check that shows it. The RK3528 and
RK3518 datasheets list the same blocks, apart from the differences in the next section, so each row
covers all three chips.

➖ marks a block that no board here wires up, going by its factory tree. `probe.py` checks on any
box that an option is present and uses it once; compare its output with this table. Each board's own
measurements are in its `board.md`.

## RK3528, RK3528A, RK3518

The three datasheets (RK3528 rev 1.4, RK3528A rev 1.2, RK3518 rev 1.0) describe the same CPU, GPU,
video decoder and encoder, display, HDMI and audio, word for word. They differ only here:

| Block                     | RK3528          | RK3528A              | RK3518              |
| ------------------------- | --------------- | -------------------- | ------------------- |
| DRAM                      | DDR4, LPDDR4(X) | adds DDR3(L), LPDDR3 | as RK3528A          |
| 1000M RGMII MAC           | ✓               | ✓                    | none, nor its pins  |
| PCIe 2.1, USB 3 combo PHY | ✓               | ✓                    | USB 3 only, no PCIe |
| SM2                       | ✓               | ✓                    | none; SM3, SM4 kept |
| Dolby part                | RK3528-D        | none                 | none                |

The RK3518's text drops the USB 3 host and its PHY with PCIe, but its block diagram keeps USB 3.0
DRD, and an RK3518 box here runs its OTG port at 5000 Mbps. None lists VP9, which the decoder does
on each chip here. The GPU is a Mali-450 in all three; the RK3528's rev 1.3 dropped its "MP2", the
RK3528A's keeps it. Every board here leaves PCIe and the RGMII MAC off.

## System

| Option                                                   | Status | Check                                           |
| -------------------------------------------------------- | ------ | ----------------------------------------------- |
| 4× Cortex-A53, DVFS                                      | 🟠     | `box.py` cpu; PVTM picks one bin lower than 6.1 |
| Mali-450, DVFS                                           | ✅     | `gpu.py` dEQP, `box.py` gpu: 300, 700, 800 MHz  |
| eMMC HS400                                               | ✅     | HS400 with enhanced strobe: 102 MiB/s read      |
| eMMC command queue                                       | ❓     |                                                 |
| SD 3.0                                                   | ✅     | `box.py` storage: SDR104                        |
| FSPI                                                     | ➖     | no board boots from SPI flash                   |
| DDR, rate by status                                      | ✅     | `box.py` `ddr.governor`: fixed rate, as stock   |
| 5 PLLs, CRU, PMU domains                                 | 🟡     | `probe.py` system: PLL rates, domains           |
| Timers, GIC                                              | 🟡     | `probe.py` system: timers, interrupts           |
| DMAC, memory to memory                                   | ✅     | `probe.py` dmatest: 20 copies, none failed      |
| PWM                                                      | ✅     | `box.py` input, leds                            |
| IR on PWM3/7                                             | 🟡     | `probe.py` system: NEC by GPIO on PWM3's pin    |
| Watchdog                                                 | ✅     | `box.py` system; `reboots.sh`                   |
| Crypto: AES ECB/CBC/CTR/XTS, SM4, DES/TDES, hashes, HMAC | ✅     | `box.py` crypto: all 19 self-tests pass         |
| Crypto: the default the fastest, engine or CPU           | ✅     | `box.py` crypto bench: 20 of 20 at 4 KiB        |
| Crypto: a timed-out or wedged job recovers               | ✅     | `box.py` crypto recovery: the next hash runs    |
| Crypto: HMAC-SM3                                         | ❌     | wrong digest in its self-test: not offered      |
| Crypto: AES CFB/OFB                                      | ❓     | no kernel test vectors: not offered             |
| Crypto: GCM, AES and SM4                                 | ✅     | self-tests pass; SM4 51.8 MB/s at 4 KiB         |
| Crypto: XTS-SM4, CTS-CBC-AES                             | ✅     | self-tests pass; SM4 176.7 MB/s at 4 KiB        |
| Crypto: RSA on the PKA by the CRT, 512 to 4096 bits      | 🟠     | `box.py` crypto.rsa: 29.9 signs/s, CPU 31.2     |
| Crypto: AES CCM/CMAC                                     | ❓     | not on the engine; the CPU does them            |
| RNG                                                      | ✅     | `box.py` `hwrng`                                |
| Mailbox, MCU                                             | ➖     | no user                                         |
| OTP                                                      | ✅     | `rockchip-otp0`: leakage and PVTM values        |
| TSADC                                                    | ✅     | `box.py` thermal                                |
| SARADC, 4 channels                                       | ✅     | `adc-keys`; `box.py` input                      |

## Video

| Option                                      | Status | Check                                          |
| ------------------------------------------- | ------ | ---------------------------------------------- |
| H.264 to 4K60, 10-bit, 4:2:2, 4:0:0         | ✅     | `video.py` decode                              |
| H.264 4:2:2 in MBAFF                        | ❌     | wrong chroma: refused                          |
| HEVC Main/Main10 to 4K60                    | ✅     | `video.py` decode                              |
| H.264 MVC                                   | ➖     | on hold                                        |
| MPEG-1/2/4, H.263 to 1080p60                | ✅     | `video.py` decode: up to 1080p's area          |
| VC-1 SP/MP/AP                               | ➖     | on hold                                        |
| AVS, AVS+, AVS2                             | ➖     | no stateless API in Linux                      |
| Decoder error concealment                   | ✅     | `video.py` conceal: each codec at 1080p        |
| Decoder ½ downscale, 8-bit 4:2:0            | ✅     | `video.py` scale: H.264, HEVC, VP9 at 65–67 dB |
| Decoder ¼ and ⅛ downscale                   | ❌     | wrong picture at every ratio: refused          |
| Encode H.264 HP@4.2, HEVC Main, 1080p60     | ✅     | `video.py` encode: 60.5 and 72 fps at 1080p    |
| Encode input: YUV 4:2:0/4:2:2, packed, RGB  | ✅     | `video.py` input: each layout, 35–47 dB        |
| Encode input 4:4:4: NV24, NV42, YUV444M     | ✅     | `video.py` input: 35.3 dB                      |
| Encode input 4:0:0                          | ❌     | hung the SoC: refused                          |
| Encode input ARGB1555                       | ❌     | hung the SoC: refused                          |
| Encode input ARGB4444                       | ❓     | untried, as ARGB1555 hung: refused             |
| JPEG encode                                 | ✅     | `video.py` encode                              |
| JPEG decode 4:0:0–4:4:4 to 8176×8176        | ✅     | `video.py` decode: 4:1:1 as NV12               |
| JPEG decode from 48×48, 76 Mpixel/s         | ✅     | `video.py` decode: 48×48; 1080p at 313 fps     |
| JPEG decode ROI                             | ❓     | its register is unknown                        |
| VDPP scale (ZME)                            | ✅     | `video.py` convert: 43–47 dB, each format      |
| VDPP NV21 in and out, 4:4:4 out             | ✅     | `video.py` convert: exact; 4:4:4 at 43 dB      |
| VDPP 4:2:2 in, scaling                      | ❌     | read as 4:2:0                                  |
| VDPP 4:2:2 out, scaling                     | ❌     | the job fails                                  |
| IEP2 4:2:2 in and out                       | ✅     | `video.py` deinterlace: 42.3 and 38.7 dB       |
| VDPP BT.601/709, limited/full conversion    | ❓     | no register known for it                       |
| VDPP DMSR                                   | ✅     | `video.py` convert: 56 dB against plain        |
| De-interlace (IEP2) to 1920 wide, I5O2      | ✅     | `video.py` deinterlace: one frame per field    |
| De-interlace a frame a frame, I5O1 and I1O1 | ✅     | `video.py` fields: one frame per input         |
| RGA formats, scale, rotate, mirror          | ✅     | `video.py` convert: exact; XRGB 57.6 dB        |
| RGA XRGB8888 either way, BT.601/709 ranges  | ✅     | `video.py` convert                             |
| RGA 10-bit YUV 4:2:0/4:2:2 source           | ✅     | `video.py` convert                             |
| RGA 4096 destination; recovery on a hang    | ✅     | `video.py` convert; larger refused             |
| RGA vertical upscale, source to 2048 wide   | 🟠     | `video.py` convert; wider refused              |
| RGA blending, fills, BPP1–8 expansion       | ➖     | no V4L2 interface for them                     |

## Display

| Option                                         | Status | Check                                      |
| ---------------------------------------------- | ------ | ------------------------------------------ |
| VP0 3840×2160@60                               | ✅     | `display.py` rating: sustained             |
| VP0 4096×2304@60                               | ➖     | beyond HDMI 2.0 in RGB                     |
| VP0 1080p120                                   | ✅     | `display.py` rating: none refused          |
| VP1 PAL/NTSC, composite                        | ✅     | `display.py` composite: bars kept          |
| Cluster: AFBC, scale, linear mirror Y          | ✅     | `display.py` rotation, by writeback        |
| Cluster rotate 90/270 (AFBC)                   | ✅     | `display.py` rotation, by writeback        |
| Esmart: 4 regions each                         | 🟡     | `display.py` regions; not seen on a screen |
| VP0 gamma LUT, 1024 entries                    | 🟡     | `display.py` gamma; not seen on a screen   |
| Overlay SDR to PQ, colorop pipeline            | ✅     | `display.py` colorop: within 1 code        |
| Overlay SDR to HLG, colorop pipeline           | ✅     | `display.py` colorop: within 1 code        |
| Overlay HDR layer: to SDR, or passed under SDR | ❌     | needs the stock HDR library's tables       |
| VP0 ACM (hue, saturation)                      | ➖     | no Linux interface for it                  |
| Writeback XRGB/RGB888/RGB565/YUV420            | ✅     | `display.py` writeback: each format        |
| HDMI 2.0b RGB                                  | ✅     | `display.py` hdmi                          |
| HDMI YCbCr 4:2:0 at 4K60, 10-bit               | ✅     | `display.py` deep colour                   |
| HDMI YCbCr 4:4:4, 4:2:2                        | ✅     | `display.py` color format                  |
| HDMI deep colour (10-bit)                      | ✅     | `display.py` deep colour: 30-bit           |
| HDMI BT.2020 colorimetry for HDR               | ✅     | `display.py` hdmi: PQ and HLG              |
| HDMI 3D frame packing                          | ✅     | `display.py` stereo: 5 modes               |
| HDMI HDCP 1.4/2.2                              | ➖     | on hold: no keys on any box                |
| CEC                                            | ✅     | `/dev/cec0`; wake by TV untested           |
| CVBS cable detection                           | ❓     | `probe.py` display: connector status       |

### Line buffers

The RK3528 splits one line buffer between its Esmart display planes. The split decides which Esmart
planes exist and how wide each can be; Cluster0, the 4K video plane, is outside it. Every board's
tree sets `02`, the split tested here; the kernel command line overrides it.

| Value | Esmart buffers      | HDMI's Esmart planes        | Composite's planes |
| ----- | ------------------- | --------------------------- | ------------------ |
| `02`  | 0: 4K, 1: 2K, 2: 2K | desktop 4K, cursor          | Esmart2            |
| `01`  | 0: 4K, 2: 4K        | desktop 4K, cursor 4K       | Esmart2            |
| `03`  | 0–3: 2K each        | desktop 2K, overlay, cursor | Esmart3, Esmart2   |
| `00`  | 0: 8K               | desktop 8K                  | none               |

In `02`, Esmart1 is HDMI's cursor and Esmart2 is composite's plane, or HDMI's overlay on a board
without composite; Esmart3 gets no buffer, so it is not a plane. In `03`, Esmart2 is HDMI's cursor
and Esmart3 is composite's plane. A desktop wider than 2048 needs `00`, `01` or `02`.

To change it, on the box, then reboot:

```sh
P='rockchipdrm.esmart_lb_mode=1'
F=/etc/u-boot-menu/conf.d/zz-esmart.conf
echo "U_BOOT_PARAMETERS=\"\$U_BOOT_PARAMETERS $P\"" | sudo tee $F
sudo u-boot-update
```

To go back to the tree's value, remove that file and run `sudo u-boot-update`.

## Audio

| Option                             | Status | Check                                    |
| ---------------------------------- | ------ | ---------------------------------------- |
| SAI2 to the codec, 8–96 kHz, 12/24 | ✅     | `box.py` audio: each rate in real time   |
| SAI 16, 24 and 32-bit samples      | ✅     | `box.py` audio: each format in real time |
| SAI3 to HDMI, 8 channels           | ✅     | `display.py` hdmi audio: 8 ch at 192 kHz |
| HDMI jack                          | ✅     | `box.py` audio: HDMI jack                |
| SAI0 PCM to Bluetooth              | ➖     | factory trees disable it                 |
| SAI1, PDM                          | ➖     | `probe.py` audio                         |
| S/PDIF to GPIO                     | ✅     | `box.py` audio                           |
| S/PDIF to HDMI                     | ➖     | factory trees feed HDMI from SAI3        |

## Connectivity

| Option                     | Status | Check                             |
| -------------------------- | ------ | --------------------------------- |
| 100M MAC and PHY           | ✅     | `box.py` network, throughput      |
| Checksum offload, TSO, WoL | 🟡     | `probe.py` network                |
| 1000M RGMII MAC            | ➖     | `probe.py` network                |
| USB 2.0 host, EHCI/OHCI    | ✅     | `box.py` usb                      |
| USB 3.0 DRD, xHCI 5 Gb/s   | ✅     | `box.py` usb: 5000 Mbps           |
| PCIe 2.1                   | ➖     | `probe.py` system                 |
| SDIO 3.0                   | ✅     | `box.py` network: the Wi-Fi radio |
| UARTs, flow control        | ✅     | Bluetooth, with RTS               |
| I2C                        | 🟡     | `probe.py` system                 |
| SPI, TS input, smart card  | ➖     | `probe.py` system                 |
