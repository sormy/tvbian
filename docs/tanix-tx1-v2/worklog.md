# Tanix TX1 V2 worklog

## 2026-10-23

- Kind: family (Allwinner, new to the repo). Order: sections 0, 10, 1–8, 11.
- Photos, partial: the shop listing, not the label. "Tx1 Mini", Allwinner H313, 2 GB RAM, 16 GB
  eMMC, 2.4 GHz Wi-Fi; no brand named. Label photo still owed.
- The name searched: "Tanix TX1" names at least two PCBs:
  - `CS_H313_TX1_EMCP_V1.1`, 2023-09-21, SCI S9082H Wi-Fi: mainline Linux
    `sun50i-h313-tanix-tx1.dts`, mainline U-Boot `tanix_tx1` (2024-04); eMMC HS200 left off there.
  - `QHZIW_H313_TX1_EMCP_V20`: a "6031" Wi-Fi chip (Armbian forum topic 56895).
  - Neither has an SD slot or Ethernet: FEL (the button inside the AV jack, USB-A to USB-A) is the
    install route.
- Brand confirmed against tanixtvbox.com's TX1 page: H313, Mali-G31, 1/2 GB + 8/16 GB eMCP, 5 V/2 A,
  one USB 2.0 host, no card reader, no LAN, no SPDIF, 802.11b/g/n, blue power LED. Fits both PCBs.
  The shop listing claims several USB ports: count them on the box.
- Silkscreen `QHZIW_H313_TX1_EMCP_V2.0`, `DATE:2024-03-21`: the second PCB, not mainline's.
  Mainline's TX1 tree and U-Boot are hints only; the tree comes from the stock dump. Wi-Fi expected
  the "6031": a chip bring-up, section 9.
- ID proposed: `tanix-tx1-v2`. Waits on the human's confirmation.
- Host: `adb`, `tio` present; no `sunxi-fel`.
- PCB photos: `board1.jpg` (top), `board2.jpg` (bottom), metadata stripped. Read off them:
  - Ports: DC 5 V barrel, HDMI, 3.5 mm AV, one USB-A. One USB, as Tanix says; the listing is wrong.
  - SoC, eMCP and Wi-Fi under the heat sink and the bottom thermal pad: markings not visible. A
    stamped-metal antenna at the top's lower right, a PCB-trace antenna on the bottom's left.
  - IR receiver: three through-holes at the bottom's lower right, its body at the top's lower left.
  - Two LED footprints at the top's bottom edge, centre.
  - A QFN beside three `1R0` inductors on the bottom: likely the PMIC or DC-DC; marking unreadable.
  - Serial: four through-holes on the bottom's right edge, silkscreened top to bottom `VCC`, `RX`,
    `TX`, `GND`. No pin hunt needed (section 2's procedure assumes unmarked pads).
- Doc gap: `docs/bring-up.md` section 2 gives the console baud for Rockchip and Amlogic only.
  Allwinner's BROM and vendor U-Boot are expected at 115200; to confirm on the stock boot log, then
  add it.
- The FEL tool: `tools/sunxi-fel/build.sh`, sunxi-tools pinned at `a08a24a` (2026-10-20, carries an
  H616 FEL fix); `./build.sh tool sunxi-fel` builds natively on macOS arm64 against Homebrew's
  libusb, zlib and dtc's libfdt.
- FEL alone reaches only SRAM; reading the eMMC needs a payload with DRAM up: mainline U-Boot's
  `ums`. Mainline `tanix_tx1_defconfig` is the V1.1's: LPDDR3 timings from its factory boot0, an
  AXP313 on R_I2C with DCDC3 at 1.2 V. Unproven on V2.0 until its PMIC and boot0 DRAM parameters are
  read.
- The stock boot on serial at 115200 (`stock/tanix-tx1-v2/boot.log`), header as silkscreened. It
  ends at a `console:/ $` shell, uid `shell`.
  - boot0 `12a0e3cc`: PMU AXP1530 (mainline's AXP313), `DRAM_VCC` 1200 mV, LPDDR3 at 600 MHz, **1536
    MB** (sold as 2 GB), `para1 30fa`, `para2 6001000`, `tpr13 26061`; chip id `0x5c00`.
  - eMMC 15028 MB, 8-bit HS DDR52; `mmcblk0` 30777344 sectors.
  - BL31 `05d6c57` (2021-10-28), U-Boot 2018.05-g8ac4189, Linux 4.9.170; platform `sun50iw9`.
  - Same PMIC, rail voltage and DRAM type as mainline's V1.1 config.
- The SoC: `/proc/device-tree/compatible` `allwinner,h616 arm,sun50iw9p1`. The shell: Android 10
  `userdebug`, test-keys; `su 0` gives root on serial. Model property reads "Google".
- No network on stock. `usbc0` is host by default; reading `usbc0/usb_device` switches it to device
  (`otg_role` → `usb_device`), `adbd` up with `sys.usb.config=mtp,adb`. Reading `usb_host` switches
  it back: these sysfs reads have side effects.
- Doc gap: section 0 assumes `adb` over the network; a box with no Ethernet and no Wi-Fi set up
  reaches `adb` through serial root and the OTG port in device mode.
- Section 3 over serial: each file `su 0` → gzip → base64 on the console, SHA-256 checked on the
  host. 115200 baud moves a 1.25 MiB boot package in about two minutes.
  - Wi-Fi: AltoBeam ATBM6031-X, SDIO `007a:6011`, `atbm613x_wifi_sdio`; firmware `ATBM_*.bin` in
    `/vendor/etc/firmware`.
  - eMMC: Samsung `Q316BB`, manfid `0x15`, 05/2018.
  - boot0 at sector 16, 64 KiB, no second copy at 256; boot package at 24576 and 32800, identical,
    four items: `u-boot`, `monitor`, `dtbo`, `dtb`. The `dtb` is the factory tree.
  - The factory tree's `dram_para1`/`2` nodes are a DDR3 template; boot0's header (byte 56) holds
    what ran. Against mainline's V1.1: `CA_DRI` `0x0d0d` (V1.1 `0x1919`), `TPR6` `0x2fc08080`
    (`0x2fb08080`), `TPR11` `0x0f110e0f` (`0x0e0f0d0d`), `TPR12` `0x0f111011` (`0x11131213`);
    `DX_ODT`, `DX_DRI`, `ODT_EN`, `TPR10` the same. boot0's `tpr1` is `0x80000000`, left at
    mainline's 0: untested.
  - `mac_addr` comes from the unit (env's `mac=` is empty): vendor-assigned, redacted in `stock/`.
    The serial `snum` kept, as on the other boards. Raw dump in `backup/tanix-tx1-v2-serial-dump/`.
  - Stock `dmesg` starts at 6.6 s: not an early-boot baseline.
- FEL U-Boot, scratch: TF-A v2.14 `sun50i_h616` BL31; U-Boot v2026.10 `tanix_tx1_defconfig` with
  `usbotg` → `peripheral`, `USB_GADGET_DOWNLOAD`, `CMD_USB_MASS_STORAGE`, `DRAM_CLK=600` and the
  four V2.0 values. `CMD_USB_MASS_STORAGE` needs `USB_GADGET_DOWNLOAD`, or Kconfig drops it
  silently. The eMMC is U-Boot's `mmc 1`: `sunxi-u-boot.dtsi` aliases `mmc1 = &mmc2`.
- First FEL runs: `sunxi-fel version` → `soc=00001823(H616)`. Mainline SPL brings DRAM up on the
  V2.0 values, TF-A and U-Boot start, then U-Boot hangs after `DRAM: 2 GiB`: the 1536 MB part is
  sized 2048. `dram_dw_helpers.c` writes and reads back the top quarter to catch a 3/4 part; here it
  aliases lower memory and passes. U-Boot relocates into memory that is not there. Stopgap for the
  FEL payload: `SUNXI_DRAM_MAX_SIZE` → `0x60000000` (no prompt, so its Kconfig default). The
  detection needs an upstream fix.
- Capped at 1.5 GB, U-Boot reaches its prompt: `DRAM: 1.5 GiB`, `mmc@4022000: 1`, `mmc info` the
  `Q316BB`, 8-bit at 52 MHz, `0x1d5a000` sectors. The FEL script never runs: with `BOOTSTD`,
  `distro_bootcmd` is `bootflow scan`, which has no FEL target. `ums 0 mmc 1` typed on serial fails
  "Controller uninitialized": the MUSB glue is `UCLASS_USB_GADGET_GENERIC`, probed only with
  `DM_USB_GADGET`. Payload now: `DM_USB_GADGET`, `BOOTCOMMAND="ums 0 mmc 1"`, no script.
- Ports, by the human: HDMI, one USB-A, DC 5 V, AV with the FEL button behind it, one more button,
  IR, two LEDs. No Ethernet.
- `DM_USB_GADGET` is wrong for sunxi: `musb_register()` compiles out `MUSB_PERIPHERAL` with it and
  returns `-EINVAL` ("No USB device found"). Without it, only `usb_ether_init()` probes the MUSB at
  boot (`board/sunxi/board.c`); `USB_ETHER` defaults on for sunxi with `USB_MUSB_GADGET`, but
  `tanix_tx1_defconfig` had already written it unset. Payload: `USB_ETHER` on, `DM_USB_GADGET` off.
- Without a power cycle: `loady 0x4a000000` + `sz --ymodem` moves a 756 KB `u-boot.bin` in about 75
  s, CRC32 matching. `go` to it hangs at relocation with the caches on, and that build had no
  `dcache` command: `CMD_CACHE` added for next time.
- FEL backup running: `ums` enumerates as a 15.8 GB disk, exactly 30777344 sectors; macOS mounted
  `bootloader` and `Reserve0` (FAT) for about 30 s before `diskutil unmountDisk`. `/dev/rdiskN` is
  root's; `sudo` from `!` has no terminal, so an `osascript` askpass ran the `chown`. 12.6 MB/s.
- The FEL loader is now board data: `boards/tanix-tx1-v2/factory_boot0.bin` (moved from `stock/`),
  `uboot/tanix-tx1-fel.conf`, `uboot/build-fel.sh`, `./build.sh loader tanix-tx1-v2` →
  `fel_loader.bin`, byte-identical on rebuild. The DRAM type, clock, the nine values mainline's H616
  driver reads (`TPR1` is not among them), and the size (`para2` high half, MiB) come from boot0.
  The cap is `patches/u-boot/0004`, a prompt on `SUNXI_DRAM_MAX_SIZE`. Mainline ignores `dr_mode`
  for the sunxi MUSB, so the tree is mainline's untouched. `docs/allwinner-fel.md`.
- The kernel: mainline has the H616 (`sun50i-h313-tanix-tx1.dts` is the V1.1's) but, through 7.2.12,
  no H616 HDMI: no TCON TV, HDMI PHY or pipeline nodes, and no H616 Cedrus. The vendor's is
  Allwinner's 4.9 BSP. Chosen: `sunxi64`, kernel.org longterm (6.18.58), Armbian's
  `linux-sunxi64-current.config` (6.18) as the base, and Jernej Škrabec's H616 display series,
  `patches.drm/0001`–`0041` from Armbian `sunxi-6.18` at `fac57a0`: `patches/linux-sunxi/`. All 41
  apply on 6.18.58; the fragment pins `DRM_SUN8I_MIXER`, `TCON_TOP`, `DW_HDMI`, `DW_HDMI_CEC`.
  Cedrus (Armbian's `add-vpu-node` and `patches.media`) waits for the codec lines. Armbian carries
  no AltoBeam driver, in its patches or `drivers_network.sh`: the ATBM6031 is a chip bring-up.
- The backup: `backup/tanix-tx1-v2-stock.img.xz`, 15758000128 bytes raw (30777344 × 512) in 1253 s,
  raw SHA-256 `a8170c9c37e04d0ff1047aebcaa6c19ac64ea392f9640f920f25035f9e1607cf`. GPT, boot0, both
  boot package copies and `env` are byte-identical to what stock Android read over serial.
- macOS wrote to the box: `.fseventsd`, 2026-10-23 23:06, on `bootloader` (p1) and `Reserve0` (p16),
  the FAT partitions it mounted in the ~30 s before `diskutil unmountDisk`. On the eMMC and in the
  backup; nothing Android reads. Fix: `patches/u-boot/0005`, `ums -r` sets the LUNs' write-protect
  flag; the loader's default boot command exports read-only, a FEL-passed script (`ums 0 mmc 1`)
  writes. Rebuild waits for the kernel build: Apple `container` will not attach `tvb-work` to two
  VMs ("The storage device attachment is invalid").
- The backup round-trips: `xz -dc` hashes to the raw read's `a8170c9c…07cf`.
- The kernel builds locally: `./build.sh kernel kernel/sunxi64.conf` →
  `linux-image-6.18.58-tvb-sunxi64`, headers, metapackage; `bindeb-pkg` 735 s. Its
  `sun50i-h313-tanix-tx1.dtb` carries the display engine, both mixers, `hdmi@6000000`, the HDMI PHY
  and `tcon-top@6510000`, disabled: enabling them is the board tree's job (`0042`, left out, does it
  for other boards).
- The FEL loader rebuilt with `0005`: `bootcmd` exports read-only unless a FEL script is passed;
  byte-identical on rebuild.
- The committed read-only loader on the box: `/dev/disk16`, both FAT partitions mounted `read-only`;
  six windows (GPT, boot0, boot package, env, mid-disk 15388672, the last 2048) match the backup.
- The per-unit window: Allwinner secure storage at sector 12288 (6 MiB), 4 KiB items twice each: the
  key map at 12288/12296, `mac` at 12304/12312, `snum` at 12320/12328; nothing else up to 12335.
  Also on the eMMC before the boot package: a second boot0 at 512–639 (256 KiB), and `sdmmc_arg`,
  boot0's eMMC tuning, at 24504. The `mac` is the cmdline's `mac_addr`, an Ethernet address on a box
  with no Ethernet.
- Direction from the human: test the write capability, no full restore; the image installs over FEL,
  and installing from USB, with no SD slot, is a TODO.
- Bootloader and image layout: one U-Boot for both jobs. `bootcmd` runs distro boot from the eMMC;
  with `fel_booted`, the read-only `ums`, or a FEL-passed script. `uboot/build.sh` hands a board
  with `factory_boot0.bin` to `uboot/build-sunxi.sh`; `fel_loader.bin` is a copy. The image
  (`sunxi-h616` in `image/build.sh`): an MBR, U-Boot at sector 16 (to 1666, bounded by
  `preserve-sectors`), the rootfs at 32768, bootable. `board.dts`: mainline's TX1 plus `0042`'s TX1
  HDMI hunk; the V1.1's rails match stock V2.0's (`dtb.md`). `preserve-sectors` 12288-12799.
- First image: `tvbian-tanix-tx1-v2-trixie-2026-10-24.img.xz`, 129 MiB, rootfs 912 MiB, 973078528
  bytes raw.
- First install attempts wrote nothing. 1: `ums` ended, back to `=>`, while the unmounted disk sat
  idle ~1.5 min; the `chown`ed node was `r--r-----`, and `dd` was refused. 2: root's `dd` refused to
  open the disk: `ums -r` ran, so `fel_booted` was set and `fel_scriptaddr` was not: sunxi-fel's
  script address, written to the SPL header at `0x18`, never reached U-Boot. Now the FEL branch
  checks for the script's magic at `0x4fc00000` itself, and the write script wipes it first.
- Serial RX stopped echoing after the cable was reseated: TX from the box works, input does not.
- Reverted, the human's call: no read-only export. `0005`, the script check and the write script
  cost a U-Boot patch and a mode switch, and every write attempt failed on the switch. Over FEL the
  loader runs `ums 0 mmc 1`; macOS's `.fseventsd` on the FAT partitions is a documented trap.
- The write test: the image written over FEL `ums` around 12288-12799, 6.7 MB/s (967 MB in 145 s;
  reads 12.6). Read back: MBR + U-Boot, rootfs head and tail match the image; the secure storage
  matches the backup, untouched.
- First boot from the eMMC, serial attached, the OTG cable out: the SPL from `MMC2`
  (`DRAM: 2048 MiB`, its own size probe), TF-A, U-Boot (`DRAM: 1.5 GiB`),
  `/boot/extlinux/extlinux.conf` on `mmc 1:1`, kernel, initrd, `/usr/lib/tvb/board.dtb`;
  `Machine model: Tanix TX1 V2.0`, 393216 pages; root `mmcblk1p1` re-mounted r/w;
  `TVBian (Debian GNU/Linux 13) tanix-tx1-v2 ttyS0` and its login. The second "Booting Linux" is the
  console's replay once earlycon hands over, not a reset.
- `systemd: Failed to set watchdog hardware timeout to 1min 20s: Invalid argument`: the H616's
  watchdog cannot hold that. Root growth not yet seen in the log; it needs a shell.
- Armbian lists the Tanix TX6s (two), the TX6 and the X96Q (H313, LPDDR3); no TX1 of either PCB.
- Wi-Fi driver found: `github.com/gtxaspec/atbm-wifi`, AltoBeam's vendor driver (GPL-2.0, on
  `cw1200`; pushed 2026-10-06), and `github.com/NoNamedCat/armbian-tanix-tx1-6031` (pushed
  2026-10-16, no licence file): a 5.8 MB patch on it for the 603x over SDIO on 6.18,
  `atbm6031_fw.bin` and `firmware_sdio.bin`, and a 6031 tree with reset PG18 and the 32 kHz clock on
  PG10. It reports Wi-Fi working on this PCB revision. Not yet built here.
- Wi-Fi packaged. NoNamedCat's 5.8 MB patch on `gtxaspec/atbm-wifi` `380838e` is 214 added and 63
  removed lines in 13 files; the rest is CRLF and whitespace churn. Rebuilt line by line keeping the
  base's bytes: `patches/atbm6031/0001`, 22 KB. On top, ours: AltoBeam SDIO IDs only (the port
  matched `SDIO_ANY_ID` twice); build paths (`/tmp/wifi-test` hardcoded; `$(srctree)/$(src)` breaks
  from 6.13, `$(abspath $(src))` holds); `<asm/unaligned.h>` forwarded, bridging off (`net/ipx.h`).
  `MAKE_ARGS='PWD=$(src) -k'`: its Makefile reads `.config` from `$(PWD)`. Result: `atbm6031.ko`,
  aliases `sdio:…v007Ad6011`, `6031`, `6032` only; `wifi_bt_comb` defaults 0.
- Firmware: none of the stock `ATBM_*.bin` sits in the stock module, so the stock image is not
  recoverable as a file; `tvb-firmware-atbm6031` ships the port's `atbm6031_fw.bin` (Ares_AX,
  2023-07-05).
- The tree's Wi-Fi: the factory sets a 1.8 V bias on port C only and its SDIO node carries
  `sunxi-dis-signal-vol-sw`: port G runs 3.3 V. `mmc1` `vqmmc` and `vcc-pg-supply` on DLDO1;
  `post-power-on-delay-ms = <200>` as the port has it. PG19 `chip_en`, driven by stock, left alone.
- The trees were not done the repo's way: `board.dts` was mainline's V1.1 tree edited by hand, and
  U-Boot ran mainline's V1.1 tree untouched; no `board.patch`, no `uboot.patch`. Mainline's
  `max-frequency = <100000000>` on the eMMC, against the factory's 50 MHz, is the kind of value that
  slips in: the boot with `mmc-ddr-1_8v` at it hung on
  `sunxi-mmc 4022000.mmc: data error, sending stop command`
  (`backup/tanix-tx1-v2-boot-wifi-ddr.log`). Redone from the factory blob.
- Bases: `kernel-h616-vendor-4.9`, Allwinner's own 4.9 BSP as `Allwinner-Homlet/H6-BSP4.9-linux`
  publishes it (the H6's; Allwinner publishes no H616 one), whose `sun50iw9` tree includes only
  generic dt-bindings; `kernel-h616-mainline-6.18`, `uboot-h616-mainline-2026.10`. The BSP's gpio
  cells are bank, pin, function, pull, drive, data: no `gpio-flags` renderer. `factory_uboot.dtb` is
  the boot package's `dtb`, the one the vendor U-Boot and kernel share. Both decompile with their
  proofs: `factory_board.dts` 5523 lines, `factory_uboot.dts` 5913.
- The eMMC failure, the whole of it (the human's serial capture): after `send stop command failed`,
  `kworker/0:1H` blocks in `mmc_blk_mq_rw_recovery` → `__mmc_send_status`; at 120 s `khungtaskd`
  panics (`hung_task: blocked tasks`), and the box stays down: nothing reboots on panic. Armbian's
  `sunxi64` config panics on a hung task; to revisit with `PANIC_TIMEOUT`.
- The stock U-Boot has no tree of its own: no FDT header in its 1 MB binary; the boot package's one
  `dtb` is its control tree (its banner's `Model: sun50iw9` is that blob's), and the kernel gets the
  same blob after U-Boot's `update dts`. `factory_uboot.dtb` is that blob, the same as
  `factory_board.dtb`.
- `board.dts` is the factory tree edited onto mainline by hand, `board.patch` its diff (3 hunks,
  4763 lines out, 934 in: the vendor's clock nodes, `sys_config` records and absent hardware go).
  `./build.sh board-dtb` regenerates it byte-identically. Caught on the way: the vendor's
  `allwinner,drive = <0xffffffff>` ("leave") reads in mainline's legacy binding as (n + 1) × 10 mA,
  which wraps to 0 and would fail the console's pin group.
- `dtcx`: a GIC proxy counts as the GIC; a gpio specifier with no flags renders decimal after its
  reference; all ones stays hex; `refargs`, a reference and its numeric arguments.
- One tree in stock, checked: the `boot` partition (Android boot image v2) holds no FDT; the
  kernel's `/sys/firmware/fdt` (`stock/…/board-runtime.dtb`) is the boot package's `dtb` with 67
  lines U-Boot writes: `bootargs`, the initrd and its `/memreserve/`, `memory` at 1.5 GiB (the
  blob's is 512 MiB), boot0's DRAM parameters, the boot logo's framebuffer, the eMMC tuning
  (`sdc_tm4_*`); no node added or removed. U-Boot reads the same blob: its
  `get sdc2 sdc_dis_host_caps 0x100` is `card2_boot_para`'s, and its binary carries the property
  names it looks up.
- One tree for both stages, as stock: `BOARD_UBOOT_DTB=board` names the board's tree as U-Boot's
  control tree (default `uboot`, the Rockchip boards' `uboot.dts`); `factory_uboot.*` and the U-Boot
  base dropped. `build-sunxi.sh` places it as `allwinner/tvb-<board>` and sets `OF_LIST` too: binman
  packs `OF_LIST`'s trees, which `defconfig` had filled with the V1.1's ("default-dt entry argument
  … not found in fdt list"). The SD controller stays in the tree, off: `sunxi-u-boot.dtsi` aliases
  `mmc0 = &mmc0` and the eMMC as `mmc1`. U-Boot's packed tree: `Tanix TX1 V2.0`, eMMC 50 MHz,
  `mmc-ddr-1_8v`, no hardware reset. Every binding and header the port uses is in U-Boot's
  `dts/upstream`.

## 2026-10-24

- WPA3: NetworkManager's WPA2/WPA3 transition profile made wpa_supplicant 2.10 authenticate with
  SAE, and cfg80211 returned `-EINVAL` before the driver: the driver declares no
  `NL80211_FEATURE_SAE` without its own `CONFIG_ATBM_FUNC_SAE_AUTHEN`, off in its `.config`.
  `patches/atbm6031/0005` turns it on; joined over WPA3.
- The factory-port `board.dtb` installed over ssh (the previous one kept as
  `/usr/lib/tvb/board.dtb.known-good`): eMMC DDR52 at 50 MHz, Wi-Fi up, cpufreq 480–1320 MHz.
- A WARN at Wi-Fi bring-up, `netdevice: wlan0: Incorrect netdev->dev_addr` in `dev_addr_check`: the
  driver's own mac80211 `memcpy`s into `dev_addr`, leaving 5.17's shadow copy zero.
  `patches/atbm6031/0006` sets it through `eth_hw_addr_set`.
- The eMMC hang again, on the factory-port tree, ~2 min after login: `mmc_blk_mq_rw_recovery` →
  `__mmc_send_status` never completes, `khungtaskd` panics at 120 s, the box stays down. `sunxi-mmc`
  adds both DDR capabilities itself on a new-timings host (all but the H5's eMMC), so `mmc-ddr-1_8v`
  against `mmc-ddr-3_3v` changes nothing: every tree here ran DDR52, and the 23rd's reading of the
  first hang as the 100 MHz cap's is unfounded. Cause open; stock tunes the eMMC per unit
  (`sdc_tm4_*` in its runtime tree), mainline runs fixed delays.
- Nothing recovered it: `BOOTPARAM_HUNG_TASK_PANIC` (Armbian's `sunxi64` config) with no panic
  timeout, and no watchdog: `sunxi_wdt` gives its 16 s hardware limit as `max_timeout`, so systemd's
  `RuntimeWatchdogSec=80` failed
  (`Failed to set watchdog hardware timeout to 1min 20s: Invalid argument`).
  `kernel/sunxi64.fragment` drops the hung-task panic; `patches/linux-sunxi/0042` gives the 16 s as
  `max_hw_heartbeat_ms`, as `meson_gxbb_wdt` does, and the core pings in between.
- HDMI, by eye on the TV: the panel's native 2K at 60 Hz, no artifacts; the console in 8x16 (the
  kernel on the box predates the `TER16x32` fragment).
- The old tree swapped back by `e2cp` over FEL's `ums` (the loader then exposed the disk read-only:
  built with `ums -r`; `ums 0 mmc 1` typed at its prompt made it writable). It booted clean once,
  then logged `sunxi-mmc 4022000.mmc: data error, sending stop command` on another boot: the Linux
  eMMC errors are not the factory port's alone. After that boot, ssh authenticated and stalled, and
  the serial `login` echoed and never asked for the password.
- The FEL loader now starts fastboot (writes) and offers DFU (reads), no host disk: `head` (sectors
  0–12287) and `1:1` by fastboot, `head`, `rootfs`, `emmc` by DFU.
  `fastboot getvar version-bootloader` answers over FEL. On our tree that U-Boot cannot reach the
  eMMC: `Card did not respond to voltage select! : -110`. A warm reset into the eMMC's U-Boot on
  mainline's V1.1 tree, power never cut, read the eMMC and booted: the card was not wedged; our tree
  breaks U-Boot's eMMC init. Serial log
  `backup/tanix-tx1-v2-serial/tanix-tx1-v2-20261024-110957.log`, 11:18–11:20.
- Why our tree's U-Boot missed the eMMC: U-Boot's sunxi pinctrl reads only the generic `pins`,
  `groups` or `pinmux`; a group carrying the legacy `allwinner,*` names is skipped without an error
  (`pinctrl_generic_get_subnode_type` returns `PST_NONE`). From the eMMC the SPL has muxed PC0–PC16
  already, which hid it; over FEL nothing does. The seven groups now use `pins`, `function`,
  `drive-strength` ((n + 1) × 10 mA, as Linux reads the legacy drive) and `bias-*`. Loaded over FEL,
  the boot U-Boot on our tree read the eMMC and started the kernel (11:33:58–11:34:13).
- U-Boot builds by variant: `./build.sh uboot <board> [boot|loader]`. The FEL loader is the `loader`
  variant, on the defconfig's tree: a board tree can no longer take the eMMC away.
- Linux, old tree on the disk, the hang without any `data error`: writeback to `mmcblk1` blocked,
  `blk_mq_timeout_work` waiting, `mmc_blk_mq_rw_recovery` → `__mmc_send_status` never completing;
  `sshd`, `jbd2` and `systemd-timesyncd` blocked behind it; hung-task panic at 11:24:04. Logins
  stall because they write.
- Testing trees from RAM over FEL: U-Boot 2026.10 boots through bootstd
  (`Scanning mmc 1:1... Found /boot/extlinux/extlinux.conf`), which ignores the script `sunxi-fel`
  hands it. The first two "tests" (a 25 MHz cap at 11:37, the drive-phase kernel at 11:47) booted
  the disk's kernel and old tree: not tests. The runner now stops autoboot over serial, types
  `source 0x43100000`, and fails unless the script's own line is in the log.
- Patch `0043`: Allwinner's driver (orangepi `linux-orangepi` `orange-pi-4.9-sun50iw9`,
  `sunxi-mmc-v4p5x.c`) drives the eMMC command line at 180° always and the data lines at 180° in
  DDR; mainline never writes the drive delay register. Stock's sample delay for DDR52 at 50 MHz is
  `0x14` (`sdc_tm4_sm2_freq0 = <0xff1414ff>`), mainline's 0. The hangs follow writes; reads
  (U-Boot's 1.5 GB, every boot's kernel, initrd and rootfs) do not hang.
- `0043` from RAM over FEL, our tree, 11:53: `Watchdog running with a hardware timeout of 1min 20s`
  (`0042` ✅), the `TER16x32` console (✅, by eye), login, then ~7 GB of writes without an error: 13
  × 500 MB direct sequential at 67.5–69.0 MB/s, 10 × 20000 4 KiB writes with fsync at ~37 MB/s;
  `actual clock: 50000000 Hz`, DDR52. Then reading the eMMC controller's registers through
  `/dev/mem` from Python (11:56:40) never returned, and from ~11:57:05 the eMMC hang again
  (`mmc_wait_for_cmd`, `jbd2` blocked). Not counted for or against `0043`: the poke touched the
  controller. Never poke the controller's registers from user space on a box under test.
- `0043` from RAM again, 12:37: `data error, sending stop command` 5 s after the kernel started,
  `send stop command failed`, the hang, then `hung_task_panic=1 panic=10` rebooted it (12:41:49
  `Rebooting in 10 seconds..`, 12:42:00 `Trying to boot from MMC2`): panic-reboot ✅. The drive
  phase alone is not the fix; the 7 GB clean boot was one good boot of an intermittent fault.
- `0044`: the sample delay from the tree, `allwinner,sample-delay`, written with the enable bit
  where mainline writes 0. Stock's for DDR52 at 50 MHz is 20 (0x14). After every write the card
  answers with a CRC status the host samples, so a write depends on the sample point too.
- The serial logger now starts a file per boot, at the SPL's banner.
- `0043` + `0044`, `allwinner,sample-delay = <20>`, from RAM, 13:00: script line logged, then 10 ×
  (500 MB direct at 67.4–69.6 MB/s + 20000 × 4 KiB fsync at ~37 MB/s), `data errors: 0`. The
  property reached the kernel: `/proc/device-tree/soc/mmc@4022000/allwinner,sample-delay` reads
  `00 00 00 14`.
- Installed over ssh: the kernel with `0042`–`0044` and `TER16x32`, `atbm6031` with `0006`, and the
  board package whose tree carries the generic pins and `allwinner,sample-delay = <20>`. For the
  count only, `/etc/u-boot-menu/conf.d/zz-test.conf` adds `hung_task_panic=1 panic=10` (later conf.d
  drop-ins override `/etc/default/u-boot`; `u-boot-update` adds `root=` itself).
- The count, from the eMMC with the installed kernel and tree: 5 reboots, each checked for
  `allwinner,sample-delay = 20` in `/proc/device-tree` and `Watchdog running` in the journal, then
  10 × (500 MB direct + 20000 × 4 KiB fsync): 67.3–70.8 MB/s, 0 data errors, 0 panics in every
  boot's log (`backup/tanix-tx1-v2-serial/tanix-tx1-v2-20261024-1306…1315*.log`). With the RAM boot
  at 12:58, 6 of 6. The test command line removed after.
- Wi-Fi on `0006`: no `Incorrect netdev->dev_addr`, no `cut here`; joined over WPA3.
- The ramoops region: with `CONFIG_PSTORE_RAM=y` and a `ramoops@7e000000` node, `map` or `no-map`,
  the kernel oopses right after `ramoops: using 0x100000@0x7e000000, ecc: 0` (`keep_bootcon`,
  14:39:04: `Internal error: Oops - Undefined instruction: 0000000002000000 [#1] SMP`), and the oops
  printout dies after `Modules linked in:`. Without the node the same kernel boots (`fdt rm` at
  U-Boot's prompt, 14:47). The node is out of the tree; pstore stays built in. Cause open.
- Recovery without FEL or `sudo`: stop U-Boot over serial, load the disk's kernel and tree, edit the
  tree with `fdt rm`, `booti`.
- Reinstalling `linux-image` alone left `modules.dep` without the out-of-tree `atbm6031`: no `wlan0`
  until `depmod -a`. Installing it with `tvb-atbm6031-modules` in one `dpkg -i` keeps the index
  whole.
- The aligned kernel installed with the ramoops-free tree; it boots unassisted from the eMMC:
  `Watchdog running`, `kernel.panic` 10, no data error, Wi-Fi up (14:54).
- The button: `BOARD_UBOOT_KEY=PH9` (stock's `recovery_key`, held 2 s for Android recovery). Held at
  power-on, our U-Boot boots a USB stick first, else u-boot-menu's second entry (the previous
  kernel), via `pxe_label_override`; a label a menu lacks is reported and its first entry boots.
  `gpio input` returns the pin's value, 0 when the active-low button is held.
- Our U-Boot written to the eMMC over ssh: sectors 16–12287 saved first
  (`backup/tanix-tx1-v2-uboot-area-before.bin`), `dd` at sector 16, read back equal
  (`addc4a6734d40d4b`). It boots unassisted: `Model: Tanix TX1 V2.0` (15:11:50), kernel, login.
- The RAM: memory stress past ~256 MB hard-locked the box (16 s, then the watchdog's reset); CPU
  stress alone passed 2 min at up to 1320 MHz and throttled to 1008 MHz past the 70 °C trip ✅.
  Stock: boot0 `Actual DRAM SIZE =1536 M`, its kernel maps `40000000-9fffffff : System RAM`; its
  Android `/proc/meminfo` claims 2024052 kB, more than its own map holds. A public H616 box with
  this unit's `para1 = 30fa, para2 = 6001000, dram_tpr13 = 26061` logs
  `32bit,2 ranks training success!` and `1.5GB autoscan enable` (ophub/amlogic-s9xxx-armbian issue
  3569): two ranks, each 3/4 populated. Mainline maps each rank a full GiB with the chip select on
  top, so rank 0's top quarter is a hole our 1.5 GiB cap hands to Linux. `mtest` from the FEL
  loader: `0x50000000`– `0x60000000` 0 errors (15:59); `0x70000000`–`0x80000000`
  `Address bit stuck high @ 0x70004000`, reads 0, then U-Boot's own exception and reset
  (16:00:39–41).
- `patches/u-boot/0004` (new): with two ranks, the chip select goes under the two top row bits, so
  the missing quarter of each 3/4-populated rank sits above 1.5 GiB. The old `0004`, a build-time
  cap from boot0's `para2`, is gone. From the FEL loader (16:17): SPL `DRAM: 1536 MiB` by itself;
  `mtest` `0x70000000`–`0x80000000`, `0x80000000`–`0x90000000`, `0x90000000`–`0x9a000000` each
  `Tested 1 iteration(s) with 0 errors`.
- The route without `ums`, end to end, no `sudo`: DFU read of `head` (6 MiB in 1.8 s), the new
  U-Boot spliced at sector 16, `fastboot flash head` (0.9 s), DFU read-back identical. Booted from
  the eMMC: `DRAM: 1536 MiB`, `DRAM: 1.5 GiB`. The loader's `dfu_alt_info` and
  `fastboot_raw_partition_head` are set by its boot command, so they are missing at its prompt.
- Under Linux on it: `stress-ng --vm 2 --vm-bytes 90% --verify --cpu 2 -t 300`, up to 1212 MB used,
  `failed: 0`, where 1100 MB had locked the box in seconds. The CPU held 1200–1320 MHz at 68–72 °C.
- The loader sets `fastboot_raw_partition_head` and `dfu_alt_info` in its preboot, in place of the
  defconfig's `usb start`: a prompt has them, and fastboot no longer waits on USB host start.
- The PH9 boot selector (USB stick, else the previous kernel) removed from the build for now, kept
  as a design in `docs/todo/tanix-tx1-v2.md`. The eMMC's U-Boot (`4cbee47de736e8a8`) still has it.
- Wi-Fi throughput, `iperf3` against `plex` (wired, 192.168.1.96), 10 s TCP each way: up 6.91
  Mbit/s, down 14.2 Mbit/s, at -33 dBm with tx 135 Mbit/s (MCS 7, 40 MHz) and rx 19.5 Mbit/s (MCS
  2). The SDIO bus runs 50 MHz, 4 bits, SD high-speed, 3.3 V: about 200 Mbit/s raw, so the driver is
  the limit.
- Wi-Fi throughput, each step measured with `iperf3` against `plex` (wired), 10 s TCP, at -33 dBm:

  | Driver and firmware                                       | Up   | Down Mbit/s |
  | --------------------------------------------------------- | ---- | ----------- |
  | `0001`–`0006`, NoNamedCat's firmware (ver 17678, 4 bufs)  | 6.9  | 14.2        |
  | the same, stock `ATBM_lite_blecomb_sdio.bin` (ver 19897)  | 16.1 | 11.0        |
  | `0007` (no jiffy sleep in the TX buffer poll), NoNamedCat | 12.8 | 13.7        |
  | `0007`, stock firmware                                    | 20.7 | 15.1        |
  | `0007`, `0008` (bus released between polls), stock        | 24.7 | 17.2        |

  Before: ~23,000 SDIO host interrupts/s and 16 `irq_period:Miss` per 10 s; after `0008`, 0 misses.
  Dead ends: `ATBM_mercu_blecomb_sdio.bin` brings no `wlan0`; TX confirms on
  (`# CONFIG_ATBM_FUNC_ NOTXCONFIRM`) makes the driver exit, `[BH] Fatal error`. The chip is 2.4 GHz
  only (`Band 1`, `2GHZ` firmware); the driver advertises HT20/HT40, no HE.

- After the failed TX-confirm driver, `systemctl reboot` hung, and SysRq `b` ended in TF-A:
  `sysrq: Resetting`, then `PANIC at PC : 0x0000000040008000` (18:20:03), inside BL31. The box
  stayed there until power was cut.
- Wi-Fi, where the rest of the gap is (UDP, `iperf3` to `plex`, SDIO requests from the `mmc`
  tracepoints): upload, the box can only send 23–27 Mbit/s; each write fills all 6 firmware buffers
  (42 × 256 B), 354 writes/s, ~13 free-buffer polls (8 transfers each) between writes: the firmware
  takes ~2.8 ms per 6 frames, with no TX retries and a reported 135 Mbit/s rate. Download, up to 57
  Mbit/s with 32% loss: one frame per read (7 blocks) plus a 1-block read, ~10,800 requests/s; the
  access point's rate to us falls to MCS 1–2 under load and returns to MCS 7 idle. Not the cause:
  `stbc=0`, `sgi=0`, the `performance` governor (25.3 up, 18.0 down); SDIO interrupts (the host has
  `MMC_CAP_SDIO_IRQ`, `ksdioirqd` waits on it). Bar: the M20 on the same access point, 2.4 GHz, ~90
  Mbit/s TCP both ways. The chip is 1T1R 802.11n, SDIO 2.0, 50 MHz.
- Hardware decode: `patches/linux-sunxi/0045` (Cedrus, the H616 on the H6 variant) and `0046` (SRAM
  C1), Jernej Škrabec's as Armbian carries them; the tree gains `video-codec@1c0e000` (the factory's
  `ve@01c0e000`, SPI 93) and `ve_sram`. One-shot boot from `/boot/test/`:
  `cedrus 1c0e000.video-codec: Device registered as /dev/video0`. `patches/ffmpeg/` (Kwiboo's
  v4l2-request on trixie's 7.1.5): `Using V4L2 media driver cedrus (6.18.58) for S264`; 1080p30
  `testsrc2`, 300 frames, 300 video-engine interrupts each: H.264 112 fps, HEVC 203, MPEG-2 166, VP8
  164; `framemd5` identical to the software decode for H.264, HEVC and VP8; MPEG-2 70.8 dB PSNR
  (IDCT rounding, not bit-exact by spec).
- The stock driver, `atbm613x_wifi_sdio.ko`, carved from the backup's `super`/`vendor`: AltoBeam's
  newer 613x SDK (`HMAC_VER:3352`, ours 3174), loaded with `wifi_bt_comb=0`; its `atbm_HwGetChipFw`
  then picks `ATBM_lite_fw_sdio.bin`, the no-BLE image, for the 6031-X. It also uses a 488-byte SDIO
  block (ours 256) and NAPI with GRO on receive; its interrupt is in-band SDIO, as ours. The 6031-X
  is 2.4 GHz only (AltoBeam's ATBM6031 page; `ATBM_lite_*` hold no 5 GHz code); stock's driver lists
  5 GHz channels for the 6132 and skips them all.
- `ATBM_lite_fw_sdio.bin` (19040, 2023-12-06): `Input buffers: 29 x 1648 bytes`, against 6 on the
  BLE combo image; TCP 64.6 up, 61.8 down Mbit/s, the access point's rate to us held at MCS 5 under
  load. The repo's firmware is now this image.
- `patches/atbm6031/0009`, 488-byte SDIO blocks as stock (`set_block_size=488`): TCP 69.1 up, 70.0
  down Mbit/s, from 64.6 and 61.8.
- 4K decode: from CMA (64 MiB) every 4K stream fell back to software
  (`cedrus … dma alloc of size 13271040 failed`); with `iommus = <&iommu 3>`, as the factory's `ve`
  node, H.264 and HEVC at 3840 and 4096 wide decode with one interrupt per frame, PSNR `inf` against
  the software decode (bit exact). Past the hardware: VP8 and MPEG-2 at 3840 time out every frame
  (`frame processing timed out!`), HEVC at 7680 falls back, H.264 at 7680 "decodes"; after the
  timeouts the engine stays broken (later H.264 at ~5 dB PSNR) until a reboot. Cedrus clamps to
  4096×2304 for every codec.
- GRO on receive, as stock's NAPI path (`gro_cells` on the mac80211 interface, in place of
  `netif_rx`): TCP 69.6 up, 69.3 down, then 69.1 and 68.4 — no change; dropped. Signal -32 dBm, TX
  MCS 7 40 MHz. `wsm_write_mib fail !!! mibId=4132` at boot is `WSM_MIB_USE_MULTI_TX_CONF`, which
  the no-BLE firmware refuses.
- CPU with and without GRO, `/proc/stat` over a 15 s downlink: 20.8–21.7 % busy at 68.6 Mbit/s
  without, 17.8–25.4 % at 48–69 with — no saving either. This driver hands up one frame per SDIO
  read, so `gro_cells` finds nothing to merge; stock's gain comes from NAPI batching the whole
  bottom half.
- BLE's Wi-Fi penalty is memory, not airtime: the combo image loads a third segment, `fw_sram`
  (`CONFIG_ATBM_BLE_CODE_SRAM`), and reports 6 input buffers against 29; the driver only reads
  `numInpChBufs`. Its one coexistence control, `ATBM_BLE_COEXIST_START`/`STOP`, time-shares the air
  while BLE is active and cannot return the buffers.
- Decode limits, one engine interrupt per frame, PSNR against the software decode: MPEG-2 75–77 dB
  from 1920 up to 3840×2160 (15M and 20M); VP8 bit exact to 2048 wide (2048×1440 too), 48 dB at
  2176, 18–25 dB from 2304 — wrong pictures, no error — and every frame timed out at 3840. The
  earlier "MPEG-2 at 3840 times out" was the engine already wedged by HEVC at 7680.
- The wedge: VP8 at 3840 reads past its buffer, `Page fault for 0xf1fff000 (master 3, dir rd)`, the
  frame times out, Cedrus's watchdog resets the engine; later H.264 at 6–28 dB, `L2PG_INT=8` latched
  at `0x030f0184`. Not the cure: a full TLB flush; clearing `INT_CLR`; unbinding and rebinding
  Cedrus. The cure: pulsing master 3's bit in `IOMMU_RESET_REG` (`0x030f0010`) with the engine idle
  — H.264 bit exact again, no reboot. The IOMMU's fault handler does the same pulse, but while the
  engine still transfers.
- From boot, `Page fault for 0x9a500000 (master 0, dir rd)` every 16.7 ms: the IOMMU translates
  every master (`IOMMU_BYPASS_REG` 0), and the display engine, master 0 in the factory's `disp`, was
  not attached. `iommus = <&iommu 0>` on mixer0, as mainline's H6: no IOMMU interrupt at idle, HDMI
  connected; `sun4i-drm display-engine: late IOMMU probe at driver bind, something fishy here!` with
  a backtrace, the path mainline's H6 takes too.
- `patches/linux-sunxi/0047` exports `sun50i_iommu_reset_master()`, `0048` calls it from Cedrus's
  watchdog after the engine's reset. One-shot boot, then installed: after VP8 at 2560, 3840, 4096
  and 7680, HEVC, H.264 and MPEG-2 at 7680, ten frames each, H.264 decodes bit exact every time. VP8
  at 3840 and 4096 times out every frame: 60 timeouts, ffmpeg still running at 120 s.
- CEC: `cec-ctl --playback` claims logical address 4 at 1.0.0.0, from the TV's EDID; every message
  to the TV ends `Tx, Not Acknowledged (4), Max Retries`, and the topology holds only the box. The
  factory tree sets `hdmi_cec_support = <0>`.
- GPU: Panfrost on the Mali-G31, `shader_present=0x1`, 432 MHz: `glmark2-es2-drm --off-screen` score
  35 — `build` 5 FPS, `phong` 3, `texture` 101 — and `gpu sched timeout, js=0` on the first run. The
  CPU sits idle and the GPU finishes one job per frame, 230 ms each. DRAM is not the limit:
  `stress-ng --memrate` writes 2.87 GB/s.
- GPU, corrected: `glmark2-es2-drm` ignores `-s` and renders the whole 2256×1504 screen. Panfrost's
  `profiling` counters: the fragment engine busy 4.95 s in 5, 432 MHz from cycles over busy time,
  ~25 cycles a pixel in `build`. Not the cause: runtime PM (`control=on`), `PAN_MESA_DEBUG`
  `noafbc`, `linear`, `noidvs`, `nocrc`, the MBUS bandwidth limits (all cleared). Stock ran the GPU
  at 600 MHz (`pll_gpu 600000000`), DCDC1 960 mV; the factory's `operating-points` hold 504–600 MHz
  at 950 mV. Those as an OPP table: devfreq at 600 MHz by cycles, `build` 232 → 170 ms, `phong` 411
  → 307, `texture` 101 → 120 fps, `desktop` 20 → 26, no `sched timeout` (14 before); 65–67 °C.
- Audio: no sound card. HDMI audio on the H616 goes through its audio hub, which mainline 6.18 has
  no driver for. The analog codec has one, `sun4i-codec`, off in Armbian's defconfig; with
  `CONFIG_SND_SUN4I_CODEC=y`: `card 0: Codec [H616 Audio Codec]`, `speaker-test -t sine -f 440`
  plays at 48000 Hz with no error. Not yet heard.
- Three warm reboots in a row: up and `running` in ~20 s each, `/dev/video0` there, `hwclock -r`
  keeping time across them. The only error-level lines are the ATBM firmware's banner
  (`Input buffers: 29 x 1648 bytes`, `WSM firmware … ver: 19040`), printed at error level.
- HDMI audio: Armbian's AHUB port as `linux-sunxi/0049`, `0050`; the tree gains `ahub_dam_plat`,
  `ahub1_plat`, `ahub1_mach` (codec `&hdmi`, `#sound-dai-cells` on it) and pll-audio-hs/-4x by
  number, 17 and 20, which mainline's header leaves out. One-shot boot: `1 [HDMI ]: HDMI - HDMI`;
  `speaker-test -D plughw:1,0` plays at 48000 Hz, no error. Armbian's `ahub_dam_mach` fails
  (`can't create pcm ahub_dam-snd-soc-dummy-dai :-22`); dropped. The analog card still plays.
- IR: the receiver binds (`rc1`, `sunxi-ir`), PH10 on mux 3 with its pull-up as stock, `ir` at 8 MHz
  from osc24M; only `lirc` enabled and no keymap, so `evtest` showed nothing. PH10 as a plain input
  idles high: the receiver is powered. Stock's `supply = "vcc-pl"` names no regulator.
- HDMI audio heard on the TV, 440 Hz from `speaker-test -D plughw:1,0`; installed as the default
  tree. The card has no volume control (`ELD`, IEC958, channel map only); a WAV at half amplitude
  (`volume=0.5`) played through `aplay`: heard quieter on the TV.
- CEC, corrected: the display here is a BOE panel (EDID: BOE, model 135, 2019), a monitor, and
  monitors implement no CEC, so the unacknowledged messages say nothing about the box. PI2's mux 5
  is HDMI CEC; muxed to it in RAM: still `Not Acknowledged`. Stock leaves PI0–PI2 `io_disabled`.
- DDC/CI: `ddcutil --bus 1` on dw-hdmi's I2C adapter: `EOPNOTSUPP` — its master does only an address
  byte and one data byte, or an address then a read; a DDC/CI request is a longer write. The EDID
  reads through the HDMI block's own DDC lines, PI0/PI1 (mux 5) unused, so no GPIO bus to bit-bang
  as on the M20. ddcutil also reports the panel without DDC/CI.
- Wi-Fi throughput against the chip, not the M20: the M20's MT7668 runs two streams (MCS 13–15), the
  ATBM6031-X one. `iw`: TX MCS 7 at 40 MHz, 135 Mbit/s; one stream tops out at 150. TCP 69–70 Mbit/s
  is ~50 % of that, the usual share for 802.11n; SDIO at 50 MHz × 4 bits leaves headroom.
  Aggregation is short of room: 29 input buffers, `aggr token not enough` in the driver's log. No
  measured figure for the chip found from AltoBeam or elsewhere.
- GPU, full `glmark2-es2-drm` on screen at 2256×1504: `texture` 221–226, `bump` normals 91 and
  height 88, `effect2d` 70 — but `build` 6, `shading` 4, `bump` high-poly 2: the same rock, two
  triangles against thousands. Seen on screen: the rock bleeding into the previous scene's cat —
  frames left unfinished by `gpu sched timeout, js=0`, the 500 ms job limit. The cost follows the
  triangle count. Mesa 25.0.7's `pan_select_tiler_hierarchy_mask()` keeps the level covering the
  whole framebuffer; the G31 has 2 levels (`Tiler:0x00000209`), so at 2256 wide only the 1024- and
  2048-pixel bins: every 16×16 tile walks nearly every triangle.
- Mesa 25.0.7 built with a test override of the hierarchy mask, run from `/tmp` by
  `LD_LIBRARY_PATH`. Off-screen, `build` / `bump` high-poly / `terrain`: stock (`0xc0`) 6 / 2 / 2,
  23 timeouts; `0x81` (16 + 2048 px) 131 / 89 / 4; `0x03` 132 / 89 / 5; `0x06` 133 / 89 / 5; none
  timed out. Full default suite on screen, `0x81`: score 42 → 110, timeouts 61 → 0, `build` 6 → 249,
  `shading` 4 → 91–201, `ideas` 6 → 108, `shadow` 2 → 34, `terrain` 2 → 5, `refract` 2 → 9;
  `texture` 221 → 181 and `pulsar` 223 → 164, full-screen quads in 16-pixel bins. Clean on screen.
  Upstream `main` spreads the levels from a table, `0x82` for two.
- Full suite on screen with upstream `main`'s mask for two levels, `0x82` (32 + 2048 px): score 121
  against 110 for `0x81`, no timeouts, every scene equal or faster — `texture` 212–218, `pulsar`
  206, `build` 257–264, `ideas` 130. Upstream's choice ships, as a backport.
- Upstream's fix found: `548f652d101`, Eric R. Smith, 2025-04-23, first in Mesa 25.2.0 (25.1.0 lacks
  it). Backported onto 25.0.7 as `patches/mesa/0001`; built with no override, the full suite on
  screen scores 121, as `0x82` did, no timeouts, no scene apart by more than 10 %.
- `extras/mesa`: Debian's `mesa 25.0.7-2+deb13u1` rebuilt with `patches/mesa/0001`, 20 debs in 8
  minutes, `X-Tvb-Inputs` on `mesa-libgallium` (mesa regenerates `debian/control` from `control.in`,
  so the field goes in both). Installed over the box's five Mesa packages:
  `GL_VERSION … Mesa 25.0.7-2+deb13u1+tvb0~local`, full suite on screen 121, no timeouts.
- DDC/CI, dug in: `tcon_tv0` `GCTL=0x80000003`, bit 1 the vendor's `pad_sel` ("DDC analog", also
  what its CEC code demands) already set. EDID through `i2ctransfer -y 1 w1@0x50 0 r8`:
  `00 ff ff ff ff ff ff 00` as booted; with `pad_sel` cleared, `Resource temporarily unavailable`,
  with PI0/PI1 off and on mux 5 alike; restored, read again. The connector's DDC reaches only the
  PHY's pads, which only dw-hdmi's I2C master drives: one address and one data byte a transaction,
  where a DDC/CI request is one 4–7-byte write. The M20's route, `i2c-gpio` on its DDC pins, needs
  them on GPIO; here there is none.
- ramoops, corrected: the node oopsed at 14:39 on 2026-10-24, before the DRAM fix at 16:17, and
  `0x7e000000` lay in the range then broken (`Address bit stuck high @ 0x70004000`). The same node
  now: `ramoops: using 0x100000@0x7e000000`, no oops, by kexec then installed.
- Panic test, `echo c > /proc/sysrq-trigger`, `kernel.panic` 10: the box stayed dark until power was
  cut. With `kernel.panic` 0, the 16 s hardware watchdog reset it and `dmesg-ramoops-0` held the
  panic. TF-A v2.14's `sunxi_system_reset()` writes the shortest timeout without restarting the
  count; with Linux's watchdog running the count is already past it. Its sequence plus the reload
  (`(0xa57 << 1) | 1` to the control register), from userspace over `/dev/mem`: instant reset.
  `patches/tf-a/0001` adds the reload; U-Boot rebuilt and written at sector 16, read back identical,
  the old head in `backup/tanix-tx1-v2-head-before-tfa.bin`. Panic again: back on its own in ~51 s,
  `Kernel panic - not syncing: sysrq triggered crash` in `dmesg-ramoops-0`.
- Suspend: only `s2idle` (`/sys/power/mem_sleep`); `rtcwake -m freeze -s 10`: entry 178.4 s, exit
  190.5 s, the same boot id, `atbm_log … Device resume`, Wi-Fi reconnected; after: HDMI connected,
  H.264 bit exact, both cards, 60 Mbit/s.
- Codecs, one clip set (60 frames, `testsrc2`), `drm_prime`, fps from `-benchmark` rtime: H.264 142
  / 30, HEVC 163 / 33, HEVC Main10 139 / 29 (8-bit out, 56.6 dB against 10-bit software), MPEG-2 133
  / 34, VP8 125 at 1080p; VP9 45 / 14 with no engine interrupt — software. `/dev/video0` offers
  `MG2S`, `S264`, `S265`, `VP8F`.
- VP9's factory node, `vp9@01c00000`, `sunxi-google-vp9`, IOMMU master 2: mainline drives the H6's
  twin with `hantro` (`sun50i-h6-vpu-g2`, built in), but the H616 clock driver has no VP9 clock; the
  H6's registers, `0x6c0` and `0x6cc`, read 0 after a write, the decoder's registers 0, and the
  vendor clock driver (`clk-sun50iw9`) has no VP9 entry.
- Encoder probe, the engine held on by `power/control` `on` (opening `/dev/video0` does not power
  it; Cedrus does on streaming): `VE_MODE` `c0000007`, takes encoder mode `c00000c7`; at Bootlin's
  V3s offsets, the AVC encoder at VE + `0xb00` reads `+0x08` `0x1e`, `+0x1c` `0x260`, `+0x8c`
  `0xffffffff` from reset, its stream start latches `12345670`, its end `12345673` (inclusive,
  word-aligned); the ISP at VE + `0xa00` latches its output address. `VE_VERSION` (`0xf0`) reads 0.
- Crypto engine: `sun8i-ce` registers 10 algorithms in `/proc/crypto` (AES ECB/CBC, 3DES, SHA-224 to
  -512); `/dev/hwrng` is "sun8i Crypto Engine TRNG": 1 MiB holds all 256 byte values, 3914–4297
  each, and zlib grows it (1.0003).
- LibreELEC's Allwinner video series (LibreELEC.tv `96d9f0f`) on our tree, in a second build volume,
  `tvb-scratch`: `0409`–`0425` apply but for two hunks — `0411`'s H616 variant (fuzz) and its blank
  lines in the watchdog, dropped; `0406` is our `0045`. Kept as `linux-sunxi/0051`–`0066`. Booted by
  kexec: `/dev/video0` adds `VP9F`, `SVC1`, and `P010` and AFBC on CAPTURE.
- kexec with the tree from disk left 472 MB: U-Boot writes the memory size into the tree it boots.
  4K Main10 then ran out (`cedrus … dma alloc of size 40435712 failed`, the OOM killer). With the
  live tree, `/sys/firmware/fdt`: 1459 MB, and it decodes.
- ffmpeg 9.0.2, the newest release: LibreELEC's `v4l2-request` `0001`, `0002` and the M20's 11
  mem2mem patches apply together, no reject; as `patches/ffmpeg/` `0001`–`0013`. On Cedrus, PSNR
  against software: VP9 140 / 28 fps at 1080p / 2160p, identical; HEVC Main10 to `P010` 89 / 18,
  identical at 10 bits; VC-1 Advanced 304 at 720p, 64 at 1080i with B-frames, identical; WMV3 Main
  refused by the hwaccel, 33 fps in software. The M20's `research/ffmpeg-v4l2m2m/build.sh` now takes
  `patches/ffmpeg/` and is not rebuilt since.
- DI300: LibreELEC's `0426` builds after one fix, 6.18's `v4l2_m2m_buf_copy_metadata()` taking
  `copy_frame_flags` (`linux-sunxi/0068`); the node, LibreELEC's `0435`, at `0x01420000`, SPI 89,
  IOMMU master 1 — the factory tree has none. kexec with the tree's memory set from the live one
  (`fdtput … /memory@40000000 reg 0 40000000 0 60000000`):
  `sun50i-di300 … registered as /dev/video0`, Cedrus on `video1`. ffmpeg 9.0.2 with LibreELEC's
  `vf-deinterlace-v4l2m2m` (`ffmpeg/0014`): the 1080i VC-1 sample, 100 frames at 121 fps, 53 decoder
  and 51 deinterlacer interrupts; a moving `testsrc2` 1080i H.264 clip combs without it and is solid
  with it. An output `-ss` after the filter emits nothing.
- Jellyfin's 4K test clips, 40 Mbit/s, 4K@60, 300 frames, one interrupt a frame: H.264 31.9 fps;
  HEVC 8-bit 42.7, HEVC 10-bit 23.7 — linear `NV12`/`P010`, the hwaccel taking the driver's default.
  A test-only build forcing the capture format: tiled `ST12` 59.0 and 50.2; AFBC `AS12` 69.5, `AS01`
  68.4 — real time at 4K@60, the datasheet's figure. ffmpeg picks AFBC only when the driver's
  default is a format it does not know; it needs our kernel's headers to know AFBC at all.
- All installed, normal boot: `video0` the DI300, `video1` Cedrus; VP9, HEVC Main10 and VC-1
  identical against software, 50 deinterlacer jobs. The filter gave both frames of a pair the
  input's timestamp in a halved time base — a muxer warning a frame, an output `-ss` emitting
  nothing; `ffmpeg/0015` puts them in the output base: no warning, the seek works.
- TV encoder: the factory's `tv0`, `allwinner,sunxi-tv`, a TVE top at `0x06520000` and the encoder
  at `0x06524000`, clocks `tve_top`, `tve` from `pll-video1`; the vendor clock driver's `TVE_CFG`
  `0xbb0`, `TVE_GATE` `0xbbc` (gates 0–1, resets 16–17). Clocked by hand: the encoder reads
  `00000000 00010000 00000000 02014924 21f07c1f 00760020 00000016 0016020d 00f0011a`, `+0x10` the
  NTSC chroma frequency `sun4i_tv` writes; the top reads `80004200 0000023a 00000010` at `+0x28`.
- The display planes offer RGB only: the DE33 VI plane's format list leaves YUV out ("supported by
  HW but driver needs improvements"), scalers off. LibreELEC's display series, written for 7.2,
  carries the rest; on 6.18, with or without Armbian's `0001`–`0041` under it, 38–40 of its patches
  reject. On 7.2.12: 194 of 202 apply; the eight HDMI and framebuffer ones rebased, all 202 apply,
  the display drivers build clean. Ours on top apply: `0042`–`0044`, `0047`–`0050`. Its H616 display
  nodes use our tree's binding. `kernel/sunxi64-next.conf`, as `meson64-next`.

## 2026-10-25

- H.264 encoder: Bootlin's `cedrus/h264-encoding` (`4e9497947c56`) rebased onto `linux-sunxi/0068`
  with an H616 variant, kexec'd: decode unchanged, encode faults on its first job —
  `Page fault for 0x000000000000f000 (master 3, dir rd)`, frame timeout, 0 bytes. Bootlin writes the
  MV and deblocking addresses as 0; given buffers, the fault moved to `0x21c01000` and followed the
  picture size (`0x9000xxxx` at 640×480, `0x2000xxxx` at 720p).
- Wrong turn: the fault was not a missing buffer. A debug hook shifting chosen address registers
  right by 8 moved the fault each time to the next register's value `<< 8` (`0xfe880000 << 8` =
  `0x88000000`): every encoder address is in 256-byte units — stream, MB info, MV, deblocking, REF0,
  REC, subpixel. The ISP's input addresses are plain: shifted, they faulted at the shifted value.
  Sentinels written into unprogrammed registers during the job (`(0xa0 + i) << 16`) named the last
  read, `0xab000000`: `0xb9c`, a register Bootlin leaves alone.
- Buffer use measured with 0xa5-filled buffers and the last changed byte: MB info about 16 bytes a
  macroblock column (632 at 40, 3832 at 240); `0xb9c` one byte a macroblock row, even (30, 46, 68,
  136); MV never written (`WB_MV_INFO_DIS`); deblocking only past 2048 wide, 10752 bytes at 240
  columns.
- Encoded but decoded wrong: "top block unavailable" at macroblock 20 of 40, every size at half the
  width. Doubling the ISP `PIC_INFO` width changed nothing, byte for byte; doubling the scaler size
  `0xa2c` decoded clean — the H616 counts it in 8-pixel units. 4K then completed with no bytes until
  the mode register got `PIC_WIDTH_MORE_2048`; a VP9 decode had left `RAMPD` and bit 30 set in it.
- Wrong turn: PSNR of 12–26 dB came from the test, not the engine — the test appended to its
  bitstream file across runs, and ffmpeg's `psnr` filter paired the raw stream's frames by
  timestamp. Per-frame PSNR in Python on raw NV12: I 51.4, P 48.0 dB at 640×480; 51.0 / 47.7 at
  1080p; 51.6 / 47.9 at 2160p.
- Engine time, queue to dequeue, 12 frames: 1.2 ms at 640×480, 3.9 at 720p, 8.7 at 1080p (115 fps),
  30.2 at 2160p (33 fps); the datasheet gives 1080p@60 and 4K@25.
- ffmpeg `h264_v4l2m2m` hung at end of stream: no `ENCODER_CMD`, no EOS. With the mem2mem drain, 120
  1080p frames to MP4. "Overread VUI by 8 bits": Bootlin puts the headers with the engine's
  emulation prevention off and escapes nothing — `num_units_in_tick` = 1 put `00 00 00 08` raw and
  ended the SPS early, 16 of 68 size × rate pairs broken; the timing fields were also swapped. Both
  fixed, all 72 clean. 640×360 was coded as 368 lines, uncropped: the format was rounded up and the
  default crop taken from it.
- ffmpeg P-frames fell to 30–34 dB while the test tool's held 47: the reference lived in the picture
  buffer, and ffmpeg requeues the one it just dequeued. Two reference slots in the context: 46.5 dB.
  1366×768 from rawvideo sheared: ffmpeg copied at the frame's 1366 linesize into a 1376 stride
  (`ffmpeg/0016`); from `testsrc2`'s padded frames it was already right. A page-aligned 1366×768
  buffer faulted one byte past its end — the ISP reads past the chroma plane; a row of slack.
- `./build.sh kernel kernel/sunxi64.conf` with `linux-sunxi/0069`–`0082`: applies and builds;
  installed. ffmpeg PSNR against source, rawvideo in: 45.9 dB at 640×360, 46.1 at 1366×768, 46.5 at
  1080p, 47.1 at 2160p; decode unchanged — H.264, HEVC, VP8, VP9 identical, VC-1 Advanced identical.
- HEVC Main10 through ffmpeg to software frames fails on the installed kernel as on this one: ffmpeg
  takes the driver's `AS01` default and cannot transfer it. Not the encoder's doing.
- IR: `evtest` silent with the remote pressed — the receiver decoded fine, the tree named no keymap
  (`rc-empty`, only `lirc` enabled). With every protocol on: NEC, address 0x80, codes `0x8051` power
  … `0x800d` OK. The factory tree's `ir_addr_code9 = <0x7f80>` with power `0x51`; stock's layout in
  `super` (`key 81 POWER`, `key 13 DPAD_CENTER`, `key 83 HOME`) is mainline's `rc-tanix-tx3mini`
  code for code. The tree names it; `ir-remote.hwdb` moves Home to `KEY_HOMEPAGE`, ⌫ to
  `KEY_BACKSPACE` and drops Mouse, as the canonical keymap; `sunxi-ir` gets `/dev/input/ir-remote`;
  the shared power-key policy, as the other H313 box, so the remote's power key suspends instead of
  powering off for good.
- IR keys after a kexec: `rc_core: IR keymap rc-tanix-tx3mini not found`, then `rc-empty` — the
  driver is built in and probes at 2.9 s, before the rootfs carries the keymap module; udev's
  `rc_maps.cfg` matches the map the driver names, now `rc-empty`. The earlier keys came from a
  keymap loaded by hand. `IR_SUNXI=m` in the fragment. `linux-sunxi/0083` gives the receiver
  `power/wakeup` `enabled`. A kexec from the 472 MB boot with the tree from disk (the box lacks
  `fdtput`, so no memory fix) never came back: not on the network, no watchdog reset.
- The power cycle came up off the network: no answer at 192.168.1.245 or by name, no unknown host in
  a subnet sweep answering SSH. The kernel built with `IR_SUNXI=m` was installed without the
  `tvb-atbm6031-modules` built with it; the likely cause, unconfirmed until the console is read.
- `sunxi64-next` 7.2.12 builds, kernel and `atbm6031`. In the way, one at a time: the fragment's
  hung-task line (6.19 made it a count) and NTFS3 (7.2's NTFS_FS is the old driver); Armbian's audio
  hub on 7.2's API (`of_gpio.h`, the card's DAPM pointer, `snd_kcontrol_chip()`); `0044`'s
  sample-delay member and `0050`'s `#sound-dai-cells`, both already in LibreELEC's series; the AC200
  core and PHY both `ac200.ko`; `atbm6031` on 6.19's cfg80211 (`wireless_dev` in key and station
  ops) and `IEEE80211_MIN_ACTION_SIZE` taking a field. The step's own log,
  `build/out/logs/<kernel>/<step>.log`, names the error the console's tail hides.
- Off the network, read on serial: `wlan0` missing, `modprobe: FATAL: Module atbm6031 not found`,
  `modules.dep` without it — the lone `linux-image` reinstall's index. `depmod -a`: `wlan0` up at
  192.168.1.245. Not symbol versions. IR after a cold boot: `sunxi_cir` a module,
  `Registered IR keymap rc-tanix-tx3mini` at 11.9 s. `wlan0` `54:14:e9:d9:73:d1`, `addr_assign_type`
  0: the eFUSE address, the same lease every boot.
- Off the network, read on serial: `wlan0` missing, `modprobe: FATAL: Module atbm6031 not found`,
  `modules.dep` without it — the lone `linux-image` reinstall's index. `depmod -a`: `wlan0` up at
  192.168.1.245. Not symbol versions. IR after a cold boot: `sunxi_cir` a module,
  `Registered IR keymap rc-tanix-tx3mini` at 11.9 s. `wlan0` `54:14:e9:d9:73:d1`, `addr_assign_type`
  0: the eFUSE address, the same lease every boot.
- Encoder rate control, `0084`: 300 frames of 1080p `testsrc2`, `-b:v` 4M → 3988 kbit/s, 10M → 9882.
  1M overshot to 23.8 Mbit/s: a fixed-QP sweep, 60 frames, 1.5 Mbit/s at QP 45–47, then 23.8 from QP
  48 — QP plus the +4 chroma offset past 51, which the engine does not clip. The QP now stops at 51
  minus the chroma offset: 1M settles at 1754 kbit/s, the content's floor.
- HEVC Main10 to software frames failed by default: `0066` made AFBC (`AS01`) the 10-bit default and
  ffmpeg takes a default it knows. On 6.18 the planes cannot scan AFBC out anyway. `0085` puts P010
  first: ffmpeg logs `CAPTURE buffer format P010`, PSNR against software at 10 bits `inf` at 1080p
  and 2160p, no forcing build. AFBC stays on request for the display path on 7.2.
- 7.2 first boot, kexec, the 1.5 GiB tree: Wi-Fi, IR up; `cedrus: Failed to claim SRAM` and
  `failed to bind 6510000.tcon-top: -61`. 7.2's SRAM section is `allwinner,sun50i-h616-ve-sram`
  (6.18's `sram-c1`), and its TCON-TOP reads a second output, `tcon-top-tv1`: both added beside
  6.18's, Cedrus and the pipeline bind. Then master-0 faults at a physical address, about two a
  second: 7.2 maps display buffers through the `planes` node, 6.18 through `mixer0`. `iommus` on
  `planes` only: 7.2 clean, 6.18 1342 faults in 20 s. On both — one IOMMU group, every master in it:
  one fault at the hand-over on 7.2, none on a real 6.18 boot. Installed.
- The encoder series on 7.2: `0072`'s whole-file rewrites conflict, yet LibreELEC's 7.2 Cedrus
  differs from 6.18's by two lines (`kzalloc_obj()`, a two-argument `v4l2_m2m_buf_copy_metadata()`).
  Replayed with git, conflicts to the series, and `0086` for the call: `7.2/cedrus/`. Kexec on 7.2:
  decode against software `inf` for H.264, HEVC 4K, Main10 at 10 bits, VP9 4K, VC-1; encode at 4M
  3988 kbit/s, no decode errors.
- Image, the TX1's set only (board, base, keyring, `atbm6031` firmware, the Mesa extra, 6.18 through
  `0085`): `tvbian-tanix-tx1-v2-trixie-2026-10-25.img.xz`, 129 MiB, rootfs 932 MiB. The board
  package carries the IR map and `hwdb`, the power-key and s2idle policy, and the tree with both
  IOMMU nodes. Installing it from FEL is the human's.
- Bad frames: the timeouts known here are VP8 past the engine's width — wrong pictures from 2304, a
  2 s timeout a frame at 3840. `0086` advertises VP8 to 2048: at 3840
  `Failed setup for format drm_prime`, software decode, `inf` against software, no timeout; 2048 and
  1920 stay on Cedrus, bit exact.
- SysRq `b`: no TF-A panic any more; `sysrq: Resetting` at 13:59:35, U-Boot SPL at 14:00:46.
  `systemctl reboot` and `reboot -ff`: SPL within 0.6 s. TF-A v2.14's H616 map points
  `SUNXI_R_WDOG_BASE` at `0x030090a0`, the watchdog Linux drives — the register is right; the
  emergency path skips reboot notifiers and device shutdown, and recovers only by the watchdog.
- Emergency resets, timed on serial to the next boot: SysRq `b` pinned to CPU 0, to CPU 2, and plain
  at 21 s of uptime — each about 1 s; a forced panic 12 s (`kernel.panic` 10). The 71 s run did not
  come back; `Reset after a stuck driver` ✅.
- 7.2's planes, `drm_info`: five planes offering NV12, NV21, NV16, P010, YUYV, `YUV420_8BIT` and
  `YUV420_10BIT`, with four `ARM_AFBC` modifier entries; 6.18 offers no YUV format at all.
- IR keymap, final: the `hwdb` corrections never held — udev's `ir-keytable -a /etc/rc_maps.cfg`
  reloads `tanix_tx3mini.toml` when the receiver appears. `linux-sunxi/0088` adds `rc-tanix-tx1`:
  the TX3 mini's codes on the canonical keys (`KEY_HOMEPAGE`, `KEY_BACKSPACE`, `KEY_NEXTSONG`,
  `KEY_PREVIOUSSONG`, Mouse as `KEY_TOUCHPAD_TOGGLE`); `rc_maps.cfg` has no entry for it, so it
  stays. `hwdb` dropped. `ir-keytable -r`: 31 keys. A hand-copied `hwdb` no package owned had kept
  `0x8052` reserved until removed.
- 7.2 playback, GStreamer `v4l2slh265dec ! kmssink`: zero copy —
  `import_dmabuf … found KMS mem in DMABuf mem`, the same buffers round. `sync=false`: 30.0 fps at
  4K and at 1080p, none dropped, on a 2256x1504@60 mode — a flip every second vblank. `sync=true`:
  0.36 fps, nearly all dropped. Decode alone into `fakesink`: about 47 fps (the clip is 1800 frames;
  an earlier "7 fps" assumed 300).
- `kmssink skip-vsync=true`, `sync=false`: 35.5 fps, none dropped — `kmssink` waits a vblank after
  each blocking `drmModeSetPlane`, which already took one. `sync=true` still 0.5 fps: GStreamer's
  lateness handling, not the display. The 7.2 CRTC arms its event for the next vblank, as it should.
- HDMI 10-bit on 7.2: the monitor's EDID HDMI VSDB has DC_30bit and DC_36bit, and HDR static
  metadata. The connector offers `max bpc` (8–16), `Colorspace`, `HDR_OUTPUT_METADATA`; plane 35
  offers XR30, AR30, P010, Y210. `modetest -a`, XR30 on plane 35, `max bpc` 10: `VP_PR_CD` stays
  `0x40`, `TX_INVID0` `0x1` — 8-bit RGB out.
- Why 8-bit: `sun50i_fmt_is_10bit()` is true only for `MEDIA_BUS_FMT_UYYVYY10_0_5X30`, and the HDMI
  bridge takes only formats the engine validates — 10-bit is YUV 4:2:0, offered for modes a sink
  lists in 4:2:0, a TV's 4K. The monitor's 2256x1504 is RGB only.
- TVE, from Allwinner's H616 BSP (`orangepi-xunlong/linux-orangepi`, `orange-pi-5.4-sun50iw9`,
  `drivers/video/fbdev/sunxi/disp2/tv/de_tve_sun8iw11.c`, which the Makefile builds for sun50iw9):
  calibration lives in the top block's `0x028` [31:16], never in encoder `0x300`–`0x30c`; DAC0
  routed by top `0x020`; `0x02c` `0x23a` and `0x030` `0x10`, as the probe read them. PAL and NTSC
  tables, 216 MHz off PLL-VIDEO1 at 432 MHz, cable sense on `0x038`. Scope in the to-do.
- Composite, 7.2: `7.2/0089` adds `allwinner,sun50i-h616-tv-encoder` to `sun4i_tv` (top as a second
  register range, Allwinner's register tables, three clocks and two resets in bulk, cable sense on
  `0x038`). With TCON-TV1, the TCON-TOP's TV1 endpoints and the encoder node in a test tree: the
  pipeline binds, `card0-Composite-1` `disconnected`, HDMI `connected`. Top `0x020` 1, `0x028`
  `0x82d24200` — the efuse's 722 at `0x0300622c` [31:16] — `0x02c` `0x23a`, `0x030` `0x10`; encoder
  `0x030` `0x80000001`, `0x03c` `0x9999`. `tve0` 471 MHz off PLL-VIDEO0; with `assigned-clocks`
  PLL-VIDEO1 reached 432 MHz but `tve0` stayed on PLL-VIDEO0. HDMI's TCON is on PLL-VIDEO0 too.
- The encoder clock: the parent alone, assigned, took (`tve0` on PLL-VIDEO1); with a rate, the
  framework re-parented it to PLL-VIDEO0 — 216 MHz there needs PLL-VIDEO0 changed, HDMI holds it,
  and `tve0` stayed at 942/2. `linux-sunxi/0090`, `CLK_SET_RATE_NO_REPARENT` on `tve0`: 216 MHz off
  PLL-VIDEO1, HDMI's PLL-VIDEO0 untouched. A leading 0 in `assigned-clock-parents` dropped the list.
- Composite on 6.18: `0089` (`sun4i_tv`, LibreELEC's quirks with the H616 encoder) and `0091`
  (LibreELEC's `0209`, the H616 TCON-TOP, whose TV1 gate TCON-TV1 needs); 6.18's binding lacks
  `CLK_PLL_VIDEO1`, so the tree writes its index, 11, the same on both. Kexec, then a real boot:
  TCON-TV1 and `6524000.tv-encoder` bound, `Composite-1` `disconnected`, HDMI `connected`, `tve0`
  216 MHz off PLL-VIDEO1, no IOMMU fault. In the board tree.
- 7.2 on the final board tree, kexec: `Composite-1` `disconnected`, HDMI `connected`, `tve0` 216 MHz
  off PLL-VIDEO1, `rc-tanix-tx1` loaded, `cedrus-dec`, `cedrus-enc`, `sun50i-di300` present. One
  IOMMU read fault at the mixer's bind, `0xff7be000`, on 7.2 kexecs only, never on 6.18; likely: the
  old kernel's scanout IOVA, still fetched when the new IOMMU comes up. A cold boot starts from
  U-Boot's framebuffer, untranslated.
- IR, ⏪ ⏩ (`0x80bd`, `0x80bb`): the buttons are rewind and fast-forward, not track keys.
  `KEY_PREVIOUSSONG`/`KEY_NEXTSONG` give `XF86AudioPrev`/`Next`, Kodi's `SkipPrevious`/`SkipNext`;
  `KEY_REWIND`/`KEY_FASTFORWARD` give `XF86AudioRewind`/`Forward`, Kodi's `Rewind`/`FastForward`
  (xkeyboard-config `symbols/inet`, Kodi `LibInputKeyboard.cpp`, `keyboard.xml`). Upstream's
  `KEY_PREVIOUS`/`KEY_NEXT` have no keysym. `linux-sunxi/0088` changed.
- IR, 1/a (`0x8058`): kept mainline's `KEY_SUBTITLE`. It reaches Kodi as `XF86Subtitle`, key name
  `subtitle` (`XBMC_keytable.cpp`); `keyboard.xml` binds nothing to it, `remote.xml` binds it to
  `DialogSelectSubtitle`. No evdev code means a digits-or-letters toggle.
- IR, `evtest /dev/input/ir-remote`, pressed by hand on the 0088 keymap before ⏪ ⏩ changed: 30
  buttons, Power not pressed, each its own scancode and key, no `KEY_UNKNOWN`; held Blue repeats.
  `INPUT_PROP_POINTING_STICK` is rc-core's own, for its mouse emulation; `dw_hdmi`'s CEC input has
  it too. The canonical keymap gains ⏪ ⏩, 1/a and plain colour keys.
- IR, correction: `0x80bd`, `0x80bb` print ⏮ ⏭, not ⏪ ⏩; back to
  `KEY_PREVIOUSSONG`/`KEY_NEXTSONG`. In Kodi's video player `SkipNext` takes the next chapter, else
  the next scene, else the next item (`VideoPlayer.cpp`, `ACTION_NEXT_ITEM`); `Rewind`/`FastForward`
  set trick-play speed. Fullscreen video seeks on the D-pad: `StepBack`/`StepForward`,
  `ChapterOrBigStep…` (`keyboard.xml`).
- IR wake, pressed by hand on 6.18: the power key, `Power key pressed short`,
  `suspend entry (s2idle)` at 251.98 s; a second press, `suspend exit` at 257.74 s, delivered to
  logind at 257.744 s while the suspend job still ran (`sleep.target` stopped at 257.77 s): no
  second suspend. `rc1` `power/wakeup` `enabled`; `wakeup_count` stays 0, the driver reports no
  wakeup event.
- IR wake, logs: asleep 5.8 s by the wall clock (20:30:26.15–20:30:31.92); freeze 1 ms, no device
  error on suspend or resume, HDMI `connected`, no IOMMU fault. Wi-Fi, disconnected by
  NetworkManager for the sleep: the first scan after resume `CTRL-EVENT-SCAN-FAILED ret=-16`, the
  driver's `atbm_ieee80211_suspend can not process cfg cmd`; NetworkManager retried, lease at
  20:30:38.06, 6.1 s after wake. `aggr token not enough` runs before sleep too (37 before, 59
  after); `sunxi-musb does not have ULPI bus control register` only at suspend and resume. Not yet:
  a sleep of minutes.
- LEDs, seen by hand: blue running, red in `s2idle`, blue again on wake (`led-sleep`; triggers
  `none`, `power` 1 and `standby` 0 running). Powered off: not reported yet.
- BLE path, from the driver's source: `ATBM_BLE` depends on the 6012B, WIFI4 or 6132 options, not
  `ATBM603x`; `ATBM_BLE_WIFI_PLATFORM` adds `CONFIG_ATBM_BLE_CODE_SRAM` and `CONFIG_WIFI_BT_COMB`.
  The BlueZ glue, `CONFIG_ATBM_SUPPORT_BLUEZ` in `mac80211/ble.c` (`hci_recv_frame`), is set nowhere
  and calls `set_bit()` on `hdev->dev_flags`, a bitmap behind `hci_dev_set_flag()` today.
- BLE, `patches/atbm6031/0011`: the driver's own BlueZ glue built in, `wifi_bt_comb` picking at
  load. The SDIO branch set `loader_ble` from the eFuse alone (`6031-X UID … support BLE`), its
  `wifi_bt_comb` check commented out; now both. Three API breaks: `set_bit()` on `hdev->dev_flags`,
  `class_create()`'s owner, `remove` returning `int`. At 0: `-NoBle-` firmware, no `hci0`; TCP 64.5
  up, 64.3 down, against 61.6–62.3 and 65.5–65.7 for the module before, same hour. At 1:
  `+BlueDroid+` 19897, 6 input buffers, `hci0` on SDIO; `bluetoothctl scan le` 8 devices in 12 s;
  TCP 23.4–23.6 up, 14.9–15.6 down. Installed as debs, `/etc/modprobe.d/atbm6031-ble.conf`, a
  reboot: `hci0` at `54:14:E9:D9:73:D2` again (public), 6 devices in 10 s. The eFuse dump holds only
  the Wi-Fi MAC, `…73:d1`; no driver code writes a BD address. File removed, a reboot: `-NoBle-`, no
  `hci0`, TCP 62.4 up, 66.6 down.
- 6.18 on 7.2's display stack. LibreELEC's display patches one by one on 6.18: 34 of 75 fail, nearly
  all because `0001`–`0040` were an older DE33 series than 7.2 merged. `linux-sunxi/6.18/0001` takes
  7.2.12's `sun4i`, `bridge/synopsys`, `ccu-sun8i-de2.c`, `sun50i-iommu.c`, `dw_hdmi.h`; then
  LibreELEC's `0100`–`0106`, `0200`–`0275` less `0236`, `0409`, `0500`, `0901`, `0902` apply clean,
  81 of 81, and ours `0041`–`0088` after them, 48 of 48, with `7.2/0089`. `6.18/0003`: 108 errors to
  none (`struct drm_atomic_commit`, color-format bits, `of_drm_find_and_get_bridge()`,
  `hpd_notify()`, `field_prep()`, an include). Retired: `0001`–`0040`, `0051` (LibreELEC's `0409`),
  `0089`, `0091`.
- First kexec: an IOMMU read fault at `0x9a600000` every frame, master 0; the console's XR24
  2256x1504 framebuffer. 6.18's `drm_gem_dma` allocates through `drm->dev`, 7.2's through
  `drm_dev_dma_dev()`, the planes device `0240` sets. `6.18/0002` backports that: one fault at bind,
  the old kernel's scanout, then none.
- 6.18 checks, kexec then installed and a real boot: no IOMMU fault after a cold boot; HDMI
  `connected`, `Composite-1` `disconnected`, `tve0` 216 MHz; planes offer NV12, P010, YUV420 and the
  AFBC formats; both sound cards, `/dev/cec0`; `rc-tanix-tx1` 31 keys; Wi-Fi up. Through Cedrus,
  H.264 and HEVC Main10 at 3840, 60 frames each: `framemd5` equal to software.
  `v4l2slh265dec ! kmssink skip-vsync=true sync=false`, 4K HEVC: 29.7–33.5 fps, nothing dropped,
  every buffer by `import_dmabuf`.
- `/dev/input` names: `dw_hdmi` → `hdmi`, `sunxi-ir` → `ir-remote`, and `gpio-keys`, the PH9 button,
  none. `base/input-names.rules` adds `input/gpio-keys`; after `udevadm trigger`,
  `gpio-keys -> event0`.
- Renamed, by function: `adc-keys` and `gpio-keys` both link `input/buttons`. Every board here has
  one: the Rockchip boxes' `adc-keys`, the toothpick (`KEY_VOLUMEUP` or `KEY_F11`), the TX1's
  `gpio-keys`, PH9 (`BTN_0`).
- Sleep past the watchdog: the first regression pass slept 120 s in s2idle and came back a new boot,
  nothing in `pstore`. `sunxi_wdt` has no PM ops on 6.18 or 7.2, and the timer (16 s hardware
  maximum, the core pinging for systemd's 80 s) runs on in s2idle. Every sleep before was 6–10 s.
  `linux-sunxi/0092` stops it on suspend, starts it on resume: `rtcwake -m freeze -s 40`, 42 s, same
  `boot_id`; after it, mode register `0x030090b8` reads `0xb1`, enabled at 16 s, and `state`
  `active`.
- Regulatory domain: `iw reg set DE` returned 0 and `iw reg get` stayed `country 00`. At boot,
  `cfg80211: loaded regulatory.db is malformed or signature is missing/invalid`: Debian's default
  alternative, `regulatory.db-debian`, is signed by `CN=benh@debian.org` (from its `.p7s`), which
  our kernels do not trust. The upstream alternative loads, and DE applies. The kernel side, as
  Debian does: `kernel/regdb-certs/benh@debian.org.x509`, extracted from that signature (SHA-256
  `AD:11:BB:…:B9:36`), and `CFG80211_CERTIFICATION_ONUS` with `CFG80211_EXTRA_REGDB_KEYDIR` in every
  family's fragment. Back on Debian's database, no warning at boot; `iw reg set DE`, then
  `country 98`, DE intersected with the access point's country.
- CPU top step: stock offers this chip's bin (its `0x04`) 1344 MHz at 1.12 V; mainline's table, bin
  speed4 here, stops at 1320 MHz. `board.patch` adds `opp-1344000000`, 1.12 V, `opp-supported-hw`
  `0x10`; the decompiled tree differs from the previous by that node alone.
  `stress-ng --cpu 4 --cpu-method all --verify` 5 min: passed, 0 failed; 1344 MHz at 1120000 µV for
  the first 30 s, then the 70 °C trip holds 1200 MHz, 69.6–73.9 °C.
- PH9, pressed by hand: `evtest`, `gpio-keys`, `BTN_0` press and release, twice. The FEL button
  never shows: only the BootROM reads it. `dw_hdmi`, the CEC remote's input under the HDMI node's
  `rc0`, now links `input/cec-remote`, as the Rockchip boxes' CEC input does.
- The buttons' link renamed `input/recovery-button`, the human's call: each board here has the one
  button, its hidden recovery button.
- PH9's code: mainline labels a "recovery", "update" or "maskrom" button `KEY_VENDOR` (32 trees), a
  "reset" one `KEY_RESTART`; `BTN_0` was ours, stock's Linux never exposed the pin. Now
  `KEY_VENDOR`; the decompiled tree differs from the installed one by that and the 1344 MHz step.
  Not yet installed: the box serves media.
- Watchdog past its hardware maximum. `kill -STOP 1` leaves PID 1 `S`: the kernel never stops init.
  Four `chrt -f 1` busy loops with `sched_rt_runtime_us` -1: userspace still ran, the loops capped
  by `RT_GROUP_SCHED`. Serial was unplugged for both, so neither could see a reset. The test that
  works: `busctl set-property … Manager RuntimeWatchdogUSec t 0` releases the device; a script opens
  `/dev/watchdog0`, `WDIOC_SETTIMEOUT` 80 (granted 80), writes once and sleeps. The next boot's
  kernel started 103 s after arming; U-Boot to kernel is ~14 s, so the reset came ~89 s in: the core
  fed the timer to 80 s, then its 16 s ran out.
- 6.18 with the 1344 MHz step and PH9 as `KEY_VENDOR`: the button's key bitmap sets bit 360; links
  `recovery-button`, `cec-remote`, `ir-remote`.
- Ten warm reboots, each checked: back in 36–37 s, `wlan0` addressed, HDMI `connected`, three video
  devices, three input links, no failed unit, no MMC error, no IOMMU fault.
- Stop and restart: GStreamer `decodebin3 ! kmssink` three times on H.264 1920 and HEVC 3840, ffmpeg
  on Cedrus five times, each cut by `timeout`: no new warning, no IOMMU fault. Scaling: a 3840x2160
  NV12 frame on plane 0 at `crtc-pos=2256x1269+0+117`, the aspect kept.
- `atbm6031` unloaded and reloaded five times: `wlan0` addressed in 3–4 s each. The log's matches
  are the capability lines named `…_BUG [0]` and the known `mibId=4132` refusal.
- Final regression, `tools/validate/validate.sh`, 6.18 installed then 7.2 by kexec: boot 12.2 / 11.9
  s; RAM 1473 / 1472 MiB; watchdog 80 s; 480–1344 MHz; country US from the access point, DE set and
  read back as an intersection; Wi-Fi 64.6 / 68.0 and 63.8 / 64.9 Mbit/s up / down; CEC `1.0.0.0`;
  NV12, P010 and AFBC planes; six codecs bit exact on both (MPEG-2 by spec), HEVC 3840 31 fps and
  Main10 18 fps per 60-frame clip on both, H.264 1920 108 against 86 fps, a gap to recheck on a
  longer clip; glmark2 off-screen 122 / 121; eMMC 64.4 MB/s and 520 / 516 IOPS; 77 / 76 °C at 1008
  MHz under four cores; 120 s of s2idle on the same boot on both. One IOMMU fault on 7.2, the kexec
  handover's. Warnings 1478 / 246, nearly all `atbm_log` at warn level.
- From the human: the standby LED is red in s2idle, as expected; no RTC battery inside. The SoC's
  `sun6i-rtc` keeps time while powered, as the `rtcwake` alarms show; a power cut loses it.
- LEDs, from the human: blue while on; at sleep blue gives way to red, at wake back to blue, as
  `boards/common` `led-sleep` drives them. Powered off: not yet looked at.
- PH9, pressed by hand on 6.18: `evtest /dev/input/recovery-button`, `KEY_VENDOR` (360) press and
  release, twice.
- HDMI hotplug, by the human on 6.18: the monitor unplugged and replugged, the picture back. The
  kernel at 02:55:14 and 02:55:16: `hdmi-audio-codec …: HDMI: Unknown ELD version 0`; the connector
  `connected` after. Audio after a replug not yet played.
- HDMI audio after the replug: heard, by the human. The ELD line is the plug transition alone.
- `poweroff`, seen by the human: every LED dark. The AXP313 cuts the rails, the IR receiver's with
  them, so only a replug starts the box. `boards/common/powerkey.conf` said "no PMIC" for every
  board; now both cases.
- Analog audio, timed: `aplay -d 3` takes 6.07 s on the codec at 32–96 kHz, 3.03 s on HDMI. Two
  audio stacks share `pll-audio-hs`: Armbian's vendor AHUB (`0049`, `0050`; `0050` drops the PLL's
  fixed post-divider so the clock tree reports twice the real rate) and LibreELEC's (`0518`–`0521`;
  the H616 codec needs 1024 × fs, `0521`). Dropping `0050`'s clock hunk and adding `0519`, `0521` on
  6.18 left the codec at 6.07 s: Armbian's AHUB holds the PLL at its own rate. Reverted.
- 7.2 now follows kernel.org's 7.2.13: today's 7.2 builds were 7.2.13, and the staging script still
  took 7.2.12's package, so the 7.2 audio timings before this entry ran yesterday's kernel.
- LibreELEC's audio stack alone on 7.2.13 (`0049`, both `7.2/0050` out; their hub and HDMI audio
  options on), the tree with their `audio-hub@5097000` and `sound-hdmi` in place of the vendor's
  three nodes: codec 3.06 s at 44.1 kHz and 3.11 s at 48, HDMI (`sunxi-hdmi`) 2.99 and 3.05;
  `audio-codec-1x` 49.152 MHz, `audio-hub` 24.576 MHz.
- LibreELEC's audio on 6.18 too: `0501`–`0505`, `0514`, `0518`–`0521` in place of Armbian's `0049`,
  `0050`; `6.18/0004` brings 7.2's IEC958 subframe masks, `6.18/0005` names the hub's `pcm_new`
  `pcm_construct`. 6.18 now follows 6.18.59: the first install took 6.18.58's package and still ran
  Armbian's driver (`CONFIG_SND_SOC_SUNXI_AHUB=y`). On 6.18.59 with the new tree: codec 3.11 s at
  44.1 kHz and 3.10 at 48, HDMI 3.04 and 3.04. Armbian's `0049` and the three `0050` copies deleted.
- A 4K frame's import into DRM and back, as a player that does not cache framebuffers pays per frame
  (a static `fbimport`: dma-heap buffer, `drmPrimeFDToHandle`, `drmModeAddFB2WithModifiers`,
  `drmModeRmFB`, close; 30 rounds): NV12 4.4 ms, P010 8.7 ms on 6.18.59, nearly all import and
  close, 0.7 µs a 4 KiB page. `sun50i-iommu` advertised `pgsize_bitmap = SZ_4K` though LibreELEC's
  `0409` writes runs: one call, one entry flushed, per page. `linux-sunxi/0093` advertises 4 KiB–1
  MiB: NV12 1.8 ms, P010 3.7 ms; HEVC Main10 4K still bit exact, no IOMMU fault.
- Final regression, 6.18.59 installed and 7.2.13 by kexec, both with LibreELEC's audio and `0093`:
  audio 3.05–3.13 s for 3 s on both cards and kernels; 4K import NV12 1.71 / 1.73 ms, P010 3.31 /
  3.33; six codecs bit exact (MPEG-2 by spec), H.264 1920 102 / 84 fps, HEVC 3840 32 / 32; glmark2
  122 / 121; eMMC 64.7 / 67.1 MB/s; Wi-Fi 64.4 / 67.9 and 62.7 / 60.0 Mbit/s; 1200 MHz at 73 / 72 °C
  under four cores; 120 s of s2idle on the same boot on both; one IOMMU fault on 7.2, the kexec's.
- The two gaps, root-caused, quiet box: H.264 on a 30 s 1080p clip (900 frames, x264 High, 8
  Mbit/s), 122.1 / 124.7 / 124.9 fps on 6.18.59, 128.8 / 123.6 / 123.1 on 7.2.13, 900 engine
  interrupts each, `ve` 600 MHz from `pll-ve` on both; one frame from cold start 0.57 s on both. The
  60-frame 102 / 84 fps ran on 7.2 straight after its kexec, the CPU 50% busy. Wi-Fi down, ten runs
  each at -30 dBm: 7.2 58.3–64.2, 6.18 59.8–65.0 while `tx bitrate 135.0 MBit/s MCS 7` (40 MHz),
  34.9–49.3 in the runs where the access point had dropped to `65.0 MBit/s MCS 7` (20 MHz).

## 2026-10-26

- Decoder scaling, Cedrus. The VE probed with the engine clocked by an HEVC decode: H.265
  `SDRT_CTRL` (`0x550`) reads back `0x3f00` after all ones, the ratio bits as on the H713; the
  H713's polyphase block at VE `0xf00` reads 0 here, absent.
- `linux-sunxi/0094`: the secondary output writes the scaled NV12 picture at the start of the
  CAPTURE buffer, the full reconstruction hidden after it, as P010's. Built as a renamed module
  (`sunxi-cedrus-scale`, driver `cedrus-test`) and bound in place of the built-in driver, no reboot.
  Unscaled output unchanged: H.264 1080p and HEVC 4K MD5 equal to the built-in driver's, HEVC Main10
  equal to the software decode at 10 bits.
- First scaled run returned the full size: the decoder node had `G_SELECTION` and `S_SELECTION`
  disabled (`v4l2-ctl` `ENOTTY`), selection being the encoder's crop. Enabled for COMPOSE.
- Then every download crashed (`av_image_copy_to_buffer`, a 960-wide buffer copied as 1920x1080):
  `avcodec_default_get_buffer2` gives a hardware frame the coded size. `ffmpeg/0017` restores the
  CAPTURE size in the hwaccel's post-process and scales the crop. A limit of 540 on H.264 1080p
  (coded 1088) gave ¼: the limit now bounds the visible size, and gives ½.
- Against FFmpeg's decode area-scaled in software, 60 frames: H.264 ½ 64.9 dB, ¼ 55.6 (Y 53.9); HEVC
  4K ½ 63.2 dB, ¼ 64.8. No engine hang at either ratio, unlike the H713's HEVC.
- Decode to `drm_prime`, quiet box: HEVC 4K 300 frames 36.7 fps full, 34.8 at ½, 35.3 at ¼; H.264
  1080p 600 frames 131 full, 125 at ½. The engine still writes the full reference; the saving is in
  what the display and the player read.
- AV jack: a composite-to-HDMI converter showed no signal and its speakers clicked, the codec idle
  (`pcm0p` closed throughout) and unchanged with the line out driven by silence. Clearing `PAD_SEL`
  (bit 1) in TCON TV1's `GCTL` (`0x06516000`) silenced it; setting it again for 20 s brought the
  clicks back. LibreELEC's `0211` sets it on every H616 TV TCON at bind; `linux-sunxi/0095` sets it
  at mode set, for HDMI only.
- Composite: `Composite-1` reports disconnected (no load sense); forced on (`status` `on`), the
  console's client set 480i on `crtc-1` and every commit after timed out waiting for vblank. TCON
  TV1 enabled (`GCTL` `0x80000003`, `0x090` `0x80100140`, 720x240 a field), its VB interrupt
  enabled, `tcon-tv1` 13.5 MHz and `tve0` 216 MHz on, `tcon-top` `0x1c` `0x32`, `0x20` `0x11000000`;
  not one TCON TV1 interrupt. `PAD_SEL` cleared: no change.
- Correction: the clicks are the TV encoder's DAC load detection, which `0089` armed at bind
  (`0x030` `0x80000001`). With `PAD_SEL` clear and every TV bit at the kernel's defaults the jack
  clicked; off the box it did not; `0x030` cleared, silent. The one `PAD_SEL` toggle was chance.
  `0089` no longer arms it; `0095` stays, Allwinner's own pad handling.
- Composite, every vendor setting live (traced from Allwinner's 4.9 BSP for sun50iw9,
  `de_tve_sun8iw11.c`, `drv_tv.c`, `lowlevel_v33x/tcon/de_lcd.c`): `tcon-top` `0x000` bit 4 (TV1
  clock from the TVE), `0x020` bit 21 (the TV1 gate: clearing it stops TCON TV1, bit 24 does
  nothing); TVE `0x004` bit 16 (composite enable, absent from our tables); TCON TV1 progressive
  858x525 (`0x090` `0x800001f0`, `0x094` `0x02cf01df`, `0xa4` `0x041a0023`, `0xa8` `0x003d0005`) at
  60.0 frames/s; `GCTL` `0x80000000`; detection off. The converter's audio hissed once the DAC
  drove; no plug on the yellow input gave a picture. Neither audio nor video verified at the jack.
- `0089` without detection, 6.18.59 installed: `0x030` reads 0 from boot, the TVE unclocked; the
  converter on the AV jack silent.
- `0095` reverted. With it the first EDID read at boot failed and the console took the 1024x768
  fallback: TCON TV0's `PAD_SEL` gates HDMI's DDC, so it must be set before the first probe. Live:
  pads on 18 modes, `PAD_SEL` cleared 4 (the no-EDID set), set again 18. LibreELEC's `0211`, setting
  it at bind, stands; the clicks were the encoder's load detection.
- Without `0095`, a cold boot with HDMI connected: console framebuffer 2256x1504, `tcon-tv0` 235.5
  MHz, TCON TV0 `GCTL` `0x80000003`, TVE `0x030` 0; the screen at its native mode.
- BLE: the driver reloaded with `wifi_bt_comb=1`, Wi-Fi back at 135 Mbit/s MCS 7 40 MHz. Another
  box's remote, `Bluetooth remote` `61:1A:47:5F:30:8D`, paired, bonded, trusted, connected with a
  `NoInputNoOutput` agent: HID over GATT, `Bluetooth remote Keyboard` on `event3` and
  `Bluetooth remote Mouse` on `event4`. README's recipe found nothing: a device seen before prints
  no `[NEW]` line in a scan; it reads `bluetoothctl devices` after the scan now, and prints the MAC
  or "not found".
- The BLE remote's keys and air-mouse read in `evtest` on `event3` and `event4`, by hand.
- BLE on 7.2.13 by kexec: `wifi_bt_comb=1`, `hci0` UP RUNNING `errors:0`, an LE scan 13 devices, the
  remote's bond kept; Wi-Fi at 135 Mbit/s MCS 7 40 MHz.
- USB stick (SSK, `24a9:205a`, 58 GB) on the USB-A port, USB0 routed to EHCI0: not seen after two
  power cycles with it in; hotplugged with the box up, `480M` on `ehci-platform`. Its contents
  first: the H96 Max M20's image; the Tanix image written over it, 995098624 bytes in 58 s, hash
  equal. `fio`, `--direct`: 29.4 MB/s sequential read, 843 IOPS 4K random read, 22.3 MB/s sequential
  write, 301 IOPS 4K random write. A warm reboot with it in: enumerated at `480M` 3.6 s into boot;
  the box booted the eMMC, our U-Boot trying it first.
- Power-cycled with the stick in: `480M` on `ehci-platform` 3.6 s into boot. The two earlier misses
  did not recur; their cause is not shown.
- Wi-Fi against `plex` (iperf3), 15 s each way: idle 65.1 Mbit/s up, 63.9 down; under
  `stress-ng --cpu 4 --io 2` 64.5 up, 61.0 down; `tx bitrate 135.0 MBit/s MCS 7 40MHz`.
- Wi-Fi latch sought: `iperf3 --bidir` to `plex` for 600 s, each direction 12–25 Mbit/s in every 10
  s interval, none at 0; a 2 s run after, 66.7 Mbit/s.
- C5: `aquaman-60s-video.mkv`, 4K HEVC Main10 HDR10 at 23.98 fps, 1491 frames: decoded to
  `drm_prime` through P010 in 75.7 s, 19.7 fps, CPU 67–77% idle. `kmssink` refused
  (`drmModeSetPlane`: EACCES): another session's player held DRM master.
- U3 on the stick: `fio` 64 KiB random, 70% reads, iodepth 8, 60 s, under
  `stress-ng --cpu 4 --vm 1`: 10.8 MB/s read, 4.6 write, 0 errors, no USB reset, the stick still
  attached.
- HEVC with `VE_MODE_DDR_MODE_BW_256`, as VP9 takes on the H616: 300 4K frames 11.2 s against 8.2 at
  `BW_128`, MD5 equal, five `cedrus_dec_h265.c:325` reference warnings; `BW_128` none. Stock runs
  `ve` at 624 MHz to our 600, `de` 696 to 600, `gpu` 600 to 504; DRAM 1200 and `mbus` 400 alike.
- AFBC on 6.18's planes (`modetest -p`): `YU08` with `ARM_AFBC` 16x16 SPARSE, YTR, SPLIT modifiers
  on one plane; `YU10` LINEAR only on all three. Stock's 4.9 `disp2` scans AFBC itself.
- Correction: `modetest -p` misdecodes IN_FORMATS here (AFBC on 15- and 16-bit RGB, which the code
  never offers; `YU10` linear, which it forbids). `drmModeAddFB2WithModifiers` on 6.18.59 takes a 4K
  `YU08` and `YU10` framebuffer with AFBC 16x16 sparse and sparse-split alike: 10-bit AFBC is there.
- Wi-Fi latch, 2026-10-27 04:00, 10169 s associated: tx 65.0 MBit/s MCS 7 at 20 MHz, rx 11.0 MBit/s;
  the box's scan saw the AP at 20 MHz, no secondary; iperf3 to `plex` 18.7 up, 3.4 down; station
  counters tx retries 4467, failed 211, rx drop misc 314; signal -41 dBm. `iw disconnect` and a
  reconnect: 17.3 / 5.3, unchanged. `rmmod atbm6031; modprobe atbm6031`: tx 135 MBit/s 40 MHz, 66.7
  up, 67.5 down. The ten-minute run before had passed: N8's ✅ was too short a look.
  `aggr token not enough` ran at a flat 36 per 10 min all boot, latched or not.
- Player-like hour (`research/atbm6031-latch-bug/tools/playsoak.sh`): no deep latch; the AP's rate
  to the box MCS 1-5 under a 50 Mbit/s stream. Two firmware TX stalls, `wait space timeout` at 429 s
  and 3676 s, each a driver `halt` and a reassociation (`AP ... lost`); TX tokens 0-3 after both.
- Wi-Fi latch reproduced: the player hour on 0007 with a 1-2 ms poll (0 TX stalls, against 2 on the
  package) latched by t+60m, 20.2 up / 5.6 down idle, rx 11 Mbit/s, no reconnect. `stop_ba`: no
  change; a reconnect: none; firmware `halt` then a reconnect: 52.4 down, 59.2 up. The latch is
  firmware state; the fix is the driver noticing and restarting it.
- Wi-Fi 32 kHz, 2026-10-27: stock drives PG10 from `losc_out` ← `hosc32k` ← `hoscdiv32k`, a fixed
  32768 Hz off the crystal. Ours ran `osc32k-fanout` ← `osc32k` ← `iosc-32k`: the RTC's RC (`iosc`
  13828103 Hz), calibrated against the crystal (`0x0700000c` 0x694077c3). The fanout mux
  (`0x07000060` bits 2:1) takes `pll-32k`, the only crystal source at 32768 Hz; written live (`0x1`
  → `0x3`), the link held, 66.6 Mbit/s down, MCS 7. `board.dts` now parents the fanout to
  `CLK_PLL_SYSTEM_32K`. Whether the RC caused the latch: open.
- Firmware strings (`atbm6031_fw.bin`, NDS32, `Dec 6 2023`): `compenCfo%d->%d`, `DCXO%u->%u`,
  `ppm%d,cnt%d`, `Temp%d,%d`: the firmware corrects its crystal at run time. A latch module with
  `latch_trace` logs its CFO MIB and temperature; healthy, `rx_cfo -4 tx_cfo -4 temp 63`.
- Wi-Fi, forcing, 2026-10-27, RC 32 kHz, 10 min each under a 50 Mbit/s stream: back-to-back scans
  (~80), a disconnect every 20 s, `stress-ng --cpu 4` to 68 °C: no latch; firmware CFO MIB -4 ppm
  throughout, frozen.
- Firmware reboots: `atbm_rx_directly ... wsm_seq=0`, the firmware's message sequence restarting.
  The night before, 8; every `wait space timeout` 11-26 s after one, so the TX stalls were these.
  Today 3 in 43 min with the drift watch writing `WSM_MIB_ID_DBG_PRINT_TO_HOST` every 5 s, 0 in 64
  min with it off, 1 in 30 min with it written once: the firmware's log over SDIO coincides.
- After a driver restart the CFO MIB read `init 0` for 40+ min: `atbm_reinit_firmware` never sends
  the probe's `"cfo 1 0"` nor `wsm_set_rate_power()`. Sent again (0014): `init 1`, -4 ppm, 1 s after
  reassociating, on a forced `halt` and on a real reboot (11:25:31).
- 0013 reloads on a 0 out of turn. The 09:55:57 and 11:25:31 reboots alike: disconnected at +0.5 s,
  wpa_supplicant's authenticate at +2.1 s, the driver's at +9.2 s, connected at +10.4 s, the DHCP
  lease at +18.3 s.
- GRO (0012): 79.0-81.4 Mbit/s down at 8-12% CPU, against 66.5-69.5 at 18-19% on the package.
- Module builds took over an hour: `Makefile.vendor`'s bare `export`s expand kbuild's `size_append`
  per recipe; `size_append=` on the command line, 84 s.
- Reconnect after a restart, 7.2 s of it: wpa_supplicant blocked in `ieee80211_get_channel_mode` on
  `iflist_mtx`, which the scan's `ieee80211_recalc_idle` held through `__atbm_flush`'s `7* HZ` wait
  for frames to the lost AP. 0017 drops them when joined to nothing: two forced restarts,
  authenticate 24 ms after the request, connected at +2.87 and +2.82 s, the lease at +2.95 s; 81.3
  Mbit/s down at 13% CPU after.
- 0016: `atbm_printk` at `KERN_ERR` for every class; 93 kernel lines in 10 min before, all of them
  warning or above.
- VE clock, 2026-10-27: PLL-VE `0x03001058` N 0x18 → 0x19 by hand, 600 → 624 MHz as stock runs it;
  `aquaman-60s-video.mkv` (4K HEVC Main10, 1491 frames) to `drm_prime`: 19.51 fps at 600, 19.68
  at 624. +0.9% for +4%: 4K Main10 is not bound by the engine's clock; the tree stays at 600.
- Boot, 2026-10-27, `CONFIG_CRYPTO_DEV_SUN8I_CE=y`: the CE probes at 0.69 s and
  `systemd-random-seed` no longer waits (was 1.66 s), but the total held at 12.1-12.4 s: it was off
  the critical path. Kernel 5.6 s: 1.24 s between the display engine binding mixer0 and mixer1, its
  LCD controller bound at 4.10, 4.84 and 5.21 s; the serial console 0.6 s.
- 0016 second pass: boot warnings 272 → 14; the rekey setup logged the KEK's and KCK's first four
  bytes at error level, now gone.
- Firmware-log capture: 70 min of the player soak with `latch_fwlog=1`, no reboot. The firmware's
  own `CPU:` reads 16-18% under the stream. `/etc/modprobe.d/atbm6031-fwlog.conf` keeps the log on
  until one is caught.
- 7.2.13 with 0012-0017, 2026-10-27: 11.9 s to `graphical.target`, the same 14 boot warnings; N6
  79.1 down at 10% CPU, 65.5 up; N7 under `stress-ng --cpu 4 --iomix 2` 77.0 / 66.5; X4 five
  reloads, back in 2.6-2.7 s; C5 19.36 fps; C9 eleven stops, no warning; S14 5 min clean; ten
  reboots 35-38 s, every device, DDR52 each; S19 armed at 80 s unpinged, the kernel 94.2 s after, so
  ~80 s: 7.2 resets at the set timeout where 6.18 ran the core's 80 s plus the hardware's 16.
- AV jack audio, 7.2: the user hears none on the composite converter either. The codec side works:
  `speaker-test -D plughw:0,0 -c 2` RUNNING, `hw_ptr` advancing, no warning; Line Out on at 17/31,
  DAC on at 45/63; ALDO1 (`vcc1v8`, the factory's `avcc-supply`) always on; the factory tree has no
  amplifier GPIO. The default sink is HDMI (H6): a test must name card 0. Picture and sound both
  absent also fits a cable whose TRRS pinout puts ground elsewhere. Not verified.
- 7.2 unattended, 2026-10-27: U3 `fio` 64 KiB random 70% read under `stress-ng --cpu 4 --vm 1`, 60
  s, 12.9 / 5.5 MB/s, 0 errors, no USB reset; H17 `glmark2-es2-drm` 120 on screen; C8 3840x2160 NV12
  `drmModeSetPlane at (0,117) 2256x1269`, no warning.
- N8 on 7.2, 2 h of the player soak, 2026-10-27 17:11: two firmware reboots, 17:30:56 and 17:45:30,
  each reloaded at once, disconnected +0.6 s, connected +3.4 s, the lease +3.6 s: 2.7 s off the AP
  both times, as forced restarts measured. A third drop at 17:49:08 was a TX stall
  (`wait space timeout`), reloaded the same way, back in 2.0 s. No latch. After, the AP itself at 20
  MHz ("no secondary"), 27 Mbit/s down.
- Firmware log before both reboots (`latch_fwlog=1`): its usual reports to the last line, CPU
  12-16%, `ppm-4`, gain steady; a scan of channels 1 and 6 4 s before the first, nothing before the
  second. The firmware gives no warning before it reboots. The modprobe option is removed.
- USB-first boot, 2026-10-27: mainline's `tanix_tx1_defconfig` already has USB host and storage,
  ext4 and FAT, and `preboot=usb start`; `boot_targets=fel mmc_auto usb0` reached the eMMC first.
  `BOOT_PREBOOT='usb start; setenv boot_targets fel usb0 mmc_auto'` in `uboot/tanix-tx1.conf`; the
  eMMC head (sectors 0-12799) backed up, the U-Boot at sector 16 matched the previous build, the new
  one written and read back, secure storage untouched. The 2026-10-27 image on the stick, its Wi-Fi
  profile, key and password age seeded: booted from it, root `/dev/sda1`, U-Boot 2026.10, MCS 7. The
  stick's `extlinux.conf` renamed: the eMMC booted, back in 42 s.
- M6, 2026-10-27: booted from the stick, `tvb-install -y /dev/mmcblk0`: the partition table with the
  rootfs grown to 15 GB, 2.0 GB by file, boot sectors 1-32767 but 12288-12799; secure storage equal
  to the morning's backup. The stick's image carried the U-Boot before `BOOT_PREBOOT`, so the
  install put eMMC-first back; the USB-first one written after. The eMMC booted: root
  `/dev/mmcblk0p1` under a new UUID, Wi-Fi, no failed unit. U-Boot's environment is `uboot.env` on a
  FAT partition the image does not have: nothing persists, the preboot sets the order every boot.
- AFBC in a player at 2256x1504 (the player's session, 6.18): the top of the picture clean, the rest
  garbage, `sun50i-planes 1100000.planes: RCQ sync timed out` three times this boot. Its reading of
  the driver: an AFBC layer turns the video fetcher's coarse downscale off, leaving the scaler alone
  to shrink 3840x2160 to 2256x1268, 1.70x, where the driver's own formula allows about 1.38x at this
  mode; the atomic check accepts the layer anyway. Linear P010 goes through the coarse stage and is
  clean. The 1.38x not checked here.
- Correction: C8's ✅ stood on the request, not the picture: kmssink's
  `drmModeSetPlane at (0,117) 2256x1269` on 7.2, and linear NV12 only on 6.18. "10-bit AFBC is
  there" stood on `drmModeAddFB2WithModifiers` accepting the buffer, not on a frame shown.
- 0096 on 6.18, 2026-10-28: TEST_ONLY atomic commits on plane 33 at 2256x1504@60
  (`tmp/afbct/afbcscale.c`): AFBC 3840x2160 to 2256x1269, `Invalid argument`; AFBC 2256x1269 1:1,
  AFBC 2400x1350 to 2000x1125 and linear NV12 3840x2160 to 2256x1269, accepted. The patch's own
  estimate is atomic_update's: mixer clock, mode, the wider width; the line buffer from the per-SoC
  table. The same boot logged `RCQ sync timed out` at 183 and 192 s, with the player on screen; its
  log says nothing then: cause open.
- 0097, 2026-10-28, 6.18: 0094's scaling allowed for 10-bit H.265 as P010, the 2-bit plane sized
  from the coded picture. `aquaman-60s-video.mkv` (4K Main10 HDR10) with `capture_max_width=1920`,
  `_height=1080`: 1920x1080 P010, its HDR metadata kept; the whole clip 25.23 fps (19.4 full); 10
  frames against a software area scale, 67.6 dB PSNR (Y 65.9); no warning. The 10-bit cost was the
  full-size P010 copy, not the decode: AFBC is not needed for a smaller screen.
- 0096 + 0097 in the player (its session's box suite, 2256x1504@60): `hevc10-4k.mkv` at the screen's
  size, 1920x1080 P010, 75.7 dB against an area-scaled software decode; AFBC asked, AFBC at full
  size; all 24 picture cases pass; "plays on after a seek" passes, where it failed before. The
  Aquaman stream, P010 and the size from the start, 20 s from 600 s: 387 shown, 4 dropped, 27 late.
  With AFBC asked, refused by 0096 and reopened linear: from 0 s 452 shown, 8 dropped; later starts
  vary, its own seek reopen and audio stall at the HDR switch, by its account. No `RCQ` or Cedrus
  warning in any run.

## 2026-10-28 — Wi-Fi gone after a reboot

- Rebooted into 6.18.59 without `0096`, with `0091`, `0098` and `0099`. The box booted, by the
  owner's eye; Wi-Fi fell to a low rate, then carried nothing. No ping, no ssh, nothing on the LAN
  sweep. `0091` is not a boot hang. Logs not read yet: the box has no other way in.
- README's 2.4 GHz row ✅ → 🟠; board.md gains "Wi-Fi link held" ❌.
- Wrong: the radio was never up. On USB Ethernet: `mmc1: new high speed SDIO card`, no `wlan0`,
  `modinfo atbm6031` not found. `linux-image-*` ships its own `modules.dep`; installed alone, it
  dropped `atbm6031` from the index, and nothing ran `depmod`. `depmod -a; modprobe atbm6031`:
  joined in 3 s. Both doc marks reverted.
- Fix: `modules/build.sh` gives each driver package a dpkg file trigger on its kernel's
  `modules.dep`, so its `postinst` reindexes whenever the kernel package rewrites it. Checked on the
  box by hand-adding the trigger: reinstalling the kernel deb runs it, `atbm6031` stays indexed.
- `0091` on the box: `de`, `mixer0` and `mixer1` at 696000000 Hz.
- Allwinner's path on 6.18.59 without `0096`, with `0091` (`de` 696 MHz) and `0099`: full-size AFBC
  shrunk by the display, 3840x2160 YU10 to 2256x1268, BT.2020, by Fuseamp, 30 s from 600 s. Aquaman
  (WEB-DL): 686 shown, 1 dropped, 0 late. Inception (UHD remux): 690 shown, 0 dropped, 0 late. No
  `RCQ sync timed out` in either. Picture by eye not yet checked.
- Cadence at 60 Hz: Aquaman a clean 3:2; Inception ~36 irregular holds in 30 s, nothing dropped or
  late: decode time on heavy pictures or the player's pacing, unmeasured.
- Fuseamp's suite: 24/24 picture cases, every playback case passes, 4K Main10 with AFBC 182 shown,
  cold start 1292 ms. One `RCQ sync timed out` at 497 s uptime, during its mode-set case.

## 2026-10-30 — Kodi 22 test build on the box

- Kodi `22.0rc1-Piers` with `patches/kodi/` `0001` and `0003`, Kodi's own FFmpeg 9.0.2 without
  `patches/ffmpeg/`: built in the arm64 trixie container, unpacked to `/opt/kodi-test`, run as the
  transient unit `kodi-test` with `KODI_HOME` and `KODI_BIN_HOME` pointing there. 82 runtime
  libraries installed from Debian; `fuseamp.service` disabled and stopped.
- GBM on `HDMI-A-1` at the display's 2256x1504, GUI plane 33 `AR24` linear; `Mali-G31 (Panfrost)`,
  OpenGL ES 3.1 on our Mesa 25.0.7.
- CEC: Kodi registers `/dev/cec0` through libcec's Linux API, `0003`'s static build.
- Audio: Kodi defaults to card 0, the H616 analog codec, and fails `snd_pcm_writei` every 3 s; set
  to `ALSA:sysdefault:CARD=sunxihdmi`, HDMI opens clean.
- Idle on the home screen: 27% of one core, 280 MB resident, SoC 61.9 °C.
- No hardware decode in this build: no `v4l2request` until `0002` and `0004`.
- Jellyfin for Kodi 2.2.0 from Jellyfin's repository: its repository addon `1.0.0` points at
  `repo.jellyfin.org/releases/client/kodi`, gone; pointed at `kodi.jellyfin.org/py3`, Kodi installs
  the addon and its nine `script.module` dependencies from Kodi's own repository. The addon finds
  the LAN server on its own and asks for a user.
- Jellyfin for Kodi's sync misbehaved, and its threads kept Kodi from stopping: `SIGKILL`. Replaced
  by JellyCon 1.0.2, on a wiped `/root/.kodi`: HDMI audio and the repository set again, JellyCon
  installed from the repository. Its first-run password dialog likewise blocks Kodi's stop. Signed
  in off-screen instead: `POST /Users/AuthenticateByName` with JellyCon's own `Authorization` header
  and device ID (`special://temp/jellycon_guid` plus the username's MD5), the token into its
  `auth.json`, `server_address` and `username` into its `settings.xml`. Kodi starts on Home with no
  prompt and JellyCon lists the server's libraries.
- Undo: `systemctl stop kodi-test`, `rm -rf /opt/kodi-test /root/.kodi`,
  `systemctl enable --now fuseamp`.
- Rebuilt with `patches/kodi/` `0001`–`0004` and `patches/ffmpeg/` through `-DFFMPEG_PATCHES`:
  `--enable-libudev --enable-v4l2-request --enable-v4l2-m2m --disable-vaapi`, VAAPI and VDPAU off.
  `kodi-gbm` carries `h264`, `hevc`, `vp9`, `mpeg2` and `vc1` `_v4l2request`.
- `videoplayer.useprimedecoder` and `useprimedecoderforhw` on, `useprimerenderer` 0, as LibreELEC's
  `appliance-gbm.xml`. The same 10-bit HEVC film from Jellyfin: `CDVDVideoCodecDRMPRIME`,
  `v4l2request option afbc=8,10`, video plane 33 at 1920x1080 under GUI plane 39. Plane 33 scans out
  `YU10`, modifier `0x800000000000061`, shown at 2256x1270. Cedrus 24 interrupts/s, one per frame;
  Kodi 50–82% of one core.
- HDR10 in Kodi: the monitor's EDID lists PQ and BT.2020 YCC, not BT.2020 RGB. During a 4K HDR10
  film Kodi sets `HDR_OUTPUT_METADATA` to the film's (PQ, BT.2020 primaries, 1000/0.005 nits, MaxCLL
  2339, MaxFALL 994) and `Colorspace` `BT2020_RGB`, and clears both on stop. Colorspace held at
  `Default` instead changes nothing.
- The controller is not told: `/dev/mem` at `0x06000000`, `FC_PACKET_TX_EN` (`0x10e3`) `0x9f`, the
  DRM InfoFrame on, `HB` `01 1a`, `PB0` 2 (PQ), but 1000/0.0001 nits and MaxCLL, MaxFALL 0: an
  earlier film's own mastering values, not this film's. Mainline 6.18 `dw-hdmi` writes the DRM
  InfoFrame only in `dw_hdmi_setup()`, a mode set; its connector's atomic check forces one when the
  metadata changes, its bridge's (`dw_hdmi_bridge_atomic_check()`, the path `0103` takes) does not.
  An HDR change at the same mode never reaches the wire, and the InfoFrame stays whatever the last
  real mode set wrote: HDR over the interface, or SDR over a film.
- Kodi against Fuseamp, the same Jellyfin films: idle on Home 27–36% of one core against 0%; first
  picture 1080p SDR 2.3 s against 1.1 s, 4K HDR10 2.9 s each; playing 4K 50–109% against 50–100%;
  Fuseamp `--check-playback` 0/481 and 0/485 dropped, both `hevc_v4l2request`. JellyCon lists a menu
  level in 2.4–2.8 s. Kodi's idle is its main thread (25%) with the GUI plane's framebuffer
  unchanged over 2 s: the loop, not drawing. `videoscreen.limitguisize` 1080 leaves it as it was.
- 6.18.60 with `linux-sunxi/0095`: the HDR InfoFrame follows Kodi at one mode, read at `0x10e3` and
  `0x1168`: SDR menu off; a 4K HDR10 film on, PQ, 1000/0.005 nits, MaxCLL 2339, MaxFALL 994, its
  own; straight on to another, MaxCLL 313, MaxFALL 137; back to the menu off. Each matches the
  connector's `HDR_OUTPUT_METADATA` byte for byte.
- `0096` refuses an AFBC layer the display would shrink: Kodi's 4K AFBC at 2256x1270 failed every
  test commit (`EINVAL`), the HDR change with it. `patches/kodi/0004` now asks AFBC only for a
  picture no larger than the mode, else `capture_max_*` from the mode; 4K then comes scaled by the
  decoder, linear, and every commit passes.

## 2026-10-30 — the FEL loader without fastboot

- The loader boots straight into `ums 0 mmc 1`: fastboot, DFU and their `head` region gone, the disk
  the one route for backup, restore and install. `board.md`'s fastboot and DFU rows dropped; they
  measured the loader before. Untested on the box yet.

## 2026-10-30 — the FEL loader and U-Boot, end to end

- The loader that boots straight into `ums 0 mmc 1`: the eMMC as `/dev/disk16`, 15.8 GB, 7 s after
  `sunxi-fel uboot`. Read 0–12799: the secure storage 12288–12799 equal to the stock backup's; the
  U-Boot at 16 already this build. Write test at 8192–8319, 64 KiB of random data: read back
  identical, the original written back and verified. U-Boot written at 16, read back identical.
- Raw disk access from an app without Full Disk Access is refused even to root
  (`Operation not permitted`); from a terminal with it, `sudo dd` works. GNU coreutils' `stat` ahead
  on the PATH takes `-f` as file-system status.
- Booted from the eMMC on DC: 6.18.60, kernel 6.2 s, userspace 6.1 s, Wi-Fi at 13.6 s.
- A timed reboot, 6.18.60: shutdown 2.6 s, reset through U-Boot to the kernel 17.1 s, kernel 5.8 s,
  userspace 6.2 s, Wi-Fi 13.3 s after the kernel started: 33.0 s from `systemctl reboot` to Wi-Fi.
  The 17 s is unbroken down without serial; tolerable, nothing in the logs.
- HDR10 on 6.18.60 with `0095`, read back from the controller by the Kodi session: the DRM InfoFrame
  off on the SDR menu, PQ with the film's own mastering data and light levels on each film, updated
  film to film, off again after; the monitor followed. Output stays 8-bit RGB at 2256x1504: 10-bit
  needs YUV 4:2:0 on a 4K TV mode.

## 2026-10-31 — Cedrus: VP8 to 4096, JPEG, VC-1 Main

- Cedrus built as a module (`sunxi64.fragment`), so a driver change is a module build on the box; an
  `insmod` of a module the kernel has built in loads nothing, which first passed for a test.
- VP8 past 2048 wide: the deblocking and intra prediction rows moved to DRAM, as H.264's, gave 2304
  and 2560 bit exact; 3840 and 4096 still timed out, the IOMMU faulting 12 KiB into the probability
  buffer, which our driver sized 0x2400 and `libawvp8.so`'s `vp8_init_decode` allocates at 0x5400.
  At 0x5400 every width to 4096 decodes bit exact, 38 fps at 3840. `0086`'s limit gone.
- JPEG: Emmanuel Gil Peyrot's decoder on the reworked driver. FFmpeg's `mjpeg_v4l2m2m` asks for
  `MJPG`, so the engine answers both fourccs. The kernel's `v4l2_jpeg_parse_header` refuses chroma
  sampled other than 1x1, which FFmpeg's own encoder writes for 4:2:2 and 4:4:4; libjpeg's files
  decode, chroma 42–52 dB against software from the engine's 4:2:0 conversion, luma 78 dB.
- A single JPEG hung FFmpeg at drain: the stateless decoder took no stop command. With the stateful
  one, a still came back as two pictures: the empty last buffer kept `buffer_prepare`'s payload.
  Zeroed (`0802`), shared with the encoder's drain. Stopping the picture queue also left its buffers
  with the driver, a videobuf2 warning each (`0801`).
- VC-1 Main: Robotica (1440x1080, overlap, no B pictures) decodes bit exact with only the refusal
  lifted; the SMPTE conformance streams do not: `SMM0005` (B pictures) keeps luma exact and drifts
  chroma to 19 dB, `SMM0015` (FASTUVMC, MULTIRES) drifts both. Writing EPHS `MULTIRES`/`RANGERED`,
  as the vendor does, changed nothing. Software decodes Robotica at 1.48x real time: Main stays
  refused, its comment and `0065`'s message now saying why.
- Both kernels, 6.18.60 and 7.3.1, built in: H.264, HEVC, Main10, VP8, VP9 bit exact to 4096, MPEG-2
  by IDCT, the VC-1 conformance streams but Main, JPEG and MJPEG, H.264 encode. MJPEG 1080p 100 fps,
  software 47. One `frame processing timed out` in 1075 frames of interlaced VC-1 with B pictures,
  every frame still bit exact, on both kernels.
- JPEG encode, `0804`, from `libvencoder.so`'s debug info: the H616's JPEG mode counts the picture
  in 8-pixel units, takes its quantisation tables at `0xe0`/`0xe4` as a rounding offset and
  reciprocal per entry, codes with the fixed Annex K Huffman tables and leaves the end marker to
  software. First run decoded; 640x480 to 4096x2160, odd sizes too, at the true size: luma 40 / 45 /
  55 dB at quality 50 / 85 / 95. A 4K frame in 108 ms through a test client, FFmpeg's software 557
  ms. `v4l2-ctl`'s mem2mem streaming returned empty buffers for H.264 as well: not a test of the
  driver.

## 2026-10-31 — Cedrus: MPEG-4 Part 2 and H.263

- Private stateless controls (`0805`): VOL, VOP, quantisation, slice; Cedrus engine `0806` after
  `libawmpeg4normal.so`'s register map, FFmpeg hwaccel `ffmpeg/0019`. The engine decodes a run of
  macroblocks and parses no packet header: a request per video packet or H.263 GOB with a header,
  found by the hwaccel in the VOP. The NCF buffer holds the last I/P/S-VOP's co-located data: the
  driver tracks that picture and refuses a B-VOP whose backward reference is another.
- First run decoded: FFmpeg's encodes at 720p 64–70 dB luma against software, the IDCTs differing.
  FFmpeg's `mpeg4` encoder slices a frame per thread, five video packets: the packet path was tested
  before the whole-VOP one. IRQ counts confirmed a request per packet (2449 for 120 frames with
  `-ps 2000`) and per GOB.
- Interlaced: field-predicted chroma off by up to 20 dB with `VECTRL` bit 19 set, as the vendor sets
  it always; it is DivX's field chroma rounding, FFmpeg's `FF_BUG_HPEL_CHROMA`: set from that bug
  only. P-VOPs then 64 dB. B-VOPs with field motion stayed 32–60 dB: errors in a quarter of the
  direct macroblocks over an interlaced co-located one, none over a frame one. `0x120`'s field
  distances in six encodings, zero included, and a flipped top-field-first changed no pixel: the
  engine ignores them. Interlaced B-VOPs refused; FFmpeg leaves interlaced streams without
  `low_delay` to software.
- DivX qpel chroma bugs (`QPEL_CHROMA`, `QPEL_CHROMA2`) mapped onto the vendor's `VECTRL` 25:20
  table: DivX 5.01 and 5.03 qpel samples 68–85 dB chroma. Plain qpel takes mode 0, confirmed by
  sweeping the field: luma never moved. Quarter-sample luma settles 1–10 dB below half-sample
  against software, 57 dB on FFmpeg's encodes, 45 dB on DivX 5.03's; no switch found.
- GMC from the vendor's `calc_affine_transforms_{1,2,3}point`: DivX 5's 2-point translations decode
  at 57–73 dB (angel, wow, dx502). Xvid's 3-point warp put chroma at 41 dB until the chroma offset
  took FFmpeg's half-sample term the vendor leaves out, 66 dB after; luma stays 38–42 dB from a
  29-pixel pan on, qpel in the same file.
- Drift: Xvid build 9 at QP 2 without an I-VOP in 228 frames falls to 43 dB; FFmpeg's own simple
  IDCT against the Xvid IDCT falls the same way, the engine stays closer (49 dB): IDCT mismatch, not
  a decode error. FFmpeg's 1080p ASP encode with a 250-frame GOP holds 64 dB.
- Damaged streams: where software conceals (`xvid-ttm1`, `messenger.h263`), the engine stops at the
  error and leaves the rest of the picture unwritten: 4 dB on `ttm1`. FFmpeg ignores
  `V4L2_BUF_FLAG_ERROR` for every codec.
- Refused and decoded in software, checked: data partitioning, H.263 long vectors (`pooch.mov`),
  H.263+ UMV, interlaced with B-VOPs.
- Both kernels, 6.18.60 and 7.3.1, built from the confs, Cedrus from their packages: the same PSNR
  to the hundredth on 35 clips. 1080p ASP with B-VOPs 143 fps, software 86; 720p 311, software 187;
  4CIF H.263 304, software 257; QCIF H.263 slower than software, a request's cost over 99
  macroblocks. `codecs.sh` with the new FFmpeg unchanged on both, its one VC-1 timeout included.
- `0804` built in, 6.18.60 and 7.3.1: the same JPEG bytes and PSNR on both, 1920x1080, 1366x768,
  4096x2160 at quality 85.
- Resolution probe, 3-frame clips at 1920x1080 up to 8192x4320: H.264, HEVC, Main10, VP8, VP9 and
  profile 2 decode to 4096x2304 and go to software past it; MPEG-2 to 3840x2160; MPEG-4 to
  1920x1080, refused from 2560 wide; H.263 to 1408x1152. MJPEG decoded to 4096x2304 though `0803`
  capped JPEG at 2048: `S_FMT` sized the coded format by the engine it replaced, MPEG-2's, the one
  the context opens with. `0807` sizes it by its own; JPEG decodes bit-near exact, 79–81 dB, to
  6000x4000 and 4096x4096, so its cap is 6144x6144, not 2048. At 8192 the box runs out of memory.
- Encode ladder: H.264 to 4096x2304; at 5120x2880 ffmpeg aborted on a stride assertion after the
  driver clamped the format. `ffmpeg/0032` refuses at init, "larger than the encoder takes". JPEG to
  4096x4096.
- FFmpeg's MJPEG encoder through V4L2, `ffmpeg/0033` and an `MJPG` engine in `0804`: 1920x1080,
  1366x768 and 4096x2160 encode at full range; `-q:v` 2 / 5 / 15 give luma 58 / 49 / 34–40 dB. A
  first build gave the `MJPG` engine the JPEG engine's quality control again: one handler holds
  every engine's controls, the second registration failed, and opening the encoder oopsed in
  `__v4l2_ctrl_handler_setup`; a reboot freed the module.
- Every Cedrus decoder capped at 4096x2304 by our driver, not the hardware. With the caps lifted (a
  probe module): HEVC and VP9 8-bit decode bit exact to 8192x4320; HEVC Main10 to 6144x3456, 7680
  wide fails; VP9 profile 2 fails at 7680. MPEG-4 decodes right to 4080x2160 (the engine's 8-bit
  macroblock counts; our cap was 2048). MPEG-2 right at 4000x2250, broken at 4000x3000. H.264 and
  VP8 broken past 4096x2304, with IOMMU faults: their real limit. HEVC 6144x3072 failed once (2
  frames, faults) and passed bit exact on a second run: a repeatable suite before any cap moves.

## 2026-10-31 — the caps measured, `0808`

`tools/validate/video.py` against a probe module with each cap at the engine's register limit (MPEG
engines 4096x4080, HEVC 16383x16383):

- HEVC 8192x8192 hangs the SoC; the watchdog reset it. 8192x4320 is the HEVC and VP9 cap; VP9 at
  8192x8192 was not reached.
- H.264 at 4080x4080 decodes broken: 4096 wide holds 2304 lines, no more.
- JPEG 6144x6144 hung the SoC in the full run, 6000x4000 decodes; the cap goes to 6000x4000.
- `0808`: those caps, the 10-bit SPS refused past 6144x3456 (7680x4320 hangs), MPEG-4 to 4080.
- A wrong turn: the suite's MPEG-4 and H.263 came out "software" and MJPEG encode "broken". The
  FFmpeg in use, rebuilt from an older tree, lacked `ffmpeg/0019`, and the run had passed a watchdog
  reset, which loads the packaged module over the probe one. Rebuilt from a clean 9.0.2 with every
  patch: MPEG-4 to 4080x2160, MJPEG encode to 4096x4096 at 54–56 dB.
- Frame rates, decoder alone, 3840x2160: H.264 31, HEVC 61, Main10 33, VP9 43, profile 2 25, VP8 45,
  MPEG-4 32, JPEG 28. H.264 encode 24 against libx264 `ultrafast` 8.4; MJPEG encode 10.8 against
  FFmpeg's `mjpeg` 6.9.
- `mjpeg_v4l2m2m` decodes nothing after an end of stream: a looped input gets its first pass only.
  The restart command goes out; the capture queue stays done. Open.

## 2026-11-01 — Wi-Fi was channel 1

The slow receive and the drops were the AP's own three networks on channel 1. Channel 6 at 40 MHz
cleared both: near, 72.6 Mbit/s down and 62.2 up; at 15 m, 24.5–33.9 down and 22.6 up, sending at
MCS 7 and receiving at MCS 2-3. Channel 6 at 20 MHz stayed at 18.9 down. A firmware restart does not
clear it.

## 2026-11-01 — HLG

The 4K TV does not support HLG, so a player cannot be checked on it.

## 2026-11-02 — the display engine's tone mapping, `0276`

Fuseamp's side: its commits `c78a1e5` and `27be9b3`, its `docs/prism.md` "Display-engine LUT
experiment", its `tools/kernel/` (the experimental patch and its README).

- Allwinner's DE330 driver (`de_cdc.c`, `de330_feat.c`, Orange Pi's 5.4 `sun50iw9` tree): a CDC on
  VI channels 0 and 1, channel 0's with a CSC on each side of the LUT; a 17-point LUT of 30-bit
  nodes in eight parity banks at `0x1000`–`0x6400` of the channel's `0x8000`; vendor tables per SDR,
  WCG, HDR10, HLG and HDR10+ pair. Its RCQ path marks the banks dirty every frame.
- First probes, by `/dev/mem` on the installed kernel: the vendor's HDR10-to-SDR table and a Prism
  table on AFBC 4K, a 1:1 crop on the 2256x1504 monitor: 216 / 215 shown in 4 s, all 4,913 nodes
  read back. Python's bulk writes took a bus error; 32-bit aligned writes from C++ do not.
- The experimental patch (Fuseamp's `tools/kernel/0001`): plane properties `SUNXI_CDC_LUT3D_SIZE`
  and `SUNXI_CDC_LUT3D` on the RCQ, built on the cached 6.18.60 tree in a container of its own.
  Booted by kexec, never installed: the Image, the installed initrd, the live tree from
  `/sys/firmware/fdt` (U-Boot's memory size in it) with a writeback node added by `fdtput`
  (`allwinner,sun50i-h616-de33-wb` at `0x11000`, both mixers' `port@1` `endpoint@1`), and
  `systemd.mask=fuseamp.service` on the command line. A kexec without `--initrd` panics, no root
  device, and the watchdog boots the installed kernel.
- LUT RAM read back while the CDC runs differs from what was written; after it stops, every node
  matches. Writeback is the check, not readback.
- `0276`, the patch reviewed: the table uploaded once a blob and on becoming visible (300 flips on
  one blob kept it in all 30 captures), channel 1's CDC without the CSC regions, the new state
  passed to the update, properties per plane as `COLOR_ENCODING`'s are. Built by
  `./build.sh kernel kernel/sunxi64.conf`; its Image kexec'd: short blobs, a reserved field set,
  unknown or past 32 bits refused; RGB bypass, identity, a channel mix, an inversion switched while
  active and back, disabled again, NV12 bypass, identity and Y inverted, all within one 8-bit code.
  A constant table on NV12: red, green and blue carry Y, Cb, Cr.
- This driver's fixed channel map: mixer 0 VI 0 (plane 33 here), UI 6 and 7; mixer 1 VI 1, VI 2 and
  UI 8. One VI plane with a CDC on the HDMI mixer; the UI channels have a matrix CSC only. The
  vendor's single-screen map puts VI 1, CDC and all, on mixer 0 too.
- Prism's tables against libplacebo, 64 YUV patches each, writeback in 8-bit RGB: the engine is
  within 1–2 codes of the 17-point table interpolated trilinearly, 32 off tetrahedrally. Against a
  65-point bake, max and mean: HDR10 to SDR 72 / 4.0 (the 72 one saturated out-of-gamut patch, the
  next 15), HLG to SDR 11 / 2.4, SDR BT.2020 to BT.709 8 / 1.7, SDR BT.709 8-bit to PQ 2 / 0.6, HLG
  to PQ 10 / 1.2, HDR10 to HLG 56 / 5.6.
- HDMI: `HDR_OUTPUT_METADATA` with PQ and `Colorspace` `BT2020_RGB`: `FC_PACKET_TX_EN` 0x9f, the DRM
  InfoFrame version 1, 26 bytes, EOTF 2 and the metadata as sent; AVI C 3, EC 6. The output stays
  RGB 8-bit (`VP_PR_CD` 0x40) whatever `max bpc`: the mixer offers RGB888 and 4:2:0 alone, and
  dw-hdmi lists RGB888 ahead of every deeper format.
- 10-bit 4:4:4 tried on the monitor (TMDS 294.6 MHz of its 300): `TX_INVID0` 0x19, `VP_PR_CD` 0x50,
  but the `hdmi` clock came out 269.1 MHz for 294.4. The video PLL steps by 12 MHz and divides by
  whole numbers; the TCON took 471 / 2, and 5/4 of that has no divider. Dropped for 4:2:2, whose
  12-bit container runs at the pixel clock: offered for HDR alone (`max bpc` 10 or more, an
  `HDR_OUTPUT_METADATA` EOTF other than SDR, a sink with YCbCr 4:2:2); SDR stays RGB 8-bit. On the
  wire unchecked yet.
- Pixel clocks the CCU picks, by its own rounding (2256x1504 checked: 235.5 MHz from 471 / 2):
  3840x2160 at 23.976 295.5 MHz (−4056 ppm), at 59.94 591.0 (−4056 ppm), 1920x1080 at 23.976 74.143
  (−444 ppm), at 59.94 148.0 (−2370 ppm); 24, 30, 50, 60 Hz exact.
- Tried: a sigma-delta table on `pll-video0` for the four 1000/1001 clocks, 74.176, 148.352, 296.703
  and 593.407 MHz (24 MHz × (n + pattern / 2^17), the audio PLL's form, pattern register `0x140`,
  enable bit 24). A first mode set to 1920x1080 at 59.94 left `PAT0` 0x4001735f (the pattern, its
  enable cleared) and the PLL integer at 471 MHz; the second hung the box, no network and no
  watchdog reset, until power was cut. Without a serial console the cause is unseen: the pattern
  register, the enable order, or the TCON losing its clock while the mixer runs. Not taken.
- `0277`, the TCON's FIFO underflow (debug register `0xfc`, bits 30 and 31, latched until cleared)
  counted at each vblank in `dri/0/crtc-0/underruns`: 0 at rest. `display_box`, 10 s each,
  2256x1504@60, 4K pictures shrunk to the screen, with and without the interface: AFBC (0096's limit
  lifted by a test knob) 0 underflows, 224–233 shown, 0–7 dropped, on Main10 HDR10, Dolby Vision 8.1
  and 8-bit 4K; the same as linear P010, 270–513 underflows, 49–121 shown; 8-bit linear, 12–13
  underflows, 232 shown. The 4K breakup is the linear fallback's bus load.
- `0096` revised to the line-time model at 90%: 3840x2160 onto 1269 lines needs 87% at 696 MHz and
  passes; at the old 600 MHz it needed 101%, the breakup seen then.
- `0278` with PQ, `max bpc` 10, `Colorspace` `BT2020_YCC`: `TX_INVID0` 0x12 (YCbCr 4:2:2, 12-bit),
  AVI Y 1, EC 6, the DRM InfoFrame EOTF 2; HLG the same with EOTF 3; `max bpc` 8 or SDR: RGB 8-bit,
  the DRM InfoFrame off. `tcon-tv0` and `hdmi` both 235.5 MHz. The picture on the wire unseen.
- AFBC on UI channel 6: the vendor's DE330 lists a decoder there (`fbd_u_reg`, the VI one's first
  0x58 bytes), and a test kernel offered and scanned it out 1:1. No client: the Mali-G31's
  `AFBC_FEATURES` is 0x10001, bit 0 set, so Mesa 25.0 allocates every AFBC request linear. Not
  taken.
- UI planes scale 2256x1504 to 1920x1080 and 1280x720 and back in TEST_ONLY commits; DE33's UI
  scaler holds 2048 pixels a line: `0279` refuses a wider source scaled (2256x1504 to 1920x1080
  `EINVAL`, 2048x1366 to 1920x1080 and 1:1 accepted).
- The tvbian build with `0096` revised and `0276`–`0279`, kexec'd: AFBC 4K shrunk to the screen
  accepted, 0 underflows, Main10 HDR10 and 8-bit 4K 232 shown, none dropped, in 10 s.
  `tools/validate/display.py`: 18 passed, 0 failed (the LUT within 2 codes on every case, the HDMI
  cases, no underflow at rest).

## 2026-11-03 — `afbc_shrink_margin`

- `0096`'s 90% is `sun8i_mixer.afbc_shrink_margin`, percent, clamped to 50–150, read at each check.
  4K Main10 at 1400x1050 (97.9% of a line time): 90, 97 and 98 refuse it, the player goes linear,
  16–28 underflows and 14–82 shown in 6 s; 100 takes it, 0 underflows, 137 shown.
- Swept at 150, every mode the monitor lists, 10 s each, Main10 HDR10 and Dolby Vision 8.1, no
  interface, the stand-in interface and overlay islands (drawn 1.5 times smaller off 2256x1504),
  after 60 s warm-up, 58–61 °C. The share of a line time each needs, and the underflows: 2256x1504
  87.3%, 1920x1080 74.5%, 1920x1200 81.7%, 1280x800 81.6%, 1400x1050 97.9%, 1024x768 100.1%, 800x600
  100.3%: 0 in every load. 1600x1200 99.3% and 640x480 104.2%: 571–583, every refresh, with or
  without the interface; a 1080p picture at those modes 0.
- Not monotonic past 98%: the one-pixel-a-clock model holds to about ±2%. 90 kept: the lowest
  failure is 99.3%, and a 4K screen's interface traffic was not in these runs.

## 2026-11-03 — keeping boot0 on install: not pursued

Read from the stock boot package at 24576: four TOC1 items with `run_addr` 0, each carrying its own
Allwinner head. `u-boot` is AArch32, a `uboot` spare head with a checksum and run address
`0x4a000000`; `monitor` is BL31, AArch64, a `monitor`/`CHKv1.0` head at `0x48000000`. Behind stock
`boot0`, ours would need TF-A relinked from `0x40000000` behind a `monitor` head and U-Boot proper
behind a `uboot` head, `PRELOADED_BL33_BASE` to match. FEL recovers the box from any state, so the
gain, the unit's own DRAM init on the eMMC, is not worth it; the install keeps writing our SPL.

## 2026-11-03 — VI channel 1 has no CDC

- Mixer 1's VI 1 moved onto mixer 0, the vendor's single-screen map (`sun50i_planes.c`: mixer 0
  `{0, 1, 6, 7}`, mixer 1 `{2, 8}`, the primary the first UI channel): plane 41 on CRTC 0, overlay,
  zpos 0–3, ARGB8888 and YUV, scanned out. Its `SUNXI_CDC_LUT3D` changed nothing: every table came
  back as identity, `display.py` 7 failures on it.
- With plane 41 shown, channel 1's overlay attribute read `0xff008403`, as channel 0's; its CDC
  control at `0x01128000` and LUT at `0x01129000` read 0 and kept no write, plain data offsets
  included. The vendor's mode 0 lists a CDC on channels 0 and 1 at the same offset; this H313
  decodes none on channel 1. Channel 0's, with the plane shown: control 1, the LUT programmed.
- `0276` exposes the CDC on channel 0 alone, its CSC stages always set; the map change dropped, no
  CDC to gain. `display.py` 18 passed on the kexec'd build. The interface into PQ stays a GPU pass.

## 2026-11-03 — HDR10+ dynamic metadata out, `0280`–`0281`

- dw-hdmi has one vendor-specific InfoFrame slot, HDMI's own VSIF's, and treats any
  `HDR_OUTPUT_METADATA` change as a mode set. This tree's HDMI encoder is a bridge chain with
  `drm_bridge_connector`, so a property on dw-hdmi's own connector never appears: the payload rides
  in `sun4i_crtc_state`, beside the format and encoding the encoder already reads.
- `HDR10PLUS_VSIF` on each CRTC, the 27-byte CTA-861-G payload. `display.py`, the kexec'd build: a
  26-byte blob and a wrong OUI refused (`EINVAL`); a payload, then a second one, committed without
  `ALLOW_MODESET`: `VSDSIZE` 27, the OUI and all 24 payload bytes as sent, `DATAUTO0` VSD set; none:
  HDMI's VSIF back, OUI `03 0c 00`, size 4; a payload kept across a `max bpc` mode set. 24 passed.
- dw-hdmi sends HDMI's VSIF on every HDMI sink, format none where the mode needs nothing. At 4K 24,
  25 and 30 Hz the VSIF carries `HDMI_VIC` and the AVI none; with HDR10+ in the slot the AVI takes
  the CTA VIC. Not seen on the wire: the monitor lists no 4K mode.
- 7.3: `0280` applies as it is; `0281` rewritten for `drm_atomic_commit` and the blob replace's
  `max_size`, its objects built clean.

## 2026-11-03 — 1000/1001 refresh by the closest rate, `0282`–`0283`

- The video PLLs are integer, 24 MHz × N / M, M 1 or 2, the TCON dividing by M × P and the HDMI
  clock by 1–16. Searched over every N, M and divider with the TCON and HDMI clocks equal: 80.8 ppm
  at 4K 23.976 and 29.97, 1080p 23.976 and 59.94 (816 MHz × 4 / 11 and its halves), −444 ppm at 4K
  59.94. The CCU rounds down and never reached them; the fractional PLL, which hung the box, is not
  needed.
- `CCU_FEATURE_CLOSEST_RATE`, A64's flag: NM, divider and mux clocks honour it, MP did not. With MP
  honouring it and the H616's video PLLs, TV TCONs and HDMI clock flagged, measured from the clock
  tree during each mode: 1080p 59.94 148.2857 → 148.3636 MHz (−444 → +80.8 ppm), 720p 59.94 74.1429
  → 74.1818 MHz, the HDMI clock equal to the TCON's; 60 Hz modes and 2256x1504 unchanged. No 4K mode
  on the monitor. `display.py` 24 passed on the combined build.
- Before and after: 640x480 at 59.94, the TCON 453 MHz / 18, 25.167 MHz, the HDMI clock's divider
  stops at 16, so it takes `pll-video2`, 24.750 MHz.

## 2026-11-03 — no early flip event, `0284`

- A player committing `NONBLOCK | PAGE_FLIP_EVENT` only after the previous flip event had 3 to 23
  commits refused `EBUSY` in 8 s of 1080p VP9 AFBC on a video plane: each a dropped picture.
- Return probes: every refusal came out of `drm_atomic_helper_setup_commit`,
  `[PLANE:45:plane-2] busy with a previous commit`, plane-2 being one the player sets with no CRTC,
  so tracked by the commit's fake commit, done only at `hw_done`. Before each, the accepted commit's
  work started up to 10 ms late and a vblank in between sent a flip event:
  `sun4i_crtc_finish_page_flip` falls back to `crtc->state->event`, which `0251` added for the
  self-timed writeback CRTC, and a nonblocking commit's state is swapped in before its work runs.
- `0284` takes that path only for a CRTC without vblank. Kexec'd: 0 refused in 6 runs, 5 of them
  with 0 of 196 pictures dropped; the first after boot dropped 61 with none refused. `display.py` 24
  passed, writeback included.
- `0281` moved after `0036` in `kernel/sunxi64.conf`: written against 6.18's `drm_atomic_state`, it
  did not apply where it was, among the 7.2 drivers' `drm_atomic_commit`.

## 2026-11-03 — H.264 4K keeps up, `0810`

- H.264 4K High 5.1 at 24 fps, AFBC and scaled to 2256x1504, dropped 52–55 of 198 pictures, and a
  seek past its one early keyframe showed nothing. FFmpeg's `v4l2request` to a null sink, full size:
  23 fps; HEVC 4K 37; H.264 1080p 119.
- The engine is the limit: kprobes on the H.264 trigger and the IRQ, full size, 41.8 ms busy and 0.4
  ms idle a picture, HEVC 25.8; scaled to 2256x1504, 38.5. `pll-ve` 600 → 648 → 696 MHz by register:
  12.3, 12.0, 11.9 s, so memory, not clock. `VE_MODE` `BW_256` slower, 13.8 s; the 1 MiB write mode
  11.9. Stock runs DRAM and `mbus` as we do.
- Every picture referenced linear NV12, `cedrus_dec_format_picture_write` 3840x2160 `NV12`. `0810`
  puts a scaled H.264 picture's hidden reconstruction in 32x32 tiles: 33 ms a picture, not 38.5; 0
  of 198 dropped twice, the seek at 2.5 s; VP9 1080p and HEVC 4K 0 dropped; `display.py` 24 passed.
  Fuseamp's frame sums, all 288 scaled pictures, identical to the linear reference's.

## 2026-11-03 — `display.py` unattended

- 32 passed on the 0284 + 0810 kernel: the CDC LUT cases, planes 33 and 41 composed exactly with the
  video scaled, the LUT mapping its plane alone, 3598 paced nonblocking commits in 60 s none
  refused, HDMI, HDR10+, underruns, and the four synthetic screens. The monitor lists HDR itself, so
  the main pass ran on it; its EDID and 2256x1504 came back after the synthetic ones.
- The writeback takes no full-size capture at 2256x1504; half size, which it scales to, does.
- Mainline dw-hdmi sends PQ or HLG to a screen that lists neither; Rockchip's sends neither.
- `display.py` `rating`: 4K60, 4K30, 4K24, 1080p120, 1080p60, 1080p24, 720p120 and 720p60 sustained,
  10 s each, the video at the mode's size, no TCON underflow, no kernel warning; 4K120 and 8K
  pruned. Largest 4K60, fastest 1080p120; 33 passed.

## 2026-11-03 — `HZ` 300

- `kernel/sunxi64.fragment`: `PREEMPT`, already on, and `HZ` 300 from 250. `cyclictest` under
  `stress-ng --cpu 4 --io 2 --vm 1`, 60 s, every CPU: an ordinary thread's worst wakeup 12.7 ms at
  250, 10.4–11.2 ms at 300 over three runs, the average 170–177 µs either way; a real-time thread's
  worst 1.0–1.7 ms against 1.25, within its run-to-run spread.

## 2026-11-03 — HDMI and TV TCON share a reachable rate, `0285`

- Baseline, `modetest -M sun4i-drm -s 70:#22`: `tcon-tv0` 25,166,666 Hz from `pll-video0`, HDMI
  24,750,000 Hz from `pll-video2`. All 23 monitor modes swept; 1680×945 also differs: TCON
  131,333,333 Hz from `pll-video0-4x`, HDMI 132 MHz from `pll-video2-4x`.
- Fractional modes on the same divider differ in reporting only: MP truncates, HDMI's M divider
  rounds up; 1080p59.94 reports 148,363,636 / 148,363,637 Hz. An M divider on `tcon-tv0` reports as
  HDMI does.
- Kexec'd with `0285` on both TV TCONs: all 23 monitor modes and the 16 synthetic HDMI 2.0 modes of
  `display.hdr_edid(ladder=True)` set; `hdmi` and `tcon-tv0` have identical `clk_rate` and
  `clk_parent` in every mode. Synthetic-mode rates and parents match the baseline; 640×480 and
  1680×945 move to reachable rates.
- The baseline already gives 296,571,429 Hz at 4K 23.976 and 29.97 and 594 MHz at 4K 59.94: the
  `0283` figures in the README were computed without the PLL rate bounds; corrected there.
- `python3 /root/display.py`: 20 passed, 0 failed. Writeback checks skipped: the installed tree has
  no writeback connector.
- `tcon-tv1` feeds the TV encoder, 216 MHz on `pll-video1` by the tree; on video0 only, with HDMI at
  2256×1504 holding it at 471 MHz, no M reaches 27 MHz. `0285` narrowed to `tcon-tv0`.
- 7.3 does not take `CONFIG_BOOTPARAM_SOFTLOCKUP_PANIC=y`: 7.0 made it a count. The next fragments
  set 1.

## 2026-11-04 — lockups, the RCU stall timeout, Cedrus fixes

- `lib/test_lockup.c` built out of tree. One CPU, interrupts off:
  `CPU0: Watchdog detected hard LOCKUP on cpu 1` 15.3 s in; with `hardlockup_panic` 1 the box reset
  43 s in. All CPUs: the 16 s hardware watchdog reset it 32 s in.
- One CPU, preemption off, 30 s: no soft-lockup report. `rcu_preempt self-detected stall` came
  first, 21.0 s in, and its report touches the soft-lockup clock: a 50 s spin reported
  `stuck for 49s` at 48.6 s. `rcupdate.rcu_cpu_stall_timeout` 60, Rockchip's: the report at 24.9 s,
  the box reset about 53 s in. The fragment sets `CONFIG_RCU_CPU_STALL_TIMEOUT=60` on sunxi64 and
  meson64.
- VP9 profile 2: key frames exact, every inter frame of 1920x1080 and 1280x1080 wrong, 64 dB;
  640x480, 1280x720, 1920x1072 and 1920x1088 exact. A test kernel with the low 2 bits plane placed
  after the chroma at the frame's height, not the buffer's 1088, decodes every size exact: `0811`.
- H.263's run-to-run difference was the suite: `-v verbose` merged into the `framemd5` output put a
  log prefix on a record now and then, 5 of 40 runs one frame short while FFmpeg reported 3 decoded.
  `md5_lines` finds a record anywhere on its line; three ladders since, 12 of 12 pass.
- `0808`'s JPEG and MPEG-4 sizes moved into `0803` and `0806`; the series' end state is unchanged,
  both kernels build.
- `0096`'s default margin 98: the 2026-11-03 sweep's lowest failure needed 99.3%, 1400x1050 at 97.9%
  plays with 0 underflows.

## 2026-11-04 — CMA from `BOARD_CMA`, 16 MiB

- In use, `CmaTotal` less `CmaFree` every 50 ms: a 4K60 synthetic screen with a 4K NV12 video plane
  and the interface over it, flipped at a player's pace, while the engine decoded 4K HEVC Main10
  with AFBC frames through `v4l2request`, iperf3 from plex on Wi-Fi: 2.5 MiB, flat at idle; 1726
  commits, 57.5/s. Cedrus and the mixer allocate through their IOMMUs. USB was idle: nothing is
  attached.
- `cma=16M` by `tvb.conf` and `u-boot-update`: pool 16 MiB, idle 1.5 MiB, the same load 1.5 MiB,
  1737 commits, none refused; `display.py` 20 passed.

## 2026-11-04 — Wi-Fi silent after a group rekey

- 16:07:10 UTC `wpa_supplicant` completed a group rekey (`GTK=CCMP`), `atbm_log` `2/2 Group`. From
  16:08:55 every NTP request timed out, and the Mac's ARP entry for the box stayed incomplete; no
  disconnect, no driver message. Traffic came back at 16:44:47 by itself.
- The boot ran on throughout (`journalctl --list-boots`: one boot from 15:59 UTC): no hang, so the
  watchdog had nothing to fire on. No allocation failure on `cma=16M`.

## 2026-11-04 — H.264 and HEVC at a 32-byte pitch, `0812`; JPEG by area

- HEVC 4080x4080 never passed on the Tanix: the 2026-10-31 passes are the H96 Max's (RK3518) runs.
  Intra pictures exact, every inter picture's chroma wrong (15 dB), whole width, worst at the left.
- By width: HEVC 1936, 2000, 4048, 4080 wide fail; 1920, 3840, 4064 and 3840x4080 are exact; H.264
  1936 fails, 1920 exact; VP9 and VP9 profile 2 at 1936 exact. An odd multiple of 16 breaks H.264
  and HEVC.
- Lines at 32 bytes alone broke intra pictures too: the stride registers were computed from the
  width, not `bytesperline`. Registers from `bytesperline` and 32-byte lines: H.264 and HEVC exact,
  VP9 broken, so VP9 fetches at the stride it is given and keeps 16. `0812`.
- MJPEG 4096x4096: `failed to configure engine job: -22` on every frame. `0807` sizes a coded format
  by its own engine; JPEG's 6000x4000 limit then clamped 4096 lines to 4000 and the header check
  refused the frame. With the limit opened: 4096x4096, 6000x4000, 4000x6000, 4096x5120 at 78–81 dB.
  `0803` now takes 6000 a side and 24 Mpixel; 6144x4096 is refused frame by frame, the box up.
- `video.py` decode and scale on the result: HEVC 4080x4080 and MJPEG 4096x4096 pass, nothing worse
  than the 0811 run; HEVC 16384x8640 refused as before, its software reference OOM-killed as before.

## 2026-11-04 — Wi-Fi across forced group rekeys

- The H96 Max 3518D as a WPA2-PSK CCMP access point on 2.4 GHz channel 1, `wpa_group_rekey=20`, PTK
  rekey off, beside its own client link; the Tanix joined it from a NetworkManager profile that a
  script left after 540 s.
- 27 group rekeys (hostapd's `group key handshake completed`, the Tanix's
  `Group rekeying completed`): 505 of 505 one-second probes answered, a unicast ping to a pinned
  neighbour and one behind a fresh ARP broadcast, the broadcast under the group key. No stall.
- An idle soak on the home network, 18:09–20:20 UTC, 30 s pings: 258 of 262, the 4 misses single and
  apart; the home access point did not rekey in that time.

## 2026-11-04 — `RCQ sync timed out`, not reproduced

- The warning is `sun8i_rdma_sync`'s, from `0252`'s CRTC disable and `0238`'s writeback: a 40 ms
  poll for the queue's fetch, which comes at the next frame start, 41.7 ms away at 24 Hz.
- 159 mode sets between 1920x1080@24 and @60 on a synthetic HDMI 2.0 screen, a plane up: 0 timeouts.
  The 40 ms bound is not shown to be the cause; nothing changed.
- `0813` and FFmpeg `0037`: a 10-bit 1080p HEVC picture read by the CPU, 63.6 ms from coherent
  CAPTURE buffers, 8.1 ms with `cacheable=1`; frame md5s identical.

## 2026-11-05 — HDMI PCM rewind refused by the audio hub

- Installed `alsa-utils` and `libasound2-dev`; GCC was present. `aplay -l`: HDMI card 1, device 0;
  kernel `6.18.60-tvb-sunxi64`, alsa-lib `1.2.14-1+deb13u1`.
- Fuseamp stopped for the runs. Raw `hw:1,0`, bypassing plugins: S16_LE and S32_LE twice each, 48
  kHz stereo, 9600-frame buffer, 1200-frame periods, 300 ms tone before rewind. Initial full
  request: `rewindable=9600 rewind=0 state=RUNNING` in all four runs.
- `tools/validate/pcm-rewind.c` leaves two periods queued for the post-fix no-xrun check:
  `rewindable=9600 requested=7200 rewind=0 state=RUNNING`, both formats twice; refill and
  drop/prepare/restart: `restart=ok xruns=0`, no recovery, all exit 0. Logs:
  `build/logs/tanix-tx1-v2/20261105-hdmi-rewind.log` and
  `build/logs/tanix-tx1-v2/20261105-hdmi-rewind-guarded.log`.
- Extracted `build/kernel-tarballs/linux-6.18.44.tar.xz` into `/tmp/tvb-hdmi-rewind/`; attempted
  every `kernel/sunxi64.conf` patch in order. Existing failures: `0214`, `0215`, `0226`, `0072`,
  `0073`, `0074`; audio patches apply. Application log: `/tmp/tvb-hdmi-rewind/apply.log`. No
  unrelated patch changed.
- `sound/soc/sunxi/sun50i-h616-ahub.c:1003–1006` sets `NO_REWINDS` on every HDMI playback stream.
  Its ack at line 1083 skips conversion for ordinary PCM. `sound/core/pcm_lib.c:2246` rejects
  backward pointer updates under that flag; `sound/core/pcm_native.c:3023` maps the error to zero
  frames. The pointer uses `snd_dmaengine_pcm_pointer`; sun6i DMA advertises burst residue at
  `drivers/dma/sun6i-dma.c:1371`, not descriptor-only residue.
- alsa-lib v1.2.14 `src/pcm/pcm_hw.c:821–845`: rewindable uses the mapped pointer distance; rewind
  uses the ioctl. No hub module parameter or sysfs switch exposes `NO_REWINDS`. Switching
  S16_LE/S32_LE twice each leaves the failure unchanged; the flag itself cannot be toggled without a
  new kernel. No kernel build or kernel swap performed here.
- `0904` keeps `SYNC_APPLPTR` and applies `NO_REWINDS` only to IEC958 in `hw_params`;
  `sound/core/pcm_native.c:822` copies the resulting `params->info` into `runtime->info`. Listed in
  both kernel configs; `patch --dry-run --batch -p1` passes on the audio-patched 6.18.44 tree.
  IEC958's restriction stays in place. Hardware result pending the host build.
- Post-build box test: stop Fuseamp, compile the copied reproducer with
  `gcc -O2 -Wall -Wextra /tmp/pcm-rewind.c -lasound -lm -o /tmp/pcm-rewind`; run
  `timeout 5 /tmp/pcm-rewind hw:1,0 S16_LE` and `timeout 5 /tmp/pcm-rewind hw:1,0 S32_LE`, twice
  each. Expected: `rewindable=9600 requested=7200 rewind=7200` (pointer timing may lower the first
  two), `rewind=requested > 0`, `state=RUNNING`, `restart=ok xruns=0`, exit 0. Check the kernel
  journal for new audio/DMA warnings. Then restart Fuseamp and check seek/stop by ear.

- Fuseamp restarted with the requested `setsid -f` command; `pgrep -a -x fuseamp`:
  `4223 ./fuseamp -platform eglfs`. Kernel journal over the preceding ten minutes: no entries.
- Prettier ran with `--print-width 100 --prose-wrap always` on the four changed Markdown files;
  `git diff --check` passed for the touched files. The full-tree check reports existing whitespace
  in `boards/h96max-m20/board.patch`. Nothing staged, committed, pushed or branched.

## 2026-11-07 — HDR on a PC monitor; the green background

- The owner's monitor (2256x1504, HDR10 in its EDID, YCbCr 4:4:4 and 4:2:2, deep colour to 16 bits,
  300 MHz TMDS), 6.18.62 with a test `0286`: HDR10 at 8 bpc goes as RGB, a picture; at 10 bpc as
  YCbCr 4:2:2 (`0278`), no signal at 2256x1504, a picture at 1920x1080@60.
- At 1080p60 4:2:2 HDR10, an area no layer covers shows green with `BKCOLOR` at the 10-bit YUV
  black, 8-bit YUV black or RGB black alike: `0286`'s premise is wrong, the patch dropped.

## 2026-11-07 — HDR in 10 bits: the H616 PHY table read by TMDS rate

- `0278` with 4:2:2 offered only at a CEA mode (`drm_match_cea_mode`), 6.18.62, the owner's monitor,
  HDR10 at 10 bpc: 2256x1504 goes as RGB 8-bit, a picture. Its first 1080p60 (mode #3, negative
  syncs, its own timing, not VIC 16) also goes as RGB, a picture. The earlier 4:2:2 picture at
  1080p60 was that same non-CEA mode #3, so CEA is not what this monitor needs; untested at VIC 16
  (#4).
- 10-bit RGB: Allwinner's BSP (`orangepi-xunlong/linux-orangepi`, `orange-pi-5.4-sun50iw9`,
  `disp2/hdmi2`) sets the CCU `hdmi` clock to the TCON's rate, the pixel clock, and passes the PHY
  the pixel clock and colour depth (`phy_aw_configure`); its PHY table has 10- and 12-bit entries.
  The PHY's PLL makes the 5/4 TMDS clock. The earlier try asked the CCU for the TMDS rate, 294.4
  MHz, and got 269.1: a wrong request, not a hardware limit. Our dw-hdmi picks the PHY's 10-bit
  settings (`res[depth]`), and the glue sets `tmds` to the pixel clock for RGB.
- A test patch: HDR at 10 bpc offered as 10-bit RGB first, the mixer and CSC taking it as RGB. The
  controller sends it (`TX_INVID0` 0x03, `VP_PR_CD` 0x50, AVI RGB, `PHY_STAT0` 0xf3, PHY locked),
  but the owner's monitor shows no signal at 2256x1504 or VIC 16 1080p60, with the CCU `hdmi` clock
  at the pixel rate (235.5, 148.5 MHz) or asked for 5/4 (got 297.0, 198.0).
- The same monitor on the H96 Max 3518 (6.1.172), forced through `color_format` and `color_depth`:
  HDR10 as 10-bit RGB at 2256x1504 and at VIC 16, and as YCbCr 4:2:2 at 2256x1504, all three a
  picture. The monitor takes both; the Tanix's HDMI path fails 10-bit RGB everywhere and 4:2:2 at
  235.5 MHz.
- Cause, from Allwinner's BSP (`phy.c`, its default PHY path): its PHY table is keyed by pixel
  clock, its 10-bit rows at 148.5 and 237.6 MHz `0x214C` (HDMI 1.4), at 297 MHz `0x3B4C` (HDMI 2.0);
  for 4:2:2 it programs the 8-bit row. 7.2's dw-hdmi keys `sun50i_h616_mpll_cfg` by TMDS clock and
  by `res[depth]`: 10-bit RGB at 235.5 or 148.5 MHz lands on `0x3b4c`, 4:2:2's 12-bit container on
  the 12-bit row (`0x5a64` at 235.5 MHz). The BSP has no 235.5 MHz row at all.
- A test patch: 4:2:2 on the 8-bit PHY row; the TMDS ≤ 297 MHz row's 10-bit entry `0x214c`; the CCU
  `hdmi` clock at the pixel rate. HDR10, the owner's monitor: 10-bit RGB at 2256x1504 and at VIC 16,
  4:2:2 at 2256x1504 and at VIC 16, all four a picture (`VP_PR_CD` 0x50 for RGB, AVI 4:2:2 for
  4:2:2).
- `0278` now the mixer's 10-bit RGB and 4:2:2 output; `0287` 4:2:2 on the 8-bit PHY setting; `0288`
  the H616 table bounded by the BSP's five TMDS bands (45.25, 92.5, 185, 340, 594 MHz), the 8-bit
  settings at 27, 74.25, 148.5, 297 and 594 MHz unchanged; `0289` HDR as 10-bit RGB where the sink's
  TMDS limit allows, else 4:2:2. On that kernel HDR at 10 bpc picks 10-bit RGB at 2256x1504 and at
  VIC 16 (`VP_PR_CD` 0x50). `sunxi64-next` takes the same set, `0289` on 7.3's colour-format bits.

## 2026-11-07 — 4K streams ramping after a resume

- 4K streams ramped up for about 30 s after a resume. One was the network: four waits for data in 33
  s at 46–61 Mbit/s. The other was the player falling behind, every 2nd or 3rd picture shown:
  `fuseamp.service` was in a restart loop, 186 starts, beside a copy started by hand that held the
  display. With the unit alone, the same clip reached 24 fps within a second.
