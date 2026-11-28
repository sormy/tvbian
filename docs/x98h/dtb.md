# X98H device tree

Translated from the stock Android 12 tree (Allwinner's 5.4 kernel) to mainline 6.18 with
`kernel-h616-vendor-5.4`. `board.patch` holds the changes below. Built, not yet booted.

| Block      | Mainline description                               | Source                      |
| ---------- | -------------------------------------------------- | --------------------------- |
| SoC        | H618: `allwinner,sun50i-h618`, cpufreq's key       | owners' mainline boots      |
| PMIC       | AXP313A for the AXP1530; the binding's IRQ pair    | factory tree                |
| Rails      | ALDO1 1.8 V, DLDO1 3.3 V, fixed; DCDC3 U-Boot's    | `sys_config` `[power_sply]` |
| CPU        | stock's OPPs, speed bins 0–4; DCDC2 held to them   | factory tree                |
| Banks      | PC on ALDO1, PG on stock's 1.8 V; PF unset, 3.3 V  | eMMC's vqmmc; factory tree  |
| eMMC       | MMC2, 8-bit HS200 at 100 MHz, enabled              | factory tree; stock U-Boot  |
| SD         | MMC0, PF0–PF5, detect PF6 pulled up, 30 mA         | factory tree                |
| Wi-Fi      | MMC1 at 1.8 V, PG18 reset, PG10 32 kHz clock       | factory tree                |
| Bluetooth  | UART1 PG6–PG9, `aicsemi,aic8800-bt` at 1.5 Mbaud   | the D80 on the R69-1, HK1   |
| Ethernet   | EMAC1 RMII PA0–PA9, the AC300 at MDIO 0            | owner's MDIO scan           |
| EPHY clock | PWM5, 24 MHz                                       | factory `tv_pwm_ch`         |
| USB        | one VBUS switch, PH8, on all four PHY ports        | factory `drvvbus-supply`    |
| HDMI       | DE33, TCON TV0, HDMI on ALDO1, its sound card      | factory tree                |
| AV         | the TV encoder, enabled                            | the AV jack, `pcb-top.webp` |
| LEDs       | PH6 power, active-low; PH7 standby                 | factory `gpio_para`         |
| Recovery   | PH9, `gpio-keys` `KEY_VENDOR`                      | `sys_config` `recovery_key` |
| IR         | PH10, `rc-x98h`: 27 of the remote's 30 keys        | stock `customer_ir_fe01.kl` |
| Addresses  | `ethernet0` EMAC1, `ethernet1` Wi-Fi, `bluetooth0` | U-Boot's MACs               |
| Crash log  | `ramoops` at 0x7e000000                            | the family's                |

## Checks

- `semdiff` against stock's tree: every difference comes from a commented rule in the translation
  conf, mainline's dtsi, or `board.patch`.
- `dt-validate` against 6.18's bindings with our patches: only the board's own compatible and the
  H616's SRAM sections, which every H616 board reports.

## Left as questions

- The front panel (stock's `aw_vfd`): an AiP1628 on PC2, PC7 and PC12. It needs a `titanmec,tm1628`
  node on `spi-gpio`, and our TM16xx build has no SPI support for `sunxi64` yet.
- S/PDIF: the controller on PH4 is on, but there is no sound card for it yet.
- The I2S2 card on PG11 and PG12, probably the radio's audio link.
- The AC200 node: the H618 has its own TV encoder and codec, and Ethernet uses the AC300.
- Bluetooth host wake on PG16, and Wi-Fi host wake on PG15. Wi-Fi uses the SDIO bus's own interrupt;
  PG15 would only matter for wake-on-WLAN.
- Stock's CPU speed bins 5 and 6, which mainline treats as bin 4.

## Slower than stock

- Wi-Fi's SDIO bus at 50 MHz high speed; stock runs SDR104. Mainline's `sunxi-mmc` has no tuning for
  SDR104.
- The SD card at high speed; stock switches its I/O to 1.8 V for UHS, which mainline cannot yet.

## Not taken from the sister

- The H313's Wi-Fi power-on delay: this box's stock tree has none.
- LED colours: an owner has to look.
