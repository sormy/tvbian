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

## 2026-11-23 — `cma=16M`, and HDMI on a real screen

- `BOARD_CMDLINE` takes `cma=16M`, as every RK35xx sibling; the pool read 8192 kB from the tree,
  16384 kB after.
- With a 2256×1504 screen on HDMI: next2 reads `connected`, a 256-byte EDID and 23 modes, and the
  owner sees a picture. 6.1, the same screen, reads `disconnected`.
- 6.1's tree matches the siblings' for HDMI: pins, `reg` with GPIO0's bank, `hpd-gpios` GPIO0 A2,
  GRF. GPIO0 A2 reads high; its interrupt never fired. The vendor mirrors that GPIO into the VO GRF
  sink-detect bit once in `rockchip_hdmi_parse_dt()`, straight after setting the pin's input enable.
- A `u-boot-update` reset the menu's default to next2 again.
- Reproduced on four 6.1 boots, the screen attached each time: the connector `disconnected`, GPIO0
  A2 high, its interrupt 0, and `VO_GRF_HDMI_MASK` (`0xff360014`) `0x4b`: `SNKDET_SEL` 1,
  `SNKDET` 0. The controller holds the probe's "no sink" while the pin reads one.
- Writing `SNKDET` 1 by hand, as the vendor's GPIO interrupt would (`0x00200020` to `0xff360014`):
  `connected`, the 256-byte EDID, 23 modes, 2256×1504 at 60 Hz set and the console on the screen.
  The probe's mirrored level alone was wrong.
- `drm-rockchip-dw-hdmi-rk3528-hpd-at-detect.patch` mirrors the GPIO again at each hot-plug read;
  one patch for 6.1 and 6.12, whose functions are identical.
- UART2's DMA: both kernels run it in interrupt mode. The factory `dmas` have no `dma-names`; the
  vendor driver logs `failed to request DMA, use interrupt mode` (the R69-1's 6.1), mainline
  requests `rx` and `tx` by name and warns the same (`8250_port.c`). The trees differ only in that
  warning.
- 6.1 with the patch, four boots with the screen attached: each `connected`, the 256-byte EDID,
  `SNKDET` 1, and 2256×1504 at 60 Hz set at 12.8 s with the console on HDMI. Before it, four of four
  `disconnected`.

## 2026-11-24 — the analog codec on time

- The 6.1 codec's "3.02 s for a 2 s clip" was a misreading: `audio`'s clip is 3 s, and its `2` is
  the channel count. Every HK1 regression reads 3.01–3.03 s on all three kernels. On 6.1, by hand:
  3.03 s and 3.02 s for 3 s at 44.1 and 48 kHz, 2.02 s for 2 s.

## 2026-11-24 — the GPU's clock on 6.1

- The tree's "SCMI's 800 MHz, unthrottled here" was wrong on 6.1: `devfreq-ff700000.gpu` is bound to
  `soc-thermal`'s 85 °C passive trip, `step_wise`, beside the CPU's.
- On `ACLK_GPU_MALI` devfreq lists 300–800 MHz, but the clock stops at 498 MHz: 800 MHz asked, 800
  in `cur_freq`, 498000000 in `aclk_gpu_mali`.
- On SCMI, the factory's `core`, on 6.1: lima took 300 MHz at 875.7 mV; asking 500 MHz, which the
  table holds at the same 875 mV, reset the box, two of two, nothing in pstore. The table is
  `rockchip,pvtm-pvtpll`, set up by the vendor's OPP helpers, which lima does not call.
- With the GPU held powered (`power/control` `on`), SCMI stepped 500, 600, 700 and 800 MHz, no
  reset: the reset is the rate set with the GPU suspended, its clocks gated; `PD_GPU` is always-on.
  Through Rockchip's OPP helper lima read `pvtm-volt-sel=3`; 800 MHz at 912 mV, the table's
  default 950.
- `drm-lima-devfreq-rockchip-opp.patch`: the table through the helper, and no rate set unless the
  GPU is in use. With it, suspended: 500 and 800 MHz asked, 300 MHz kept, no reset.
- The tree's `core` on SCMI: glmark2 93, 76 on `ACLK_GPU_MALI`. A 600 s soak: 75.5 °C at most, the
  GPU 500 s at 800 MHz, no warning, the same boot.
- 6.12 with the patch and the tree: suspended, 500 and 800 MHz asked, 300 kept, no reset; glmark2
  105 at 800 MHz. Its first boot, warm from 6.1, did not come back, nor a power cut after; a later
  power cut booted it. The console saw none of it. On 6.1, three warm reboots on the tree, all back
  in 34–39 s.
- `U_BOOT_DEFAULT="l2"` in `/etc/default/u-boot`: each kernel install had made next2 the default.

## 2026-11-24 — the SDIO power-off delay

- The test, on 6.1: the Wi-Fi modules unloaded, `ffc20000.mmc` unbound and bound, the modules
  loaded, `wlan0` addressed. At 2 s: the unbind 3.7–3.9 s, `wlan0` back in 8.2 s, two of two. At 0
  µs (`fdtput`): the unbind 12–26 ms, `wlan0` back in 4.5 s, three of three; three warm reboots back
  in 35–37 s, both SDIO functions and `wlan0` addressed each time.
- A driver reload alone, its unload re-probing the host (`97`): at 2 s the unload 3.9–4.3 s, `wlan0`
  back in 8.2–8.6 s; at 0 µs 0.4 s and 4.7 s, three of three.
- The stall on vendor kernels alone: a shutdown at 0 µs, then a boot without B2 in the power
  sequence: B2 read high (`/sys/class/gpio`), no card. With the host unbound, B2 driven low by hand,
  then the host bound, the module loaded and unloaded, which stalls it again:

  | B2 low  | card back |
  | ------- | --------- |
  | none    | 0 of 14   |
  | 0 ms    | 0 of 1    |
  | 0.1 ms  | 2 of 3    |
  | 0.3 ms  | 3 of 3    |
  | 1 ms    | 4 of 4    |
  | 10 ms   | 4 of 4    |
  | 2000 ms | 1 of 1    |

- The reboot into a 10 ms DTB did not come back: no ping, no ARP, the console silent after a power
  cut, nothing captured of the boot. A serial capture started on the H313 after it.
- With the driver loaded, the host's unbind and bind oopsed in `aicbsp_get_feature`
  (`build/logs/hk1-rbox-k8s/vendor-sdio-rebind-oops.log`): processes blocked behind it ignored
  SIGKILL, and the reboot took 5 minutes of systemd's stop timeouts. No decoder freeze after it.
- The power cut booted 6.1 on the 10 ms DTB: both functions, `wlan0` addressed. The console capture
  had U-Boot only: the FTDI adapter on the H313 had reattached at 9600 baud.
- At 10 ms, the Wi-Fi driver unloaded and udev loading it back: unload 0.4 s, `wlan0` in 4.5–6.5 s
  on 6.1, 7.2 s on 6.12, three of three each. A warm reboot 6.1 to 6.12 came back in 38 s; 6.12 to
  6.1 did not, no ping after 6.5 minutes, the serial detached.
- Warm boots into 6.1: four of four back at 0 µs, none of two at 10 ms, a cold one back. Each hang
  followed SDIO power cycles; the decoder freeze hit on 2 s too. Which it is needs the console.
- At 2 s, the driver reloaded three times then a warm reboot into 6.1, from 6.1 twice and from 6.12
  once: three of three back in 36–37 s. Five reloads on 6.12 back in 9–29 s; one earlier missed a 60
  s wait with both functions present.
- The 2 s stays: it revives a stall and its warm boots come back; 10 ms hung both warm 6.1 boots,
  and 0 µs at shutdown leaves the card stalled for a boot without B2's pulse.

## 2026-11-24 — installed to eMMC

- `tvb-install -y` from SD to the 29.1 GiB eMMC: 3.4 GB of rootfs, its own UUID, the eMMC's
  idbloader, vendor storage (its MAC) and secure storage kept.
- With the SD out: 6.1 from the eMMC, root `ffbf0000.mmc` with `boot0` and `boot1`, both SDIO
  functions, `wlan0` addressed. With the SD in, the SD's menu boots: the SPL reads SD first.

## 2026-11-24 — kexec on the vendor kernels

- `CONFIG_KEXEC` and `CONFIG_KEXEC_FILE` in `kernel/rk35xx.fragment`: 6.1 and 6.12 had neither.
  `kexec-tools` on the box, `LOAD_KEXEC=false`: a reboot stays a reboot.
- 6.1 to 6.12, SCMI tree: up in 23 s; Wi-Fi, Bluetooth, the decoder and HDMI as a normal boot, but
  lima failed, `gpmmu dte write test fail`, error -5, a module reload the same: the GPU keeps 6.1's
  state without the firmware's reset.
- 6.12 to 6.12, committed tree: no kernel came up, nothing in pstore or the journal; the box reset
  by itself into the default 6.1.

## 2026-11-24 — the DDR rate, vendor against next2

- Vendor 6.12: `normal_rate = 786000000`, available 324 and 528 MHz, 528 for 17 minutes, no change.
- The factory DMC table enables two rows, 920 and 1056 MHz. Rockchip's
  `rockchip_dmcfreq_adjust_opp_table()`, 5.10 and 6.1 alike, writes BL31's trained rates over the
  enabled rows in order: 324 and 528 fit, 786 has no row. Stock Android stops at 528 too.
- next2's `rk3528_dmc_trained_opps()` adds every trained rate and runs 786 MHz: about half again the
  bandwidth, and most of next2's glmark2 lead, 117–127 against 93 and 105 at the same 800 MHz GPU.

## 2026-11-24 — the dark reboots are in the reset path

- Kexec from 6.1 into 6.12, then a reboot back through U-Boot, ten cycles planned: the kexecs came
  up 3 of 3 in 22–23 s, Wi-Fi and both SDIO functions each time; the third reboot into 6.1 went
  dark.
- Today's dark boots, all through the reset and U-Boot: two into 6.1 (10 ms tree), two into 6.12,
  one out of 6.12. Kexec into 6.12, 4 of 4 up. The 2026-11-22 strand, the watchdog counting across a
  soft reboot, fits; not proven.
- systemd's watchdog off (`RuntimeWatchdogSec=off`, `RebootWatchdogSec=off` in
  `/etc/systemd/system.conf.d/`, a test override): reboot 1 back in 32 s, reboot 2 dark. The
  watchdog strand is ruled out.
- The HK1's factory loader: DDR init V1.07 (2023-08-04), rkbin SPL v1.04 (2023-04-11). The R69-1,
  the M2 Plus, the 3518 and the 3518D carry DDR init v1.11 (2025) and 2025 SPLs, the same mainline
  U-Boot. rkbin's notes from V1.07 to v1.11: LPDDR3 ODT detection and Vref training (v1.09), Vref
  training off below 600 MHz (v1.10), a tRFC minimum (v1.11); none names a reboot.
- On the committed tree, the GPU on the CRU: warm reboots dark 2 of 7. Boots after a power cut fail
  too. The eMMC's wear `0x01`, pre-EOL normal; 41 °C; no MMC, ext4 or I/O errors.
- A candidate for the dark boots: mainline U-Boot's `rockchip_dnl_mode_check()` reads SARADC channel
  1 at each boot and, at 0–30, writes the boot ROM's download flag and resets; the ROM then waits on
  USB. The flag outlasts a warm reset. Channel 1 is every RK3528 box's recovery button, U-Boot's
  SARADC set alike on all; the HK1's reads 1014 in Linux. Not shown: a dark box on USB would be the
  proof.
- Resets by the hardware watchdog (armed 10 s, unpinged), committed tree: 5 back in 34–39 s, the
  sixth dark. The reset's path does not matter: PSCI's 2 of 7, the watchdog's 1 of 6.
- A U-Boot without SARADC, so with no download-key check, in the eMMC's first copy: dark 3 of 9,
  then a tenth; the download-key candidate is ruled out. The original back in both copies,
  `bf227874`.

## 2026-11-24 — dark reboots against the vendor build

- Warm reboots on the committed tree, a dark one power-cycled from the strip:

  | Vendor 6.1                          | kexec | Built        | Dark    |
  | ----------------------------------- | ----- | ------------ | ------- |
  | release `-7`, 17 Nov                | off   | CI           | 0 of 15 |
  | release `-8`, 23 Nov                | off   | CI           | 0 of 15 |
  | `-8`'s source, the `2026-11-23` tag | off   | here, cached | 0 of 16 |
  | `-8` with kexec                     | on    | here, cached | 3 of 11 |
  | the same, `TVB_BUILD_CACHE=0`       | on    | here, clean  | 3 of 15 |
  | with the lima patch and AIC8800 94  | on    | here, cached | 5 of 16 |

- The configs differ only by `KEXEC`, `KEXEC_FILE`, `KEXEC_CORE`, `CRASH_CORE` and `TRANS_TABLE`;
  both `gcc 14.2.0-19`, KASLR on, the images 2 KB apart. A plain reboot runs no kexec code; how it
  darkens a boot is not known. The 3518 on the same kexec build: 0 dark in 10.
- The kexec build with `nokaslr` (KASLR's lines gone from the log): dark 3 of the first 6. The
  virtual layout is not it. U-Boot's `booti` puts the Image at `kernel_addr_r` `0x02000000` either
  way, `image_size` `0x25B0000` in both headers, clear of the DTB at `0x12000000`.
- `memtester 2500M` at the DMC's 528 MHz, stopped after 7 tests: all `ok`.
- Back on `-8`'s source built here, kexec off (`e35a1834`).
- kexec out of `kernel/rk35xx.fragment` again: the vendor kernels build as the releases do.
- Same source, built here, kexec the only difference: off 0 of 16, on 6 of 26. Equal rates would
  give this split about 4 % of the time: not yet evidence.
- A/B, `-8`'s source built here, kexec the only difference, blocks of 10 warm reboots alternated,
  the first reboot after each switch not counted: off 1, 0, 0 (1 of 30); on 1, 2, 3 (6 of 30). Both
  go dark: kexec is not the cause. On's excess would come by chance 5 % of the time one-sided, 10 %
  two-sided.
- The kexec build with the decoder's node `disabled` (the committed tree otherwise): dark 3 of the
  first 12 counted. The decoder's probe is not it.
- kexec back in `kernel/rk35xx.fragment`: the A/B shows it is not the cause.

## 2026-11-25 — the hang is the DMC's DDR rate change

- Serial's ground had come off the clip: the garbled console of the earlier power cycles was that,
  not the board. Every not-ok reboot since then was a hang, none a booted box without Wi-Fi.
- The kexec build, 20 warm reboots each, the console reading the last line:

  | DTB                       | Hang | Last line                            |
  | ------------------------- | ---- | ------------------------------------ |
  | committed                 | 7    | `mpp_rkvdec2 ff740100.rkvd…`, 8.38 s |
  | decoder and its IOMMU off | 5    | `mpp_jpgdec …`, 8.37 s               |
  | `mpp-srv` off             | 5    | `rockchip-dmc dmc: avs=0`, 8.36 s    |
  | `dmc` off                 | 0    |                                      |

- The DMC finds 786 MHz from the loader, its table holds 324 and 528, and `dmc_ondemand` asks for
  `normal_rate` 786: devfreq clamps it to 528 and BL31 changes the rate mid-probe. The M2 Plus's
  table holds 786, so it never changes rate at boot.
- At runtime, idle, the userspace governor stepping 528 and 324: one step by hand held; the scripted
  stepping reset the box twice, the console going from the login prompt straight to the DDR init's
  banner, nothing between (`build/logs/hk1-rbox-k8s/vendor-ddr-runtime-step-reset.log`). The rate
  change itself fails on this board, not only at boot.
- The DDR rates BL31 trained, from the DMC's `available_frequencies` with a third row enabled: 324,
  528, 666 and 786 MHz. The M2 Plus's table holds all four; the HK1's factory table, two.
- The HK1's own 1184 MHz row enabled (three rows, boot change 786 to 666 MHz): hang on reboot 3 of
  3, at 8.38 s. A smaller rate step still hangs.
- The DMC's `center-supply` is `vdd_logic`, a PWM rail that starts at 900 mV; the DMC rows ask 850.
  On the HK1 the GPU's `mali-supply` is the same rail; on the M2 Plus the DMC is its only user. Test
  waiting: `vdd_logic` held at 900 mV.
- `vdd_logic` held at 900 mV: every boot hung, 12 of 12, at 8.28 s. The rail registers at 899 mV, so
  the floor made the regulator core write the PWM, by 1 mV. Recovered by stopping U-Boot on the
  serial console and booting 6.1 by hand with `board.dtb.committed`.
- At runtime, lima raising the GPU to 800 MHz moved `vdd_logic` 851 to 875 mV (PWM duty 2450 to 2850
  ns): the box stayed up. The scripted DMC steps, 528 and 324 MHz, both at 850 mV, reset it with no
  voltage write.
- So the DDR rate change fails on this board whatever the voltage, and a logic-rail write during
  boot does too. The DMC does only harm here: `board.patch` disables it, the DDR staying at the 786
  MHz its own loader trains, as on the M2 Plus, which never changes rate at boot.
- next2 on this eMMC: every write fails after the card re-initialises at 4 s, root read-only; passed
  to the next2 work.
- With the DMC off in `board.patch` (`7f2b41e2`), the full build (lima, AIC8800 `94`, kexec): 20
  warm reboots on 6.1 and 20 on 6.12, none hung; `vdd_logic` stays at 899 mV.
- That is a workaround, not a fix: why the rate change fails here is open, on the HK1's todo page.
- memtester at 786 MHz, the DMC off: one full pass over 3000 MB clean, a second stopped 10 minutes
  in, clean.
- Wall-clock decode, `ffmpeg9 -c:v <codec>_rkmpp` to null, synthetic clips, three runs each, the DDR
  at 786 MHz: H.264 High 3840×2160 at 60, 600 pictures, 44.1 fps (42.3 at 528 MHz); HEVC Main10
  7680×4320 at 25, 50 pictures, 20.4 fps (16.4).
- `video.py run --engine rkmpp --suite decode` on vendor 6.1, the DDR at 786 MHz
  (`build/validate/video/hk1-rbox-k8s-6.1-dmcoff.json`): every codec at or above the M2 Plus's 6.1
  run; at 3840×2160 H.264 61.6 fps, HEVC 116.9, HEVC Main10 112.4. The 42.3 and 16.4 fps above were
  wall clock, FFmpeg's start included, not the engine's.
- H.264 4:2:2 and 4:0:0 came back broken: `h264_rkmpp` logs `Unsupported frame format 0x2` and
  `0xc`, MPP's NV16 and YUV400. A family item, on `docs/todo/rk35xx.md`.
- Composite writeback on vendor 6.1, `display.py composite`: PAL and NTSC set on CRTC 117, each
  capture signalled done, the buffer unwritten: six equal bars, black or all-zero NV12 (0, 77, 0). A
  frame-height capture (576, 480 lines) instead of a field's gave the same. Rockchip's
  `vop2_wb_commit` enables writeback on the RK3528 without a check for the video port or interlace.
  A family item, on `docs/todo/rk35xx.md`.
- Vendor 6.12 entered by kexec, then `systemctl poweroff`: the box came back on its own, answering
  SSH 113 s later. `watchdog-dw-wdt-stop-at-power-off.patch` added to `kernel/rk35xx-next.conf`.
- 6.1 (the next2 work's build) and 6.12, each with `watchdog-dw-wdt-stop-at-power-off.patch`, each
  installed with its own modules: after `systemctl poweroff` neither answered for 333 s; the strip
  brought each back.
- The install also took next2's 7.3.6, and `U_BOOT_DEFAULT="l2"` in `/etc/default/u-boot` then named
  6.12: the default counts labels, not kernels. 7.3.6 was a debug build: removed and purged, with
  the next2 metapackage the box never had; 6.1 is `l2` again.
- The next2 work's 3518D soak on 6.1 logged
  `devfreq ff700000.gpu: Couldn't update frequency transition information.` 201 and 257 times,
  against 11–12 before: with the GPU suspended the lima patch reported `clk_get_rate()`, and the
  3518D's CRU clock rounds below its OPP. The patch now reports the OPP the clock rounds to. On the
  HK1 with it: 0 warnings under glmark2; `min_freq` written with the GPU suspended reports 800 MHz,
  no reset.
- With the fix, the next2 work's 120 s `box.py` soak on the 3518D, 6.1: 0 transition warnings,
  temperature and CPU ops in line with earlier vendor runs. Its GPU offers 700 and 800 MHz, the
  factory table's two rows.
- 6.12 rebuilt with the fixed lima patch, booted from the menu: 0 transition warnings under glmark2,
  800 MHz; `min_freq` written with the GPU suspended reports 800 MHz, no reset. Entered by kexec
  from 6.1 instead, lima failed to probe: `gpmmu dte write test fail`, error -5. On
  `docs/todo/rk35xx.md`.
- For the next2 work, vendor 6.1 kexec'd into next2 7.3.5 with `keep_bootcon loglevel=8`: ramoops
  registered at 0.077 s; the last line, at 1.23 s, `clk: Disabling unused clocks`, then nothing for
  2.5 minutes and no watchdog reset; the strip brought it back to 6.1
  (`build/logs/hk1-rbox-k8s/next2-kexec-from-6.1-hang.log`).
- The same kexec plus `clk_ignore_unused`: past 1.24 s to `/init`, but the CRU never registered
  (`of_clk_src_onecell_get: invalid clock index 511`,
  `couldn't get clock 0 for /clock-controller@ff4a0000`); at 12.2 s every clock consumer deferred,
  then the box reset into 6.1
  (`build/logs/hk1-rbox-k8s/next2-kexec-from-6.1-clk-ignore-unused.log`). The box's 7.3.5 kernel
  came from `build/out/debs` at 22:11, its `board-next2.dtb` from the commit: the pair may not
  match.
- The same 7.3.5 kernel and DTB picked once from U-Boot's menu: no clock errors, 0 deferred devices.
  The pair matches; the unregistered CRU comes only from the kexec from 6.1.
- Which tree a kexec'd next2 holds, read by an `/init` overlay printing to `/dev/kmsg`: after
  `kexec -l --dtb=<next2>`, 104610 bytes, the vendor compatible order, and U-Boot's `/chosen`
  (`u-boot,version`, `smbios3-entrypoint`): 6.1's own tree. kexec-tools 2.0.29 loads through
  `kexec_file_load`, which on arm64 copies the running kernel's tree and ignores `--dtb`. With `-c`
  (classic `kexec_load`), next2 got its own file and panicked at 0 s,
  `Failed to allocate page table page`: `board-next2.dtb` has no `/memory`, U-Boot adds it at boot
  (`build/logs/hk1-rbox-k8s/next2-kexec-c-own-tree-panic.log`). `tools/validate/kexec_once.py` as
  written enters a test kernel on the running kernel's tree; passed to the next2 work.
- `video.py run --engine rkmpp --suite encode` on vendor 6.1
  (`build/validate/video/hk1-rbox-k8s-6.1-encode.json`): H.264 and HEVC pass to 8192×8192, 16384
  broken; at 1920×1080 53.6 and 60.5 fps, beside the M2 Plus's 53 and 60. `board.md`'s other encode
  rows ➖, VC-1 decode ❓ with no FFmpeg path, as on the M2 Plus.
- 10-bit encode, vendor 6.1: `hevc_rkmpp` and `h264_rkmpp` list `nv12` and `yuv420p` only; a
  `p010le` source with `-profile:v main10` came out `Main, yuv420p`, and `h264_rkmpp` has no
  `high10`. The hardware's 10-bit encode is untested; `board.md`'s 10-bit encode rows ❓, not ➖.
- 10-bit encode has no path in any software we have, by the next2 work's reading: next2's rkvenc
  lists 23 source formats, all 8-bit; MPP's VEPU540C maps every `*_10BIT` format to
  `VEPU5xx_FMT_BUTT` ("unsupport frame format"), and its H.265 and H.264 writers fix the bit depth
  at 8. The datasheet says HEVC Main. The 10-bit encode rows ➖.
- `h264_rkmpp` wrote Constrained Baseline: the wrapper never set a profile, and MPP's default is
  Baseline. `patches/ffmpeg/0063` sets it, High for H.264 unless asked, and refuses one MPP does not
  write; `0062` exports MPP's 4:2:2 and 4:0:0 frames as NV16 and R8. On the HK1, vendor 6.1:
  - 4:2:2 and 4:0:0 at 1080p and 4K bit-exact against the software decode; `video.py` decode, its
    rkmpp download now in the codec's format: 46.9 and 75.5 fps at 3840×2160.
  - Encode High: 52.9 fps at 1920×1080 against Baseline's 53.6; at the same bitrate 46.44 dB against
    45.42, 41.41 against 40.66 at 8192×8192 (`hk1-rbox-k8s-6.1-encode-high.json`).
  - `-profile:v 77` and `66` give Main and Constrained Baseline; HEVC `main10` is refused.
- stress-ng STREAM, 15 s, three runs each, the DDR at 786 MHz: 1252–1273 MB/s with one worker,
  2794–2848 with four, against 983 and 1925 at 528 MHz.
- The RTL8153 adapter in a USB 2 port, behind the box's `1d5c:5011` USB 2.0 hub, at 480 Mb/s on
  EHCI; the xHCI SuperSpeed bus empty. Vendor 6.1, 15 warm reboots: `eth1` back at 1000 every time,
  no xHCI errors. `iperf3 -c plex --bind-dev eth1`, 10 s: 309 Mb/s up, 321 down, the USB 2 limit.
  The SuperSpeed port is still to test.
- The owner: the front panel shows the time only, no status icons.
- next2 7.3.6 with the next2 work's eMMC-taps patch, booted once from the menu, hung waiting for
  root: every eMMC read failed (`I/O error, dev mmcblk1, sector 0 op 0x0:(READ)`, 132 lines), so the
  boot-once hook never ran and every boot took it again
  (`build/logs/hk1-rbox-k8s/next2-emmc-taps-boot-once.log`). The serial clips, knocked loose, were
  reseated; the menu's 6.1 entry was picked over serial, then `default l3` and `U_BOOT_DEFAULT`
  restored and `/var/lib/tvb-boot-once` removed.
- The blue USB 3 port, vendor 6.1: a Lexar USB 2.10 stick on the xHCI bus at 480 Mb/s, 512 MiB
  direct reads 36.1 MB/s twice. The SuperSpeed bus saw no device; the RTL8153 stayed on the USB 2
  hub.
- next2 7.3.6 on the next2 work's HS200-only tree, picked once from the menu over serial: root rw,
  no eMMC errors, HS200 at 148.5 MHz (`build/logs/hk1-rbox-k8s/next2-hs200-boot.log`). Its fio, 512
  MiB direct with crc32c verify: 66.1 MiB/s write, 114 read, a verify-only pass clean. The
  `invalid driver type` lines come at HS200 too: harmless. next2 drives this card at HS200, not
  HS400ES.
- next2 regression, its first boot on the HS200 tree:
  `mmc1: error -110 whilst initialising MMC card` at 2.84 s, no `mmcblk1`, initramfs waiting for
  root two hours (`build/logs/hk1-rbox-k8s/next2-regression-hang.log`). The earlier HS200 boot came
  up: next2's HS200 card init is flaky here. Recovered by a power cycle and 6.1 picked over serial.
- The Lexar USB 2.10 stick, disposable by the owner, in the blue port, vendor 6.1: `usb-storage` at
  480 Mb/s on xHCI; `fio` 256 MB read-only 33.2 MB/s, 128 MB write at 8 GiB 28.7 MB/s, crc32c verify
  clean, `stress-ng` on four CPUs and a 256 MB VM worker beside it; no USB resets.
- A SanDisk V30 `SH64G` in the SD slot, vendor 6.1: high speed, 49.8 MHz, 4 bits, 3.3 V. `fio`, the
  fixed runs on a file on its ext4: 23.9 MB/s read, 20.8 write, 2133 and 311 IOPS 4K; no CRC error.
  Stock's tree gives the slot no `vqmmc-supply` or UHS mode; its `vccio_sd` is a fixed 1.8 V nothing
  uses, where the M2 Plus's is GPIO4 B6 switching 3.3 and 1.8 V. High speed is the most stock ran.
- The Lexar USB 3.2 stick: high speed at boot (`usb 1-1` at 8.5 s); replugged, SuperSpeed on `uas`
  (`usb 2-1` at 271 s, 5000 Mb/s). The port does SuperSpeed; the boot-time enumeration does not.
- The Lexar at boot on three warm reboots and a power cycle: SuperSpeed at 8.7 s every time; the one
  high-speed boot did not repeat. Under `fio` with `stress-ng`, 1 GB: 360 MB/s read, 317 write,
  crc32c clean.
- SD hotplug, vendor 6.1: a card in at 81.0 s, read at high speed; removed at 91.6 s.
- Front panel: `display` brightness 1 to 8 written and read back; the owner saw no change.
- Built-in Ethernet against Plex, negotiated: 10 Mb/s full 9.39 up, 9.30 down; 100 Mb/s full 93.65
  up, 94.10 down; no retransmits. Forced 10 Mb/s with autoneg off left the switch at half duplex.
- Deep sleep with the DMC off, woken by the remote's power key: 1 success, Wi-Fi and the Lexar back;
  `xHC error in resume, USBSTS 0x401, Reinit` on resume, the stick back at 5000.
- An LE scan, 12 s: 16 devices, no HCI errors. The box comes with no BLE remote.
- The ports, from where each device enumerated: the USB 2 port on xHCI's high-speed side (`1-1`, the
  OTG PHY); the blue port's high-speed lines on EHCI (`3-1`), its SuperSpeed on xHCI (`2-1`). The
  `1d5c:5011` USB 2.0 hub was inside the Ethernet adapter, which sat in the blue port; the Lexar's
  one high-speed boot was in the USB 2 port. Corrects the entries above.
- The Lexar in the USB 2 port, `usb-storage` at 480 Mb/s, under `stress-ng`: 256 MB read-only 34.9
  MB/s, 128 MB written at 8 GiB 32.0 MB/s, crc32c clean.
- A Logitech receiver `046d:c52b` in the USB 2 port: full speed, 12 Mb/s, on xHCI; HID keyboard,
  mouse and consumer control. `evtest`: the owner's keys arrived. The USB 2 port is the OTG port,
  the one recovery's Loader uses: both modes now shown.
- `systemctl poweroff` on 6.1, the DMC off and the watchdog patch in: off about 5 minutes on its
  own, then on from the remote's power key, a new boot ID, 6.1 the default.
- On a 2256×1504 HDMI screen, vendor 6.1: `speaker-test` to `hw:0,0` heard; glmark2-es2-drm build,
  phong shading and texture at 60 fps, the owner seeing no artifact, the GPU at 800 MHz. No 4K mode
  on it: the 4K60 player and HDR wait for a 4K TV.
- DDC/CI: dw-hdmi's I2C master refused the request at 0x37 (`EOPNOTSUPP`, plain and combined
  transfers alike). Every other RK3528 vendor tree carries the HDMI DDC as `i2c-gpio`, the HDMI pin
  group keeping CEC; the HK1's patch now does too, its pins from its own `hdmi_pins` (`a8e11901`).
  6.1: EDID read over it, 2256×1504; VCP 0x10 brightness 100/100, 0x12 contrast 50/100, 0x62 volume
  20/100; brightness set to 80, read back, restored. 6.12: the bus up, VCP 0x10 read.
- On a TV over the AV jack, vendor 6.1: `Composite-1` forced on, PAL and NTSC colour bars from
  `modetest` seen. `speaker-test` on `hw:1,0`, the codec, ran on time but nothing was heard: during
  playback `ACODEC_ANA09` and `ANA0D` stay 0, the line out muted, and `pa-ctl` on GPIO0 A0 stays
  low. Rockchip's `rk3528_mute_stream` unmutes both, so it is never called for this card.
- Correction: the silent playback went to HDMI. ALSA's card numbers changed between boots, the codec
  card 0 and HDMI card 1, so `hw:1,0` was HDMI, unplugged. Played by name,
  `plughw:CARD=rk3528acodec,DEV=0`: `rk3528_hw_params` and `rk3528_mute_stream` ran, the line out
  unmuted (`ANA09`, `ANA0D` 0x31), `pa-ctl` high, and the owner heard it on the TV.
- Front panel brightness again, levels 1 and 8 held 3 s each: the owner saw it change. The first
  sweep's 1 s steps went unnoticed; brightness works.
- The sweep 1 to 8 at 2 s each, two rounds: the owner saw eight distinct levels.
- Fuseamp, the owner's player, on the 2256×1504 screen: 4K24 HEVC with Dolby audio and H.264 played.
  No HDMI sound: it opened `pcmC0D0p`, card 0, the codec on this boot. ALSA's default now names
  HDMI, `boards/common/alsa-hdmi-default.conf` to `/etc/alsa/conf.d/60-tvb-hdmi-default.conf`,
  picked by every RK35xx board: `defaults.pcm.card rockchiphdmi` broke alsa-lib's configuration;
  `pcm.!default` on `hw:CARD=rockchiphdmi,DEV=0` plays. The owner heard Fuseamp over HDMI. The next2
  trees name the card `rockchip,hdmi` too.
- HDR HEVC in Fuseamp on the owner's HDR monitor (EDID: EOTF SDR and PQ, BT.2020 YCC only, YCbCr
  4:4:4 and 4:2:2, DC_30 and DC_Y444, TMDS 300 MHz). Fuseamp set `max bpc` 10 and `Colorspace`
  `BT2020_YCC`; dw-hdmi's status read `RGB`, 8 bit, `ITU.BT601`, `EOTF: ST2084`. The vendor's
  `dw_hdmi_rockchip_select_output` takes the depth from its own `color_depth`, 8, and never from
  `max bpc`, so its BT.2020 path to 10-bit YCbCr 4:2:2 is skipped.
  `drm-rockchip-dw-hdmi-max-bpc-deep-colour.patch` lets `max bpc` above 8 ask for 10 bits.
- With the max-bpc patch, vendor 6.1: Fuseamp's HDR switch gave `YUV422`, 10 bit, `ITU.BT2020`,
  `EOTF: ST2084` at the same 235.7 MHz TMDS; the video plane `Cluster0-win0` took the 3840×2160
  `YU10` AFBC picture. One Dolby Vision HEVC stream froze in Fuseamp after the switch, its plane
  left on one framebuffer, passed to the Fuseamp work; a 4K HDR10 film then played with no glitch.
- 6.12 with the max-bpc patch, the same 4K 10-bit HEVC HDR10 film at 24 fps in Fuseamp: `YUV422`, 10
  bit, `EOTF: ST2084`; AVI `FC_AVICONF1` (0x101A) 0xc8, colorimetry extended, and `FC_AVICONF2`
  (0x101B) 0x60, extended colorimetry 6, BT.2020; the plane flipping. 6.12's `hdmi0/status` prints
  `ITU.BT601` all the same: its debug print decodes the DRM colorimetry with the V4L2 enum.
- The owner: 4K24 in a player is enough for the player check; 4K60 not asked.
- `display.py --no-ladder` on vendor 6.1 with the max-bpc patch, the HDMI cable out
  (`build/logs/hk1-rbox-k8s/vendor-61-display-max-bpc.log`): 43 passed, 13 failed. SDR, PQ, HLG at
  max bpc 8 and 10 pass, PQ and HLG with EOTF 2 and 3, extended colorimetry 6; 1920-wide max bpc 10
  gives `VP_PR_CD` 0x50. Failing: 3840-wide 60 Hz max bpc 10 stays RGB 8-bit, not YCbCr 4:2:0; AFBC
  rotation by 90 and 270; 3D frame packing; BG24 writeback; composite writeback. A first run, the
  cable pulled during it, also failed the PQ and HLG cases.
- glmark2-es2-drm `--off-screen -b build:duration=8`, the EDID override forced on, no screen: vendor
  6.1 108 fps, 117 with `vblank_mode=0`, `scmi_clk_gpu` at 800 MHz as the GPU's `core`; vendor 6.12
  128 and 135. The build scene by the next2 work: the 3518D on vendor 6.1, its GPU at 300 MHz, 86;
  next2 177 on the 3518D, 192 on the M2 Plus. The 57 reported above was a faulty run.
- The DDR at 786 MHz and thermals: the factory tree's 75 and 85 °C trips cool the CPU and GPU only,
  no DMC map; the DMC's one temperature rule raises its voltage to 900 mV below 10 °C, which the
  loader's 899 mV `vdd_logic` already holds. Combined load, `stress-ng` four CPUs and two 512 MB VM
  workers with glmark2 on the GPU, 120 s: 48 °C idle, 68.9 °C peak, no cooling state engaged.
- The next2 work's corrected RK3528 eMMC taps patch: three kexec boots each at HS200 and HS400ES
  clean, no -110, HS400ES reading 102 MiB/s, boot0 writes verified; the next2 tree's HS200 hunk
  dropped.
- Vendor 6.12 on the M2 Plus, by the next2 work: `vdd_gpu` at full PWM duty, 1148 mV, its maximum,
  while the GPU idles, 873 mV while it renders; 6.1 holds 873 mV. The lima patch's 6.12 path is the
  suspect; open.
- The next2 work's HK1 regression, vendor 6.1: the video step died on a 16384x8640 H.264 encode, the
  box off the network until a power cut; the same case had failed cleanly twice the day before.
  `patches/ffmpeg/0067` refuses a frame past 8192x8192 at the encoder's open. With it, 16384x8640 is
  refused in 1 s ("16384x8640 is larger than the hardware's 8192x8192"), 8192x8192 still encodes,
  the box up.
- Vendor 6.12's PWM rails at their maximum from boot (vdd_logic 1006 mV on the HK1, by the next2
  work) is the regulator, not lima: upstream's `pwm_regulator_init_boot_on` sets a disabled
  inverse-polarity boot-on PWM to full duty, and Rockchip's enable then skips
  `regulator-init-microvolt`, which it applies only at duty 0.
  `6.12/regulator-pwm-init-voltage-over-boot-on-duty.patch` leaves the duty alone where an init
  voltage is given.
- 6.12 with the regulator patch, booted from the menu once (U-Boot leaves the PWM disabled; after a
  kexec 6.1 leaves it enabled, and `init_boot_on` returns early either way): `vdd_logic` at 899 mV,
  duty 3250 of 5000 ns, the GPU bound and suspended, never used. Before the patch, 5000 of 5000,
  1006 mV. Entered by kexec from 6.1, lima again failed `gpmmu dte write test fail`, the box's own
  tree loaded.
