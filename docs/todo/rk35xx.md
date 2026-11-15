# Rockchip: what is left, every board

- [ ] **RK3528: the film plane in the mixed mode is black.** An HDR film at zpos 0 under SDR planes
      (`HDR_BYPASS`): the SDR planes map exactly, the film comes out black with `POST_BUF_EMPTY`,
      with Rockchip's own blob too. The register image is at fault, not the screen. The VOP then
      underruns until a reboot.
- [ ] **RK3528: HDR on a real HDR screen**, the picture by eye.
- [ ] **DDC/CI on `rk35xx-next`**, on one RK3528 box for them all.
- [ ] **MJPEG decodes in hardware through our FFmpeg.**
- [ ] **Optional: every codec the hardware decodes or encodes reaches our FFmpeg**, AVS, AVS+, AVS2
      and VC-1 included where the chip has them. For completeness more than use.
- [ ] **`display.py` passes with a real screen attached**, HDR or not.
- [ ] **VOP2: AFBC for the video and interface planes.** Which planes take which AFBC formats at 4K,
      and whether a plane refuses it mid-play.

- [ ] **RK3518 boards: revisit the GPU against the H96 Max M20.** Same Mali-450 and the same BOE
      2256x1504 panel: the M20 scores glmark2 **64** at it native; the RK3528 boards scored 41 at
      1080p and 2048x1152, before today's vendor kernel clocked the native mode. Record each board's
      GPU clock and devfreq governor, then rerun glmark2 on the same panel.

- [ ] **Check the `ttyFIQ0` login on a serial header.** Every Rockchip board's console is `ttyFIQ0`,
      seen in `/proc/consoles` with its getty running; never on a cable.

- [ ] **RK3528 boards: a 4K display on the R69 and the 3518.** Every RK3528 `board.dts` sets
      `esmart_lb_mode = [02]`, a 4K line buffer for Esmart0, where the factory's `[03]` corrupts the
      right third of a 4K frame; ✅ on the 3518D only. Check `3840x2160p60` full-screen with no
      fringe on the right, then that a 1080p display still comes up clean.

- [ ] **The R69's Wi-Fi comes back after every warm reboot.**
- [ ] **6.12: a `_regulator_put` WARNING in the USB2 PHY's deferred probe**, now and then on the
      3518D and the R69. The probe fails `IRQ index 0 not found`, after `vcc5v0_host: could not add
      device link ... -ENOENT`; its cleanup puts the regulator. Taints the kernel (512).

- [ ] **RK3528: name the DDR parameters a vendor tunes.** The H96 Max 3518's factory DDR init is
      rkbin's `rk3528_ddr_1056MHz_4BIT_PCB_v1.11.bin` with three bytes changed in its parameter
      table; read which fields with `ddrbin_tool`, and whether rkbin's blob with them set equals a
      factory loader, so an imported board's DRAM need not wait for its dump.

- [ ] **AIC8800 Bluetooth address as on sunxi.** The chip's eFuse first, then the Wi-Fi's own
      address plus one, wherever it came from; today a tree address beats the eFuse, and the
      fallback is the SoC serial's.

- [ ] **To consider: RK3528 and RK3518 on mainline.** Mainline 7.3.4's `rk3528.dtsi` describes 60
      of the 95 blocks the M2 Plus enables: enough for a headless server. Missing, by size:

      | Size   | Blocks                                                            |
      | ------ | ----------------------------------------------------------------- |
      | Small  | `tsadc`, SAI, S/PDIF, RNG, crypto, SFC, timer, DFI, SRAM, IOMMUs  |
      | Medium | Hantro `vdpu`, JPEG decoder, RGA, IEP                             |
      | Large  | VOP2's RK3528 variant, HDMI and its PHY: no picture without them  |
      | Large  | rkvdec (HEVC, H.264, VP9), rkvenc: no mainline encoder driver     |
      | Large  | audio codec, composite TV encoder                                 |

      Check the lists for posted RK3528 VOP2, HDMI and rkvdec series first. Video would go through
      V4L2 stateless, as on the H616, not MPP.

- [ ] **8K in real time on the DDR3 boxes**: decode and display together at 8K, fps and dropped
      frames, against an LPDDR3 box. The 8K line today is the engine alone; bandwidth is what DDR3
      lacks.
