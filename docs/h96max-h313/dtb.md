# H96 Max H313 device tree

Boots from SD on 6.18.62, and on 7.3.3, the `-next` kernel.

| Block        | Mainline description                               |
| ------------ | -------------------------------------------------- |
| SoC          | H616 clocks, interrupts, resets and pinctrl        |
| PMIC         | AXP313 binding for factory AXP1530                 |
| UART0        | PH0/PH1                                            |
| SD           | MMC0, PF0–PF5, detect PF6 pulled up                |
| eMMC         | MMC2, 8-bit HS200 at 100 MHz                       |
| Wi-Fi        | MMC1, PG18 reset, PG10 clock                       |
| Ethernet     | EMAC1 RMII, PA0–PA9                                |
| EPHY         | AC300 package on EMAC1 MDIO, address 0             |
| EPHY clock   | PWM5 PA12, 24 MHz bypass                           |
| LEDs         | PH6 power, blue; PH7 standby, red; states retained |
| Recovery     | PH9 in the AV jack, `gpio-keys` `KEY_VENDOR`       |
| IR           | PH10, `rc-h96max-h313`                             |
| USB          | Factory host mode; FEL loader uses peripheral mode |
| Video, audio | Existing H616 mainline bindings                    |
| AV           | Mixer1, TCON TV1, the TV encoder; composite off    |
| Bluetooth    | UART1 PG6–PG9, `aicsemi,aic8800-bt` at 1.5 Mbaud   |
| BT GPIOs     | Hogs: PG19 reset and PG17 wake held high           |

Factory boot0 supplies the loader's DRAM parameters; the factory tree's `/dram` is a DDR3 template.

## EPHY variant

The factory tree describes an AC200 on TWI3 at 0x10; the vendor kernel picks AC200 or AC300 at run
time. This unit's SID word at 0x2c is `0x0507`: bit 8 selects AC300, calibration 7. No AC200 answers
on TWI3, so the tree has no TWI3 and no AC200 node.

## Pending checks

- eMMC: stock's 100 MHz and HS200; HS400 left out, mainline's `sunxi-mmc` has none. No sample delay.
- Pin banks on the rails `PIO_POW_VAL` (`0x0300b348`) measures: PC and PG at 1.8 V on ALDO1, PF, PH
  and PI at 3.3 V on DLDO1. The Wi-Fi host's `vqmmc-supply` is ALDO1, so the bus signals at 1.8 V as
  its bank runs; high speed, no UHS. Wi-Fi associates and Bluetooth comes up on it.
- CPU OPPs are stock's table, one row a frequency, `opp-microvolt-speed4` for SID `0x5c00`, stock's
  bit 2 and mainline's bin 4; the other bins are open questions and get no rows. DCDC2 is held to
  those OPPs, 900–1120 mV; DCDC1 and DCDC3 keep the vendor's span, so their boot voltages stand.
- Bluetooth host wake, PG16, is not wired; nothing wakes on it yet.
- The remote's keys need validation.
