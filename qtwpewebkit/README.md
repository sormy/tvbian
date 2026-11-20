# QtWpeWebKit

QtWebEngine's API over [WPE WebKit](https://wpewebkit.org): a Qt browser that renders on GLES 2
GPUs, which Chromium, QtWebEngine and Firefox have left for GLES 3. WPE WebKit still renders with
GLES 2 and plays video through GStreamer's hardware decoders; QtWpeWebKit puts it in Qt.

## Where it runs

| Box             | SoC, GPU                   | Falkon on it                                         |
| --------------- | -------------------------- | ---------------------------------------------------- |
| H96 Max M2 Plus | RK3528, Mali-450 on Lima   | browses, YouTube; H.264, HEVC and VP9 4K60 full rate |
| H96 Max H313    | H313, Mali-G31 on Panfrost | H.264 1080p60 full rate; VP9 4K60 decoded at 60      |
| H96 Max M20     | S905L3, Mali-450 on Lima   | HEVC 1080p60 full rate                               |

Any GPU with EGL and dma-buf import should do; without one, frames come by CPU.

## How

- `src/`: WPE's platform (display, toplevel, view, input) on Qt's, in process. WebKit's frames
  arrive as dma-bufs, imported as EGLImages and drawn in a `QOpenGLWidget`
  (`Qt::AA_ShareOpenGLContexts`).
- `compat/`: QtWebEngine's classes by name, so an application ports by a build switch; Falkon's
  patches are in `patches/falkon/`.
- `webprocess/`: a web-process extension for what WebKit's API does not ask the UI process
  (`docs/interception.md`).
- Needs WPE WebKit 2.54 with WPEPlatform: `extras/wpewebkit` builds it until Debian has it.

## Build and test

```sh
cmake -S qtwpewebkit -B build -G Ninja -DBUILD_TESTING=ON
cmake --build build
build/qtwpewebkit-demo https://wpewebkit.org
qtwpewebkit/tests/run.sh build   # each test against QtWebEngine and QtWpeWebKit
```

A test fails only where QtWebEngine passes; `tests/known-gaps.txt` lists what WebKit cannot do.
Needs Qt 6 (Widgets, OpenGLWidgets, WebChannel), EGL and GLES 2; the tests also QtWebEngine.
