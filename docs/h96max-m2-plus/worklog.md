# H96 Max M2 Plus worklog

## 2026-11-05 — First contact

- Owner supplied the purchase URL, listing title, specifications and both PCB photos.
- Listing advertises RK3528, Android 14, Wi-Fi 6 and Bluetooth 5.4; hardware confirmation pending.
- PCB reads `M2_P_ZX_20250328`; SoC covered by heatsink.
- Owner accepted board ID `h96max-m2-plus` and has an OTG cable.
- No board writes performed; stock backup pending.
- Owner confirmed the date suffix is part of the PCB name: `BOARD_PCB=M2_P_ZX_20250328`.

## 2026-11-05 — Listing access

- Web tool could not open the AliExpress listing; item-number search returned no results.
- Owner supplied the title and specification image instead.

## 2026-11-05 — USB access and stock extraction

- With DC disconnected, holding the PCB button while attaching USB-A OTG entered factory Loader.
- `rkdeveloptool ld`: `2207:350c`, Loader. `rci`: `38 32 35 33`, RK3528.
- `rfi`: 61,079,552 sectors; expected image size 31,272,730,624 bytes.
- Sandboxed rkdeveloptool saw no device; host I/O Registry showed the Rockchip download gadget. USB
  access outside the sandbox enumerated it successfully.
- Two `rl 64 4096` reads each returned 2,097,152 bytes, byte-identical. SHA-256:
  `5ef455a92bc425d4fb5ac9f296927f9526f6f0306e3718c4298d22cc387f5d4d`.
- IDB header `RKNS`; DDR entry sector 4, 120 sectors. DDR banner: `ddr-v1.11 4bit PCB-56f70fd2ad`.
- `./build.sh loader h96max-m2-plus` packed the board's own DDR init.
- `rd 3` entered Maskrom; `db boards/h96max-m2-plus/maskrom_loader.bin` succeeded.
- Recovery-loader boot-block read matched both factory reads, including byte count.
- Full `rl 0 61079552` started with a 2400-second cap; log:
  `build/logs/h96max-m2-plus/stock-backup.log`. No eMMC writes performed.
- GPT, kernel and U-Boot trees extracted from completed host-image ranges during backup.
- Android logical partition geometry, metadata header and table checksums passed; vendor and
  vendor_dlkm extracted from their linear extents.
- `e2cp` extracted `vendor:/etc/firmware/SWT6621S_NV_SDIO.bin`; 220 bytes, matching the packaged
  `SWT6621S_NV_SDIO_STANDALONE_FDD.bin` exactly. Both SHA-256:
  `8a3875ca90672ae87a28c5a629a218a98cbf3377a09757525601e3fb279b1693`.
- Packaged shared NV differs: SHA-256
  `13e120659acd80066ea71db418cf8518e47086fa4c08cde2b28e63d41672f6ae`.
- IRAM, DRAM and combined radio firmware also match the packaged SWT6621S files exactly.
- Static build properties: `H96_Max_M2PLUS`, `RZX.V01.20251231.1026`, Android 14 `userdebug`.
- Embedded kernel banner and IKCONFIG: 6.1.118 build 315, ARMv7. U-Boot banner: 2017.09 build s401.

## 2026-11-05 — Artifacts prepared

- `./build.sh board-dtb h96max-m2-plus`: 302 cells named, none unnamed.
- `./build.sh uboot-dtb h96max-m2-plus`: 45 cells named, none unnamed.
- U-Boot factory tree differs from H96 Max 3518 only in `fixed-emmc-driver-type`: 4, retained.
- `./build.sh uboot h96max-m2-plus`: v2026.10, 734,208-byte FIT; host artifact only.
- U-Boot build retained factory-tree warnings about raw references, interrupts and SPI numbering;
  log: `build/logs/h96max-m2-plus/uboot-build.log`.
- `./build.sh board h96max-m2-plus`: board package built; log:
  `build/logs/h96max-m2-plus/board-build.log`.
- Image build started; log: `build/logs/h96max-m2-plus/image-build.log`.
- No TVBian boot attempted; prepared tree changes remain unverified on this board.

## 2026-11-05 — Backup complete and boot route corrected

- Full stock read exited 0; image size exactly 31,272,730,624 bytes.
- Independent reads of the boot block, super header and final 33 sectors match the image.
- Primary GPT points to the final sector's valid backup GPT header. Verification summary:
  `build/logs/h96max-m2-plus/backup-verification.txt`.
- Test image built: `tvbian-h96max-m2-plus-trixie-2026-11-06.img.xz`.
- Image root extracted and checked against the board's tree and full PCB name; extlinux selects
  kernel 6.1.172 and `/usr/lib/tvb/board.dtb`. Installed radio NV matches the stock dump.
- Separate private bring-up image prepared with the owner's public key and password age cleared;
  filesystem check passed. No credentials added to repo payloads.
- Owner wrote 1,074,807,808 bytes to the selected SD card; no card readback performed here.
- Owner checked the box: no SD slot. SD route abandoned before any box write.
- No reboot or eMMC write performed; USB-console investigation changed no U-Boot source or config.

## 2026-11-05 — Direct eMMC risk assessment

- `diff -u boards/h96max-3518/factory_uboot.dts boards/h96max-m2-plus/factory_uboot.dts`: only
  factory `fixed-emmc-driver-type`, 1 versus 4.
- Equivalent comparison of prepared `uboot.dts`: only model/comment and that retained driver type.
- Same `uboot/rk3528.conf`: U-Boot v2026.10, vendor-storage patch, BL31 v1.21, ADC enabled.
- Factory DDR-init and SPL remain in protected sectors; no replacement DDR tuning proposed.
- Existing family board reports record eMMC boots and button-to-Maskrom recovery, but this board has
  not booted the prepared FIT or tested that button path under it.
- Main unresolved risk: a failure before U-Boot can read the recovery button leaves no tested
  cable-only recovery route. A second U-Boot copy does not rescue a valid FIT that hangs after
  handoff. Serial or a hardware Maskrom entry may then be needed.

## 2026-11-05 — eMMC commands prepared

- Owner has serial available and chose a direct eMMC attempt; requested commands to run by hand.
- Prepared `backup/h96max-m2-plus-bringup-preserved.img`, 1,074,807,808 bytes, from the private
  bring-up image with every `preserve-sectors.rk35xx` range restored from this unit's stock image.
- All protected ranges compared byte-for-byte; U-Boot FIT also matched its build artifact.
- Image SHA-256: `7474ac7dee5e7af47bd7ff10c5251822d6526f6cca317412c83582ba52cb471d`.
- Current OTG session: Maskrom with usbplug resident; flash query still succeeds, 61,079,552
  sectors.
- Commands supplied for write, complete image-sized readback, comparison and reboot only after
  success. No flash command run by the agent.

## 2026-11-05 — First TVBian runtime checks

- Owner supplied SSH access after direct eMMC installation; both Ethernet and Wi-Fi connected.
- Full image-sized flash readback matches the preserved bring-up image with `cmp`.
- Running `6.1.172-tvb-rk35xx`; installed board identity and DTB hash match the repo artifacts.
- Boot evidence: `build/logs/h96max-m2-plus/first-live-system.log`; no failed systemd services.
- `stress-ng --vm 1 --vm-bytes 2800M --vm-keep --verify --timeout 60s --metrics-brief`: exit 0; log:
  `build/logs/h96max-m2-plus/ram-stress.log`.
- Bounded Bluetooth discovery found LE and BR/EDR devices; controller reports no RX/TX errors.
- Initial `iperf3` tests used `plex`, explicitly bound to each interface. These overlapped RAM
  verification and Bluetooth discovery; not the quiet three-run median required for comparison.
- Network evidence: `build/logs/h96max-m2-plus/network-baseline.log`.
- One watched warm reboot returned both interfaces and all three addresses unchanged; log:
  `build/logs/h96max-m2-plus/warm-boot-01.log`.
- Stock vendor-storage copies decoded from the backup: newest valid copy version 5, Ethernet matches
  LAN_MAC. No Wi-Fi or Bluetooth address item in that copy; their chip source not verified.
- Wi-Fi's vendor-address lookup failure is not proof of a missing Ethernet address. The radio
  remains usable; station-info length warnings and TXBA renegotiation remain findings.
- eMMC partition verification passes after first-boot growth; initial GPT warnings preceded it.
- Watchdog clock readback is 24 MHz; systemd grants the 89-second hardware step.
- Owner requested saved scripts fed to `ssh 'sh -s'`; scripts kept under
  `build/logs/h96max-m2-plus/scripts/`.
- Changing Codex configuration did not alter the running session's restricted network sandbox.
- Watchdog test: released PID 1's device over D-Bus, opened `/dev/watchdog0`, requested 600 then 10
  seconds; ioctl returned 600 then 11, final GETTIMEOUT 11. Pinged once and stopped.
- Board returned with a new boot ID, both networks and unchanged addresses; exact reset latency was
  not captured. Above-hardware timeout accepted by the watchdog core, not clamped at ioctl.
- Saved reset script: `build/logs/h96max-m2-plus/scripts/watchdog.sh`; further timing verification
  remains before closing the watchdog reset check.
- Forced `echo c > /proc/sysrq-trigger`: board returned on both networks; archived `dmesg-ramoops-0`
  contains `Kernel panic - not syncing: sysrq triggered crash`. Evidence:
  `build/logs/h96max-m2-plus/panic-recovery.log`.
- Five-minute `stress-ng --cpu 4 --verify` started, temperature, policy clocks and cooling states
  sampled every five seconds; saved script `build/logs/h96max-m2-plus/scripts/cpu-thermal.sh`.
- Five-minute four-core CPU verify completed with exit 0; policy stayed at the highest factory OPP,
  all cooling states zero. Complete log: `build/logs/h96max-m2-plus/cpu-thermal-complete.log`. No
  new MMC or IOMMU fault observed.
- Live inventory reports HDMI disconnected, three ALSA cards, MPP/RGA/DRM/CEC nodes and input
  symlinks. Media userspace tools are not installed. Display connection requested while the
  remaining unattended system checks continue.
- Warm-cycle preflight initially stopped before any reboot: `ping` missing. Installed `iputils-ping`
  as a test utility. A second preflight rejected `IOMMU binding ... default mapping` because its
  fault regex matched `default`; narrowed the regex before proceeding. Neither failure indicates a
  board fault.

## 2026-11-05 — Session restart and intermittent Wi-Fi probes

- Server restart interrupted the host runner after four recorded warm boots. Current boot ID matches
  the fourth log; no runner remained. Closed one orphaned SSH client by its exact PID.
- Resume preflight failed Wi-Fi-bound gateway pings: one probe, then all three probes in a separate
  diagnostic. Ethernet passed; Wi-Fi stayed associated; no disconnect in the network journal.
- A later ICMP packet trace received all three replies through `wlan0`, without reassociation or
  configuration changes. Reverse-path filtering is zero on both interfaces. Cause unverified.
- Evidence: `build/logs/h96max-m2-plus/network-ping-failure.log` and
  `build/logs/h96max-m2-plus/network-icmp-trace.log`.
- Kept the failure; changed subsequent health probes from one packet to three. No driver, firmware,
  tree, routing or sysctl change made.
- Dual-interface capture explains the failed probes: ICMP requests left `wlan0`, while replies to
  its IPv4 address arrived on `eth0`. The interface-bound ping discarded them.
- Temporary `arp_ignore=1`, `arp_announce=2` and a Wi-Fi neighbour refresh passed two rounds on both
  interfaces; original sysctls restored on exit. Warm-cycle checks use the same temporary isolation.
  Evidence: `build/logs/h96max-m2-plus/network-dual-interface-trace.log` and
  `build/logs/h96max-m2-plus/network-arp-isolation.log`. No production network policy changed.
- Owner supplied the product and store URLs; updated `BOARD_HOME`, `BOARD_STORE` and board identity
  links. Earlier listing screenshots remain factory evidence.
- `./build.sh board h96max-m2-plus` rebuilt successfully after the URL update; board configuration
  passes `bash -n`.
- Existing host FFmpeg CLI checked: 9.0.2, but built without Rockchip MPP. Not copied or used for
  codec claims; Rockchip-capable CLI still required. No Debian FFmpeg installed; nothing built on
  the box.
- Warm-cycle runner recorded successful boots through cycle nine. Before the tenth, Wi-Fi-bound
  gateway pings again lost all replies despite temporary ARP isolation; Ethernet passed. No tenth
  reboot triggered. Logs: `build/logs/h96max-m2-plus/warm-boot-01.log` through
  `build/logs/h96max-m2-plus/warm-boot-09.log`.
- Stopped the reset loop under the procedure's repeated-failure rule. The earlier trace proves one
  reply-path failure; the latest failure was not captured and is not assigned to the radio.
- Storage stress, protected-range runtime hashes and quiet network medians were prepared but not
  run. Full system validation, the next kernel and physical checks remain open.
- Final readback: same ninth boot, kernel `6.1.172-tvb-rk35xx`, both interfaces addressed, no failed
  services, original ARP sysctls both zero. HDMI remains disconnected. Evidence:
  `build/logs/h96max-m2-plus/session-final-state.log`.

## 2026-11-05 — Continued unattended validation

- Owner requested continuing through the full bring-up after the partial stop.
- Refreshing the router's legitimate Wi-Fi mapping with gratuitous ARP passed two rounds of Ethernet
  and Wi-Fi probes. Added the refresh to the temporary test isolation; tenth warm boot completed. No
  persistent network policy change. Evidence: `build/logs/h96max-m2-plus/network-gratuitous-arp.log`
  and `warm-boot-10.log`.
- Four prescribed fio modes, then CRC32C verification of a temporary file, completed with exit 0;
  temporary data removed. Log: `build/logs/h96max-m2-plus/storage.log`.
- Every live protected eMMC range matches the stock backup in size and SHA-256. Read device selected
  by its boot0 companion. Evidence: `build/logs/h96max-m2-plus/preserve-runtime.jsonl`.
- Added shared `validate-build` steps to `build.sh`: patched FFmpeg and the configured kernel's
  lockup module. Lockup module builds against 6.1.172; FFmpeg download initially reset, then
  configure exposed missing pkg-config in the build environment; explicit dependency added.
- Idle Ethernet and Wi-Fi medians completed with each socket bound to its interface, three runs each
  direction. World-domain scan succeeds; both global and self-managed PHY accept US and return
  to 00. Log: `build/logs/h96max-m2-plus/network-idle.log`.
- Patched FFmpeg 9.0.2 and MPP built successfully on the host; private binaries and libraries copied
  to `/var/tmp/tvb-validation`. No system media packages replaced.
- Single-CPU hard lockup reset the board and returned a new boot within the recovery limit; detailed
  record: `build/logs/h96max-m2-plus/hard-lockup-recovery.log`.
- Idle network results and storage measurements added to the board's measured table.
- Hard-lockup health readback confirms
  `Kernel panic - not syncing: Watchdog detected hard LOCKUP on cpu 0`, both networks and the fitted
  drivers returned. Log: `build/logs/h96max-m2-plus/hard-lockup-health.log`.
- Video runner now creates a private disk-backed directory under `/var/tmp` and cleans it on exit;
  its box-side temporary paths use the supplied directory. Shared tool build procedure documented.
- Soft-lockup readback confirms `Kernel panic - not syncing: softlockup: hung tasks`, archived after
  recovery. Evidence: `build/logs/h96max-m2-plus/soft-lockup-health.log`.
- Repository tests pass after the shared validation-tool additions; log:
  `build/logs/h96max-m2-plus/build-tests.log`.
- All-CPU interrupt-disabled hang test started with a three-minute host recovery cap. No kernel
  image or tree replacement involved.
- All-CPU interrupt-disabled hang returned a new boot within the host recovery cap; hardware
  watchdog recovered the box with no CPU available to run a lockup detector. Evidence:
  `build/logs/h96max-m2-plus/all-cpu-lockup-recovery.log` and `all-cpu-lockup-health.log`.

## 2026-11-06 — System lines, dmesg accounting, the USB 3 port

- Short watchdog test: requested 10 s, driver granted 11 s; the box went quiet, reset and returned a
  new boot 34 s after the trigger began, kernel uptime 17 s at readback. Not the 89 s maximum. Log:
  `build/logs/h96max-m2-plus/watchdog-short-recovery.log`.
- `dmesg`, `systemd-analyze` and package audit: `system-audit.log`, `dmesg-boot.log`. Boot lines
  diffed against the H96 Max 3518 and R69 on the same `6.1.172-tvb-rk35xx`; lines only this box
  prints: the USB 3 root port's `config error` (6.7 s, 9.1 s, 201 s) and the `gpu-bus` OPP chain.
- `gpu-bus` is `okay` in this factory tree, `disabled` in both sisters'. It fails on a missing
  `pvtm` regulator, so `vdd_logic` does not track the GPU clock. DMC OPPs floor `vdd_logic` at 850
  mV; `gpu-bus` asks 850 mV at 700 MHz and up to 875 mV at 800 MHz. Idle read: 900 mV. Scoped in
  Known gaps; no change made.
- USB: the archived listing image says USB 2.0; the H96 Max M2 product text says USB 3.0. The PCB's
  receptacle has nine leads: USB 3.0. A `NOT FITTED` comment copied from the 3518D was written, then
  reverted on the owner's correction; DTB unchanged throughout (`cmp` against the installed one).
  The 3518D's graft removing `usb3-phy` broke suspend; this tree stays as the factory wired it.
- Image audit: apt history shows only bring-up installs
  (`stress-ng fio ethtool iperf3 rfkill evtest`, `iputils-ping`, `htop`). Log: `image-audit.log`.

## 2026-11-06 — Video engine

- `video.py run --engine rkmpp` with the host-built FFmpeg 9.0.2 and MPP 1.1.0 in
  `/var/tmp/tvb-validation`. Results: `build/validate/video/h96max-m2-plus-6.1.172-tvb-rk35xx.json`,
  log `video-run.log`.
- VP9 came out `broken` with zero frames. FFmpeg's stderr shows MPP refusing at open:
  `unable to create dec vp9 for soc rk3528 unsupported` (`vp9-probe.log`). MPP 1.1.0's `mpp_soc.c`
  gives the RK3528 `vdpu382` (H.264, HEVC, AVS2) and the RK3528A, the RK3518 boxes' die, `vdpu381`
  (adds VP9). The refusal is right; `video.py`'s rkmpp fallback pattern knew only
  `unsupported by MPP`. Widened to the per-SoC message, and the scale case checks it too: VP9 re-run
  reads `refused` (`video-vp9-recheck.log`), merged into the run's JSON.
- 16384×8640 H.264 and HEVC: the HEVC parser rejects the stream (`invalid pps id 0`), no frame,
  FFmpeg exits with an error; the next decode passes (`oversize-probe.log`). The 16K encode resets
  `rkvenc` and recovers.
- Idle CMA 3.0 MiB of 512 MiB, console framebuffer up. RK3528 column added to
  `docs/video-support.md`.

## 2026-11-06 — Display, audio, CEC, DDC, GPU

- `display.py` on the attached BOE 2256x1504 monitor: 10 passed, 9 failed. Its EDID lists HDR, so it
  was used as is; the output went YCbCr 4:4:4 and the writeback refused it
  (`YUV2RGB is not supported by writeback`), failing `sdr2hdr`, `scope` and `sinks`; HLG was not
  sent, the monitor listing PQ only (`Not support EOTF 3`). Log: `display-run.log`.
- With `off` written to the connector's `status`: synthetic screens, RGB output, 19 passed, 0
  failed; `detect` restored, monitor back at its native mode. Log: `display-headless.log`.
- Three sound cards, each 3 s of silence at 44.1 and 48 kHz in 3.03–3.16 s; CEC physical address
  1.0.0.0 (`display-io.log`). glmark2 43 at 1080p, GPU devfreq at 800 MHz (`glmark2.log`).
- DDC/CI: the owner's monitor has it. `i2cdetect -r` on the dw-hdmi bus answers every address but
  0x37; `ddcutil` write-read fails `EOPNOTSUPP` (`ddc-probe.log`). Scoped in `docs/todo/rk35xx.md`.
- Installed for testing: `alsa-utils`, `v4l-utils`, `ddcutil`, `glmark2-es2-drm`.

## 2026-11-06 — Network bands, load, addresses

- 2.4 GHz: the connection pinned to `bg` for the run, then restored: channel 6, 40 MHz HE-MCS 9,
  medians 131.4 up / 168.1 down Mbit/s (`wifi-24.log`).
- Under `stress-ng --cpu 4 --hdd 1`: Ethernet 93.2 / 94.0, 5 GHz 208.5 / 215.1 Mbit/s, the idle
  numbers; no RX or TX error; 71.4 °C (`network-load.log`).
- Wi-Fi address: the driver takes the module parameter, then `chip.mac`, then a random tail under
  `FE:FD:FC`. A patch deriving that tail from the SoC id was built and loaded: the address stayed
  `fe:fd:fc:53:fe:66`, as it did over a plain reload with the RNG long seeded. The address is the
  chip's, not random; the patch was dropped and the original module restored (`mac-0008.log`).
- IOMMU interrupts unchanged over 30 s idle (`iommu-idle.log`).

## 2026-11-06 — Input names, the RTC

- `base/input-names.rules` had two rules for `input/cec-remote`: Rockchip's on `hdmi_cec_key`,
  Allwinner's on `dw_hdmi`. Rockchip's 6.1 kernel registers both, so they raced; `dw_hdmi` won and
  `hdmi_cec_key` had no link. Rockchip's `dw-hdmi-cec.c` reports only `KEY_POWER` on `hdmi_cec_key`,
  on a CEC wake; a TV remote's keys come through the CEC adapter's `rc0`, `dw_hdmi`, on both
  families. `cec-remote` is now `dw_hdmi` for every family, `hdmi_cec_key` is `cec-powerkey`.
  Rebuilt `tvb-base` installed: all five event nodes linked (`input-audit.log`).
- No `/dev/rtc*`: suspend waits for the remote as a wake source.

## 2026-11-06 — `rk35xx-next`, 6.12.69: the SDIO card after a warm reboot

- 6.12.69 installed beside 6.1 (`install-next.log`): menu `l0` 6.12, `l1` 6.1. First boot clean:
  both networks, the Seekwave and Lima modules, no failed unit.
- Warm reboots: on the third boot `wlan0` was missing,
  `mmc1: Failed to initialize a non-removable card` after 400, 300, 200 and 187.5 kHz. Unbind and
  bind of `ffc20000.mmc`: the card at SDR104, `wlan0` associated (`wifi-missing-next.log`).
  `clk_32k` enabled: not the sleep clock.
- Counted with a check that waits for the host's verdict and finds the host by its controller
  (`sdio-cycles-next-*.log`): factory 200 ms 11 of 20 boots without the card, 1000 ms 3 of 16;
  toggled 200, 1000, 200, 1000. The delay is a lever, not the cause: factory tree restored, the
  numbers in `docs/todo/rk35xx-sd-uhs-warm-reset.md`.

## 2026-11-06 — `rk35xx-next`, 6.12.69: the pass

- `next-pass.sh` ran every unattended check on 6.12 (logs `*-next*`). Same as 6.1: RAM verify,
  storage within noise (random read 5760 against 6619 IOPS), every preserved eMMC range's hash,
  Ethernet, 5 GHz, under load, the decode and encode matrix within 4% (`video.py compare`: only HEVC
  encode past 7680×4320, erratic on both), audio, CEC, input links. glmark2 50 against 43. Boot
  11.0–11.5 s against 10.3 s, the kernel's 5.7 s against 3.9 s.
- `display.py` failed 8 on 6.12, then rated 720p60. Two tool faults, not the board: 6.12 re-reads an
  `edid_override` only across a status change (`edid-override-next.log`), and its console does not
  follow a new screen, leaving the CRTC at a mode the screen no longer lists. `display.py` now goes
  through `off` before an override and before the restore, and sets the preferred mode when the
  CRTC's is not offered: 19 passed on 6.12 (`display-headless-next3.log`).
- Hard lockup: on 6.12 a single CPU with interrupts off was caught by the soft-lockup detector;
  `nmi_watchdog` 0, the detector built on perf's NMI, which the RK3528's GICv2 lacks. 6.1 uses the
  other-CPU detector. `CONFIG_HARDLOCKUP_DETECTOR_PREFER_BUDDY=y` in `kernel/rk35xx-next.fragment`:
  `nmi_watchdog` 1, `Watchdog detected hard LOCKUP on cpu 3`, its NMI backtrace unanswered, the
  soft-lockup panic 8 s later, the box back in 74 s (`hard-lockup-next-*`).
- `dmc` stays in deferred probe on 6.12: the DDR at 786 MHz, no scaling.
- `wlan0` was missing after three of the five resets: the SDIO first init, as on warm reboots.

## 2026-11-06 — Back on 6.1; 10 Mbit/s; the rating's noise

- 6.12: `CONFIG_AUTOFS_FS=y` in `kernel/rk35xx-next.fragment`: systemd had logged
  `Failed to find module 'autofs4'` and left `binfmt_misc` unmounted; now an autofs mount, no failed
  unit.
- `U_BOOT_DEFAULT="l1"` in `/etc/default/u-boot`: the box boots 6.1, 6.12 kept as `l0`.
- `display.py` on 6.1 after both fixes: 19 passed, but 1080p120 not sustained over one
  `usb usb4-port1: config error` line in its window, no late flip, no underrun. The rating now
  leaves out lines from USB ports, the radios and MMC hosts (`OFF_PATH_NOISE`): 19 passed, 4K60 and
  1080p120 (`display-headless-6.1-final.log`).
- 10 Mbit/s forced with autonegotiation off: 7.72 up, 1.57 down, the switch at half duplex by
  parallel detection. Advertising 10BASE-T full alone: 9.29 / 9.30 (`eth-10-autoneg.log`).

## 2026-11-06 — The 30-minute combined soak, and the thermal zone

- 6.1, `soak.sh`: `stress-ng` 2 CPU and 1 GiB VM with verify, glmark2 on screen, a looping 4K HEVC
  decode, `iperf3` over 5 GHz, `fio` random 64 KiB with CRC32C verify, at once (`soak-6.1.log`).
  Stress passed; `fio` 24.9 GiB each way, `err=0`; Wi-Fi 200 Mbit/s, no disconnect; no new MMC
  error. 95 °C at 5.7 min, 100–105 °C from 8 min on, peak 105.0 °C; the CPU held 2016 MHz.
- At 21 min, 06:43:03: `lima ... mmu page fault` on `ppmmu0` and `ppmmu1`, `pp task error`,
  `mmu resume`; glmark2 ran on.
- No throttle at 105 °C: the zone's `step_wise` binds the CPU and GPU cooling to trip 1, 110 °C;
  trip 0, 95 °C, has none (`thermal-config.log`). Every RK3528 factory tree here sets 95 / 110 / 120
  and `sustainable-power = 638`, the shape of `power_allocator`, which switches on at trip 0 and
  holds trip 1; our kernel defaults to `step_wise`. Either way the factory design runs to 110 °C.

## 2026-11-06 — GPU alone; two hours of Wi-Fi traffic

- glmark2 `--run-forever` alone, 25 min: peak 81.1 °C, no `lima` fault (`gpu-soak-6.1.log`). The
  soak's fault came only with the SoC past 100 °C under every load at once; once, not yet toggled.
- `iperf3 -b 50M` over 5 GHz for 2 h: no `CTRL-EVENT-DISCONNECTED` (`wifi-soak-6.1.log`). After it,
  about half the `iperf3` runs over `wlan0` hung at `Connecting to host plex`; Ethernet 6 of 6;
  `ping` over `wlan0` clean; `plex` has no IPv6 address; with ARP isolation and a gratuitous ARP,
  still 3 of 6; reassociation 4 of 6 hung, a driver reload 3 of 6 (`wifi-recheck*.log`,
  `wifi-latch.log`, `wifi-family.log`).
- Rebinding `ffc20000.mmc` with the Seekwave drivers loaded fails the chip's boot
  (`skw_check_cp_ready: CP-ready timeout`, `skw_boot_loader ... ret=-62`): rebind only a host whose
  card never came up. Rebooted: 8 of 8 Wi-Fi runs (`wifi-after-reboot.log`).

## 2026-11-06 — The SDIO cause, and the DDR scaler on 6.12

- `pwrseq_simple.c` is the same on both vendor kernels: reset held from its probe to the host's
  power-up, and on `power_off` for `power-off-delay-us`. Both kernels' `mmc_rescan_try_freq()` power
  the card off after each failed attempt, so each retry got about 1 ms of reset.
- A runtime check (unbind, a timed gap, bind) was abandoned: the Seekwave SDIO driver could not be
  unloaded (`modprobe -r` hung), each rebind leaked an `skw_sdio_rx_thread`; rebooted.
- `power-off-delay-us = <200000>` in `sdio-pwrseq`: 20 of 20 warm reboots on 6.12 with the card, 19
  at the second clock, 300 kHz, one at the first (`sdio-cycles-next-poweroff200.log`); without it 11
  of 20 failed.
- 6.12's `rockchip-dfi` has no RK3528 entry, so the DMC waited on its devfreq event forever. Ported
  as `patches/linux-rockchip/6.12/devfreq-event-rockchip-dfi-rk3528.patch`: `dmc` probes as on 6.1.
  It stays at 786 MHz with no transition, as on 6.1: the factory's `auto-freq-en = <0>`.
- DDR at idle, 6.12 with the DFI port, `max_freq` capped through sysfs: 48.1 °C averaged over 5 min
  at 786 MHz after 5 min settling, 46.3 °C over the next 5 min at 324 MHz (`ddr-idle-next.log`). The
  factory's `auto-freq-en = <0>` pins 786 MHz on both kernels.

## 2026-11-06 — The thermal governor, and throttling at 95 °C

- `power_allocator` cannot bind: `devfreq-ff700000.gpu is not a power actor`, Lima's devfreq having
  no power model; writing it to the zone's `policy` fails `EIO`. `step_wise` is the governor here.
- A second soak, `step_wise`: 105.5 °C peak, 102.6 °C mean over the last 20 min, CPU 2013 MHz on
  average; no Lima fault this time (`soak-6.1-power-allocator.log`, policy unchanged).
- `trip_point_1_temp` written 95000 for the run, the cooling bound there: peak 95.1 °C, mean 94.8
  °C, CPU 1676 MHz on average (low 1416), GPU 606 MHz, Wi-Fi 190 Mbit/s, `fio` 25.6 GiB verified,
  stress passed, no kernel warning. Restored to 110000 (`soak-6.1-trip95.log`).
- Rockchip's own `rk3528.dtsi` (`develop-6.1`) has the same zone: trips 95 / 110 / 120 °C,
  `sustainable-power = <638>`, both cooling maps on the 110 °C `target`. Up to 110 °C is the SoC's
  design; nothing failed at 103–105 °C. The trees keep the factory's trips.

## 2026-11-06 — DDR scaling: the factory's `<0>` stands

- 6.1, `auto-freq-en = <1>` in a test DTB: the DMC moved 29 times in an idle minute, mostly at 528
  MHz. The display suite passed 4K60 with no underrun, then the box went silent mid-rating; the next
  boot stopped about 13.6 s in, during systemd's start; the third stayed up. No panic, no lockup
  record: resets by the hardware watchdog alone (`display-ddr-auto.log`, console ramoops).
- Known-good `board.dtb` back, rebooted: DMC at 786 MHz, no transition. Load-based DDR scaling hangs
  this board; the factory's `<0>` is why. The 2 °C at idle is not available.
- Ethernet: `gmac0` runs RMII on the SoC's 100 Mbit/s PHY; `gmac1`, the RGMII MAC, is disabled in
  the factory tree and no external PHY is fitted. 100 Mbit/s is the board's, as its spec sheet says.

## 2026-11-06 — USB 3

- The box went dark when a stick went in: a wrong outlet, the box unpowered, not the stick.
- Lexar USB 3.2 (`21c4:0809`) in at power-on: `4-1` at 5000M on the SuperSpeed root port, no hub,
  `uas`. Under `stress-ng --cpu 4`: 1 GiB raw read 291 MiB/s, 1 GiB write 199 MiB/s with CRC32C read
  back at 254, random 4K 2982 IOPS; no error, the link at 5000M after (`usb-fio.log`).
- Hotplug: pulled, back 2.2 s later as SuperSpeed on `xhci-hcd`, `uas`, `sda1` and `sda2` read.
- USB 2 side: a Logitech receiver (`046d:c52b`) on `usb 1-1` at 12M, four HID inputs. No 480M device
  yet.
- USB 2 at 480M: PNY USB 2.0 stick (`154b:007a`) on `usb-storage`, under `stress-ng --cpu 4`: 256 MB
  read 19.5 MiB/s, 128 MB write 7.5 MiB/s with CRC32C read back at 23.6; no error, 480M after. The
  stick's own speeds.
- The recovery button, inside the AV jack: `adc-keys`, `KEY_VOLUMEUP` press and release, the factory
  code, as on the 3518 and R69; `input/recovery-button` points at it.
- Recovery button to `KEY_VENDOR`, the project's code for it (`docs/todo/README.md`), from the
  factory `KEY_VOLUMEUP`: the DTB differs by `linux,code` alone; a press gives code 360 on
  `input/recovery-button`.

## 2026-11-06 — The Bluetooth remote

- `tvb-pair-remote` failed once with `Device … not available`: it removed the remote it had just
  found, paired or not, then waited for it to advertise again. Second run paired but never saw a
  key: its test was `ServicesResolved: yes`, a line this BlueZ does not print for the remote, and
  `ls /dev/input/event*`, always true. Fixed in `base/pair-remote`: the remove only for a remote
  paired before; done once an input device's `uniq` is the remote's address. `tvb-base` rebuilt.
- Keys under `evtest /dev/input/bt-remote` showed nothing: every key of this handset arrives on the
  Consumer Control node, `bt-remote-consumer`, the raw HID reports consumer usages (`01 42 00`, Menu
  Up). 20 keys, each the canonical keymap's. The 3518D's `board.md` says keys on `bt-remote`;
  recheck there before `remote-keymap.md` changes.
- `event8`, "Bluetooth remote", declares no `EV_KEY` and reports nothing: no link, rightly.

## 2026-11-06 — The IR remote onto the canonical keymap

- `code_print` on `rockchip_pwm_remotectl`, Bluetooth blocked so the remote falls back to IR:
  usercode `0xfb04`, table `ir_key6`. Nine keys off the canonical map (cog `KEY_F13`, voice
  `KEY_F14`, mouse `KEY_TEXT`, OK `KEY_REPLY`, home `KEY_HOME`, the app keys `KEY_F6`–`F9`).
- Remapped in `board.patch`; two guesses wrong on the first build (cog and mouse, Netflix and Prime
  Video), settled by presses named by the owner: `4d` cog, `d0` mouse, `04` YouTube, `14` Netflix,
  `4c` Prime Video, `4b` Google Play, as the R69's labelled table has them under `0xfb05`. Final
  pass: every button the canonical key.
- The same remap in the 3518's `0xfb04` and the R69's `0xfb05` tables; unpressed there.
- Bluetooth: the Mouse button sends no key, the handset switching to pointer mode itself.

## 2026-11-06 — Suspend and wake

- `deep`, `HandlePowerKey=suspend`. BLE: power key, `PM: suspend entry (deep)`, a press about 8 s on
  woke it, same `boot_id`; logind logged the waking press and did not act on it. With Bluetooth
  blocked, IR only: the same. `suspend_stats` 2 success, 0 fail.
- Resume logs `skw_sdio_suspend_adma_cmd: timeout`, `SKW_CMD_RESUME expect len: 149, recv len: 0`
  and `xHC error in resume ... Reinit`. Ethernet, Wi-Fi association, Bluetooth and USB all back;
  Wi-Fi 3.9 Mbit/s at once, 43.8 a minute later, 217 after the second resume.
- A sleep past the watchdog's 89 s left to the sisters' result, the owner's call: same SoC, watchdog
  and remote.
- A third sleep, 153 s in `deep` (15:55:18 to 15:57:51), past the watchdog's 89 s maximum: woken by
  the remote, same `boot_id`, `suspend_stats` 3 success, 0 fail.
- LEDs, the owner watching: running blue (`power`), asleep red (`standby`), blue again on wake; red
  then green while booting, before the kernel sets them.
- Off and on: a 5 s hold over BLE, logind `Power key pressed long`, `Powering off`, the LED red; a
  short press about 30 s later booted a new `boot_id`.
- `base/input-names.rules`: `bt-remote` now the Consumer Control node, where this handset sends
  every key; the keyboard interface is `bt-remote-keyboard`. The 3518D's 2026-09-07 note had keys on
  the keyboard node; same handset model, so the swap stands for every box unless a unit shows
  otherwise. `tvb-base` rebuilt and installed, links read back.
- Pointer mode over BLE: the d-pad as accelerating `REL_X`/`REL_Y`, OK as `BTN_LEFT` (`90001`), on
  the Mouse node, `bt-remote-mouse`, the only one declaring them.
- `tvb-pair-remote` with both fixes: the owner paired the remote with it, keys arriving; the run
  completes.

## 2026-11-06 — `s2idle`

- `s2idle` set for one sleep: the power key slept it; neither the remote's power key nor anything
  else woke it, and the watchdog, past its 89 s, did not reset it: its driver stops it on suspend.
  The owner power-cycled it; `deep` is the default again. `deep` covers the box; the `s2idle` check
  now asks for `s2idle` only where `deep` is missing.
- Why `s2idle` does not wake: with `remote_support_psci = <1>` the driver hands the IR interrupt and
  the power key to ATF (`sip_smc_remotectl_config`), which listens only in PSCI suspend and after
  power-off; `s2idle` never enters it. Psci off would likely give `s2idle` IR wake but lose wake
  from off. Parked: `deep` covers sleep.
- Fuseamp, deployed by its session, with our patched FFmpeg: the owner played 4K HEVC 10-bit
  smoothly on the 2256x1504 monitor, audio heard over HDMI. `rkvdec` took 2037 interrupts; playback
  had ended before the CPU was read.
- The boot on HDMI: the screen starts with the kernel, the owner watching;
  `generic-rk3528_defconfig` has no display driver, so U-Boot shows nothing.
- Seven more sleeps and wakes by the owner on one boot: `suspend_stats` 7 success, 0 fail; Ethernet,
  Wi-Fi at 206 Mbit/s and the remote back after. Ten of ten in all.
- Draw, the owner metering: 1.3 W idle after boot, 0.7 W in `deep`.

## 2026-11-06 — The codecs with no FFmpeg path

MPP 1.1.0's `osal/mpp_soc.c`, the `rk3528` entry, against `patches/ffmpeg/`; not implemented.

| Codec | MPP on the RK3528                  | FFmpeg                                  |
| ----- | ---------------------------------- | --------------------------------------- |
| AVS   | `vdpu2`, `HAVE_AVS`                | `cavs`, `cavsvideo` demuxer; no `rkmpp` |
| AVS+  | `avspd`, `MPP_VIDEO_CodingAVSPLUS` | `cavs` too; no `rkmpp`                  |
| AVS2  | `vdpu382`: AVC, HEVC, AVS2         | `avs2`, raw demuxer; no `rkmpp`         |
| VC-1  | none, on any SoC                   | —                                       |
| MVC   | `h264d` decodes both views         | no second-view output                   |

- AVS, AVS+ and AVS2 are reachable by one patch of ours beside `0034`: `cavs_rkmpp` and
  `avs2_rkmpp`. One FFmpeg ID covers AVS and AVS+; the sequence header's profile picks MPP's coding,
  `0x20` AVS, `0x48` AVS+. Synthetic streams: `libxavs`, `libxavs2`; whether `libxavs` writes AVS+
  is unchecked.
- VC-1: the listing's claim has no decoder behind it in MPP.
- MVC: the base view plays as H.264; the second is lost.
- No published `rkmpp` AVS patch found.
- The 3518D's `board.md`: FFmpeg's FATE `cavs.mpg`, as an elementary stream, made MPP spin under
  both `vdpu2` codings, no frame.

## 2026-11-06 — DDC/CI over `i2c-gpio`

- `ddcutil detect` saw no display: the connector stood forced `off` from a `display.py` stand-in
  run; `echo detect` to its `status` brought the BOE monitor back, EDID 256 bytes. Over dw-hdmi's
  bus 0x37 still failed `EOPNOTSUPP`.
- Graft, as the M20's: `hdmi_pins` keeps the CEC pin, `gpio0 RK_PA4` SCL and `RK_PA5` SDA as GPIO,
  an `i2c-gpio` node, `ddc-i2c-bus` on the HDMI node. DTB `ef3fa760`, the old kept as
  `board.dtb.preddc`.
- After the reboot: `i2c-hdmi-ddc` on `/dev/i2c-8`, EDID 256 bytes, `ddcutil detect` Display 1, MCCS
  2.2; brightness 100, set 80 and read 80, set back 100.
- `i2c-gpio` is a module: HDMI binds at 7.6 s, 6.3 s before; left so.
- The same graft built into the H96 Max 3518, the 3518D and the R69 trees. Installed on the 3518D
  (`7ac1ea3d`) and the R69 (`88aa00b6`, with its canonical IR table): `i2c-hdmi-ddc` probes, HDMI
  binds after it near 8.5 s, no screen attached to either; the 3518D logged no `ddc read failed`.
  The 3518 the same (`54681668`), renamed from `h96max-h313` to its `BOARD_HOSTNAME`.

## 2026-11-06 — AFBC to the plane

- A player's check counting the pictures committed to the plane with a non-zero modifier, through
  `hevc_rkmpp`, synthetic 3840×2160 HEVC and AAC from `libx265`, onto the 2256×1504 monitor, 8 s
  each: Main 181 of 181, Main10 233 of 233. Dropped 0, late 0, commits refused 0; the VOP2 log
  clean.

## 2026-11-06 — CMA, 16 MiB

- The allocator's count, `/sys/kernel/debug/cma/reserved/used`, sampled every 20 ms. On `cma=512M`:
  idle 772 pages, 3.0 MiB; `display.py` 19 passed, its synthetic screens and rating ladder, while
  `hevc_rkmpp` decoded 8K HEVC 8- and 10-bit frames uncompressed, a seek, and a 1080p, 8K, 1080p
  stream, 13 rounds, Wi-Fi at 195 Mbit/s: peak 772 pages. Every engine is behind an IOMMU.
- `cma=16M`: pool 4096 pages, idle 772; the same load bar the seek, the stream and Wi-Fi: peak 772,
  `display.py` 19 passed. `BOARD_CMA=16M` on every RK3528 board.
- Under the rating's large modes a few 8K decodes failed, on 512M as on 16M; alone they pass. The
  1080p, 8K, 1080p stream failed every round: `Internal bug, should not have happened` from
  `hevc_rkmpp`.

## 2026-11-06 — `hevc_rkmpp` across a resolution change

- `ffmpeg` called it an internal bug: `avcodec_send_packet()` gave EAGAIN. With MPP's input full, a
  refused packet stayed in `in_pkt`; written later, the decoder returned EAGAIN with the caller's
  next packet still held, which libavcodec takes as consumed. A first fix, waiting for a frame while
  the queue was full, missed it.
- `patches/ffmpeg/0038`: `receive_frame` takes packets until libavcodec has none or MPP is full,
  then waits for a frame while full.
- 1080p, 8K, 1080p HEVC: 210 frames of 210, both changes, no error, three runs. 1080p alone 13.3x,
  8K 0.826x, as before. Under `display.py` 19 passed with 8K 8- and 10-bit, a seek and that stream
  in 10 rounds: no decode failed, against about 1 in 10 before: the same EAGAIN, MPP slower under
  the display's load.

## 2026-11-07 — Serial

- The owner found the console: three plated holes near the SoC heatsink's corner, beside the LED, TX
  · GND · RX, RX the square pad, 3.3 V. At 1500000 8N1, hooks resting in the holes gave noise
  between clean lines, and the adapter dropped off USB every few seconds; held firm, a clean log
  from U-Boot's menu to the `ttyFIQ0` login, the command line the board's then the distro's
  (`build/logs/h96max-m2-plus/2026-11-07-serial-boot.log`).
