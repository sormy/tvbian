# `tvb-va-driver`: hardware video in Debian's own programs

Debian's programs, unpatched, decode and encode on the box's video hardware: Firefox, Chromium, mpv,
VLC, Kodi, GStreamer's players, WebRTC. We ship only what sits beneath them: drivers, plugins,
settings.

## Open

- [ ] **Firefox's VA environment in `tvb-va-driver`**: `MOZ_ENABLE_WAYLAND` and
      `MOZ_DISABLE_RDD_SANDBOX` where every session reads them, a greetd-started `labwc` included.
- [ ] **Survey, one box a family**: what Debian's GStreamer and FFmpeg 7.1 already decode; whether
      Debian's arm64 Chromium is built with VA-API; whether Firefox and Chromium list modifiers at
      surface creation.
- [ ] **Debian's `libavcodec` stays stock on trixie**: our series on 9.0.2 is a port to 7.1, not a
      backport, redone on each of its security updates. Our patches go upstream; forky's FFmpeg is
      the next look.
- [ ] **`tvb-va-driver` in the images**, once each family's suite passes:
      `tools/validate/va_driver.py`.
- [ ] **Interlaced MPEG-4 through `tvb-va-driver`** on `sunxi-h616` and `rk35xx`, and interlaced
      MPEG-2 on `rk35xx`: refused now, as `ffmpeg9` fails them too.
- [ ] **`ffmpeg9 -hwaccel vaapi` on `meson-gxl` ends MPEG-2 and MPEG-4 with every picture**: the
      last 2 are lost at the end of the stream, at any `-hwaccel_output_delay`; Debian's FFmpeg 7.1
      gets them.
- [ ] **`meson-gxl` VC-1 with slices refuses every wrong picture after a drain**: `vc1-ap-slices`
      lets one through at 17 dB.
- [ ] **`mpv --hwdec=vaapi` on the display node**: mpv's DRM output opens VA on `card0`, whose
      driver name (`meson`, `sun4i-drm`) no package installs; with it linked by hand, `vainfo` opens
      it and mpv still does not.
- [ ] **4K in Debian's programs**: linear frames carry 1080p; 4K needs AFBC end to end, which a
      program gets only by listing the modifier at surface creation, and only Panfrost samples.
- [ ] **VC-1 Main on Cedrus** once `linux-sunxi` `0815` ships: offered, and a sequence that allows B
      pictures (`MAXBFRAMES` above 0) refused at its context, as the kernel refuses it.
- [ ] **`ffmpeg9 -hwaccel vaapi` on `rk35xx`**: device creation fails with `-12`; Debian's FFmpeg
      opens the same driver.
- [ ] **AV1 ranked `NONE` for the browser alone**: `tvb-va-driver` hides GStreamer's software AV1
      box-wide, so YouTube in WebKit picks VP9, and AV1 files play in no GStreamer player; the line
      moves to the browser's launcher once it is packaged.
- [ ] **A resolution change mid-stream on MPP**: VP9 480p to 1080p and back, as YouTube switches,
      fails `vaEndPicture` through FFmpeg and corrupts references on the way down through GStreamer;
      the suite should carry the switch both ways.
- [ ] **GStreamer in the host check**: its `va` plugin opens only a DRM render node, which the build
      container lacks; a Linux host or CI could pass `vgem`'s node in.
- [ ] **10-bit by capability on MPP**: `narrows_ten_bit` lists NV12 alone for every client; P010
      where the client's GPU samples it.
- [ ] **Held pictures detected**: `backend_v4l2m2m.c` assumes them by codec; a decoder seen holding
      one should switch the workaround on.
- [ ] **Standalone build**: `build.sh` reads repo paths, and the host engine needs
      `patches/ffmpeg/0039`; a meson build of its own, and no licence yet.
- [ ] **Chromium's sandbox**: every engine's device opened in `vaInitialize`, before the sandbox
      closes; today each opens at its first context.
- [ ] **`VideoProc`**: scaling for Jellyfin's `scale_vaapi`, and NV12 to ARGB where Chromium's GL
      cannot import NV12.
- [ ] **Chromium's encoder** through `tvb-va-driver`, which offers no packed headers.
- [ ] **GStreamer on `rk35xx`**: an MPP plugin package; AirPlay mirroring (`uxplay`) needs it.
- [ ] **Encode** for WebRTC and screen capture, through `tvb-va-driver`'s H.264, HEVC and JPEG
      encoders in a browser.
- [ ] **Zero copy to the screen**: a VA-API frame imported by Lima and Panfrost without a CPU copy.
- [ ] **A matrix**: program by codec by family, in `tools/validate/`.
