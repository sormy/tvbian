# Amlogic boards: what is left

What spans the family's boards.

- [ ] **A hardware cursor plane**: the second graphics layer, OSD2, as a cursor plane, if the S905L3
      has one usable; mainline `meson` drives OSD1 only.
- [ ] **Keep an Amlogic board's Ethernet address, as `LAN_MAC` is kept on Rockchip.** It is the
      unifykey `mac` slot, encrypted, so only the vendor U-Boot reads it (`keyman read mac`); the
      stock env hands it to Android as `mac=`. Our `aml_autoscript` runs in that U-Boot: read it,
      then `env export -t` `ethaddr` to fixed RAM for `boot.scr` to `env import` in the chained
      U-Boot, which sets `local-mac-address`. ❓ `env export` in this U-Boot; a RAM address neither
      relocates over.

- [ ] **A TV remote's keys over HDMI CEC as input events.** `CONFIG_MEDIA_CEC_RC` cannot be set in
      `meson64` or `meson64-next`: it needs `RC_CORE` built in where `CEC_CORE` is.
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
- [ ] **H.264 switching size mid-stream**: 640x360, 1280x720, 640x360 through `h264_v4l2m2m` on
      7.3.5 loses pictures or hangs, run to run (84 of 90; a hang; 90 with 3 wrong; 14), with
      "Buffer N done but it doesn't exist in m2m_ctx" and "Unexpected H264 ISR" in the log. VP9's
      switch decodes bit-identical since `0040`, HEVC's always did.
- [ ] **HEVC 4K wrong once, then never again**: `hevc_v4l2m2m` on `hevc-4k30.mp4` (Main, B-frames)
      gave 0 of 60 frames right with "Missing L0 reference POC 8, using POC 10/12", after a run of
      VA and native HEVC 4K decodes and speed tests; fresh, and after VP9 4K decodes, 60 of 60 with
      CMA near 400 MB free. When it shows again: the CMA free, the CAPTURE count and what ran
      before.
- [ ] **VC-1 Advanced profile**: through `tvb-va-driver` 6 of 60 pictures arrive, the rest held or
      refused; `ffmpeg9`'s `vc1_v4l2m2m` decodes the same stream at 18.9 dB Y, `vc1-ap-slices`
      at 17.
- [ ] **`0040` on a built kernel**: tested as a module built outside the kernel tree on 7.3.5, which
      also failed MPEG-4 and VC-1 that the installed module passes; to show on a kernel built with
      it that only VP9 changed.
- [ ] **`meson-vdec`'s first HEVC decode after idle at its rate**: twice, 51 ms a picture for the
      first 20 seconds and normal after, not from the page cache; a clock or the firmware's load is
      to look at. On a fresh boot with `0041` (no abort) the first 1080p24 HEVC play still drops 230
      of 498, and the next clip, 1080p60, none. Not CMA: on a fresh boot the first two decodes to
      null make 82 CMA allocations each, 103 and 95 ms in all, none over 10 ms, and decode at 116
      and 142 frames a second, well above the clip's rate; the first play's drops come after the
      decoder, at the display's first use, as the overlay's refusal does. Traced on a fresh boot
      (V4L2 QBUF/DQBUF, 19 November): in a bad play the decoder holds most CAPTURE buffers yet gives
      out 7.5 pictures a second, a buffer's round trip 191 to 341 ms at the median, where a later
      play's is 30 ms: the decoder is slow then, not starved by the player, while decoding to null
      right after boot runs at 116 frames a second with its clocks at 500 MHz. The display at work
      beside it, early in a boot, is what differs. A later fresh boot: plays at 120 and 420 s ran 83
      and 41 ms a picture, then straight after one decode to null run to its end 7.3 ms, nothing
      dropped, the same 20 CAPTURE buffers each time. The decode to null ends drained at end of
      stream; the slow sessions came after boot or after plays stopped mid-stream, some leaving
      buffers active on stop (below): that leak, a stop leaving state the next session pays for, is
      fixed by `0042` and retested: not the cause. On the `0042` kernel a play beside the display at
      150 s still ran 61 ms a picture with every commit refused, after a decode to null run to its
      end at 100 s, so that warm-up does not reliably help either. In that play the decoder always
      had input queued (16 on average) and free CAPTURE buffers (25), and gave 6.5 pictures a
      second, with the display not scanning out (2 vblanks a second). No clock, power domain or
      devfreq rate differs before and after a warm-up. Sampled and traced further, the decoder is
      not slow but stalls: full speed for 1 to 3 s, then no interrupt for up to 3.3 s with input
      queued and no CAPTURE buffer free. The player collects pictures, and gives buffers back, only
      as the display shows them, and early in a boot the display gives no vblank. The "Missing L0
      reference" ending each stall is the player's: over 0.5 s behind it skips to the next CRA,
      whose RASL pictures reference what it skipped (fuseamp fixes that). So the decoder is sound
      here; the cause is the display not scanning out after its first mode set, the item below.
- [ ] **VP9 pictures lent in place by `meson-vdec`**: its VP9 CAPTURE queue grants only the 16
      buffers the decoder holds, so `tvb-va-driver` copies every picture out on the CPU. A few above
      its minimum, as its H.264 and HEVC queues take, would let it lend them; CPU only, VP9 4K
      through VA already plays at 99% of native.
- [ ] **NV12 on the M20's overlay from the first commit after boot**: on a fresh boot, with the
      stand-in screen hot-plugged just before, the meson overlay refuses every NV12 commit (EINVAL)
      for a stretch, the decoder's dma-bufs and dumb buffers alike, then takes them (fuseamp, 19
      November). The refusal once taken for a CPU map of the picture was this one, the first display
      use after an idle. It needs the boot's first mode set followed at once by NV12: with the
      screen up 20 s first, a fresh boot's first NV12 play is taken whole, and a later re-plug and
      play is too. Something of the plane's or VPU's setup finishing after that first mode set.
      Traced: while every commit was refused the CRTC gave 2 vblank events in 30 s, and 58 a second
      once they were taken; the display was not scanning out yet after the first mode set.
- [ ] **H.264 pictures handed out while still references, on `meson-vdec`**: the GXLX2 runs
      mainline's single-instance `codec_h264` with `gxl_h264.bin`, whose firmware keeps its
      references in the client's CAPTURE buffers and gives a picture back when its own order allows.
      A client that waits on each picture before sending more (mpv through VA, FFmpeg's
      `hwdownload`) stalls after a few, and the drain that would free them ends the session
      ("Missing L0 reference POC"). VP9 and HEVC keep their references apart and write the client's
      picture as a second copy, which is why they play. The way out, from Amlogic's own driver
      (media_modules `h264_multi/vmh264.c`): its MDEC double write before T7 only points a second
      canvas at the picture (`MDEC_DOUBLEW_CFG1`) and is meant for a scaled-down copy, its 1:1
      setting left out; what keeps H.264's references apart on G12A-class chips is its MMU mode,
      references compressed in the decoder's own memory and the client's picture written by the HEVC
      core's SAO stage (`hevc_sao_set_pic_buffer`), as our VP9 and HEVC already do. Chosen on 19
      November: that port. Amlogic's driver allows it on the GXLX2 (`0x2a`, at least TXLX and not
      GXLX), and the M20's factory `video_ucode.bin` carries its firmware, `g12a_h264_multi_mmu.bin`
      and `gxl_h264_multi_mmu.bin`, run on the HEVC core beside MDEC's H.264. Steps: unpack the
      firmware as the others are (done, from the factory file as its neighbours are); bring up the
      multi-instance decoder (`codec_h264_g12a`, the factory's `g12a_h264_multi.bin`) on the GXLX2,
      as Amlogic's driver runs it, which as it stands does not start there (19 November: its source
      restarts with `search_valid=0`, no picture decoded; the firmware is the right one, Amlogic's
      loader taking for the GXLX2 the newest at or below it, G12A's, so the parser, power or
      clocking our driver gives the GXLX2 is what to compare); bring up the HEVC core's MMU and SAO
      for H.264 from `codec_hevc_common.c`, references in its compressed buffers; then CAPTURE
      buffers as output only, so `codec_h264_multi_queue_frame` hands each picture out at the
      stream's reorder depth. The multi-instance firmware it needs, `gxlx2/g12a_h264_multi.bin` and
      `g12a_h264_multi_mmu.bin` from the M20's stock, ships in the firmware package since 23
      November, loaded by nothing until the port runs.
- [ ] **Constrained baseline from `meson-venc`'s H.264**: it encodes with the CABAC microcode
      (`ga_h264_enc_cabac`), so Main only, and a WebKit call, which asks for constrained baseline,
      cannot use it. The tree also names a CAVLC microcode (`gxl_h264_enc`), untried on the GXLX2.
- [ ] **CBR from `meson-venc`'s H.264**: it lists VBR only, and lands 15 to 28% under its target at
      2 to 4 Mbit/s; WebKit's WebRTC asks `vah264enc` for CBR, which then fails to set on the M20.
- [ ] **A JPEG encoder on the S905L3**: the factory `video_ucode.bin` carries `gxl_jpeg_enc`.
- [ ] **"Buffer N done but it doesn't exist in m2m_ctx"** still once in 15 MJPEG and MPEG-4 drains
      and restarts after `0037`: another path completes a buffer twice.
