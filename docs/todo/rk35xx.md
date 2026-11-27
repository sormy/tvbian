# Rockchip: what is left, every board

- [ ] **RK3528: the film plane in the mixed mode is black.** An HDR film at zpos 0 under SDR planes
      (`HDR_BYPASS`): the SDR planes map exactly, the film comes out black with `POST_BUF_EMPTY`,
      with Rockchip's own blob too. The register image is at fault, not the screen. The VOP then
      underruns until a reboot.
- [ ] **RK3528: HDR on a real HDR screen**, the picture by eye.
- [ ] **DDC/CI on `rk35xx-next`**, on one RK3528 box for them all.
- [ ] **RK3528: 4K60 video on a display plane in the desktop**: the GPU composites 4K at about 46
      fps, so mpv drops frames wherever `labwc` composites the video.
- [ ] **RK3528: H.264 at 3840x2160 60 fps**: MPP decodes a 25 Mbit/s High 5.2 stream at 43 fps.
- [ ] **MJPEG decodes in hardware through our FFmpeg.**
- [ ] **Optional: every codec the hardware decodes or encodes reaches our FFmpeg**, AVS, AVS+, AVS2
      and VC-1 included where the chip has them. For completeness more than use.
- [ ] **`display.py` passes with a real screen attached**, HDR or not.
- [ ] **VOP2: AFBC through a size change.** Cluster0 alone takes AFBC; whether it refuses an AFBC
      frame mid-play when the stream changes size.

- [ ] **Vendor 6.12: the chip's PVTM bin applied**: 900 mV on every chip today, below stock's for
      bins 0-4.
- [ ] **Vendor 6.12: HDMI writeback after composite**: commits still succeed; a capture is refused.
- [ ] **Vendor kernels: an off-table HDMI mode at its own pixel clock**: 2256x1504 (235.7 MHz) runs
      the PHY at 1080p60's 148.5 MHz. Computed, as on next2, or refused.
- [ ] **Vendor kernels: the GPU on stock's SCMI clock**, 800 MHz, not the CRU's 498 MHz cap, on
      every board as on the HK1, each soaked; and `gpu-bus` scaling `vdd_logic` with it, once
      `rockchip_bus.c` asks for its `bus` regulator, not `pvtm`.
- [ ] **Check the `ttyFIQ0` login on a serial header.** Every Rockchip board's console is `ttyFIQ0`,
      seen in `/proc/consoles` with its getty running; never on a cable.

- [ ] **RK3528 boards: a 4K display on the R69 and the 3518.** Every RK3528 `board.dts` sets
      `esmart_lb_mode = [02]`, a 4K line buffer for Esmart0, where the factory's `[03]` corrupts the
      right third of a 4K frame; ✅ on the 3518D only. Check `3840x2160p60` full-screen with no
      fringe on the right, then that a 1080p display still comes up clean.

- [ ] **Vendor kernels: composite writeback captures the picture, or is refused**: on the RK3528 it
      signals each capture done and leaves the buffer unwritten, a field's height or a frame's.
- [ ] **Vendor kernels: lima probes in a kernel entered by kexec**: on the HK1, 6.12 entered from
      6.1 fails `gpmmu dte write test fail`, error -5; booted from the menu, it probes.
- [ ] **Vendor kernels: what `display.py` shows the vendor display lacks**: 4K60 at max bpc 10 as
      YCbCr 4:2:0, AFBC rotation by 90 and 270, 3D frame packing, BG24 writeback; on the HK1.
- [ ] **A warm reboot never strands a box.** The watchdog's count carries over a reboot, and a boot
      that outlasts what is left of it is reset partway, sometimes into a box dark until its power
      is pulled. The count restarts, or stops, before the next boot, on every kernel.
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

      HDMI EDID, CEC and DDC/CI are wired but untested here: no sink.

- [ ] **8K in real time on the DDR3 boxes**: decode and display together at 8K, fps and dropped
      frames, against an LPDDR3 box. The 8K line today is the engine alone; bandwidth is what DDR3
      lacks.

## 👤 By hand

- [ ] A sibling booted on 6.1 with a screen attached: does HDMI find it.
