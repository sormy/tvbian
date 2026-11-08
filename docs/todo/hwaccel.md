# Hardware video in Debian's own programs

Debian's programs, unpatched, decode and encode on the box's video hardware: Firefox, Chromium, mpv,
VLC, Kodi, GStreamer's players, WebRTC. We ship only what sits beneath them: drivers, plugins, a
shadowed library, settings.

## What each program loads

| Program               | Hardware path                                    |
| --------------------- | ------------------------------------------------ |
| Firefox               | VA-API, through the system `libavcodec` it loads |
| Chromium              | VA-API, its own code; its FFmpeg is bundled      |
| mpv, VLC, Kodi        | the system `libavcodec`, by name or hwaccel      |
| GStreamer's players   | its V4L2 elements, or a vendor plugin            |
| Vulkan Video programs | ➖: Mali has no Vulkan video driver              |

FFmpeg picks no hardware itself: a program asks for a decoder by name (`h264_rkmpp`) or opens a
hwaccel device (`vaapi`, `v4l2request`). Firefox opens VA-API only.

## Each family, by layer

| Layer             | `rk35xx` (MPP)   | `sunxi-h616` (stateless) | `meson-gxl` (stateful) |
| ----------------- | ---------------- | ------------------------ | ---------------------- |
| VA-API driver     | `rockchip-vaapi` | `v4l2_request`           | none known             |
| Debian GStreamer  | an MPP plugin    | `v4l2codecs` ❓          | `v4l2` ❓              |
| Debian FFmpeg 7.1 | no `rkmpp`       | no `v4l2request`         | `v4l2m2m` ❓           |

`rockchip-vaapi` is written for RK3588 and Firefox; its HEVC is disputed upstream. Nothing known
drives a stateful decoder through VA-API.

## Two tiers

| Tier                              | Gets                                                 |
| --------------------------------- | ---------------------------------------------------- |
| Debian's programs                 | decode and encode in hardware; AFBC where negotiated |
| Ours: fuseamp, Kodi, mpv's config | decoder scaling and AFBC to a plane                  |

- **AFBC** reaches a program through VA-API only when it lists the modifier at surface creation
  (`VASurfaceAttribDRMFormatModifiers`); the driver picks linear otherwise, never forced.
- **Only Panfrost samples AFBC**: the H313's Mali-G31. Mali-450 under Lima cannot, so on the RK3518,
  RK3528 and S905L3 AFBC pays only on a plane.
- **Decoder scaling stays ours**: VA-API's decode-time processing is used by neither FFmpeg nor the
  browsers.

## Open

- [ ] **Survey, one box a family**: what Debian's GStreamer and FFmpeg 7.1 already decode; whether
      Debian's arm64 Chromium is built with VA-API; whether Firefox and Chromium list modifiers at
      surface creation.
- [ ] **Our decoders in Debian's `libavcodec`**: `patches/ffmpeg/` backported to Debian's 7.1, a
      shadowed `extras/` package every Debian player loads; our 9.0.2 beside it helps only our
      tools. ❓ the backport's size.
- [ ] **A VA-API driver a family**, packaged: `v4l2_request` for `sunxi-h616` first, the family
      closest to working stock and the only one where AFBC can reach a browser; `rockchip-vaapi` for
      `rk35xx`; `meson-gxl` waits for a stateful driver.
- [ ] **GStreamer on `rk35xx`**: an MPP plugin package; AirPlay mirroring (`uxplay`) needs it.
- [ ] **Browser settings shipped**: Firefox's VA-API prefs as a system prefs file; Chromium's
      `LIBVA_DRIVER_NAME` and flags in `/etc/chromium.d/`.
- [ ] **Encode** through the same layers, for WebRTC and screen capture.
- [ ] **Zero copy to the screen**: a VA-API frame imported by Lima and Panfrost without a CPU copy.
- [ ] **A matrix**: program by codec by family, in `tools/validate/`.
