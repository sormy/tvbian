# Kodi on our FFmpeg

Kodi 22 built on Debian stable, our FFmpeg 9.0.2 linked in statically, drawing through GBM and
decoding to DRM PRIME frames scaled to the screen and compressed where the plane takes them.

## Why our own

- trixie ships `kodi` 21.2 on Debian's FFmpeg 7.1: no `v4l2request`, none of `patches/ffmpeg/`. sid
  has 21.3; no Kodi 22 is packaged.
- Kodi 22.0rc1 (`22.0rc1-Piers`) pins FFmpeg 9.0.2, the release `patches/ffmpeg/` sits on.
- GBM draws on KMS and reads input through libinput: no X11 or Wayland libraries. Debian's 21.2
  pulls 251 packages, 568 MiB; ours, with Mesa without LLVM, 🟡 200–250 MiB.

## Building on trixie

Builds on arm64 trixie with `0001`, `0003` and Kodi's FFmpeg 9.0.2 ✅ 2026-10-29:
`apt-get build-dep kodi` plus `meson ninja-build bison`, 13 minutes on 10 cores; `kodi-gbm` 62 MiB,
`/usr/share/kodi` 46 MiB, stripped.

```bash
cmake <kodi> -DCORE_PLATFORM_NAME=gbm -DAPP_RENDER_SYSTEM=gles \
  -DENABLE_INTERNAL_EXIV2=ON -DENABLE_INTERNAL_NLOHMANNJSON=ON -DENABLE_INTERNAL_SWIG=ON \
  -DENABLE_INTERNAL_CEC=ON -DENABLE_INTERNAL_FFMPEG=ON \
  -DFFMPEG_EXTRA_FLAGS="--enable-libdrm --enable-libudev --enable-v4l2-request --enable-v4l2-m2m --disable-vaapi"
```

- Kodi 22 refuses trixie's exiv2, nlohmann_json and swig, and builds CEC off with trixie's libcec
  7.0: hence the internal ones.
- `FindFFMPEG.cmake` enables libva whenever it finds it, whatever `-DENABLE_VAAPI` says: hence
  `--disable-vaapi`.
- FFmpeg static inside Kodi: no second `libav*` beside Debian's. `patches/kodi/0002` applies
  `patches/ffmpeg/` before Kodi's own `001` and `008`; `0001`–`0018` apply cleanly with them ✅,
  `0019`–`0035` not yet tried.
- Debian's shared libraries stay shared: Mesa's driver, binary addons and Python modules load into
  Kodi, and their security updates come from Debian.

## Patches still to write

- **`0005`:** `-capture_max_width`, `-capture_max_height` and `-afbc` as decoder options to
  `*_v4l2m2m` and `*_rkmpp`, in `avcodec_open2`.
- **`0006`:** `FindDecoder` takes the first decoder with a `DRM_PRIME` hw config. The native `h264`
  and `hevc` carry `v4l2request`, ahead of `*_v4l2m2m` and `*_rkmpp`, and our device creation never
  fails: on Amlogic and Rockchip 🟡 the hwaccel fails at init and Kodi decodes in software. The
  decoder the box has, picked.
- Kodi switches the display mode at playback when "Adjust display refresh rate" is on: a mode larger
  than the GUI's leaves `0004`'s bound stale.

## Per family

| Family    | Decoder | Kodi reaches it through    | State                      |
| --------- | ------- | -------------------------- | -------------------------- |
| Allwinner | Cedrus  | `v4l2request`, `0004`      | ✅ AFBC to the plane, 6.18 |
| Amlogic   | GXLX2   | `*_v4l2m2m`, `0005` `0006` | ❓                         |
| Rockchip  | MPP     | `*_rkmpp`, `0005` `0006`   | ❓                         |

A frame goes to a plane only when one advertises its format and modifier; otherwise through GLES,
where Panfrost's AFBC YUV import is ❓ and Lima has none.

## What the media stick takes from Kodi

| Want           | In Kodi           | Addon                              |
| -------------- | ----------------- | ---------------------------------- |
| Bundled remote | libinput, keymaps |                                    |
| CEC            | libcec, `0003`    |                                    |
| Home share     | SMB, NFS          |                                    |
| USB stick      | UDisks2           | `udisks2` on the box               |
| YouTube, VP9   |                   | `plugin.video.youtube`             |
| DLNA renderer  | UPnP              |                                    |
| AirPlay audio  | AirTunes          |                                    |
| Jellyfin       |                   | `jellyfin-kodi` or JellyCon        |
| Plex           |                   | PlexKodiConnect                    |
| Gamepad        |                   | `peripheral.joystick`              |
| Wi-Fi          |                   | ❓ ours, over NetworkManager       |
| Captive portal | `0001`            | Firefox under `cage`, ❓           |
| YouTube cast   |                   | ❓ none known with DIAL and Lounge |

- Kodi's own repository builds binary addons for Android, macOS and Windows only: we build
  `inputstream.adaptive` and `peripheral.joystick` per Kodi release, as debs. Python addons install
  from the Kodi repository.
- `inputstream.adaptive` plays the YouTube addon's DASH; Widevine through it is L3.
- AirTunes needs `libshairplay-dev` at configure time; Zeroconf rides Avahi.
- LibreELEC's `appliance-gbm.xml` turns DRM PRIME decode on, direct to a plane; Kodi's default is
  off, so without it nothing reaches a hardware decoder.

## Plan

Each phase ends in something that runs; the next starts from it.

### 1. Extras take an upstream release

`UPSTREAM`, `TAG` or `TAGS`, `VERSION`, `AFTER`, and `extras/<name>/debian/`, through `version.sh`,
`carried.sh`, `build.sh`, `inputs.sh` and `plan.sh`.

- [ ] The scripts, with a Debian extra's path left as it is: mesa's inputs hash unchanged.
- [ ] `tests/` for both kinds.
- [ ] `docs/sources.md` and `docs/build.md`; the `extras/` row of the tree table in `AGENTS.md`.

### 2. `extras/kodi`, built

- [ ] `extra.conf` pinned on `22.0rc1-Piers`, `VERSION=2:22.0~rc1`, `PATCHES` `0001`–`0004`.
- [ ] `debian/control`: `kodi`, `kodi-bin`, `kodi-data`, `kodi-addons-dev`; Build-Depends Debian's
      own plus `meson`, `ninja-build`, `bison`, `libshairplay-dev`, `libdav1d-dev`; `kodi` provides
      `kodi-api-*` from `versions.h`.
- [ ] `debian/rules`: the configure line above, internal FFmpeg with its flags,
      `-DENABLE_VAAPI=OFF -DENABLE_VDPAU=OFF`, `-DCMAKE_BUILD_TYPE=Release`, the split by path. Kodi
      22's VAAPI code needs pixel formats Debian's FFmpeg 7.1 lacks; these boxes have none.
- [ ] `./build.sh extra kodi`: build time and the debs' installed size here.
- [ ] Installs on a box over `image/packages.list`; `kodi --windowing=gbm` reaches the home screen;
      the remote moves it.
- [ ] FFmpeg in `kodi-bin` lists `v4l2request` among its hwaccels.
- [ ] `appliance.xml` in `kodi-data`: DRM PRIME decode on, direct to a plane; AirPlay on.
- [ ] `service.xbmc.versioncheck` out of the addon manifest; `kodi` recommends `python3-pil` and
      `python3-pycryptodome`.

### 3. The video path

- [ ] `0004` on an Allwinner box: 4K HEVC on the plane from Kodi, `capture_max_*` from the GUI mode.
- [ ] Plane reads measured against fuseamp's.
- [ ] A failed plane commit reopens the decoder linear, as fuseamp does; `0004` predicts the refusal
      from the picture's size instead.
- [ ] `0005`, `0006` on an Amlogic box: `*_v4l2m2m` picked, FBC to the plane at 10 bits.
- [ ] `0005`, `0006` on a Rockchip box: `*_rkmpp` picked, AFBC to the plane.
- [ ] `0003`: the TV's remote moves Kodi; Kodi turns the TV on and off.

### 4. Binary addons

- [ ] `extras/kodi-inputstream-adaptive` and `extras/kodi-peripheral-joystick`: upstream extras on
      their `Piers` tags, `AFTER=kodi`, Debian's package names.
- [ ] YouTube through `plugin.video.youtube` on VP9; a gamepad drives the menus.

### 5. The Kodi image

- [ ] `./build.sh image <board> kodi` → `tvbian-<board>-<suite>-kodi-<date>.img.xz`: our Kodi debs
      from `/out/debs` beside the `tvb-*` ones, as `packages.list` would take Debian's 21.
- [ ] A `kodi` user in `video render audio input`, and a unit starting Kodi on GBM at boot.
- [ ] `udisks2`, for removable media.
- [ ] The release builds both images per board: CI time and the release's size checked.

### 6. The media stick on it

- [ ] `0001` on a box: Firefox up under `cage`, Kodi back with its remote, no stray keys.
- [ ] The NetworkManager addon: Wi-Fi, and the hotspot a phone completes a portal through.
- [ ] The Firefox wrapper: ends itself once NetworkManager reports full connectivity.
