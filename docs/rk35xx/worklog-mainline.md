# RK35xx mainline worklog

The mainline kernel, next2: its patches, translation and tests.

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

## 2026-11-22 — translation rules from the HK1

- `amlogic,fd628_dev` joins the front-panel `unsupported` rule; `amlogic,dummy-battery` and
  `-charger` are `none`, no 6.1 driver binding them; `cec-enable`, `num-slots` and `supports-emmc`
  are `none`, no mainline reader. Every RK3528 next2 DTB regenerated byte-identical.
- `cec-enable`: in the vendor kernel only the RK628 bridge drivers read it; both kernels' `dw-hdmi`
  register CEC when the block's `HDMI_CONFIG0_CEC` bit is set (mainline `dw-hdmi.c` line 3573).

## 2026-11-22 — the same planes on both kernels

- The vendor driver types RK3528 VOP2 as VOP3 and ignores `rockchip,plane-mask`: each plane's ports
  are its window table's `possible_vp_mask`. Esmart0, Esmart1, Cluster0 VP0; Esmart2 VP0 and VP1,
  `DRM_PLANE_TYPE_CURSOR`; Esmart3 VP1, primary. `esmart_lb_mode` `02` feeds Esmart0 (4K), Esmart2
  and Esmart3 (2K); the vendor registers no plane for Esmart1.
- Next2 hard-coded `02`, offered Esmart1 unbuffered, kept Esmart2 VP1-only, and registered no cursor
  plane: mainline VOP2 types none on any SoC.
- `drm-rk3528-vop2-esmart-lb-mode.patch`: the split from the tree's `esmart_lb_mode` or
  `rockchipdrm.esmart_lb_mode`, `02` without either; Esmart windows it leaves unbuffered not
  registered. A `u8` mask dropped Esmart2 and Esmart3, whose IDs pass bit 7: `W=1` caught it.
- `drm-rk3528-vop2-cursor-plane.patch`: the vendor's table, Esmart2 a cursor plane on VP0 and VP1,
  Esmart3 VP1's primary. Composite's desktop moves to Esmart3, which showed black on next2.
- The vendor kernels take `rockchipdrm.esmart_lb_mode` over the tree's value. The translator keeps
  `esmart_lb_mode`; every next2 board patch sets `02`, each DTB's only change.
- Built: 6.1, 6.12, next2; checkpatch clean. The 20:42 regression, the 3518, 3518D and R69-1 on all
  three kernels: HDMI's planes alike everywhere, primary, overlay and cursor.

## 2026-11-22 — the front panel's bus, translated

- `panel-bus`: a vendor front-panel node, `rockchip,fd655_dev` or `amlogic,fd628_dev`, becomes
  mainline's `i2c-gpio` bus `i2c-display` on its clock and data pins, open drain. The chip and its
  digit map stay in each board's patch: no vendor node carries them.
- The HK1's next2 tree came out identical to its hand-written bus; its patch and the H96 Max
  RK3528's now add only `display@24`.

## 2026-11-24 — next2: Bluetooth's RTS, and the datasheet's blocks

- `rk-bluetooth` adds the vendor Bluetooth node's pin state, its RTS, to the UART's own. On the
  R69-1 and the HK1, 7.3.5: pin 98 owned by `ffa00000.serial` in `uart2m0-rtsn` (before: unclaimed),
  `hci0` powered, a 60 s scan found 39 and 33 devices, no pin-claim error. The Seekwave boxes' trees
  are unchanged.
- The datasheet's blocks on the R69-1's next2: `rockchip-rng` the current hwrng; V4L2's JPEG
  decoder, IEP2, VDPP, RGA, `rkvenc`, `rkvdec` and the Hantro decoder; both SAIs, S/PDIF, the analog
  codec, TSADC and the PWMs bound. The crypto engine has no driver.
- The analog codec at the datasheet's rates: 8, 16, 32, 44.1, 48 and 96 kHz open as asked; 12 kHz
  opens 11.025, 24 kHz opens 22.05. Next2's driver lists `SNDRV_PCM_RATE_8000_192000`, as the
  vendor's does.

## 2026-11-24 — next2's Bluetooth UART with its RTS

- `rk-bluetooth` adds the vendor Bluetooth node's pin state, its RTS, to the UART's `pinctrl-0`;
  next2's H4 driver turns on flow control, which had no RTS pin. Trees changed: the HK1, the R69-1
  and the H96 Max RK3528, one line each; the 3518s' and the M2 Plus's vendor node is disabled.
- On 7.3.5, the HK1 and the R69-1: GPIO3 A2 (pin 98) `MUX UNCLAIMED` before, `ffa00000.serial`,
  group `uart2m0-rtsn` after; `hci0` powered, a 60 s scan finding 33 and 39 devices.
- Idle on the R69-1, 20 s, nothing running: vendor 6.1 spends 93% at 1200 MHz; next2 7.3.5 100% at
  1416, under `ondemand` and `schedutil` both. Neither has a cpuidle driver: the factory gives CPU0
  and CPU1 the disabled `cpu-sleep0`, which `cpuidle-psci` cannot register, and the vendor binds
  none either.
- The PVTM bin decides it, and this chip sits on the bin 4/5 line (1544/1545): 6.1 read 1541 (bin 4)
  and 1557 (bin 5) on two boots, next2 1554 to 1556 (bin 5). On bin 4, 1200 MHz costs the energy
  model 168603 against 1416's 173129 and is used; on bin 5, 1648 against 1646, so 1200 is marked
  inefficient and skipped, on either kernel. Next2's measurement and table match the vendor's.
- DDR on the R69-1: next2 decodes 300 frames of 4K60 HEVC in 3.57 s (84.1 fps) at 780 MHz under
  `performance`. `simple_ondemand` hung the box within seconds, watchdog reset. One step at a time
  under `userspace`: 780 → 528 MHz holds; 528 → 324 hangs. Vendor 6.1, same box, steps 780 → 528 →
  324 → 780 and stays up; its default governor is `dmc_ondemand`, not `performance`.
- One next2 boot hung within a minute at idle, before any DDR change, with nothing logged; the next
  idled 5 minutes clean. Not reproduced.
- The first DDR change after boot always holds, up or down (780 → 528, 780 → 324); the second always
  hangs (528 → 324, 324 → 780). The first took 6 ms and the completion IRQ (GIC 49) never fired:
  `set_rate` compared `(long)res.a1` with `-6`, and BL31's 32-bit `-6` reads `0xfffffffa` as a long,
  so "pending" was never seen, no `POST_SET_RATE` was sent, and the firmware was left mid-change.
  The vendor compares `(int)res.a1`; `devfreq-rk3528-dmc.patch` now does.
- On next2 7.3.6 with the cast corrected: six spaced changes in a row hold, all three rates, 5–7 ms
  each, the completion IRQ never raised, so the firmware never answered "pending" and the cast was
  not what the 7.3.5 build lacked. `simple_ondemand` under the 4K60 decode still hangs the SoC, with
  nothing in pstore. The vendor scales by system status (`dmc_ondemand`), not by polled load.
- Decode against FFmpeg's software, R69-1, next2 7.3.6: H.264 4:2:2 (High 4:2:2) and 4:0:0
  (`chroma_format_idc` 0), 10 frames each, bit-exact in every plane, `rkvdec` 10 interrupts each.
  JPEG on `ff870000.video-codec`: 4:0:0, 4:2:0 and 4:1:1 at 77–78 dB luma, 8176×8176 at 78 dB,
  8192×8192 at 80 dB; 4:2:2, 4:4:0 and 4:4:4 fail `capture: driver decode error` with no interrupt.
- `rkjpegd` converts every colour JPEG to NV12 in the hardware (`YUV_OUT_FMT_NV12`). Against
  FFmpeg's decode subsampled the same way, nearest-neighbour: 4:1:1, 4:2:2 and 4:4:4 (libjpeg's) at
  77 dB luma, 44/43 dB chroma; 4:2:0 at 78/75/76 dB. `v4l2_jpeg_parse_header` refuses 4:4:0 and
  FFmpeg's 4:2:2 (luma 2x2, chroma 1x2), `-22`, so those decode in software.
- Encode ladder, R69-1, next2 7.3.6: H.264 passes to 8192x8192 (48 dB luma), HEVC to 4096x2304, and
  HEVC 4096x4096 is refused by the driver's 5120x2880 cap. The 8192x8192 H.264 that failed before
  was the OOM killer: FFmpeg queues 16 raw frames, 1.6 GB, on a box with 1.5 GB. `video.py` now
  gives a V4L2 encoder a queue of 4.
- 10-bit encode input: the VEPU540C takes none. MPP's `vepu5xx_yuv_cfg` maps every 10-bit format to
  `VEPU5xx_FMT_BUTT`. Its `src_cfmt` does take BGRA8888, BGR888, BGR565, YUYV, UYVY, 4:0:0, and
  4:2:0, 4:2:2 and 4:4:4 planar and semi-planar; next2's `rkvenc` offers NV12 and NM12 only
  (`v4l2-ctl --list-formats-out`, R69-1).
- MPEG-4 VOP with `vop_time_increment_resolution` 0, sent by a raw request-API client (FFmpeg's
  parser rejects it first), R69-1, next2 7.3.6: both buffers come back `ERROR`, no VDPU2 interrupt,
  and an MPEG-4 decode after it matches software at 71 dB. The request itself never completed: the
  refusal returned after `hantro_start_prepare_run` without `hantro_end_prepare_run`, leaving its
  controls pending. With the patch completing it before refusing, the request completes, both
  buffers `ERROR`, and the decode after still matches at 71 dB; AIC8800 Wi-Fi up on the rebuilt
  modules.
- rkvenc's WARN on a failed `start_streaming` (`videobuf2-core.c`, `done_list` not empty), R69-1,
  next2 7.3.6: tripped by an H.264 encode at 32x64, which the driver refuses; 16384x8640 is now
  refused at `S_FMT` and never reaches it. In separate header mode, `buf_queue` completed a CAPTURE
  buffer with the parameter sets while vb2 queued the waiting buffers ahead of `start_streaming`.
  `media-rkvenc-header-after-start.patch` hands them out after a successful `start_streaming`: two
  refusals log no WARN, and the H.264, HEVC and MJPEG ladder passes as before.
- `video.py`'s encode ladder had never timed H.264 or HEVC here: in separate header mode the
  parameter sets come out as a packet of their own, 61 for 60 frames, and the timing wanted an exact
  count. With that packet allowed, R69-1, next2 7.3.6: H.264 134 fps at 720p, 60.5 at 1080p, 17 at
  2160p; HEVC 157, 72 and 20. Past a size too slow to play, the ladder now climbs on untimed to the
  size limit, and a pass with no rate counts as neither playable nor faster than the CPU.
- Size caps measured past 1920x1088, R69-1, next2 7.3.6 with the caps lifted to 4096x2304 in a
  throwaway build. VDPU2: MPEG-1, MPEG-2, MPEG-4 and VP8 decode at 5–20 dB past 8160 macroblocks
  (2560x1440, 3840x2160, 2048x2048, 1920x1200, 1600x1600, 1920x1920, 1920x2160), with interrupts and
  no faults; 1080x1920, the same 8160 macroblocks, decodes right (MPEG-2 72.7 dB, VP8 bit-exact).
  The hardware's limit is the area, not each side. VDPP: 3840x2160 page-faults `ff860800.iommu` at
  iova 0, its `FORCE_RESET` times out, and VDPP and IEP2 then output nothing until a reboot. Both
  caps stay. IEP2 was not tried: its 1920x1088 already takes 1080i, the largest interlaced picture.
- VDPP at 1:1, 1920x1080 and 1920x1088 NV12, four runs each: output identical to the input. An
  earlier run scoring 29.8 dB on alternate runs, and 2560x1440 at 5.8 dB, came from a script whose
  FFmpeg read the script itself from stdin (`sh -s` without `-nostdin`).
- OTP `opp-info` (CPU 0x32, GPU 0x38, DMC 0x3e, 6 bytes each, from the factory tree's cells), read
  from `/sys/bus/nvmem/devices/rockchip-otp0/nvmem`: all zero on the R69-1, the H96 Max 3518D and
  the M2 Plus.
- DDR rate changes, R69-1, one test a boot, each step logged and synced first. next2 7.3.6: ten
  steps 1 s apart under a 4K60 HEVC decode hold; 324 MHz held 60 s holds; `simple_ondemand` polling
  the DFI, pinned at 780 or at 324 MHz for 60 s, holds; steps 0.5 s apart hang the SoC within eight,
  with cpufreq pinned too; `simple_ondemand` over all three rates hangs within seconds of its first
  change. Vendor 6.1, `userspace` governor: one run took steps 0.5 s, 0.2, 0.1, 0.05 s apart and
  back to back; a second hung in the 50 ms round. Changes close together hang the firmware or the
  controller on both kernels. The vendor tree scales by system status only
  (`auto-freq-en = <0x00>`), never by load; next2's default `performance` never changes the rate.
- The vendor never changes the DDR rate in use: its tree gives `dmc_ondemand` one status rate,
  `NORMAL`, and no load scaling (`auto-freq-en = <0x00>`). The M2 Plus on vendor 6.1 after 8 h 56
  min: `trans_stat` 0 transitions, 786 MHz throughout, `system_status` 0x801. next2's `performance`
  holds the top rate the same way; nothing more to port.
- Crypto: the RK3528's block is Rockchip's `crypto-v4` (`crypto@ffc40000`); mainline's
  `rk3288_crypto` takes only the RK3288, RK3328 and RK3399 blocks. The A53s carry
  `aes pmull sha1 sha2`, and vendor 6.1 serves AES and SHA-256 from them (`*-ce` drivers), not the
  block.
- Plane rotation by writeback (`display.py`'s new `rotation` check), R69-1, next2 7.3.6: the Esmart
  planes offer `reflect-y` and mirror right; Cluster0 offers `reflect-x` and `reflect-y`, took both
  on a linear buffer and showed it unmirrored, its mirror bits being the AFBC decoder's
  `ROTATE_MODE`. `drm-rockchip-vop2-cluster-mirror-afbc-only.patch` refuses them on a linear buffer:
  both refused, every other transform as before. A reflection is sent with `rotate-0`, as DRM wants
  one rotate bit.
- HDMI audio plug state on next2: `hdmi-codec` reports no jack unless the card hands it one, and
  `simple-card` made jacks for aux devices only. With `asoc-hdmi-codec-jack-type.patch` and
  `asoc-simple-card-link-jacks.patch`, R69-1, next2 7.3.6: card `rockchip,hdmi` has
  `hdmi-audio-codec.4.auto-jack Jack` and the input device
  `rockchip,hdmi hdmi-audio-codec.4.auto-jack`; with no screen it reads off. A forced connector runs
  no detection, so `dw-hdmi` never reports a plug through it: the on state needs a screen on a next2
  box.
- VDPP fault recovery, throwaway build with VDPP's cap at 4096x2304 and a job watchdog, R69-1:
  3840x2160 finished, garbage, no fault; 4096x2304 ended in an error interrupt
  (`job failed, status 0x20`), the soft reset reported done, yet `ff860800.iommu` went on faulting
  (333 lines) and its `FORCE_RESET` and stall requests timed out; every job after wrote nothing. The
  watchdog never fired, so it was not kept. Recovery needs the IOMMU reset with the engine's, as
  MPP's `mpp_iommu_refresh` does; the cap refuses the only trigger known.
- Rotation on vendor 6.1, R69-1: Cluster0 offers `reflect-x`, `reflect-y`, `rotate-90` and
  `rotate-270`; on a linear buffer `reflect-y` shows right, the other three are refused. The vendor
  writes a linear buffer's vertical mirror to `CLUSTER_WIN_CTRL0` bit 21 and an AFBC one's to
  `AFBCD_ROTATE_MODE`; mainline writes only the latter, so next2 refuses both reflections there.
- Integration coverage for this round, run on the R69-1: `video.py` decodes H.264 4:2:2 (bit-exact)
  and 4:0:0 (55 dB, x264's full range taking another swscale path), JPEG 4:0:0, 4:1:1, 4:2:2 and
  4:4:4 from `cjpeg` (78–79 dB); its `refusal` suite (the zero-resolution VOP, H.264 at 32x64) and
  `convert` suite (VDPP and RGA: 1:1 exact, scales 45–51 dB) pass. `box.py`'s `ddr.governor`,
  `ddr.transitions` and `audio.<card>.hdmi-jack` read `performance`, 0, `off disconnected` on next2
  and `dmc_ondemand`, 0, `off disconnected` on vendor; `display.py`'s `rotation` passes on both.
- Composite on next2: `display.py composite` sets PAL and NTSC but the writeback is black, as in the
  2026-11-22 regression on the 3518 and 3518D; it broke when the cursor plane took Esmart2 and left
  VP1 Esmart3. Esmart3 written into VP1's mixer slot 1 (`0xff1f`) instead of slot 0, a throwaway
  build on the R69-1: still black, so the slot is not the cause.
- The R69-1 left unbootable: an edit of `/boot/extlinux/extlinux.conf` through an `awk` program that
  failed to parse truncated the menu before a reboot. Its copy is at `/var/tmp/extlinux.before` on
  the eMMC root; the way back is a TVBian SD card, the SPL taking the card's U-Boot first.
- Line buffer split `02` on the RK3528, measured: with every Esmart registered, Esmart0, Esmart1 and
  Esmart2 each scan out their fill by writeback on HDMI, and Esmart3 on composite stays black; split
  `03` (2K each) shows composite through Esmart3. The vendor's generic table, which has split 2 drop
  Esmart1, is wrong for this chip; vendor 6.1 shows composite in `02` through Esmart2. The lb-mode
  patch now registers Esmart0, 1 and 2 in `02`, and the cursor patch gives VP1 Esmart2 as its
  primary there, Esmart1 HDMI's cursor. Composite through Esmart2 is untested on this kernel: the
  boxes with an AV jack were down, offline or another session's.
- Composite cable detection in the vendor's code: the kernel's TVE driver and Rockchip's U-Boot
  (`rockchip_tve.c`, next-dev) both report the connector connected always. The kernel header names
  `VDAC_CABLE_CTRL` (`0x288`) for the RK3528 without fields; the RK322x VDAC's bits at that offset
  are `CAB_EN` (5), `CAB_REF` (4), `CAB_FLAG` (0), and the only use clears `CAB_EN`. The datasheet
  lists cable detection; which bit follows a cable needs one plugged and unplugged. Our
  `drm-rockchip-tve-unknown-connector.patch` stays, its message corrected: the VDAC can sense, the
  driver does not.
- JPEG decode in the hardware's own layout, `media-rkjpegd-native-422-444.patch` and FFmpeg `0053`,
  the 3518D on next2 7.3.6: the decoder lists `NV16` and `NV24`; 4:2:2 decodes at 74.6 dB chroma
  (42.4 as NV12), 4:4:4 at 76.6 (39.5); the 4:2:0 ladder to 8192x8192 and 4:0:0 unchanged; 4:1:1
  stays NV12 at 34 dB, V4L2 having no 4:1:1 format. `video.py` now holds a lossy decode's chroma to
  30 dB as well as its luma to 50: no pass among the 997 recorded falls under it.
- RGA on next2, the 3518D: `horizontal_flip` gave a vertical flip and `vertical_flip` a horizontal
  one, exact against FFmpeg's `vflip` and `hflip`; mainline sets `MIRR_MODE_X`, which mirrors left
  to right, for VFLIP. `media-rga-mirror-axes.patch` swaps them. Then `video.py`'s `convert` suite,
  now a table: the RGA's copy, flips and 90/180/270 rotations byte-exact against FFmpeg (V4L2's
  rotation clockwise), NV12 to XRGB at 57.6 dB of FFmpeg's BT.601 limited range, scales at 39.2 and
  39.6 dB of bicubic; VDPP's copy exact, scales 43.2 and 46.6 dB; both refusals pass.
- HDMI on next2, the 3518D, a synthetic screen, read from `dw-hdmi`'s registers: at 1080p60 and at
  4K60, max bpc 8 or 10, SDR or PQ, `TX_INVID0` `0x01` (RGB, 8-bit) and `VP_PR_CD` `0x40` (24-bit);
  4K60 at 594 MHz. HDR goes out as 8-bit RGB with EC 0: the connector has no `Colorspace`. Mainline
  `dw-hdmi`, the only bridge after Rockchip's encoder, offers `MEDIA_BUS_FMT_FIXED`, which the glue
  takes as RGB888: no deep colour and no YCbCr whatever the sink lists.
- The H96 Max 3518 left unbootable: next2 7.3.6 (the HDMI bus format, VP0's four layers, split
  `02`'s plane roles) installed and made its default, to be put back once it answered; it never did,
  and ARP shows it off the network. The 3518D boots the same kernel; the 3518's difference is VP1
  driving composite, which this kernel changed. Its menu is at `/var/tmp/extlinux.safe`.
- `tools/validate/boot_once.py`, the 3518D: next2 7.3.6 booted once; its initramfs restored the menu
  2.99 s in (`tvb-boot-once: the menu before restored`), the default back on 6.1. BusyBox's remount
  needs the device named: without `$ROOT` it left the root read-only and the menu on next2.
- HDMI bus format on next2, the 3518D, `drm-bridge-dw-hdmi-select-bus-format.patch` and
  `drm-rockchip-dw-hdmi-rk3528-deep-colour.patch`: `display.py`'s new `deep colour` check on a
  synthetic screen that takes 4:2:0 (`hdr_edid(y420=True)`): 1080p60 at max bpc 10 sends 10-bit RGB
  (`TX_INVID0` `0x03`, `VP_PR_CD` `0x50`), 4K60 10-bit YCbCr 4:2:0 (`0x0b`, AVI 4:2:0) at the PHY's
  594 MHz in, 371.25 MHz TMDS out; max bpc 8 unchanged. The PHY's rate is doubled for pixel
  repetition: without it 576i50 and 480i60 were refused. VP0 takes the datasheet's four layers, so
  four planes compose at once. The full `display.py` then 27 passed, 0 failed; one run in three
  failed Cluster0's `rotate-0` with the frame plane 47 had shown before: a stale writeback.
- HDMI `Colorspace`, `drm-bridge-dw-hdmi-colorspace.patch`, the 3518D on next2 7.3.6: the property
  attached beside `HDR_OUTPUT_METADATA`, the AVI InfoFrame's colorimetry from it. `display.py` hdmi,
  judged now the property exists: PQ and HLG at max bpc 8 and 10 send EC 6 (BT.2020), SDR EC 0. The
  full `display.py` 27 passed, 0 failed.
- HDMI 8-channel PCM on next2, the 3518D, `asoc-rockchip-sai-tdm-lanes.patch` and SAI3's
  `rockchip,sai-tx-route = <0 1 2 3>` folded into `arm64-dts-rk3528-media-display.patch`. Before:
  the screen attached sends no ELD, so the codec offered 2 channels; under a synthetic 7.1 screen
  (`hdr_edid(surround=True)`) dw-hdmi took 8 (`AUD_CONF0` 0x2f, `FC_AUDICONF0` 0x70, allocation
  0x13) but the SAI refused: `Mismatch mclk: 6144000, at least 12288000`, its TDM putting every
  channel on its one lane. The ELD reaches the codec only while the output is lit (`curr_conn`).
  After: SAI `TXCR` 4 lanes of two 32-bit slots, a 64-bit frame; `display.py`'s new `hdmi audio`
  passes 2, 6 and 8 channels at 48 kHz and 8 at 192 kHz, 3.01–3.08 s for 3 s, lanes 0x1/0x7/0xf.
  Vendor 6.1 on the same box: the same four lines.
- HDMI YCbCr 4:4:4 and 4:2:2 on next2, the 3518D, `drm-bridge-dw-hdmi-color-format.patch`: dw-hdmi
  attaches the core `color format` property and offers 4:4:4 and 4:2:2 only when asked, so AUTO
  stays RGB then 4:2:0; 4:2:2 takes 4:4:4 from the VOP and dw-hdmi decimates it, as the vendor does.
  10-bit 4:2:2 at 4K60 was refused alone: the glue took the TMDS rate from the VOP's 10-bit 4:4:4,
  742.5 MHz; the rate now comes from the bridge's output, folded into
  `drm-rockchip-dw-hdmi-rk3528-deep-colour.patch`. `display.py`'s `color format` 7 of 7.
- Writeback's stale frame (1 full `display.py` in 3, Cluster0 `rotate-0` showing the frame before):
  a commit landing between a frame start and its interrupt latched a frame late, and the job's stop
  went with its start, so it completed with nothing written. The stop now waits for the job's second
  frame start, `drm-rk3528-vop2-writeback.patch`; the vendor counts frame starts as before, the
  RK3528 having no `WB_COMPLETE` in its interrupt table. 10 rotation sweeps 70 of 70; full
  `display.py` 36/1 (the audio line below) and 37/0.
- HDMI 8 channels at 192 kHz: one underrun in 15 runs, inside a full `display.py`, with
  `rockchip-sai ffb70000.sai: TX FIFO Underrun` and `dma-pl330: Runtime PM usage count underflow!`;
  10 of 10 alone.
- `video.py` conceal on next2, the 3518D: a 1080p clip of each codec with 4096 bytes zeroed
  mid-stream; every codec decodes as many frames as FFmpeg's software decoder, the log quiet. The
  10-bit codecs first read 0 frames: the suite downloaded frames this engine only counts.
- `probe.py` on the 3518D, next2 7.3.6 against vendor 6.1.172: vendor takes AFBC rotate-90/270 and
  both mirrors on Cluster0, next2 the mirrors only; vendor has `Content Protection` and
  `GAMMA_LUT`/`ACM_LUT_DATA`/`HDR_EXT_DATA`, next2 none; next2 has `color format`; both take
  4096x2160@60 and refuse 4096x2304@60; neither registers a crypto engine; the vendor's video is
  MPP's (`VDPU2 RKVDEC AVSPLUS_DEC RKJPEGD RKVENC IEP2 VDPP`), next2's V4L2's, rkvenc taking NV12
  only, VDPP NV12 to NV12, JPEG answering no crop selection.
- VP0 gamma LUT on next2, the 3518D: `dt-bindings-rk3528-vop-gamma-lut.patch`,
  `arm64-dts-rk3528-vop-gamma-lut.patch` (the vendor tree's window at `0xff845000`, 4 KiB) and
  `drm-rockchip-vop2-rk3528-gamma-lut.patch` (1024 entries, VP0 only; the vendor loads it as the
  RK3588's). `GAMMA_LUT` attached; after an inversion commit the window reads `0x3fffffff` at 0, `0`
  at 1023. The writeback shows no table, inversion or square, on next2 and on vendor 6.1 alike: it
  is taken before gamma. Mainline's gamma port select wrote all of `LUT_PORT_SEL`, `0x8000000` to
  `0`: the Esmart line-buffer split (bits 27:26) back to mode 0 on every gamma commit;
  `drm-rockchip-vop2-lut-port-sel-fields.patch` updates the port's field alone, the split read
  `0x8000000` before and after. `display.py` runs gamma first now: full run 37 passed, 0 failed.
- Cluster0 AFBC rotate-90/270 on next2, the 3518D, `drm-rockchip-vop2-rk3528-cluster-rotate.patch`.
  `display.py`'s rotation now also shows a 256x256 AFBC quadrant buffer, written as uncompressed
  sub-blocks (size code 1, the bytes in linear XRGB8888's order): no encoder needed. Offered as the
  vendor offers it, rotate-90 showed the clockwise picture and rotate-270 the anticlockwise one, on
  next2 and on vendor 6.1 alike: the decoder's 90-degree bit turns clockwise, DRM's 90
  anticlockwise. The RK3528's bits are now swapped, the transform offset following the hardware's
  turn. A linear buffer rotated was taken and scanned out as garbage; refused now, as the vendor
  refuses it. Rotation 12 passed, 0 failed: AFBC rotate-0, both reflections, rotate-90 and
  rotate-270 exact. Cropped to 240 lines, not whole superblocks, the five pass too: 17 passed, 0
  failed; by quadrant centres, which a shift of a few lines would not move.
- rkvenc source formats on next2, the 3518D, `media-rkvenc-rk3528-source-formats.patch` and FFmpeg
  `0054`. The VEPU540C takes MPP's layouts: a format code, a red/blue or U/V swap and an alpha swap,
  strides in bytes, three plane addresses; RGB through nine weights and three offsets. Measured
  against MPP's names: the 24-bit "BGR888" code reads R, G, B unswapped, so RGB24 takes no swap and
  BGR24 the swap (its picture showed red and blue exchanged). Grey codes 4:0:0 with a 4:2:0 SPS,
  which FFmpeg's decoder rejects ("left block unavailable"): not offered. FFmpeg mapped its 32-bit
  RGB to V4L2's ambiguous BGR32 and RGB32, and had no NV21: "Encoder requires nv12 pixel format";
  mapped now. An RGB-sourced stream read 28.6 dB, its samples limited range under FFmpeg's
  full-range tag; the SPS's VUI now says limited, BT.601 (ffprobe `tv`, `smpte170m`, H.264 and
  HEVC), JPEG takes full-range weights. `video.py` input: NV12, NV21, YUV420P, YUYV, UYVY 47.3 dB;
  NV16, YUV422P 39.9; the four 32-bit orders and both 24-bit 35.1–35.2; RGB565 45.9; HEVC and JPEG
  from BGR0 35.2, 35.3. The encode suite holds a chroma floor now too: every case passes.
- VDPP formats on next2, the 3518D, `media-rockchip-vdpp-formats.patch`: NV12 and NV21 in, those and
  NV24, NV42 out, the scaler's chroma at full size and its output format 6 for 4:4:4, as MPP's VDPP
  v1 sets them. MPP forces a 4:2:0 source ("vep only support yuv420"), so 4:2:2 is not offered.
  `video.py` convert: NV21 copy and NV21 to NV12 exact; NV24 and NV42 at 1:1 43.0 dB against
  FFmpeg's bicubic chroma; the scales 43.2 and 46.6 as before.
- VC-1 and JPEG ROI, read in the vendor's code: MPP has no VC-1 decoder (no `vc1` under `codec/dec`
  or `hal`), so no Rockchip code drives VC-1 on the VDPU2; MPP's rkjpegd registers
  (`hal_jpegd_rkv_reg.h`) have a scale-down mode but no ROI position. Both stay open, the reason
  recorded.
- H.264 4:0:0 on next2, the 3518D: decoded into NV12, the VDPU381 writing luma alone, chroma left as
  memory held it (`video.py` decode `h264gray` U/V 6 dB). MPP sizes a 4:0:0 picture by its luma, so
  the decoder writes no chroma: `media-rkvdec-h264-grey.patch` offers GREY for such a stream, FFmpeg
  `0055` maps it to GRAY8 over R8. `h264gray` exact at 1080p and 2160p, 274 fps.
- HEVC past 8K, measured with clips made for it: 8192x4320, 8256x4320, 8192x8256, 10240 to 16384
  wide at 1088, 16384x2160 all decode exact; 16384x8640 and 8192x16384 stop at
  `rkvdec: dma alloc of size 268435456 failed`, 8192x8192 10-bit one time in two: the 2 GB box's
  memory, not the decoder. `video.py`'s estimate charged 10-bit twice and held 8 frames: now 5/4, 12
  frames and 512 MB beside them, so those sizes are skipped past the box's memory, not called
  broken.
- Esmart regions as planes, the 3518D on next2, `research/esmart-regions`: regions 1 to 3 of each
  Esmart as planes, each region's registers 0x30 on from the one before, the window's CSC, mirror,
  colour key and bus fields left to the window. Measured by writeback: a window and its three
  regions in four strips exact; a region after a gap, or sharing a line with the one before, stays
  dark, so the patch refuses both, and a region alone, above the one before or at another zpos. 18
  passed. Kept out of the kernel: the vendor's sub-windows reached writeback but showed black on
  HDMI (the 3518D's `dtb.md`), and writeback here precedes stages HDMI passes through; the whole
  `display.py` with it failed `planes`'s no-sub-window rule and `planes-all` on 13 planes.
- Crypto engine on next2, the 3518D: Dawid Olesinski's RK3568/RK3588 driver (v3, 2026-08-16, from
  Corentin Labbe's), carried; the vendor's v3 driver, which takes the RK3528's `crypto-v4`, is the
  same v2 register map with version registers. The RK3528's: AES `0x3717ff`, every mode and key
  size; hash `0x100187`, SHA-1, SHA-224, SHA-256, MD5, SM3, no SHA-384 or SHA-512. Registered whole,
  SHA-512 timed out on its DMA and SHA-224 beside it failed; `crypto-rockchip-rk3528.patch`
  registers what the flags name. Kernel self-tests on, all 8 pass (`box.py` `crypto.selftests`, its
  engine pattern now matching `-rk2` drivers). AF_ALG here binds by algorithm name only, and the
  engine ties the CPU's crypto extensions at priority 300.
- Cluster0's Y mirror on a linear buffer, next2, the 3518D: mainline's RK3576-style table, the
  RK3528's, takes Y mirror from the AFBC decoder's rotate mode, which a linear buffer ignores; the
  vendor sets the window's `CTRL0` bit 21 for a linear buffer and the decoder's bit for AFBC. Moving
  YMIRROR to `CTRL0` alone mirrored linear but left AFBC unmirrored, so both are written, each for
  its buffer: `drm-rockchip-vop2-cluster-linear-ymirror.patch`. `display.py` 42 passed, 0 failed:
  linear `reflect-y` and AFBC `reflect-x`/`reflect-y` by writeback; linear `reflect-x` refused, the
  vendor's RK3528 window having no field for it.
- VDPP DMSR on next2, the 3518D: MPP enables it by default with fixed parameters; its 21 registers
  at `0x80`, from MPP's own `set_dmsr_to_vdpp_reg()` compiled on the host, and `CONFIG0` bit 24, as
  `V4L2_CID_SHARPNESS`, off by default: `media-rockchip-vdpp-dmsr.patch`. It smooths edges: 1:1,
  54.2 dB luma of the plain scaler, edge energy 1.60 to 1.49; up 1280x720 to 1080p 43.0 dB of
  FFmpeg's bicubic, 43.2 without; down, 64.9 dB of off. `video.py` convert `dmsr`, `dmsr-up`.
- VDPP 4:2:2 in, the 3518D: an experiment offered NV16 with format code 1, then 2: both identical,
  luma exact, chroma 25/19 dB of FFmpeg's, the engine reading 4:2:0. MPP's VDPP v1: "vep only
  support yuv420"; the datasheet's 4:2:2 is likely the IEP2's. Output untried: no code to try.
- A 3518D reset during that experiment's script, on next2: not reproduced by any of its steps run
  one at a time (DMSR down, NV16 by either code), the box up after each; the previous boot's journal
  was in RAM, the ramoops record an old one. Unexplained.
- HDMI 3D frame packing back in, the owner's word: `display.py` stereo passes 5 modes on the 3518D
  and the M2 Plus, 1080p24 and 720p60/50, active lines twice the picture plus the gap, the vendor
  InfoFrame's payload `(0x40, 0x00)`.
- Esmart regions in next2's patch list, the owner's word that HDMI's black was the vendor kernel's:
  `drm-rockchip-vop2-rk3528-esmart-regions.patch`, from `research/`. `display.py`: region planes
  kept out of every check but `regions`; `compose()` turns them off with the rest and resets each
  plane's rotation, which `rotation` left mirrored, refused beside an unrotated region. 3518D 64/0,
  M2 Plus 62/0; the no-sub-window rule dropped.
- `video.py` memory: a case past the box's memory is its own verdict, `memory` (💾), its reason in
  the report, never a fail. The M2 Plus (4 GB) decodes every 8192x8192 case, 10-bit included;
  16384x8640 10-bit reads "needs 3037 MB, 3399 MB free".
- IR on next2: mainline has no Rockchip PWM-capture IR driver; the translator gives the vendor's
  `rockchip,remotectl-pwm` as `gpio-ir-receiver` on the same pin, the board's keymap. The M2 Plus
  registers `rc0`, `gpio_ir_recv`, NEC; a key press waits on a person. `probe.py` counted CEC's rc
  device as an IR receiver, the 3518D's only one: now an rc device offering only `[cec]` is not.
- S/PDIF to HDMI: the six RK3528 factory trees here each give HDMI's sound card `sai3` as its CPU
  DAI; `spdif_8ch` drives its GPIO pins alone. No board wires the second input: ➖.
- Analog codec rates on next2, the M2 Plus: the SAI and the codec offered `SNDRV_PCM_RATE_8000_*`,
  which leaves out 12 and 24 kHz; `asoc-rockchip-sai-12k-24k.patch` and
  `asoc-rk3528-codec-12k-24k.patch` add them. `box.py` audio now plays every rate a card offers: a 3
  s play took 3.14 s at 11.025 and 22.05 kHz, a constant 0.125 s, the last period of 1378 frames
  padded (6 s took 6.135); the line is now a 3 s play less a 1 s one, 2.000 s at every rate on the
  codec, S/PDIF and HDMI, 11.025 kHz 1.990. 176.4 and 192 kHz run in time; heard, unknown.
- HDMI 8 channels at 192 kHz, the underrun seen 1 run in 15 on an earlier next2 build: not
  reproduced on the current one, 0 of 80 on the M2 Plus (40 with the dw-hdmi register dump
  `display.py` reads mid-stream) and 0 of 60 on the 3518D, against a synthetic 7.1 screen. Which
  change since cured it is not known; `display.py` hdmi audio keeps watching for it.
- Bluetooth PCM on SAI0: the six RK3528 factory trees here each disable the Bluetooth sound card and
  its `delta,dfbmcs320` codec; SAI0 is on in three, with no card on it. No board wires it: ➖.
- SAI0 and SAI1 on next2: mainline's dtsi had neither; `arm64-dts-rk3528-sai0-sai1.patch` adds both,
  no pins, each board giving its mux. The translator's `radio-pcm` rule now also turns SAI0 on where
  the vendor does, the 3518D, the M2 Plus and the H96 Max 3518, its pins still held by the SDIO
  power sequence so the radio initialises. On the M2 Plus and the 3518D: `rockchip-sai` bound to
  `ffb80000.sai`, no pin conflict, Wi-Fi associated and `hci0` up.
- VP0's ACM: the vendor drives it through its own `ACM_LUT_DATA` blob property, hue, saturation and
  luma gain tables after blending; mainline has no post-blend colour interface to carry it and
  nothing here would set it: ➖, as AVS. The RK3528's overlay HDR differs: one window through the
  HDR engine, mixed with the rest before writeback, which 7.3's per-plane colorop API can express.
- Overlay HDR, the plan: the RK3528's engine takes every parameter from a userspace blob, its
  `hdrvivid_regs`, which on stock Rockchip's closed display library computes. Its SDR-to-HDR half is
  known here: `display.py`'s `rk_sdr2hdr()` builds it for PQ and HLG, passing by writeback on the
  vendor kernel. 7.3's per-plane colorop API has its terms, gamma 2.2, a 3x4 matrix, a multiplier
  and the inverse PQ curve: SDR planes on a PQ screen first. HDR to SDR, the tone-mapping half, has
  no known parameters.
- SDR to PQ, the design: on VP0's planes a colorop pipeline, gamma 2.2 curve, 3x4 matrix,
  multiplier, PQ_125 inverse EOTF, the engine's order; taken whole or bypassed whole, alike on every
  plane using it, the stage being shared. The matrix fills `SDR_CSC_COE*` (Q13, no offsets); the
  multiplier `m` sets SDR white at 80·m nits, `SDR_CFG_COE0`'s term −log10(8m)·1020; the rest are
  `display.py` `rk_sdr2hdr()`'s constants: `SDR2HDR_CTRL` 0x2, `SDR_CFG_COE1` 4913, `HDRVIVID_CTRL`
  0x203, the inverse-gamma curve (69 words), its start and change indices (6 each) and 64 unit
  gains, at `0x2010`–`0x2900`; `OVL_CTRL` bit 5 the path, VP0's background delay 21 more. Checked by
  writeback against `sdr_to_hdr()`.
- SDR to PQ on next2, the 3518D: `drm-rockchip-vop2-rk3528-sdr2hdr-colorop.patch`, each plane's
  color pipeline "SDR to PQ", gamma 2.2, 3x4 matrix, multiplier, PQ 125 inverse EOTF, programming
  VP0's SDR-to-HDR stage, `OVL_CTRL` bit 5, the background delay 21 more. `display.py` sdr2pq: 7
  colours by writeback within 1 code of `sdr_to_hdr("PQ")` at 203 nits; part bypassed, a negative
  coefficient and two planes' whites apart refused, two alike taken; the suite 69/0. SDR to HLG: the
  engine does it, DRM's colorops name no HLG curve.
- SDR to PQ on the M2 Plus: `display.py` sdr2pq the same, 7 colours within 1 code, the refusals and
  the shared pipeline as on the 3518D; the suite 67/0.
- HDR video under SDR planes on PQ, the vendor's way: the bottom window is the HDR layer, out of the
  layer mixer (alpha from the second layer on) and through the HDR engine in bypass, `OVL_CTRL` bit
  4 and `HDRVIVID_CTRL` bypass; the SDR mix, through SDR to HDR, blends over it in the HDR mixer,
  alpha at `0x660`–`0x66C`. The HDR window waits the SDR path's lead, about 26 cycles
  (`hdrvivid_dly` in bypass 1 against `sdr2hdr_dly` 21 and the layer mix), the SDR windows none, the
  background 37. Next: a plane left bypassed at the bottom while the rest ask SDR to PQ, by
  writeback.
- The HDR layer under SDR planes on PQ, tried on the 3518D: the bottom plane routed through the HDR
  engine (`OVL_CTRL` bit 4, its alpha to the HDR mixer, 26 cycles' delay) with `HDRVIVID_CTRL`
  `0x236`, `0x237`, `0x234` or `0x34`: the bypassed plane read (151, 245, 255) for (40, 120, 200)
  and the converted one (240, 255, 243) for (111, 125, 82); with `0x203` the two swapped and the top
  black. In "bypass" the engine still applies tables, its PQ gamma and a tone table by DMA, that
  only Rockchip's closed userspace sets, and no program here feeds the vendor kernel's
  `HDR_EXT_DATA` to read them from. Dropped; SDR to PQ alone stays.
- VDPP 4:2:2 out, the 3518D: an experiment set the output code to 1, then 2, the ZME's output to 5
  and its chroma to half width, full height, into an NV24-sized buffer: each job failed, status
  `0x20`, nothing written; the code-0 control exact (luma 0.00, chroma 0.39 of FFmpeg's NV24). The
  VDPP took three NV12 copies after, byte-exact. The RK3528's VDPP writes 4:2:0 or 4:4:4 alone; the
  datasheet's 4:2:2 is likely the IEP2's.
- The crypto engine's hashes failing their self-tests now and then, next2 on the 3518: each a "Hash
  result not valid", `HASH_VALID` not set within 1 ms of the DMA's end; a different set each boot (3
  boots: 2, 0 and 4 errors). The vendor's driver checks the flag only before engine v4 ("crypto < v4
  need to check hash valid"); the RK3528's reads `0x4000001`, v4. The poll now runs below v4 alone,
  in `crypto-rockchip-rk3528.patch`: three boots, all 8 algorithms pass, no hash error, taint 4096
  (out-of-tree modules) alone.
- The Seekwave's board-named firmware asked with `firmware_request_nowarn()`, `0015`: no "Direct
  firmware load" on three boots of the 3518.
- The 3518D's next2 baseline, the regression on 7.3.6 alone (2026-11-24): 3 fails, the Seekwave
  firmware names (since fixed), `firmware:optee` and `SKW_CMD_GET_STA`, the last two on the vendor
  kernels too. Untested: multichannel audio (no 7.1 screen), gamma (writeback before it), suspend
  (no RTC), `va.mpv.vaapi` (no labwc session), `va.probe.initialize` (no `va_probe`).
- The vendor's `optee` node dropped from every RK3528 board's next2 tree, a translation rule: each
  boots our U-Boot (`BOARD_UBOOT=rk3528`), whose FIT carries ATF and U-Boot alone, and the driver's
  probe answered "api uid mismatch" on 6.1, 6.12 and next2. The 3518 on next2 with it:
  `drivers.unbound` none, crypto 8 pass, no firmware failed, Wi-Fi up. The 3518's next2 regression
  before it (2026-11-24): 851 checks, its one fail this node.
- kexec for kernels under test, on the 3518D: the installed vendor 6.1.172 (built 2026-07-28) lacked
  `CONFIG_KEXEC`, its syscalls weak stubs; rebuilt from today's fragment it has both. A `kexec -l`
  of next2 7.3.6 from its menu entry, then `systemctl kexec`: no answer, not even ping, and no
  reset, for systemd stops the watchdog before a kexec unless `KExecWatchdogSec` is set.
  `base/watchdog.conf` sets it to 80 s beside `RuntimeWatchdogSec`; `tools/validate/kexec_once.py`
  loads a menu entry and refuses to jump without it. The strip's port 1 cycled the box; it has not
  answered since, cause not yet seen.
- DDR rates on next2 as Android's: `rk3528_dmc_trained_opps()` gave every rate BL31 trained, where
  Rockchip's `rockchip_dmcfreq_adjust_opp_table()` maps the factory table's enabled rows, in order,
  onto the trained rates and offers none past the last row. On the HK1 (two enabled rows) that ran
  next2 at 786 MHz, stock Android and the vendor kernels at 528, with no long verified memory run at
  786 and a dark boot 1 in 4 in the window the loader runs 786. The driver now maps as the vendor's
  does. The 3518D on next2: 324, 528, 666 MHz, at 666, as vendor 6.1; the M2 Plus: 324 to 786, at
  786, as vendor. A rate past the factory table waits on that board's own hours of verified memory
  stress at temperature.
- The GPU on next2 offers 300 MHz below the vendor's table on the 3518D (vendor 700 and 800) and
  idles there: a lower rate at the row's voltage.

## 2026-11-24 — kexec from the vendor kernel into next2

- On the 3518, vendor 6.1 into 7.3.6-next2 by `kexec_once.py`, the watchdog running at the jump
  (`Watchdog running with a hardware timeout of 1min 29s` in the old boot's journal): no answer in 4
  minutes and no watchdog reset; the strip's port 3 brought it back. The persistent journal holds no
  next2 boot: it never reached journald.
- The same jump with `rootwait=20 panic=10` added reset by itself 57 s after the kexec, back on
  vendor 6.1. next2's tree has the vendor's ramoops region and its kernel `PSTORE_RAM`, yet the
  console pstore kept after the reset is the vendor boot that jumped: next2 stopped before its
  ramoops probed. Not the root wait, then; the handoff. A vendor display still scanning out through
  its IOMMU at the jump is the next suspect. `boot_once.py` stays the way into next2.
- With the vendor's `display-subsystem` unbound before the jump, still dark past 4 minutes: not the
  display. The 3518 back by the strip's port 3.

## 2026-11-25 — next2's H.264 encode held to 7680 wide

- At 8192 wide the VEPU540C's H.264 is now and then garbage, with no error: 8192x4320 in half the
  3518D's runs at any DDR rate, 8192x8192 on the HK1 (30.25 dB) and the R69-1 (broken). Every size
  to 7680x4320 is bit-exact in every next2 run on every board. JPEG is bit-exact to 8192x8192 on all
  of them.
- `RKVENC_RK3528_MAX_WIDTH` is 7680 in `media-rkvenc-rk3528-vepu540c.patch`; the HEVC patch carried
  the old define as context and was regenerated with it. A JPEG width of its own was tried and
  dropped: the raw picture's size is clamped to the codec set at the time, H.264 by default, so JPEG
  past 7680 was refused anyway. JPEG shares the 7680.
- On the 3518D after the change: H.264 and JPEG at 8192x4320 refused; at 7680x4320, H.264 47.533 and
  JPEG 50.335 dB.

## 2026-11-25 — the M2 Plus's display suite: a run poisoning the next, and 3D's planes

- A second `display.py` run failed 11 checks, errno 22, where the first passed: `sdr2pq` left its
  plane's `COLOR_PIPELINE` set, its colorops on, and later tests commit that plane without clearing
  it. Not `screen.py`, which skipped in 3 s. `display.py` now sets every plane's pipeline to bypass
  as it opens the card; the poisoned box's next run passed as the first.
- 13 warnings at `rockchip_drm_vop2.c:1525` came from frame-packed 3D: the plane check clips to
  `drm_mode_get_hv_timing()`, both views (1470 lines at 1280x720), and the update bounded the plane
  by the mode's 720, skipping a 1080-line plane. The update now bounds it as the check does, in
  `drm-rockchip-dw-hdmi-rk3528-frame-packing.patch`: no warning in a full run, the 5 stereo modes
  pass.
- One earlier run of the pair reset the box (no pstore record, the RAM journal lost): not seen again
  in three since, with the kernel log streamed.
- Two intermittent captures, 1 in 3 runs each: AFBC reflect-y cropped, two cells misplaced; and
  Esmart0's regions all black, Esmart1's right in the same run.
- The reset found: display.py's regions check repeated 20 times on the M2 Plus ended in 258 IOMMU
  write faults on the VOP's MMU at IOVA 0xfd2000, then an oops in `try_module_get` on
  0xff000000ff000000, two opaque black pixels (pstore). A cancelled writeback job ended without
  stopping the engine; once the VOP's IOMMU detached, the engine went on writing, its buffer's IOVA
  taken as a physical address in kernel memory. `vop2_wb_cancel()` now stops the engine first
  (`drm-rk3528-vop2-writeback.patch`). The regions check on the box: 1 bad round of 20 before, all
  strips black and every refusal taken.
- On the fix, the M2 Plus: the regions check 40 rounds, none bad; no IOMMU fault, warning or reset;
  `screen.py` passes; a full `display.py` 67 passed, 0 failed. The bad regions round and the black
  captures were the same engine writing on, not a capture race.
- The `display.py` run straight after those 40 rounds was refused from `sdr2pq` on, errno 22, by
  vop2's CRTC check (drm.debug 0x14: `[CRTC:386:video_port0] atomic driver check failed`); `sdr2pq`
  alone then passed, and the next full run passed 67 of 67.
- A board's build now prints each unresolved and unknown item under its counts
  (`tools/dtcx/translate.py`); before, only the counts reached the build. The HK1's one: its HDMI
  node's `sleep` pin state, the same `hdmi_pins` as `default`. `state sleep same` keeps it, the
  vendor's as set: no other board's tree carries a sleep state.
- The R69-1's, `h96max-rk3528`'s and the HK1's next2 trees regenerated: OP-TEE dropped; the crypto
  engine, SAI0 and SAI1 disabled, and the VOP's gamma LUT range added from the SoC patches. Not yet
  booted on the R69-1 or the HK1; `h96max-rk3528` has no box here.
- The M2 Plus's display-full refusals in the regression, found: DRM turns a CRTC off when the
  framebuffer its primary plane shows is freed (`Disabling [PLANE:35] because [FB:404] is removed`,
  then `Set [NOMODE]` on both CRTCs), and display.py frees a buffer when Python collects it. Every
  check after composes on an off CRTC: `Writeback-1 has framebuffer, but [CRTC:386] is off`,
  errno 22. When it struck depended on collection: rotation's Cluster0 cases first, regions,
  `sdr2pq` and the rest after. `compose()` now turns the CRTC back on with the run's mode where it
  reads off. On the M2 Plus: the replay that failed every time passes, a full run 73 passed, 0
  failed.
- `display_free()` now stops a session unit that is starting as well as one running: greetd's
  greeter on the M2 Plus restarts in a loop on next2 (`greeter exited without creating a session`),
  and between restarts it reads `activating`.
- The R69-1 on its regenerated next2 tree: the default regression, 715 checks, 0 failed. The crypto
  engine's 8 algorithms pass their self-tests, the OP-TEE failure is gone, and both SAI playback
  devices work.
- The M2 Plus's regression, after the CRTC fix: 8 failed where it was 14. Rotation, regions and
  `sdr2pq` pass. Still failing: pacing, whose first 89 commits pass and every later one fails, and
  the six HDMI sink checks after it. pacing now records the CRTC's and HDMI's state at its first
  failed commit. greetd's failure is the desktop's greeter, labwc running gtkgreet on VT 7, exiting
  on next2: 5 restarts and `start-limit-hit` before any test.
- The numbers of the 2026-11-25 next2 runs read against each board's vendor 6.1 run (2026-11-22, the
  M2 Plus's 2026-11-20):
  - fio within 1–4% on every board; Wi-Fi 20–30% faster on next2, the Seekwave fixes.
  - glmark2 about twice the vendor's (3518 114 against 55): the vendor's GPU sits at 498 MHz, a rate
    its own table of 700 and 800 lacks.
  - DDR: the 3518 at 786 MHz on both kernels.
  - CPU under load: the R69-1 read 1200 MHz on next2 against 1416, the M2 Plus 1008 against 2016,
    neither thermal. `box.py` took its last sample after `stress-ng` ended, the `ondemand` governor
    already stepping down. It now samples only under load: the R69-1 on next2, 1416 MHz sustained,
    as vendor.
  - The CPU's voltages run above the vendor's: 1416 MHz at 914 mV on the R69-1 against 900; on the
    M2 Plus 964 against 950 at 1416 MHz, 1100 against 1073 at 2016.
- The M2 Plus's pacing failure, narrowed: it follows a `screen.py` that rendered its frames, never
  one that skipped (5 replays). The whole-output disable is the kernel's fbdev client restoring the
  console: ftrace on next2 shows `close()` → `drm_release` → `drm_client_dev_restore` →
  `drm_fbdev_client_restore` → `drm_client_modeset_commit`, every plane cleared and no mode on
  either CRTC. greetd's crash loop is one trigger: `display_free()`, `screen.py`'s too, started it
  again after a run, its greeter took the console's VT 1.5 s into the next. `display_free()` now
  stops every session unit whatever it reads and starts again only one that was steadily active.
  Pacing still failed in 2 of 4 rounds after that, about 1.7 s in each time: another closing
  descriptor, being traced.
- Correction: greetd's greeter on the M2 Plus is the desktop's, labwc running gtkgreet on VT 7
  (`50-tvb-desktop.conf`), not Debian's `agreety`; why it exits on next2 is open.
- The M2 Plus's regression with greetd off: 758 checks, 1 failed. display-full 73 passed, 0 failed;
  the CPU 2016 MHz under load as vendor; settled in 2 s, not 18. The fail:
  `mmc0: Tuning failed, falling back to fixed sampling clock`, random writes 3.7 MB/s against
  vendor's 9.8. Both kernels run the eMMC at HS200, 100 MHz, from the same node; mainline gives the
  RK3528 the RK3588's HS200 transmit tap, 16, where Rockchip's driver sets 12 for the RK3528 (and
  the RK3562). `arm64-dts-rk3528-emmc-txclk-tapnum.patch` sets 12 by the binding's
  `rockchip,txclk-tapnum`. soak peaked at 95.1 °C, the M2 Plus's trip.
- Tap 12 on the M2 Plus: in its running tree (`/proc/device-tree/soc/mmc@ffbf0000`), six next2 boots
  tuned with no failure, and `box.py`'s storage step twice: sequential read 87.9 and 87.2, write
  76.7 and 69.9, random read 22.5 and 22.6 MB/s, as vendor's 87.5, 76.3 and 22.6. Random writes, 4.3
  and 6.1, vary run to run on next2 with tuning good (3.7 to 8.2); vendor's 9.8 is still above them.
  Every next2 tree regenerated with the tap; the 3518s, the R69-1 and the HK1 not yet booted on it.
- The four boxes on the tap-12 trees, default profile: the 3518 742 checks, 0 failed; the M2 Plus
  756, 0 failed; the 3518D 708 and the R69-1 723, 1 each: HDMI audio, 8 channels at 192 kHz, an
  underrun of 0.1–0.6 ms. No eMMC tuning failure on any. Wi-Fi lower on the R69-1 and the M2 Plus
  than their last runs (loaded download 83 against 160 on the R69-1), the four boxes run at once;
  random writes vary run to run, the M2 Plus's 4.8 MB/s against vendor's 9.8.
- The M2 Plus's panic step on next2: back with 3 pstore records in both of today's runs; the
  stranding on the todo is gone. Its lines read "back -49 s after it", "reset -15 s after it went
  unpinged": a box without an RTC boots on its last saved time, and the gap is negative until NTP
  sets the clock, so every "timely" check passed on it. `onbox.py` now times a reset only once NTP
  has set the clock, waiting up to 90 s, and says the gap is unknown otherwise.
- Remote wake on next2: `soc-rockchip-pm-config.patch` hands BL31 the board's
  `rockchip,sleep-mode-config`, `wakeup-config` and `pwm-regulator-config`; the translator keeps the
  vendor's `rockchip,pm-rk3528` node, Rockchip's flag header as a local dtcx header, and gives the
  IR receiver `wakeup-source`. On the 3518: the driver bound, BL31 took every value,
  `wake.remote 1 of 1 armed: rc0:enabled`, `mem_sleep` deep. A key waking it needs a hand.
  `soc-rockchip-pm-config-virtual-poweroff.patch` makes power-off the vendor's sleep the remote
  ends.
- Virtual power-off on the 3518, next2: off at 11:05:27, answering again within 120 s, up 44 s. The
  same on vendor 6.1: off at 11:09:26, back within 120 s. `tvb-base` runs systemd's hardware
  watchdog, the DesignWare counter cannot be stopped once started, and a firmware sleep in place of
  power-off keeps it powered: it resets the box about 80 s after power-off, on both kernels. Suspend
  is safe: `dw_wdt_suspend()` gates its clocks. `watchdog-dw-wdt-stop-at-power-off.patch` gates the
  counter's clock at power-off prepare, before the virtual power-off's handler, the bus clock left
  for a ping still on its way.
- With the watchdog patch, the 3518 on next2 powered off at 11:17:17 and stayed off 12 minutes; the
  strip's port 3 brought it back. The remote starting it from that sleep needs a hand.
- The CPU's voltage against vendor: both kernels pick the same PVTM level. R69-1: vendor
  `pvtm=1543`, `pvtm-volt-sel=4`; next2 `pvtm 1533: bin L4`, L4 at 1416 MHz being 912.5 mV, read
  back 914. The 3518: vendor `pvtm=1566`, `pvtm-volt-sel=5`, its tree having no L5 at 1416 MHz, so
  the plain `opp-microvolt`, 900 mV (debugfs `u_volt_target 900000`); next2's L5 is 900 too. The
  vendor's PVTPLL calibration (`rockchip_pvtpll_calibrate_opp`) needs `rockchip,pvtpll-avg-offset`
  and its siblings, which no factory tree here carries: it never runs. Open: the R69-1's vendor
  reads 900 at level 4. `box.py`'s CPU step now records `pvtm.cpu` and `pvtm.gpu`, count and level,
  from either kernel's log, and the report fails a level unlike the board's own kernel's.
- Bring-up checklist against the suite: each box-testable item in `system.md`, `network.md`,
  `power.md` and `storage.md` now names the key that answers it. New checks where none answered:
  `boot.startup`, systemd's startup waited for before `boot.seconds`, which every run before read
  `none`, the step running before startup finished; `wake.remote`; `pvtm.cpu`, `pvtm.gpu`;
  `gpu.ladder`; `eth.<if>.mbits` untested without a cable, where it was silent; the report fails an
  address unlike the board's last run's or its own kernel's.
- The four boxes with the sleep-config node, the IR wake source, virtual power-off and the watchdog
  patch, default profile: 744, 714, 764 and 722 checks, one failure each, `boot.seconds none`:
  startup had finished (`boot.startup running`), but a boot past a minute prints as `= 1min 4.2s`,
  which the parse missed. `boot.seconds` now reads systemd's `FinishTimestampMonotonic` (the 3518:
  10978375 µs, as `systemd-analyze`'s 10.978 s).
- The new lines: `wake.remote 1 of 1 armed` on the three with a receiver; `gpu.ladder` 300, 700, 800
  MHz at 900 mV on three, five rates at 824 mV on one, a rail the GPU shares and does not scale;
  `pvtm.cpu` L2 to L5 and `pvtm.gpu` L5 to L8 across the four chips.
- `tools/validate/power_switch.py`, `regression.py run --power-switch CMD`: where the host switches
  the box's outlet, each kernel tested is held asleep 180 s and off 300 s, a box answering before
  the hold ends failed, then power-cycled back.
- The R69-1's CPU voltage, explained: on vendor 6.1 this boot `pvtm=1557`, `pvtm-volt-sel=5`, the
  OPP target at 1416 MHz 900000 µV, the rail 900700; the boot before read 1543 and level 4, next2
  1533 and L4 (912.5 mV). The chip sits at the L4/L5 boundary, about 1550 counts, and its count
  moves boot to boot. Both kernels select by the same rule: no gap.
- `power_switch.py` on the 3518, next2: `power.sleep held 190 s`, `power.poweroff held 310 s`, each
  back after the strip's cycle. Two runs before failed to boot next2 for the second hold:
  `boot_once.py` rebuilds the initramfs, 23 s on an idle box and more on one just up, and the call
  gave it 30 s with `systemctl reboot` chained after; the ssh cut short, no reboot came. It now has
  180 s and the reboot is its own call; startup is waited for before each.
- `video.py` `readback` (video.md C12): a 4K decode's frames a second kept in the device's buffers
  against copied to memory. The 3518, vendor 6.1, MPP: H.264 61.3 fps kept, 12.1 copied, 188 MB/s;
  HEVC 115.8 and 12.0, 167 MB/s. The copy reads uncached memory: a player that takes 4K frames
  through the CPU stops near 12 fps. C7 needs no new check: `decode`'s ladder runs its largest
  passing size again after the failures past it, `flaky` where it no longer passes.
- `readback` on next2, the 3518: H.264 58.6 fps kept, 11.5 copied, 178 MB/s; HEVC 107.1 and 11.5,
  160 MB/s: as vendor's. FFmpeg's V4L2 request decode copies its frames to memory unless asked to
  keep them (`-hwaccel_output_format drm_prime`), so `readback_case` times both forms; the copy
  reads uncached memory on both kernels.
- 4K decode, kept frames, the 3518: next2 H.264 58.6, HEVC 107.1 fps; vendor 61.3 and 115.8. The
  decoder's clocks are the same on both kernels, idle and decoding (`aclk_rkvdec` 339428572,
  `clk_hevc_ca_rkvdec` 594000000, DDR 786 MHz), and so is its row-cache SRAM, 48 KB at `0xfe480000`.
  Per frame next2 takes 0.75 ms more for H.264 (17.06 against 16.31) and 0.70 ms more for HEVC (9.34
  against 8.64): a fixed cost a frame whatever the decoder's work, FFmpeg's request decode waiting
  on each frame before the next, where MPP keeps the decoder fed.
- The 4K decode gap's cause, the 3518 on next2, `video.py`'s timing: HEVC 105.1 fps at FFmpeg's
  default threads, 110.9 at two, 113.4 at one; H.264 58.6, 59.2, 60.1. Vendor's MPP: 115.8 and 61.3.
  Frame threads only add the hand-off and the hwaccel context's mutex where the hardware decodes;
  one thread already overlaps the next request with a decode, the frames leaving in display order
  behind it. The earlier reading, a serialized request path, was wrong: two threads only looked
  faster with FFmpeg's start-up in the timing.
- ffmpeg9 `0056`: where a decoder gets a V4L2 request device and the caller leaves the thread count
  to FFmpeg (`threads auto`, the CLI's default), it decodes on one thread; a count the caller sets
  is kept. `video.py` leaves the count alone, so next2 is timed as a program using ffmpeg9 runs it,
  as vendor's MPP decoder is.
- ffmpeg9 with `0056` on the 3518, next2, the default threads: HEVC 111.6 fps (105.1 before; one
  thread 113.4), H.264 59.7 (58.6 before; one thread 59.6). Against vendor's MPP 115.8 and 61.3:
  3.6% and 2.6% behind, from 9% and 4.4%.
- The last 3%, traced on the 3518 (function tracer on `rkvdec_device_run` and the IRQ handler, 4K
  HEVC): the decoder runs 8.85 ms a frame, idle 40-120 us between jobs, except every third frame
  idles 1.4-1.5 ms, the job started by the decoding thread itself. `avcodec_send_packet()` decodes
  into its one-frame buffer and the request hwaccel's `post_process` waits there on the frame's
  hardware: the next frame is parsed and submitted only once this one is done. Vendor's MPP parser
  runs ahead of its hardware on its own thread (`mpp_dec_parser`, `mpp_worker_0`).
- ffmpeg9 `0057`: an hwaccel with `HWACCEL_CAP_DELAY_OUTPUT` hands its frames out one late, so the
  wait falls on a frame already decoded while the next runs; the V4L2 request hwaccels set it. 3518,
  next2, 4K: HEVC 115.2 fps (vendor 115.8), H.264 60.0 (61.3); 15 frames hardware against software,
  `-pix_fmt yuv420p` framemd5, identical for both, the held frame out at the end.
- `0057` fixed: draining, a frame with none held passed through, or FFmpeg's CLI asserted
  (`ffmpeg_dec.c:809`, `EAGAIN` while flushing) on a damaged HEVC clip whose first frame left only
  at the drain. The 3518's conceal, decode, scale, deinterlace, refusal and readback suites: nothing
  worse than the 12:29 regression.
- Where next2's 4K HEVC frame goes, function tracer, medians of 30: hard IRQ to the IRQ thread 26
  us, the thread to `rkvdec_device_run` (the mem2mem kworker) 66 us, `device_run` to the kick 90 us,
  the hardware 8645 us. The hardware's bound is 115.7 fps, vendor's MPP 115.8: its link mode queues
  the next job in hardware and hides the 182 us. Clocks (340/600 MHz), SRAM row buffers and colmv
  compression match vendor's.
- CPU of 600 4K frames without flushes, whole box from `/proc/stat`, the 3518: HEVC next2 5.43 s,
  1.23 s CPU; vendor MPP 5.12-5.43 s, 1.81-2.15 s. H.264 next2 10.29 s, 0.96 s; vendor 9.91-10.01 s,
  1.84-2.01 s. V4L2 takes a third to a half less CPU.
- The same 600 frames as a three-frame clip looped (`-stream_loop`, a flush each loop): H.264 next2
  12.19 s and 3.5 s CPU against vendor's 10.26 s and 1.53 s. FFmpeg's `h264_decode_flush` freed
  every table and the next slice rebuilt them, "Reinit context" each loop, the 4K picture pools
  zeroed again. ffmpeg9 `0058` keeps them; a changed SPS still reinitialises.
- `0058` on the 3518, next2: the looped H.264 600 frames 10.47-10.80 s and 1.0 s CPU (12.19 s and
  3.5 s before; vendor MPP 10.26 s and 1.53 s); HEVC unchanged, 5.66 s. framemd5 of a 1080p clip
  looped 10 times, software unflushed against software and hardware looped: identical for H.264 and
  HEVC. H.264 4:0:0 differs as yuv420p in one pass too, identical as `gray`: hardware hands out
  GREY, software yuvj420p. Decode, conceal and input suites: nothing worse than the 12:29 run.
- Per-job hardware time, the 3518, the same 600-frame 4K files, vendor's link IRQ against next2's
  hard IRQ: H.264 16.13 against 16.59 ms, HEVC 8.47 against 8.76; next2's decoder busy 98-99%. The
  slow frames differ by frame type, at the same clocks (340/600 MHz) and DDR (786 MHz).
- The RCB SRAM, read from the decoder's base registers mid-decode: next2 filled it in register order
  at generic sizes, a page each (intra, transd row and column, stream row), the deblocking row in
  DDR. MPP sizes each for the stream and gives the SRAM deblocking, intra, SAO, inter first.
  `media-rkvdec-vdpu381-rcb-sram-priority.patch`: H.264 and HEVC size theirs as MPP does, in MPP's
  order. Packed a page each, HEVC's deblocking (24960 B for 32x32 CTUs) took 28 KB and SAO missed;
  the SRAM mapped once and packed at 64 B, H.264 holds deblocking and intra, HEVC deblocking, intra
  and SAO. Mapped at its kernel address, the 8K VP9 cases' buffers collided with it
  (`iova 0x80470000 already mapped`); mapped through `dma_map_resource()` they pass.
- With it, per job: H.264 16.17 ms, HEVC 8.63 ms (next2's still carry ~150 us between jobs).
  `video.py` rate, medians of five, 4K: next2 HEVC 115.6 fps, H.264 61.4; vendor MPP 116.8, 61.0.
  framemd5 against software identical for 4K and 1080p HEVC and H.264 and 1080i H.264. Decode,
  conceal, scale, afbc, input, refusal, deinterlace and readback suites: nothing worse than the
  12:29 regression; no kernel warnings.
- `dpkg -i` of the next2 image ran `u-boot-update`, which set the menu default to the newest kernel,
  l0; boot_once saved and restored that menu. The 3518 came up on next2 from a plain reboot. The
  default put back to l4, 6.1.172, beside the file and moved over it.
- Between two jobs on next2, medians over 64, the 3518: hard IRQ to the IRQ thread 21 us, the thread
  to `device_run` 45 us (the mem2mem worker), `device_run` to the kick 81 us. FFmpeg started only
  the first job of each run, the worker every other: the next frame was always queued.
- `media-v4l2-mem2mem-run-next.patch` and `media-rkvdec-run-next-from-irq-thread.patch`: the next
  job started from the IRQ thread; that step 27-30 us.
  `media-rkvdec-vdpu381-start-before-request- complete.patch`: the decoder kicked before the
  request's controls complete, its IRQ and watchdog waiting on a completion `device_run` holds;
  `device_run` to the kick 60-62 us. 3000 64x64 frames, H.264 and HEVC, three runs each (about 1500
  jobs a second): identical to software, no warnings.
- The vendor driver sets the decoder's three caches (cacheable, read-allocate, 64 B lines), clears
  them and sets 0x1c outstanding reads before every job; next2 never did. Written to the binding's
  "cache" region (0xff740600, as the RK3588's and RK3576's): per-frame means unchanged, HEVC 8.61 to
  8.62 ms, H.264 16.14 to 16.15. Dropped.
- Wrong turn: next2's "frame A 0.5 ms slower" compared different frames of the three-frame cycle,
  the two traces starting at different frames. Per cycle, vendor 25.3 ms, next2 25.8 ms: the
  hardware matches; the difference is the ~110 us a frame between jobs.
- `va.probe.initialize` read "no va_probe beside the driver" on every box: nothing installs it in
  the system's dri folder. `vaapi_test.py --probe` names it; the regression sends the built
  `va_probe` with the VA suite and refuses to start without it. The 3518, next2: seven `probe.*`
  lines through the option, the missing path named without it.
- `boot_once.py`'s restore moved from `local-bottom` to `local-premount`: root mounted by the hook,
  the menu written beside and moved over, not with `cat >` onto it. Two wrong turns on the 3518:
  klibc's `mount` needs a type, and a hook gets neither the init's `$FSTYPE` nor its resolved
  `$ROOT`; `resolve_device` and `get_fstype` from `/scripts/functions` give both. Then next2 once,
  "tvb-boot-once: the menu before restored" at 3.0 s, default back to l4, a plain reboot on 6.1.
  Each failed try left the default on next2 until it was put back by hand.
- Every other engine against vendor's MPP, the 3518, `video.py`'s rates and the whole box's CPU
  while each runs, one run each; next2 against vendor: VDPU2 decode at 1080p, MPEG-2 76.4 against
  72.9 fps (CPU 37 against 50% of a core), MPEG-4 84.8 against 80.8 (32 against 45%), VP8 60.2
  against 58.9 (25 against 27%), H.263 1408x1152 82.6 against 80.2 (32 against 39%). The encoder at
  40 Mbit/s: H.264 1080p 62.2 against 55.4, 4K 17.2 against 14.4; HEVC 1080p 73.9 against 61.9, 4K
  20.0 against 16.3. MPP refuses MPEG-2, MPEG-4 and VP8 at 4K; next2's 14-17 fps there at 84-103%
  CPU is FFmpeg's software fallback, the VDPU2 being a 1080p engine. JPEG has no MPP path in
  ffmpeg9.
- ffmpeg9 `0059`: `-nosw_fallback` fails a decode whose hwaccel cannot be set up, where FFmpeg went
  on in software; `video.py` passes it on every hwaccel path, and the message is a fallback the
  verdicts already read as "refused". The 3518's decode, conceal, scale, afbc and refusal suites:
  nothing worse; AFBC MJPEG (six) "linear" and scale MJPEG 4K "full" now "refused": MJPEG has no
  request hwaccel, those were software decodes. VDPU2 at 4K: no rate, where it timed the CPU.
- The HDMI audio jack on next2 follows the output, not the hotplug: dw-hdmi reports it in the
  bridge's enable and disable. The 3518D with no screen, `box.py`'s `hdmi-jack.follows` under
  `display.py`'s SDR sink and after: on within 0.3 s; off at once 7 times in 8, once at 10.2 s, the
  connector poll; waited up to 15 s, ten runs of ten "on with a screen, off without".
- HEVC encode past 5120x2880 is the hardware's: the 3518D on vendor 6.1 through MPP's `hevc_rkmpp`
  at 40 Mbit/s, 10 frames of `testsrc2` scored against the source, six runs a size: 6144x3456
  garbage in 5 (5.4-13.1 dB, one 34.4), 7680x4320 in 6 (5.2-15.2 dB), 5120x2880 33.98 dB in all 6.
  next2's encoder holds HEVC at 5120x2880, where MPP has no such cap.
- C9 on rkvdec: `media-rkvdec-test-failure.patch`, `fail_next_job` 1 gives the next job a one-cycle
  timeout, 2 points its output at IOVA 0x1000, unmapped. On the 3518, next2: each mode's decode
  reports one corrupt frame (none without), the IOMMU logging "Page fault at 0x1000 of type write"
  for 2 and nothing for 1; the clip decodes identical to software right after, no reboot. The IOMMU
  lets the core go on, its writes dropped: a fault ends the job, it does not stall it. `video.py`
  `failure`, both modes for H.264 and HEVC at 1080p: 4 passed; the 1080p decodes, 18.
- C9 on Hantro VDPU2 and VDPP: `media-hantro-vdpu2-test-failure.patch` and the VDPP fix,
  `media-rockchip-vdpp-recover.patch` (`fail_next_job`: 1 leaves the next job unstarted, 2 points
  its output at IOVA 0x1000). A write to an unmapped page left the Rockchip IOMMU idle with the
  fault active and the write in its replay buffer (status 0x6b): each PAGE_FAULT_DONE replayed it,
  the bank never stalled, `rk_iommu_enable()` gave up before its force reset, and every later job of
  the master came out blank until a reboot. 7.3 refuses `iommu_set_fault_handler()` on a DMA-API
  domain, so the master cannot hear of it. `iommu-rockchip-reset-a-bank-stuck-on-a-fault.patch`:
  such a bank is reset unstalled, and a work after the fault enables it again once its master is
  idle.
- VDPP before its fix: a bus error soft-reset the core in the interrupt, timed out on the stalled
  IOMMU, and the CRU pulse that followed left VDPP and IEP2 with no output to a reboot. Now a
  watchdog ends a failed or unanswered job from a work: the IOMMU reset through the group VDPP
  shares with IEP2, then the core; no CRU pulse. On the 3518: modes 1, 2 and 2 again, each followed
  by a 1080p copy byte-identical to its source.
- `video.py` `failure` on the 3518, next2: H.264, HEVC and VP8 pass both modes, MPEG-2 and MPEG-4
  pass the timeout; after a fault their next decode is 5.35 dB until a VP8 decode runs, then 75.8
  and 76.0 dB. Hantro reports a failed job only in the kernel log: the case counts that or a corrupt
  frame as the failure. MPEG-2 against software is never bit-exact: the case judges the decode after
  by the decode suite's own verdict.
- Why MPEG-2 and MPEG-4 stayed wrong after a fault: VDPU2's interrupt handler took the pending bit
  (`DEC_IRQ`, set for any cause) as a finished job, so a bus error on the faulted write came back as
  a good picture and the core kept the error's state until a VP8 job reprogrammed it. G1's handler
  takes the ready bit. `media-verisilicon-vdpu2-done-only-when-ready.patch`; and
  `media-hantro-recover-timeout.patch` now ends a failed job through the watchdog's recovery, the
  core and its IOMMU reset, as a timed out one.
- `video.py` `failure` on the 3518, next2, with VDPP's case added: H.264, HEVC, VP8, MPEG-2, MPEG-4
  and VDPP, timeout and fault each, 12 passed, the next job right every time; 18 1080p decodes pass;
  no warning at boot.
- `TVB_BUILD_DEBUG=1`: a kernel conf's `DEBUG_PATCHES` applied after its `PATCHES`. next2's three
  `fail_next_job` patches moved there, VDPP's split out of its recovery patch; a release build
  applies 128 patches and its `rockchip_vdec`, `hantro_vpu` and `rockchip_vdpp` carry no
  `fail_next_job`.
- Wrong turn: the debug kernel looked to hang at boot on the 3518, four times; the release image
  booted. Blacklisting the three modules did not help, and a release build versioned `+debug` "hung"
  too: the image alone broke the `tvb-*-modules` pin, their `depmod` trigger stayed pending, and
  next2 came up with no Wi-Fi. Installed with its own module packages, it boots.
- The debug build's `+debug` version suffix dropped: it broke the module packages' version pin.
- The debug kernel installed with its own module packages on the 3518: the three `fail_next_job`
  parameters present; `video.py` `failure`, H.264, HEVC, VP8, MPEG-2, MPEG-4 and VDPP, timeout and
  fault each: 12 passed, the next job right every time.
- C9 on every video engine: `media-rkvenc-vepu540c-test-failure.patch` and
  `media-rkjpegd-test-failure.patch` join the debug list (133 patches in a `TVB_BUILD_DEBUG=1`
  build); `video.py` `failure` gains MJPEG decode and an encoder case. On the 3518, the debug kernel
  installed with its module packages: H.264, HEVC, VP8, MPEG-2, MPEG-4, MJPEG decode, H.264, HEVC
  and JPEG encode, and VDPP, timeout and fault each, 20 passed, each failure in the kernel log and
  the next job right.

## 2026-11-25 — HDMI audio, 8 channels at 192 kHz

- `display-full`'s `hdmi audio` across today's next2 runs: 8 channels at 192 kHz passed 17 times;
  its two underruns (0.109 and 0.610 ms) were one run, 10:42, on the R69-1 and the 3518D at once.
- The HDMI PCM's buffer, vendor and next2 alike: 512 KiB preallocated, `BUFFER_BYTES` to 524288,
  about 85 ms at 8 channels, 192 kHz, S32. Vendor has no record of the case.
- On the 3518D, next2, the suite's synthetic surround screen, `display.py`'s own `play_reading`: 25
  of 25 clean while the 32275-register dump (216 ms) is read mid-stream, 25 of 25 without. Not
  reproduced on the current build; the regression keeps the case.

## 2026-11-25 — the GPU bus on vendor 6.1

- `aclk_gpu_root` in `clk_summary` on vendor 6.1, no bus devfreq on any box (`/sys/class/devfreq`:
  `dmc` and the GPU): 498 MHz on the 3518, the 3518D and the R69-1; 297 MHz on the M2 Plus, whose
  `gpu-bus` fails to probe. On the 3518D the same at idle and through glmark2, the GPU's own
  `scmi_clk_gpu` reading 300 MHz under load. Vendor does not scale the bus here; next2's fixed 498
  MHz is the vendor's rate or above it.

## 2026-11-25 — kexec from vendor 6.1 into next2, on serial

- The HK1, 6.1 into next2 7.3.5 by kexec, `keep_bootcon loglevel=8` beside its `earlycon`
  (`build/logs/hk1-rbox-k8s/next2-kexec-from-6.1-hang.log`): ramoops registers at 0.077 s; the last
  line `clk: Disabling unused clocks` at 1.234584 s, then nothing for 2.5 min and no watchdog reset.
  `pd_gpu` `failed to get clk at index 0: -517` three times at 0.41–0.46 s.
- The 3518, 6.1 into next2 7.3.6 with `clk_ignore_unused` added: `systemd-kexec` done, the watchdog
  running; back on 6.1 by itself within about 20 s, where without it the box stayed dark. pstore
  empty: next2 stopped before its ramoops probed, earlier than the HK1.
- The HK1 with `clk_ignore_unused`
  (`build/logs/hk1-rbox-k8s/next2-kexec-from-6.1-clk-ignore-unused.log`): past
  `clk: Not disabling unused clocks` to `/init` at 1.25 s, but at 0.250 s
  `of_clk_src_onecell_get: invalid clock index 511` and
  `rockchip_clk_of_add_provider: could not register clk provider`: the CRU never registered, and at
  12.2 s nearly every device deferred on a clock or GPIO; then a reset into 6.1. The same kernel and
  DTB picked once from U-Boot's menu: none of those lines, `devices_deferred` empty. The CRU node's
  first assigned clock is `XIN_OSC0_DIV`, 372; no tree here names 511.
- What U-Boot adds to the 3518's next2 tree (`/sys/firmware/fdt` against the file): `/memreserve/`
  for the initrd, `serial-number`, `/chosen`, the `memory` node, the GMAC's `local-mac-address`;
  nothing in the CRU. The 3518 kexec'd into next2 with that exact tree: dark, the strip's port 3.
- The 3518 kexec'd with the GMAC, EHCI, OHCI and DWC3 unbound first: dark, the strip's port 3. Not
  the tree, nor those DMA masters. Left: the state 6.1 leaves in the CRU or GRF, read at probe; it
  needs the HK1's serial.

## 2026-11-26 — VDPU2 limited by area

- `media-hantro-rk3528-vdpu2-area-limit.patch`: a Hantro format may carry `max_macroblocks`, applied
  after its size box by shrinking the height; the RK3528's NV12, MPEG-2 (MPEG-1 through it), MPEG-4
  and VP8 take either side to 1920 within 8160 macroblocks. H.264 keeps 1920x1088, untested past it.
- FFmpeg took the shrunk OUTPUT size and decoded nothing, unexplained (VP8 1920x1200 `broken`, 0
  frames): FFmpeg `0060` refuses a coded size the driver gives back smaller, as one it does not
  list.
- `video.py`: `AREA_SIZES`, 1080x1920 at the area and 1920x1200 past it, in the ladder and the MPEG
  lists; `--only=` and `--skip=` passed to the box, as a regex starting with `-` was read as an
  option.
- The 3518, release next2 7.3.6 (129 patches), its module packages, FFmpeg with `0060`: 1080x1920
  decodes on MPEG-1 74.3 fps (75.94 dB), MPEG-2 74.8 (75.43), MPEG-4 84.7 (75.99), VP8 69.9;
  1920x1200 refused on each; 2560x1440 refused as before; H.263 to 1408x1152 passes (78.22 dB); the
  refusal suite passes. rkvdec passes all three sizes, H.264 to VP9 profile 2.

## 2026-11-26 — rkvenc's grey source, withdrawn

- A patch offering `GREY` as `RKVENC_CFMT_YUV400` (10), its headers saying 4:0:0: H.264 High with
  `chroma_format_idc` 0, HEVC range extensions' Monochrome profile, JPEG one component, the crop in
  luma samples, HEVC SAO off. checkpatch clean; `v4l2-ctl --list-formats-out` lists `GREY`.
- The 3518, next2 7.3.6 (130 patches), `video.py` `input`: every layout passed as before (NV12 47.3
  dB to RGB565 45.9); H.264 from `gray` at 1280x720 hung the box: no answer, no watchdog reset,
  pstore empty; the strip's port 3 brought it back on 6.1. The driver defaults to High and CABAC, so
  the earlier grey run that did not hang coded the same registers: the H.264 change was the headers
  only. A 4:0:0 encode can hang the VEPU540C; grey stays refused, the patch out of the tree, the
  input suite without `gray`.

## 2026-11-26 — the regression, vendor 6.1, 6.12 and next2

- `regression.py run --profile default --kernels all`, the 3518, 3518D, M2 Plus and R69-1 at once
  (`build/validate/regression/2026-11-26`). next2 7.3.6, 129 patches, FFmpeg `0057`–`0060`: 782–832
  checks a box, 2–3 failed: parity with 6.1 (`hdmi_cec_key`, `bt-powerkey`, `devfreq-dmc` cooling,
  the R69-1's `bt_default` rfkill), `pvtm.cpu` and `pvtm.gpu` a bin under 6.1's, and on the 3518 one
  Seekwave `stale TXBA, tid: 0, renegotiating` in the soak. Every untested video case is past a
  box's memory. Decode, scale, AFBC, encode, input, conceal and refusal pass.
- Measures past 10% on next2: idle and soak temperatures and `cpu.load.c` above 6.1's, which ran
  first: each box's idle temperature climbs with the run's order (M2 Plus 48.3, 56.6, 61.6 °C).
  Wi-Fi under load 12–18% under, four boxes on the air and one iperf3 server at once.
- PVTM on the R69-1 at one temperature: 6.1 1558 and 1546 (40–43 °C, bin 5); next2 1513 and 1514 at
  1416000 kHz, 950750 uV (bin 4). Vendor's `rockchip_get_pvtm_pvtpll` asks
  `regulator_set_voltage(reg, pvtm->volt, INT_MAX)`, sleeps `pvtm-sample-time` and reads once: a
  rail above 950 mV stays there. next2 asks 950 mV exactly, so it reads lower and picks a bin's
  higher voltages. `rockchip,pvtm-temp-prop` is `<0 0>` in the factory tree: neither corrects for
  heat.

## 2026-11-26 — kexec: the HK1's clock 511 is vendor's tree

- The factory blob's CRU `assigned-clocks` start `<&cru 0x1ff>`, 511 in vendor 6.1's numbering;
  next2's start `<&cru 0x174>`, `XIN_OSC0_DIV`. The HK1's kexec'd next2 ran on vendor's tree, what
  kexec-tools takes from `/sys/firmware/fdt` without `--dtb`.
- Not so: both HK1 captures passed `--dtb` (kexec-tools `--debug`: 92046 bytes, next2's 91929-byte
  tree; vendor's is 103747), and next2 still asked for 511: which tree it parses is the next check.
- On the 3518, `kexec_once.py`'s load with `--debug`:
  `dtb: /usr/lib/tvb/fdt/7.3.6-tvb-rk35xx-next2/board.dtb`, 89112 bytes at 0x2700000, the kernel at
  0x200000. With its own tree the 3518 still goes dark.

## 2026-11-26 — PVTM measured as the vendor does

- `cpufreq-rockchip-pvtm.patch`: the measuring voltage asked as `(volt, INT_MAX)`, one
  `pvtm-sample-time` wait, one read, as vendor's `rockchip_get_pvtm_pvtpll`; the settle loop and the
  rate and voltage check gone.
- Each box booted once on it: R69-1 1539 (39 °C, bin 4), 3518 1498 (bin 3), 3518D 1556 (bin 5), M2
  Plus 1322 (bin 1); vendor 6.1's 1546–1558 (bin 5), 1545 (5), 1618 (6), 1361 (2). Both kernels
  measure at 950 mV (`vdd_cpu: ... at 950 mV`, `regulator-init-microvolt` 953000) and 1416 MHz,
  next2's built in (`CONFIG_ARM_ROCKCHIP_CPUFREQ_PVTM=y`) as vendor's. Vendor 6.1's `clk-pvtpll.c`
  and `rockchip_opp_select.c` carry nothing for the RK3528: its PVTPLL is BL31's, through SCMI, on
  both kernels. The 2.5–4% is unexplained; next2's bin a step lower runs each OPP higher.

## 2026-11-26 — kexec from vendor 6.1 into next2, on next2's own tree

- The HK1's session found it (`build/logs/hk1-rbox-k8s/`): the kexec'd next2 held a 104610-byte
  tree, vendor 6.1's with U-Boot's `/chosen`; kexec-tools 2.0.29 loads by `kexec_file_load` first
  (6.1 has `CONFIG_KEXEC_FILE`), which on arm64 takes the running kernel's tree. Forced to
  `kexec -c` with next2's file, next2 panicked at 0 s, `Failed to allocate page table page`: the
  file has no `/memory`, which U-Boot adds.
- `kexec_once.py`: `kexec -c`, and the entry's tree copied to `/var/tmp/kexec.dtb` with the running
  tree's `/memory`, `serial-number` and each `local-mac-address` (by node name) put in by `fdtput`.
- The 3518, vendor 6.1 into next2 7.3.6 by it: up in 33 s on its own tree (compatible
  `h96max-3518,rk3518-tvbox rockchip,rk3528`, 89460 bytes), `running`, no clock errors, `eth0`
  `00:ef:00:4a:43:a6` from vendor storage, `wlan0` `fe:fd:fc:99:08:5f` as a menu boot gives, the
  menu's default still 6.1.

## 2026-11-26 — the regression's vendor kernels, read against their last runs

- Video, case by case against each kernel's last run: no case that passed fails now. Changed: the
  3518D's 6.12 `decode h264i 1920x1080` pass to flaky; cases now skipped as past memory (the R69-1's
  next2 five, its 6.12 three, the 3518D's next2 one), from `video.py`'s larger allowance, 12 frames
  held and 512 MB spare, RAM the same (1467 MiB).
- Vendor failures new since 2026-11-22 are cases new since then: MPP's `conceal` (every codec),
  H.264 4:2:2 and grey through MPP, VP9 8192x8192 (an `rk_iommu` fault), HEVC encode 7680x4320 (5.9
  dB); the checks `drivers.unbound` (crypto, OP-TEE, `rkvtunnel`), `mtd_vendor_storage` deferred,
  6.12's `hdmi-jack.follows` (off with a screen) and AFBC rotate-90 and rotate-270 on vendor's VOP2.
  next2 passes each.
- `display-full` crashed on both vendor kernels: `DRM_CLIENT_CAP_COLOR_PIPELINE` gives `EINVAL` on
  them, and `color_pipelines` let it out. Now no pipelines where the kernel refuses the cap.

## 2026-11-26 — writeback, each format the datasheet lists

- `display.py` `writeback`: a quadrant pattern full screen captured through each
  `WRITEBACK_PIXEL_FORMATS` entry, each quadrant read back. The 3518, next2: `BG24`, `AR24`, `RG16`,
  `NV12` offered; `BG24` came back red and blue exchanged, `NV12` 13–15 codes off.
- `BG24`: the engine's "BGR888" writes B first in memory, DRM's `RGB888`.
  `drm-rk3528-vop2-writeback.patch` now offers `DRM_FORMAT_RGB888` for it.
- `NV12` of an RGB output: BT.601 limited within 1 code, BT.709 limited 25 off; read as BT.601.
- After: `RG24`, `AR24`, `RG16`, `NV12`, 4 passed at 1920x1080.

## 2026-11-26 — VDPP colour conversion, the datasheet's BT601_l/BT601_f/BT709_l/BT709_f

- next2's VDPP copies the output queue's colour fields to the capture queue: no conversion, and none
  claimed.
- MPP develop's `mpp/vproc/vdpp/` (`vdpp`, `vdpp2`, `vdpp3`, `hwpq_vdpp_proc`, `vdpp_api`,
  `vdpp_common`): no matrix, range remap or YUV-RGB step on pixels. `sw_dci_csc_range` (DCI reg3 bit
  3, 0x10EC) tells the histogram the input's range; `src_range` scales the black-bar threshold
  (`bbd_det_blcklmt * 219 / 255 + 16`). The ZME's `format_in`/`format_out` choose 4:2:0 or 4:4:4. No
  register drives the datasheet's conversion: ❓.

## 2026-11-26 — RGA against the datasheet

- New `video.py` convert cases, failing first on next2: `BX24` either way, `NV15` and `NV20` sources
  (made from P010/P210, packed four samples to five bytes), 4096x2304 and 4608x2592 destinations.
  3840 to 4608 hung the RGA for good: `v4l2-ctl` in `v4l2_m2m_cancel_job`, a hung-task trace every
  two minutes, the RGA unusable until a reboot.
- `media-rga-recover-timeout.patch`: a 1 s watchdog a job; past it the IOMMU reset by an empty
  domain, the core by vendor 6.1's `rga2_soft_reset` (`SYS_CTRL` bits 3, 4 and 6, bit 0 polled), the
  buffers failed.
- `media-rga-rk3528-formats.patch`: XRGB32 (ARGB32's format, a source's alpha swap lost on
  XBGR8888); NV15/NV20 sources by `SRC_INFO` bits 27 and 28 as vendor sets them, and vendor's forced
  tile read for a 10-bit source neither scaled nor turned (its rows' first 16 pixels read from pixel
  192 on without it); corner addresses in bytes; destination 4096 a side (vendor's `rga2e` output
  range). Vertical upscale measured: a source 2048 wide to 4096x2304 39.7 dB, 2064 wide 31.3, 2560
  wide 21.6, horizontal alone right at 2560: refused past 2048 wide.
- `media-rga-csc-quantization.patch`: RGB to YUV was BT.601 full range (white 255, red 77/85/255)
  under a format saying limited; now by `ycbcr_enc` and `quantization`, vendor's mode numbers.
- `v4l2-ctl` does its gets and its capture try before its output set: a refusal is read from the
  frame's size. The 3518, next2: 27 convert cases, 25 pass, `dst-past-4096` and `vup-past-2048`
  refused.

## 2026-11-26 — system blocks against the datasheet

- `probe.py` DMA memcpy, by `dmatest` (`CONFIG_DMATEST=m` in the next2 fragment): before, no module;
  after, the 3518, `dma0chan6` 20 copies, 0 failed, `dma0chan2` and `dma0chan3` alike.
- Against the factory tree: one DMAC (`dma-controller@ffd60000`), as vendor; the USB3 port
  `dr_mode = "host"`; `i2c6` and `i2c7` disabled, no client wired. SARADC: all four channels read.
- Crypto: next2's engine serves AES ECB/CBC/XTS, MD5, SHA-1/224/256 and SM3; vendor 6.1 serves none,
  its crypto device unbound, every algorithm the CPU's. The datasheet's HMAC, other AES modes, SM4,
  DES/TDES and RSA: no driver, a todo.

## 2026-11-26 — JPEG decode, SAI samples and IEP2 modes against the datasheet

- JPEG decode's 48x48 minimum: 48x48 and 64x64 against FFmpeg's software decode, 67.1 and 67.0 dB;
  32x32 and 16x16 end in `driver decode error`, the frame flagged corrupt. `video.py` decodes MJPEG
  48x48 now: 59.2 dB. Its 76 Mpixel/s: 1080p at 313 fps, about 650.
- SAI samples: each card offers S16, S24 and S32; `box.py` audio plays each at 48 kHz, 2 s in 2.000
  s on S/PDIF, the codec and HDMI.
- IEP2: `media-rockchip-iep2.patch` sets `IEP2_DIL_MODE_I2O2` alone; the datasheet's other modes are
  a todo.

## 2026-11-26 — the crypto engine: more ciphers, HMAC, recovery, priorities

- `crypto-rockchip-rk2-more-ciphers.patch`: AES CTR, SM4 ECB/CBC/CTR, DES and TDES ECB/CBC, each by
  its version register. R69-1, next2: all pass their self-tests. CFB and OFB were added, then
  dropped: the kernel has no test vectors for them (`alg: No test for ofb(aes)`).
- Version registers, read with the engine pinned active (`power/control` on): AES `0x3717ff`, DES
  `0x370033`, SM4 `0x3007ff`, HASH `0x100187`, HMAC `0x10001b`. A first read with the engine
  suspended gave `0x5` everywhere, meaningless: the rule on `/dev/mem` broken, the box unharmed.
- `crypto-rockchip-rk2-hmac.patch`: HMAC_VERSION read as the hash register first offered
  `hmac(sha1)` and `hmac(sha512)`; SHA512 HMAC timed out on DMA at boot. Read as Rockchip's own list
  in order (SHA1, SHA256, SHA512, MD5, SM3), `0x1b` gives SHA1, SHA256, MD5, SM3: SHA1, SHA256 and
  MD5 pass; SM3 fails on a wrong digest and is not offered.
- After that one SHA512 HMAC timeout every engine job timed out until a reboot: the driver pulsed
  the CRU reset with the engine's DMA busy. `crypto-rockchip-rk2-recover-timeout.patch` resets as
  Rockchip's driver does, `RST_CTL` `SW_CC_RESET` polled. With
  `crypto-rockchip-rk2-test-failure.patch` (debug), a provoked timeout and a provoked wedge: the
  next hash runs, 98 and 97 MB/s.
- Userspace cannot reach the engine: on 7.3 AF_ALG binds only names in an allowlist
  (`/proc/sys/crypto/af_alg_restrict`), and never an async driver (`AF_ALG_CRYPTOAPI_MASK`). The
  bench is `tcrypt` (`CONFIG_CRYPTO_BENCHMARK`), each driver named.
- tcrypt's multi-update hash test oopsed in the fallback (`sha1_ce_transform`, a read past the
  caller's stack): the driver passed the fallback every request flag, the core's own among them.
  `crypto-rockchip-rk2-hash-fallback-flags.patch` passes `MAY_SLEEP` alone, as the RK3288 driver.
  tcrypt's multi-update rates (3–4 GB/s) are its own artefact: the CPU's `sha1-lib` shows them too.
- tcrypt, R69-1, MB/s at 256 B and 4 KiB: `ecb(aes)` engine 16/245, `aes-ce` 401/1224; `ctr(aes)`
  15/212 against 322/974; `sha256` 6/96 against `sha256-lib` 205/613; `hmac(sha1)` 5/85 against
  155/551; `md5` 6/95 against 129/176; `ecb(sm4)` 15/175 against `sm4-generic` 34/35; `ecb(des)`
  16/176 against 29/29; `sm3` 6/94 against `sm3-lib` 56/83. Every engine algorithm was at 300, tied
  with the CPU's and winning the tie. `crypto-rockchip-rk2-priority.patch`: AES, MD5, SHA and their
  HMACs at 200, under the CPU's and over `aes-lib`'s 110.
- `box.py` read tcrypt's lines by counting the log's lines; a full log buffer drops old ones, so
  late results and both recovery checks read nothing. Now by a marker written to `/dev/kmsg`.
- `kexec_once.py` took `memory-controller` for the memory node when run from next2. Matched by name
  now. Kexec from next2 into next2 resets the box; from vendor it boots: a todo.

## 2026-11-26 — IEP2 reads the frames either side (I5O2)

- `media-rockchip-iep2.patch`: I5O2, the previous, current and next frames read, as MPP's motion
  mode; FFmpeg's `0061` feeds it a frame ahead and drains at the end with `V4L2_DEC_CMD_STOP`.
- The test's two-input graph (the filter beside `bwdif`, through `psnr`) timed out in the drain: the
  core's stop marks the last frame but schedules no job, so with the job before it done the last one
  never ran. A single-input graph hid it: its stop came while a job ran. The driver's stop now
  schedules.
- Against `bwdif`, luma PSNR by output frame, the 3518: I2O2 42.4 at its worst; I5O2 39.6, 43.3,
  43.8, 43.7, 41.3, 31.6. The first and last frames, given themselves for the missing neighbour,
  wove moving fields. They run I2O2 now: 42.8, 42.4, 43.6, 43.7, 42.4, 43.0.
- With the priorities and the marker, R69-1, debug next2: `box.py --suite crypto` passes, every
  default the fastest at 4 KiB (20 algorithms; `xts(aes)` 216 engine, 868 `xts-aes-ce`), the next
  hash after a provoked timeout and wedge 95 and 93 MB/s, no oops.

## 2026-11-26 — rkvenc's sources past the ten: 4:4:4 in, 16-bit RGB refused

- MPP's VEPU5xx format enum runs 0–15: ARGB1555 3, YUV400 10, AYUV2BPP 11, YUV444SP 12, YUV444P 13,
  ARGB4444 14, AYUV1BPP 15. Its HALs never drive 12–15 or 3: no plane offsets, the HEVC buffer setup
  refusing them, a 4:4:4 chroma stride of half the luma's. AYUV2BPP and AYUV1BPP have no V4L2
  format.
- `media-rkvenc-rk3528-more-sources.patch`, the 3518, `video.py` input, H.264: NV24 passes at 35.3
  dB, with the chroma stride twice the luma's, in bytes as V4L2 lays it; MPP's half would read the
  chroma wrong. NV12 47.3, NV16 39.9 beside it.
- An RGB555 source (ARGB1555, MPP's U-V swap) hung the SoC past its watchdog: no reset in five
  minutes, a power cut, nothing in pstore. ARGB1555 and ARGB4444 are not offered; 4444 untried.
- FFmpeg had no V4L2 map for NV42 or planar 4:4:4: `0064` adds them, for NV42 and YUV444M.
- With `0064`, NV42 and `yuv444p` (YUV444M) encode as NV24 does, 35.3 dB, YUV444M with MPP's U-V
  swap. `yuv444p` into Matroska first crashed FFmpeg: the global header's black frame, from
  `av_frame_get_buffer`, holds every plane in `buf[0]`, and the multi-buffer copy read `buf[1]`.
  `0065` copies each plane by rows at the driver's stride.

## 2026-11-26 — a decoded 4K picture read by the CPU, cached

- The todo's cached capture buffers were there: rkvdec and Hantro set `allow_cache_hints`, and our
  FFmpeg's `0037` asks for non-coherent CAPTURE buffers with `v4l2request=v:,cacheable=1`.
- The 3518, next2, `video.py` readback at 3840x2160: H.264 61.6 fps kept, 11.6 copied uncached, 49.0
  cached; HEVC 116.6, 11.6, 49.7. Frames cached and uncached hash alike (framemd5), and match
  FFmpeg's software decode. The MB/s the case derives (2980 cached for H.264) is above the board's
  RAM read: copy and decode overlap, so the frames a second are the measure. A cached decode nobody
  reads costs its upkeep: 0.83 s against 0.74 s for 63 frames of 4K HEVC.
- `video.py` readback times the cached copy against the plain decode and fails one whose frames
  differ from the uncached.

## 2026-11-26 — the decoder's ½ downscale, read in MPP

- MPP's RK3528 entry: `vdpu382`, `cap_down_scale = 1`. `vdpu382_setup_down_scale` sets
  `reg012.scale_down_en`, all four `reg029` ratios to 2, `reg030`/`reg031` strides of half the
  frame's in 16-byte units, and `reg198`/`reg199` to offsets in the decode buffer: the half-size
  copy follows the full picture, luma at the frame's NV12 size, chroma after it. No ¼ ratio, no
  10-to-8-bit flag on `vdpu382`. Nothing in the files read turns it on: a frame's `thumbnail_en`
  gates it, `MPP_FRAME_THUMBNAIL_MIXED` the only mode used.
- Our `rkvdec-vdpu381-regs.h` has the fields. On V4L2 a smaller CAPTURE than the stream needs the
  full picture kept as a reference elsewhere: internal reference buffers, the copy in the CAPTURE
  buffer, as Hantro's post-processor does.

## 2026-11-26 — IEP2 4:2:2

- MPP's IEP2: `IEP2_FMT_YUV422 2`, `IEP2_FMT_YUV420 3`; `CONFIG0` source format bits 1:0, swap 5:4,
  destination 9:8 and 13:12; `SP_VU` 1. A semi-planar chroma stride is the luma's. MPP's decoder
  sends 4:2:0 alone; no 4:2:2 path was ever driven.
- `media-rockchip-iep2.patch` offers NV12, NV21, NV16 and NV61 each side. `video.py` gains an
  interlaced 4:2:2 clip, `h264i422`, de-interlaced against `bwdif` in 4:2:2.

## 2026-11-26 — PVTM a bin low: vendor's read, step by step

- Vendor's `rockchip_get_pvtm_pvtpll` (develop-6.1): an OTP `pvtm` cell first, used if set; then the
  rate, the voltage (`volt`, `INT_MAX`), one `usleep_range(sample_time)`, one `regmap_read` at
  `pvtm-offset`, a temperature term from `pvtm-temp-prop`. The 3518's tree has no `pvtm` cell
  (`leakage`, `opp-info`, `mbist-vmin`) and a zero `temp-prop`: vendor measures as we do, the same
  order, register and window. `clk-pvtpll.c` has no RK3528 table, the CPU clock is SCMI on both.
- Left: the rail. Both ask 950 mV of the PWM regulator; mainline's duty for it may not be vendor's.
  Next: the PWM's period and duty in debugfs, vendor and next2, at one OPP.

## 2026-11-26 — the mainline patches against checkpatch

- `checkpatch.pl --strict` over the 135 next2 patches: 97 clean. The errors are imports (the W132D
  patches without a `Signed-off-by`, Gaignard's AFBC formats) and our `afbc-nonsplit` keeping
  `v4l2-ioctl.c`'s one-line `case` style. Fixed: the Seekwave binding, now described and split from
  its vendor prefix; `pm-config`'s bindings split from the driver, twice; an alignment in
  `iommu-rockchip-attach-only`. Left as checkpatch flags them: the `MAINTAINERS` note on each new
  file, an entry naming its maintainer; `esmart-regions`' `reg_field` array, built at run time; the
  macro arguments `crypto-rockchip-rk2-priority` shows outside its hunk.
- The README missed `media-rkvenc-recover-timeout.patch` and the Seekwave binding; its
  `source-formats` row said grey, which is refused.

## 2026-11-26 — the FE PHY's temperature switch, read in vendor's driver

- The RK3528's integrated FE PHY (`0x00441400`) is vendor's `rk630phy.c`, its T22 branch (address
  2). Every 500 ms to 1 s `rk630_phy_service_task` reads `rockchip,thermal-zone`; at or under 85 °C
  page 6 register 0x14 bits 7:6 read `11` (receive detect at 260 mV, init `0x10c8`), over 85 °C
  `10`. No hysteresis. The same task switches page 6 register 0x10 between `0x5540` and `0x555e` by
  its no-signal and packet counts. `rk630,phy-disable-switch` turns both off, 0x14 left at `0x1088`.
- Mainline's `rockchip.c` writes `0x1088` once: vendor's over-85 °C and disabled setting, at every
  temperature. A change needs a cabled link to test; none on the 3518.

## 2026-11-26 — next2's 10-bit pictures, unchecked until now

- `video.py` counted next2's 10-bit decodes (`count_only`): our FFmpeg's `v4l2request` mapped the
  decoder's NV15 and NV20 to `yuv420p10` and `yuv422p10`, then offered no download format, so no
  10-bit picture was ever compared. A frame count passes a decoder writing garbage.
- FFmpeg `0066` unpacks NV15 and NV20 on download to P010 and P210, keyed on the CAPTURE format so
  other packed 10-bit layouts stay out. `video.py`'s `rkvdec` engine downloads 10-bit like 8-bit,
  each frame hashed against FFmpeg's software decode.

## 2026-11-26 — the HK1's next2 regression: its eMMC would not write

- The release 7.3.6 next2 on the HK1: `I/O error, dev mmcblk1 … op 0x1:(WRITE)` at 4.3 and 6.1 s,
  the superblock among them; `invalid driver type` and
  `Can't reduce the clock below 52MHz in HS200/HS400 mode` beside them. `systemd-remount-fs` failed,
  root stayed read-only, `onbox.py` died on `state.json`. The same kernel boots the 3518, 3518D, M2
  Plus and R69-1 from eMMC cleanly: the HK1's chip or its next2 tree, handed to its session.
- The regression had set the default to next2 for that boot, and a read-only root could not put it
  back. Out: the vendor tree fixed up on the host with the live memory, serial and MACs, a manual
  `kexec -c` with a direct `kexec -e` so the hardware watchdog stayed armed, the default restored
  from vendor 6.1. Root `clean`, an orphan cleanup only.
- Before the HK1 deployed, `build/out/debs` held the 25th's `+debug` kernel and module debs beside
  the release ones; its deploy refused the mixed set. Moved to `build/stale-debs`. The four other
  boxes had installed the release `7.3.6-0~local`.
- Cause, likely: the HK1 is the only RK3528 tree at HS400ES (`mmc-hs400-enhanced-strobe`, 150 MHz);
  the four others run HS200 at 100 MHz or less. Mainline's `sdhci-of-dwcmshc` takes the RK3528 as
  the RK3588: HS400 transmit and command taps at 90° (0xA, 0x8, `EN_SRC_CLK_NEG`), strobe tap 4,
  strobe delay 0x16, no lock-value selection. Vendor's `rk3528_drvdata`: transmit 6, command 6 on
  both clock edges, strobe 3, strobe delay 10, the DLL's lock value selected on every tap,
  `ORI_GATE` on the receive clock. `mmc-sdhci-of-dwcmshc-rk3528-taps.patch` gives the RK3528 those;
  the RK3576 and RK3588 keep theirs. The 52 MHz line fits as aftermath: after an error the core
  lowers the clock still at HS400 timing, and the driver skips the DLL. Untested.
- With the taps patch, the HK1 did not come back: a kexec from vendor reset at once, nothing logged;
  `boot_once.py` then put next2 on the menu for one boot, and it never reached the network, a power
  cycle alike. Its hook restores the menu only once the initramfs runs, so a kernel hanging earlier
  boots again at each reset. The patch is out of the conf until a box with a serial console shows
  what it does: it changes the HS200 path of every RK3528 tree too.
- From the HK1's serial (`build/logs/hk1-rbox-k8s/next2-emmc-taps-boot-once.log`): with the taps
  patch next2 boots, `invalid driver type` at 2.69 s, then from about 25 s every eMMC read fails,
  132 lines of `I/O error, dev mmcblk1, sector 0 op 0x0:(READ)`; root never mounts. Without it only
  writes failed: the vendor numbers on mainline's sequence read worse, not better. The patch stays
  out. Recovered over serial by the HK1's session, `default l3`.
- The HK1's next2 tree at HS200 (`mmc-hs400-1_8v` and `mmc-hs400-enhanced-strobe` dropped, as the
  four other RK3528 trees run), until next2's HS400 works on this card: the patch's harm exception.
  Installed with the release kernel, one menu boot by serial due.
- The HK1 at HS200 on next2, by one serial menu boot: root read-write, HS200 at 148.5 MHz, `fio` 512
  MiB direct write 66.1 MiB/s with crc32c verify, read 114 MiB/s, a second verify pass clean, no mmc
  error. The `invalid driver type` lines are there too: harmless. HS400ES on next2 stays a todo.

## 2026-11-26 — the batch's regression, next2 against vendor 6.1

- Failing as this morning: input and cooling parity (`hdmi_cec_key`, `devfreq-dmc`), the PVTM bins.
  The recovery cases and the crypto recovery read untested: a release build has no knobs.
- next2 runs hotter: R69-1 idle 53.3 °C against 44.9, CPU load 61.6 against 53.8, soak 66.6 against
  59.4; 3518D idle 53.3 against 47.7. Both sit a PVTM bin under vendor, a higher voltage at each
  rate.
- 3518D eMMC sequential write 30.8 MB/s against vendor's 37.6, at the tree's 50 MHz on both.
- glmark2 on next2 116–120 against vendor's 54 on both boxes, lima against Mali's own driver:
  checked as a too-good number, its rates and frames still to read.
- R69-1 `crypto.bench.ecb(des)`: the engine's 4 KiB rate missing (`16/-`), 176 MB/s this afternoon;
  the 3518D's measured.
- HS200 on the HK1 is a workaround, not the fix. The fix is HS400ES's own delay line, measured:
  `mmc-sdhci-of-dwcmshc-test-taps.patch` (debug) sets the HS400 transmit, command and strobe taps
  while the card runs; one menu boot at HS400ES on a debug kernel, root read-only as reads work,
  then each tap against writes to an eMMC boot partition, backed up first and read back.

## 2026-11-26 — next2's 10-bit, HDR10 and 4:2:2 interlaced, compared

- With FFmpeg `0066`, the 3518 on next2: every H.264 10-bit and HEVC Main10 size from 1080p to
  8192x4320 matches FFmpeg's software decode, frame by frame, where until now only frames were
  counted. HEVC Main10 4K 104 fps.
- `hevc10hdr` (4K HEVC Main10, BT.2020, PQ, a 1000-nit mastering display, MaxCLL 1000): decoded in
  hardware at 106.5 fps, its mastering display, light levels, BT.2020 and `smpte2084` as software
  gives them. The `hdr` case first failed on its own parser: FFmpeg 9 writes "Mastering display
  metadata" capitalised.
- `h264i422` (High 4:2:2, interlaced): luma exact, chroma off, U 17 dB and V 9 dB; progressive 4:2:2
  (`h264422`) exact. MPP's `vdpu382` H.264 HAL sets the same strides for 4:2:2 and 4:2:0, frame or
  field, and no chroma plane register exists: next, vendor's MPP on the same clip.
- VP9 profile 2 on next2, the 3518: every size to 8192x4320 matches software frame by frame. 4K, the
  clip 61 times over less once, to drop the start-up: 65 fps linear, 83 fps AFBC.
- M2 Plus: next2 as the others (parity, PVTM), and Wi-Fi: soak ping loss 1.1%, loaded download 120
  Mbit/s against the last run's 134. Its vendor 6.12 hung after its reboot test until a power cut by
  hand (the M2 Plus is on no strip port). Not hotter on next2. The 3518: idle 48.9 °C against 43.1,
  CPU load 59.4 against 53.1, soak 66.1 against 60.
- The rule's names: the run took `.local` names, and this Mac lost them mid-run; collected again by
  bare name (`AGENTS.local.md`), the R69-1 as `cnc` past the Mac's own ssh alias.
- `h264i422` on vendor 6.1 through MPP: the decoded frame's chroma U 17.5 dB, V 9.2 dB, as next2's;
  MPP's de-interlaced frames worse. The datasheets (RK3528, RK3528A, RK3518) list H.264 BP/MP/HP
  only, neither High 4:2:2 nor High 10, both of which decode exact, and say YUV422 output "is
  supported by H.264"; of fields they say nothing. So the hardware does it, and both drivers miss a
  step. A refusal patch refuses it on the RK3528 until ours decodes it.
- `h264i422`, narrowed on next2 with a debug kernel (no refusal), each run checked for hardware
  frames: FFmpeg decodes in software after the refusal despite `-nosw_fallback`, which made two
  experiments read as fixes until checked.
  - Luma exact in every variant: intra only, no deblocking, CAVLC. So the bitstream parses right.
  - Row buffers ruled out: each at 400%, alone or all, the same U 14.85 / V 9.79 dB.
  - The SPS height as the frame's, not the field's: no change, and the first frame breaks.
  - x264's `fake-interlaced` with `tff=1` failed as MBAFF did: `tff=1` turns MBAFF back on, so that
    clip was MBAFF too.
  - The chroma picture is mispredicted, not misplaced: no constant row shift fits; flat areas a
    shade off, errors every 32 chroma rows carried down and right, as intra prediction carries them.
  - MPP's "same failure" was read from frames not aligned one to one; not evidence.
- A clip that really is `fake-interlaced` (`frame_mbs_only` 0, `mb_adaptive_frame_field` 0, read
  back with `trace_headers`): bit-exact in hardware. The fault is 4:2:2 in MBAFF. The refusal is
  narrowed to it (`media-rkvdec-rk3528-refuse-mbaff-422.patch`); field pictures (PAFF) untested, no
  encoder at hand writes them. `video.py` gains `h264i422frame`; the debug row-buffer and SPS
  patches go, their answers here.
- The de-interlace case judged luma alone; it now judges chroma too, the psnr parse shared with the
  decode cases. `h264i422frame` is signalled progressive (FFmpeg's libx264 writes no field order
  under `fake-interlaced`), so the case names `setfield=tff` on both sides; without it the two
  de-interlacers guessed opposite orders, 28.8 dB. IEP2 on the 3518, against bwdif: 4:2:0 42.4 /
  36.1 dB, 4:2:2 42.3 / 38.7 dB (luma / worst chroma).

## 2026-11-26 — the RK3528's delay-line taps, read after the DLL locks

- The earlier taps patch read the DLL's lock value before the DLL was started: every tap was set
  against a stale lock, hence every eMMC read failing on the HK1. Rockchip's
  `dwcmshc_rk3568_set_clock` reads it once the DLL locks, as `(STATUS0 & 0xff) * 2`, then sets the
  receive clock (gated), transmit (HS200 12, HS400 6), command (6, both edges, HS400) and strobe (3)
  against it. The patch now does the same, HS200's transmit tap included; checkpatch clean.
- The HK1 on next2's HS200 tree failed card init one boot in two (`error -110`, from its serial):
  HS200 there is no workaround either.
- Each box by kexec into next2 with root read-only, then a 512 MiB direct read twice and three 4 MiB
  random patterns written direct to the unused `boot0` and read back, `boot0` zeroed after:
  - 3518, HS200 99 MHz: reads agree, writes verified, no eMMC errors; vendor 6.1 the same at 100.
  - 3518D, high-speed 49.5 MHz: the same; vendor at 50.
  - R69-1, HS200 99 MHz: the same; vendor at 100. The read hashes differ between kernels where
    vendor's read-write root wrote in the first 512 MiB between runs; within a kernel they agree.
  - M2 Plus: off the network, not checked.
  - HK1, vendor 6.1 only so far: HS400ES at 100 MHz, not the tree's 150, all clean. next2 drove
    HS200 at 148.5 MHz.
- kexec next2 into next2, the 3518: reset, back on 6.1 by the watchdog and the default; it
  reproduces. Ruled out: the watchdog (89 s, next2 on the network in ~20 s); `/proc/kcore`, absent
  on vendor too. kexec-tools places the second kernel's segments higher from next2 (initrd
  0x7b00000, tree 0x8dea000, purgatory 0x8e00000) than from vendor (0x4130000, 0x2700000,
  0x2716000): next2 keeps its own tree and initrd reserved at exactly the addresses vendor's kexec
  used. Both kernels see one RAM range from 0x200000, no holes, no secure reservation, so the higher
  placement alone explains nothing yet. pstore after the reset is empty on vendor, which maps
  ramoops at the same 0x110000: the second kernel's console needs a serial line.
- glmark2 at 2.2× vendor on next2 (3518D 117 against 53, M2 Plus 116 against 54): both bind `lima`
  with the same Mesa, `simple_ondemand`, 700/800 MHz OPPs. DDR during the run: vendor's
  `dmc_ondemand` holds 666 MHz, next2's fixed 786, 18% at most. The clock tree during the run:
  vendor's `scmi_clk_gpu` at 300 MHz, enable count 0, while its devfreq reports 800; next2's at 800,
  enabled. Vendor's OPP never reaches the GPU clock, so the GPU runs at its 300 MHz floor (800/300 =
  2.7×, the rest DDR and the CPU). next2's number is the GPU's; vendor's is vendor's gap. From the
  clock tree's rate, not a measured clock: likely, not verified.
- `crypto.bench.ecb(des)` read "not run" on the R69-1 and M2 Plus: `ecb-des-rk2` had no 4096 B rate.
  On the 3518 five tcrypt runs give every size, 177 MB/s at 4096 B. The runs kept no kernel log, so
  the bench now names tcrypt's own failure line where a size has no rate.
- "next2 idles 5–8 °C over vendor" was the run's order, not the kernel. `temp.idle.c` was read once
  at the start of each kernel's run, and the kernels run in turn: on the 3518D vendor 6.1 47.7,
  vendor 6.12 52.7, next2 53.3, both later kernels warm from the tests before. Measured alike, two
  minutes idle each: both kernels 44.4 falling to 42.7 °C, both at 1416 MHz the whole minute (the
  3518D's table is 1200 and 1416), neither with cpuidle. The CPU rail: next2's PWM sets 1667 ns of
  5000 for vendor's requested 1700, a 24 MHz tick down, ~3.8 mV on the 746–1201 mV map: not heat.
  `temp.idle.c` is now read once the box stops cooling (no lower reading for 60 s, 300 s at most),
  with `temp.idle.cooled.s` beside it. The todo item goes.
- The 3518D's CPU stays at 1416 MHz idle on both kernels: one transition in 321 s of vendor 6.1;
  forced through `userspace`, 1200 reaches `scmi_clk_cpu`. The governor skips 1200 as inefficient,
  the energy-model todo's case, not a clock that will not move.
- The 3518D's eMMC write "18% under vendor" was the run's order too: in that run vendor 6.12 wrote
  32.8 against 6.1's 37.6, reads equal on all three. Alternating kernels, two minutes' rest each,
  the suite's fio write (512 MiB, 1 MiB, depth 32, direct, 30 s) twice a boot: vendor 31.0, 32.4,
  34.0, 34.0; next2 33.2, 33.6, 32.5, 31.0 MB/s. Means 32.9 and 32.6: no gap. The todo item goes.
- PVTM against the CPU PWM: next2's `pwm-rockchip` rounds the duty down (`mul_u64_u64_div_u64`),
  1667 of 5000 ns read back for 1700 asked, one 24 MHz tick, ~3.8 mV on the 746–1201 mV map; about
  1% of a ring oscillator's count at most, short of the 2.5–4% gap. Vendor's actual duty unread: a
  `/dev/mem` read of the PWM went to registers whose bus clock `pclk_pwm0` next2 gates between calls
  (enable count 0; vendor keeps it at 1), and read 0. Against the rule; nothing hung.
- Vendor's `pwm-rockchip` rounds the duty to the nearest tick (`DIV_ROUND_CLOSEST_ULL`), mainline's
  down, as the PWM API asks of `.apply`: for 1700 ns, vendor 41 ticks (1708 ns), next2 40 (1667). On
  the 746–1201 mV map: vendor ~901.4 mV, next2 ~897.0 at the same OPP, next2 4.4 mV lower at every
  OPP the rounding hits. The direction PVTM's lower count points to; likely not all of it.
- The M2 Plus "down" at 01:02 UTC was a suspend: logind logged "Power key pressed short", most
  likely the IR remote pressed by accident, then suspend (deep) and a wake later on its own. Up
  since its last regression; not cycled, no fault.
- IR remotes across boxes: the 3518, 3518D and M2 Plus trees take nine remote codes each, the HK1
  eleven, the R69-1 nine; `0xff00`, `0x1dcc`, `0x7f80`, `0xfe01`, `0xdd22`, `0x3bc4` and `0x4040`
  are on most, each with a power key. One remote's power press reaches every box that takes its
  code: the M2 Plus's 01:02 suspend fits a press meant for another box. Stock Android has the same
  tables. A dual-mode remote paired over BLE reaches its own box alone.
- The glmark2 gap, by scene (`build`, fps): 3518D vendor 6.1 with `SCMI_CLK_GPU` at 300 MHz 86; the
  HK1 vendor 6.1 at 800 MHz 108, vendor 6.12 128 (the HK1 session, its tree's `core` on
  `SCMI_CLK_GPU`, `dc27cb7`); next2 177 (3518D), 192 (M2 Plus). The clock is real and worth about a
  quarter; vendor at 800 MHz is still 1.4–1.6x short of next2. The other trees name `ACLK_GPU_MALI`
  as `core`, so vendor's devfreq moves the CRU clock and leaves `SCMI_CLK_GPU` at 300 MHz.
- `crypto.bench.sm3` at 4 KiB: the engine 97–102 MB/s against the CPU's 80–85 on the three RK3518
  boxes; on the M2 Plus (RK3528, a faster CPU) the CPU 104 against the engine's 93 (96 last run,
  inside the slack then). One priority serves both SoCs: the engine stays the default, freeing the
  CPU; the M2 Plus's line fails by 1%.
- The HK1 on next2 with the corrected taps patch, its HS200 tree, three boots by kexec, root
  read-only: HS200 at 148.5 MHz each time, no `-110`, no "Can't reduce the clock" line, no eMMC
  error; 512 MiB direct read 75.6–76.6 MiB/s, hashes agreeing; three 4 MiB `boot0` writes a boot
  verified, 51.5–59.5 MiB/s. Before the patch, card init failed one boot in two. `kexec_once` first
  refused the HK1 and the M2 Plus: no `fdtput`, and a 22 November `tvb-base` without
  `KExecWatchdogSec`; rebuilt and installed with `device-tree-compiler`.
- The M2 Plus's GPU rail, the HK1 session's question: vendor 6.12 drives `vdd_gpu` at full PWM duty
  (5000 of 5000 ns, 1148 mV, the regulator's top; the OPP table's is 1000) while the GPU idles, 873
  mV only while it renders; vendor 6.1 holds 873 mV. Handed to the lima patch's owner.
- The HK1 at HS400ES on next2, the same three boots with its tree's `mmc-hs400-1_8v` and
  `mmc-hs400-enhanced-strobe` back: enhanced strobe at 148.5 MHz each time, no eMMC error; 512 MiB
  direct read 102.0–102.3 MiB/s (HS200 76), hashes agreeing; `boot0` writes verified, 54.7–62.0
  MiB/s, the first boot's 20.4, 10.2, 11.2. The HK1's next2 tree drops its HS200 hunk; the
  regenerated `board.dtb` decompiles, sorted, to the tree tested.
- The 3518's idle heat, controlled: vendor 6.1, then next2 by kexec, then 6.1, each idle 15 minutes,
  read every 3: next2 settles at 44.4 °C from 9 minutes, 6.1 at 39.4–40.0 from 7. A real ~4 °C gap
  on this box, where the 3518D and R69-1 measured alike show none; back on the todo page, scoped to
  the 3518. Its Seekwave Wi-Fi, the power domains and the clocks left on are where the boxes differ.
- The 3518 again, an hour later: 6.1 at 39.4 °C, then next2 by kexec steady at 37.2 for 12 minutes.
  Two controlled comparisons on one box, +4.4 and −2.2 °C: the shelf's own drift, as the other
  boxes' regressions start and stop beside it, is larger than any kernel gap. Interrupts at idle
  (11: ~330/s both; IPI5 79 against 134/s), Wi-Fi power save off on both, 294 against 389 clocks
  enabled: no difference yet tied to heat. The todo now asks for a reference box read at the same
  moments.

## 2026-11-27 — the HK1's first full next2 regression, HS400ES

- `build/validate/regression/2026-11-27/hk1-rbox-k8s`: next2 with the HS400ES tree and the corrected
  taps: every step done; storage on the HS400ES root, display, the video suite's 16384x8640 encode
  (refused by next2's 4096 clamp) all pass. Failures: input and `bt_default` parity, a PVTM bin,
  `crypto.bench.sm3` (the RK3528's CPU 104 against the engine's 79 MB/s, as the M2 Plus), and 10-bit
  decode and 4:4:4 encode input "broken".
- Those video failures were a stale FFmpeg: the HK1's `ffmpeg9` was installed 26 November 14:58,
  before `0064`–`0066`, over the deb the runner had placed and marked `.installed`; the runner
  trusted the marker. `regression.py` now also compares each deb's `md5sums` with dpkg's installed
  copy (`/var/lib/dpkg/info/<package>.md5sums`; for a deb that ships none, the list dpkg writes,
  each data file's MD5 in archive order), and reinstalls on a difference. Checked against the HK1:
  `tvb-base` and the next2 kernel match, `ffmpeg9` differs.
- Vendor 6.1 on the HK1: the video step's 16384x8640 H.264 encode left the box off the network, no
  watchdog reset; port 0 cycled after an hour. The 2 GB boxes skip that case for memory. The HK1
  session's `0067` refuses past 8192 in FFmpeg; the kernel wedge is its todo.
- The HK1's next2 video cases again with the current `ffmpeg9`: H.264 10-bit, HEVC Main10, VP9
  profile 2 at 1920x1080, 1080x1920 and 3840x2160, their concealment, `hevc10hdr` decode and its
  signalling, every H.264 encode input (`nv24`, `nv42`, `yuv444p` 35.3 dB): all pass.
- Vendor 6.12's rail, the HK1 too: from boot until the GPU first sets a voltage, its supply's PWM
  sits at full duty, `vdd_logic` at 1006 mV, the regulator's top; 912 mV at 800 MHz, and held after.
  General to 6.12, as on the M2 Plus's `vdd_gpu`; with the lima patch's owner.
- next2 does not share vendor 6.12's full-duty rails: the M2 Plus booted into next2, 86 s up, GPU
  suspended and never used: `vdd_gpu` 1350/5000 ns, 824 mV; `vdd_cpu` 3900/5000, 964 mV; `vdd_logic`
  2800/5000, 874 mV. The HK1 session traced 6.12's to Rockchip's enable path applying
  `regulator-init-microvolt` only at duty 0, after upstream's `pwm_regulator_init_boot_on`.
- The HK1 session's 6.12 regulator fix on the M2 Plus, a real boot of the 05:26 debs: `vdd_gpu` 900
  mV at 2200/5000 ns with the GPU never used, where it sat at 1148. Installing that kernel moved the
  M2 Plus's default to `l0`, next2 (no `U_BOOT_DEFAULT` there), and its next reboot came up on
  next2: put back to `l3`, the todo's case again.

## 2026-11-27 — driver gaps: the PWM rails' minimum, composite in split 03

- `regulator-pwm-reach-the-requested-minimum.patch`: `pwm-regulator` set the duty its formula gave
  and the PWM rounded it down, the lower voltage on these rails, and reported the duty asked, not
  the one run. It now reads the PWM's own state (`pwm_get_state_hw`) for the voltage it reports, and
  after a set steps the duty toward the higher voltage until that state reaches the requested
  minimum, never past the maximum. The 3518 on next2: `vdd-cpu` asked 2014 ns, ran 2000, reported
  928 mV, at or over each OPP's minimum. CPU PVTM 1484 at 950.75 mV, bin L3 (the last regression L2;
  vendor 1558, L5): one boot, so the rail's share of the gap is not separable; about 5% stays.
- A kexec from that next2 into next2 with a command-line word: reset, back on 6.1 by the watchdog,
  the todo's case. From 6.1 it boots.
- Composite in line-buffer split `03` (`rockchipdrm.esmart_lb_mode=3`, one boot by kexec): Esmart3
  composite's plane, PAL and NTSC set, both writebacks keep the colour bars. With `02` (Esmart2) on
  four boxes in the last regression, composite works in both splits; the todo item goes.
- `crypto-rockchip-rk2-gcm.patch`: GCM for AES and SM4 on the crypto v2 engine, as Rockchip's kernel
  drives it: the associated data and the text one DMA list of two items, the first marked
  `STRING_AAD`, their lengths in `CH0_AAD_LEN` and `CH0_PC_LEN`, the 12-byte IV loaded as given, the
  tag from `CH0_TAG_0..3` after `TAG_VALID`. Both are copied into one 64 KiB coherent buffer per
  request; empty data or text, or more, go to software. The 3518, next2: `gcm-aes-rk2` (priority
  200, under the CPU's) and `gcm-sm4-rk2` (300) register and pass their self-tests; tcrypt mode 224,
  `gcm(sm4)` on the engine, 558584 engine interrupts over the run: 51.8 MB/s at 4 KiB, 32.0 at 1
  KiB, 0.9 at 16 B. tcrypt's AEAD speed modes take a name, not a driver, so `gcm-aes-rk2`, under the
  CPU's, is timed by none; the bench's AEAD line is a todo with the rest. CCM: the mode exists
  (`0x07`), vendor never drives it.
- The VP1 underflow at a 4K HDMI teardown with composite lit, the 3518 on next2: not reproduced. No
  console holds either output here (no fbdev; `video=Composite-1:d`), so a client must: one
  `modetest` per output cannot both be DRM master, and one `modetest` with two `-s` builds one
  4560x2160 framebuffer the driver refuses. Reproducing it needs per-CRTC framebuffers and one CRTC
  disabled, `display.py`'s atomic path: the check to write before the fix.
- RK3528 FE PHY against vendor's `rk630phy.c` (T22, PHY address 2): `config_init` writes page 6
  register 0x14 as `0x10c8`, receive detect at 260 mV; a delayed work (500 ms with signal, 1 s
  without) reads the thermal zone the tree names (`rockchip,thermal-zone = "soc-thermal"` in every
  factory tree here) and sets 160 mV (`0x1088`) over 85 °C, no hysteresis; the same work tunes the
  ADC for long cables (page 6 reg 0x10, `0x555e` or `0x5540`) from link and packet counts. next2
  wrote `0x1088` always: `net-phy-rockchip-rk3528-fephy.patch` now writes `0x10c8`, folded in as the
  patch is not yet upstream. The 85 °C switch and the long-cable tuning need a binding for the zone
  and a service task: the todo. Only the HK1 has its internal port cabled; its test waits on the HK1
  session.
- The HK1's cabled FE PHY, 100 full, `iperf3` to `plex` 10 s each way: vendor 6.1 93.8 / 94.2
  Mbit/s, 0 retransmits; next2 at 160 mV 94.1 / 94.0, 0; next2 at 260 mV 94.0 / 94.0, 2; link up ~2
  s after configuring each time, no receive errors. No regression on this short cable; the setting's
  gain, a weaker signal detected, needs a long or poor one. The register is not read back: its page
  is reached only by writing the page select.
- A kexec from vendor 6.12 into next2 reset the HK1 too, as from next2 into next2 on the 3518; from
  vendor 6.1 it boots.
- The idle CPU at 1416 MHz, 1200 skipped: vendor 6.1 does the same on the 3518D (one transition in
  321 s), and it is the energy model's right answer, not a gap: two steps at one voltage cost the
  same energy a cycle, so the lower is only slower, and running at the higher one then idling costs
  no more. The todo item goes.
- The HDR overlay item against the datasheets (RK3528, RK3528A, RK3518 alike): "HDR10, SDR2HLG, HDR
  VIVID, HLG"; no HDR to SDR, which the stock composer also refuses on the RK3528 ("RK3528 TV
  unsupport HDR2SDR"). next2's SDR to HDR stage is a programmable inverse gamma before a fixed PQ
  mode (`0x203`, `4913`); HLG there needs an HLG curve in DRM's colorop API, which 7.3 lacks (sRGB,
  PQ 125, BT.2020, gamma 2.2), and Vivid's dynamic metadata has no Linux interface. The item is now
  those two, waiting on the interfaces; `research/rk3528-hdr` stays for the tables.
- DDR rate changes against their spacing, the R69-1 on next2 by kexec, `userspace`: six changes 2 s
  apart (780, 528, 324 MHz) held; the seventh, 780 → 528 MHz, again 2 s after the last, hung the
  SoC, the watchdog back to 6.1. A change can hang at any spacing, not only under a second; vendor's
  load scaling hung the M2 Plus the same way (2026-11-06), and vendor stays up only by never
  changing the rate in use. Its `devfreq-dmc` cooling device is in no thermal zone's cooling map
  (the maps take `cpu0` and the GPU), so it never moves either. next2 holds the top trained rate and
  registers no DMC cooling device: one would only expose the hang. The parity line stays reported,
  the todo says why.
- Vendor's crypto v2 list (`crypto_v2_algs[]`): CFB and OFB for AES, SM4, DES and TDES, which Linux
  dropped from its crypto API; XTS for SM4; GCM; RSA by the PKA. The mode codes in
  `rk_crypto_v2_reg.h` go further than vendor drives: CTS 2, CCM 7, CMAC 9, CBC-MAC 10, none used.
- `crypto-rockchip-rk2-xts-sm4-cts.patch`: `xts(sm4)` on the AES XTS path (two key banks, no
  key-size bits) and `cts(cbc(aes))` on mode 2, any length from a block as one DMA item. The 3518 on
  next2: both pass their self-tests, CTS's vectors of 17, 31 and 47 bytes on the engine; `xts(sm4)`
  176.7 MB/s at 4 KiB, 784136 engine interrupts over tcrypt's run.
- CCM on the crypto v2 engine, mode 7, three IV layouts by a boot parameter, the 3518: the IV as
  Linux passes it and the nonce alone give wrong results; A0 as the IV with B0 and the
  length-prefixed data built in software gives the right result once, then `-110` on the next
  request, a reset before each job and `TAG_VALID` cleared or not. Not offered; the experiment and
  its table are in `research/rk3528-crypto-ccm/`.
- `crypto-rockchip-rk2-rsa.patch`: raw RSA on the crypto v2 engine's PKA, Rockchip's sequence (the
  length and map tables, NP = 2^(bits + 132) / N by the PKA's own shifts and divisions, then
  `MOD_EXP`), every wait bounded where Rockchip's spins, the SRAM hand-over included. One difference
  kept on purpose: Rockchip's register-clearing loop stops at the count, not first plus count, and
  clears one register of the three it is asked for. The 3518 on next2: `rsa-rk2` and
  `pkcs1(rsa-rk2,sha256)` pass their self-tests; a kernel signature (`keyctl pkey_sign`, PKCS#1,
  SHA-256) verifies under OpenSSL. Signing by `keyctl`, 20 each: the engine 9.1/s at 2048 bits and
  1.4/s at 4096, generic RSA 31.2/s and 5.3/s, its CRT the difference; OpenSSL 133.7 and 19.7/s.
  `rsa-rk2` ranks 50, under generic's 100; CRT on the PKA is the todo.
- kexec from next2 into next2, bisected on the 3518 by unbinding drivers before the jump (the script
  detached on the box, its log synced first): the ten media devices unbound, still a reset; the
  fourteen I/O devices unbound, next2 booted (Wi-Fi among them, so it came up unreachable, read back
  from the journal); USB, Ethernet and audio unbound, a reset; I2C2 (`ffa60000`, an enabled bus with
  nothing on it) unbound, next2 booted, and in that next2 I2C2 failed to bind, silently. A clean A/B
  from 6.1 then left the box unreachable with nothing unbound and no watchdog reset, and the journal
  does not keep every kexec'd boot. Leading suspect: I2C2 left mid-state across the jump. Not
  confirmed: a reset, a hang and a boot without Wi-Fi look alike from the network; the serial
  console settles it.
- `media-rockchip-iep2-frame-per-frame.patch`: IEP2's one-frame modes behind a driver control,
  `V4L2_CID_ROCKCHIP_IEP2_FRAME_PER_FRAME` in a range reserved for the driver: I5O1T or I5O1B
  mid-stream, I1O1T or I1O1B at the edges, the first field's, one capture buffer a job. Vendor's
  modes: DISABLE 0, I5O2 1, I5O1T 2, I5O1B 3, I2O2 4, I1O1T 5, I1O1B 6, PD 7, BYPASS 8, DECT 9. The
  3518, `v4l2-ctl`, ten 1080 NV12 frames as `interlaced-tb`: 18 frames out with the control off, 9
  with it on (no stop sent, the tenth undrained); each one-frame output against the two-frame run's
  first-field frame 62 dB to identical, against its second 33–35 dB.
- SDR to HLG on next2: `drm-colorop-hlg-inv-eotf.patch` adds DRM's fixed curve "HLG Inverse EOTF",
  BT.2100's for the 1000-nit reference display (system gamma 1.2, the inverse OOTF weighting each
  component by the luminance of all three); `drm-rockchip-vop2-rk3528-sdr2hlg.patch` offers it as
  the pipeline's last curve beside PQ's, the pipeline now "SDR to HDR". HLG's multiplier is SDR
  white as a share of the peak, 2^-16 to 1, the white term −log10(m)·850; `SDR_CFG_COE0`'s high half
  −171, `SDR_CFG_COE1` 4094 and `SDR2HDR_CTRL` bit 3 (vendor's `sdr2hdr_dstmode`), the HLG terms
  `display.py` `RK_TARGETS` had by writeback on the vendor kernel. The 3518D: `display.py` colorop
  (was sdr2pq) SDR to PQ and to HLG at 203 nits, 7 colours each within 1 code; the refusals as
  before; the suite 80/0.
- HDR Vivid, what it takes: the vendor's dw-hdmi sends no CUVA InfoFrame; the RK3528's "HDR VIVID"
  is the VOP's hdrvivid engine tone-mapping from the frame's dynamic metadata, its curves (264-word
  tone table by DMA, 81 gamma points, 9 modifiers, PQ gamma and HLG terms) all from the stock
  `libhdr_params_parser.so`, CUVA's basic and spline tone curves and a register generator a mode.
  FFmpeg already parses the metadata (`AV_FRAME_DATA_DYNAMIC_HDR_VIVID`).
- `video.py` `fields`, the IEP2's one-frame control unattended: ten 1080 frames, the control off,
  then on. The first run on the 3518D: 18 and 9 frames, the one-frame outputs 49.8 dB at worst
  against the first-field frames, 35.3 at best against the second's; the next, 61.9. The same input
  differed run to run: hashed per frame, the first job (the frame alone) alike every run, every
  later job, motion read, different each run, in the shipped two-frame mode too. The motion and
  motion-vector buffers were the device's, never cleared, so each stream started from the last one's
  motion history, and two streams at once would share it. Folded into `media-rockchip-iep2.patch`:
  each stream allocates its own at its start, zeroed, freed at its stop. `fields` now runs the
  two-frame mode twice and needs the two alike.
- The motion-history fix on the 3518D: `fields` twice, each 18 and 9 frames, the two-frame runs
  byte-identical, each one-frame output identical to its first-field frame (35.5 dB to the
  second's). `video.py` deinterlace as before: h264i 42.41 dB, h264i422frame 42.31, h264i422 (MBAFF)
  refused.
- The kexec reset, without serial: the FTDI adapter on `h96max-h313` hears no box. In the 3518's
  journal every next2 boot was entered from 6.1; no next2 entered from next2 logged a line, so the
  second kernel dies before journald. pstore reaches across the reset (systemd-pstore moves records
  to `/var/lib/systemd/pstore/` at boot, `/sys/fs/pstore` empty after): a sysrq panic on 6.1 and one
  on next2 both read back on 6.1. next2 into next2 with `panic_on_oops`, `softlockup_panic` and
  `hung_task_panic`: silent, 6.1 back 2 min 24 s later by the watchdog, no new record. Not the
  watchdog's limit: `tclk_wdt_ns` 24 MHz and 89 s on both kernels, past `KExecWatchdogSec` 80.
- `patches/ffmpeg/0068`: `deinterlace_v4l2m2m=rate=frame` sets the driver's "Frame per Frame"
  control, found by name, takes one frame a job and keeps the input's time base; a driver without it
  refused at configuration. `video.py` deinterlace runs each clip at both rates against bwdif's.
  First run on the 3518D: `rate=frame` 27.2 dB, the edges exact and the middle frames matching
  nothing. Saved to files, each `rate=frame` frame was the `rate=field` first-field frame exactly;
  the comparison was wrong: bwdif halves its time base at either rate, so `setpts=N` paired frames
  one apart. Both sides now `settb=AVTB,setpts=N`: h264i 42.41 dB at a frame a field, 42.42 a frame
  a frame; h264i422frame 42.31 and 42.41; h264i422 (MBAFF) refused at both. MPP never runs IEP2's
  I5O1 modes (I5O2 mid-stream, I1O1T for the first frame alone).
- kexec next2 into next2, counted strictly (the second kernel's own command line read back): 3 of 3
  failed, the watchdog bringing 6.1 back each time. The earlier bisection by unbinding counted any
  next2 answering, a first kernel whose kexec never ran included: its results are void, I2C2's among
  them. Next: next2 into 6.1, to tell the first kernel's leftover state from the second's early
  boot.
- The decoder's downscale, `media-rkvdec-rk3528-scale-down.patch`: MPP's `vdpu382_setup_down_scale`
  enables `reg012.scale_down_en`, writes 2 to register 29's four five-bit ratios and the half stride
  to 30 and 31, the scaled luma and chroma bases at 198 and 199. Mainline's VDPU381 map matches the
  VDPU382's (its names are off by one: `reg164_180_ref_base` holds 16, ending at 179; the CABAC
  table at 197), 198 and 199 unused before 200. A COMPOSE on CAPTURE picks the ratio; a buffer holds
  the scaled NV12 picture, the full one, then the motion vectors, as Cedrus does. The row buffers
  and the decoder's strides keep the full picture; a TRY_FMT no longer moves the running layout.
  `video.py` scale now asks 1080, 540 and 270 lines of a 4K stream, recording the size asked. The
  3518D: half 67.0 dB (H.264), 65.35 (HEVC), 66.35 (VP9) against FFmpeg's area scale; a quarter and
  an eighth, with every ratio code from 1 to 24 by a test parameter, about 10 dB, most codes leaving
  the buffer unwritten: capped at half, asked smaller it gives 1920x1080. VP9 was first given a
  quarter for 1080 lines: its 2176 padded lines do not halve into 1080; the fit is now judged on the
  coded size. 10-bit, 4:2:2 and 4:0:0 stay full size; decode rates as before (4K H.264 60.1 fps,
  HEVC 114.1, VP9 72.0).
- PVTM's low-temperature floor, read against the vendor: `rockchip_system_monitor.c` polls the SoC
  zone and below `rockchip,low-temp` (10 °C, 5 °C hysteresis) raises each OPP to at least
  `rockchip,low-temp-min-volt` (900 mV), dropping those it would push past the rail's maximum, and
  goes cold before suspend. The 3518 on next2: CPU 900 and 925 mV (bin L3), GPU 875, 900 and 912.5
  mV (bin L4), the GPU on `vdd_cpu`, so the rail never falls under 900 mV and the floor changes
  nothing; vendor 6.1 holds 900 mV throughout. The GPU has its own rail on the M2 Plus and the H96
  Max RK3528 (`vdd_gpu`) and the HK1 (`vdd_logic`): there 875 mV is reached. Left a medium item: a
  thermal poll, runtime OPP voltages applied to the running OPP, and the suspend hook.
- `crypto-rockchip-rk2-rsa-crt.patch`: a private key carrying its CRT parameters signs by RFC 3447's
  CRT, as generic RSA does since 6.10: m1 = c^dP mod p and m2 = c^dQ mod q on the PKA, c reduced
  below each prime on the CPU first, the combination by the MPI library. The 3518 on next2, PKCS#1
  SHA-256 by the keyring, routed by priority (`CRYPTO_MSG_UPDATEALG`, the other PKCS#1 instance
  deleted): 23.5/s at 2048 bits and 4.6/s at 4096, from 9.1 and 1.4; generic 28.8 and 5.2, so
  `rsa-rk2` stays at 50. The first run of 8 fresh keys oopsed in `rk2_rsa_words`: the key parser
  keeps DER's leading zero byte, about half of private exponents carry one, and the words were
  counted without it but filled with it, past the array. Folded into
  `crypto-rockchip-rk2-rsa.patch`: the zero bytes dropped first. 24 fresh keys of 1024, 2048 and
  4096 bits through `pkcs1(rsa-rk2,sha256)` after, every signature verified by OpenSSL, no oops.
  `box.py` crypto.rsa does the same unattended.
- `box.py` crypto.rsa on the 3518, in-process through the keyring syscalls: 4 of 4 fresh keys
  verified at 1024, 2048 and 4096 bits; 29.9/s at 2048 bits through `pkcs1(rsa-rk2,sha256)`, the
  CPU's 31.2/s; the keyctl tool's own start-up was the rest of the earlier gap. Two wrong turns on
  the way: `struct keyctl_pkey_params` is 40 bytes, its seven spare words zero, and the signature's
  length must be the key's, nothing longer.
- VP1's underflow, reproduced on the 3518 by `display.py composite`: 10 `POST_BUF_EMPTY` lines (the
  rate limit's burst) within 2 ms of a composite mode set, the TV encoder's interlaced output on
  VP1. Per enable: without writeback 1 in 12, with it 3 in 12; a PAL mode set with NV12 writeback
  and a line-alternating picture, 8 of 8, NTSC 0 of 8. Vendor's `rockchip_drm_vop2.c` flags a VP1
  `POST_BUF_EMPTY` on the RK3528 and at the next frame start turns `p2i_en` off for a frame and on
  again, its comment: to re-sync the line parity, else odd and even lines go out in the wrong order.
  Writeback takes the current field, so it cannot show the parity the encoder sends: a TV check, the
  todo's 👤 item. The recovery, and an enable that does not underflow, are the todo.
- The FE PHY's 85 °C switch, folded into `net-phy-rockchip-rk3528-fephy.patch`: a delayed work reads
  the `soc-thermal` zone each second and clears page 6 register 0x14 bit 6 over 85 °C (`0x1088`, 160
  mV), sets it back under (`0x10c8`, 260 mV), bit 13 (10BASE-T) left to the link handler; cancelled
  at suspend and remove, restarted by `config_init` on resume. The zone is the SoC's by name: the
  factory trees' `rockchip,thermal-zone = "soc-thermal"` on the PHY node was dropped in translation,
  and names the zone every next2 tree has. A debug build's `hot_mc`
  (`net-phy-rockchip-rk3528-fephy-test-hot.patch`) moves the threshold. The 3518, no cable, link up:
  `box.py` `eth.eth0.hot` 160 mV at 44.4 °C in 0.4 s, back to 260 mV in 0.9 s. The long-cable tuning
  stays the todo.

## 2026-11-27 — research notes into the todo's appendices

- `research/rk3528-hdr/README.md` and `research/rk3528-crypto-ccm/README.md` are now the HDR Vivid
  and AES CCM appendices of `docs/todo/rk35xx-mainline.md`, beside the items they serve.
  `ccm-experiment.patch` moved to
  `patches/linux-rockchip-mainline/crypto-rockchip-rk2-ccm-experiment.patch`, in no kernel conf. The
  earlier entries' `research/` paths name where they were.
