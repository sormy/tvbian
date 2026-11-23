# Rockchip: what is left, every board

- [ ] **RK3528 translation: the drops not shown safe on a box**: VOP2's `rockchip,grf`, the xHCI
      quirks, eMMC `use-v2-tuning` and enhanced strobe, the boot logo, `system-monitor`'s floors.
- [ ] **RK3528: the film plane in the mixed mode is black.** An HDR film at zpos 0 under SDR planes
      (`HDR_BYPASS`): the SDR planes map exactly, the film comes out black with `POST_BUF_EMPTY`,
      with Rockchip's own blob too. The register image is at fault, not the screen. The VOP then
      underruns until a reboot.
- [ ] **RK3528: HDR on a real HDR screen**, the picture by eye.
- [ ] **DDC/CI on `rk35xx-next`**, on one RK3528 box for them all.
- [ ] **No MPP once every Rockchip board runs mainline**: video through `rkvdec` and Hantro by V4L2,
      and what exists only for MPP retired: `tvb-va-driver`'s MPP backend and `libmpp` in it,
      `patches/mpp`, `patches/wpewebkit` `0001`, and our FFmpeg's `*_rkmpp` decoders.
- [ ] **RK3528: 4K60 video on a display plane in the desktop**: the GPU composites 4K at about 46
      fps, so mpv drops frames wherever `labwc` composites the video.
- [ ] **RK3528: H.264 at 3840x2160 60 fps**: MPP decodes a 25 Mbit/s High 5.2 stream at 43 fps.
- [ ] **MJPEG decodes in hardware through our FFmpeg.**
- [ ] **Optional: every codec the hardware decodes or encodes reaches our FFmpeg**, AVS, AVS+, AVS2
      and VC-1 included where the chip has them. For completeness more than use.
- [ ] **`display.py` passes with a real screen attached**, HDR or not.
- [ ] **VOP2: AFBC through a size change.** Cluster0 alone takes AFBC; whether it refuses an AFBC
      frame mid-play when the stream changes size.

- [ ] **Vendor 6.12: HDMI writeback after composite**: commits still succeed; a capture is refused.
- [ ] **Vendor kernels: an off-table HDMI mode at its own pixel clock**: 2256x1504 (235.7 MHz) runs
      the PHY at 1080p60's 148.5 MHz. Computed, as on next2, or refused.
- [ ] **The vendor kernels' decoder reset at probe**: warm boots of the HK1's 6.1 froze in its
      probe, a power cut alone clearing it; next2's own driver never froze. The vendor resets it on
      errors and at shutdown only; `rkvdec2_reset`, CRU lines in the PMU idle request, is the
      candidate at probe, not the IOMMU reset, which froze every boot.
- [ ] **Vendor kernels: the GPU on stock's SCMI clock**, 800 MHz, not the CRU's 498 MHz cap: after
      lima's throttling, as on next2, and its OPPs at the chip's PVTM bin; and `gpu-bus` scaling
      `vdd_logic` with it, once `rockchip_bus.c` asks for its `bus` regulator, not `pvtm`.
- [ ] **Check the `ttyFIQ0` login on a serial header.** Every Rockchip board's console is `ttyFIQ0`,
      seen in `/proc/consoles` with its getty running; never on a cable.

- [ ] **RK3528 boards: a 4K display on the R69 and the 3518.** Every RK3528 `board.dts` sets
      `esmart_lb_mode = [02]`, a 4K line buffer for Esmart0, where the factory's `[03]` corrupts the
      right third of a 4K frame; ✅ on the 3518D only. Check `3840x2160p60` full-screen with no
      fringe on the right, then that a 1080p display still comes up clean.

- [ ] **The R69's Wi-Fi comes back after every warm reboot.**
- [ ] **6.12: a `_regulator_put` WARNING in the USB2 PHY's deferred probe**, now and then on the
      3518D and the R69. The probe fails `IRQ index 0 not found`, after
      `vcc5v0_host: could not add device link ... -ENOENT`; its cleanup puts the regulator. Taints
      the kernel (512).

- [ ] **RK3528: name the DDR parameters a vendor tunes.** The H96 Max 3518's factory DDR init is
      rkbin's `rk3528_ddr_1056MHz_4BIT_PCB_v1.11.bin` with three bytes changed in its parameter
      table; read which fields with `ddrbin_tool`, and whether rkbin's blob with them set equals a
      factory loader, so an imported board's DRAM need not wait for its dump.

- [ ] **AIC8800 Bluetooth address as on sunxi.** The chip's eFuse first, then the Wi-Fi's own
      address plus one, wherever it came from; today a tree address beats the eFuse, and the
      fallback is the SoC serial's.

- [ ] **RK3528 and RK3518 on mainline, to replace the vendor kernel.** Left, by size:

      | Size   | Gap                                                                                       |
      | ------ | ----------------------------------------------------------------------------------------- |
      | Small  | VP9 profile 2 at 2160p decodes ~61 fps linear; its AFBC speed and 2160p60 pacing unmeasured |
      | Small  | VP1 underflows (~10 POST_BUF_EMPTY) as a 4K HDMI console is torn down, composite lit      |
      | Small  | DDR held at its top rate as vendor; simple_ondemand selectable, untested under 4K60 load  |
      | Small  | DDR's devfreq as a cooling device, as the vendor's `devfreq-dmc`                          |
      | Small  | The TV's power key over CEC wakes the box, as the vendor's `hdmi_cec_key`                 |
      | Small  | A Bluetooth remote's key wakes the box, as the vendor's `bt-powerkey`                     |
      | Small  | The HDMI audio jack's plug state as an input, as the vendor's `rockchip,hdmi` card        |
      | Small  | HEVC encode past 5120x2880 now and then garbage; the datasheet rates it to 1080p60        |
      | Small  | rkvenc: a failing start_streaming leaves its buffers to vb2 (16384x8640 trips the WARN)   |
      | Small  | MPEG-4 VOP with a zero time increment resolution hangs VDPU2: refused, untested on the box |
      | Medium | Hantro VDPU2: IOMMU reset on a timeout untested; a 1 ms watchdog hangs any recovery       |
      | Small  | VDPP and IEP2 capped at 1920x1088, VDPU2 (VP8, MPEG-1/2/4) too: each untested past it     |
      | Small  | `video.py` stops climbing below 24 fps: a run that finds the size limit, slow or not      |
      | Small  | VOP IOMMU: the H96 Max RK3528 to boot with it, which next2's `cma=16M` assumes            |
      | Large  | AVS, AVS+, AVS2: stateless controls of our own, as VC-1's and MPEG-4's; MPP has the HALs  |
      | Medium | VC-1 SP, MP, AP to 1080p60: a backend over the H313's VC-1 controls, `linux-sunxi` `0064` |
      | Medium | vendor 6.12 applies no PVTM bin: 900 mV on every chip, below stock's for bins 0-4         |
      | Small  | composite: Esmart2 is VP1's primary and shows; Esmart3, its overlay, alone shows black    |
      | Small  | PVTM's 10 °C floor (`rockchip,low-temp-min-volt`) not applied                             |
      | Small  | PVTM's per-chip floor (`mbist-vmin`) not applied: index 1 on each chip here, a no-op      |
      | Small  | OTP's OPP voltage offset (`opp-info`) not applied: zero on the M2 Plus, others unread     |
      | Medium | the remote wakes the box from sleep or off: neither on the HK1; BL31 has no sleep config |
      | Medium | a panic's restart strands the M2 Plus on next2: the watchdog's count carries over boot    |
      | Small  | idle CPU at 1008-2016 MHz under schedutil on next2, never its 408 floor: cause unknown    |
      | Small  | RK3528 PHY: the vendor's RX signal-detect switch above a temperature is not in next2      |
      | Small  | VDPU2 and RGA/VDPP GRF memory bits stock's Android kernel sets: meaning unknown, unset    |
      | Small  | GPU bus fixed at 498 MHz; the vendor scales it with the GPU                               |
      | Small  | HDMI audio: SAI clocks stop between streams, as vendor's do not; a clipped start untested |
      | Small  | crypto, BT PCM on SAI0                                                                    |
      | Small  | H.264 encode at 8192x8192 broken, rated to 1080p60: refused instead, or fixed             |
      | Small  | 10-bit encode input: untested                                                             |
      | Medium | HDMI out is RGB only: no YCbCr 4:4:4, 4:2:2 or 4:2:0, which 4K60 10-bit needs             |
      | Large  | VOP2 overlay HDR: HDR10, HLG, SDR2HLG, HDR Vivid processing; vendor has it, next2 none    |
      | Small  | decoder ½ downscale while decoding, as MPP does: not wired on next2                       |
      | Medium | H.264 MVC (3D) decode: the H.264 controls extended for a second view, our own             |
      | Medium | HDMI 3D out (frame packing and its InfoFrame), which a 3D TV's glasses need beside MVC    |
      | Small  | H.264 4:2:2 and 4:0:0 (monochrome) decode output: untested on next2                       |
      | Small  | JPEG decode: 8176x8176, 4:0:0 to 4:4:4, ROI, as the datasheet lists: untested             |
      | Small  | Esmart layers' 4 regions each: not used by next2's VOP2                                   |
      | Small  | Cluster layer rotation: untested on next2                                                 |
      | Medium | HDMI 8-channel PCM through SAI3, and S/PDIF to HDMI and GPIO: next2 has stereo            |
      | Small  | composite (CVBS) cable detection: in the datasheet's VDAC, unused                         |

      HDMI EDID, CEC and DDC/CI are wired but untested here: no sink.

- [ ] **8K in real time on the DDR3 boxes**: decode and display together at 8K, fps and dropped
      frames, against an LPDDR3 box. The 8K line today is the engine alone; bandwidth is what DDR3
      lacks.
