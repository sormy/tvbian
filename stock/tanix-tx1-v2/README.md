# Tanix TX1 V2.0 — stock evidence

Read 2026-10-23 from stock Android 10 over the serial console, root through `su 0`, each file
gzipped and base64'd across the line and checked by SHA-256. `mac_addr` is redacted to
`XX:XX:XX:XX:XX:XX` in `cmdline.txt`, `getprop.txt` and `board-runtime.dtb`'s `/chosen/bootargs`.

| Property    | Value                                                                |
| ----------- | -------------------------------------------------------------------- |
| silkscreen  | `QHZIW_H313_TX1_EMCP_V2.0`, `DATE:2024-03-21`                        |
| SoC         | Allwinner H313, `allwinner,h616 arm,sun50iw9p1`, chip id `0x5c00`    |
| PMIC        | AXP1530 at `0x36`                                                    |
| DRAM        | LPDDR3, 1536 MB, 600 MHz, `DRAM_VCC` 1200 mV                         |
| eMMC        | Samsung `Q316BB`, manfid `0x15`, 30777344 sectors                    |
| Wi-Fi       | AltoBeam ATBM6031-X, SDIO `007a:6011`, driver `atbm613x_wifi_sdio`   |
| build       | `Google/p281/p281:10/QP1A.191105.004/eng.lizhon.20260714.193338`     |
| bootloaders | boot0 `12a0e3cc`, BL31 `05d6c57` 2021-10-28, U-Boot 2018.05-g8ac4189 |
| kernel      | 4.9.170, built 2026-06-23                                            |

| File                            | What                                                    |
| ------------------------------- | ------------------------------------------------------- |
| `boot.log`                      | power-on to the shell prompt: boot0, BL31, U-Boot       |
| `u-boot.bin`, `monitor.bin`     | the boot package's `u-boot` and BL31 items              |
| `dtbo.dtb`                      | the boot package's `dtbo` item                          |
| `board-runtime.dtb`             | `/sys/firmware/fdt`, after U-Boot edited it             |
| `gpt.bin`                       | sectors 0–33                                            |
| `firmware/`                     | the `ATBM_*` files from `/vendor/etc/firmware`          |
| `dmesg.txt`                     | from 6.6 s: the ring buffer had wrapped                 |
| `cmdline.txt`, `getprop.txt`    | the boot                                                |
| `kernel-config.txt`             | `/proc/config.gz`                                       |
| `cpuinfo.txt`, `meminfo.txt`    | the SoC and its memory                                  |
| `iomem.txt`                     | the memory map                                          |
| `partitions.txt`                | `/proc/partitions`, `by-name`                           |
| `emmc-identity.txt`             | CID, CSD, life time                                     |
| `lsmod.txt`, `sdio.txt`         | the vendor's drivers; the SDIO IDs and `vendor/modules` |
| `gpio.txt`, `pinmux.txt`        | the wiring state                                        |
| `regulators.txt`, `clocks.txt`  | the rails and clocks                                    |
| `cpufreq.txt`, `thermal.txt`    | the factory OPPs and trip points                        |
| `input-devices.txt`, `leds.txt` | buttons, IR, LEDs                                       |

boot0, eMMC sector 16, 64 KiB, is `boards/tanix-tx1-v2/factory_boot0.bin`. The boot package sits
twice, at sectors 24576 and 32800, byte-identical; its `dtb` item is
`boards/tanix-tx1-v2/factory_board.dtb`.
