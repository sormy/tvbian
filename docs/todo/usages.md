# Three uses on one image

Every box boots the same minimal image. `apt install` turns it into any of three machines:

| Use    | Install                     | Is                                             |
| ------ | --------------------------- | ---------------------------------------------- |
| Server | nothing                     | the minimal image as it ships: SSH, no display |
| Desk   | `tvb-desktop`               | a desktop, 3D and video in hardware in apps    |
| TV     | `tvb-kodi` or `tvb-fuseamp` | the player from boot, driven by the remote     |

A use's package is a metapackage: it pulls a use's programs and makes them what the box boots into.
A box boots into one session, so the sessions conflict with each other; the programs do not. The
desk's programs are Debian's, on our Mesa and VA-API driver from the repo. `tvb-kodi` is Kodi built
with our patches (`kodi.md`); `tvb-fuseamp` installs beside it and beside the desk. Removing the
session leaves the server.

## Desk

One suggested setup, light enough for a Mali-450:

| Part            | Choice                                 | Why                                        |
| --------------- | -------------------------------------- | ------------------------------------------ |
| Compositor      | `labwc`                                | stacking, no animations; Raspberry Pi OS's |
| Top bar         | `waybar`                               | a macOS-like menu bar                      |
| Dock            | `waybar`                               | a macOS-like dock                          |
| Theme           | WhiteSur, dark or light                | the macOS look; `extras/whitesur`          |
| Font            | Inter                                  | close to the macOS system font             |
| Login           | `greetd` with a graphical greeter      | Wayland-native                             |
| Audio           | PipeWire                               | Debian's default                           |
| 3D              | our Mesa (`extras/mesa`)               | Debian's is a third of Panfrost's speed    |
| Video in apps   | our VA-API driver (`tvb-va-driver`)    | browsers and players decode in hardware    |
| Browser, player | Firefox, Chromium, mpv, with VA-API on | their settings, not patches                |

Apps leave hardware decode off by default, so the session also ships the system-wide defaults that
send each one's video through VA-API:

| App       | Where                                 | What                                              |
| --------- | ------------------------------------- | ------------------------------------------------- |
| Firefox   | `/usr/lib/firefox-esr/defaults/pref/` | `media.ffmpeg.vaapi.enabled`, the RDD sandbox off |
| Chromium  | `/etc/chromium.d/`                    | `--enable-features=VaapiVideoDecoder` and kin     |
| mpv       | `/etc/mpv/mpv.conf`                   | `hwdec=vaapi`, `vo=dmabuf-wayland`, H.264 sites   |
| GStreamer | `tvb-va-driver`                       | `GST_VA_ALL_DRIVERS=1`                            |

The GPU and decoder of each SoC:

| SoC family  | GPU, Mesa driver     | Decoder            | VA-API backend |
| ----------- | -------------------- | ------------------ | -------------- |
| RK3528      | Mali-450, `lima`     | rkvdec through MPP | MPP            |
| H616, H313  | Mali-G31, `panfrost` | Cedrus, stateless  | V4L2 request   |
| GXLX2 (M20) | Mali-450, `lima`     | Amlogic, stateful  | V4L2 stateful  |

- [ ] **`tvb-desktop` on every family**: it installs onto the minimal image and logs in.
- [ ] **The desktop runs at 1080p on every family**, idle CPU under 5 %, no dropped frames moving a
      window; 4K output only where the GPU holds it.
- [ ] **3D in hardware**: `glmark2-es2-wayland` runs on the GPU, not `llvmpipe`, on both kernels.
- [ ] **Video in hardware in Debian's apps**: Firefox, Chromium and mpv play H.264 and HEVC 1080p
      through VA-API, CPU under 30 %, on each family.
- [ ] **The defaults above, shipped by `tvb-desktop`**, each checked by the app's own report
      (`about:support`, `chrome://gpu`, mpv's `hwdec-current`), not assumed.
- [ ] **Encode in hardware** where the SoC has an encoder: `ffmpeg -c:v h264_v4l2m2m` or the MPP
      encoder from a webcam, measured.
- [ ] **Our Mesa and VA-API driver are published** in the repo, so `apt` picks ours over Debian's.
- [ ] **A browser that keeps up on `lima`**: Firefox's WebRender and Chromium's GPU process both
      need OpenGL ES 3.0, and the Mali-450 has 2.0, so both paint on the CPU; so does WebKitGTK,
      whose GTK gets no GL context. `cog` and Qt WebEngine's `falkon` draw on Lima, yet decode video
      on the CPU.
- [ ] **Hardware video in WebKit on `rk35xx`**: its sandbox hides `/dev/mpp_service` and the device
      tree that MPP reads, so `cog` decodes in software.
- [ ] **YouTube in mpv out of the box**: Debian's `yt-dlp` is too old for YouTube.
- [ ] **A screen plugged in after login gets its scale**: `scale-outputs` runs at login only.
- [ ] **Measured on a `lima` box and a `panfrost` box**: frame rate of the desktop, a 1080p video in
      Firefox, memory after login.

## TV: `tvb-kodi`, `tvb-fuseamp`

| Part    | Choice                        | Why                                         |
| ------- | ----------------------------- | ------------------------------------------- |
| Player  | Kodi, ours; FuseAmp           | 4K in hardware, decoder scaling, AFBC       |
| Session | starts the player at boot     | no desktop between the remote and the TV    |
| Remote  | IR, BLE, CEC from the TV      | every box's handset                         |
| Video   | our FFmpeg (`extras/ffmpeg9`) | the hardware decoders Debian's FFmpeg lacks |

- [ ] **`tvb-kodi` exists**, Kodi built on our FFmpeg with our patches, booting straight into it on
      every family.
- [ ] **`tvb-fuseamp` installs beside it**, and beside the desk, once FuseAmp is ready for release.
- [ ] **The remote drives it from boot**: IR, BLE, and the TV's own remote over CEC.
- [ ] **4K HDR plays in hardware** on each family that decodes it.

## Both

- [ ] **One minimal image** for every use; the session installed is the only difference.
- [ ] **Switching use is installing another session**, the old one removed with no leftover service.
- [ ] **Each session's install is tested** by the regression suite on one box per family.
