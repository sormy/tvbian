# Hardware decoding in Debian's programs

Which Debian 13 programs decode video in hardware on a TVBian box, and how they reach the chip.
`video-support.md` lists what each chip decodes; this page lists which programs get to use it. Read
from Debian's packaging and the upstream source Debian builds (2026-11-13); only `ffmpeg9` is
measured on a box so far.

A program reaches the video hardware one of three ways:

- **V4L2, through GStreamer**: Debian's GStreamer already drives the H313's decoder and the
  S905L3's, ranked above software. Nothing to install.
- **VA-API**: what most players and browsers ask for. TVBian's driver, `tvb-va-driver-<family>`
  (`va-driver/README.md`), answers it on every chip; packaged, no image installs it yet.
- **`ffmpeg9`**: TVBian's FFmpeg, every chip, the command line.

Debian ships no VA-API driver for these chips: Mesa's cover AMD, NVIDIA and virgl only. Its `ffmpeg`
has no `v4l2request` for the H313 and no `rkmpp` for the RK3518 and RK3528 (RK35xx below), and its
V4L2 decoders copy every frame to memory.

The chip columns are Debian as installed, without the VA driver; the last column, with it. ✅
measured · 🟡 the path exists, not tried · 🟠 works with known faults · ❓ unknown · ➖ no path.

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
  the H313 (`/dev/media*`) and RK35xx (`/dev/mpp_service`) need `MOZ_DISABLE_RDD_SANDBOX=1`.
- **Chromium** opens only PCI GPUs for VA-API unless given
  `--hardware-video-device-path=/dev/dri/renderD128` ([vaapi_wrapper.cc][cr-vaapi]); a file in
  `/etc/chromium.d/` carries the flag. Its GPU sandbox opens only `/dev/dri` ([sandbox
  hook][cr-hook]): ❓ whether it lets the decoder's calls through.
- **Epiphany**'s sandbox opens `/dev/video*` and `/dev/media*`, not RK35xx's `/dev/mpp_service`
  ([BubblewrapLauncher.cpp][wk-bwrap]).

## Transcoding, editing and serving

| Program                    | Asks for           | H313 | RK35xx | S905L3 | With the VA driver |
| -------------------------- | ------------------ | ---- | ------ | ------ | ------------------ |
| [ffmpeg 7.1][ffmpeg]       | VA-API, V4L2       | ➖   | ➖     | 🟠     | every chip         |
| `ffmpeg9`, TVBian's        | V4L2, MPP          | ✅   | ✅     | ✅     | not needed         |
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
