# Tanix TX1 V2.0: what is left

The board's open items, in the order they block each other; first, the checklist lines not yet ✅
that need hands.

## Needs you at the box

- [ ] Photos: the retail box and the unit's label.
- [ ] AV port bring-up: no picture and no sound on a composite-to-HDMI converter. Stock drives the
      jack from the same blocks, the internal TVE and codec (`stock/tanix-tx1-v2/kernel-config.txt`:
      `TV_DISP2_SUNXI=y`, `DISP2_TV_AC200` off); the AC200 is up on stock only for its EPHY.
  - [ ] Stock over FEL on the same converter and cable: a picture or sound decides cable or jack
        against driver. A picture: dump `tcon-top`, TCON TV1, TVE, TVE top and copy the difference.
  - [ ] Headphones straight in the jack: the codec's line out by ear, with no converter muting it.
  - [ ] In the kernel, found live (`worklog.md`, 2026-10-26): `tcon-top`'s H616 TV1 gate (bit 21,
        not 24) and the TVE clock source; TVE `0x004` bit 16 in both tables; TCON TV1 progressive on
        the TVE clock; `GCTL` bit 0 clear; then `pll-video1` shared with HDMI's TCON.
- [ ] HDMI 10-bit: a 4K TV at 4K60; `VP_PR_CD` reads 10-bit (`0x50`) in YUV 4:2:0.
- [ ] HDMI CEC: plug into a CEC TV, `cec-ctl -d /dev/cec0 --playback -S` lists `0.0.0.0: TV`.
- [ ] Stock restored over FEL, then on stock PH9 held 2 s at power-on and the bundled remote's Menu
      held from power-on through stock's first 2 s, each either reaching Android's recovery or not.

## Issues found

- [ ] Wi-Fi latches: rx drops to 11 Mbit/s after hours associated, until the firmware restarts;
      `atbm6031/0015` now restarts it on detection. The trigger is not known.
- [ ] Patch parity: one series per subsystem on both kernels, taken whole: LibreELEC's where it is
      better maintained (audio, the video engine, `sunxi-mmc`), the other boards' and SoCs' patches
      (AC200, other trees, SCPI) out of 7.2; per-kernel copies only where the API forces them.
- [ ] A self-wake on 7.2: asleep from the remote at 23:21:40, awake at 23:22:43 with no key, while
      7.2 ran without Wi-Fi. Not seen again in four sleeps since; the wake source,
      `/sys/power/pm_wakeup_irq`, was not read. Read it if it recurs.
- [ ] The 70 °C trip holds the CPU at 1008–1200 MHz under four cores, 76–77 °C. Stock's own trips
      and cooling against ours, before calling it the box's limit.

- [ ] One U-Boot for the eMMC and FEL: the two builds differ in control tree, configs and startup;
      only the startup needs to, by `fel_booted`. One tree and one config set halve the variants to
      test. Blocked on the board tree keeping U-Boot's eMMC init, which it broke once
      (`Card did not respond to voltage select!`).

- [ ] `RCQ sync timed out`: logged twice with a player on screen and once during a mode set; the
      display engine's register queue missed its sync. Cause not found.

## Waiting on your go

- [ ] Install from stock Android over the network: stock is `userdebug`, `test-keys`, `adb` on TCP
      5555 with `ro.adb.secure` 0, so `adb root` works. The image from a stick, written around the
      per-unit window, then a reboot. Not run; run once with the FEL backup as the way back, then
      documented.
- [ ] A reboot into FEL from Debian, no button: stock U-Boot jumps to the BootROM's FEL
      (`jump to efex`, `misc` "boot efex"); whether ours can, untested.
- [ ] PH9, the recovery button (U-Boot), as the fallback in our U-Boot: held at power-on, the
      previous kernel (`pxe_label_override l1`, u-boot-menu's second entry); held longer, U-Boot's
      boot menu on HDMI, for a USB keyboard. Stock reads it held 2 s for Android's recovery. Known:
      `gpio input` reads the active-low pin as 0 when held. Built once, removed; your call to
      rebuild.
- [ ] `/root/fallback-618/` on the box, the 6.18 debs before 7.2's display stack: delete once the
      new kernel has served a while.

## For consideration

- Deep suspend: Linux reaches `deep` only through PSCI `SYSTEM_SUSPEND`. On the A64, H5 and H6 that
  is SCPI to crust on the ARISC core; the H616 has no such core and no secure SRAM A2 (TF-A's
  Allwinner documentation), so TF-A uses its native ops: core on/off, system off and reset. Effort:
  a native `SYSTEM_SUSPEND` in TF-A, DRAM self-refresh and the wake path from EL3 — large. The
  AXP313 is there to cut the CPU rails once that exists; `poweroff` already cuts them all.
- The display stack is 7.2's on both kernels (`linux-sunxi/0034`–`0038`): planes offer NV12, P010
  and AFBC, and GStreamer scans Cedrus's buffers out with no copy. `kmssink` tops out at 36 fps
  (`skip-vsync=true`; 30 without) — each legacy plane update blocks a vblank — and with clock sync
  drops nearly every frame. The player that counts is Kodi 22, on atomic commits: its 4K60 playback
  is the test. HDMI 10-bit: the monitor takes 30- and 36-bit (EDID), the stack offers `max bpc`,
  `Colorspace` and `HDR_OUTPUT_METADATA` and XR30, AR30, P010 on the VI plane, yet an XR30 plane at
  `max bpc` 10 leaves `VP_PR_CD` at 8-bit (`0x40`): LibreELEC's DE33 output takes 10 bits only as
  YUV 4:2:0, which a sink offers on 4K TV modes; RGB 10-bit would extend `sun50i_fmt`. CEC needs a
  TV.
- Every fix on `sunxi64-next` comes back to `sunxi64`, 6.18, once it works on `-next`.

## Repo

- [ ] Image rebuilt with every patch here: the last, `tvbian-tanix-tx1-v2-trixie-2026-10-28.img.xz`,
      predates `0095`, the 6.18.60 kernel and the FEL loader that boots into `ums`.
