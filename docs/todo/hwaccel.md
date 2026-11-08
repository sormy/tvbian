# Hardware video in Debian's own programs

Debian's programs, unpatched, decode and encode on the box's video hardware: Firefox, Chromium, mpv,
VLC, Kodi, GStreamer's players, WebRTC. We ship only what sits beneath them: drivers, plugins,
settings.

## What each program loads

| Program                      | Path                         | Needs                                 |
| ---------------------------- | ---------------------------- | ------------------------------------- |
| Chromium                     | VA-API, its own code         | flags; ❓ Debian's arm64 build has it |
| Firefox                      | VA-API, via Debian's FFmpeg  | prefs; on alone for Mesa drivers only |
| mpv                          | VA-API, via Debian's FFmpeg  | `hwdec=vaapi`; off by default         |
| VLC                          | VA-API, via Debian's FFmpeg  | nothing: tries it alone               |
| GStreamer players, WebKitGTK | GStreamer's `va` or V4L2     | ❓ `va` takes a non-Intel/AMD driver  |
| Kodi                         | VA-API, if built with it     | ❓ Debian's build; ours has none      |
| Vulkan Video programs        | ➖: Mali has no video driver |                                       |

FFmpeg picks no hardware itself: a program asks for a decoder by name (`h264_rkmpp`) or opens a
hwaccel device (`vaapi`, `v4l2request`). Firefox opens VA-API only.

## Each family, by layer

| Layer             | `rk35xx` (MPP)   | `sunxi-h616` (stateless) | `meson-gxl` (stateful) |
| ----------------- | ---------------- | ------------------------ | ---------------------- |
| VA-API driver     | `rockchip-vaapi` | `v4l2_request`           | none known             |
| Debian GStreamer  | an MPP plugin    | `v4l2codecs` ❓          | `v4l2` ❓              |
| Debian FFmpeg 7.1 | no `rkmpp`       | no `v4l2request`         | `v4l2m2m` ❓           |

No VA-API driver means no browser decode: `meson-gxl` has none. `rockchip-vaapi` is written for
RK3588 and Firefox; its HEVC is disputed upstream. Nothing known drives a stateful decoder through
VA-API.

## Two tiers

| Tier                              | Gets                                                 |
| --------------------------------- | ---------------------------------------------------- |
| Debian's programs                 | 1080p in hardware, linear frames; 4K where AFBC goes |
| Ours: fuseamp, Kodi, mpv's config | 4K and up: decoder scaling and AFBC to a plane       |

- **Linear frames carry 1080p, not 4K**: 4K needs AFBC end to end.
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
- [ ] **Debian's `libavcodec` stays stock on trixie**: our series, 38 patches on 9.0.2, is a port to
      7.1, not a backport, redone on each of its security updates. Our patches go upstream; forky's
      FFmpeg is the next look.
- [ ] **A VA-API driver a family**, packaged: `v4l2_request` for `sunxi-h616` first, the family
      closest to working stock and the only one where AFBC, and so 4K, can reach a browser;
      `rockchip-vaapi` for `rk35xx`; `meson-gxl` waits for a stateful driver.
- [ ] **GStreamer on `rk35xx`**: an MPP plugin package; AirPlay mirroring (`uxplay`) needs it.
- [ ] **Settings shipped**: Chromium's VA-API flags, `VaapiIgnoreDriverChecks` among them (it trusts
      only Intel, AMD and NVIDIA drivers), and `LIBVA_DRIVER_NAME` in `/etc/chromium.d/`; Firefox's
      VA-API prefs as a system prefs file; `hwdec=vaapi` in a system `mpv.conf`.
- [ ] **Encode** for WebRTC and screen capture: both VA-API drivers known are 🟡 decode-only.
- [ ] **Zero copy to the screen**: a VA-API frame imported by Lima and Panfrost without a CPU copy.
- [ ] **A matrix**: program by codec by family, in `tools/validate/`.
