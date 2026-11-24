# Falkon on WPE WebKit: the desk's browser on GLES 2

Falkon on WPE WebKit through `qtwpewebkit` is the browser where Firefox and Chromium paint on the
CPU: every `lima` box. It is worth shipping only as a browser that decodes video, and encodes a
call's, in hardware on every family. What it still lacks.

## Video

- [ ] **Hardware decoding in Falkon on every family, for every codec a site sends**: H.264, HEVC and
      VP9, as a file and through Media Source Extensions as video sites stream it.
      `tools/validate/browser.py` plays each clip both ways and names the decoder WebKit made. The
      M20, first run, files only: all nine clips decoded on the engine, presented at 0.63 to 0.90 of
      their rate at 1080p60, under 1 fps at 4K60. The H313 and the M2 Plus are still to run.
- [ ] **Falkon showing what it decodes on the H313**: H.264 1080p60 as a file decodes 34 frames a
      second and shows 12, where Chromium shows every frame at 1.00x; WPE's MiniBrowser never
      reports. On 18 November, with WPE 2.54.3: VP9 1080p60 as a file decodes 49 a second and shows
      0.1.
- [ ] **WebKit picking `tvb-va-driver`'s decoders**: on the M20 it takes GStreamer's stateful
      `v4l2vp9dec`, ranked as `vavp9dec`, which stalls; the driver's profile demotes only the
      stateless `v4l2sl*` ones. On 18 November, through GStreamer's V4L2 decoders: H.264 presents
      nothing, HEVC as a file fails with "Could not read from resource", and only VP9 1080p plays,
      0.88x as a file, 0.76x through MSE.
- [ ] **YouTube at 2160p60 for a whole video**: on the M2 Plus, chosen in the player's menu, it
      plays VP9 3840x2160@60 (itag 315) through `vavp9dec`, the web process at 38% of a core, then
      after about a minute stops with "Something went wrong" and an empty buffer while the box
      downloads at 178 Mbit/s. On the H313, with Panfrost's alignment fixed, Falkon decodes and gets
      the same cut-off (403s on itag 18) while Chromium plays the same video two minutes through.
      Not the user agent: a genuine Chrome one played once and was cut off the next run, as was
      WebKit's own Chrome quirk. Tallied on 19 November, eight runs a box: a run plays its three
      minutes or stops about 33 seconds after play, half and half, AdBlock on (5 of 8) or off (4 of
      8), with the 403s on itag 18 in full plays and stopped ones alike. In a stopped run the page
      itself closes its MediaSource, no WebKit or GStreamer error before it: YouTube's script ends
      it, at the same point each time, as a check it makes of the viewer would. Untried: a person's
      session on a screen, which a headless one with a synthetic click may not pass for.
- [ ] **YouTube playing in Falkon, every time and on every family**: on 19 November it plays on the
      M2 Plus, VP9 through `vavp9dec` across six size switches, played by the check's click
      (`wlrctl`) with the page's console on (`FALKON_ENABLE_JS_OUTPUT`). Earlier runs there and on
      the H313 ended in "Something went wrong" after a 403 on the player's fallback stream (itag
      18); on the H313 the page also takes a minute, its web process at 160% of a core. On the H313
      `vavp9dec` decodes, but Panfrost rejects its pictures ("unsupported offset or stride
      alignment") at YouTube's small sizes, and the player gives up.
- [ ] **YouTube on the M20**: its VP9 through MSE stops after a few frames on `v4l2vp9dec`; with the
      V4L2 decoders demoted, WebKit makes no decoder at all. Meson's VP9 hands a picture over a
      packet late. And the box has 2 GB with 512 MB of CMA: Falkon and its web process swap. On 18
      November the video never starts: 0:00 after the play key, the web process at 80% of a core. On
      19 November, clicked: `v4l2vp9dec` decodes (2639 interrupts in two minutes), then its CAPTURE
      pool fails to allocate at the player's size switch, with CMA 390 of 512 MB free and nothing in
      the kernel log; the player shows "Something went wrong".
- [ ] **A file that sometimes shows nothing**: Falkon played HEVC 1080p60 at 0 frames once on the M2
      Plus, where every other H.264 and HEVC file plays at 1.00x at 1080p and 4K, and VP9 1080p60 at
      0 once on the H313, 0.92x the next run.
- [ ] **Falkon losing its compositor on the M20**: an HEVC 1080p60 MSE play on 20 November ended
      "Error reading events from display: Broken pipe", the file play before it fine. Once; watch
      whether it repeats, and what labwc logged.
- [ ] **The check's file numbers that do not add up**: VP9 4K60 as a file on the H313 reported a
      media rate of 1.04x to 1.14x from 16 to 40 pictures decoded a second, and H.264 1080p60
      "failed" at 54 fps shown with 60 decoded and the clock at 1.00x. Find what
      `requestVideoFrameCallback` counts on WebKit's file player, and judge a play on the clock and
      the frames decoded and shown together.
- [ ] **YouTube above 480p on `rk35xx`**: its player switches VP9 size mid-stream, which MPP fails;
      the player stops with an error.
- [ ] **YouTube's first minute at full quality**: the page's start-up load holds its bandwidth
      estimate near 1 Mbit/s for about 70 s, then 25 to 35.
- [ ] **VP9 4K60 at its rate on `rk35xx`**: 44 fps presented with the sandbox on.
- [ ] **Every clip at its rate**: 1080p60 and 4K presented at 91 to 93% of the clip's rate on the M2
      Plus, at 30 fps as at 60.
- [ ] **4K30 on `sunxi-h616`**: VP9 and HEVC stall at about 2 fps where `gst-launch` keeps up; 4K24
      plays. On 18 November Falkon plays H.264, HEVC and VP9 4K at 0 to 0.3x on the H313, files and
      MSE, where Chromium plays 4K30 at 0.9 to 1.0x. On 19 November GStreamer alone keeps up at 4K30
      there: VA into DMABuf decodes HEVC at 66, VP9 at 69 and H.264 at 41 frames a second, and into
      `glimagesink` HEVC presents 37 and VP9 56, into `waylandsink` 51 and 53. So the decoder,
      Panfrost's import and the display keep 4K; the stall is in WebKit's or `qtwpewebkit`'s
      presentation, holding pictures the decoder then waits for. Falkon's own HEVC 4K30 there runs
      0.28x, 0.54x and 0.84x from one run to the next, and Chromium's 0.75x to 1.00x, with
      `avahi-daemon` at a fifth of the box in one: a 4K verdict wants repeated runs on a quiet box.
      With AdBlock's cache warm, three runs: HEVC 4K30 as a file 0.41x, 0.15x, 0.15x, through MSE
      0.77x, 0.82x, 0.72x (Chromium's file 1.00x, MSE 0.74x to 0.78x). The file player pauses for
      buffering again and again ("Pausing stream for buffering"), on a clip of 30 Mbit/s that HEVC
      1080p60 has too and plays: WebKit's HTTP source, which hands its data over on the web
      process's main thread, falling behind at 4K, is the suspect. It was its download's pause: 2%
      of the clip, resumed at 80 ms of media. With `0009` (no pause below 32 MiB) HEVC and VP9 4K30
      files play at 1.00x there, twice over. H.264 4K30 plays at 0 to 0.35x, 12.6 decoded a second,
      where GStreamer alone presents it at 33 (`glimagesink`) and 34 (`waylandsink`): the Cedrus
      engine's own edge, H.264 4K at 30 being the H616's stated limit, with WebKit's cost on top.
- [ ] **The media download's floor found, not fixed at 32 MiB**: WebKit pauses a file's download at
      2% of its size and resumes below 1%, which for a small 4K file left the decoder starving on
      the H313; `0009` sets a floor of 32 MiB under both. Fixed bytes are wrong at both ends: a
      high-bitrate stream can drain 32 MiB in seconds, a low one holds minutes. Find it instead:
      from the stream's bitrate (its size over its duration, or the demuxer's), keep some seconds of
      media ahead, bounded by the box's memory; then send that, not the constant, upstream.

## Calls

- [ ] **A camera in a call**: with `vivid` on the M20 as a camera (1280x720, GStreamer captures it),
      WebKit lists no device: its web process enumerates inside the sandbox, which binds
      `/dev/video*` but not `/sys/class` or `/run/udev`, so GStreamer's V4L2 provider finds none.
      WebKit expects cameras through the camera portal and PipeWire, which the test's session does
      not run: `browser.py`'s `call-camera` to run in a session with PipeWire and the portal.
- [ ] **A canvas captured at 30 frames a second in WebKit**: a 720p30 call from a canvas sends 15 to
      19 frames a second on the H313 and the M2 Plus, in Falkon and MiniBrowser alike, where
      Chromium sends 29 on the H313. Every frame captured is encoded, and the encoder makes 53 a
      second. The capture is the cap: WebKit reads the whole canvas back on the main thread, 14 ms
      at 720p, in a zero-delay timer that waits behind the page's own rendering, so it runs about 19
      times a second while the page paints 54. A camera's frames come through GStreamer and miss it;
      untried without a camera.
- [ ] **A constrained-baseline H.264 encoder on the M20**: see the Amlogic list; until then a WebKit
      call there has no hardware H.264.
- [ ] **Chromium's encoder in the call check**: Chromium's stats name no encoder without a camera
      granted; on the H313 its call sends 29.5 fps through `tvb-va-driver`'s encoder, which only its
      own log shows.
- [ ] **Firefox's calls in hardware**: Firefox ESR 153 encodes WebRTC's H.264 with libx264 even when
      hardware encoding is forced, so its calls stay on the CPU.
- [ ] **Firefox's media sandbox, off for hardware decoding**: Firefox ESR 153 decodes through VA
      only with `MOZ_DISABLE_RDD_SANDBOX=1`, which `tvb-va-driver`'s generator now sets where the
      engine is MPP, Cedrus, rkvdec or Hantro: a sandbox around untrusted media given up. Decide:
      keep it, or find what the sandbox blocks (a device node, an ioctl) and allow only that.
- [ ] **A webcam's MJPEG decoded in hardware in a call**: a USB camera sends MJPEG at 720p and up,
      and WebKit captures through GStreamer, so `vajpegdec` through `tvb-va-driver` takes it where
      its JPEG decode works; Chromium and Firefox decode it on the CPU.

## Page start-up

YouTube's home page on the M2 Plus settles 22 s after Enter cold and 13 to 18 s warm (22 November):
9 s to the server's skeleton, then 13 s booting about 10 MB of script on one Cortex-A53 core,
parsing and running it while three cores sit mostly idle. Measured and ruled out, each within a
second of the baseline: JSC's JIT sooner (`JSC_thresholdForJITAfterWarmUp=100`), one compiler thread
each, the `performance` governor, Falkon's ad-blocker off, `-mtune=cortex-a53`, a Safari user agent.
JSC obeys the options: with its JIT off the cold load takes 31 s.

The public suites on the M2 Plus (23 November), each browser in a fresh profile on a headless
2256x1504 output at scale 1.5, Speedometer 10 iterations:

| Browser                    | Speedometer 3.1 | JetStream 2.2 |
| -------------------------- | --------------- | ------------- |
| Falkon                     | 0.778           | 22.40         |
| MiniBrowser, WPE WebKit    | 0.845           | 22.62         |
| Chromium 156, V8 and Blink | 1.02            | 25.46         |

Falkon's own cost is the ad-blocker (0.72 with it, 0.78 without, at 3 iterations); JetStream 3.0
runs in both WebKits (14.16 and 14.23) but not in Chromium, whose preload of its 466 MB fails. Ideas
to probe:

- [ ] **Chromium's time on the same box, as the target**: YouTube cold and warm in Debian's Chromium
      or in Falkon on QtWebEngine, so the gap to V8 is a number, and how much of it its code cache
      closes.
- [ ] **A bytecode cache for a page's scripts**: V8 keeps a script's compiled bytecode with the HTTP
      cache from about its second load, so a warm start skips most parsing and compiling; JSC
      compiles every script anew each visit. It has the machinery (Apple's `JSScript` caches
      bytecode), not the plumbing into the network cache. Parsing and bytecode generation were about
      a seventh of the main thread's time on YouTube's boot.
- [ ] **A script parsed off the main thread**: V8 streams a large script's parse and compile to
      other cores as it downloads; JSC parses on the main thread once it has it all.
- [ ] **WebKit built with profile-guided and link-time optimization**: an instrumented build run on
      YouTube and other heavy sites on a box, then a rebuild with the profile, as browsers ship;
      worth perhaps a tenth to a fifth on the engine's own code: parser, runtime, DOM, style.
- [ ] **YouTube kept resident**: a page already booted, throttled in the background, opens at once;
      a preload at idle after login would hide even the first boot. Costs a few hundred MB of the 4
      GB and a design for where the page lives.

## Falkon

- [ ] **The ad-blocker's generic hiding at its cost**: EasyList's 13,636 `##selector` rules become
      `css-display-none` on every page and frame, one stylesheet each style recalculation checks;
      Speedometer 3.1 on the M2 Plus scores 0.72 with it and 0.79 without, plain WebKit 0.82. To
      choose: drop generic hiding (network and site rules stay), or apply only the selectors whose
      classes and ids the page has, as uBlock Origin does.
- [ ] **A page's screen wake lock**: `navigator.wakeLock.request("screen")` is refused with
      `NotAllowedError` (seen in Speedometer), so a video site cannot keep the screen from blanking
      while it plays; QtWebEngine grants it, and `swayidle` would need the inhibit passed on.
- [ ] **Inspect Element at the clicked node**: Falkon's panel holds WebKit's own Web Inspector,
      Safari's: `setInspectedPage` shows it in the devtools page's view
      (`webkit_web_view_toggle_inspector`, the view WebKit makes taken into a `WebWidget`), tested
      against QtWebEngine and seen in Falkon on the H313 (Ctrl+Shift+I). Inspect Element opens the
      panel; selecting the clicked node has no call in WebKit's API.
- [ ] **Chrome extensions**: WPE 2.54's API reads an extension's manifest, permissions and icons
      only; running one needs WebKit's extension controller in its GLib API.
- [ ] **Printing**, built on nested event loops WebKit's API does not run.
- [ ] **Downloads paused and resumed, and Save Page's complete HTML**: WebKit's downloads do
      neither, and it saves a page as MHTML only.
- [ ] **Speed-dial thumbnails**, rendered through QtWebEngineQuick's QML today.
- [ ] **PyFalkon's plugins**, bound to PySide's WebEngine types.

## `qtwpewebkit`

- [ ] **A page frame on screen without a copy of its own**: `WebWidget` is a `QOpenGLWidget`, so
      each frame WebKit composited is drawn again into the widget's framebuffer, and Qt composes
      that into the window: a full-size pass on the GPU per frame that MiniBrowser does not make.
      WPE keeps each buffer's EGLImage (`WPEBufferDMABuf.cpp`); only the texture is rebound per
      frame.
- [ ] **AFBC for the page's buffers**: `qtwpewebkit` offers WebKit no formats or modifiers, so its
      buffers are linear; on Panfrost, AFBC would cut the bandwidth of each pass after.
- [ ] **Video on its own plane**: decoded pictures go through `glupload` and `glcolorconvert` (NV12
      to RGBA), WebKit's compositing, `qtwpewebkit`'s pass and the compositor's; WPE's hole-punch
      would put them on a display plane and spare every pass. In progress: `tvbvideoplanesink` hands
      the decoder's dma-buf to a subsurface under the page, labwc puts it on a plane; 4K60 at 48 to
      55 fps on the M2 Plus, and about one start in five freezes the video.
- [ ] **Video in AFBC on its plane**: `tvb-va-driver` can offer each decoder's own AFBC
      (`research/va-driver/afbc-detect.patch`), but GStreamer's `va` offers downstream only the
      linear modifier a plain surface exports (`sys/va/gstvacaps.c`); then `tvbvideoplanesink`
      taking `DMA_DRM` caps with it, and labwc putting it on the one plane that reads it (Cluster0
      on the RK3528). Less memory traffic at 4K60; Panfrost on the H313 samples AFBC too.
- [ ] **A texture per page buffer**: `WebWidget::paintGL` binds each frame's EGLImage to its one
      texture with `glEGLImageTargetTexture2DOES`; WPE keeps the EGLImage per buffer already, so a
      texture per buffer would leave nothing to rebind.
- [ ] **A scheme handler's reply read as it arrives**: `QWebEngineUrlRequestJob::reply()` reads its
      device once with `readAll()`; QtWebEngine reads as data comes, so a `QNetworkReply`, a process
      or a pipe not yet complete is cut short. Hand WebKit a stream fed by the device's `readyRead`
      instead.
- [ ] **A redirected main frame told on plain HTTP**: without fetch metadata a request is the main
      frame when its URL is the page's, which a redirect's target is not yet; a block on it then
      neither shows as the main frame's nor fails the load. Tell it by the navigation in flight.
- [ ] **One packaging helper for the extras**: `extras/librice/build.sh` and
      `extras/qtwpewebkit/build.sh` each carry `depends_of` and `deb`, near copies; qtwpewebkit's
      debs lack the copyright file librice's have. One helper under `extras/`, sourced by both.
- [ ] **The faster colour conversion, per board**: WebKit's GL sink turns each NV12 picture into an
      RGBA texture on the GPU (`glupload`, `glcolorconvert`); `WEBKIT_GST_DISABLE_GL_SINK=1` gives
      its fallback sink, `videoconvert` on the CPU with ORC's NEON. A weak GPU (Mali-450 on the M20)
      may lose to NEON, if the decoder's buffers are cached. Measure both on each board, 1080p60 and
      4K60, file and MSE, and set the faster in the session's environment. The CPU's cost is the
      read: fuseamp's NEON pass over Cedrus's uncached CAPTURE on the H313 takes 127 ms a 1080p
      picture, so the CPU path needs the decoder's buffers cacheable (its FFmpeg `0036`, `0037`; for
      WebKit, `tvb-va-driver`'s), and then a NEON NV12-to-RGB loop of its own if `videoconvert` is
      short. On the GPU, one full-frame pass is dear: fuseamp's measures 11.8 ms a 1080p picture on
      the H313's Mali-G31, 17.8 ms on the M20's Mali-450, so at 4K a second pass alone outruns a 60
      Hz frame. First find whether WebKit's `glcolorconvert` converts or passes NV12 through to its
      compositor's YUV shader; if it converts, fold the conversion into the compositor's draw, each
      plane imported as its own image (fuseamp's `GpuPictures.cpp`: luma and chroma at their own
      offsets and pitches in bytes, YUV to RGB in the shader), one pass. H313, 20 November, MSE: the
      GL sink shows 56.4 of 57.5 decoded at H.264 1080p60 and 47.2 of 60 at VP9 4K60; `videoconvert`
      13.1 and 0.6, its reads of the uncached CAPTURE: the H313 keeps the GPU.
- [ ] **AdBlock's first compile off the critical path**: on a profile without its cache, WebKit
      compiles Falkon's filter lists into content rules on one core for 40 seconds on the H313, from
      about 25 seconds after start (`ListStore Queue`); cached after, in
      `~/.cache/falkon/qtwpewebkit-content-filters`. Every list update pays it again.
      `qtwpewebkit`'s conversion now writes its JSON directly instead of through Qt's JSON objects:
      EasyList, 77,464 rules, in 2.4 s instead of 9.2 s on the M20, the same rules; WebKit's own
      compile after it remains.
- [ ] **AdBlock compiled per subscription, kept until it changes**: `qtwpewebkit` hashes all of
      Falkon's lists into one identifier and keeps only the latest compiled list, so any change, a
      custom rule even, recompiles EasyList's 77,000 rules, and a profile that applies its small
      lists before EasyList arrives deletes EasyList's compiled list. One compiled list per
      subscription, each kept until its text changes, compiles only what changed.
- [ ] **Shorter patterns for WebKit's content-rule compile**: every `||` rule starts with
      `^[a-z][a-z0-9+.-]*://([^/]*\.)?`, and `^` becomes a character class; WebKit builds its state
      machines from these, about 40 s of a core for EasyList on the H313. Measure the compile with
      simpler equivalent prefixes, as Safari's converters write them, before changing any.
- [ ] **A console message's line**: `javaScriptConsoleMessage` gets a page's messages with
      QtWebEngine's levels and texts, through the web process's `console-message-sent`, but line 0:
      without an inspector attached WebKit finds no caller frame for `console.log`. An
      off-the-record profile's page sends none, by WebKit's design.
- [ ] **Falkon rebuilt when `qtwpewebkit`'s ABI changes**: a member added to `QWebEnginePage` left
      the Falkon built before it unable to start against the new library, at the same `0.1.0`. Until
      1.0, Falkon needs an exact `libqtwpewebkit0` and a rebuild with it.
- [ ] **A stable ABI on QtWebEngine's Qt 6 API, as 1.0**: each public class's state behind a
      d-pointer, as Qt keeps it, so a fix never changes a class's size; soname 1 frozen, and the
      tests checking the exported symbols and class sizes against it.

## Release

- [ ] **Packages**: `extras/qtwpewebkit` and `extras/falkon` build `libqtwpewebkit0`,
      `libqtwpewebkit-dev` and Falkon as Debian's `falkon` on them; shipped once YouTube plays on
      every family, before the desktop that recommends Falkon.
- [ ] **`extras/wpewebkit` built in CI** with a compiler cache that holds WebKit: about 30 minutes
      and 24 GB of memory cold.
- [ ] **`patches/wpewebkit` upstream, first of all**: each one carried is a WebKit build ours to
      keep warm; the extra retires with the last. `0001` and `0003` to `0009`, so the extra retires
      once Debian ships them; `0002` is WebKit 2.56's already. Each first checked against WebKit's
      main branch, then sent as a bug with a layout or API test. Likely taken: `0001` (MPP's devices
      bound as the sandbox binds `/dev/mali`), `0005` and `0006` (they tighten security), `0007` and
      `0008` (one window per user activation, as the spec and Chromium). A new API needs its use:
      `0004`. Doubtful: `0003`, a script's DOM node as an empty object, QtWebEngine's behaviour
      rather than a bug. `0009` goes as a bug report, its fix the floor found from the stream
      (above), not 32 MiB. Falkon's own (`patches/falkon`: the `FALKON_WPE` build switch, AdBlock
      through content blockers) go to KDE next, so Debian's Falkon builds on qtwpewebkit without
      ours. Against WebKit's main, 20 November 2026: `0009` is fixed upstream another way, pause at
      20 MiB and resume at 2 MiB (bug 322499, PR 72408): drop ours, backport it, check the H313's
      4K. `0008` is half fixed by PR 75999 (a forced gesture no longer revokes the user's): backport
      it, then see whether ours is still needed. `0001` goes as a follow-up to bug 311007 (V4L2 in
      the sandbox), rebased. `0004` as "is-popup too late in create", after bug 325290, with a
      `TestUIClient.cpp` test. `0007` with a layout test on bug 248767. `0003`, `0005`, `0006`
      reverse upstream choices (JS handles; bug 271345; Apple's reverted CORS enforcement): opt-in
      API, or kept in qtwpewebkit instead.
