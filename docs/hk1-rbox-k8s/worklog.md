# HK1 RBOX K8S worklog

## 2026-11-20

- Owner confirmed `hk1-rbox-k8s` and reported PCB `FX-RX3528-D4`, dated `20230822`.
- AV-jack button and USB 2.0 OTG reached factory Loader at `2207:350c`.
- Two reads with `rkdeveloptool rl 64 4096` matched at 2,097,152 bytes. SHA-256:
  `a71691a43001ddaa956b8a103992e72b878175255ad7486475f5237497db9618`.
- The `RKNS` header's DDR entry starts at sector four and spans 59,392 bytes. The blob reports
  `DDR V1.07 4bit PCB 4fe5906c9d huan.he 23/08/04-17:05:07`.
- `./build.sh loader hk1-rbox-k8s` packed the factory DDR blob. `rd 3` reached Maskrom and `db`
  uploaded the board's loader. A third idbloader read matched both factory Loader reads.
- `rfi` reported 61,063,168 sectors. The full read ran through the board's loader.
- The dump was 31,264,342,016 bytes. Its idbloader matched, and both GPT headers and partition
  arrays passed CRC validation and agreed. `xz -t` passed on the archive saved as
  `backup/hk1-rbox-k8s-stock.img.xz`. Archive SHA-256:
  `b57e326db9df6da8db31e93ea2170fe791647c95bf04f8652799493b4f278e7e`.

- Carved the `rk-kernel.dtb` entry from the stock boot partition at offset `0x206bc00`. All three
  copies match. The FIT `fdt` at offset `0x1a3600` in the U-Boot partition matches its embedded
  SHA-256 and the second FIT copy.
- The factory tree proof caught the front display's two unrecognised GPIO references. Declaring
  `fd628_gpio_clk` and `fd628_gpio_dat` in the vendor base recovered GPIO4 A3 and A2. The generated
  kernel tree and its upstream view then compared equal. The factory U-Boot decompile was clean.
- Stock `vendor_dlkm:/lib/modules/modules.load` lists `8822cs.ko`, `8822es.ko`, `8852be.ko` and the
  AIC8800 stack. The WLAN node's RTL8822CS label is a candidate. The HK5246F module's SDIO ID will
  identify the device at first boot.
- The board model test and 192 dtcx tests passed.
- Built U-Boot v2026.10, the board package and a Trixie SD candidate with kernel
  `6.1.172-tvb-rk35xx`. U-Boot reported warnings on the inherited factory SPI, clock, DMA and
  interrupt descriptions and omitted optional OP-TEE.
- Checked the image's five idbloader copies, both FIT copies, installed board DTB and extlinux
  entry. `r8152.ko` is present. `xz -t` passed. Image SHA-256:
  `5998da4824f45853a6851987b13e21b0774d4f32b29a358a67695ccc3c4751b1`.
- No external SD card was attached to the host. First boot is pending.
- After the owner inserted the prepared SD card, `hk1-rbox-k8s.local` resolved to `192.168.1.152`.
  Both pings returned and SSH presented a host key. Root rejected the available key. The root device
  and SDIO identity still need an authenticated check.
- After the owner installed the SSH key, BatchMode login succeeded over USB Ethernet (`eth1`,
  `r8152`). Root was on `mmcblk1p1`; the host reported type SD. The separate eMMC had boot
  partitions and the Android partition map. Kernel `6.1.172-tvb-rk35xx`, 3921 MiB RAM.
- The boot log identifies the HK5246F via SDIO IDs `c8a1:0082` and `c8a1:0182`. AIC8800 probe
  requested `fw_patch_table_8800d80_u02.bin`, then removed the card when the file was missing.
- Installed `tvb-firmware-aic8800` on SD. A live driver retry could not recover the missing SDIO
  card. The next warm boot restored USB Ethernet and brought up `wlan0`. The driver reported its
  address from eFUSE, and a scan returned 2437, 2462, 5200, 5220, 5280, 5320 and 5600 MHz.
- Added `tvb-firmware-aic8800` and `bluez` to the board's dependencies and rebuilt the SD image.
  `eth0` bound the RK630 PHY over RMII with no cable. Stock Bluetooth config names `/dev/ttyS2`.
- Bound AIC8800 H4 to UART2 at 1.5 Mbaud using stock pinmux. The first boot registered `hci0` with
  BR/EDR and LE and a public address one above Wi-Fi's eFUSE address. Power-on failed while both
  Bluetooth rfkill entries were soft-blocked. A manual address command did not clear the failure.
  Applying the shared Rockchip rfkill add rule cleared the block. Discovery returned nine device
  events with zero HCI RX/TX errors.
- Added the common Bluetooth rfkill rule to the board package. On a new boot `hci0` was powered and
  `UP RUNNING` with zero HCI errors. Its address was unchanged with no manual address command.
  `wlan0` and USB Ethernet also came back.
- `stress-ng --vm 1 --vm-bytes 3G --vm-keep --verify --timeout 60s` passed. The thermal zone read
  45.5 °C at completion.
- Rebuilt the SD image with the Bluetooth tree and rfkill rule. `xz -t` passed. Image SHA-256:
  `8ad8ef6192898a1b3beab7fa01fbb3ab9406d1d34c4b9c9879fa3bb5dfb56601`.
- Ran the short system, storage and input baseline on SD. RAM and fio completed, with zero MMC
  errors or idle IOMMU faults. The kernel exposed `KEY_VENDOR` for recovery. The suite flagged
  deferred `mtd_vendor_storage`, unbound stock devices including `fd628-dev`, missing optional
  family modules, and missing RTL8153 firmware for the test adapter. See
  `build/logs/hk1-rbox-k8s/baseline.log`.

## 2026-11-21

- The RK630 PHY still reported no carrier. USB Ethernet linked at 1000 Mb/s. Installed
  `firmware-realtek` on the SD system for the RTL8153 test adapter and added audio, DRM and IR test
  tools.
- The stock boot payload reports Android kernel 5.10.157. Its built-in `fd628_driver_probe` and
  `fd628_gpio_clk` / `fd628_gpio_dat` strings match the unbound panel node in TVBian.
- Headless audio timed the analog codec at 3.02 s for both rates. HDMI took 4.54 s at 44.1 kHz and
  3.01 s at 48 kHz with no sink. Physical playback is pending.
- The synthetic display run staged PAL and NTSC modes, but composite writeback lost the colour bars.
  HDMI composition and SDR-to-HDR colour checks passed. The stock VOP configuration exposed nine
  Esmart sub-windows and failed the all-plane check. Staged a DTB with the RK3528 4K line buffer and
  sub-windows removed. The pre-display DTB is on the SD rootfs for rollback.
- Rebooted with the VOP change. The retest passed all-plane composition and 3601 paced commits at 60
  Hz. A focused synthetic 4K60 run sustained 601 commits with zero refusals or late flips. The full
  headless run reported 20 passes and two composite writeback failures.
- The RTL8153 adapter loaded `rtl8153a-4` after reboot. The new SD image passed `xz -t` and
  contained the same DTB as the live test. SHA-256:
  `a4430c55808f2a5d0f7467202f8bfa7d111da85723555b1c5ae577bc5c843cfc`.
- Ran `translate.py` for a mainline 7.3 preview from the board's own factory DTS. The report in
  `build/logs/hk1-rbox-k8s/next2-translation.txt` lists nine unknown tokens, nine unsupported tokens
  and one unresolved HDMI sleep pin state. The preview has yet to build or boot.
- Imported the active Wi-Fi profile from a sibling with a new profile UUID and no fixed MAC. USB
  Ethernet kept the preferred route. DHCP and direct SSH worked on the WLAN address.
- `iperf3 --bind-dev wlan0`, 10 s each direction, receiver rates: 124/113 Mb/s on 2437 MHz and
  163/84.7 Mb/s on 5200 MHz. Restored automatic band selection and checked that WLAN was up.
- Built the first mainline 7.3 draft with `./build.sh board-dtb hk1-rbox-k8s/next2`. Its upstream
  view proved equivalent. Boot and the translation report findings remain open.
- Mainline 7.3.5 booted from SD with the translated tree, GPIO3 B2 held high by the SDIO pinctrl and
  the watchdog enabled. The boot guard restored the vendor menu. Both AIC8800 SDIO functions bound,
  Wi-Fi got DHCP, and SSH worked over Wi-Fi.
- The 2.4 GHz upload reached 120 Mb/s. Download fell to zero after four seconds and timed out. The
  USB RTL8153 initially linked over the SuperSpeed hub, then disappeared after xHCI reported that it
  could not access memory fast enough. Mainline exposed no Bluetooth controller.
- Confirmed from mainline MMC core that it reads `sd-uhs-ddr50` and `fixed-emmc-driver-type`. The
  translation now preserves both. An X88 translation comparison showed only the intended eMMC
  drive-strength property added. All 192 dtcx tests passed.
- The image builder now checks that extlinux's direct DTB paths or per-kernel DTB links resolve. The
  HK1 image built with the links and its embedded mainline DTB matched the first boot test.
- The warm return to 6.1 restored USB Ethernet and Bluetooth. The SDIO card was absent, including
  after rebind of the dedicated controller at `ffc20000.mmc`. Cold boot requested to test recovery.
- The FD650B-S has a two-wire driver candidate in the published TM16xx series
  (`20250926141913.25919-1-jefflessard3@gmail.com`). The panel's segment map is unverified.
- With Wi-Fi absent on 6.1, toggled unclaimed GPIO3 B2 low for two seconds while the SDIO host was
  detached. Rebinding enumerated both functions and restored Wi-Fi. The box did not reboot.
- The mainline tree's MMC power sequence now controls GPIO3 B2 and B4 and holds them low for two
  seconds at power-off. Mainline booted and associated, but a warm return to the old vendor tree
  still left the card absent.
- Moved GPIO3 B2 into the vendor tree's MMC power sequence as well. Booting that tree from the
  stalled state brought back Wi-Fi and Bluetooth. Unloading and reloading `aic8800_fdrv` brought
  back the Wi-Fi DHCP link at the same boot ID. Bluetooth remained powered.
- After the reload, bound 5 GHz transfer reached 185 Mb/s up and 198 Mb/s down. Rebuilt the SD image
  with the new power sequence for both trees. `xz -t` passed. Archive SHA-256:
  `f7ba115d71d9742f08a13ba14a8c89bd3bddced7b2a383554a838ae404b4887f`.
- Verified both installed trees match the repo before a warm 6.1 → 7.3.5 → 6.1 round trip. Mainline
  restored the vendor menu and associated, with a 5 GHz download at 209 Mb/s. On the return, Wi-Fi
  re-enumerated and got DHCP on 6.1 with Bluetooth powered. No manual GPIO action or power cycle was
  needed.
- Vendor 6.1 with FFmpeg 9.0.2 and Rockchip MPP decoded three synthetic 4K H.264 and HEVC frames
  byte-exactly. HEVC Main10 decoded three frames at 8192×4320 by frame count. The hardware refused
  1080p VP9. Both 4K H.264 and HEVC encodes decoded back with 43.05 and 41.59 dB luma PSNR. No new
  kernel errors were reported. See `build/logs/hk1-rbox-k8s/vendor-video-large.log`.
- The vendor CPU suite ran four loaded cores for 300 s, peaked at 62.7 °C and registered no cooling
  state. The lowest sample was 816 MHz. The measured top OPP was 2016 MHz at 1050 mV.
- The existing H4 serdev patch for 6.12 applied to mainline 7.3.5 and built. The resulting
  `hci_uart.ko` contains the AIC8800 OF alias. Added the UART2 child to the translated tree and
  verified its upstream view. The board package and SD image rebuilt.
- Booted the rebuilt 7.3.5 kernel and Bluetooth DTB. The OF alias bound UART2 to H4, and `hci0` was
  powered with the same public address as on 6.1. A ten-second scan returned eight discovery events
  with zero HCI RX/TX errors. Wi-Fi remained associated at 5200 MHz.
- Mainline 2.4 GHz retest completed at 89.5 Mb/s up and 13.1 Mb/s down. Automatic band selection was
  restored and the link returned to 5 GHz. USB Ethernet through the same hub sustained 941 Mb/s in
  both directions for ten seconds each, with the gigabit link present afterward. The earlier xHCI
  disconnect remains an intermittent finding.
- Returned to vendor 6.1 with Wi-Fi and Bluetooth. The same SuperSpeed hub's downstream port 4 now
  failed to enumerate on the vendor kernel. A port-only disable/enable did not recover it. Direct
  adapter testing is pending. The first 32,768 eMMC sectors still hash identically to the backup.
- Vendor 6.1 rebooted after the SysRq panic. `dmesg-ramoops-0` contained the matching
  `sysrq triggered crash` record. Wi-Fi and USB Ethernet returned.
- The unpinged watchdog reset the board at an 11 s configured timeout. Both network links returned
  and systemd rearmed the watchdog at its reported 89 s hardware timeout.
- A 45 s all-CPU test with interrupts disabled ended on the same boot, before the 89 s hardware
  watchdog timeout. The separate all-CPU preemption lockup with interrupts enabled tripped the soft
  detector at 26 s. The box panicked, rebooted, recorded the panic in console-ramoops and restored
  Wi-Fi, USB Ethernet and Bluetooth.
- Both vendor and mainline DesignWare MMC drivers consume `card-detect-delay` before they rescan
  after a controller card-detect event. The RK3528 translator now preserves the HK1's 500 ms value.
  The mainline DTB proof and 194 dtcx tests passed. The SD image rebuilt and passed `xz -t`; SD
  hotplug remains unverified.
- The stock Android PWM keylayout and DTB contain multiple handset tables. Mainline's GPIO IR
  receiver uses stock GPIO4 C6. The bundled handset's address still needs a capture.
- `tools/validate/reboots.sh` passed ten vendor 6.1 warm cycles from SD. Each boot loaded the same
  tree, re-associated Wi-Fi in 24.8–36.2 s, enumerated one Bluetooth controller and logged zero MMC
  errors. USB Ethernet was absent after boot 10. The box remained reachable over Wi-Fi.
- `tvb-install` identified the SD source and the internal 29.1 GiB MMC32G target. Its preflight
  listed the idbloader, DVKR, SSKR and trust ranges for preservation. Declined at confirmation.
- Fifteen-second stress-ng STREAM runs read 983 MB/s with one worker and 1925 MB/s with four. A 512
  MiB read-only direct fio run on the eMMC sustained 242 MB/s.
- Vendor 6.1 exposes `s2idle` and `deep`, with no registered RTC. The power inventory left the box
  awake. A physical wake source is needed to verify suspend.
- `./build.sh test` passed all 339 repository tests.
- Headless glmark2 rendered the build scene on Mesa's Mali450 renderer. Two runs scored 135 and 124.
  The on-screen suite remains untested.
- Vendor 6.1 finished a 120 s combined CPU, RAM, SD, graphics and Wi-Fi check. The three jobs exited
  cleanly, the thermal zone peaked at 65.5 °C, and kernel warning count and Wi-Fi ping loss were
  both zero during the run.
- Vendor MPP decoded synthetic 1080p VP8 byte-exactly, 1080p MPEG-2 and MPEG-4 Part 2 at 75.76 and
  75.98 dB luma PSNR, and 704×576 H.263 at 74.53 dB. No fallback or new kernel errors.
- Booted mainline 7.3.5 with the latest card-detect DTB. V4L2 decoded synthetic 4K H.264 and HEVC
  byte-exactly. It decoded 4K Main10 by frame count, 1080p VP9 byte-exactly and 1080p MJPEG at 55.12
  dB luma PSNR. All three encodes (4K H.264, 4K HEVC and 1080p MJPEG) decoded back. No fallback or
  new kernel errors. See `build/logs/hk1-rbox-k8s/next2-video.log`.
- Mainline's headless display suite returned 15 passes and no failures. Its composite PAL and NTSC
  writeback retained all six colour bars. HDMI paced 3601 commits in 60 s with no refusals or missed
  events. HDMI writeback composition was skipped at that mode. Mainline sent PQ and HLG InfoFrames
  even to the synthetic SDR sink.
- Mainline's synthetic 4K60 test completed 601 commits at 60.1/s, with no refusals, late flips or
  new kernel lines. Physical HDMI and composite output still need a sink.
- MPP H.264 and HEVC decoder scaling passed from 3840×2160 to 1920×1080, at luma PSNR 67.00 and
  65.35 dB. The first interlaced H.264 test requested a nonexistent `h264i_rkmpp` decoder. The
  corrected test uses `h264_rkmpp` and returned all three frames, but luma/chroma PSNR was
  27.18/22.32 dB against the software reference.
- The interlaced PSNR test compared different output cadences. MPP emits progressive pictures at
  1/60 s intervals. Each of three sampled output pictures contained a luma field that matched
  software exactly. A 30-frame synthetic stream produced 57 progressive pictures, ending at 0.933 s.
  The short clip stopped on an explicit MPP EOS frame. The three missing field-rate outputs remain
  to be traced.
- A continuous 30-picture synthetic H.264 clip reproduced 57 progressive outputs on vendor 6.1. MPP
  1.1.0's IEP2 trace processed all 30 decoded pictures. The first picture emitted one output. The
  second waited for temporal history. The next 28 each emitted two. At the single empty EOS task,
  `mpp/vproc/mpp_dec_vproc.c` emitted EOS and released its final two references without draining
  them. See `build/logs/hk1-rbox-k8s/vendor-h264i-single-eos.log`.
- A temporary MPP 1.1.0 build using IEP2's spatial I2O2 mode emitted 60 pictures from a 30-picture
  320×240 top-field-first stream. Every first output preserved the top luma field byte for byte, and
  every second output preserved the bottom field. The probe forced spatial processing on every
  picture and used the test clip's fixed PTS step. The installed library was untouched. I2O2 is a
  candidate for draining the tail while preserving temporal processing in the middle. See
  `build/logs/hk1-rbox-k8s/mpp-i2o2-run.log`.
- A tail-only I2O2 prototype reached 60 outputs for both field orders, with a byte-identical prefix
  and a steady 1/60 s PTS step. A luma field comparison exposed a false pass by count: the first
  added picture repeats the penultimate picture's second field. Stock MPP loses one field at stream
  start and both fields of the last picture. Its first BFF output also preserves the top field. A
  complete fix must cover startup, tail and temporal output timestamps. See
  `build/logs/hk1-rbox-k8s/mpp-tail-compare.log`.
- The next temporary MPP build emitted a spatial pair at startup and at EOS. It kept IEP2 temporal
  processing in the middle and timed each temporal pair from its source picture. Both field orders
  passed the two- and 30-picture 320×240 tests. Every output preserved the expected luma field in
  order, with uniform 1/60 s timestamps. Progressive 1080p output had the same SHA-256 as stock MPP.
  The 30-picture 1080p interlaced clip emitted 58 outputs once and 60 on the traced retry. The
  prototype allocates extra output buffers and can skip a pair on allocation failure. Buffer
  handling and the one-picture case need work before packaging. See
  `build/logs/hk1-rbox-k8s/mpp-boundaries-compare.log`.
- The buffer-wait prototype reuses the normal IEP2 output buffers at startup. At EOS it keeps the
  drain task pending until both output buffers are available. Ten consecutive 1080p runs returned 60
  outputs each. Both field orders still preserved every expected luma field in one-, two- and
  30-picture tests. A one-picture stream has no adjacent PTS to derive a field interval, so the
  prototype assigns both outputs the source PTS. Longer clips retained the 1/60 s step. The probe is
  still a temporary library. See `build/logs/hk1-rbox-k8s/mpp-buffer-{compare,repeat}.log`.
- An Annex B stream changed resolution from 320×240 to 1920×1080 after 30 interlaced pictures. The
  buffer-wait prototype emitted 118 of 120 outputs. The info-change task discarded the last queued
  picture of the old size. A revised prototype drains it before publishing the new format and
  releases spare buffers of the old size. The rerun emitted 60 outputs at each resolution. A
  separate 1080p EOS run emitted 60. See `build/logs/hk1-rbox-k8s/mpp-format-switch-run.log`.
- The normal `ffmpeg9` build now carries the IEP2 boundary patch against MPP 1.1.0. The package's
  input fingerprint includes the patch and its build stamp records the patch hash. Extracted the
  built package on the HK1 and ran its FFmpeg with its bundled MPP. The 1080p clip emitted all 60
  outputs and the resolution-change clip emitted all 120. See
  `build/logs/hk1-rbox-k8s/ffmpeg9-mpp-package-run.log`.
- The MPP decode validator now checks the preserved luma field in each progressive output. The
  corpus uses distinct fields sampled at 60 Hz. On the HK1 the installed MPP failed with 3 of 6 and
  57 of 60 outputs. The patched package matched all 6 and all 60 luma fields, in order, with no new
  kernel errors. See `build/logs/hk1-rbox-k8s/ffmpeg9-field-validator.log`.
- Vendor 6.1 leaves the factory panel lines GPIO4 A3 and A2 unclaimed. A temporary open-drain probe
  found both lines idle high. DAT went low on the ninth clock for the FD650B documented command
  bytes, the TM1650-family command bytes and three control bytes. This is a bus response, but
  command-only probes cannot identify the register protocol or segment map. The probe sent no
  display data and released both GPIOs. See `build/logs/hk1-rbox-k8s/fd650b-ack.log`.
- Recovered symbols from the stock 5.10.157 kernel in `boot.img`. Its `FD628_Command` writes
  controller byte 0x48. The stock driver uses payload 0x31 for enable and 0x80 for off.
  `fd628_dev_write` sends the five display bytes to 0x66, 0x68, 0x6a, 0x6c and 0x6e. The shutdown
  path treats 0x66 separately from the four digit writes. A GPIO probe sent the stock enable and
  four digit transactions, then blanked the panel and sent off. All command and payload bytes were
  acknowledged. Segment and icon placement still need visual confirmation. See
  `build/logs/hk1-rbox-k8s/fd650b-stock-disassembly.log` and `fd650b-pattern.log`.
- Extracted stock `/system/bin/vfdsrv` from the Android system logical partition. The five-byte
  write to `/dev/fd628_dev` places hour tens, hour units, minute tens and minute units in bytes 1–4.
  The stock kernel maps these bytes to wire commands 0x68, 0x6a, 0x6c and 0x6e. The userspace digit
  table at 0x750 uses the standard seven-segment masks. It toggles bit 7 of byte 2 for the clock
  colon. The clock daemon normally writes zero to byte 0, so this path supplies no mapping for the
  separate status icons at wire command 0x66.
- Built the published TM16xx I²C driver at `3bd8337744ce` against vendor 6.1.172 and mainline 7.3.5.
  The vendor test build uses its older I²C probe and symbol namespace APIs, drops compatibility
  shims already provided by that kernel, and includes the line-display helper. The vendor modules
  loaded and unloaded cleanly on the HK1. Compiled candidate DTBs for both kernels with I²C GPIO,
  the recovered four digit rows and colon at row 1, segment 7. The running DTB has no panel I²C
  node, so this run verified driver registration without probing the panel. See
  `build/logs/hk1-rbox-k8s/fd650b-driver-{isolated,load}.log`.
- Booted vendor 6.1 from SD with the temporary panel tree. Saved the previous DTB at
  `/var/tmp/hk1-panel-boot-test/board.dtb.before-panel`. Wi-Fi and USB Ethernet returned.
  `tm16xx-i2c` bound I²C device `9-0024`. The display reported four characters, brightness 3 and
  colon on. All eight traced digit writes succeeded, four for `4321` and four for `1234`. Left
  `12:34` set for visual confirmation. The modules are loaded from the test directory and need
  manual loading after reboot. See `build/logs/hk1-rbox-k8s/fd650b-i2c-trace.log`.
- Added the TM16xx I²C module to the RK35xx vendor and next2 build lists. The standard module
  packager produced three modules for 6.1.172 and two for 7.3.5. Both generated board trees now
  carry the factory-backed panel wiring and clock mapping. The dtcx proof needed three literal
  properties declared in the mainline base to distinguish their numbers from reassigned phandles.
  Both tree proofs and all 194 dtcx tests passed.
- Installed the built board package and both matching TM16xx module packages on the SD system.
  Mainline 7.3.5 and vendor 6.1.172 each loaded the packaged I²C driver automatically and exposed
  four characters and the colon control. Both returned `1234` and colon brightness 1 after the test
  write. Restored vendor as the default with both entries in the boot menu. Wi-Fi returned on both
  boots. USB Ethernet was present on mainline and absent on the vendor return.
- The board package now starts a minute timer when the TM16xx display LED appears. On a fresh vendor
  SD boot, udev requested the timer and the first run wrote the current local HHMM with the colon
  on. The HK1 hardware runs also qualify it for the default tested-by-TVBian support level. Removed
  its import-only `BOARD_SUPPORT=not_tested` setting.
- Renamed the front-panel service and timer to `tvb-display`. Installed the new board package on SD
  and verified default 24-hour, explicit 12-hour and explicit 24-hour settings. The 12-hour readback
  preserved the blank leading digit. Restored the default and left the timer active. See
  `build/logs/hk1-rbox-k8s/panel-clock-format-test.log`.
- Verified `PANEL_CLOCK_FORMAT=off` blanks all four clock digits and clears the colon on the vendor
  SD system. Switching back to 24-hour mode restored the clock and colon.
- Renamed the setting to `PANEL_CLOCK`. Verified all three values and precedence over the previous
  `PANEL_CLOCK_FORMAT` spelling on the vendor SD system.
- The owner confirmed visible front-panel output. The installed display service verified brightness
  levels 1, 3 and 8, steady colon states and both phases of the 500 ms blink. The display-only New
  York timezone produced the expected digits. Clock off blanks the colon even with blinking
  selected. Restored the previous settings after testing.
- Renamed the service, timer and settings file to `tvb-front-panel`. Verified the `DISPLAY_`
  settings on the vendor SD system, including precedence over the old file. The udev rule requested
  the renamed timer and the timer was active after testing.
- Changed the default colon mode to blinking. On the HK1, the installed package selected the timer
  trigger with 500 ms on and 500 ms off. Both brightness states were observed.
- Added vendor 6.12.69 to the SD boot menu alongside 6.1.172 and mainline 7.3.5. Both vendor kernels
  select the vendor tree. The standard module packager built TM16xx for all three releases.
- Vendor 6.12.69 booted from SD and started the packaged front-panel clock. Wi-Fi reached 205 Mb/s
  up and 174 Mb/s down. The SuperSpeed hub and USB Ethernet adapter were absent on this warm boot.
  Progressive 1080p H.264 matched the 6.1 output hash. The patched MPP matched all 60 source luma
  fields in the interlaced test. ALSA cards and the Mali render node enumerated.
- The 6.12 Bluetooth monitor showed successful UART transactions and a valid factory public address,
  followed by an Unconfigured Index event. Its HCI core interprets `HCI_QUIRK_USE_BDADDR_PROPERTY`
  as an invalid factory address. Moved the quirk into the two paths with a replacement address. A
  temporary module built against the running kernel exposed one powered controller to BlueZ, with
  the factory address retained.
- With the corrected 6.12 H4 module, an eight-second LE scan reported 323 device events. Two-second
  silent analog playback took 2.027 s at 44.1 kHz and 2.019 s at 48 kHz.
- The 6.12 headless display run returned 14 passes and four failures. HDMI paced 3601 flips in 60
  seconds without a refusal or missed event. Composite writeback lost PAL and NTSC colour bars.
  SDR-to-PQ and SDR-to-HLG colour stages returned EINVAL. The xHCI root buses returned after driver
  rebind, but the hub and adapter remained absent.
- The full 6.12 kernel rebuild passed and its metapackage now depends on the TM16xx package. All 342
  repository tests passed.
- Rebooted into the rebuilt 6.12 package. A new boot ID, the running H4 module's matching source
  version, BlueZ's powered controller and the active display timer verified automatic startup. The
  boot menu kept all three kernels and selected 6.1 as the default.
- Returned to vendor 6.1.172 with all three kernels still in the boot menu and 6.1 as default. The
  exact 6.1 module rebuilt with the shared address fix also exposed a powered controller.
- The HK1 and M2 Plus VOP2 nodes have the same HDMI and composite routing and line-buffer setting.
  On clean 6.12 with the same HK1 DTB, HDMI capture verified all seven PQ and HLG colours within one
  code. After the PAL/NTSC composite test, the same HDMI capture returned EINVAL for XRGB8888,
  ARGB8888 and NV12. Both HDR commits still succeeded without capture. The 6.12 symptom follows the
  display transition. See `build/logs/hk1-rbox-k8s/next-612-hdr-isolate.log`.
- Reordered the display suite to run HDMI before composite and check capture again after the switch.
  On vendor 6.12, the revised run reported 20 passes and three failures. Both SDR-to-HDR colour
  stages passed within one code. The remaining failures were PAL and NTSC writeback and the return
  to HDMI writeback.
- The regression profile now runs the GPU screen capture before the full display step, which ends
  with composite. All 343 repository tests passed in the build container.
- After the display run, rebooted with 6.1 selected as the default. The HK1 did not answer SSH at
  either known address or resolve by mDNS. Cold-start verification is pending.
- The owner's cold reboot returned the HK1 to 6.1 with the front-panel timer and Wi-Fi active. The
  built-in RK630 Ethernet reached SSH at 100 Mb/s full duplex, with 93.7 Mb/s up and 94.1 Mb/s down.
  The owner saw no HDMI output before or after reboot. With the connector unforced, a fresh detect
  reported disconnected, zero EDID bytes and zero modes while the HPD GPIO read high. The direct DDC
  read returned EPERM. The vendor driver returns that error when its internal PHY HPD bit is low.
- Owner reported a dark Ethernet link LED on next2. The factory DTB selects UART3 mode 1 on GPIO4 B7
  and C0, with no LED pinctrl on the PHY. The next2 translation adds both PHY LED groups on those
  same pins. Vendor 6.1 pinmux showed UART3 owning both pins while the internal Ethernet had
  carrier. The jack LED wiring remains to be confirmed.

## 2026-11-21 — Bluetooth on next2, and what the translator dropped

- With the `rk-bluetooth` conversion: `hci0` UP RUNNING, a scan finds devices on both kernels.
- Bluetooth address `68:8F:C9:E1:CF:00` on 6.1 and 7.3.5, its eFUSE's.
- The `rk-wlan` conversion replaces the tree's hand-written `RK_PB2` hunk; the tree byte-identical.
- Parity, 6.1 against 7.3.5: inputs 6 against 2, cooling 3 against 2, rfkill 3 against 2.
- Compared the supplied product specifications with stock and live evidence. Android's
  `/system/build.prop` reports Android 13, API 33. `lscpu` reports four Cortex-A53 cores. The test
  card is a 64 GB microSD. The 5 GHz WLAN link reported HE-MCS 11. The Bluetooth controller reported
  HCI version 13 (5.4).
- Vendor 6.1 decoded all 30 pictures of a synthetic MPEG-1 1080p60 clip at 75.71 dB luma PSNR. Its
  4K60 H.264 High test returned all 600 pictures in 14.18 s, or 42.3 fps. The VC-1 software decoder
  accepted the conformance sample. The V4L2 hardware wrapper found no suitable device.
- Vendor 6.1 decoded all 50 pictures of a synthetic 7680×4320 HEVC Main10 clip in 3.04 s. That
  averaged 16.4 fps against the 25 fps source. See
  `build/logs/hk1-rbox-k8s/vendor-hevc10-8k25-spec.log`.

## 2026-11-22 — the board swept

- The front-panel clock moved to `tvb-base` as `/usr/lib/tvb/front-panel`; this board's package list
  dropped its four lines. On the box: the timer active, the panel at the current time.
- Vendor tree: the GPU's `core` on `ACLK_GPU_MALI`, as the siblings, after devfreq showed SCMI's
  300–800 MHz with no throttling on 6.1; UART2's `dmas` dropped, after 6.1 logged
  `dma-names property ... missing`; `remote_support_psci` `1`. On 6.1: `aclk_gpu` 297 MHz idle, the
  DMA line gone, `remote_support_psci` 1 in the live tree, Bluetooth and Wi-Fi up, no oops.
- `powerkey.conf` added: logind's default powered the box off on the remote's power key.
- Comments moved to the lines each patch changes; both trees' DTBs otherwise unchanged.
- Translation: rules for `amlogic,fd628_dev` (unsupported), the Amlogic dummy battery and charger
  (no driver binds them on 6.1), `cec-enable`, `num-slots` and `supports-emmc` (no mainline reader).
  The report has no unknown token; every RK3528 next2 DTB is byte-identical.
- Not taken from the siblings: `mode-maskrom`, the factory SPL untested; the DDC bus, HDMI failing
  at hot-plug detect first.
- Installing the board package regenerated the boot menu and made next2 the default; set back to 6.1
  by hand.

## 2026-11-22 — the regression's findings fixed

- Full regression, every step, all three kernels. The HK1's own failures: next2's PHY on "Generic
  PHY", and `gpu-bus` unbound on 6.1 and 6.12 (`_opp_set_regulators: no regulator (pvtm) found`).
- next2: the PHY's LED pin state dropped, the pins UART3's as in the factory tree, no LEDs fitted.
  The PHY now binds `Rockchip RK3528 integrated FEPHY`; no pin-claim errors; 100 Mb/s, DHCP.
- Vendor: `gpu-bus` disabled. It sets `vdd_logic` for SCMI's GPU clock, which the GPU no longer runs
  on; its probe fails anyway, the vendor `rockchip_bus.c` naming its OPP regulator `pvtm` where it
  has only `bus`. The R69-1's factory tree disables it too. On 6.1: no probe errors.
- A first retest was void: another build held the volume, the package step refused, and a retry loop
  reported its `sleep`'s status. The box got the deploy's older package.
- 2.4 GHz on next2, Wi-Fi forced to `bg`, `iperf3 --bind-dev wlan0` against the host: upload 142
  Mb/s at 2437 MHz, -22 dBm; the download returned nothing. The band restored, the box set to boot
  6.1 and rebooted from next2; it did not come back on Ethernet or Wi-Fi within 5 minutes.
- The dark box was the watchdog strand, not Wi-Fi: next2's boot ended in a clean reboot, both
  kernels' shutdowns logging alike (`watchdog did not stop!`, 89 s armed, about 1 s to the reset);
  the next boot logged nothing and stayed dark until power-cycled. Twelve kernel switches earlier
  the same day came back. Where the dead boot stopped needs the serial pads.
- Serial console on the pads: `ttyFIQ0`, 1500000 baud. With it recording, 16 reboots alternating
  next2 and 6.1 all came back, 35–37 s each. The 2.4 GHz test repeated on next2: download 74.7 Mb/s,
  then a reboot into 6.1, back in 37 s. Neither the empty download nor the strand reproduced.

## 2026-11-22 — the 6.1 decoder probe freeze

- The serial console caught it: after the regression's panic, a power-key restart, and a soft
  reboot, the 6.1 boot froze 12.87 s in, inside `mpp_rkvdec2`'s probe, output cut mid-line. Only a
  power cut cleared it. The other three boxes passed the same steps.
- The vendor resets the decoder on errors and at shutdown only, never at probe. A reset at probe
  with the device's own hook, the RK3528's IOMMU force reset, froze every 6.1 boot, cold too:
  removed. The box was rescued by stopping U-Boot over serial, `setenv pxe_label_override l0`,
  booting next2.
- Without that patch, 32 warm reboots into 6.1, nothing run between them, all came back. The freeze
  needs something done before the reboot; the trigger is unknown. next2 never froze here.

## 2026-11-22 — the bundled remote

- 12 buttons, IR only: power, menu, home, the D-pad and OK, back, volume − and +, mouse. Usercode
  `0xfe01` (6.1's `code_print`), the factory's `ir_key6`. On 6.1 evtest read OK as `KEY_REPLY`, home
  as `KEY_HOME`, mouse as `KEY_TEXT`; the tree now gives them the canonical keys.
- next2 had no keymap, the receiver on `rc-empty`. NEC decoding read address `0x01` and each command
  as the vendor's code inverted: OK `0x13` for the vendor's `0xec`. `rc-hk1-rbox-k8s` maps the 12.
- The first two captures were empty: `ir-keytable -t` buffers into a pipe and `timeout`'s SIGTERM
  drops the buffer. `stdbuf -oL` fixed it.
- Power suspends to `deep` through logind. A sleep hook in `tvb-base` blanks the front panel before
  sleep and restarts its clock on waking.
- next2: `rc-hk1-rbox-k8s` loaded, evtest read all 11 non-power buttons as their keys. Power
  suspended the box to `deep`, and no press woke it; a power cut did.
- 6.1: power suspends to `deep` and the remote's power wakes it, both at once, the front panel dark
  asleep and the clock back on waking: the `tvb-base` sleep hook.
- 6.1 with the fixed table: home, OK and mouse read `KEY_HOMEPAGE`, `KEY_OK`, `KEY_TOUCHPAD_TOGGLE`.
- 6.1: after `poweroff.target`, the remote's power key started the box: `remote_support_psci`.
- The panel's first write is at 12 s, about 25 s after a press, with the clock saved at shutdown;
  NTP's set at 40.47 s now redraws it at 40.49 s (`OnClockChange`), not at the next minute.

## 2026-11-22 — VP9 on the vendor kernels

- OTP reads `35281000`; MPP refused VP9 on 6.1 without `rockchip,rk3528a` in the root compatible,
  while next2's V4L2 decoder plays it. With the name last, 6.1's `vp9_rkmpp` decoded 1920×1080 to
  8192×4320 identical to FFmpeg's decoder, downloaded as NV12; 8192×8192 gave 1 frame of 3.
- A first test hashed DRM PRIME frames without `hwdownload`: `-22`, no frames, on the R69-1 too.
- The 8192×8192 attempt aborted two decoder jobs, each reset; the warm reboot after it, and one
  after refused VP9 attempts, probed the decoder normally, console on the H313's serial adapter.
