# Rockchip on mainline

Experimental RK3528 patches for `rk35xx-next2`, the mainline kernel tested on the H96 Max M2 Plus.

| Patch                                                      | Adds                                                                                                            |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `dt-bindings-rk3528.patch`                                 | Media, PHY, thermal bindings                                                                                    |
| `dt-bindings-rk3528-audio.patch`                           | SAI/PDM fallback bindings                                                                                       |
| `dt-bindings-rk3528-core-grf.patch`                        | The GRF block holding the CPU PVTPLL                                                                            |
| `dt-bindings-vendor-prefixes-seekwave.patch`               | The `seekwave` vendor prefix                                                                                    |
| `dt-bindings-seekwave.patch`                               | The Seekwave SV6160 Lite loader's GPIOs                                                                         |
| `dt-bindings-rk3528-rga.patch`                             | The RGA2E, on the RK3288's interface                                                                            |
| `dt-bindings-rockchip-iep2.patch`                          | The IEP2 deinterlacer                                                                                           |
| `dt-bindings-rockchip-vdpp.patch`                          | The VDPP scaler                                                                                                 |
| `dt-bindings-rockchip-vop2-resets.patch`                   | VOP2 resets in the binding                                                                                      |
| `dt-bindings-rockchip-iommu-dlr.patch`                     | The IOMMU's attach-only flag                                                                                    |
| `dt-bindings-rockchip-grf-rk3528-pmu.patch`                | RK3528 PMU GRF compatible                                                                                       |
| `dt-bindings-rk3528-gpu-grf.patch`                         | RK3528 GPU GRF compatible                                                                                       |
| `dt-bindings-devfreq-rockchip-dfi-rk3528.patch`            | RK3528 DDR monitor compatible                                                                                   |
| `dt-bindings-rockchip-rk3528-dmc.patch`                    | RK3528 DMC binding                                                                                              |
| `arm64-dts-rk3528-media-display.patch`                     | SoC block descriptions                                                                                          |
| `arm64-dts-rk3528-dfi.patch`                               | PMU GRF and DDR monitor nodes                                                                                   |
| `arm64-dts-rk3528-gpu-grf.patch`                           | The GPU GRF node                                                                                                |
| `arm64-dts-rk3528-gpu-bus-clock.patch`                     | GPU bus at 498 MHz                                                                                              |
| `arm64-dts-rk3528-dmc.patch`                               | The DMC node and its table                                                                                      |
| `media-v4l2-afbc-formats.patch`                            | AFBC formats, Gaignard's RFC v2                                                                                 |
| `media-v4l2-afbc-nonsplit-formats.patch`                   | Non-split AFBC 16x16 formats                                                                                    |
| `media-rkvdec-rk3528.patch`                                | VDPU382 decoder match                                                                                           |
| `media-rkvdec-rk3528-refuse-mbaff-422.patch`               | rkvdec: 4:2:2 H.264 in MBAFF refused on the RK3528 until its chroma decodes right                               |
| `media-rkvdec-rk3528-scale-down.patch`                     | rkvdec: the RK3528's picture scaled down by half through COMPOSE                                                |
| `media-rkvdec-vdpu381-hevc-afbc.patch`                     | HEVC AFBC output, 8-bit and 10-bit                                                                              |
| `media-rkvdec-vdpu381-h264-vp9-afbc.patch`                 | H.264 and VP9 AFBC output                                                                                       |
| `media-rkvdec-vdpu381-colmv-compress.patch`                | Collocated MVs compressed                                                                                       |
| `media-videobuf2-dma-contig-noncoherent-attrs.patch`       | Non-coherent alloc, attrs it takes                                                                              |
| `media-videobuf2-dma-contig-dmabuf-cpu-access-sync.patch`  | Dma-buf CPU access syncs                                                                                        |
| `media-rkvdec-cache-hints.patch`                           | Cache hints on the capture queue                                                                                |
| `media-rkvdec-vp9-rename-get-ref-buf.patch`                | VP9 for VDPU381, 1/3                                                                                            |
| `media-rkvdec-vp9-common.patch`                            | VP9 for VDPU381, 2/3                                                                                            |
| `media-rkvdec-vdpu381-vp9.patch`                           | VP9 for VDPU381, 3/3                                                                                            |
| `media-hantro-rk3528-bindings.patch`                       | The RK3528 VPU's compatible                                                                                     |
| `media-hantro-rk3528.patch`                                | Hantro VP8 refused past 1080p                                                                                   |
| `media-hantro-vdpu2-mpeg1.patch`                           | MPEG-1 on VDPU2, by MPEG-2's controls                                                                           |
| `media-hantro-vdpu2-mpeg4.patch`                           | MPEG-4 Part 2 and H.263 on VDPU2                                                                                |
| `media-hantro-cache-hints.patch`                           | Cache hints on decoder capture                                                                                  |
| `media-hantro-recover-timeout.patch`                       | the core and its IOMMU reset after a timed out or failed job                                                    |
| `media-hantro-vdpu2-test-failure.patch`                    | Hantro: `fail_next_job`, a test parameter: the next VDPU2 decode times out (1) or faults (2), debug builds only |
| `media-verisilicon-vdpu2-done-only-when-ready.patch`       | VDPU2: a job done only on the ready bit, not on any interrupt                                                   |
| `media-hantro-rk3528-vdpu2-area-limit.patch`               | RK3528 VDPU2: 8160 macroblocks, either side to 1920; H.264 kept at 1920x1088                                    |
| `media-rga-shared-irq.patch`                               | A shared IRQ left alone while asleep                                                                            |
| `media-rga-rk3528.patch`                                   | The RGA2E through its own IOMMU                                                                                 |
| `media-rga-mirror-axes.patch`                              | RGA flips along the axis named                                                                                  |
| `media-rga-recover-timeout.patch`                          | RGA: a job that never ends is reset and failed, no reboot                                                       |
| `media-rga-rk3528-formats.patch`                           | RK3528 RGA2E: XRGB8888, NV15/NV20 sources, a 4096 destination                                                   |
| `media-rga-csc-quantization.patch`                         | RGA: RGB and YUV converted by the frames' matrix and range                                                      |
| `media-rockchip-iep2.patch`                                | IEP2 deinterlacer, V4L2 mem2mem                                                                                 |
| `media-rockchip-iep2-frame-per-frame.patch`                | IEP2: a frame per input frame, its first field's, by a driver control                                           |
| `media-rockchip-vdpp.patch`                                | VDPP scaler, V4L2 mem2mem                                                                                       |
| `thermal-rk3528.patch`                                     | TSADC                                                                                                           |
| `cpufreq-rockchip-pvtm.patch`                              | CPU OPPs at the chip's PVTM bin                                                                                 |
| `bluetooth-hci-h4-aic8800-bdaddr.patch`                    | The AIC8800's BT at Wi-Fi's + 1                                                                                 |
| `drm-lima-devfreq-cooling-energy-model.patch`              | GPU throttled by the power allocator                                                                            |
| `drm-rk3528.patch`                                         | VOP2, HDMI, PHY                                                                                                 |
| `drm-dw-hdmi-dblclk.patch`                                 | dw-hdmi takes 480i/576i on opt-in                                                                               |
| `drm-rk3528-hdmi-dblclk.patch`                             | RK3528 HDMI opts in                                                                                             |
| `drm-bridge-dw-hdmi-select-bus-format.patch`               | dw-hdmi alone picks deep colour, 4:2:0                                                                          |
| `drm-rockchip-dw-hdmi-rk3528-deep-colour.patch`            | RK3528 HDMI 10-bit and 4:2:0                                                                                    |
| `drm-bridge-dw-hdmi-colorspace.patch`                      | HDMI Colorspace: BT.2020 for HDR                                                                                |
| `drm-bridge-dw-hdmi-color-format.patch`                    | HDMI color format: YCbCr 4:4:4 and 4:2:2 on request                                                             |
| `phy-inno-hdmi-27027khz.patch`                             | 480p/480i at 60.00 Hz                                                                                           |
| `phy-rockchip-inno-hdmi-rk3528-scaled-pre-pll.patch`       | Any pixel clock near the table                                                                                  |
| `drm-rk3528-vop2-vp1.patch`                                | VP1 and Esmart3                                                                                                 |
| `drm-rk3528-vop2-bt656.patch`                              | VP1 to the TV encoder                                                                                           |
| `drm-rk3528-tve.patch`                                     | Composite PAL/NTSC encoder                                                                                      |
| `drm-rk3528-vop2-writeback.patch`                          | VOP2 writeback connector                                                                                        |
| `drm-rockchip-vop2-reset.patch`                            | VOP reset at bind, before its IOMMU                                                                             |
| `drm-rockchip-vop2-rk3528-aclk-gating.patch`               | aclk pre auto gating off                                                                                        |
| `drm-rockchip-vop2-scanout.patch`                          | Lit output for DDR rate changes                                                                                 |
| `drm-rk3528-vop2-afbc.patch`                               | AFBC scanout on Cluster0                                                                                        |
| `drm-rk3528-vop2-esmart-lb-mode.patch`                     | Esmart line buffers: tree, cmdline                                                                              |
| `drm-rk3528-vop2-cursor-plane.patch`                       | Esmart2 as HDMI's cursor plane                                                                                  |
| `drm-rockchip-vop2-cluster-mirror-afbc-only.patch`         | Cluster mirroring: AFBC buffers only                                                                            |
| `dt-bindings-rk3528-vop-gamma-lut.patch`                   | binding: the VOP's gamma LUT window                                                                             |
| `arm64-dts-rk3528-vop-gamma-lut.patch`                     | the VOP's gamma LUT window                                                                                      |
| `drm-rockchip-vop2-rk3528-gamma-lut.patch`                 | VP0's gamma LUT                                                                                                 |
| `drm-rockchip-vop2-lut-port-sel-fields.patch`              | gamma port select keeps the line-buffer split                                                                   |
| `drm-rockchip-vop2-rk3528-cluster-rotate.patch`            | Cluster0 rotates AFBC by 90 and 270                                                                             |
| `media-rkvenc-rk3528-source-formats.patch`                 | rkvenc: YUV and RGB sources on the RK3528; grey refused                                                         |
| `media-rkvenc-rk3528-more-sources.patch`                   | rkvenc: 4:4:4 sources; its 16-bit RGB hangs, refused                                                            |
| `media-rockchip-vdpp-formats.patch`                        | VDPP: NV21 in and out, NV24 and NV42 out                                                                        |
| `drm-bridge-dw-hdmi-frame-packing.patch`                   | dw-hdmi: frame-packed 3D modes                                                                                  |
| `drm-rockchip-dw-hdmi-rk3528-frame-packing.patch`          | RK3528: 3D frame packing                                                                                        |
| `media-rkvdec-h264-grey.patch`                             | rkvdec: H.264 4:0:0 as GREY                                                                                     |
| `media-rkvdec-vdpu381-rcb-sram-priority.patch`             | rkvdec: the SRAM mapped once, packed with the busiest row buffers, sized for the stream                         |
| `media-v4l2-mem2mem-run-next.patch`                        | mem2mem: a driver runs the next job at once, from a context that can sleep                                      |
| `media-rkvdec-run-next-from-irq-thread.patch`              | rkvdec: the next job started from the interrupt thread, not a worker                                            |
| `media-rkvdec-vdpu381-start-before-request-complete.patch` | rkvdec: the VDPU381 started before its request's controls complete                                              |
| `media-rkvdec-test-failure.patch`                          | rkvdec: `fail_next_job`, a test parameter: the next job times out (1) or faults (2), debug builds only          |
| `dt-bindings-crypto-rockchip-rk3568.patch`                 | crypto engine binding: Dawid Olesinski's v3, 2026-08-16, in review                                              |
| `crypto-rockchip-rk3568-offloader.patch`                   | crypto engine driver: the same series, patch 2/4                                                                |
| `dt-bindings-crypto-rockchip-rk3528.patch`                 | the RK3528's crypto engine in the binding                                                                       |
| `crypto-rockchip-rk3528.patch`                             | the RK3528's engine: only what its version registers flag                                                       |
| `crypto-rockchip-rk2-more-ciphers.patch`                   | crypto: CTR AES, SM4, DES/3DES, where the engine reports them                                                   |
| `crypto-rockchip-rk2-hmac.patch`                           | crypto: HMAC MD5/SHA1/SHA256/SHA512 in the engine                                                               |
| `crypto-rockchip-rk2-recover-timeout.patch`                | crypto: a failed job resets the engine itself, not by the CRU                                                   |
| `crypto-rockchip-rk2-hash-fallback-flags.patch`            | crypto: the hash fallback no longer reads past the caller's stack                                               |
| `crypto-rockchip-rk2-priority.patch`                       | crypto: AES and hashes rank under the CPU's faster drivers                                                      |
| `arm64-dts-rk3528-crypto.patch`                            | the RK3528's crypto engine node                                                                                 |
| `drm-rockchip-vop2-cluster-linear-ymirror.patch`           | Cluster Y mirror for linear buffers, RK3528/RK3576                                                              |
| `media-rockchip-vdpp-dmsr.patch`                           | VDPP: DMSR as the sharpness control                                                                             |
| `media-rockchip-vdpp-recover.patch`                        | VDPP: a failed or stalled job recovered, IOMMU then core, no reboot                                             |
| `media-rockchip-vdpp-test-failure.patch`                   | VDPP: `fail_next_job`, a test parameter, debug builds only                                                      |
| `media-rkvenc-vepu540c-test-failure.patch`                 | rkvenc: `fail_next_job`, a test parameter, debug builds only                                                    |
| `media-rkjpegd-test-failure.patch`                         | rkjpegd: `fail_next_job`, a test parameter, debug builds only                                                   |
| `crypto-rockchip-rk2-test-failure.patch`                   | debug: the next hash times out or wedges the engine                                                             |
| `mmc-sdhci-of-dwcmshc-test-taps.patch`                     | debug: HS400 delay-line taps set while the card runs, for a sweep                                               |
| `drm-rockchip-vop2-rk3528-esmart-regions.patch`            | Esmart regions 1–3 as overlay planes                                                                            |
| `asoc-rockchip-sai-12k-24k.patch`                          | SAI: 12 and 24 kHz                                                                                              |
| `asoc-rk3528-codec-12k-24k.patch`                          | RK3528 codec: 12 and 24 kHz                                                                                     |
| `arm64-dts-rk3528-sai0-sai1.patch`                         | SAI0 and SAI1 nodes                                                                                             |
| `arm64-dts-rk3528-emmc-txclk-tapnum.patch`                 | the eMMC's HS200 transmit tap as Rockchip sets it                                                               |
| `mmc-sdhci-of-dwcmshc-rk3528-taps.patch`                   | eMMC: the RK3528's delay-line taps, set against the DLL's lock value as Rockchip's kernel sets them             |
| `regulator-pwm-reach-the-requested-minimum.patch`          | pwm-regulator: the PWM's rounded duty never under the requested minimum; the voltage it runs reported           |
| `crypto-rockchip-rk2-gcm.patch`                            | crypto v2: GCM for AES and SM4, the engine computing the tag                                                    |
| `crypto-rockchip-rk2-xts-sm4-cts.patch`                    | crypto v2: XTS for SM4 and CTS for AES, as the engine's version registers offer                                 |
| `crypto-rockchip-rk2-rsa.patch`                            | crypto v2: raw RSA on the public key accelerator, under generic RSA's priority                                  |
| `crypto-rockchip-rk2-rsa-crt.patch`                        | crypto v2: RSA private keys by the CRT, the two exponentiations on the PKA                                      |
| `dt-bindings-rockchip-pm-config.patch`                     | The board's sleep configuration node                                                                            |
| `soc-rockchip-pm-config.patch`                             | BL31's sleep mode, wake sources and PWM regulators from the tree                                                |
| `dt-bindings-rockchip-pm-config-virtual-poweroff.patch`    | `rockchip,virtual-poweroff` in that node                                                                        |
| `soc-rockchip-pm-config-virtual-poweroff.patch`            | power-off as a sleep the remote ends, as Rockchip's kernel                                                      |
| `watchdog-dw-wdt-stop-at-power-off.patch`                  | the watchdog's counter stopped at power-off, which a firmware sleep keeps powered                               |
| `drm-rockchip-vop2-rk3528-sdr2hdr-colorop.patch`           | RK3528: SDR planes to PQ, a colorop pipeline                                                                    |
| `drm-colorop-hlg-inv-eotf.patch`                           | DRM colorops: BT.2100's HLG inverse EOTF as a fixed curve                                                       |
| `drm-rockchip-vop2-rk3528-sdr2hlg.patch`                   | RK3528 VP0: SDR to HLG, the HLG curve beside PQ's                                                               |
| `iommu-rockchip-attach-only.patch`                         | An IOMMU only its master enables                                                                                |
| `iommu-rockchip-reset-a-bank-stuck-on-a-fault.patch`       | IOMMU: an idle bank stuck on a replayed fault reset unstalled, not left wedged                                  |
| `media-rc-keymaps-h96max-m2-plus.patch`                    | The M2 Plus's IR remote keymap                                                                                  |
| `media-rc-keymaps-r69-1.patch`                             | The R69-1's IR remote keymap                                                                                    |
| `media-rc-keymaps-hk1-rbox-k8s.patch`                      | The HK1's IR remote keymap                                                                                      |
| `asoc-rk3528-codec.patch`                                  | Internal audio codec driver                                                                                     |
| `asoc-hdmi-codec-jack-type.patch`                          | HDMI codec reports a line-out jack                                                                              |
| `asoc-simple-card-link-jacks.patch`                        | simple-card: jacks for link codecs                                                                              |
| `asoc-rockchip-sai-tdm-lanes.patch`                        | SAI TDM: the lanes the channels need; 8-ch HDMI                                                                 |
| `net-phy-rockchip-rk3528-fephy.patch`                      | Integrated Ethernet PHY tuning                                                                                  |
| `net-phy-rockchip-rk3528-fephy-test-hot.patch` | test hook: the FEPHY's 85 °C threshold as `hot_mc`, debug builds only |
| `media-rkjpegd-v7-bindings.patch`                          | JPEG decoder binding, posted v7                                                                                 |
| `media-rkjpegd-v7-driver.patch`                            | JPEG decoder driver, posted v7                                                                                  |
| `media-rkjpegd-queue-memory.patch`                         | A queue takes at most 1/8 of RAM                                                                                |
| `media-rkjpegd-native-422-444.patch`                       | 4:2:2 and 4:4:4 to NV16 and NV24                                                                                |
| `media-rkvenc-rfc-bindings.patch`                          | Encoder binding, Golle's RFC                                                                                    |
| `media-rkvenc-rfc-driver.patch`                            | Encoder front end, Golle's RFC                                                                                  |
| `media-rkvenc-recover-timeout.patch`                       | rkvenc: a job that times out resets the encoder and its IOMMU                                                   |
| `media-rkvenc-rk3528-bindings.patch`                       | RK3528 encoder compatible                                                                                       |
| `media-rkvenc-rk3528-vepu540c.patch`                       | VEPU540C H.264 back end                                                                                         |
| `media-rkvenc-rk3528-vepu540c-hevc.patch`                  | VEPU540C HEVC back end, 32x32 CTUs                                                                              |
| `media-rkvenc-rk3528-vepu540c-jpeg.patch`                  | VEPU540C JPEG encode                                                                                            |
| `media-rkvenc-header-after-start.patch`                    | Parameter sets after start_streaming                                                                            |
| `pmdomain-rockchip-skip-qos-idle-only.patch`               | Idle-only domains: no QoS, posted                                                                               |
| `devfreq-rockchip-dfi-rk3528.patch`                        | RK3528 DDR monitor                                                                                              |
| `devfreq-rockchip-dfi-ddr3.patch`                          | The DFI counts DDR3                                                                                             |
| `devfreq-skip-suspended-device.patch`                      | No rate change while suspended                                                                                  |
| `devfreq-rk3528-dmc.patch`                                 | RK3528 DDR scaling                                                                                              |

The media, thermal, display and original binding patches were imported from
[W132D Linux](https://github.com/zte-cloud-computer/w132d-linux-mainline), commit
`d9bfd153f813b7f35280db6d356ca35106d37577`, `userpatches/kernel/w132d/`. The source pins Linux
7.2.10; these patches apply to the 7.3 stable kernel `rk35xx-next2` follows. No upstream submission
is recorded here.

HDMI output is RGB, at 8 and 10 bits a channel, with HDR's InfoFrame; YCbCr output is not done. The
decoder patch selects VDPU381 operations for VDPU382; the video matrix checks it.

`cpufreq-rockchip-pvtm.patch` is ours and not sendable as it stands: it reads the vendor's
`rockchip,pvtm-*` properties, which no mainline binding has, from the CPU OPP table the translation
keeps them in. It sets the CPU, then the GPU, to the measuring rate and voltage, reads each PVTPLL
count from the GRF and runs each at the bin it maps to; `apply=0` only logs it. It reads what the
vendor kernel does: the R69-1's CPU 1553 against 1552, bin 5; the M2 Plus's 1351 against 1361, bin
L2. The M2 Plus's GPU reads 1170-1175, bin L8.

`media-hantro-vdpu2-mpeg1.patch` is ours: VDPU2 decodes MPEG-1 in a mode of its own, as MPP drives
it. A sequence flag selects it and two picture flags carry MPEG-1's full-pel vectors; these extend
the stateless MPEG-2 controls, so they are our interface, read by our FFmpeg, until upstream has one
for MPEG-1.

`media-hantro-vdpu2-mpeg4.patch` is ours: VDPU2 decodes an MPEG-4 VOP or H.263 picture whole, with
the registers MPP gives it, on the private MPEG-4 controls of `patches/linux-sunxi/0805`, which come
with the VC-1 ones of `0422` they build on.

The three VP9 patches are a posted series, imported as written: patchwork series 1134753,
`<20260726-b4-add-rkvdec2-vp9-vdpu381-v1-0-180fb2d1f10c@gmail.com>`, by Venkata Atchuta Bheemeswara
Sarma Darbha. Its fourth patch, a stride alignment its reviewers agreed to drop, is not carried.
RK3528 takes VP9 through the VDPU381 variant like H.264 and HEVC; whether the VDPU382 decodes VP9 by
the same registers is the video matrix's to show.

`pmdomain-rockchip-skip-qos-idle-only.patch`, posted, keeps QoS saves and idle requests off RK3528's
idle-only domains (VPU, VO, RKVENC), which have no power switch. Without it, powering one off
faulted at the PMU acknowledgement offset `0x1120`. Its companion, skipping a deferring domain, is
not carried: RK3528's GPU domain defers on the CRU, and skipped it never registers.

`pmdomain-clear-failed-clock.patch` clears an error pointer before bulk clock cleanup. It addresses
the observed `__clk_put` warning on deferred probe. Selected by next2: the same deferred probe now
leaves taint at zero and produces no `__clk_put` warning.

`media-v4l2-afbc-formats.patch` is Benjamin Gaignard's "[RFC v2] media: Add AFBC pixel formats"
(linux-media, 2026-04-17), rebased to 7.3.4: the fill hook sits in `v4l2_fill_pixfmt_mp_aligned`,
which 7.3.4's `v4l2_fill_pixfmt_mp` wraps. Its split 16x16 formats are Cedrus's; reviewing it,
Nicolas Dufresne left the plain 16x16 names to RK35xx rkvdec's non-split output, which
`media-v4l2-afbc-nonsplit-formats.patch` adds.
