# Rockchip: what is left, every board

- [ ] **RK3528: the film plane in the mixed mode is black.** An HDR film at zpos 0 under SDR planes
      (`HDR_BYPASS`): the SDR planes map exactly, the film comes out black with `POST_BUF_EMPTY`,
      with Rockchip's own blob too. The register image is at fault, not the screen. The VOP then
      underruns until a reboot.
- [ ] **RK3528: HDR on a real HDR screen**, the picture by eye.
- [ ] **VOP2: AFBC for the video and interface planes.** Which planes take which AFBC formats at 4K,
      and whether a plane refuses it mid-play.
