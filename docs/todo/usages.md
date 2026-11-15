# Three uses on one image

Every box boots the same minimal image. `apt install` turns it into any of three machines:

| Use    | Install                                     | Is                                             |
| ------ | ------------------------------------------- | ---------------------------------------------- |
| Server | nothing                                     | the minimal image as it ships: SSH, no display |
| Desk   | `tvb-labwc-session`                         | a desktop, 3D and video in hardware in apps    |
| TV     | `tvb-kodi-session` or `tvb-fuseamp-session` | the player from boot, driven by the remote     |

A `-session` package is a metapackage: it pulls a use's programs and makes them what the box boots
into. A box boots into one session, so the sessions conflict with each other; the programs do not.
The desk's programs are Debian's, on our Mesa and VA-API driver from the repo. `tvb-kodi` is Kodi
built with our patches (`kodi.md`); `tvb-fuseamp` installs beside it and beside the desk. Removing
the session leaves the server.

## Desk

One suggested setup, light enough for a Mali-450:

| Part            | Choice                                 | Why                                        |
| --------------- | -------------------------------------- | ------------------------------------------ |
| Compositor      | `labwc`                                | stacking, no animations; Raspberry Pi OS's |
| Top bar         | `waybar`                               | a macOS-like menu bar                      |
| Dock            | `nwg-dock`                             | a macOS-like dock                          |
| Theme           | WhiteSur GTK and icons                 | the macOS look; not in Debian              |
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
| Every app | `/etc/environment.d/`                 | `LIBVA_DRIVER_NAME`, our driver for the SoC       |
| Firefox   | `/usr/lib/firefox-esr/defaults/pref/` | `media.ffmpeg.vaapi.enabled`, the RDD sandbox off |
| Chromium  | `/etc/chromium.d/`                    | `--enable-features=VaapiVideoDecoder` and kin     |
| mpv       | `/etc/mpv/mpv.conf`                   | `hwdec=vaapi`                                     |
| GStreamer | `/etc/environment.d/`                 | the `va` plugin's decoders ranked first           |

The GPU and decoder of each SoC:

| SoC family  | GPU, Mesa driver     | Decoder            | VA-API backend |
| ----------- | -------------------- | ------------------ | -------------- |
| RK3528      | Mali-450, `lima`     | rkvdec through MPP | MPP            |
| H616, H313  | Mali-G31, `panfrost` | Cedrus, stateless  | V4L2 request   |
| GXLX2 (M20) | Mali-450, `lima`     | Amlogic, stateful  | V4L2 stateful  |

- [ ] **`tvb-labwc-session` exists**: Debian's labwc, the bar, dock and greeter as its depends, the
      login session set up; it installs onto the minimal image of every family.
- [ ] **The desktop runs at 1080p on every family**, idle CPU under 5 %, no dropped frames moving a
      window; 4K output only where the GPU holds it.
- [ ] **3D in hardware**: `glmark2-es2-wayland` runs on the GPU, not `llvmpipe`, on both kernels.
- [ ] **Video in hardware in Debian's apps**: Firefox, Chromium and mpv play H.264 and HEVC 1080p
      through VA-API, CPU under 30 %, on each family.
- [ ] **The defaults above, shipped by `tvb-labwc-session`**, each checked by the app's own report
      (`about:support`, `chrome://gpu`, mpv's `hwdec-current`), not assumed.
- [ ] **Encode in hardware** where the SoC has an encoder: `ffmpeg -c:v h264_v4l2m2m` or the MPP
      encoder from a webcam, measured.
- [ ] **Our Mesa and VA-API driver are published** in the repo, so `apt` picks ours over Debian's.
- [ ] **WhiteSur from upstream or not at all**: not in Debian; its licence checked first.
- [ ] **Measured on a `lima` box and a `panfrost` box**: frame rate of the desktop, a 1080p video in
      Firefox, memory after login.

## TV: `tvb-kodi`, `tvb-fuseamp`

| Part    | Choice                        | Why                                         |
| ------- | ----------------------------- | ------------------------------------------- |
| Player  | Kodi, ours; FuseAmp           | 4K in hardware, decoder scaling, AFBC       |
| Session | starts the player at boot     | no desktop between the remote and the TV    |
| Remote  | IR, BLE, CEC from the TV      | every box's handset                         |
| Video   | our FFmpeg (`extras/ffmpeg9`) | the hardware decoders Debian's FFmpeg lacks |

- [ ] **`tvb-kodi` exists**, Kodi built on our FFmpeg with our patches; `tvb-kodi-session` boots
      straight into it on every family.
- [ ] **`tvb-fuseamp` installs beside it**, and beside the desk; `tvb-fuseamp-session` once FuseAmp
      is ready for release.
- [ ] **The remote drives it from boot**: IR, BLE, and the TV's own remote over CEC.
- [ ] **4K HDR plays in hardware** on each family that decodes it.

## Both

- [ ] **One minimal image** for every use; the session installed is the only difference.
- [ ] **Switching use is installing another session**, the old one removed with no leftover service.
- [ ] **Each session's install is tested** by the regression suite on one box per family.
