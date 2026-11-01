# Tanix TX1 V2.0 — board details

## Identity — check yours matches before flashing

| Field   | Value                                                                  |
| ------- | ---------------------------------------------------------------------- |
| PCB     | `QHZIW_H313_TX1_EMCP_V2.0 2024-03-21`                                  |
| SoC     | Allwinner H313, H616 family, `soc=00001823(H616)` over FEL             |
| RAM     | 1.5 GiB LPDDR3 in the eMCP, two ranks, sold as 2 GB                    |
| eMMC    | Samsung `Q316BB`, 30777344 sectors (14.7 GiB)                          |
| PMIC    | AXP1530, mainline's AXP313                                             |
| Wi-Fi   | AltoBeam ATBM6031-X on SDIO, `007a:6011`, 2.4 GHz                      |
| Ports   | HDMI, one USB-A (also FEL), DC 5 V, AV                                 |
| Buttons | FEL behind the AV jack; U-Boot recovery, PH9                           |
| LEDs    | PH6 power (blue), PH7 standby (red)                                    |
| In box  | the IR-only remote, an HDMI cable, a USB-to-DC power cable, no adapter |

No Ethernet, no SD slot. A Tanix TX1 with PCB `CS_H313_TX1_EMCP_V1.1` is a different board: its DRAM
settings differ in four of eight words, and its Wi-Fi is another chip.

## Addresses

| Interface | Address             | Source                                                   |
| --------- | ------------------- | -------------------------------------------------------- |
| Wi-Fi     | `54:14:e9:d9:73:d1` | the chip's eFuse: `efuse data is […0x73:0xd1]`, then set |
| BLE       | `54:14:E9:D9:73:D2` | the firmware's, public: the eFuse's plus one, every load |

## Test report — 2026-10-26, 6.18.59 / 7.2.13

In the bring-up checklist's order, each kernel's mark side by side; numbers read 6.x / 7.x, from one
regression pass on each.

| Check            | 6.x | 7.x | What shows it                                                    |
| ---------------- | :-: | :-: | ---------------------------------------------------------------- |
| photos           | 🟡  | 🟡  | `image1.jpg`, the unit and remote; no retail box or label        |
| SoC              | ✅  | ✅  | H313; FEL reports `soc=00001823(H616)`                           |
| kind             | ✅  | ✅  | board, chip (ATBM6031) and family (sunxi)                        |
| backup           | ✅  | ✅  | `backup/tanix-tx1-v2-stock.img.xz`                               |
| backup size      | ✅  | ✅  | 30777344 sectors, the eMMC's                                     |
| backup read      | ✅  | ✅  | FEL read hash matches the Android-side read                      |
| per-unit window  | ✅  | ✅  | `preserve-sectors` 12288–12799                                   |
| DRAM init carved | ✅  | ✅  | `factory_boot0.bin`                                              |
| stock boot log   | ✅  | ✅  | `stock/tanix-tx1-v2/boot.log`                                    |
| ID searched      | ✅  | ✅  | the V1.1 PCB is another board                                    |
| ID confirmed     | ✅  | ✅  | confirmed by the human                                           |
| PCB photos       | ✅  | ✅  | `board1.jpg`, `board2.jpg`                                       |
| serial pads      | ✅  | ✅  | outlined in red on `board2.jpg`                                  |
| components       | 🟡  | 🟡  | SoC, eMCP and Wi-Fi markings hidden under the heat sink          |
| doc sections     | ✅  | ✅  | every section, Addresses included                                |
| PCB name, date   | ✅  | ✅  | `QHZIW_H313_TX1_EMCP_V2.0 2024-03-21`                            |
| stock files      | ✅  | ✅  | `stock/tanix-tx1-v2/`                                            |
| identity table   | ✅  | ✅  | its README's identity table                                      |
| factory DTBs     | ✅  | ✅  | `factory_board.dtb`, `board-runtime.dtb`                         |
| nothing kept out | ✅  | ✅  | nothing kept out is committed                                    |
| source bases     | ✅  | ✅  | `kernel-h616-vendor-4.9`                                         |
| family kernel    | ✅  | ➖  | 6.18 boots on the tree                                           |
| -next kernel     | ➖  | ✅  | 7.2 boots on the tree                                            |
| NOT FITTED hunks | ✅  | ✅  | one `NOT FITTED` hunk                                            |
| hunks say why    | ✅  | ✅  | audited hunk by hunk; every change says why                      |
| nodes intact     | ✅  | ✅  | eMMC first after every tree change                               |
| dtb.md           | ✅  | ✅  | `dtb.md`                                                         |
| suspend setup    | ✅  | ✅  | s2idle, the one candidate                                        |
| README lists it  | ✅  | ✅  | `README_ALLWINNER.md`                                            |
| support matrix   | ✅  | ✅  | its support matrix                                               |
| firmware package | ✅  | ✅  | both images in `tvb-firmware-atbm6031`                           |
| loaders on eMMC  | ➖  | ➖  | Rockchip's line                                                  |
| board.dtb        | ✅  | ✅  | `board.dtb` identical                                            |
| network boot     | ✅  | ✅  | Wi-Fi, no serial                                                 |
| U-Boot on serial | ✅  | ✅  | U-Boot on serial                                                 |
| kernel on serial | ✅  | ✅  | the kernel on serial                                             |
| serial login     | ✅  | ✅  | a login on serial                                                |
| boot on HDMI     | ✅  | 🟡  | HDMI console from early boot, by eye on 6.18                     |
| dmesg accounted  | ✅  | ✅  | 14 warnings on both, each in Quirks                              |
| boot blame       | ✅  | ✅  | 12.1 / 11.9 s: kernel 5.6, root device 2.4, NM 1.8               |
| second boot time | ✅  | ✅  | the second boot, 12.2 s, recorded here                           |
| board identity   | ✅  | ✅  | `tanix-tx1-v2`, its name and PCB                                 |
| modules loaded   | ✅  | ✅  | `atbm6031` loaded                                                |
| warm reboots     | ✅  | ✅  | ten reboots, 35–38 s each, every device back                     |
| power cycles     | ✅  | ❓  | three cold boots, 2026-10-26: every device back                  |
| RAM              | ✅  | ✅  | 1473 / 1472 MiB of 1.5 GiB                                       |
| RAM under stress | ✅  | ✅  | `stress-ng --vm 90% --verify`, 5 min                             |
| watchdog busy    | ✅  | ✅  | `wdctl`: busy                                                    |
| watchdog timeout | ✅  | ✅  | 80 s, the largest the core grants                                |
| no userspace MAC | ✅  | ✅  | no such service                                                  |
| image contents   | ✅  | ✅  | `tvb-base`, the board's packages                                 |
| watchdog resets  | ✅  | ✅  | armed at 80 s, left unpinged: reset ~89 / ~80 s in               |
| CPU frequencies  | ✅  | ✅  | 480–1344 MHz, stock's top step                                   |
| thermal          | ✅  | ✅  | 73 / 72 °C, held at 1200 MHz under four cores; stock's trips     |
| decode           | ✅  | ✅  | six codecs bit exact; H.264 1080p 122–129 fps on both            |
| encode           | ✅  | ✅  | H.264 encode decodes back at 46 dB                               |
| 4K HEVC file     | 🟠  | 🟠  | 4K Main10 19.4 fps full, 25.2 at ½ (0097); 8-bit 36.7; CPU idle  |
| 4K60 on screen   | 🟠  | 🟠  | 4K60 HEVC 42 / 46 fps, short of 60                               |
| zero copy        | ✅  | ✅  | `import_dmabuf`, no copy                                         |
| video scaling    | 🟠  | 🟠  | linear scales; AFBC past the scaler refused (0096); 2 `RCQ` open |
| stream restart   | ✅  | ✅  | eleven stops: no warning, no fault                               |
| 4K60 on AFBC     | 🟠  | ❓  | 6.18.60: AFBC shrinks refused (`0096`), decoder scaling instead  |
| 1080p on a TV    | ✅  | ❓  | 2026-10-31: 24, 25, 30, 50, 60, 120 Hz, `modetest -s`            |
| 1440p on a TV    | ✅  | ❓  | 2026-10-31: 120 Hz, the only rate the TV offers                  |
| 4K on a TV       | ✅  | ❓  | 2026-10-31: 24, 25, 30, 50, 60 Hz; 60 Hz as 10-bit 4:2:0         |
| PC monitor modes | ✅  | ✅  | the monitor's native 2256×1504 at 60 Hz, a PC timing             |
| HDMI hotplug     | ✅  | ❓  | unplugged and replugged: the picture comes back                  |
| HDMI audio       | ✅  | ❓  | heard on the TV, the default sink                                |
| 5.1 LPCM         | ❓  | ❓  | needs a receiver                                                 |
| passthrough      | ❓  | ❓  | needs a receiver                                                 |
| HDR              | 🟠  | ❓  | 6.18.60: HDR InfoFrame follows (`0095`); frame rate needs a TV   |
| CEC address      | ✅  | ✅  | `1.0.0.0` from the monitor's EDID                                |
| CEC TV remote    | ✅  | ❓  | 2026-10-31: arrows, channel, colour keys on `cec-remote`         |
| CEC TV power     | ✅  | ❓  | 2026-10-31: standby, then image view on wakes it                 |
| DDC read         | ❌  | ❌  | DDC reaches only the PHY's pads                                  |
| DDC write        | ❌  | ❌  | as DDC read                                                      |
| S/PDIF           | ➖  | ➖  | no S/PDIF                                                        |
| AV out           | ❌  | ❌  | no picture or sound on a composite-to-HDMI converter             |
| GPU headless     | ✅  | ✅  | glmark2 off-screen 122 / 121                                     |
| GPU on screen    | ✅  | ✅  | glmark2 on screen 121 / 120                                      |
| console font     | ✅  | 🟡  | `TER16x32`, by eye on 6.18                                       |
| audio timing     | ✅  | ✅  | 3 s in 3.05–3.13 s on the codec and HDMI, 44.1 and 48 kHz        |
| sleep, wake      | ✅  | ✅  | the remote's power key, both ways                                |
| off, on          | ❌  | ❌  | powered off, the IR receiver is unpowered; a replug              |
| wake routes      | ✅  | ✅  | IR, the one route                                                |
| resume stays up  | ✅  | 🟡  | the waking press lands in the suspend job                        |
| deep sleep       | ❌  | ❌  | TF-A offers no system suspend                                    |
| long suspend     | ✅  | ✅  | 120 s on the same boot, the timer re-armed                       |
| RTC              | ✅  | ✅  | `sun6i-rtc` while powered; no battery, NTP after a cut           |
| power draw       | ❓  | ❓  | draw not measured                                                |
| eMMC fio         | ✅  | ✅  | 64.7 / 67.1 MB/s; 519 / 509 IOPS 4 KiB with fsync                |
| SD fio           | ➖  | ➖  | no SD slot                                                       |
| SD hotplug       | ➖  | ➖  | no SD slot                                                       |
| eMMC speed modes | ✅  | ✅  | DDR52 through ten reboots                                        |
| external boot    | ✅  | ✅  | a stick boots before the eMMC; unbootable, the eMMC boots        |
| tvb-install      | ✅  | ✅  | `tvb-install` from a USB boot: the eMMC boots, new UUID          |
| eMMC boot        | ✅  | ✅  | our loaders on the eMMC                                          |
| window intact    | ✅  | ✅  | the window reads back as the backup                              |
| service mode     | ✅  | ✅  | FEL from the button                                              |
| service loader   | ✅  | ✅  | `fel_loader.bin`                                                 |
| eMMC size        | ✅  | ✅  | 14.7 GiB                                                         |
| full-disk read   | ✅  | ✅  | the backup's round-trip hash                                     |
| window write     | ✅  | ✅  | a write around the window reads back                             |
| install over it  | ✅  | ✅  | the image written over it booted                                 |
| Ethernet speeds  | ➖  | ➖  | no Ethernet                                                      |
| Ethernet rate    | ➖  | ➖  | no Ethernet                                                      |
| Ethernet loaded  | ➖  | ➖  | no Ethernet                                                      |
| Ethernet PHY     | ➖  | ➖  | no Ethernet                                                      |
| Wi-Fi bands      | ✅  | ✅  | 2.4 GHz only; the AP's US, DE settable                           |
| Wi-Fi rate       | ✅  | ✅  | 78–81 / 79 Mbit/s down at 40 MHz; 20 MHz halves it               |
| Wi-Fi loaded     | ✅  | ✅  | under `stress-ng`, 7.2: 66.5 up, 77.0 down vs 65.5 / 79.1        |
| Wi-Fi latching   | 🟠  | 🟠  | no latch; 2 h on 7.2: 3 drops, each back in 2.0–2.7 s            |
| scan, no region  | ✅  | ✅  | scans with no region set                                         |
| region set       | ✅  | ✅  | DE set, read back as an intersection                             |
| BT up            | ✅  | ✅  | `hci0` UP RUNNING, `errors:0`, with BLE on                       |
| BT scan          | ✅  | ✅  | LE scan: 6–8 devices on 6.18, 13 on 7.2                          |
| remote pairs     | ➖  | ➖  | the bundled remote is IR                                         |
| pairing persists | ➖  | ➖  | as remote pairs                                                  |
| BLE wake         | ➖  | ➖  | as remote pairs                                                  |
| addresses stable | ✅  | ✅  | the same MAC on every boot                                       |
| addresses own    | ✅  | ✅  | the eFuse's MAC; BT one above it                                 |
| unit firmware    | ➖  | ➖  | no per-unit firmware                                             |
| IRQ tuning       | ➖  | ➖  | no tuning needed                                                 |
| USB topology     | ✅  | ✅  | no hub before the port                                           |
| USB 3 judged     | ➖  | ➖  | USB 2 only                                                       |
| ports under load | ✅  | ✅  | a stick, 60 s mixed `fio` under `stress-ng`: 0 errors            |
| USB 3 link       | ➖  | ➖  | USB 2 only                                                       |
| USB 2 link       | ✅  | ❓  | `480M` at a cold boot, a warm reboot and hotplugged              |
| USB hotplug      | ✅  | ❓  | a stick hotplugged on the USB-A port                             |
| IR IRQ           | ✅  | ✅  | the receiver's IRQ counts                                        |
| IR keymap        | ✅  | ✅  | 31 keys, the canonical keymap                                    |
| BLE keymap       | ✅  | ✅  | a BLE remote's keys in `evtest`; on 7.2 by scan and bond         |
| remote cold boot | ❌  | ❌  | as off, on: no power-on from off but a replug                    |
| buttons          | ✅  | 🟡  | PH9: `KEY_VENDOR` on `/dev/input/recovery-button`                |
| recovery button  | ✅  | ✅  | the FEL button reaches FEL                                       |
| input names      | ✅  | ✅  | `recovery-button`, `cec-remote`, `ir-remote`                     |
| LED on           | ✅  | ✅  | blue while running                                               |
| LED off          | ✅  | ✅  | dark: the AXP313 cuts every rail                                 |
| LED suspended    | ✅  | ✅  | red in s2idle, as the human expects of stock                     |
| radio, family    | ✅  | ➖  | network lines on 6.18                                            |
| radio, -next     | ➖  | ✅  | Wi-Fi and BLE on 7.2                                             |
| any country      | ✅  | ✅  | any country settable                                             |
| module reload    | ✅  | ✅  | five reloads, `wlan0` back in 3–4 / 2.6–2.7 s                    |
| tool built       | ✅  | ✅  | `sunxi-fel` from source                                          |
| tool reads       | ✅  | ✅  | the full eMMC read                                               |
| tool writes      | ✅  | ✅  | a window written, an image booted                                |
| kernel CI        | ❓  | ❓  | not yet in CI                                                    |
| -next CI         | ❓  | ❓  | not yet in CI                                                    |
| bootloader built | ✅  | ✅  | our U-Boot, `uboot/build.sh`                                     |
| install path     | ✅  | ✅  | a USB stick, then `tvb-install`; FEL's USB disk too              |
| image layout     | ✅  | ✅  | MBR, U-Boot at 16, rootfs at 32768                               |
| release image    | ❓  | ❓  | no release run yet                                               |
| no ❓ left       | ❌  | ❌  | ❓ lines remain                                                  |
| daily use        | 🟡  | 🟡  | daily use begun, a media server                                  |
| CI green         | ❓  | ❓  | not yet in CI                                                    |
| untested named   | ❓  | ❓  | no PR yet                                                        |
| no board patch   | ✅  | ✅  | `rc-tanix-tx1`, the one board-only patch, named here             |

Beyond the checklist:

| Block                  | State | What shows it                                                  |
| ---------------------- | :---: | -------------------------------------------------------------- |
| Panic reboots          |  ✅   | back on its own in ~50 s, TF-A's watchdog fix                  |
| Crash log in ramoops   |  ✅   | `dmesg-ramoops-0` holds the panic after the reboot             |
| Wi-Fi WPA3             |  ✅   | joined with SAE                                                |
| Wi-Fi with BLE on      |  🟠   | 23.5 Mbit/s up, 15.2 down: 6 buffers, not 29                   |
| Wi-Fi firmware reboots |  🟠   | under load, 15 min to hours apart; 2.8 s off, 2.9 s to DHCP    |
| Bluetooth classic      |  ➖   | the chip has BLE only                                          |
| BLE                    |  ✅   | the user's choice, off by default; LE scan finds 6–8 devices   |
| BLE pairing            |  ✅   | a BLE remote bonded: `Bluetooth remote Keyboard` and `Mouse`   |
| Crypto engine          |  ✅   | `sun8i-ce`: AES, 3DES, SHA-2 in `/proc/crypto`                 |
| Hardware RNG           |  ✅   | `/dev/hwrng` from the CE: 256 values, zlib 1.0003              |
| Recovery after a fault |  ✅   | after each bad stream, H.264 decodes bit exact                 |
| Hardware video encode  |  ✅   | `h264_v4l2m2m`: H.264 to 4K; `-b:v` within 1.2% at 4–10 Mbit/s |
| 4K frame import, P010  |  ✅   | 3.3 ms per import and drop, both kernels; was 8.7              |

## Measured numbers — 2026-10-24

| What                        | Value                                      |
| --------------------------- | ------------------------------------------ |
| eMMC sequential write       | 67.3–70.8 MB/s, 500 MB `oflag=direct`      |
| eMMC 4 KiB write + fsync    | ~37 MB/s                                   |
| eMMC bus                    | DDR52, 50 MHz, 8 bits, 1.8 V               |
| Wi-Fi, against a wired host | 67.3 Mbit/s up, 78.0–81.4 down, 2026-10-27 |
| Wi-Fi download CPU          | 8–12% of four cores at 80 Mbit/s           |
| Wi-Fi SDIO bus              | 50 MHz, 4 bits, SD high-speed, 3.3 V       |
| CPU under load              | 1200–1320 MHz at 68–72 °C, all four cores  |
| CPU idle                    | 47–58 °C                                   |
| FEL write to RAM            | 0.3 MB/s                                   |
| Reboot to Wi-Fi             | 33 s, 17 of it before the kernel           |
| glmark2, full, 2256×1504    | 121; 42 on Debian's own Mesa               |
| USB stick, `480M`           | 29.4 MB/s read, 22.3 write; 843 / 301 IOPS |

## Video engine — 2026-10-25

The H616 datasheet's limits (§2.4, linux-sunxi's `H616_Datasheet_V1.0`; none published for the
H313), against `tools/validate/video.py` on 2026-10-31: fps the engine's alone at 3840×2160, the
CPU's own beside each encoder:

| Codec                | Datasheet            | Measured          | State                           |
| -------------------- | -------------------- | ----------------- | ------------------------------- |
| H.264 BP/MP/HP       | L4.2, 4K@30          | 31                | ✅ Cedrus                       |
| HEVC Main            | L5.1, 4K@60, 6K@30   | 61                | ✅ Cedrus                       |
| Scaled CAPTURE, ½ ¼  | —                    | 4K HEVC at ½      | ✅ `0094`, `ffmpeg/0017`        |
| HEVC Main10          | as Main              | 33                | ✅ P010 default, `0085`         |
| MPEG-2               | MP/HL, 1080p@60      | 36                | ✅ Cedrus                       |
| MPEG-1               | 1080p@60             | —                 | ❌ no hwaccel                   |
| VP8                  | 1080p@60             | 45                | ✅ `0800`, to 4096 wide         |
| VP9 Profile 0/2      | 4K@60                | 43 / 25           | ✅ `0053`                       |
| VC-1 SP/MP/AP        | 1080p@60             | 304 at 720p       | 🟠 SP/AP; MP refused            |
| MPEG-4 SP/ASP, H.263 | 1080p@60             | 32                | 🟠 `0806`, `ffmpeg/0019`        |
| AVS/AVS+, AVS2       | 1080p@60; AVS2 4K@60 | ❓                | ❌ no uAPI to adopt             |
| JPEG decode          | 45 Mpixel/s          | 28                | ✅ `0803`, to 6000×4000         |
| H.264 encode         | 4K@25, CBR/VBR       | 24, CPU 8.4       | ✅ `0069`–`0084`                |
| JPEG encode          | 1080p@60             | 10.8, CPU 6.9     | ✅ `0804`, to 4096              |
| Deinterlace (DI300)  | —                    | 121, 1080i        | ✅ `0067`, `ffmpeg/0014`        |
| AV jack, composite   | CVBS out             | —                 | ❌ no picture                   |
| Dolby Vision, HDR10+ | not listed           | —                 | ➖                              |
| HDR10 to HDMI        | CTA-861.3            | InfoFrame follows | ✅ `0095`                       |
| HLG, 10-bit to HDMI  | 10-bit HDMI          | —                 | 🟠 10-bit at 4K60 4:2:0; HLG ❓ |

LE is LibreELEC's `projects/Allwinner/patches/linux`; the VP9 decoder shares the HEVC engine's slot,
so the factory tree's `vp9@01c00000` has no hardware behind it on the H616.

## IR remote — 2026-10-25

NEC, address 0x80; the stock remote is the Tanix TX3 mini's. `linux-sunxi/0088`, `rc-tanix-tx1`:

| Button              | Scancode                            | Key                                |
| ------------------- | ----------------------------------- | ---------------------------------- |
| Power               | `0x8051`                            | `KEY_POWER`                        |
| D-pad, OK           | `0x8026`–`0x8028`                   | `KEY_UP`, `KEY_DOWN`, …            |
| OK                  | `0x800d`                            | `KEY_OK`                           |
| RETURN              | `0x801b`                            | `KEY_BACK`                         |
| Home                | `0x8053`                            | `KEY_HOMEPAGE`                     |
| Menu                | `0x8049`                            | `KEY_MENU`                         |
| Mouse               | `0x8052`                            | `KEY_TOUCHPAD_TOGGLE`              |
| Vol +/-, mute       | `0x804e`, `0x8056`, `0x804d`        | `KEY_VOLUMEUP` `…DOWN` `KEY_MUTE`  |
| ⏮ / ⏭               | `0x80bd`, `0x80bb`                  | `KEY_PREVIOUSSONG`, `KEY_NEXTSONG` |
| MEDIA MUSIC WEB APP | `0x8009` `0x8011` `0x8054` `0x804f` | red, green, yellow, blue           |
| Digits              | `0x8030`–`0x8039`                   | `KEY_0`–`KEY_9`                    |
| ⌫                   | `0x8044`                            | `KEY_BACKSPACE`                    |
| 1/a                 | `0x8058`                            | `KEY_SUBTITLE`                     |

## Quirks

- **RAM:** two ranks, each 3/4 populated. Mainline's H616 DRAM driver left a hole at `0x70000000`;
  `patches/u-boot/0004` keeps the ranks contiguous, and the SPL reports `DRAM: 1536 MiB` itself.
- **eMMC:** DDR52 needs stock's output phase and sample delay (`patches/linux-sunxi/0043`, `0044`,
  `allwinner,sample-delay = <20>`); at mainline's defaults writes fail and the request hangs.
- **GPU:** one Mali-G31 shader core (`shader_present=0x1`, the hardware's own count).
- **Video engine:** decode bit exact, H.264 and VP8 to 4096×2304, HEVC and VP9 to 8192×4320, at 10
  bits to 6144×3456, MPEG-2 to 4000×2250; JPEG to 6000×4000, 4:2:2 and 4:4:4 as 4:2:0. MPEG-4 Part 2
  and H.263 baseline to 4080×2160 by PSNR against software, the IDCTs differing: 60–70 dB on
  FFmpeg's encodes, Xvid and DivX 48–73 on average; quarter-sample luma 45–57 dB; interlaced streams
  with B-VOPs and H.263 annexes left to software. H.264 encode runs 176×144 to 4096×4096 at any even
  size, JPEG encode 16×16 to 4096×4096; `/dev/video*` named `cedrus-enc`.
- **Tolerated log line:** `hdmi-audio-codec …: HDMI: Unknown ELD version 0` at each HDMI plug event;
  HDMI audio plays after the replug.
- **Boot warnings, all tolerated:** the kernel's KASLR without a seed, two GPIO bases, two dummy
  regulators and the out-of-tree taint; the Wi-Fi driver's three firmware-load register writes, one
  `wsm_generic_confirm:status(2)` and `wsm_write_mib fail … mibId=4132` (the firmware refuses that
  MIB), two scan starts and its channel type.
- **Boot time:** of the kernel's 5.6 s, the display engine's binding takes about 2 s, its LCD
  controller bound three times; the root device waits 2.4 s on udev's coldplug.
- **Clock:** the SoC's RTC runs only while the box has power; no backup battery is fitted, so the
  time is lost at every power cut and NTP sets it after boot.
- **Stock's `/proc/meminfo`** claims about 2 GB; its own memory map holds 1.5 GiB.

## BLE

The ATBM6031-X has BLE, no classic Bluetooth. BLE is the user's choice, off by default: its firmware
costs Wi-Fi most of its throughput. On, on the box:

```sh
apt install bluez
echo 'options atbm6031 wifi_bt_comb=1' > /etc/modprobe.d/atbm6031-ble.conf
reboot
```

Off: delete the file and reboot. Measured 2026-10-25, TCP against a wired host:

| `wifi_bt_comb` | Firmware              | Input buffers | Up / down, Mbit/s |
| -------------- | --------------------- | ------------- | ----------------- |
| 0, the default | `atbm6031_fw.bin`     | 29            | 62.4 / 66.6       |
| 1              | `atbm6031_ble_fw.bin` | 6             | 23.5 / 15.2       |

The BLE image keeps its BLE code in the chip's shared SRAM and leaves 6 frame buffers; the driver
only reads the count. Its coexistence control shares airtime while BLE runs and frees no buffers.

On, the controller is BlueZ's `hci0`, on SDIO, at `54:14:E9:D9:73:D2`: public, the eFuse's Wi-Fi MAC
plus one, the same on every load; the firmware sets it, the driver does not. At power-on BlueZ logs
`unexpected cc 0x0c14 length: 250 > 249` and `0x0c23 length: 1 < 4`, two replies a byte off.

## Factory boot chain and the eMMC

| Sectors      | Stock                                 | TVBian            |
| ------------ | ------------------------------------- | ----------------- |
| 0            | GPT                                   | MBR               |
| 16           | boot0, 64 KiB                         | U-Boot (SPL+BL31) |
| 512–639      | a second boot0                        | —                 |
| 12288–12799  | secure storage: key map, MAC, serial  | kept as it is     |
| 24504        | `sdmmc_arg`                           | —                 |
| 24576, 32800 | boot package: BL31, U-Boot, the `dtb` | —                 |
| 32768        | —                                     | the rootfs        |

`preserve-sectors` names the secure storage; an install writes around it.

## Serial console

Pads `VCC RX TX GND`, 115200 8N1, outlined on `board2.jpg`.

## Recovery — read this before writing anything

The FEL button always works: the boot ROM reads it, whatever is on the eMMC. With the OTG cable in
and no DC, hold it and plug the cable. The stock eMMC is `backup/tanix-tx1-v2-stock.img.xz`.

Stock's own recovery gestures, read by stock U-Boot alone (`key_boot_recovery`, `ir_boot_recovery`
in its tree), each setting `misc` to boot Android's recovery. Stock stores an IR address with its
complement in the high byte, so `0x7f80` is address `0x80`:

| Gesture                              | Source                                                |
| ------------------------------------ | ----------------------------------------------------- |
| PH9 held 2 s at power-on             | `recovery_key`, long press only                       |
| Another remote's `0x45` held at boot | NEC address `0x40`, power `0x4d`; not the bundled one |
| Menu held through stock's first 2 s  | `0x8049`, `ir_detect_time` 2000 ms, key repeats read  |

## Known gaps

Open items, with their state, are in the board's todo.
