# H96 Max H313 worklog

## 2026-11-08 — first contact

- Owner supplied the manufacturer listing URL and specification text; browser fetch failed.
- Owner reports 2 GB RAM, 16 GB eMMC, SD, two USB-A ports, AV, HDMI, Ethernet, 5 V / 2 A, a bicolor
  LED and an IR receiver. USB-A nearest SD understood as the connected OTG port.
- Owner reports serial marked on the PCB; labels, pinout and voltage not yet supplied.
- Host `build/bin/sunxi-fel version`, outside sandbox:

  ```text
  AWUSBFEX soc=00001823(H616) 00000001 ver=0001 44 08 scratchpad=00027e00 00000000 00000000
  ```

- Confirms Allwinner H616/H313 family; does not distinguish exact SoC or PCB.
- Host `adb devices -l`, outside sandbox: empty device list while box was in FEL.
- No payload uploaded and no eMMC writes. Existing loader needs this board's factory boot0.
- Stock Android boot requested to check ADB; completion not reported.
- `board.md` created at owner's request. Documentation key provisional; no board package created.
- Initial contact notes: `build/logs/new-board/contact.txt`.

## 2026-11-08 — USB check after reconnect

- Host queries outside sandbox: `sunxi-fel version` reports no FEL device; `adb devices -l` empty.
- `ioreg -p IOUSB -w 0`: host controllers only, no USB device enumerated.
- `/dev/cu.*`: Bluetooth and debug-console only; no USB serial adapter.
- Cannot determine whether stock Android or U-Boot is running without serial or another visible
  interface.

## 2026-11-08 — OTG-only candidate DRAM initialization

- Owner authorized guessed DRAM settings and specified OTG-only bring-up.
- FEL present again before trial.
- Candidate: existing `boards/tanix-tx1-v2/fel_loader.bin`, LPDDR3 at 600 MHz, built from that
  boards factory settings; not this units factory data.
- `build/bin/sunxi-fel spl boards/tanix-tx1-v2/fel_loader.bin` returned 0; main U-Boot not executed.
- Subsequent FEL version query responded.
- Saved 4096 bytes at RAM address `0x48000000`, wrote a deterministic pattern, read it back and
  restored original bytes.
- Both pattern and readback exactly 4096 bytes, byte-identical; SHA-256
  `67556a1ca3c142f9c4e2eb172a0f660bdb500c48e2b91336875b56e0187fb411`.
- Artifacts: `build/logs/new-board/dram-{original,pattern,readback}.bin`.
- Small RAM window works with candidate settings; full capacity and stability remain untested. No
  eMMC access or writes.

## 2026-11-08 — factory boot0 read pending

- Owner requested reading disk start using the candidate RAM initialization.
- Factory boot0 expected at sector 16, 128 sectors; first MiB capture planned.
- Existing FEL loader exports a writable USB disk; its command help has no read-only option.
- Automatic approval review rejected starting it because host automount could modify eMMC. U-Boot
  launch did not execute.
- `diskutil list external physical` showed no external disk before the attempted launch.
- No retained read-only UMS patch found in local git history. Build runtime available, no active
  build using work volume shown.

## 2026-11-08 — factory boot0 captured over OTG

- Owner explicitly approved writable USB export with immediate unmount and prefix reads.
- `sunxi-fel uboot boards/tanix-tx1-v2/fel_loader.bin` completed; USB gadget `1f3a:1010` appeared.
- `diskutil info /dev/disk15`: UMS disk 0, USB, 15758000128 bytes, 30777344 sectors. Disk unmounted
  successfully before reads; host automount modifications were not checked.
- Two `/bin/dd` reads, each `bs=1048576 count=1`, exactly 1048576 bytes and byte-identical.
  Administrator authentication through macOS dialog.
- Prefix SHA-256: `553249c3398e2933f095bbe6299d6d04feab56a51da1fab2ec773eb8204706cb`.
- Sector 16: `eGON.BT0`, length 65536, header checksum verified. Saved as
  `boards/h96max-h313/factory_boot0.bin`.
- boot0 SHA-256: `804a420ff65e24f9e049a9b7d60f8aef2ce80f5cfd2dbba85ba9b638edca8d78`.
- Factory DRAM parameters: LPDDR3, 600 MHz, para2 `0x08001000` (2048 MiB). Capacity not
  independently stress-tested.
- Versus candidate, parameter indices 5, 7, 26–30 differ: ODT_EN, size, TPR6, TPR10–14.
- Raw DRAM words and prefix copies remain in `build/logs/new-board/`; full eMMC backup pending. No
  host raw writes issued.

## 2026-11-08 — factory-settings loader and firmware extraction

- Added minimal `board.conf` for the FEL loader; PCB identity and final board ID remain pending.
- `./build.sh loader h96max-h313`: U-Boot v2026.10, TF-A v2.14, LPDDR3 600 MHz; 848769 bytes. Log:
  `build/logs/new-board/loader-build.log`. Hardware trial pending.
- Full disk read started from the unmounted candidate U-Boot export, piped through `xz -T2 -1` into
  `backup/h96max-h313-stock.img.xz`; completion and verification pending.
- Decompressed first 40 MiB while backup runs; `sunxi-package` at sectors 24576 and 32800.
- Matching 124389-byte FDTs at disk offsets 13725696 and 17936384. Saved
  `boards/h96max-h313/factory_board.dtb`; SHA-256
  `7288e0ed6f6ae677f610a4f98af0ea6e86b8cea5c4010f2c8a4efbf120c2e13f`.
- `dtcx.py -n kernel-h616-vendor-4.9` produced `factory_board.dts`; round-trip check passed.
- Tree configures AXP1530, EMAC1 RMII and AC200 on TWI3/PWM5. Wi-Fi SDIO1 reset PG18; Bluetooth
  reset PG19. Chip identity still unknown.
- LED policy in tree: PH6 power, PH7 standby; colors and polarity require checking.

## 2026-11-08 — radio marking

- Owner reports AIC8800 marked on PCB; full suffix not supplied.
- Existing `modules/aic8800.conf` selects rk35xx kernels only. Driver has an Allwinner compatibility
  patch; sunxi64 build and hardware validation pending.
- Existing firmware package holds D80 variants; fitted revision must be identified before choosing
  firmware.

## 2026-11-08 — PCB photos and kernel builds

- Owner supplied `image1.jpeg`–`image3.jpeg`, `pcb-top.jpeg`, `pcb-bottom.jpeg`, `pcb-wifi.jpeg`.
- Top silkscreen: `BA979_627_V1.0 24353`; date code not interpreted as a calendar date.
- Radio marking and bottom sticker: AIC8800D40L. Serial holes beside AV: RX, TX, GND from top to
  bottom in bottom photo; voltage unmeasured.
- SoC and memory markings under heatsink; no identification from those markings yet.
- `pcb-bottom.jpeg` includes unit address/serial stickers; redact before staging the photo.
- Provisional ID collision found: `boards/h96max-3518/board.conf` retires the old `h96max-h313`
  package. Proposed `h96max-h313-ba979`; confirmation pending.
- AIC8800 selected for `sunxi64` and `sunxi64-next` in its module config.
- Kernel builds pass on 6.18.62 and 7.3.3, including AIC8800 modules; logs
  `build/logs/new-board/kernel{,-next}-build.log`. No hardware validation yet.
- Candidate mainline tree compiles through `./build.sh board-dtb h96max-h313`. Based on the existing
  H616 conversion, checked against this unit's factory differences in
  `build/logs/new-board/factory-differences.json`.
- Candidate enables SD with PF6 detect, separates Wi-Fi PG18 from Bluetooth PG19, sets power LED
  active-low, removes sibling eMMC sample delay and remote map, and adds EMAC1/AC200 wiring. No boot
  test yet.

- Owner confirmed PCB name exactly `BA979_627_V1.0`; `BOARD_PCB` already matches. Printed `24353`
  remains separate, not `BOARD_DATE`.

- First super extraction attempted before the streamed backup contained the whole partition:
  1789633142 of 2147483648 bytes. Repeated after more data arrived; full super extracted and LP
  metadata header/table SHA-256 checks pass.
- Extracted system, vendor and product logical partitions under `backup/h96max-h313-extracted/`; no
  per-unit data copied into the public tree.
- Boot partition banner: Linux 4.9.170, build 424, 2026-06-22; Android boot header v2. System/vendor
  properties report release 14 and SDK 29.
- PCB-name search found the same silkscreen in the H96 Max H313 discussion:
  https://4pda.to/forum/index.php?showtopic=1098233&st=180 . Runtime claims from other units are not
  used as this unit's evidence.

## 2026-11-08 — firmware available before full backup completes

- Read AIC firmware directly from extracted vendor filesystem while disk backup continues.
- Saved both `aic8800d80/` and `aic8800dc/` sets and stock AIC modules under
  `backup/h96max-h313-extracted/`.
- D80 set has seven files. `fw_adid_8800d80_u02.bin` matches the shipped file; the other six differ.
  Hashes and sizes: `backup/h96max-h313-extracted/firmware-comparison.tsv`.
- Stock userconfig differs in line endings and disabled loss/offset settings; no firmware
  replacement chosen before hardware validation.
- Stock BSP module names the D80 firmware paths and `aicbsp_8800d80_fw_init`; this alone does not
  prove which path runs on the fitted D40L.
- Built driver has D40/D80 compatibility code and D40N/LN/WN SDIO IDs. This unit's SDIO ID and
  revision remain unread.
- Normal U-Boot also builds against the candidate board tree: 810817 bytes,
  `build/out/uboot/h96max-h313/u-boot.bin`; log `build/logs/new-board/uboot-build.log`.

## 2026-11-08 — full factory backup verified

- `backup/h96max-h313-stock.img.xz` complete; disk read returned 0 and exactly 15758000128 bytes,
  matching exported media size.
- Full xz decompression passes integrity checks and returns exactly 15758000128 bytes.
- Raw SHA-256: `9faf1761f0a2e5d21168e378a231cab22e792f276d057f063e5bf5b40d5715fe`.
- Initial MiB and boot0 match the earlier independently captured prefix.
- Verification: `build/logs/new-board/backup-verification.txt`; six window hashes retained privately
  in `backup/h96max-h313-stock-verification.json` for the next loader's readback.
- Export ejected after verification. Next hardware step: re-enter FEL, test the factory-settings
  loader and read back the recorded windows.

## 2026-11-08 — OTG-only diagnostic payload prepared

- Previous turn made progress: full backup verified and export ejected.
- FEL recheck reports no device; no user readiness confirmation yet. Hardware loader trial remains
  pending.
- Added `validate-build ramboot` to build a diagnostic initramfs through the standard build
  container.
- Build for 7.3.3 succeeds; archive includes matching kernel/modules, firmware, BusyBox, kmod,
  stress-ng and network tools.
- Offline dependency check found `/lib` missing after extracted packages; fixed merged-/usr links,
  then verified kmod resolves the sunxi USB controller dependency chain and stress-ng runs in the
  extracted root.
- Build log: `build/logs/new-board/ramboot-build.log`; outputs
  `build/out/validate/7.3.3-tvb-sunxi64/{Image,ramboot.cpio.gz}`. Hardware boot not tested.
- Prepared `build/logs/new-board/ramboot.env` and `ramboot-loader.bin`: factory-settings SPL with
  uEnv address/length seeded before execution and checksum recomputed. This avoids depending on
  post-SPL header updates reaching U-Boot; the path remains an untested candidate.
- Payload selects USB0 peripheral mode only in the RAM copy of the kernel tree, disables its
  competing host controllers, and starts the diagnostic initramfs. No storage write commands or disk
  mounts.

## 2026-11-08 — waiting for a fresh FEL entry

- Previous goal turn made progress: diagnostic initramfs and boot payload prepared and checked
  offline.
- Third consecutive goal turn requiring FEL re-entry: `sunxi-fel version` still reports no device.
- USB tree shows host controllers only; no USB serial adapter is present.
- No live build or backup remains to wait on. Hardware tests require reconnecting USB with recovery
  held, DC unplugged, and readiness confirmation.
- Goal blocked on that physical action. Factory-settings loader, Linux RAM boot, RAM stress and
  component validation remain untested.

## 2026-11-08 — SD image requested

- Owner re-entered FEL. `sunxi-fel version` responded; this unit's factory-settings SPL ran and a
  4096-byte RAM pattern matched on readback.
- Tried uploading a 32 MiB Image, candidate DTB, 147868932-byte diagnostic initramfs and uEnv data.
  Host cap killed the upload after 180 seconds; log `build/logs/new-board/ramboot-upload.log`.
- Subsequent FEL version query returned USB overflow. No kernel boot was observed; no eMMC write
  command issued.
- Owner directed SD-first kernel bring-up whenever SD is available, and requested the SD image.
  Cancelled the RAM-boot route; no upload process remains live.
- Qualified candidate package/directory as `h96max-h313-ba979` to avoid the legacy RK3518 transition
  package. Model remains H96 Max H313; PCB is `BA979_627_V1.0`.
- First SD candidate selects 7.3.3 (`sunxi64-next`), whose carried patches include EMAC1 and
  AC200/PWM support. 6.18 Ethernet path remains pending.
- Regenerated DTB with qualified compatible and model `H96 Max H313 (BA979_627_V1.0)`; added the
  board package list using common scripts.

## 2026-11-08 — SD candidate built and checked

- Built board package and `tvb-base`; image step completed through
  `./build.sh image h96max-h313-ba979`.
- Image: `build/out/images/tvbian-h96max-h313-ba979-trixie-2026-11-08.img.xz`, 970 MiB raw; root
  starts at sector 32768.
- Raw image SHA-256: `5f5cc99654f5541762de73f27d6f1a41e1f3be0645d90e58c50cc8fe5faa26dc`.
- Image checks pass: MBR/root range, packaged bootloader, kernel Image, DTB, board ID, PCB name,
  root UUID and read-only e2fsck.
- Extlinux selects 7.3.3, the packaged board DTB and root by UUID; no eMMC install performed.
- SD card is `/dev/disk14`, Built In SDXC Reader, protocol Secure Digital, 63864569856 bytes. It is
  classed internal by macOS, so `diskutil list external physical` missed it.
- Started guarded write with metadata/size checks and complete image readback; result pending.

- SD flash process is waiting on the macOS administrator-password dialog; no card write has started
  yet.

## 2026-11-08 — SD flashed; owner reports boot

- SD write and full readback passed: 1017118720 bytes on disk14; readback SHA-256
  `5f5cc99654f5541762de73f27d6f1a41e1f3be0645d90e58c50cc8fe5faa26dc`.
- Cleared stale backup GPT at the card end. Evidence:
  `build/logs/new-board/sd-flash-verification.json` and `sd-flash.log`.
- Owner reports the box appears booted. Initial SSH query for `h96max-h313.local` failed hostname
  resolution; runtime identity and root device not yet read.

## 2026-11-08 — first live validation over Wi-Fi

- Owner reports HDMI boot without visible errors, working USB keyboard, root password changed, SSH
  key added and Wi-Fi configured.
- SSH succeeds as `root@h96max-h313`; kernel 7.3.3, model `H96 Max H313 (BA979_627_V1.0)`.
- Root is the SD card: root block device reports type SD; separate 14.7 GiB MMC has boot0/boot1
  companions and remains unmounted. Evidence: `build/logs/new-board/ethernet-deferred.log`.
- Kernel maps 2048 MiB; systemd holds the watchdog at 80 seconds. Neither RAM stress nor watchdog
  reset has been tested.
- Current Ethernet probe is deferred: AC200 clock unavailable, then MDIO registration deferred; no
  eth0 registered. `CONFIG_PWM_SUN20I` and `CONFIG_MFD_AC200_EPHY_CTL` are disabled. Evidence:
  `ethernet-deferred.log`, `pwm-config.log`.
- Owner reports an earlier brief Ethernet connection and later loss; its initial cause is not
  established by the current boot's deferral.
- Building experimental modules on the host for a live dependency test before committing a
  kernel-config fix.
- AIC8800D40L enumerates as SDIO `c8a1:0082` / `c8a1:0182`, loads the shipped D80 firmware, and
  carries the working SSH link. Driver reports MAC source random; stable fallback remains to fix.

- Experimental build first stopped on 7.3 integer panic options; second stopped because NTFS3
  ACL/compression were requested while NTFS3 itself was off. Read Kconfig and compared all fragment
  values together; experimental overrides use hung-task panic 0, soft-lockup panic 1 and enable
  NTFS3 as a module. No running kernel change.

- Third experimental build failed because modular AC200 core and PHY shared a module name. Root
  cause of all three failures: the experimental FRAGMENT override omitted the existing
  `kernel/sunxi64-next.fragment`, which already handles the integer panic options, NTFS3 parent and
  built-in AC200 core.
- Stopped after three failed attempts. Corrected the experimental manifest to retain both existing
  fragments and add only PWM_SUN20I and MFD_AC200_EPHY_CTL. No fourth build started.

- Initial RAM check passes: stress-ng verified 1400 MiB for 60 seconds, exit 0, no failed workers.
  Readback log: `build/logs/new-board/ram-first-60s.log`. Longer RAM/thermal validation remains
  pending.
- Six independent Linux eMMC readback windows match the factory backup, including primary/secondary
  boot packages and the end of disk; log `build/logs/new-board/emmc-readback.log`. No eMMC data
  write.
- Installed packaged test tools on the SD root: ethtool, stress-ng, iperf3, fio and evtest; no
  package upgrades or kernel change.

## 2026-11-08 — steering and resume state

| Item               | Current state                                   | Evidence                                         |
| ------------------ | ----------------------------------------------- | ------------------------------------------------ |
| Access             | Wi-Fi SSH, `root@h96max-h313`                   | Live command capture                             |
| System             | 7.3.3, correct PCB model, SD root               | `first-wifi-system.log`, `ethernet-deferred.log` |
| HDMI, keyboard     | Owner verified login                            | Owner report; USB HID log                        |
| RAM                | Initial verified test passed                    | `ram-first-60s.log`                              |
| Ethernet now       | No eth0; clock/PHY probe deferred               | `ethernet-deferred.log`, `pwm-config.log`        |
| Earlier Ethernet   | Brief connection reported; cause unknown        | Owner report                                     |
| Wi-Fi MAC          | Driver reports random fallback                  | `first-wifi-system.log`                          |
| Factory data       | Full backup verified; six Linux readbacks match | `emmc-readback.log`                              |
| Experimental build | Stopped after three failures                    | `ethernet-module-build*.log`                     |

Log paths in this table are under `build/logs/new-board/`.

- Steering: use SD for kernel bring-up when the slot is available; FEL remains for identification,
  backup and recovery. The untested RAM-boot helper was removed.
- Build steering: the experimental FRAGMENT override omitted the existing next-kernel fragment. The
  corrected manifest retains `kernel/sunxi64.fragment`, `kernel/sunxi64-next.fragment` and the
  experimental fragment, which now adds only `CONFIG_PWM_SUN20I=m` and
  `CONFIG_MFD_AC200_EPHY_CTL=m`.
- Diagnostic steering: missing providers explain the current deferred probe, but do not establish
  why the owner could connect through Ethernet earlier. Prior-boot kernel and NetworkManager records
  still need examination; inherited bootloader clock state is not a proven explanation.
- No fourth build, live module load, reboot or eMMC install has been performed.
- Next: reconcile the earlier Ethernet connection, then resume the corrected build after the owner's
  go-ahead. Longer RAM validation, watchdog reset, Bluetooth, remote, LEDs, video/audio and the
  other kernel remain pending.
- Detailed corrections recorded in `steering.md`; current hardware claims remain in `board.md`.

## 2026-11-08 — Ethernet: AC300, not AC200

- Earlier Ethernet connection: unreconstructable. The previous boot's journal holds its first six
  seconds only; the journal lives in RAM until shutdown.
- `kernel/sunxi64.defconfig` names `PWM_SUNXI_ENHANCE`, `AC200_PHY_CTL` and `AC300_PHY`, which no
  carried patch defines. 7.3's patches define `PWM_SUN20I`, `MFD_AC200_EPHY_CTL` and
  `XPOWERS_ACX00_PHY`; none was enabled. 6.18 carries none of the EMAC1, EPHY or PWM patches.
- Added `PWM_SUN20I` and `MFD_AC200_EPHY_CTL` to `kernel/sunxi64-next.fragment`; build passed. Live
  `insmod` of both: `ac200-clock` resolved, then the AC200 core's first read at TWI3 0x10 timed out,
  `mv64xxx: I2C bus locked`.
- Trace (`pwm`, `i2c` events) across a rebind: PWM5 applied enabled, 21/42 ns, `err=0`; the two-byte
  read at 0x10 returned -110 after 2 s. Rails `aldo1` 1.8 V and `dldo1` 3.3 V always on.
- Factory tree agrees on TWI3 PA10/PA11, 0x10, PWM5 bypass; its `gmac1` names no EPHY. Stock kernel
  carries both `acx00_i2c_probe` and AC300 EPHY calibration code.
- SID `sunxi-sid0` bytes 0x2c–0x2d: `07 05`, word `0x0507`. Bit 8 set: AC300 package; calibration 7;
  low-calibration bit clear. No AC200 to answer on TWI3.
- Our U-Boot has no SID-based AC300 switch, which the carried H616 tree relies on. Tree now
  describes a fixed `x-powers,ac300-ephy-package` at MDIO address 0, clocked from PWM5, with the SID
  `ephy-config` cell; TWI3, AC200 and its EPHY control removed. EPHY and EMAC1 supplies moved from
  1.8 V `aldo1` to 3.3 V `dldo1`.
- Fragment now `PWM_SUN20I=m`, `XPOWERS_ACX00_PHY=m`; `MFD_AC200_EPHY_CTL` dropped.
- Tree audit against the factory tree: SD detect PF6 gains the factory's pull-up; stale comments
  copied from the Tanix TX1 corrected (remote count, keymap, PMIC rail sources). Port G voltage, CPU
  OPPs and Bluetooth stay pending in `dtb.md`.
- On the box: new `board.dtb` installed, the previous kept as `/usr/lib/tvb/board.dtb.known-good`;
  `pwm-sun20i.ko` and `xpowers-acx00.ko` copied into the running kernel's tree, `depmod`.
- First reboot: `EMAC reset timeout`, probe -110. The initramfs, built before the modules existed,
  lacked `xpowers-acx00`. `modprobe` and a rebind brought `eth0` up at 100 Mb/s full duplex.
- `update-initramfs -u`, reboot: PHY `X-Powers AC200/AC300 EPHY` attached at 12.4 s, link up at 14.5
  s, DHCP lease unchanged, nothing deferred.
- iperf3 over `eth0`, 10 s each way: host to box 94.0 Mb/s, box to host 91.5 Mb/s. Interface
  counters confirm the traffic on `eth0`, not `wlan0`; zero errors, drops or misses.
- Files: `kernel/sunxi64-next.fragment`, `boards/h96max-h313-ba979/board.{patch,dts,dtb}`,
  `docs/h96max-h313-ba979/{board,dtb}.md`, `docs/todo/allwinner.md`.

## 2026-11-08 — the H96 remote, and the ID `h96max-h313`

- Owner: the box ships the remote the other H96 Max models do. Stock's IR wake list holds NEC
  address `0xfb04` (power 0x08), the 3518's and M2 Plus's bundled remote.
- `0049`–`0050` add `rc-h96max`: the 3518's 22 `0xfb04` keys as NEC scancodes `0x04cc`, every one
  canonical; the M2 Plus's tree carries 12 more stock entries no button sends.
  `checkpatch.pl --strict` clean; both apply with `-F0` on 6.18.62 and 7.3.3. Tree:
  `linux,rc-map-name = "rc-h96max"`.
- On the box after a reboot: `Registered IR keymap rc-h96max`, `sunxi-ir` on `rc1`, NEC selected.
  Button presses pending.
- Owner chose the ID `h96max-h313`, which the 3518 carried until its rename. The live index holds
  RK3518 `tvb-h96max-h313` 1–3 and the transition `1:1`. `boards/`, `docs/` moved; compatible
  `h96max-h313,h313-tvbox`; `BOARD_EPOCH=2` so its versions sort above both; `plan.sh` versions a
  board in its epoch. The 3518 keeps `BOARD_RENAMED_FROM` for its `Replaces`/`Breaks`; no transition
  is built for a name a board now holds.
- `board-check` refusing `tvb-h96max-h313` on an rk35xx loader names `tvb-h96max-3518` and one
  command: `apt install tvb-h96max-3518 tvb-h96max-h313-`. Run on this box against a dummy rk35xx
  deb: refused, exit 1.
- A trixie container, stand-in debs with the live index's relations. Old `3`: `apt upgrade` takes
  `2:1` (no hook there; on an rk35xx eMMC the hook refuses it); the swap removes it and installs the
  3518 with no overwrite. 3518 with the transition `1:1`: `apt upgrade` holds `2:1` back; the swap
  removes the transition.
- Wi-Fi took a new DHCP lease after the reboot (`.252`): the random fallback MAC.

## 2026-11-08 — AV out, Ethernet at every boot, a stable Wi-Fi address

- Ethernet backported to 6.18: `0708`, `0712`–`0715`, `0720`–`0721` on `sunxi64`. `0712`'s Makefile
  context and `0721`'s autonomous-EEE hook differ on 6.18: the 7.3 forms moved to `next/`. 6.18
  builds; not yet booted.
- A reboot lost Ethernet: `EMAC reset timeout`, probe -110. The EMAC's RMII reset needs the AC300's
  clock, which the PHY driver sets up; as modules, the PHY driver loaded after the MAC probed.
  `PWM_SUN20I` and `XPOWERS_ACX00_PHY` now built in: Ethernet up at boot, the PHY attached at 12.4
  s.
- Composite, forced on, 7.3: `vblank wait timed out`, TCON TV1 zero interrupts, as on the Tanix TX1.
  Live, during a mode set: TCON-TOP `0x020` bit 21 alone started TCON TV1 at 50 interrupts/s; bit 4
  alone nothing; both doubled the rate. Mainline gates TV1 at bit 24, R40's. Allwinner's
  `lowlevel_v33x/tcon/de_lcd_type.h`: TV0 gate 20, TV1 gate 21; `tv1_clk_src` bit 4, from the TVE.
- The owner, through the CTIA-to-OMTP adapter: no signal with the gate alone; colour bars, greenish,
  once TVE `0x004` bit 16 (composite enable) was set too. PAL as well as NTSC: greenish, so RGB into
  a YCbCr encoder; `sun4i_tv`'s color correction is a no-op on DE3.3.
- Wrong turn: a PAL frame into an NTSC encoder. The connector's "TV mode" property, NTSC by default,
  picks the encoder's standard, not the display mode; PAL needs `TV mode` set to PAL.
- With the gate, composite enable and YCbCr out in the driver: colour bars, every other line black,
  slight flicker. Allwinner's `drv_tv.c` drives composite progressive: 720x576 of 864x625 and
  720x480 of 858x525 at 27 MHz, `b_interlace = 0`, TV1 clocked by the TVE; only YPbPr is interlaced.
- `0098`: the H616's TV1 gate at bit 21, its clock from the TVE. `0089`: composite enable in the
  tables, YCbCr from the CRTC's format, and Allwinner's progressive timing as the adjusted mode. The
  owner: a full picture, good colours, PAL 576i.
- Sound on the jack: line out and DAC were muted at boot. Unmuted, `speaker-test` heard on the TV.
- Wi-Fi address: the driver's eFuse read is empty. `99-stable-mac.patch` now takes the tree's
  `local-mac-address` after the eFuse: `12:00:c9:bf:a2:74 from device tree`, stable.
- Allwinner's secure storage, sector 12288: an index of `name:size`, CRC32 at 4092; 4 KiB slots from
  sector 12304, primary then backup, magic `0x17253948`, data at 0x64, CRC32 of 3172 bytes at 3172.
  Items `wifi_mac`, `mac` and `snum`. The owner: `mac` is the label's Ethernet address, with
  Amediatech's registered OUI. The Tanix TX1 holds its label address as `mac` too.

## 2026-11-08 — AV audio channel order

- `speaker-test -c 2 -t wav` on the codec: the owner hears left and right swapped through the
  CTIA-to-OMTP adapter. The same cable on the H96 Max M2 Plus: channels right, red and yellow
  swapped.
- Stock's driver, Allwinner's `sound/soc/sunxi_v2/snd_sun50iw9_codec.c`: left mixer from
  `LMIX_LDAC`, right from `RMIX_RDAC`; `LINEOUTL_SEL`/`LINEOUTR_SEL` pick each side's own mixer at
  0, their reset value, which init leaves alone; stock's audio XML names no H616 control. Mainline
  programs the same: "DAC Playback" on, "DAC Reversed" off, "Line Out Source" 0. The swap is the
  board's jack wiring.

## 2026-11-08 — factory addresses from secure storage

- U-Boot boots from the SD: the boot ROM tries it before the eMMC; the card's boot area reads
  `U-Boot 2026.10`. Mainline derives each `ethernetN` alias's address from the SID; it has no
  secure-storage reader.
- `0005`: U-Boot reads secure storage's index and items, CRC-checked, and sets `ethaddr` from `mac`
  and `eth1addr` from `wifi_mac`. Built, written to the SD's boot area over SSH, read back equal.
- After a reboot: Ethernet on the label's address, Wi-Fi on `wifi_mac`, the AIC8800 logging
  `from device tree`; both new DHCP leases.
- Bring-up: the chip's eFuse first, then the label or its factory store; check N21 added. The Tanix
  TX1's ATBM eFuse address carries AltoBeam's registered OUI and stays.

## 2026-11-08 — Bluetooth

- Stock: UART1 PG6–PG9 with RTS/CTS, `bt_rst_n` PG19 driven high by the vendor rfkill, `bt_wake`
  PG17 high, host wake PG16. The board tree had no UART1.
- Tree: UART1 enabled, `aicsemi,aic8800-bt` at 1.5 Mbaud, as on the R69-1; gpio-hogs hold PG19 and
  PG17 high. Kernel: `linux-rockchip/6.12/bluetooth-hci-h4-serdev.patch` on both sunxi kernels.
- First boot: no `hci0`. The conf edit had asserted on 6.18's conf, missing the anchor, and written
  nothing; the build carried 267 patches as before. Fixed per conf.
- The hogs landed on PA6, an EMAC1 RMII pin, and the second failed: 7.x's `gpiochip_add_hog()` hogs
  the first cell as the line, after running the cells through of_xlate only for flags. On sunxi's
  three cells that is the bank. `next/0039` hogs the line of_xlate names; PG19 and PG17 now held.
- `hci0` `UP RUNNING`, errors 0; LE only. An LE scan: 123 reports in 12 s. The controller's address
  `0B:3B:22:AC:88:20` has the I/G bit set: no eFuse address.
- `0040`: an AIC8800 whose address is made up takes the tree's `local-bd-address`; an eFuse address
  stays. U-Boot's `0005` sets `bdaddr` one above `eth1addr`, and `CONFIG_BLUETOOTH_DT_DEVICE_FIXUP`
  writes it on the node. After a reboot: `88:00:D4:D4:3A:B3`, the Wi-Fi's plus one; a scan, 117
  reports in 10 s.

## 2026-11-08 — 6.18

- 6.18.62 with every fix, booted once as the default: Ethernet on the label address, the AC300 PHY
  attached at boot; Wi-Fi `from device tree`; `hci0` `UP RUNNING`, errors 0, the Wi-Fi's address
  plus one; hogs on PG17 and PG19 through 6.18's own hog code; `rc-h96max` registered.
- Composite, PAL on connector 74 (76 on 7.3): TCON-TOP bits 4 and 21, TCON TV1 progressive 720x576
  of 625 lines at 27 MHz, TVE `0x07070001`, no vblank timeout: 7.3's working state. Picture not
  watched; a todo. Default back to 7.3.3.
- Owner: 6.18 is the board's kernel, 7.3 the `-next` one. `BOARD_KERNEL=sunxi64`; on the box,
  `U_BOOT_DEFAULT="l1"` in `/etc/default/u-boot` boots 6.18 first.

## 2026-11-09 — the unattended bring-up pass, 6.18.62 and 7.3.3

- Tools: `display.py` gained every plane at once by writeback; `video.py` AFBC and deinterlace
  suites and an interlaced clip; `gpu.py` runs dEQP from a `deqp` package (VK-GL-CTS
  `opengl-es-cts-3.2.11.0`, `deqp-runner` 0.20.3, as Mesa 25.0.7's CI) against Mesa's G52
  expectations. glmark2's `--validate` dropped: on DRM its surface is fullscreen, llvmpipe fails the
  same scenes.
- Tree: the CPU table is now the factory's, every bin: SID speed `0x5c00`, bin 4, 480–1416 MHz to
  1150 mV, DCDC2 capped at 1160 mV. The Tanix TX1's table it replaced topped at 1344 MHz. The
  writeback node added; the phantom PH9 recovery key removed.
- 7.3's `next/0276` and `next/0281` passed their blob size as 7.x's new `max_size`: short LUT and
  HDR10+ blobs were taken. Fixed; display.py 35/35 on both kernels.
- Results in the Test report. Failures and gaps: Wi-Fi country ignored, USB input unnamed, 100 s
  `s2idle` resets, 7.3's lockup only by watchdog, 6.18's CEC address missing, heat throttles at 70
  °C. Each is a todo.
- dEQP, every 20th case: 4980 pass, 0 unexpected, on both kernels with our Mesa.

## 2026-11-09 — glmark2 on our Mesa

- `glmark2-es2-drm`, full suite on screen, 2256×1504, 6.18.62, Mesa `25.0.7-2+deb13u1+tvb0`: 122.
  The 41–42 before was Debian's Mesa, pulled in by `glmark2-es2-drm`; the published repo has no
  Mesa.

## 2026-11-09 — eMMC at HS200

- Tree: `max-frequency` 100 MHz and `mmc-hs200-1_8v`, stock's; was DDR52 at 50 MHz.
- 6.18.62: `mmc0: new HS200 MMC card`, tuned at 100 MHz. `fio` read-only on the eMMC: 88.9 MB/s
  sequential, 3815 IOPS random 4k; was 75.5 MB/s, 2966 IOPS. Two warm reboots, HS200 each, no eMMC
  CRC or timeout in dmesg.
- SD: stock claims UHS to SDR104 at 150 MHz, I/O switched between DLDO1 and ALDO1 by two `vqmmc*sw`
  supplies; left at high-speed, in the board's todo.

## 2026-11-09 — Bluetooth address through the `bluetooth0` alias

- U-Boot `0006`: `local-bd-address` on the node `bluetooth0` names, the compatible as fallback;
  `CONFIG_BLUETOOTH_DT_DEVICE_FIXUP` dropped from `uboot/sunxi-h616.conf`. Tree: `bt:` label,
  `bluetooth0 = &bt`.
- Written to the SD's boot area at 8 KiB over SSH, read back equal. After a reboot, 6.18.62: `hci0`
  `88:00:D4:D4:3A:B3`, Wi-Fi `88:00:d4:d4:3a:b2` plus one.

## 2026-11-09 — `BOARD_EPOCH` dropped

- The plan continues a board's versions in the newest epoch published: `tvb-h96max-h313` holds
  `1`–`3` and the transition `1:1`, so the H313's next is `1:2`. No key in `board.conf`.
- The 3518's `Breaks: tvb-h96max-h313` is unversioned now that a board holds the name: a migrated
  box drops the empty `1:1` and is never offered the H313's package.

## 2026-11-09 — the printed address is on the PCB

- `pcb-bottom.jpeg`: a sticker reads `MAC:900EB3D69ABA`, beside
  `BA979 V1.0 AIC8800D40L HCY3802 2+16 BSK260910001`; the top's silkscreen has an empty `MAC:` box.
  Not on the enclosure, as the entries above say.

## 2026-11-09 — RAM bandwidth

- `stress-ng --stream`, 15 s, read / write MB/s, one instance then four: H313 858/572, 831/554; M2
  Plus (DDR3) 1267/844, 2833/1889; M20 (LPDDR3) 954/636, 2087/1392. One core saturates the H313's
  bus; the Tanix was offline.

- The flat ceiling is the H616's: the Tanix TX1 V2.0 shows the same, 861 / 841 MB/s on one and four
  cores, and both run their factory boot0's DRAM settings. 4K reaches the screen only as AFBC.

## 2026-11-09 — LED colours

- The owner: blue while running, red asleep, off and booting. `power` (PH6) is blue, `standby` (PH7)
  red: `color` added to both nodes.

## 2026-11-09 — LEDs keep their state

- `retain-state-suspended` and `retain-state-shutdown` on both LED nodes, as the trees phase's graft
  asks: the sleep and shutdown hooks set the colour, and the LED core no longer turns it off after.
- `systemctl suspend`, 21 s of s2idle with an RTC wake: red asleep, blue on resume, watched by the
  owner. `rtcwake -m freeze` alone bypasses systemd's sleep hooks and leaves it blue.
