# Rockchip on mainline: what is left

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

- [ ] **RK3528 translation: the drops not shown safe on a box**: VOP2's `rockchip,grf`, the xHCI
      quirks, eMMC `use-v2-tuning` and enhanced strobe, the boot logo, `system-monitor`'s floors.
- [ ] **No MPP once every Rockchip board runs mainline**: video through `rkvdec` and Hantro by V4L2,
      and what exists only for MPP retired: `tvb-va-driver`'s MPP backend and `libmpp` in it,
      `patches/mpp`, `patches/wpewebkit` `0001`, and our FFmpeg's `*_rkmpp` decoders.
- [ ] **The HK1's Wi-Fi download at 2.4 GHz, every run**: nothing in two of four runs.
- [ ] **Bluetooth on next2 with a real device**: audio streamed and a keyboard on the HK1 and the
      R69-1, now that UART2 has RTS; no H4 errors in the log.
