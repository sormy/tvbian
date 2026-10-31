# kodi — Kodi 22 on GBM

Patches on Kodi `22.0rc1-Piers`, applied in order with `git am` or `patch -p1 -E`: `0003` deletes a
file.

| Patch  | Adds                                               | Upstream      |
| ------ | -------------------------------------------------- | ------------- |
| `0001` | `System.ExecWait` hands the display and input over | not submitted |
| `0002` | `-DFFMPEG_PATCHES` for the internal FFmpeg         | not submitted |
| `0003` | libcec and libdvdnav linked into `kodi-gbm`        | not upstream  |
| `0004` | `v4l2request` device options from the display      | not submitted |

`0001`: on GBM Kodi stays DRM master and keeps reading input while `System.ExecWait` runs, so a
program that needs the screen cannot open it, and its key presses reach Kodi afterwards. Around a
waiting `ExecWait`, Kodi now suspends libinput, blanks the CRTC and drops DRM master, then takes
them back. `System.Exec`, which does not wait, is unchanged. Compiles on arm64 trixie ✅ 2026-10-29;
on a box ❓.

`0002`: `-DFFMPEG_PATCHES`, a `;` list of absolute paths, applied to Kodi's internal FFmpeg before
its own `001`, `002` and `008`: how `patches/ffmpeg/` reaches `kodi-gbm`.

`0003`: libcec builds static, with `HAVE_LINUX_API`, which it defaults off and without which it
never opens `/dev/cec0`, and without X11 RandR. libdvdnav, libdvdread and libdvdcss link in instead
of a `libdvdnav-<arch>.so` loaded at runtime: the navigator calls them directly and `DllDvdNav.h`
goes, so Kodi's Windows build, which ships its own DLL, no longer compiles. Built on arm64 trixie ✅
2026-10-29: no libcec or DVD library installed, `kodi-gbm` holds the `dvdnav_` functions, and libCEC
reports `P8_USB, DRM, P8_detect, Linux_kernel_API`.

`0004`: Kodi created the `v4l2request` device with no options. For a picture no larger than the
display mode it now asks for `afbc` at each bit depth a plane on its CRTC scans out as `YUV420_8BIT`
or `YUV420_10BIT` with the 16x16 sparse split AFBC modifier; otherwise for `capture_max_width` and
`capture_max_height` from the mode, since a display may refuse to shrink an AFBC layer. Never both:
whether the decoder combines them is untested. Logged as
`CDVDVideoCodecDRMPRIME::Open - v4l2request option <key>=<value>`.

The captive-portal browser it is for, from an addon, ❓ not yet run:

```python
xbmc.executebuiltin('System.ExecWait("seatd-launch -- cage -- firefox-esr --kiosk <url>")')
```
