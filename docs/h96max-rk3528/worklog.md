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
