# `tvb-va-driver`: hardware video in Debian's own programs

Debian's programs, unpatched, decode and encode on the box's video hardware: Firefox, Chromium, mpv,
VLC, Kodi, GStreamer's players, WebRTC. We ship only what sits beneath them: drivers, plugins,
settings.

## Open

- [ ] **Survey, one box a family**: what Debian's GStreamer and FFmpeg 7.1 already decode; whether
      Debian's arm64 Chromium is built with VA-API; whether Firefox and Chromium list modifiers at
      surface creation.
- [ ] **Debian's `libavcodec` stays stock on trixie**: our series on 9.0.2 is a port to 7.1, not a
      backport, redone on each of its security updates. Our patches go upstream; forky's FFmpeg is
      the next look.
- [ ] **Interlaced MPEG-4 through `tvb-va-driver`** on `sunxi-h616` and `rk35xx`, and interlaced
      MPEG-2 on `rk35xx` with MPP: refused now, as `ffmpeg9` fails them too.
- [ ] **`ffmpeg9 -hwaccel vaapi` on `meson-gxl` ends MPEG-2 and MPEG-4 with every picture**: the
      last 2 are lost at the end of the stream, at any `-hwaccel_output_delay`; Debian's FFmpeg 7.1
      gets them.
- [ ] **`meson-gxl` MPEG-4 Simple now and then wrong**: `mpeg4-sp` gives one picture at 22.8 dB in
      about one run in three, on either driver build.
- [ ] **`meson-gxl` VC-1 with slices refuses every wrong picture after a drain**: `vc1-ap-slices`
      lets one through at 17 dB.
- [ ] **VP9 profile 2 offered on `rk35xx-next2`**: `rkvdec` decodes it, 2160p at about 61 fps
      through `ffmpeg9`'s own path, and `tvb-va-driver` offers it not, there or on the M2 Plus.
- [ ] **Smooth from the first picture**: decoders stutter for the first seconds of a play, seen by
      eye, not measured; a warm-up before the first picture shows, a short delay in place of drops.
      Kernel or driver is not known: the first pictures' times, through VA and `ffmpeg9`'s own path,
      on each family, tell which; on `meson-gxl` the kernel's first HEVC sessions are one cause.
- [ ] **Every family at `ffmpeg9`'s native rate through VA-API**, decoding only, frames left on the
      GPU: `rk35xx` HEVC Main 10 at 88 to 89% when narrowed by the CPU; as P010 not measured.
- [ ] **`meson-gxl` VP9 4K without a copy**: the decoder grants only the 16 CAPTURE buffers it holds
      itself, so every picture is copied out for the surfaces to hold.
- [ ] **The suite times VA against `ffmpeg9`'s native path**, clip by clip, not only against the
      box's last run.
- [ ] **4K in Debian's programs**: linear frames carry 1080p; 4K needs AFBC end to end, which a
      program gets only by listing the modifier at surface creation, and only Panfrost samples.
- [ ] **VC-1 Main on Cedrus** once `linux-sunxi` `0815` ships: offered, and a sequence that allows B
      pictures (`MAXBFRAMES` above 0) refused at its context, as the kernel refuses it.
- [ ] **AV1 ranked `NONE` for the browser alone**: `tvb-va-driver` hides GStreamer's software AV1
      box-wide, so YouTube in WebKit picks VP9, and AV1 files play in no GStreamer player; the line
      moves to the browser's launcher once it is packaged.
- [ ] **GStreamer's `va` decoders on `meson-gxl`**: H.264 and VP9 time out with no frame, HEVC comes
      out at 6 dB; FFmpeg decodes the same clips through the same driver. GStreamer maps each
      picture in the thread that feeds the decoder, and meson holds it until later packets: every
      sync drains, its references lost. H.264's legacy microcode reorders by DPB fullness alone;
      HEVC's and VP9's drivers could output in decode order behind
      `V4L2_CID_MPEG_VIDEO_DEC_DISPLAY_DELAY`. VP9's driver hands a picture out only on the next
      packet's header, a lag VA cannot cover: the driver has no next packet at a sync.
- [ ] **4K H.264 and HEVC read back on `meson-gxl`**: FFmpeg reads a picture after its own reorder
      delay, which meson's DPB exceeds at 4K, so the sync drains and the stream ends after 1 to 9
      pictures; 1080p and 4K left on the GPU decode whole.
- [ ] **A sync on one VP9 picture on `meson-gxl`**: reading a picture back drains, and the drain
      ends the stream with an internal decoding error.
- [ ] **The suite leaves no process behind**: that FFmpeg outlived its run and its directory.
- [ ] **`mpv --hwdec=vaapi` on `rk35xx` and `meson-gxl`**: through Wayland, as on `sunxi-h616`. On
      `meson-gxl`, with the system heap, VP9 and HEVC play with no copy; H.264 stops after about 11
      pictures, mpv waiting on one meson holds, and the drain losing its references.
- [ ] **`va_probe` in `tvb-va-driver`**: the suite's initialize check is UNTESTED on a box without
      it.
- [ ] **GStreamer in the host check**: its `va` plugin opens only a DRM render node, which the build
      container lacks; a Linux host or CI could pass `vgem`'s node in.
- [ ] **HEVC 1080p60 in WebKit on `rk35xx-next2` now and then decodes nothing**: one Falkon file run
      of several, the others at full rate.
- [ ] **Held pictures detected**: `backend_v4l2m2m.c` assumes them by codec; a decoder seen holding
      one should switch the workaround on.
- [ ] **Standalone build**: `build.sh` reads repo paths, and the host engine needs
      `patches/ffmpeg/0039`; a meson build of its own, and no licence yet.
- [ ] **Chromium's sandbox**: every engine's device opened in `vaInitialize`, before the sandbox
      closes; today each opens at its first context.
- [ ] **AFBC for the client that lists it, on MPP**: Cedrus and `rkvdec` give AFBC to a client
      listing the modifier at `vaCreateSurfaces`; MPP only under `TVB_VA_AFBC`, a box-wide test
      switch that every 8-bit H.264, HEVC and VP9 client then gets, CPU readers refused.
- [ ] **Chromium lists the AFBC modifier**, so the switch goes: it creates surfaces with no list.
      With the switch, YouTube 4K60 VP9 on the M2 Plus shows 56.8 of 60 pictures a second.
- [ ] **MPP's AFBC layout refused when it differs from the plan**: the driver plans it from MPP
      1.1.0's own sizing, checked on the RK3528; a mismatch now lands in spare buffers it cannot
      copy.
- [ ] **The two-layer AFBC export only where asked**: NV12's second layer is a copy of the first,
      for Chromium; another client may read it as a plane.
- [ ] **10-bit AFBC** (`AN6a`, MPP's 10-bit FBC): offered, never shown on a plane.
- [ ] **GStreamer's `va` offers AFBC downstream**: it offers the modifier a plain surface exports.
- [ ] **Chromium's linear YouTube 4K60 VP9 on the M2 Plus**: decode calls p99 216 ms, 10 pictures a
      second shown, where AFBC shows 56.8.
- [ ] **The suite as a player drives VA**: each decode call's time, its slowest against one frame's
      interval. A real-time sink does not show it, as GStreamer decodes ahead of the sink: no late
      picture at 4K60 VP9 before the stall fix or after. Nor does libvpx's test pattern, which MPP
      decodes too easily to stall.
- [ ] **The suite through GStreamer's DMA path**: every clip to `DMA_DRM` caps, as WebKit takes
      them, into `fakevideosink`; it converts to system memory today. GStreamer's latency tracer
      stalls such a pipeline, so it cannot time it.
- [ ] **A clip as a site encodes it**: VP9 and AV1 with alt-refs, show-existing frames and the rate
      control a site uses, beside libvpx's real-time clips.
- [ ] **Cedrus's AFBC by its own probe**: the driver now asks which AFBC CAPTURE lists, where it
      named Cedrus's; not run on the H313 since.
- [ ] **`VideoProc` scaling**: for Jellyfin's `scale_vaapi`, and NV12 to ARGB where Chromium's GL
      cannot import NV12; it converts 8-bit and 10-bit at one size today.
- [ ] **CBR from the first second on `sunxi-h616`**: Cedrus-enc's first frame is ten times its
      share, its first second 2.7 times the target.
- [ ] **CBR on `meson-gxl`**: its encoder lists VBR alone, and WebKit asks for CBR.
- [ ] **Constrained Baseline on `meson-gxl`**: its encoder lists Main and High alone, and WebKit's
      call asks for Constrained Baseline.
- [ ] **Chromium off software AV1**: YouTube in Chromium on `sunxi-h616` decoded on the CPU, the
      engine idle; no box decodes AV1 in hardware, and Chromium 156 reports AV1 supported with or
      without `Dav1dVideoDecoder`, so only the page's codec checks can steer it to VP9.
- [ ] **Chromium's call on the box's encoder**: its VA encoder runs, but WebRTC drops to software
      below 360p, where a 3.5 fps canvas sends it.
- [ ] **Firefox shows what VA decodes on `sunxi-h616`**: HEVC 1080p60 decodes at 60 fps through VA
      and 4 are shown, the rest dropped; as few with its CPU decoder, so its drawing on Panfrost.
- [ ] **Firefox's calls on the box's encoder**: ESR 153's FFmpeg encoder opens `libx264` alone.
- [ ] **GStreamer on `rk35xx`**: an MPP plugin package; AirPlay mirroring (`uxplay`) needs it.
- [ ] **Encode** for WebRTC and screen capture, through `tvb-va-driver`'s H.264, HEVC and JPEG
      encoders in a browser.
- [ ] **Zero copy to the screen on Lima**: a VA-API frame imported without a CPU copy, as Panfrost
      does.
- [ ] **A matrix**: program by codec by family, in `tools/validate/`.
