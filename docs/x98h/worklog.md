# X98H worklog

## 2026-11-26 — sources

- Pull request 11 (an owner's box, on a community mainline kernel): the photos, an eMMC carve of the
  kernel tree and the eMMC's boot0 (`factory_boot0.bin`), and the owner's boot facts. Its tree was
  the vendor's as carved, never translated; nothing else of it is taken.
- The GitHub issue <https://github.com/ophub/amlogic-s9xxx-armbian/issues/3717>, a second owner on
  the same PCB and date code: AIC8800D80 marking, the AC300 EPHY at MDIO address 0 (ID `0x00441400`,
  control at 16), EMAC1 RMII on PA0–PA9, and its stock images' Google Drive.
- Three PhoenixSuit images, SHA-256:
  - `X98H_20221020-1143.img` `adc9180e9da45a33158c733319a6dc43200ca78fcad713396bf38d51b2b2482f`
  - `X98H_20230704-1632.img` `8ee08ec23db9e6397b19d87d1a35a67656236333a917118912ec3302ea773196`
  - `X98H_20240524-1344.img` `7ad201b63f36683399ec19fc26b05a03fa90599ffd6974cfbc082fc78d946422`

## 2026-11-26 — the images compared

- Unencrypted `IMAGEWTY` v3, 45 items each, the same layout. Kernel 5.4.125 (boot.fex banner);
  `vmlinux.fex` is the unstripped vmlinux, bzip2 over a tar.
- `sunxi.fex`, phandles aside: 2023 = 2024. 2022 lacks the 1032, 1296 and 1344 MHz CPU OPPs, the a5
  and a6 voltages and `ts0`. The owner's eMMC carve equals 2024's but for `pinctrl-2` and a
  `sunxi-dly-208M` that the vendor's U-Boot writes at boot.
- boot0 V0.651 in all three. Its first DRAM table, the 32 words from byte 56: DDR3, 648 MHz,
  `dx_odt 0x03030303`, `dx_dri 0x0e0e0e0e`, `ca_dri 0x1f12`, `tpr0 0xc0001002`, `tpr6 0x33808080`,
  `tpr10 0x002f1107`, `tpr11 0xddddcccc`, `tpr12 0xeddc7665`, equal in all three and on the eMMC.
  The eMMC copy differs in the words boot0 writes back: `para1 0x310b`, `para2 0x10000000`,
  `mr0 0x1f14`, `mr2 0x20`, `tpr1`, `tpr13 0x6041`.
- A second table at byte 1652: 648 MHz in 2022, 2023 and the eMMC, 600 MHz in 2024. It is
  `sys_config`'s `[dram_para7]`; `[dram_select_para]` reads PI14–PI16 to pick one of 32 tables. The
  eMMC boot0 equals 2023's but for the checksum and the trained words.
- Taken: 2024's tree, the eMMC's boot0; then 2024's boot0, the image's own (below). DRAM classified
  as the vendor's: `sys_config` tables, no public counterpart; our U-Boot reads only words equal in
  every copy.

## 2026-11-26 — the 5.4 base

- `kernel-h616-vendor-5.4`: Orange Pi's `orange-pi-5.4-sun50iw9` at `3a4a2941`, Allwinner's 5.4 BSP;
  its `sun50iw9-ccu.h` values equal the blob's cells on 17 nodes checked by hand.
- `dtcx.py -n`: 220 cells named, none left. Two dtcx faults found on the way: sunxi's three-cell
  GPIOs rendered pin as flags (`<&pio 5 GPIO_OPEN_DRAIN 17>`), and a `#define` after a guard and a
  blank line was swallowed (`CLK_RTC_1K`). Every other board's decompile is unchanged by both.

## 2026-11-26 — the translation

- `kernel-h616-vendor-5.4.translate.conf` inherits the 4.9 BSP's (`rules`), its own rules first. 0
  unknown, 9 questions, each this board's.
- The vendor's 5.4 drivers, read in the vmlinux or Orange Pi's source:
  - pinctrl reads `pins`, `function`, `drive-strength`, `bias-*` before `allwinner,*`; stock ran the
    SD's pins at 30 mA, not the legacy copy's 40 (`shadowed-by`).
  - PF's bias comes from the state's `power-source`, never `vcc-pf`; PG's from its 1.8 V dummy.
  - `sun50iw9_nvmem_xlate`: SID bin `0x5c00` is bin 4 on revision A, else 5 or 6 by
    `(sid[0x20] << 5) - 0xa60 < 0x941` and `(sid[0x28] & 0x3ff) - 0x26 < 8`. Bins 0–4 decode as
    mainline's; a4 and a6 are one ladder, a5 another, up to 1320 MHz at 1.15 V.
  - `hdmi_power_enable` gets `aldo1` and `dcdc1` through the node's `*-supply`; both always on.
- Wrong turns, each caught before a box: the CPU OPP rows all dropped (`speed_bins` knew only 4.9's
  one-voltage rows); USB VBUS never reached the PHY; the audio hub left disabled; `uboot_hdmi` built
  a second HDMI connector; the BL31 reservation at 0x48000000 kept.
- The issue's random resets came from DCDC2 with no settling time. The H313 on 6.18.65 takes stock's
  `regulator-ramp-delay = <200>` on DCDC2: registered, transition latency 1344144 ns. This tree
  keeps it.
- Every other board's translation is unchanged; the six RK3528 `next2` trees write
  `endpoint@ROCKCHIP_VOP2_EP_RGB0` as `endpoint@1`, the same blob.

## 2026-11-26 — the board

- Rails: the tree gives ALDO1 and DLDO1 0.5–3.5 V; `sys_config` `[power_sply]` sets 1.8 and 3.3 V.
  Fixed in the patch, so the MMC core cannot lift the eMMC's and Wi-Fi's I/O rail to 3.3 V.
- Wi-Fi calibration: stock `vendor_a` `/etc/firmware/aic_userconfig_8800d80.txt` equals the
  package's in every enabled value.
- The recovery key: first taken as absent, the tree having none; `sys_config.fex` names PH9. Our
  U-Boot's PH9 holds, and the tree has `gpio-keys` on it.
- `./build.sh board-dtb x98h`: the patch applies, compiles against 6.18, 0 differences from its
  explicit-phandle form, the upstream view proven; `devices.py` finds no block twice.
- `./build.sh loader x98h`: `fel_loader.bin`, U-Boot v2026.10, TF-A v2.14, DDR3 at 648 MHz.
  `./build.sh uboot x98h`, `./build.sh board x98h`: built.

## 2026-11-26 — the DRAM rail, and the owner's working tree

- Our U-Boot set DCDC3 to the Tanix TX1 defconfig's 1.2 V, LPDDR3's, on this DDR3 board.
  `uboot/build.sh` now gives a DDR3 boot0 1.36 V, mainline's for the Transpeed 8K618-T (DDR3,
  AXP313) and the issue's owner's reading on a running box. Stock's boot0 prints
  `DRAM_VCC set to %d mv`; the owner's banner has the value.
- `semdiff.py` against the PR's `upstream_board.dtb`, the community tree the owner's box runs, 209
  lines. The same: EMAC1 RMII and the AC300 at MDIO 0, Wi-Fi on MMC1 with PG18, the eMMC on MMC2,
  the HDMI pipeline, DCDC2 given time to settle (his `settling-time-up-us = 1000`, ours stock's
  `ramp-delay = 200`), DCDC3 at 1.36 V.
- Stock's where his is a generic H616's: CPU OPPs, thermal trips, the eMMC at 100 MHz, the SD's card
  detect pulled up, the Wi-Fi's I/O at 1.8 V on ALDO1.
- Ours only: LEDs, the recovery key, Bluetooth in the tree, the TV encoder, the fourth USB pair
  (`5311000`), VBUS on PH8, ramoops, the deinterlacer, the IOMMU on the display.
- His only: the Wi-Fi's host wake on PG15, and the vendor's audio and PWM drivers' nodes, which that
  kernel carries.
- His Bluetooth works with `enable-gpios` PG19 active-low under that kernel's `hci_aic8800`; ours
  drives PG19 as an active-low reset through our driver, as the H313 runs the same vendor line.
  Which level PG19 holds with `hci0` up is the owner's to read.

## 2026-11-26 — every file from the 2024 image

- `factory_boot0.bin` replaced by 2024's `boot0_sdcard.fex`
  (`ac8a90fa2d00d589001e489bbddf1225cc2786b447787bd91438e862156dae4d`): the import takes the image's
  own loader, not an owner's unit. The DRAM words our U-Boot reads are unchanged.

## 2026-11-26 — the front panel's map, against stock's driver

- Stock drives the panel from the kernel: `Led_Time_Display`, `MDrv_TM1623_*` and an icon switch
  each, in the vmlinux. Its display RAM is 14 bytes, written at the even addresses 0–12.
- `Led_Time_Display` lights, per digit value: 1 at 2, 4; 7 at 0, 2, 4; 0 at all but 12; 2 at 0, 2,
  6, 8, 12; 4 at 2, 4, 10, 12. So a = 0, b = 2, c = 4, d = 6, e = 8, f = 10, g = 12. Its digits,
  hours then minutes, take bits 0x80, 0x40, 0x20, 0x10, left to right. The owner's map agrees.
- Icons take bit 3 (`0x08`). `mesonvfd_hdmi_on` and `mesonvfd_cvbs_on` light 10 and 12, as the owner
  found. `usb_led_switch` and `card_led_switch` light 0 and 2 where the owner lit 4 and 6: stock's
  driver is the vendor's for any panel, its switches for icons this one may lack (Wi-Fi, Ethernet,
  app); the owner's lit-bit test is this panel's.

## 2026-11-26 — listing photos

- A seller's X98H photos (`image1.webp`–`image3.webp`): the ports as on the PCB, back DC, optical,
  HDMI, Ethernet, AV, USB 2.0, side USB 2.0, card, USB 2.0; Android 12 on the box.
- Its panel shows USB and CARD, Wi-Fi, a colon, APPS and Ethernet around the clock: stock's driver's
  icons (`usb`, `card`, `wlan`, `app`, `ethernet`), not the PR owner's HD and CVBS. The same PCB may
  carry two panel overlays.

## 2026-11-26 — the remote's keymap

- Stock's `system_a` `/system/usr/keylayout/customer_ir_fe01.kl`: 42 scancodes for NEC address
  `0xfe01` (address 0x01, its inverse 0xfe), power 64, as the vendor tree's wake list and the PR
  owner's capture. `sys_config`'s IR recovery codes 0x11, 0x19 and 0x4c are its home, back and menu.
- `rc-x98h` (`patches/linux-sunxi/0292`–`0293`, `checkpatch --strict` clean): the 27 buttons the
  layout names, as their labels read. The remote has 30 (the listing photo); APP, KD and the gear
  are among stock's F1–F11, MUSIC and EXPLORER, which one each is the remote's to show.
- The digits moved from `KEY_NUMERIC_0`–`9` to `KEY_0`–`9`, `docs/remote-keymap.md`'s canonical
  keys: the numeric codes sit above 255, which X11 does not carry.

## 2026-11-26 — the serial pads

- Three holes in the corner between the back USB-A and the side's first, labelled RX TX GND on the
  eMMC side, GND nearest the corner (owner). `board.md` had them beside the RJ45, read off the
  label's place in the photo.

## 2026-11-26 — the ID

- `x98h`, the owner's choice. "X98H" also names a gigabit-Ethernet box on another PCB, ophub's
  `x98h`; that board, if it comes, takes a qualified ID.

## 2026-11-27 — conversion checks

- `dt-validate` (6.18.65 bindings with `sunxi64.conf`'s binding patches) first reported 45 vendor
  pin groups by their vendor names. The 5.4 conf only counted `allwinner,pins` groups, so groups in
  the generic form were neither renamed nor dropped. `pin-group` now takes several properties; every
  other board's translation is unchanged.
- After that, `dt-validate` reports the board's compatible and the H616 SRAM sections, the same as
  the H313.
- `semdiff` against stock's tree, 596 lines: each explained by the conf, mainline's dtsi or
  `board.patch`.
- Checked every drop and every vendor property the conversions use up. One was lost without a report
  line: the Wi-Fi host wake, PG15 (also on the H313 and TX1). The `pwrseq` conversion now reports it
  as a question; no tree changes.
- Second `semdiff` against the PR owner's tree. One drop of ours was wrong: stock powers HDMI from
  ALDO1, which mainline calls `hvcc-supply`; the board patch now names it. His SDIO at 35 MHz, eMMC
  at 150 MHz with `cap-mmc-hw-reset`, PG bank at 3.3 V and SD detect pull-down are his own choices;
  ours follow stock (150 MHz, 100 MHz, 1.8 V, pull-up), and the H313 measured its PG bank at 1.8 V.

## 2026-11-27 — every drop audited

- Listed every enabled vendor node and property with the rule that decided it and that rule's
  reason, and each property a conversion did not read. Every reason held for the 5.4 kernel but one:
  the UHS drop's reason (no 1.8 V rail) was false for the Wi-Fi host, which has one. The outcome
  stands, as mainline's `sunxi-mmc` cannot tune SDR104; the 5.4 conf now says so, and the speed is a
  todo.

## Corrections, 2026-11-26 to 11-27 (from the retired steering file)

Each lesson is now in `docs/bring-up/`, `AGENTS.md`, a test or the tools; this is what happened.

- The recovery key was called absent because the 5.4 tree has none; it is in `sys_config.fex`. A
  per-board FEL-key setting was built and then undone. Found by the owner.
- `import.md` had no Allwinner layout; worked out from the images.
- `dtcx` only knew the 4.9 kernel's trees; unfixed, the tree would have had no CPU scaling, no USB
  power, the SD pins at 1.8 V and no HDMI audio.
- Our U-Boot would have run this DDR3 at LPDDR3's 1.2 V; found by comparing with the PR owner's
  tree.
- The board was called ready before `semdiff` against stock and `dt-validate`; found by the owner.
- A listing photo of a different model (X96H) was added and removed.
- The keymap's digits were `KEY_NUMERIC_*`, not the canonical `KEY_0`–`KEY_9`; one kernel rebuild.
- HDMI's 1.8 V supply was dropped though its own reason said to map it; found against the PR tree.
- Build steps passed through an unquoted zsh variable; two background builds failed.
- The pull request misread the PCB (`Y8927`), took the RJ45's transformer for the radio, and named
  neither the AIC8800D80 nor the AiP1628.
