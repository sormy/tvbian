# Rockchip: what is left, every board

## RK3528 display and video

- [ ] **The film plane in the mixed mode is black.** An HDR film at zpos 0 under SDR planes
      (`HDR_BYPASS`): the SDR planes map exactly, but the film comes out black with
      `POST_BUF_EMPTY`, with Rockchip's own blob too. The register image is at fault, not the
      screen. The VOP then underruns until a reboot.
- [ ] **HDR on a real HDR screen**, the picture checked by eye.
- [ ] **`display.py` passes with a real screen attached**, HDR or not.
- [ ] **DDC/CI on `rk35xx-next`**, on one RK3528 box for them all.
- [ ] **A 4K display on the R69 and the 3518.** Every RK3528 `board.dts` sets
      `esmart_lb_mode = [02]`, a 4K line buffer for Esmart0; the factory's `[03]` corrupts the right
      third of a 4K frame. ✅ on the 3518D only. Check `3840x2160p60` full-screen with no fringe on
      the right, then that a 1080p display still comes up clean.
- [ ] **4K60 video on a display plane in the desktop.** The GPU composites 4K at about 46 fps, so
      mpv drops frames wherever `labwc` composites the video.
- [ ] **H.264 at 3840x2160 60 fps.** MPP decodes a 25 Mbit/s High 5.2 stream at 43 fps.
- [ ] **AFBC through a size change.** Only Cluster0 takes AFBC; check whether it refuses an AFBC
      frame mid-play when the stream changes size.
- [ ] **8K in real time on the DDR3 boxes**: decode and display together at 8K, fps and dropped
      frames, against an LPDDR3 box. The 8K line today is the engine alone; bandwidth is what DDR3
      lacks.
- [ ] **MJPEG decodes in hardware through our FFmpeg.**
- [ ] **Optional: every codec the hardware decodes or encodes reaches our FFmpeg**, AVS, AVS+, AVS2
      and VC-1 included where the chip has them. For completeness more than use.

## Vendor kernels

- [ ] **6.12: the chip's PVTM bin applied.** Every chip runs 900 mV today, below stock's for bins
      0-4.
- [ ] **6.12: HDMI writeback after composite.** Commits still succeed, but a capture is refused.
- [ ] **6.12: no `_regulator_put` WARNING in the USB2 PHY's deferred probe**, seen now and then on
      the 3518D and the R69. The probe fails `IRQ index 0 not found` after
      `vcc5v0_host: could not add device link ... -ENOENT`, and its cleanup puts the regulator. The
      warning taints the kernel (512).
- [ ] **Composite writeback captures the picture, or is refused.** On the RK3528 it signals each
      capture done but leaves the buffer unwritten, at a field's height or a frame's.
- [ ] **An off-table HDMI mode at its own pixel clock.** 2256x1504 (235.7 MHz) runs the PHY at
      1080p60's 148.5 MHz; it should be computed, as on next2, or refused.
- [ ] **The display features `display.py` finds missing**: 4K60 at max bpc 10 as YCbCr 4:2:0, AFBC
      rotation by 90 and 270, 3D frame packing, BG24 writeback; on the HK1.
- [ ] **The GPU on stock's SCMI clock**, 800 MHz instead of the CRU's 498 MHz cap, on every board as
      on the HK1, each soaked; and `gpu-bus` scaling `vdd_logic` with it, once `rockchip_bus.c` asks
      for its `bus` regulator, not `pvtm`.
- [ ] **lima probes in a kernel entered by kexec.** On the HK1, 6.12 entered from 6.1 fails with
      `gpmmu dte write test fail`, error -5; booted from the menu, it probes.
- [ ] **The encoder refuses a frame too large for it instead of wedging.** A 16384×8640 H.264 encode
      took the HK1's vendor 6.1 off the network until a power cut, once in three runs.

## Boot and boards

- [ ] **A warm reboot never strands a box.** The watchdog's count carries over a reboot, and a boot
      that takes longer than what is left of it is reset partway, sometimes into a box that stays
      dark until its power is pulled. The count should restart, or stop, before the next boot, on
      every kernel.
- [ ] **The R69's Wi-Fi comes back after every warm reboot.**
- [ ] **Check the `ttyFIQ0` login on a serial header.** Every Rockchip board's console is `ttyFIQ0`,
      seen in `/proc/consoles` with its getty running, but never tried on a cable.
- [ ] **AIC8800 Bluetooth address as on sunxi**: the chip's eFuse first, then the Wi-Fi's own
      address plus one, wherever that came from. Today a tree address beats the eFuse, and the
      fallback is derived from the SoC serial.
- [ ] **Name the DDR parameters a vendor tunes.** The H96 Max 3518's factory DDR init is rkbin's
      `rk3528_ddr_1056MHz_4BIT_PCB_v1.11.bin` with three bytes changed in its parameter table. Read
      which fields they are with `ddrbin_tool`, and whether rkbin's blob with them set equals a
      factory loader, so an imported board's DRAM need not wait for its dump.

## 👤 By hand

- [ ] A sibling booted on 6.1 with a screen attached: does HDMI find it.
