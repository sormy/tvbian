# X98H — board details

Built from the stock firmware. No one has booted TVBian on this box yet, so it is
`BOARD_SUPPORT=not_tested` until an owner reports back.

## Identity

| Field           | Value                                   | Source                               |
| --------------- | --------------------------------------- | ------------------------------------ |
| Model           | X98H, 4 + 32 GB, 100 Mb/s Ethernet      | listing photos; PCB sticker          |
| SoC             | Allwinner H618 (sun50iw9)               | owners' mainline boots; factory tree |
| RAM             | DDR3, 648 MHz, four Micron D9QBQ        | factory boot0; `pcb-top.webp`        |
| eMMC            | Kioxia THGBMFG8C4LBAIR, 32 GB, HS200    | `pcb-bottom.webp`; owner's dmesg     |
| SD              | a TF slot; high speed, no UHS           | `pcb-top.webp`; factory tree         |
| PCB             | `YB927_141_V1.1`; code `23253`          | `pcb-top.webp`                       |
| Ports           | DC, S/PDIF, HDMI, RJ45, AV, 3 USB-A, TF | `pcb-top.webp`; `image2.webp`        |
| PMIC            | AXP1530, mainline's AXP313A             | factory tree; owner's BOOT0 banner   |
| Wi-Fi / BT chip | AIC8800D80; Bluetooth classic or LE ❓  | module marking, in the issue below   |
| Ethernet PHY    | AC300 EPHY, co-packaged, MDIO address 0 | owner's MDIO scan, ID `0x00441400`   |
| Front panel     | AiP1628, 4 digits; PC2, PC7, PC12       | `pcb-bottom.webp`; `aw_vfd`          |
| LEDs            | PH6 power, PH7 standby; colours ❓      | factory `gpio_para`                  |
| IR receiver     | PH10, behind the front panel ❓         | factory tree                         |
| Buttons         | recovery, a toothpick hole; PH9 ❓      | owner; `sys_config.fex`              |
| Remote          | 30 keys, NEC address `0xfe01`           | `image3.webp`; factory wake list     |

`image1.webp` to `image3.webp` are the seller's photos: the box, its ports and size, and the package
with the remote. `pcb-top.webp` shows the SoC side, `pcb-bottom.webp` the eMMC and panel side. There
is also an X98H with gigabit Ethernet; it is a different PCB and not this board.

### The stock image

Three PhoenixSuit images, from the Google Drive the GitHub issue
<https://github.com/ophub/amlogic-s9xxx-armbian/issues/3717> links: `X98H_20221020-1143.img`,
`X98H_20230704-1632.img` and `X98H_20240524-1344.img`, Android 12, Linux 5.4.125.

| Image      | Kernel tree         | boot0 DRAM              | U-Boot  |
| ---------- | ------------------- | ----------------------- | ------- |
| 2022-10-20 | fewer CPU OPPs      | as below                | 2018.05 |
| 2023-07-04 | = 2024's            | as below; one table 648 | 2018.07 |
| 2024-05-24 | `factory_board.dtb` | as below; one table 600 | 2018.07 |

- `factory_board.dtb` is the 2024 image's `sunxi.fex`. An owner's copy from the box's eMMC is the
  same, apart from two values U-Boot writes at boot.
- `factory_boot0.bin` is the 2024 image's `boot0_sdcard.fex`. The DRAM settings our U-Boot uses are
  the same in all three images and on the owner's box: DDR3 at 648 MHz.
- The Wi-Fi calibration file in `tvb-firmware-aic8800` matches the image's in every setting that is
  turned on.

## Serial console

| Item     | Value                                                                 |
| -------- | --------------------------------------------------------------------- |
| Location | three holes in the corner between the back USB-A and the side's first |
| Pinout   | GND, TX, RX from the corner; labelled RX TX GND on the eMMC side      |
| Level    | 3.3 V, the family's                                                   |
| Console  | `ttyS0`, UART0 on PH0/PH1, 115200                                     |

Which pad is square, and the pads marked on a photo, are still to come from an owner.

## Addresses

Each box has its own Ethernet, Wi-Fi and Bluetooth addresses. Our U-Boot reads them from the SoC's
secure storage and sets them through the tree's `ethernet0`, `ethernet1` and `bluetooth0` aliases.
No box's addresses are known here.

## Test report — 2026-11-26, import

Marks show what the files prove. Anything that needs a running box stays ❓ until an owner reports.

| Check                   | Mark | What shows it                                           |
| ----------------------- | :--: | ------------------------------------------------------- |
| board identified        |  ✅  | PCB and listing photos; the issue's case and PCB        |
| image tied to the board |  ✅  | owner's eMMC carve equals 2024's tree                   |
| DRAM init classified    |  ✅  | vendor's: `sys_config` tables, no public counterpart    |
| factory tree decompiles |  ✅  | 220 cells named, none a number; round trip exact        |
| per-board rows sourced  |  ✅  | each row in `dtb.md` names its source                   |
| loader, U-Boot, package |  ✅  | `./build.sh loader`, `uboot`, `board x98h`              |
| image                   |  ✅  | `./build.sh image x98h`, 129 MiB                        |
| SD boot                 |  ❓  |                                                         |
| CPU frequency scaling   |  🟡  | stock's OPPs for bins 0–4; the H313's AXP313A ramp      |
| eMMC                    |  🟡  | the H313's HS200 on the same host                       |
| Ethernet                |  🟡  | the H313's AC300 on EMAC1, 91–94 Mb/s                   |
| Wi-Fi                   |  🟡  | the AIC8800D80 on the R69-1 and HK1                     |
| Bluetooth               |  🟡  | the AIC8800D80 at 1.5 Mbaud on the R69-1 and HK1        |
| HDMI and its audio      |  🟡  | the H313's DE33, HDMI and audio hub                     |
| AV jack                 |  🟡  | the H313's TV encoder                                   |
| USB host                |  ❓  | one VBUS switch, PH8, for every port                    |
| S/PDIF                  |  ❓  | the controller only; no card yet                        |
| remote                  |  ❓  | `rc-x98h`, 27 of 30 keys from stock's layout            |
| front panel             |  ❓  | TM16xx SPI backend not built for `sunxi64`              |
| LEDs                    |  ❓  | PH6 power, PH7 standby, colours unknown                 |
| recovery button         |  ❓  | PH9, stock's `sys_config` `recovery_key`; FEL in U-Boot |

## Measured

Nothing yet: no box here.

## Front panel

An AiP1628 on three wires. Each even address from 0 to 12 is one segment, and each bit is one digit.
This is how stock's `Led_Time_Display` drives it, and what an owner saw lighting it up:

| Element               | Address, bit                     |
| --------------------- | -------------------------------- |
| segments a–g          | 0, 2, 4, 6, 8, 10, 12            |
| digits, left to right | bits 7, 6, 5, 4                  |
| icons                 | bit 3; HDMI at 10, CVBS at 12    |
| USB, card icons       | stock 0 and 2; one owner 4 and 6 |

## Remote

`rc-x98h` maps 27 of the 30 keys, taken from stock's `customer_ir_fe01.kl` (NEC address 0x01). The
APP, KD and cog keys send some of stock's F1–F11, MUSIC and EXPLORER codes. Which ones needs a press
on a real remote.

## Known gaps

- The CPU's speed bin is unknown. On newer chips, stock splits speed bin `0x5c00` into two bins, 5
  and 6, that mainline treats as bin 4. Bin 5 needs higher voltages, and the tree does not have
  them.
- Which DRAM table the strap pins (PI14–PI16) pick is unknown. The 2024 image lowered table 7 to 600
  MHz; the owner's box trained at 648 MHz with the default table.
- The pin bank voltages come from the factory tree and the eMMC's rail, not from a reading on a box.

## Recovery

The boot ROM tries an SD card before the eMMC. Run TVBian from a card and the eMMC stays untouched;
pull the card and Android boots again. Once our U-Boot is on the eMMC, holding PH9 at power-on
enters FEL, and `boards/x98h/fel_loader.bin` then shares the eMMC over USB for a backup or restore.
The box has a recovery button behind a toothpick hole and an OTG port, so it can also be backed up
and installed over FEL. That the button is PH9, and which USB-A socket is the OTG one, are still to
confirm; the side sockets are printed `USB2` and `USB3`, which points at the back one.
