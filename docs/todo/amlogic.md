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
- [ ] **7.3 decodes 4K slower than 6.18 outside the decoder**: `ffmpeg9`'s `v4l2m2m` on the M20 gets
      VP9 4K 15.6 fps without `0038`'s compressed references (6.18: 46) at the same 19 ms a picture
      in the decoder, and HEVC 4K 47 with them (6.18: 53).
- [ ] **The S905L3 decodes HEVC 4K60 for a CPU reader**: 62 fps when the reader skips the CAPTURE
      cache syncs (`V4L2_BUF_FLAG_NO_CACHE_INVALIDATE`, `_CLEAN`), 53 with them (`ffmpeg9`'s
      `v4l2m2m`): the 12 MB invalidate runs in the interrupt thread while the decoder waits. Moved
      to DQBUF it waits on the queue lock instead; completing pictures from a worker would hide it.
- [ ] **Pictures in decode order on request**, so GStreamer's va decoders run on the M20:
      `V4L2_CID_MPEG_VIDEO_DEC_DISPLAY_DELAY` 0 in `codec_hevc`'s and `codec_h264_g12a`'s output,
      which the driver decides. H.264 on the GXLX2 runs the legacy microcode, whose DPB reorders by
      itself: it first needs the multi-instance one the factory `amvdec_mh264.ko` drove.
- [ ] **A VP9 picture out once decoded**, not at the next one's header: `codec_vp9` handles only
      `VP9_HEAD_PARSER_DONE`, so `codec_vp9_show_frame` returns picture N when packet N+1 arrives. A
      client that waits for each picture before the next packet, as GStreamer's `vavp9dec` does,
      stalls: "No dst buffer available", then a dropped frame. The vendor's VP9 driver ends a
      picture on `HEVC_DECPIC_DATA_DONE`; whether this microcode raises it on a stream is to be
      found.
- [ ] **A JPEG encoder on the S905L3**: the factory `video_ucode.bin` carries `gxl_jpeg_enc`.
- [ ] **"Buffer N done but it doesn't exist in m2m_ctx"** still once in 15 MJPEG and MPEG-4 drains
      and restarts after `0037`: another path completes a buffer twice.
