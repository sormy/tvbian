# Hardware decoding in Debian's programs

Which Debian 13 programs decode video in hardware on a TVBian box, and how they reach the chip.
`video-support.md` lists what each chip decodes; this page lists which programs get to use it. Read
from Debian's packaging and the upstream source Debian builds (2026-11-13); `ffmpeg9` and the VA
driver are measured on a box.

A program reaches the video hardware one of three ways:

- **V4L2, through GStreamer**: Debian's GStreamer already drives the H313's decoder and the
  S905L3's, ranked above software. Nothing to install.
- **VA-API**: what most players and browsers ask for. TVBian's driver, `tvb-va-driver`
  (`va-driver/README.md`), answers it on every chip; packaged, no image installs it yet.
- **`ffmpeg9`**: TVBian's FFmpeg, every chip, the command line.

Debian ships no VA-API driver for these chips: Mesa's cover AMD, NVIDIA and virgl only. Its `ffmpeg`
has no `v4l2request` for the H313 and no `rkmpp` for the RK3518 and RK3528 (RK35xx below), and its
V4L2 decoders copy every frame to memory.

The chip columns are Debian as installed, without the VA driver; the last column, with it. ✅
measured · 🟡 the path exists, not tried · 🟠 works with known faults · ❓ unknown · ➖ no path.

## What the VA driver decodes and encodes

Measured 2026-11-15 with `va-driver/tests/vaapi_test.py` on `tanix-tx1-v2` and `h96max-h313` (H313),
`r69-1` (RK3518) and `h96max-m20` (S905L3, `meson-codecs` `0033`–`0036`). Each limit is what the
engine reports, not a table: the largest picture offered.

| Decode            | H313                | RK35xx              | S905L3              |
| ----------------- | ------------------- | ------------------- | ------------------- |
| H.264 8-bit       | ✅ exact, 4096×2304 | ✅ exact, 8192×4320 | ✅ exact, 3840×2160 |
| H.264 10-bit      | ➖                  | ➖ not offered      | ➖                  |
| HEVC Main         | ✅ exact, 8192×4320 | ✅ exact, 8192×4320 | ✅ exact, 4096×2304 |
| HEVC Main 10      | ✅ exact, 6144×3456 | ✅ 56 dB, 8192×4320 | ✅ 61 dB, 4096×2304 |
| VP9 profile 0     | ✅ exact, 8192×4320 | ✅ exact, 8192×4320 | ✅ exact, 3840×2160 |
| VP9 profile 2     | ✅ exact, 6144×3456 | ✅ 61 dB, 8192×4320 | ✅ 65 dB, 3840×2160 |
| VP8               | ✅ exact, 4096×2304 | ✅ exact, 1920×1088 | ➖                  |
| MPEG-2            | ✅ 74 dB, 4096×2304 | ✅ 73 dB, 1920×1088 | 🟠 69 dB, 1920×1088 |
| MPEG-4 SP, ASP    | ✅ 68 dB, 4080×2304 | ✅ 68 dB, 1920×1088 | 🟠 53 dB, 1920×1088 |
| H.263             | ✅ 71 dB, 4080×2304 | ✅ 71 dB, 1920×1088 | ➖                  |
| VC-1 Advanced     | ✅ exact, 4096×2304 | ➖                  | 🟠 1920×1088        |
| VC-1 Simple, Main | ❓ Simple; ➖ Main  | ➖                  | ➖                  |
| JPEG              | ✅ 77 dB, 6000×6000 | ➖                  | ✅ 71 dB, 1920×1088 |

| Encode | H313                | RK35xx              | S905L3              |
| ------ | ------------------- | ------------------- | ------------------- |
| H.264  | ✅ 52 dB, 4096×4096 | ✅ 53 dB, 1920×1088 | ✅ 49 dB, 1920×1088 |
| HEVC   | ➖                  | ✅ 48 dB, 1920×1088 | ✅ 48 dB, 4096×2304 |
| JPEG   | ✅ 43 dB, 4096×4096 | ➖                  | ➖                  |

"exact" is every frame identical to FFmpeg's software decode; a figure in dB is the worst clip's
luma PSNR against it, from the engine's IDCT or a 10-bit picture narrowed to 8 bits. Encode is
decoded back.

- **Limits come from the engine:** V4L2's frame sizes, or the size `TRY_FMT` clamps to, and its
  profile menus; on the H313 a 10-bit size is probed with the stream header Cedrus checks. MPP
  reports its SoC's decoders and encoders as 8K, 4K or 1080p classes.
- **RK35xx 10-bit** comes out of MPP as NV15, unpacked to P010 or narrowed to NV12 by the CPU.
- **RK35xx interlaced MPEG-2 and MPEG-4, H313 interlaced MPEG-4** are refused, as through `ffmpeg9`.
- **S905L3 10-bit** is written by the decoder as 8 bits, widened into the client's P010.
- **S905L3 MPEG-1/2/4 and VC-1** hold their last pictures until more stream comes. A player that
  feeds ahead, as mpv, Kodi and browsers do, gets every picture. A client that waits for each before
  sending the next, as FFmpeg's command line, gets some refused, never wrong: `VAAPI_HELD_PICTURES`,
  or `held-pictures` in `/etc/tvb-va-driver.conf`, sets `refuse` (the default), `off` or `decoded`.
  Interlaced MPEG-4 comes out at 44 dB, as through `ffmpeg9`.
- **S905L3 H.264 encode** writes Main streams; it is offered as High too, which FFmpeg asks first.
- **Rate control** is what each encoder lists: a fixed QP, VBR and CBR on the H313 and RK35xx; a
  fixed QP and VBR on the S905L3.
- **H.264 10-bit** has no VA profile FFmpeg 7.1 uses: RK35xx decodes it through `ffmpeg9` only.

## Players

| Program                     | Asks for          | H313 | RK35xx | S905L3 | With the VA driver |
| --------------------------- | ----------------- | ---- | ------ | ------ | ------------------ |
| [mpv 0.40][mpv]             | libavcodec        | ➖   | ➖     | 🟠     | every chip         |
| [Celluloid 0.28][celluloid] | mpv               | ➖   | ➖     | 🟠     | every chip         |
| [Haruna 1.4][haruna]        | mpv               | ➖   | ➖     | ➖     | every chip         |
| [SMPlayer 24.5][smplayer]   | mpv               | ➖   | ➖     | 🟠     | every chip         |
| [VLC 3.0.24][vlc]           | VA-API, VDPAU     | ➖   | ➖     | ➖     | every chip         |
| [Kodi 21.2][kodi]           | VA-API, DRM PRIME | ➖   | ➖     | ➖     | every chip         |
| [Totem 43.2][totem]         | GStreamer         | 🟡   | ➖     | 🟡     | adds RK35xx        |
| [Showtime 48.1][showtime]   | GStreamer         | 🟡   | ➖     | 🟡     | adds RK35xx        |
| [Clapper 0.8][clapper]      | GStreamer         | 🟡   | ➖     | 🟡     | adds RK35xx        |
| [Parole 4.18][parole]       | GStreamer         | 🟡   | ➖     | 🟡     | adds RK35xx        |

- **mpv** and its front ends decode in software unless told: set `hwdec=vaapi` in
  `/etc/mpv/mpv.conf`. On the S905L3 today `--hwdec=v4l2m2m-copy` works, with the faults TVBian's
  FFmpeg patches fix (resolution changes, drain). `hwdec=auto` never picks V4L2
  ([vd_lavc.c][mpv-lavc]).
- **VLC 3** and **Kodi 21** know VA-API and nothing else here, and both test a surface before the
  first frame ([converter_vaapi.c][vlc-gl], [VaapiEGL.cpp][kodi-egl]).
- **GStreamer players** keep V4L2 on the H313 and S905L3 with the VA driver installed: at equal rank
  the name decides ([rank_compare][gst-rank]). Only RK35xx moves to VA-API.

## Browsers

| Program                    | Asks for         | H313 | RK35xx | S905L3 | With the VA driver     |
| -------------------------- | ---------------- | ---- | ------ | ------ | ---------------------- |
| [Firefox ESR 153][ff-deb]  | VA-API, V4L2     | ➖   | ➖     | ➖     | S905L3; others: a flag |
| [Chromium 156][chromium]   | VA-API           | ➖   | ➖     | ➖     | ❓ with flags          |
| [Epiphany 48.5][webkit]    | GStreamer        | 🟡   | ➖     | 🟡     | no change: its sandbox |
| [Qt WebEngine 6.8.2][qtwe] | built without it | ➖   | ➖     | ➖     | ➖                     |

- **Firefox** turns hardware decoding on by itself once its probe passes ([GfxInfo.cpp][ff-gfx]).
  Its decoder sandbox opens only `/dev/video*` ([broker policy][ff-sandbox]): enough on the S905L3;
  the H313 (`/dev/media*`) and RK35xx (`/dev/mpp_service`) need `MOZ_DISABLE_RDD_SANDBOX=1`, which
  `tvb-va-driver` sets there.
- **Chromium** opens only PCI GPUs for VA-API unless given
  `--hardware-video-device-path=/dev/dri/va` ([vaapi_wrapper.cc][cr-vaapi]), the render node
  `tvb-va-driver`'s udev rule links for the GPU, whatever its number; a file in `/etc/chromium.d/`
  carries the flag. Its GPU sandbox opens only `/dev/dri` ([sandbox hook][cr-hook]): ❓ whether it
  lets the decoder's calls through.
- **Epiphany**'s sandbox opens `/dev/video*` and `/dev/media*`, not RK35xx's `/dev/mpp_service`
  ([BubblewrapLauncher.cpp][wk-bwrap]).

## Transcoding, editing and serving

| Program                    | Asks for           | H313 | RK35xx | S905L3 | With the VA driver |
| -------------------------- | ------------------ | ---- | ------ | ------ | ------------------ |
| [ffmpeg 7.1][ffmpeg]       | VA-API, V4L2       | ➖   | ➖     | 🟠     | every chip         |
| `ffmpeg9`, TVBian's        | V4L2, MPP, VA-API  | ✅   | ✅     | ✅     | not needed         |
| GStreamer pipelines        | V4L2, VA-API       | 🟡   | ➖     | 🟡     | adds RK35xx        |
| [Kdenlive 24.12][kdenlive] | VA-API             | ➖   | ➖     | ➖     | every chip         |
| [Shotcut 25.03][shotcut]   | VA-API             | ➖   | ➖     | ➖     | every chip         |
| [Jellyfin][jf-rules]       | VA-API, MPP        | ➖   | ❓     | ❓     | needs VA scaling   |
| [Gerbera 2.4][gerbera]     | a command it runs  | ✅   | ✅     | ✅     | not needed         |
| [Rygel 0.44][rygel]        | GStreamer          | ❓   | ➖     | ❓     | ❓ adds RK35xx     |
| [UxPlay 1.71][uxplay]      | GStreamer          | 🟡   | ➖     | 🟡     | adds RK35xx        |
| [HandBrake 1.9][handbrake] | Intel, NVIDIA only | ➖   | ➖     | ➖     | ➖                 |
| [OBS 30.2][obs]            | VA-API, OpenGL 3.3 | ➖   | ➖     | ➖     | ➖                 |

- **Jellyfin** scales and encodes in hardware too (`scale_vaapi`, `*_vaapi`): decoding alone does
  not make it transcode there. Its own FFmpeg brings MPP, which Jellyfin verifies on the RK3588 only
  ([Rockchip page][jf-rk]).
- **OBS** does not start: it needs OpenGL 3.3, and the boxes' GPUs give 3.1 (Panfrost) and 2.1
  (Lima) ([gl-subsystem.c][obs-gl], [panfrost.rst][mesa-panfrost], [lima.rst][mesa-lima]).
- **Gerbera** transcodes with the command it is given: `ffmpeg9` on every chip.
- **minidlna** serves files as they are: nothing to decode.

## Audio

No chip here decodes audio in hardware that Linux reaches. Surround sound reaches an AV receiver as
HDMI passthrough, as mpv, VLC and Kodi send it; ❓ untested on every board.

## Open

- [ ] Each 🟡 on a box: GStreamer players on the H313 and S905L3.
- [ ] Chromium with the flag, on each chip: its sandbox against the decoder's calls.
- [ ] Firefox on Lima: whether it still decodes when its renderer falls back to software.
- [ ] Jellyfin's own MPP build on the RK3528.
- [ ] HDMI audio passthrough on each family.

[celluloid]: https://sources.debian.org/src/celluloid/trixie/debian/control/
[chromium]:
  https://salsa.debian.org/chromium-team/chromium/-/blob/debian/156.0.8078.79-1_deb13u1/debian/rules#L93
[clapper]: https://sources.debian.org/src/clapper/trixie/debian/control/
[cr-hook]:
  https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.79/content/common/gpu_pre_sandbox_hook_linux.cc#622
[cr-vaapi]:
  https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.79/media/gpu/vaapi/vaapi_wrapper.cc#1618
[ff-deb]: https://salsa.debian.org/mozilla-team/firefox/-/blob/debian/153.7.0esr-1/debian/control.in
[ff-gfx]:
  https://github.com/mozilla-firefox/firefox/blob/FIREFOX_153_7_0esr_RELEASE/widget/gtk/GfxInfo.cpp#L1282
[ff-sandbox]:
  https://github.com/mozilla-firefox/firefox/blob/FIREFOX_153_7_0esr_RELEASE/security/sandbox/linux/broker/SandboxBrokerPolicyFactory.cpp#L863
[ffmpeg]: https://sources.debian.org/src/ffmpeg/trixie/debian/rules/
[gerbera]: https://sources.debian.org/src/gerbera/trixie/debian/control/
[gst-rank]:
  https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/1.26.2/subprojects/gstreamer/gst/gstpluginfeature.c#L395
[handbrake]: https://sources.debian.org/src/handbrake/trixie/debian/rules/
[haruna]: https://invent.kde.org/multimedia/haruna/-/blob/v1.4.0/src/settings/playbacksettings.kcfg
[jf-rk]: https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/rockchip
[jf-rules]: https://github.com/jellyfin/jellyfin-ffmpeg/blob/jellyfin/debian/rules#L68
[kdenlive]: https://sources.debian.org/src/kdenlive/trixie/debian/control/
[kodi]: https://sources.debian.org/src/kodi/trixie/debian/rules/
[kodi-egl]:
  https://github.com/xbmc/xbmc/blob/21.2-Omega/xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/VaapiEGL.cpp#L606
[mesa-lima]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.0.7/docs/drivers/lima.rst
[mesa-panfrost]:
  https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.0.7/docs/drivers/panfrost.rst
[mpv]: https://sources.debian.org/src/mpv/trixie/debian/rules/
[mpv-lavc]: https://github.com/mpv-player/mpv/blob/v0.40.0/video/decode/vd_lavc.c#L262
[obs]: https://sources.debian.org/src/obs-studio/trixie/debian/rules/
[obs-gl]: https://github.com/obsproject/obs-studio/blob/30.2.3/libobs-opengl/gl-subsystem.c#L137
[parole]: https://sources.debian.org/src/parole/trixie/debian/control/
[qtwe]: https://github.com/qt/qtwebengine/blob/v6.8.2/src/core/api/configure.cmake#L165
[rygel]: https://sources.debian.org/src/rygel/trixie/debian/control/
[shotcut]: https://sources.debian.org/src/shotcut/trixie/debian/control/
[showtime]: https://sources.debian.org/src/showtime/trixie/debian/control/
[smplayer]: https://github.com/smplayer-dev/smplayer/blob/v24.5.0/src/preferences.cpp#L257
[totem]: https://sources.debian.org/src/totem/trixie/debian/control/
[uxplay]: https://sources.debian.org/src/uxplay/trixie/debian/control/
[vlc]: https://sources.debian.org/src/vlc/trixie/debian/rules/
[vlc-gl]:
  https://github.com/videolan/vlc/blob/3.0.24/modules/video_output/opengl/converter_vaapi.c#L330
[webkit]: https://salsa.debian.org/webkit-team/webkit/-/blob/debian/2.54.0-1_deb13u3/debian/rules
[wk-bwrap]:
  https://github.com/WebKit/WebKit/blob/webkitgtk-2.54.0/Source/WebKit/UIProcess/Launcher/glib/BubblewrapLauncher.cpp#L493
