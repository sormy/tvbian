# Amlogic boards: what is left

What spans the family's boards.

- [ ] **Keep an Amlogic board's Ethernet address, as `LAN_MAC` is kept on Rockchip.** It is the
      unifykey `mac` slot, encrypted, so only the vendor U-Boot reads it (`keyman read mac`); the
      stock env hands it to Android as `mac=`. Our `aml_autoscript` runs in that U-Boot: read it,
      then `env export -t` `ethaddr` to fixed RAM for `boot.scr` to `env import` in the chained
      U-Boot, which sets `local-mac-address`. ❓ `env export` in this U-Boot; a RAM address neither
      relocates over.

- [ ] **No kernel self-tests in meson64.** 146 of its 4433 modules are KUnit and test modules, from
      Armbian's config: off in `kernel/meson64.fragment` (`CONFIG_KUNIT`), then a boot on the M20.
      The rest of its breadth stays: USB Wi-Fi, tuners and cameras are why a box is general.
- [ ] **VC-1 and interlaced MPEG-4 decode exact**: SMPTE's SA00040 (176×144), SA00050 and SA10143
      (interlaced fields) differ from software in every picture, and the last two miss one and
      three; interlaced MPEG-4 comes out at 44 dB.
- [ ] **The factory microcode our decoder does not drive**: the M20's `video_ucode.bin` also holds
      `gxl_h263` (an H.263 decoder), `gxl_xvid_multi`, `gxl_mjpeg_multi` and the AVS builds. Whether
      the multi-instance MPEG-4 decodes interlaced and quarter-pel MPEG-4 closer to software.
- [ ] **A JPEG encoder on the S905L3**: the factory `video_ucode.bin` carries `gxl_jpeg_enc`.
- [ ] **"Buffer N done but it doesn't exist in m2m_ctx"** in the decoder's log around a drain:
      whether a buffer is completed twice.
