# Tanix TX1 V2.0 — device tree

`boards/tanix-tx1-v2/board.dts` is the factory tree (`factory_board.dts`, the boot package's one
`dtb`) moved onto mainline 6.18 by hand; `board.patch` is the diff, and
`./build.sh board-dtb tanix-tx1-v2` regenerates the tree from both. U-Boot boots on the same tree
(`BOARD_UBOOT_DTB=board`), as stock's U-Boot reads its one tree.

## Kept from the factory tree

| Block       | Value                                                                 |
| ----------- | --------------------------------------------------------------------- |
| eMMC `mmc2` | 50 MHz, 8 bits, DDR52 at 3.3 V, its bank's; no hardware reset         |
| eMMC pins   | its two groups: PC1–PC16 pull-up, PC0 pull-down, 30 mA                |
| Wi-Fi       | `mmc1` 150 MHz cap, `keep-power-in-suspend`, port G on DLDO1, 3.3 V   |
| Wi-Fi power | PG10 32 kHz out, `wlan_regon` PG18, `chip_en` PG19, 200 ms            |
| Wi-Fi 32k   | from the PLL, `CLK_PLL_SYSTEM_32K`, not the RTC's RC                  |
| PMIC rails  | DCDC2 CPU 900–1120 mV; DCDC1, DCDC3 at boot; ALDO1 1.8 V, DLDO1 3.3 V |
| Thermal     | CPU trips 60, 70 °C passive, 115 °C critical; its CPU map             |
| GPU points  | 504, 540, 576, 600 MHz, all at 950 mV                                 |
| LEDs        | PH6 `power` blue, on; PH7 `standby`, off; states retained             |
| Button      | PH9, stock's `recovery_key`, as `gpio-keys` `KEY_VENDOR`              |
| USB1 VBUS   | PH8, driven high                                                      |
| IR          | `ir@7040000` on PH10                                                  |

## Changed

| Change                                     | Why                                                     |
| ------------------------------------------ | ------------------------------------------------------- |
| vendor-only nodes gone                     | no mainline binding                                     |
| pin groups: `pins`, `function`, `bias-*`   | U-Boot skips the legacy `allwinner,*` names             |
| uart0: no drive strength                   | vendor `0xffffffff` reads as 0 mA                       |
| `mmc2` `allwinner,sample-delay = <20>`     | stock's DDR52 tuning; `linux-sunxi/0044`                |
| PMIC rails: the vendor's span              | boot voltages stand; DCDC2 held to the CPU's OPPs       |
| GPU and other zones: 110 °C critical       | no cooling map, as mainline                             |
| `mmc0` (SD) kept, disabled                 | `sunxi-u-boot.dtsi` aliases it; no slot is fitted       |
| `secmon@40000000` reserved                 | TF-A's BL31, in the vendor's secure window              |
| `ramoops@7e000000`, 1 MiB                  | the crash log, in the rank the DRAM fix made whole      |
| display engine and `hdmi-connector`        | mainline's H616 display pipeline                        |
| `deinterlace@1420000`, IOMMU master 1      | the factory's `di` on mainline's DI300 binding          |
| `video-codec@1c0e000`, `ve_sram`           | the factory's `ve@01c0e000`, for Cedrus                 |
| mixer0 `iommus = <&iommu 0>`, `0707`       | mixer 0 is the DRM device's DMA device                  |
| `audio-hub@5097000`, `sound-hdmi`          | HDMI audio, LibreELEC's hub; DAI 1 the HDMI's           |
| `&hdmi` `#sound-dai-cells = <0>`           | the hub's codec                                         |
| `ir@7040000` `linux,rc-map-name`           | the stock remote: `rc-tanix-tx1-v2`, `linux-sunxi/0088` |
| `planes@100000` `iommus`, beside mixer0's  | buffers map through it; one IOMMU group                 |
| `tcon-top` TV1 clocks and output           | the TCON-TOP driver reads `tcon-top-tv1`                |
| `ve_sram` `allwinner,sun50i-h616-ve-sram`  | upstream's name, on both kernels by `0046`              |
| `tcon_tv1`, TCON-TOP TV1 endpoints         | the composite path: mixer1, TCON-TV1, the encoder       |
| `tv-encoder@6524000`, top at `0x06520000`  | the AV jack's composite; PLL-VIDEO1 at 216 MHz          |
| SID `tve-calibration@2c`                   | the encoder's DAC calibration, from the efuse           |
| CPU OPPs: stock's, `opp-microvolt-speed4`  | stock's ladder for SID `0x5c00`, to 1344 MHz at 1.12 V  |
| alias `ethernet0` on `wifi@1`              | U-Boot's stable Wi-Fi MAC                               |
| pin banks on the rails `PIO_POW_VAL` reads | PC and PG measure 3.3 V; stock names no bank supply     |
| `mmc2` `vqmmc-supply` on DLDO1             | its bank, PC, at 3.3 V; stock's ALDO1 set it to 1.8 V   |

The sample delay is this unit's; another unit may tune differently.

## Tried and reverted

| Change                       | Result                       |
| ---------------------------- | ---------------------------- |
| mainline's V1.1 tree, edited | replaced by the factory port |
