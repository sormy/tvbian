# H96 Max RK3528 worklog

## 2026-11-07 — import from a stock image

- Source: BOXPUT's `H96 Max RK3528 20230630.1201.img`. Identity: H96's product page and Armbian
  forum #59122's board photos (`RK3528_DDR3_8X4_V12`), read by the human.
- Wrong turn: the image was first imported as the H96 Max M2's, from ophub #2404's recovery link,
  then taken for the M1's; the board was built as `h96max-m2` before the image was checked against
  any photo. It is neither: the M2's board carries an RTL8211F on `gmac1`, which this image does not
  describe.
- The image is this board's: its DDR init and kernel DTB are byte-identical to what #59122's owner
  carved from this board; their stock boot log prints the same DDR banner and brings up the 100 Mbit
  `gmac0`.
- The image: `RKFW` built 2023-06-30; an `LDR ` loader; an `RKAF` archive, model `H96_Max_RK3528`,
  GPT; `super.img` sparse, ext4 inside.
- The DDR init, V1.05 (`2eef4a672d`, 23/04/14), is rkbin's `rk3528_ddr_1056MHz_4BIT_PCB_v1.05.bin`
  byte for byte.
- The idblock: the loader's FlashHead, FlashData and FlashBoot, RC4 per 512 bytes, padded to 2 MiB.
  Whole-buffer RC4 also yields `RKNS`, with a wrong DDR init.
- The trees: the kernel's from `boot.img`'s `rk-kernel.dtb` (`rk3528-evb2-ddr3-v10`), U-Boot's from
  `uboot.img`'s FIT `fdt`. Both decompile with every cell named. `board.patch` is the `rk35xx`
  recipe; `uboot.patch` the M2 Plus's conversion, its board values checked against this stock tree.
- Stock's remote: six `ir_key` tables and `ffa90030_pwm.kl`; nothing marks the bundled one.
- The front LCD: `fd655_dev` on GPIO4 19 and 20; stock's log names clock and data the other way
  round. No driver packaged; jefflessard/tm16xx-display lists `fdhisi,fd655`.

## 2026-11-08 — the radio, a U-Boot fix, the release

- Bluetooth runs on `uart2`, as stock does: `bt_vendor.conf` sets `/dev/ttyS2`, AIC's library speaks
  H4 over it. Wi-Fi on SDIO. The R69-1's split and serdev node.
- The radio, from this board's stock boot log: AIC8800D80, `chip rev: 7`, `chip_sub_id=2`, the
  R69-1's. Radxa's driver picks the R69-1's firmware set for it. Radxa ships no U01 set;
  `firmware/aic8800/README.md` corrected.
- The calibration: this image's, the R69-1's stock and radxa's `aic_userconfig_8800d80.txt` apply
  the same values, AIC's template; they differ in key layout alone.
- The image lags the board's own stock: a 2023 radio driver and calibration against 2024's, over the
  same DTB and DDR init.
- `uboot.patch` fix: the console's `stdout-path` stayed on `uart2`, the radio's UART; set to UART0,
  the debug header, as stock's `fiq-debugger`.
- Renamed `h96max-rk3528`. Built: trees, loader, U-Boot, `tvb-h96max-rk3528`, the image. Read off
  the image: the idblock at sector 64, our U-Boot at 16384, `board.dtb` byte-identical,
  `board-{id,name,pcb}` right. `./build.sh test` passes.

## 2026-11-14 — every public "M2" source is this image

- d5stick's `01_dtbdump_rockchip,rk3528-evb2-ddr3-v10.dtb` (ophub #2404) is byte-identical to
  `factory_board.dtb`: carved from this image, not read off an M2.
- ophub's `android_tv_h96-max-m2_rk3528.tar.xz` holds this image (2,446,783,050 bytes) and a photo
  of a board's back; its `…_ota_rk3528-20230630.1201.zip` is the same build.
- The M2 itself, from #2404's stock dmesg: an RTL8211F at 1 Gbps on `gmac1`, an AIC8800 module.
  Importing it needs a tree read off an M2.

## 2026-11-17 — a next2 tree, built, never booted

- `next2/`: the mainline kernel's tree, translated from this factory tree with the M2 Plus's choices
  and this board's own ports: TVE, the analog codec, S/PDIF, USB 3, IR without a keymap (the bundled
  remote's `0xfd01` table is inferred, not pressed), the logic and GPU rails held at the factory's
  900 mV. Built and proven; the box is not here.

## 2026-11-19 — an owner's unit runs it

- An owner's 4 GB / 32 GB unit, by email: booted the image from a microSD, `tvb-install` to the
  eMMC, and it boots from there; `apt update && apt upgrade` ran. Writing the image to the eMMC
  directly did not work for them; how is asked. Their PCB marking is asked too.
- `BOARD_SUPPORT=tested_by_user`, 👤 in README; `board.md` marks the microSD boot and the eMMC
  install ✅ by that report.

## 2026-11-22 — the front panel, blind

- The factory's `fd655_dev` drives the panel on GPIO4 C3 (clock) and C4 (data). The owner reads its
  symbols: wifi, network, colon, pause, play, USB, timer.
- tm16xx-display's `devices/h96-max.dtso` and `rk3566-h96-max-v56.dtso` carry one map with those
  seven symbols: an FD6551 at `0x24`, digits on grids 4 to 1, segments `3 1 2 6 4 5 0`, the symbols
  on grid 0. The vendor tree's patch adds the bus and disables `fd655_dev`; on next2 the translation
  makes the bus from `fd655_dev`, and the patch puts the panel on it.
- No other enabled node holds the two pins: `i2c0m0`, `pwm0m0` and `pwm1m0` stay disabled; the PWM
  regulators use PWM2, 4 and 7. Untested on the box.
