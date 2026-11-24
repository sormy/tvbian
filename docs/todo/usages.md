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

| Part            | Choice                                                                         | Why                                                         |
| --------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| Compositor      | `labwc`                                                                        | stacking, no animations; Raspberry Pi OS's                  |
| Top bar         | `waybar`                                                                       | a macOS-like menu bar                                       |
| Dock            | `waybar`                                                                       | a macOS-like dock                                           |
| Theme           | WhiteSur, dark or light                                                        | the macOS look; `extras/whitesur`                           |
| Font            | Inter                                                                          | close to the macOS system font                              |
| Login           | `greetd` with a graphical greeter                                              | Wayland-native                                              |
| Audio           | PipeWire                                                                       | Debian's default                                            |
| 3D              | our Mesa (`extras/mesa`)                                                       | Debian's is a third of Panfrost's speed                     |
| Video in apps   | our VA-API driver (`tvb-va-driver`)                                            | browsers and players decode in hardware                     |
| Browser, player | Falkon, mpv, with VA-API on                                                    | Falkon draws on every GPU; Firefox and Chromium need GLES 3 |
| Apps            | foot, pcmanfm, featherpad, lximage-qt, qpdfview, xarchiver, galculator, lxtask | light; Qt ones share Falkon's Qt                            |
| Settings        | pavucontrol-qt, wdisplays, blueman, nm-applet, from the bar                    | audio, screens, Bluetooth, Wi-Fi                            |

Two toolkits, each by role: GTK 3 for the shell, which waybar and gtkgreet are, and Qt 6 for apps,
which Falkon brings and the rest share nearly free; no GTK 4 and no Python but blueman's.
`apt install --install-recommends tvb-desktop` installs it: the session's own parts are its depends,
its apps recommends, each removable alone. Apps leave hardware decode off by default, so the session
also ships the system-wide defaults that send each one's video through VA-API:

| App       | Where               | What                                            |
| --------- | ------------------- | ----------------------------------------------- |
| mpv       | `/etc/mpv/mpv.conf` | `hwdec=vaapi`, `vo=dmabuf-wayland`, H.264 sites |
| GStreamer | `tvb-va-driver`     | `GST_VA_ALL_DRIVERS=1` everywhere but meson     |

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
- [ ] **Video in hardware in the desk's apps**: Falkon and mpv play H.264 and HEVC 1080p through
      VA-API, CPU under 30 %, on each family.
- [ ] **The defaults above, shipped by `tvb-desktop`**, each checked by the app's own report (mpv's
      `hwdec-current`), not assumed.
- [ ] **Encode in hardware** where the SoC has an encoder: `ffmpeg -c:v h264_v4l2m2m` or the MPP
      encoder from a webcam, measured.
- [ ] **Our Mesa and VA-API driver are published** in the repo, so `apt` picks ours over Debian's.
- [ ] **Falkon on WPE as the desk's `falkon`** (`falkon-wpe.md`): Debian's, on Qt WebEngine, draws
      on Lima yet decodes video on the CPU.
- [ ] **Hardware video in WebKit on `rk35xx`**: its sandbox hides `/dev/mpp_service` and the device
      tree that MPP reads, so `cog` decodes in software.
- [ ] **YouTube in mpv out of the box**: Debian's `yt-dlp` is too old for YouTube.
- [ ] **A screen plugged in after login gets its scale**: `scale-outputs` runs at login only.
- [ ] **`scale-outputs` picks the scale by the panel's shape**, not by its pixel count alone.
- [ ] **A greeter without the session chooser**: one session installed, nothing to choose; the login
      screen in the desktop's own look.
- [ ] **The bar's status as icons**: display, Bluetooth and volume drawn as icons; Wi-Fi as its
      signal, without the network's name.
- [ ] **The desktop fluid at the screen's own resolution on Mali-450**: at 4K, `wdisplays` and a
      moved window are a slideshow on the M2 Plus.
- [ ] **Lean on the M2 Plus**: only what the desk needs started at login, measured against the 1080p
      row above.
- [ ] **Falkon finished as an app**: blank icons (`qt6-svg-plugins` missing), tabs without a close
      button, 10 s to its first window, Qt's own theme in place of the system's.
- [ ] **The patched Chromium as a desk browser**: `research/chromium-gles2/patch.py` applied to
      Debian's binary by a dpkg trigger, its overlay and VA-API switches in `tvb-va-driver`'s
      Chromium file; YouTube 4K60 windowed at 60 fps, 40 today, decode starved by the page's CPU.
- [ ] **Measured on a `lima` box and a `panfrost` box**: frame rate of the desktop, a 1080p video in
      Falkon, memory after login.

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
