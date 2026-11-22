# RK35xx worklog

## 2026-11-15 — next2 exploration

- A mainline 7.x `rk35xx-next2`, first tested on the H96 Max 3518.
- Candidate source: `zte-cloud-computer/w132d-linux-mainline`, commit
  `d9bfd153f813b7f35280db6d356ca35106d37577`, downloaded to `build/rebase/w132d-mainline`.
- Its rkvdec, thermal and display patches imported unchanged into
  `patches/linux-rockchip-mainline/`; all apply to Linux 7.3.4.
- Its rkvdec patch selects the VDPU381 variant for RK3528's VDPU382: a candidate, not a verified
  hardware equivalence.
- `kernel/rk35xx-next2.*`: mainline's arm64 defconfig with only Rockchip among `CONFIG_ARCH_*`, plus
  an experimental fragment. The release planner discovers every kernel conf; this target is not
  release-ready.
- Config check 1 failed: built-in DWMAC under modular STMMAC; STMMAC enabled. Check 2: the
  regulatory key options need `CONFIG_EXPERT`; enabled. Check 3 passed.
- DT rebase toolkit: an explicitly invoked experimental vocabulary; one under the vendor source name
  would change every existing vendor-tree build.
- Mainline's power binding header is `rockchip,rk3528-power.h`; the vendor filename returned
  HTTP 404.

## 2026-11-15 — first mainline build and translation

- Linux 7.3.4 builds with the decoder, thermal and display patches: 606 s first, 42 s cached with
  the SoC descriptions and binding patches.
- Imported the candidate's SoC-only descriptions as a patch to `rk3528.dtsi`; its media, display,
  PHY and thermal bindings, then the SAI/PDM binding changes.
- The vendor kernel has no kexec support: no one-time kexec test.
- DT toolkit bugs: aliases before their targets disappeared; macro unit addresses did not match
  numeric ones, duplicating power domains. Fixed, with tests; all 165 pass, the H616 and GXL factory
  translations byte-identical.
- First binding validation: unconsumed vendor clock/OPP nodes, node names, missing audio fallback
  bindings, the vendor OTG supply spelling. Corrected.
- The translation report still lists unresolved blocks and policies: zero unknown tokens is not a
  completed port.

## 2026-11-15 — ready for the first boot

- Combined build passes: kernel, radio modules, metapackage. Log:
  `build/rebase/rk3528-next2-complete-build.log`.
- Binding validation reports only the board-compatible tuple:
  `build/rebase/rk3528-next2-dt-validate.log`.
- Test install beside the vendor kernels: a local-bottom initramfs hook restores the saved vendor
  menu; a systemd guard reboots an unconfirmed test after 180 s. Neither protects a hang before root
  mount.

## 2026-11-16 — First serial mainline boot

- The imported SRAM node has a label, so the translator merges the factory SRAM there: no duplicate
  `fe480000.sram`.

## 2026-11-16 — Post-mortem

- `research/rk3528-mainline/postmortem.md`: observed failures, recovery limits, agent omissions,
  proposed bring-up procedure changes. Root cause open: the PMU access trace is a failure site, not
  its cause.

## 2026-11-16 — Power-domain policy diagnostic

- Vendor 6.12 and mainline power-domain sources both use PMU ack offset `0x1120`; the vendor marks
  every RK3528 domain always-on, mainline does not.
- `pd_ignore_unused` skips only the late-init unused-domain pass, not every runtime shutdown.
- A diagnostic patch setting `GENPD_FLAG_ALWAYS_ON` on RK3528's domains reaches userspace where
  mainline's policy aborts in `genpd_power_off_work_fn`. The PMU fault's cause stays open.

## 2026-11-16 — SDIO diagnostics: the kernel side

- Config: tracing and dynamic debug, the missing font, lockup detectors, the zram baseline.
  Mainline's `CONFIG_BOOTPARAM_SOFTLOCKUP_PANIC` is an integer: `1`, not `y`. `CONFIG_ZRAM=m`
  removes the missing-`zram0` startup wait.
- Early root access for one boot: `systemd.debug_shell=ttyS0` with the serial getty masked.
- `pmdomain-clear-failed-clock.patch`: clear the failed `of_clk_get` entry before `clk_bulk_put`
  sees it. The deferred clock probe had tainted the kernel (512) and warned in `__clk_put`.
  `checkpatch.pl --strict --no-tree` on 7.3.4, with its spelling and const-struct tables, clean.
  With it: taint 0.
- `CONFIG_RESET_GPIO=m` makes the MMC power sequence pulse the enable during its off sequence
  (`pre_power_on`: `reset_control_deassert`, then `reset_control_assert`; `post_power_on` deassert
  about 12 ms later). `=n` makes the optional reset request return NULL and selects MMC's GPIO-array
  fallback. SDIO fails either way: the pulse was not the cause.
- Mainline has no RK3528 cpuidle driver.

## 2026-11-16 — SDIO found: the radio's PCM pins

- Mainline has no SAI0 node, so the translation dropped the factory SAI0, which feeds `bt_sco`, and
  its `i2s0m0` pins (GPIO3_B5–B7) kept their pull-downs. The four `i2s0m0` groups, bias off as
  factory, go in `sdio-pwrseq`'s `pinctrl-0`, in `build/rebase/prepare-next2-tree.py`.

## 2026-11-16 — next2: GPU, display, and a one-shot boot that works

- The one-shot hook never restored the vendor menu: klibc `mount` needs a device and a directory,
  and the initramfs has no `cp`. It remounts with `"$ROOT" "$rootmnt"` and copies with `cat`.
- `rockchip-drm` bound nothing: the translation drops the factory `display-subsystem` (no base
  node). Folded into `arm64-dts-rk3528-media-display.patch`, as upstream SoC dtsi files carry it.
- The GPU enabled without its OPP table, at the assigned 300 MHz.

## 2026-11-17 — glmark2 off a headless box: void

- Every `glmark2` score taken with no screen plugged in is void: the suite forced HDMI on without an
  EDID, so each kernel scanned out its fallback mode, next2 likely nothing; the near-doubling was
  memory bandwidth, not the GPU. dEQP stands: 832 passes on both kernels say next2 renders
  correctly, not faster.
- The `ACLK_GPU_MALI` 498 MHz choice rested on the void numbers.

## 2026-11-17 — gaps closed without a box, untested on one

- `media-rc-keymaps-r69-1.patch`: the R69-1's remote at NEC address 0x05; its factory table holds
  the M2 Plus remote's 22 command codes, every button the same key.
- `media-hantro-rk3528-bindings.patch`, `media-hantro-rk3528.patch`: the node is
  `"rockchip,rk3528-vpu", "rockchip,rk3568-vpu"`, as in Kwiboo's tree; the RK3528 variant caps VP8
  at 1080p, so a larger stream is refused, not decoded broken.
- `rockchip,disable-mmu-reset` on the decoder's IOMMU, as mainline's RK3576 has it: va-api saw
  `FORCE_RESET command timed out` at boot.
- The kernel builds; the three next2 trees are rebuilt and proven.

## 2026-11-17 — VP9 and PVTM, built, untested on a box

- VP9: patchwork series 1134753 (VDPU381 VP9, v1), patches 1–3 as written; 4/4 dropped, as its
  reviewers agreed. RK3528's match already points at the VDPU381 variant, so VP9 appears with no
  patch of ours. Applies on 7.3.4 over `media-rkvdec-rk3528.patch`; the kernel builds.
- PVTM: `cpufreq-rockchip-pvtm.patch` measures as the vendor does (CPU to 1608 MHz, rail to 900 mV,
  1.1 ms, the GRF count at 0x18), maps it by the factory's `rockchip,pvtm-voltage-sel` and names the
  bin's `opp-microvolt-L<n>` columns before cpufreq-dt; `rockchip,rk3528` joins cpufreq-dt's
  blocklist. The translation keeps the bin columns and, in the CPU table only, the measurement
  properties; `core_grf` at 0xff300000 is new in the dtsi patch, with its binding. The vendor's 10
  °C floor (`rockchip,low-temp-min-volt`) is not applied.
- An OPP row with no unit address met any mainline node of its name: the CPU's 600 MHz row met the
  GPU table's and was dropped. Rows now meet only their own table's.

## 2026-11-17 — the M2 Plus on the new kernel (va-api's run)

- The VDPU381 VP9 series drives the VDPU382 as it stands; `rockchip,disable-mmu-reset` clears the
  decoder IOMMU's `FORCE_RESET` timeout.
- PVTM driver: samples until two counts agree within 0.5%, no bin if they never do. Then report-only
  (`apply=1` to use it): it logs the count with the clock rate and the rail read back at the read,
  and the bin it maps to.
- CMA: `onbox.py` samples `/sys/kernel/debug/cma/*/used` every 50 ms through each regression step
  and appends `cma.peak.mib <peak> of <pool>`, failed past 90% of the pool.

## 2026-11-17 — PVTM matches vendor on the R69-1

- PVTM driver: sets exactly the measuring voltage, restores exactly the old one, and gives no bin
  when the rate or the rail reads back off it. The RK3528's point (1608 MHz, 900 mV) is unchecked.

## 2026-11-17 — the vocabulary: unresolved as the last resort

- The vendor codec, TVE and IOMMU nodes `enable` their mainline blocks; each next2 `board.patch`
  lost about 80 lines of status changes, DTBs byte-identical (the 3518D's TVE, enabled in its
  factory tree, is its board's own `disabled` now: no AV jack).
- Every other unresolved item checked against a 7.3.4 binding or a carried driver: `same` where
  mainline reads it (`opp-suspend`, `mali-supply`, `pa-ctl-gpios`, `tx_delay`, `snps,reset-*`,
  `rockchip,default-sample-phase`), `none` with its reason for vendor frameworks and tuning,
  `unsupported` for hardware with no driver here. Unresolved per board: 60–66 to 10–13.
- The trees gained `opp-suspend`, `mali-supply` and the codec's `pa-ctl-gpios` (GPIO0_A0, the analog
  amplifier the M2 Plus's tree had lacked).
- Wrong turn: mapping the BSP's `active` PWM pin state to `default`. The vendor applies it only once
  a channel runs, mainline at probe, so on the R69-1 PWM5 took the Ethernet LED's pin. It is `none`
  now.

## 2026-11-17 — the generator's conversions into dtcx, batch 2

- The vendor's SAI, S/PDIF, RNG, display subsystem and simple cards map onto mainline's by
  compatible; SAI0, SAI1 and their cards (Bluetooth PCM, the microphone array) are unsupported:
  mainline's dtsi lacks them. The vendor's dwc3 wrapper and GRF go: mainline's nodes are flat.
- New conversions: `rk-sound-card` (the vendor's HDMI card as a `simple-audio-card`) and `pwm-ir`
  (the PWM-capture remote as `gpio-ir-receiver` on its pin).
- Each tree keeps what its vendor tree enables: the generator no longer disables TVE, the analog
  card, SAI2 or S/PDIF on a board without the jack. The 3518D gains TVE, analog, S/PDIF and the IR
  receiver; the M2 Plus and the R69-1 gain S/PDIF; the H96 Max RK3528 gains HS400.
- Every other change proven by `semdiff.py` against the previous build: no difference.
- A `wrapper` node action: the vendor's dwc3 wrapper goes and its child meets mainline's flat
  `usb@fe500000`, with the vendor's PHYs, role, speed and quirks. The 3518D gains USB3 as its vendor
  tree has it; the H96 Max RK3528 runs USB2-only at high speed, as its vendor tree does.
- `#cooling-cells` kept as the vendor writes it: CPU 0 and the GPU. The cooling map names CPU 0, the
  policy CPU; the generator's copies on CPUs 1–3 went.
- `init-voltage`: a rail with the vendor's `regulator-init-microvolt` is held there unless a
  consumer's OPPs scale it (`vdd_logic`; `vdd_gpu` where it is its own rail). `withhold`: a property
  dropped from mainline's node too, for the GPU's OPP table while GPU scaling is unproven. The four
  trees byte-identical to the generator's.
- Profiles hold only what the generator reads: model, compatible, keymap, the AIC8800 marker. The
  3518 has one again; the 3518D gains the keymap its factory remote address (`0x4040`) names.

## 2026-11-18 — MPEG-4 and H.263 on VDPU2, against MPP's own registers

- The back end (`media-hantro-vdpu2-mpeg4.patch`) on the private MPEG-4 controls (`linux-sunxi`
  `0422`, `0805`); FFmpeg `0048` hands a decoder that holds no CAPTURE buffer the VOP whole.
- First run: every picture ended `DEC_TIMEOUT` (`0x2001` in the interrupt register), all zero out.
- Ground truth from the vendor kernel:
  `echo 0x1004 > /sys/module/rk_vcodec/parameters/mpp_dev_debug` (`DEBUG_SET_REG` and
  `DEBUG_IRQ_STATUS`) logs every register MPP writes and each job's status, under
  `ffmpeg9 -c:v h263_rkmpp` / `mpeg4_rkmpp` on one clip. Against Hantro's `debug=64` register log
  the differences were the prefetch threshold (1, not MPEG-2's 8), the quarter-pel filter taps in 59
  and 153 (set for every picture), and H.263's VOP time resolution (30000, fixed in MPP).

## 2026-11-18 — the next2 generator's fixes into dtcx

- A withheld `operating-points-v2` takes the cooling maps naming its node (`translate.py`,
  `unthrottled`): the GPU's map left the five trees' `board.patch`.
- `hdmi-ddc-i2c` (`conversions.py`, `also rockchip,rk3528-dw-hdmi`): dw-hdmi's DDC on the I2C
  controller whose pins are the HDMI group's, the group keeping CEC, the controller enabled; the
  three DDC hunks left each `board.patch`, the generator's comment on the pins left `board.dts`.
- Each step: retranslate, `board.patch` rewritten from the new translation to the same `board.dts`,
  `build-dtb.sh`, every DTB byte-identical. Left in `gen.py`: the radio's power sequence and reset
  (PCM pins, delay, Seekwave polarity), the AIC8800 MAC node, the board's own choices.

## 2026-11-19 — DDR rate changes: what vendor's kernel asks of BL31

Read from rockchip-linux/kernel develop-6.6 `drivers/devfreq/rockchip_dmc.c` (`rk3528_dmc_init`,
`rockchip_ddr_set_rate`); nothing run.

- SIP `0x82000008`, `smc(fid, arg0, arg1, cmd)`: `GET_VERSION` (`0x08`, needs `>= 0x100`), then
  `SIP_SHARE_MEM` (`0x82000009`, 2 pages, type DDR) mapped non-cached and zeroed, the `complete` IRQ
  (GIC SPI 17) written into the page, `INIT` (`0x00`), `GET_FREQ_INFO` (`0x0e`): BL31 lists the
  trained rates, which replace the DT's.
- A change fills `hz`, `lcdc_type`, `vop_scan_line_time_ns` and both wait flags, then `SET_RATE`
  (`0x01`); on `-6` it waits up to 85 ms on the IRQ, whose handler calls `POST_SET_RATE` (`0x09`).
  No timing parameters pass on RK3528.
- `center-supply` is `vdd_cpu`, shared with the CPU and GPU; every factory DMC OPP needs 900 mV,
  mainline's CPU and GPU OPPs reach 875 mV.
- Mainline lacks `GET_VERSION`, `POST_SET_RATE`, `GET_FREQ_INFO` and `SIP_SHARE_MEM`; `rk3399_dmc`
  uses the old register API. `rockchip-dfi.c` has no RK3528: its DDR type sits in PMUGRF
  `0x248`/`0x24c` (`0xff370000`), one channel; mainline knows no DDR3 or DDR4 there.
- Load-based scaling hung the M2 Plus on vendor (2026-11-06): change the rate on status, not load.
  The 3518D's loader trains 666 MHz (LPDDR3), the M2 Plus's 786 MHz (DDR3).

## 2026-11-19 — AFBC from rkvdec to the VOP: where each end stands

Read from MPP develop, vendor 6.1 and mainline 7.3.4; nothing run.

- VOP: mainline VOP2 scans out AFBC `YUV420_8BIT` and `YUV420_10BIT` on Cluster windows
  (`formats_cluster`, `format_modifiers_afbc`, `WIN_FEATURE_AFBDC`). Our RK3528 Cluster0 lists
  `formats_cluster` with linear `format_modifiers` and no `WIN_FEATURE_AFBDC`. Vendor's RK3528
  Cluster0 uses `rk3568_cluster0_afbc` at the RK3568 offsets, with `format_modifiers_afbc_tiled` and
  `WIN_FEATURE_AFBDC`.
- Decoder: MPP's VDPU382 HAL sets `reg012.fbc_e`, both horizontal strides to the header stride
  `/ 16`, and `reg020` to the payload offset `/ 16`, where `reg020` holds `y_virstride` linear. The
  header stride is `ALIGN(width, 64)`; the payload starts at
  `ALIGN(hdr_stride * (ver_stride + 64) / 16, 4K)`; the picture starts 4 lines down
  (`offset_y = 4`). With FBC on, MPP sizes an `RCB_FBC_ROW` row buffer and HEVC's filter column
  buffer from `filterd_fbc_on`. Mainline's `rkvdec-vdpu381-regs.h` already has `fbc_e`,
  `reg014_fbc_param_set` and the stride registers.
- V4L2: Cedrus already carries AFBC as `V4L2_PIX_FMT_YUV420_8_AFBC_16X16_SPLIT` (`AS12`) and the
  10-bit `AS01` (`patches/linux-sunxi/0058`), and FFmpeg's `0018` asks a v4l2request driver for its
  AFBC format through the device option `afbc`. Rockchip's decoder writes AFBC 16x16 sparse, not
  split (`0025` exports vendor's frames with `BLOCK_SIZE_16x16 | SPARSE`), so rkvdec needs sibling
  sparse formats beside Jernej's, offered after NV12 so a client composing with the GPU (lima
  samples no AFBC) never gets them unasked; `0018` maps each to its modifier.

## 2026-11-19 — the CPU clock is not its request on next2

- Method: `perf stat -e cycles,task-clock` on a pinned busy loop, the rate pinned by
  `scaling_min_freq` and `scaling_max_freq`. Each board's rates are in its worklog.
- BL31 takes and reports every rate: SCMI `CLOCK_RATE_SET` and `GET` on clock 0x15, flags 0, the
  same messages on both kernels. `core_grf` 0x14 and 0x18 read the PVTPLL's rate in MHz: the core
  runs off the PVTPLL from 816 MHz up, and at a given ring setting (`core_grf` 0x04) its rate
  follows the chip and the rail.
- The vendor's OPP code asks BL31 about each PVTPLL (`SIP_PVTPLL_CFG` 0x82000029, `GET_INFO`) before
  measuring the PVTM, and gives it the bin (`VOLT_SEL`). Both calls made from next2's PVTM driver:
  not kept. The factory trees carry no `rockchip,pvtpll-table`.
- The cause: the PWM regulators' pins were never muxed. The vendor names a PWM's pins `active`
  (`pinctrl-names = "active"`), and the translation dropped every `active` state, to keep an unused
  channel off a shared pin (PWM5 against the R69-1's Ethernet LED). With the CPU pinned at one ring
  setting, the GPU at 800 MHz raising the shared rail from 900 to 964 mV left the CPU at 1598 MHz:
  the rail sat at its power-on voltage on every next2 board. The translation now takes a PWM's
  `active` pins as its default where another node uses it (`state active used-as default`): the M2
  Plus's PWM0, 1 and 2, the RK3518 boards' PWM1; the R69-1's PWM5 stays off. `BOARD_PVTM=off`
  removed from the M2 Plus and the H96 Max RK3528.
- Vendor 6.12 and next2 give a chip the same clock for the same voltage (3518 against 3518D): next2
  drives the rail as vendor does.
- The RK3528 translation conf, re-read rule by rule against a runtime diff on the 3518D: stock's
  `pinmux-pins`, `gpio`, `regulator_summary` and `clk_summary` against next2's.
  `translate.py --report` now lists each `none` drop on an enabled node, which it had dropped
  unreported.
  - Pins: the HDMI DDC pins as I2C2, the IR pin as a GPIO and the eMMC pins claimed are the
    conversions; the FEPHY LED pins are unmuxed on the 3518D, which has no PHY fitted
    (`cannot attach to PHY`), and muxed on the M2 Plus, its PHY bound to the RK3528 FEPHY driver.
  - GPIOs, regulators and clocks match stock, but for the moment's state: CPU and GPU rate, the
    audio MCLK, and the GMAC clocks running with no PHY. The codec clocks are mainline's assigned
    300 and 340 MHz, the vendor's `normal-rates`.
  - `mbist-vmin`: the vendor raises an OPP under `mbist-vmin[index - 1]`, the index from OTP byte 9
    (CPU bits 0-2, GPU 3-4, logic 5-6). Byte 9 is 0x29, index 1 for each, on the 3518D, 3518, M2
    Plus and R69-1: floors 825, 825 and 850 mV, at or under every applied OPP. `opp-info` is zero.
  - `rockchip,grf`: the vendor gives it to 15 blocks; its CRU, GPU, codec, DFI and Wi-Fi drivers
    never read it, VOP2 only to invert RGB and BT.656 clocks. The codecs' `grf-mem-*`, which only
    stock's 6.1.118 Android kernel reads: rkvenc's 0x20010 already reads 0x21, VDPU2's 0x40034 and
    RGA/VDPP's 0x600e0 read 0 on next2 where stock writes 0x0f04 and 0x0ff1/0xf004.
  - The DMC's `leakage-voltage-sel` picks a column its table does not have. The GPU's
    `simple-power-model`: next2's IPA runs on the GPU's `dynamic-power-coefficient`. The OTG
    controller's `extcon`: host only on both. `pm_qos`: in mainline's dtsi.
  - Left as gaps: the PHY's temperature RX switch (`rockchip,thermal-zone`), the suspend firmware's
    config (`rockchip,pm-rk3528`), HDMI audio's computed CTS and always-on SAI clocks, the GPU bus's
    scaling. The DFI rule said unsupported; the next2 dtsi has it.
- Every `unresolved` and `dormant` entry in the RK3528 translation decided; the five boards' reports
  list none. The trees change only by `hpd-gpios`.
  - `hpd-gpios` kept: the RK3528 HDMI pad senses no hot-plug, and next2's driver mirrors this GPIO
    into the VO GRF sink-detect bit, holding its output bit set so the pad's input works.
  - `rockchip,use-v2-tuning` dropped: the vendor's v2 tuning keeps the bootloader's sample phase,
    then tries four coarse phases, then falls back to the full sweep mainline always runs.
  - `wlan-platdata`, `bluetooth-platdata` dropped: the vendor rfkill driver's lines. Wi-Fi's host
    wake serves suspend only; SDIO interrupts in band. The AIC8800's Bluetooth needed neither reset
    nor wake on the H313; on the RK3528 boards untested.
  - hwspinlock, mailbox and secure OTP dropped, disabled on every board; HDCP2 and the SCO codec
    unsupported; the ES7243 array dropped, its I2C bus disabled on every board.
- The next2 generator's edits now in the translation, each read from its vendor node: the FIQ
  debugger's console as uart0 on its pins (`console`); the template's LED names as roles
  (`led-roles`); its volume-up ADC key as the recovery button (`adc-recovery`); the Seekwave reset
  in the SDIO power sequence's polarity (`shared-reset`); vendor SAI0's pins in the power sequence,
  where the vendor enables SAI0 (`radio-pcm`). `board.patch` keeps the board's own: model,
  compatible, keymap, the watchdog, the measured 200 ms power-off and the AIC8800 MAC node. The
  generator is gone. The three Seekwave boards' DTBs are unchanged.
- The generator had copied the Seekwave boards' radio fixes onto the AIC8800 boards: `i2s0m0` pins
  in the power sequence where the R69-1's vendor SAI0 names `i2s0m1`, disabled, and stock leaves
  GPIO3_B5–C0 unclaimed; and the M2 Plus's measured 200 ms power-off. Both gone from the R69-1 and
  H96 Max RK3528 trees, untested on either box.
- HDMI pixel clocks off the PHY's table: next2's inno PHY took only its table's 99 rates, so a 3:2
  panel's native DTD, 2256x1504 at 235.7 MHz, never reached the mode list. Vendor 6.1 runs it:
  `clk_hdmiphy_pixel_io` 235700000, from `phy-rockchip-inno-hdmi-phy.c`'s PLL search
  (`inno_hdmi_phy_pll_cal`), a driver next2 does not carry.
  `phy-rockchip-inno-hdmi-rk3528-scaled-pre-pll.patch`: a rate off the table takes the dividers of
  the nearest entry whose TMDS clock is its pixel clock, the VCO scaled through the fractional
  feedback divider, inside the VCO range the table's entries span; 235.7 MHz from 234.59's chain at
  a 1885.6 MHz VCO.
- HDMI audio silent on next2: mainline's SAI sets its slot width to the sample's (16 bits, a 32 fs
  bit clock), the vendor's never changes it from 32 (64 fs), which the HDMI controller's I2S takes
  (`AUD_INPUTCLKFS` 64 fs). `rk-sound-card` now writes the CPU DAI's two slots 32 bits wide; no CTS
  patch needed.
- next2 in the release, beside the vendor kernels, opt-in as next is: a board with a `next2/` tree
  ships it as `/usr/lib/tvb/board-next2.dtb`, and its kernel hook links
  `/usr/lib/tvb/fdt/<version>/board.dtb` to that tree for a `*-next2` kernel, to `board.dtb` for any
  other; u-boot-menu's per-version `U_BOOT_FDT_DIR` gives each entry its link. One command line for
  every kernel: next2's `cma=128M` and its `ttyS0` console, which the vendor kernels skip. The
  release already publishes `linux-image-tvb-rk35xx-next2` and its modules. U-Boot 2026.10 follows
  ext4 symlinks.

## 2026-11-20 — the GPU's clock and throttling, vendor against next2

- Every next2 soak and test result so far is void on the owner's word; every RK3528/RK3518 box is
  back on vendor 6.1 by default.
- Our vendor tree names lima's `core` and `bus` both `aclk_gpu_mali`, the CRU's 500/300/100/24 MHz
  mux; the factory tree runs the GPU on the SCMI clock, as next2 does.
- The factory's own PVTM and `mbist-vmin` selection lands on next2's voltages.
- Thermal: the factory's 95 °C trip only switches `power_allocator` on; cooling is bound to the 110
  °C `target`, so neither kernel throttles below it. The gap: lima registers its cooling without an
  energy model, so the allocator budgets only the CPU. The factory gives the GPU a
  `simple-power-model`, `dynamic-coefficient = <724>`, which the conf dropped while saying mainline
  takes the GPU's `dynamic-power-coefficient`: no rule wrote it.
- Changed: `conversions.py` `gpu-power`, the conf's `node simple-power-model gpu-power`, every
  RK3528/RK3518 `next2/board.dts` (`dynamic-power-coefficient = <724>`, each from its own factory
  tree), and `drm-lima-devfreq-cooling-energy-model.patch` (`devfreq_cooling_em_register`, as
  panfrost and panthor), checkpatch `--strict` clean. The reset itself stays open.

## 2026-11-20 — the RK3528 datasheet against next2

Read: "RK3528 Datasheet", Rev 1.4, © 2025 Rockchip, pages 6-15 (features), from
`https://rockchip.fr/RK3528%20datasheet%20V1.4.pdf`, a host not confirmed as Rockchip's own.

- Against next2 it adds VC-1 (SP, MP, AP to 1080p60), H.264 MVC, H.264 4:2:2 and 4:0:0 output, JPEG
  decode to 8176x8176 with ROI, the VOP's HDR10, HLG, SDR2HLG and HDR Vivid, Esmart's 4 regions,
  Cluster rotation, SAI3's 8 channels to HDMI, S/PDIF and CVBS cable detection: each a row in
  `docs/todo/rk35xx.md`.
- It rates the encoder at 1080p60 (H.264 HP@L4.2, HEVC Main@L4.1) and the decoder at 4Kx2K@60; it
  lists neither VP8 nor VP9.

## 2026-11-21 — the patched next2 under the soak

- With `drm-lima-devfreq-cooling-energy-model.patch` and the GPU's coefficient, the M2 Plus's 1800 s
  soak completes with no reset; from 95 °C the allocator throttles the GPU and the CPU.

## 2026-11-21 — next2 on the boards' own `cma=16M`

- `BOARD_CMA=128M` in each `next2/board.conf` sized the pool for a display without its IOMMU. With
  the VOP behind its IOMMU, the full regression on next2 peaks under 3 MiB. `BOARD_CMA` and
  `package/board.sh`'s substitution are gone: next2 boots with each board's `cma=16M`, as the vendor
  kernels do. The H96 Max RK3528's next2 peak is unmeasured.

## 2026-11-21 — a mainline board as the next2 view's base

- The next2 views sit over `rk3528.dtsi` and run 911-1134 lines. Over each of mainline v7.3.4's
  RK3528 boards (ArmSoM Sige1, HINLINK H28K, NanoPi Zero2, Radxa E20C, ROCK 2A, ROCK 2F), set as
  `BOARD_KERNEL_DTB_UPSTREAM` on the M2 Plus's `next2/board.conf`, `upstream.py --prove` fails
  alike: the view drops the base board's `vcc_3v3` and `rgmii_phy`, which its PCIe, Ethernet, EEPROM
  and a regulator still name, and `dtc` stops. The vendor views over `rk3518-evb1-ddr4-v10.dts`
  prove.
- `upstream.py` fixed, with a test each: a deletion cascades until no reference dangles, across
  parents and into nodes off in both trees; an added node the base still points to is kept, as the
  M2 Plus's `rgmii_phy: phy@1` under the disabled `gmac1`, which the base's `phy-handle` names.
- Every RK3528 board then proves as the M2 Plus's base: Sige1 1162 lines, NanoPi Zero2 1139, H28K
  1131, E20C 1132, ROCK 2A 1126, ROCK 2F 1116, against `rk3528.dtsi`'s 1134. The view is the box's
  own rails, keys, LEDs and sound (380), the vendor's per-bin OPP tables (261), its pins (59) and
  OTP cells (44), none of which a router or SBC carries; next2 stays on `rk3528.dtsi`. Every other
  board's view regenerates byte-identical.

## 2026-11-21 — Bluetooth on next2, and what the translator dropped

- `kernel-rk3528-vendor-6.1.translate.conf` dropped `bluetooth-platdata` as `none`, so nothing
  powered the AIC8800's Bluetooth or bound `hci_h4`. The `rk-bluetooth` conversion puts a serdev
  `bluetooth` node on its UART, with the reset (other polarity) and wake lines; each board's patch
  adds `compatible` and `max-speed`.
- Sweep of every `none` across the seven RK3528/RK3518 factory trees: 56 drops. `wlan-platdata` also
  dropped `WIFI,poweren_gpio` and `WIFI,reset_gpio`, the chip's power line, noted only for its host
  wake. The `rk-wlan` conversion adds them to the SDIO power sequence's `reset-gpios`, once: the
  HK1's hand-written `RK_PB2` hunk goes, its tree byte-identical; the X88 Pro 13 gains
  `<&gpio1 RK_PA6 GPIO_ACTIVE_LOW>`, untested on the box.
- Parity: `box.py` records each device class's count and names, and the report fails a kernel with
  fewer than the board's own. next2 lacked `CONFIG_MEDIA_CEC_RC` (the CEC remote's input), now set
  and `dw_hdmi` registers; the IR is `gpio_ir_recv` on next2, the same receiver; the CEC and
  Bluetooth wake keys, the HDMI jack and DDR's cooling device are todos.
- CI: 8 caches at 1G; the Amlogic two at 0.97 GiB each.
