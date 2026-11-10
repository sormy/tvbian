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
| LEDs         | PH6 power, blue, active-low; PH7 standby, red      |
| Recovery     | None; FEL in the AV jack, the boot ROM's           |
| IR           | PH10, `rc-h96max`                                  |
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
- Port G at 3.3 V: the bank's mode register and DLDO1's 3.3 V both show it. Stock's SDIO node sets
  `sdio-used-1v8`: its Wi-Fi bus runs at 1.8 V, ours at 3.3 V, held to high-speed.
- CPU OPPs are the factory table, every bin, DCDC2 capped at 1160 mV.
- Bluetooth host wake, PG16, is not wired; nothing wakes on it yet.
- The remote's keys need validation.
