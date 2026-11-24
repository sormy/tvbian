# X88 Pro 13 bring-up worklog

## 2026-11-19

- [johlnx's eMMC prefix](https://forum.armbian.com/topic/37232-x/?do=findComment&comment=232185)
  expands to 10,485,760 bytes. Gzip SHA-256
  `63bb3c545fd5c15e4eb97ba4683b867884247015007242d5a6693c9a66448675`.
- ✅ Primary GPT header and entry CRCs match. U-Boot starts at LBA 16384 (8 MiB). Android `boot`
  starts at LBA 51200 (25 MiB), beyond the dump. `dtbo` starts at 20 MiB.
- ✅ Five byte-identical 512 KiB RKNS slots start at LBA 64 and repeat every 1024 sectors. The first
  2 MiB from LBA 64 is the factory idbloader input.
- ✅ CODE471 starts four sectors into each slot, spans 120 sectors and identifies itself as DDR
  V1.04, build `8b31f80e33` dated 2023-04-08. No match in the pinned rkbin V1.13 blobs.
- ✅ All six FIT payloads match their embedded SHA-256 hashes. The FIT is at `0x800000`. Its
  6997-byte U-Boot tree is at `0x9b2a00` and identifies itself as RK3528 Evaluation Board. The five
  earlier FDT headers belong to the SPL copies.
- ✅ The extracted DDR packed with pinned rkbin's usbplug and SPL into a 471,374-byte RK3528 MaskROM
  loader. Header `LDR `, chip tag `8253`. Artifacts are in ignored `build/logs/x88-pro-13/`, with
  the packed loader under `pack/`.
- ❓ PCB revision of the dump's donor, stock kernel tree, loader on hardware, TVBian boot.

### PCB photos

| Revision | Silkscreen date | Evidence                                                                                                                                |
| -------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| D4 V1.1  | 2023-04-12      | [Original board](https://forum.armbian.com/uploads/monthly_2024_04/board5.jpg.20a2677a12af287c1c8da089b4ad8025.jpg)                     |
| D4 V1.1  | 2023-04-12      | [Second population](https://forum.armbian.com/uploads/monthly_2026_02/PXL_20260223_0707173432.jpg.5eeacdb32bf1819de794e4372f4add21.jpg) |
| V1.4     | —               | [Owner report and EA6521](https://forum.armbian.com/topic/37232-rupa-x88-pro-13-rk3528-board-with-images/)                              |
| D4 V1.5  | 2024-09-23      | [PCB back](https://forum.armbian.com/uploads/monthly_2026_01/X88Pro13_Back%282%29.jpg.2ec24f2d712fb1b01bd298b9d79b32d9.jpg)             |
| D4 V1.7  | 2025-07-30      | [PCB back](https://forum.armbian.com/uploads/monthly_2026_06/photo_2026-06-20_00-23-21.thumb.jpg.6c5784fe1f2ffa9710304fce9fcbabe5.jpg)  |

- [EA6521QF close-up](https://forum.armbian.com/uploads/monthly_2025_11/photo_2025-11-08_15-29-28.jpg.ebaec3e92819f1185244e9954208b23c.jpg).
- [V1.7 owner log](https://forum.armbian.com/topic/37232-rupa-x88-pro-13-rk3528-board-with-images/page/2/)
  reports SDIO device `0x6621`. The numeric ID is evidence for that unit. Its driver match is open.
- The V1.5 photo is from shexplorer, the recipient of the prefix. The dump uploader is johlnx, who
  reports owning multiple revisions.

### Firmware candidates

- [Hugsun specifications](https://docs.haimika.com/en/hc/x88/x88-pro-13/spec/).
- [Boxput stock images and OTA](https://boxput.notion.site/X88-Series-Fireware-6f707e5e9b06413aac2df3dc291e67aa).
  Color builds 2024-07-16, 2024-07-27 and 2024-09-10. Black builds 2024-07-12, 2024-09-10 and
  2025-03-06. The tested direct ZIP links returned 404.
- [2023-05-26 Color mirror page](https://chinagadgetsreviews.com/download-android-13-stock-firmware-for-boxput-x88-pro-13-tv-box.html)
  and
  [Black mirror page](https://chinagadgetsreviews.com/download-android-13-stock-firmware-for-boxput-x88-pro-13-tv-box-2.html).
  Both signed Notion links have expired. Color Mega download unverified.
- [BigShoots AOSP v0.73](https://github.com/BigShoots/X88_Pro_13_AOSP_AndroidTV_ROM/releases/tag/v0.73).
  Modified RKFW candidate for recovering `boot` and `dtbo`. PCB match unverified.
- [johlnx's Armbian trees and images](https://github.com/joilg/x88pro). Wiring reference with
  multiple populations. Compare with the Android tree once acquired.

### AOSP image inspection

- ✅
  [Direct v0.73 image](https://github.com/BigShoots/X88_Pro_13_AOSP_AndroidTV_ROM/releases/download/v0.73/X88_Pro_13_AOSP.img)
  serves byte ranges. Its RKAF product field is `X88Pro13.TVLauncher.LGX6521S`.
- ✅ The Android boot range contains a 102,895-byte FDT at boot image offset `0x21e1600`. Model
  `Rockchip RK3528 X88PRO DDR4 V10 Board`, SHA-256
  `c8508de53780c51a03deecf361d75c6933befeef0d37f8e537a60c7610ff47bf`. Carved as
  `build/logs/x88-pro-13/aosp-boot-21e1600.dtb`.
- ✅ The AOSP FIT's three ATF payloads, OP-TEE and U-Boot DTB are byte-identical to the prefix. The
  FIT header and U-Boot executable differ.
- ❓ The extracted Linux DTB's PCB revision and whether the dump donor uses this wiring. Its
  Seekwave node and the archive's LGX6521S label identify the firmware variant.

### Boxput stock firmware comparison

Six factory ZIPs supplied from the
[Boxput catalog](https://boxput.notion.site/X88-Series-Fireware-6f707e5e9b06413aac2df3dc291e67aa).
Kernel DTBs carved from RKAF boot and recovery partitions. Eight distinct kernel DTBs, three first
DTBs. All six Android DTBO partitions contain the same reboot-mode overlay.

| Factory image                | First DTB SHA-256 prefix | Enabled radio description                | SDIO ceiling |
| ---------------------------- | ------------------------ | ---------------------------------------- | ------------ |
| Black 2024-07-12             | `c8508de53780`           | Seekwave with GPIO1_A6 enable            | 200 MHz      |
| Color 2024-07-16, 2024-07-27 | `c8508de53780`           | Seekwave with GPIO1_A6 enable            | 200 MHz      |
| Black and Color 2024-09-10   | `f180ee14a1a7`           | WLAN platform node, archive labeled 8800 | 150 MHz      |
| Black 2025-03-06             | `aba89248ff26`           | Seekwave and WLAN platform nodes         | 150 MHz      |

- All six RKFW loaders match byte for byte. Their 61,440-byte DDR V1.04 entry matches the eMMC
  capture's DDR blob byte for byte.
- Black 2025-03-06 matches the capture across the full 2 MiB U-Boot overlap. Its stock kernel DTB
  appears twice in Android boot and twice in recovery, each copy identical. Donor PCB unknown.
- The March tree places active-high GPIO1_A6 reset in the WLAN node. The July first tree has an
  active-high Seekwave enable and an active-low SDIO power-sequence reset on GPIO1_A6. The September
  first tree uses the WLAN reset and wake properties and omits the Seekwave node.
- Local differences include SDIO tuning, HDMI idle pinctrl, front-panel enablement and IR keymaps.
  Alternate DTBs also vary Bluetooth enablement. The radio driver binding and ownership of GPIO1_A6
  need a variant choice before enabling Wi-Fi.
- The July first DTB matches the BigShoots v0.73 DTB byte for byte.
- Shared hardware is a candidate for one DTS include. Full support needs variant DTBs or overlays,
  selected by hardware evidence. The six archives do not map each DTB to PCB silkscreen.
- Artifacts and comparisons are in ignored `build/logs/x88-pro-13/stock-images/`.

### Stock wireless drivers

- Extracted `vendor` and `vendor_dlkm` from the July Black, September Black and March Black RKFW
  images. Each `vendor_dlkm:/lib/modules/modules.load` lists both AIC8800 and Seekwave.
- July and September load `skw_sdio.ko` and `skw_bootcoms.ko`. March loads `skw_sdio.ko` and
  `skw.ko`. March's `skw_sdio.ko` contains the `seekwave,sv6160` probe and the `gpio_chip_en`
  property name, which its factory tree omits.
- All three `modules.alias` files list AIC8800 function matches `5449:0145`, `c8a1:c08d` and
  `c8a1:0082`, and a class-wide SDIO match for `aic8800_bsp`. Seekwave has no SDIO alias in these
  files. Stock explicitly loads both stacks.
- Extracted modules report Android kernel `5.10.157+` vermagic with symbol versioning. TVBian needs
  its own builds and can use the stock modules and firmware as reference.
- ❓ Which stock driver claims GPIO1_A6 at runtime and how each radio population enumerates.

## 2026-11-20

- ✅ The March stock DTB round-trips with the RK3528 vendor 6.1 vocabulary and translates to the
  mainline 7.3 base. The vendor 6.1 headers were used as a compatibility check for the Android
  5.10.157+ blob. `dtcx` named 306 cells and left three numeric.
- ✅ The translated DTS preprocesses and compiles to a 90,830-byte DTB. The report has zero
  unresolved, 11 unsupported and eight unknown entries. WLAN and Bluetooth platform nodes are
  dropped by existing rules. Seekwave and the front-panel compatible are unknown.
- Scratch outputs `march-mainline.dts`, `march-mainline.dtb` and `march-mainline-report.txt` are in
  `build/logs/x88-pro-13/`. Hardware boot remains untested.

- Added the board from the March kernel DTB and the capture's own U-Boot DTB and idbloader. The
  factory U-Boot DTB matches the H96 Max RK3528 blob byte for byte. Its mainline adaptation compiles
  with UART0, backed by the X88 stock FIQ console.
- The first vendor build failed the upstream-view proof on the front panel's three GPIO references.
  Naming them in the RK3528 vocabulary restored equivalence. Both kernel trees pass the
  upstream-view and phandle checks. The host ran 191 dtcx tests.
- The build generated a 733,184-byte U-Boot FIT and a MaskROM loader from the 61,440-byte DDR entry.
  The initial board package built. The first image attempt found no vendor kernel metapackage in the
  build output, so the vendor kernel build was started.
- Enabled the RK3528 DesignWare watchdog in both kernel trees and mapped the vendor GPU's interrupt
  and clock names to Lima. Kept the X88 stock GPU regulator.
- Built the vendor 6.1.172 kernel, both radio module packages, board package and Trixie SD image.
  The final image includes the rebuilt DTB. Both GPT headers and tables, all five factory idbloader
  slots and both U-Boot slots agree with the build inputs. Read-only ext4 check passed. Extlinux
  names the expected kernel, initramfs and board DTB.
- `tvbian-x88-pro-13-trixie-2026-11-20.img.xz` SHA-256
  `ff9514a6160c1e634e7c1b1dcdc74f78a2f6eef1073b13b906ea9644e581aa9b`.
- The board-model test accepts a missing PCB for untested imports. The board-listing test passes
  with the product photo. No boot or peripheral results are available.

### Seekwave bus matching

- Decoded the `skw_sdio_ids` ELF symbol from the stock modules. July and September accept
  `0000:0000` and `abcd:1234`. March also accepts `3607:6160`. The all-zero terminator differs from
  the `0000:0000` match by its class byte.
- The
  [EA6x21 source](https://github.com/joilg/ea6x21-dkms/tree/b193d8b41e42f4ccf2cb23302ce2e3c940ad2415)
  has the same three IDs as March and matches `seekwave,sv6160`. TVBian's lite driver accepts
  `3607:6160` and `1ffe:6621` and matches `seekwave,sv6160lite`.
- The full and lite builds both install a module named `skwbt`. The full source also continues after
  `-EBUSY` on GPIO requests. A parallel package needs distinct module names, probe ownership and a
  single owner of GPIO1_A6. No stock capture shows the radio's enumeration sequence or which match
  it takes on the target PCB.

### EA6x21 firmware selection

- Carved the March stock DRAM and IRAM firmware and four revision-5 calibration files from
  `vendor:/etc/firmware`. The file hashes are in the stock-image scratch directory.
- The full driver's boot firmware filenames match stock. Both candidate repository binaries differ
  from the March binaries. Its EA6621Q revision-5 calibration file matches stock.
- The candidate's Wi-Fi driver chooses calibration from the chip type returned by the radio firmware
  and the chip revision. The March stock image contains all four revision-5 names. The candidate
  repository ships only the EA6621Q file.
- The candidate Bluetooth module requests `sv6160.nvbin`, `sv6160lite.nvbin` or `sv6316.nvbin`. None
  is at the root of the three inspected stock firmware directories. The candidate Wi-Fi calibration
  and Bluetooth NV paths need separate provenance.

### EA6x21 build assessment

- The full candidate builds five modules against TVBian 6.1.172. Its unmodified source fails against
  7.3.4 on GPIO, cfg80211 and timer API changes.
- The compiled full and packaged lite stacks share 11 exported symbols and the `skwbt` module name.
  Renaming those symbols and the Bluetooth module and platform names in scratch compiled on 6.1.172.
  This tests compilation and naming only.
- Treat AIC8800 and Seekwave as alternative radio populations. The stock image's module list covers
  both. Before changing the image, identify the radio on a stock-booted unit from its PCB marking,
  SDIO vendor/device pair, bound drivers and GPIO1_A6 ownership.

### Radio markings read from PCB photos

| Photographed PCB          | Visible radio marking | Evidence                                                                                                                                                                                                                                                    |
| ------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| X88PRO 13-D4-V1.1         | LGX8800D              | [Module](https://forum.armbian.com/uploads/monthly_2024_04/board2.jpg.ff3d6d1587697912e7df940d67e12c29.jpg), [silkscreen](https://forum.armbian.com/uploads/monthly_2024_04/board5.jpg.20a2677a12af287c1c8da089b4ad8025.jpg)                                |
| V1.4, owner-reported silk | EA6521QF              | [Radio close-up](https://forum.armbian.com/uploads/monthly_2025_11/photo_2025-11-08_15-29-28.jpg.ebaec3e92819f1185244e9954208b23c.jpg)                                                                                                                      |
| X88PRO 13-D4-V1.5         | EA6521QF              | [Front](https://forum.armbian.com/uploads/monthly_2026_01/X88Pro13_Front%282%29.jpg.a9c771a210dfd840e739b9d059b97ba0.jpg), [back](https://forum.armbian.com/uploads/monthly_2026_01/X88Pro13_Back%282%29.jpg.2ec24f2d712fb1b01bd298b9d79b32d9.jpg)          |
| X88PRO 13-D4-V1.7         | ❓ Marking illegible  | [Front](https://forum.armbian.com/uploads/monthly_2026_06/photo_2026-06-20_00-23-08.jpg.53bb86b6d22f3821b3484d42009be3b6.jpg), [back](https://forum.armbian.com/uploads/monthly_2026_06/photo_2026-06-20_00-23-21.jpg.80a975c12b8b94e51e1efb25ba23b648.jpg) |

- V1.5 and V1.7 front photos show the three-pad edge header marked GND, TX and RX.
- V1.7's owner reported SDIO device `0x6621` under Armbian. The vendor ID and stock driver binding
  are missing. The photo gives no chip identification.

### DRAM markings

- V1.1 and V1.5 photos show Samsung `K4B2G0446D` and `HCK0` on the DRAM packages. Samsung lists this
  part as 2 Gb x4 DDR3. The PCB suffix `D4` and stock DTB model's `DDR4` label differ from the
  photographed parts.
  [Samsung datasheet](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/791/K4B2G0846D_2D00_HCH9.pdf)
- Stock loader bytes are shared across the six archives. Boot and DRAM training on a photographed
  revision remain untested here.

### Dump-to-PCB comparison

- The six Boxput RKFW parameter files each match the 13 fixed partition starts and lengths shared
  with the eMMC capture. The partition layout does not distinguish the firmware builds.
- March Black alone matches the full 2 MiB U-Boot overlap. The other five share a U-Boot image that
  differs from the capture by 50 bytes in two sectors. The March parameter model names both
  `LGX6521S` and `8800`.
- The separately downloaded `01_dtbdump_rockchip,rk3528-evb2-ddr3-v10.dtb` starts with a DTB that
  matches the H96 Max RK3528 factory kernel tree and contains no second complete FDT v17 candidate.
- The capture's GPT describes a 62,537,072,640-byte user area. The separately posted CyberHaZard
  partition UUIDs differ for all 14 comparable partitions.
- The uploader reported owning multiple revisions. The V1.5 serial and photo attachments belong to
  the recipient of the dump. Five forum log downloads returned HTTP 403. The firmware match
  establishes a stock reference, while the donor's PCB revision remains unknown.

## 2026-11-21

- The RK3528 translation keeps the vendor rfkill nodes' lines: the next2 tree's SDIO power sequence
  gains `<&gpio1 RK_PA6 GPIO_ACTIVE_LOW>`, the March tree's WLAN reset, and UART2 a `bluetooth` node
  with the GPIO1_C1 reset. Blind bring-up: no box, untested.
