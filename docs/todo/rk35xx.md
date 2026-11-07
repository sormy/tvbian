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
